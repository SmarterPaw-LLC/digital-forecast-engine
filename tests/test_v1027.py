# -*- coding: utf-8 -*-
"""
v10.27 — Products bulk edit: 7 fields → 17, and the records[] staleness bug.

Jason: "why is this all that i can bulk edit? i should be able to bulk edit
other attributes, like categorie, sub category, active, seasonal ect"

Two things were true at once:

  * Sub-category was ALREADY bulk-editable and badly labelled. category_id is
    a FK to a (category, subcategory) PAIR and prodBulkCatOpts already rendered
    "Category / Sub-category" in the options — the field was just called
    "Category", so there was no way to know.
  * The list genuinely stopped short of the flags and supply fields.

⚠ And the bug worth the most: the bulk apply mirrored only into allProducts,
never into records[]. That is the v7.34 staleness bug living in the bulk path —
bulk-set `in-house production` on 40 SKUs and Inventory Planning would keep
filtering on the old value until a full page reload.

The assertion that earns its keep is the ROUND TRIP: every option in the field
dropdown must produce a working value editor, and every field the editor knows
about must be reachable from the dropdown. Either gap ships a dead menu entry.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)

fails = []
def ok(cond, label):
    if cond:
        print('  ok  ' + label)
    else:
        print('  FAIL ' + label)
        fails.append(label)


def fn(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m:
        raise SystemExit('FAIL: cannot find %s' % name)
    i = js.index('{', m.end() - 1)
    depth, j = 0, i
    while j < len(js):
        if js[j] == '{':
            depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1]


def const_obj(name):
    m = re.search(r'\nconst %s = \{' % re.escape(name), js)
    if not m:
        raise SystemExit('FAIL: cannot find const %s' % name)
    i = js.index('{', m.end() - 1)
    depth, j = 0, i
    while j < len(js):
        if js[j] == '{':
            depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1] + ';'


# The dropdown lives in a template literal inside prodOpenBulkEdit.
opener = fn('prodOpenBulkEdit')
FIELD_OPTS = re.findall(r'<option value="([a-z_]+)">', opener)


# ═════════ A. the field list ═════════
print('\nA. the field list — what Jason asked for is actually there')

EXPECTED = [
    'brand', 'category_id', 'seasonal_type',
    'active', 'seasonal', 'in_house_production', 'is_top_product', 'is_bundle',
    'fulfillment_amazon',
    'msrp', 'wholesale',
    'supplier', 'case_qty', 'lead_time_days', 'safety_stock',
    'notes', 'forecast_notes',
]
for f in EXPECTED:
    ok(f in FIELD_OPTS, 'offers %s' % f)
ok(len(FIELD_OPTS) == len(set(FIELD_OPTS)), 'no duplicate options')
ok(len(FIELD_OPTS) >= 17, 'grew from 7 to %d fields' % len(FIELD_OPTS))
ok(opener.count('<optgroup') >= 5, 'grouped so the dropdown stays scannable')

# ⚠ Sub-category was always reachable; it just did not say so. Both halves of
# that fix are asserted — the label, and the hint that explains the pairing.
ok('Category / Sub-category' in opener, 'the category option names the sub-category too')
changer = fn('prodBulkFieldChange')
ok('category + sub-category pair' in changer,
   'and the editor says picking one sets both')

# Identifiers must stay OUT — they are unique per product.
for f in ['sp_sku', 'asin', 'shopify_sku', 'chewy_sku', 'barcode', 'master_id', 'title']:
    ok(f not in FIELD_OPTS, 'does NOT offer the unique identifier %s' % f)


# ═════════ B. round trip — no dead menu entries ═════════
print('\nB. round trip — every option has an editor, every editor is reachable')

h1 = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

let FIELD = 'brand';
const WRAP = { innerHTML: '' };
const document = { getElementById: id =>
  id === 'prod-bulk-field' ? { value: FIELD } :
  id === 'prod-bulk-value-wrap' ? WRAP : null };
const allCategories = [{ id: 1, category: 'Toys', subcategory: 'Teasers' }];
function prodBulkCatOpts() { return '<option value="1">Toys / Teasers</option>'; }

BOOLS
INTS
CHANGE

const FIELDS = __FIELDS__;
const noEditor = [], leaked = [], noLabel = [];
for (const f of FIELDS) {
  FIELD = f; WRAP.innerHTML = '';
  try { prodBulkFieldChange(); } catch (e) { noEditor.push(f + ' (threw: ' + e.message + ')'); continue; }
  // Every editor MUST produce the input prodBulkApply reads from, or the
  // option is a dead menu entry that silently writes null.
  if (!/id="prod-bulk-value"/.test(WRAP.innerHTML)) noEditor.push(f);
  if (/undefined|NaN|\[object/.test(WRAP.innerHTML)) leaked.push(f);
  if (!/<label/.test(WRAP.innerHTML)) noLabel.push(f);
}
t('every option produces a prod-bulk-value input', noEditor, []);
t('no option leaks undefined/NaN into its editor', leaked, []);
t('every option is labelled', noLabel, []);

// The two structural warnings are present where they matter.
FIELD = 'is_bundle'; prodBulkFieldChange();
t('is_bundle warns it is structural', /BOM/.test(WRAP.innerHTML), true);
FIELD = 'notes'; prodBulkFieldChange();
t('notes warns it overwrites rather than appends', /does not append/.test(WRAP.innerHTML), true);
FIELD = 'forecast_notes'; prodBulkFieldChange();
t('  same for forecast notes', /does not append/.test(WRAP.innerHTML), true);

// Int fields get step=1 — a fractional case qty or lead time is nonsense.
for (const f of ['case_qty', 'lead_time_days', 'safety_stock']) {
  FIELD = f; prodBulkFieldChange();
  t(f + ' is a whole-number input', /step="1"/.test(WRAP.innerHTML), true);
}
FIELD = 'msrp'; prodBulkFieldChange();
t('msrp still allows cents', /step="0.01"/.test(WRAP.innerHTML), true);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
h1 = (h1.replace('BOOLS', const_obj('PROD_BULK_BOOL_FIELDS'))
        .replace('INTS', const_obj('PROD_BULK_INT_FIELDS'))
        .replace('CHANGE', changer)
        .replace('__FIELDS__', repr(FIELD_OPTS).replace("'", '"')))
tmp1 = os.path.join(tempfile.gettempdir(), 'test_v1027_editor.js')
io.open(tmp1, 'w', encoding='utf-8', newline='').write(h1)
r1 = subprocess.run(['node', tmp1], capture_output=True, text=True, encoding='utf-8')
print(r1.stdout.rstrip())
if r1.returncode != 0:
    print(r1.stderr.rstrip())
    fails.append('editor round trip')

# The reverse direction: a field the editor special-cases but the dropdown
# never offers is unreachable code pretending to be a feature.
bools = set(re.findall(r'^\s{2}([a-z_]+):', const_obj('PROD_BULK_BOOL_FIELDS'), re.M))
ints = set(re.findall(r'^\s{2}([a-z_]+):', const_obj('PROD_BULK_INT_FIELDS'), re.M))
ok(bools <= set(FIELD_OPTS), 'every boolean field is reachable from the dropdown')
ok(ints <= set(FIELD_OPTS), 'every int field is reachable from the dropdown')


# ═════════ C. the records[] mirror — the real bug ═════════
print('\nC. records[] mirror — the v7.34 staleness bug in the bulk path')

applier = fn('prodBulkApply')
ok('prodBulkMirrorToRecords' in applier, 'bulk apply mirrors into records[]')
ok('renderInventoryTbl' in applier, 'and repaints the surfaces that read it')

h2 = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
const allCategories = [{ id: 7, category: 'Toys', subcategory: 'Teasers' }];
let records = [];
const mk = (mid, region, over) => Object.assign({
  master_id: mid, region, brand: 'Meowijuana', active: true, seasonal: false,
  seasonal_type: 'standard', is_bundle: false, in_house_production: false,
  is_top_product: false, fulfillment_amazon: 'FBA', case_qty: 0, supplier: '',
  msrp: 9.99, category_id: 1, category: 'Old', subcategory: 'Old',
  lead_time_days: 60, lead_time_src: 'default',
  safety_stock: 14, safety_src: 'default',
}, over || {});

MIRROR

// Two regions of the SAME product -> both must move. A per-region record left
// behind is exactly how Inventory Planning goes stale.
records = [mk('SP-1', 'US'), mk('SP-1', 'CA'), mk('SP-2', 'US')];
prodBulkMirrorToRecords(['SP-1'], 'in_house_production', true);
t('every region of the edited product moves',
  records.map(r => r.in_house_production), [true, true, false]);

records = [mk('SP-1', 'US')];
prodBulkMirrorToRecords(['SP-1'], 'fulfillment_amazon', 'fbm');
t('fulfillment normalises to upper case', records[0].fulfillment_amazon, 'FBM');

records = [mk('SP-1', 'US')];
prodBulkMirrorToRecords(['SP-1'], 'case_qty', '12');
t('case qty coerces to a number', records[0].case_qty, 12);

records = [mk('SP-1', 'US')];
prodBulkMirrorToRecords(['SP-1'], 'category_id', 7);
t('category_id also refreshes the resolved names',
  [records[0].category_id, records[0].category, records[0].subcategory], [7, 'Toys', 'Teasers']);

records = [mk('SP-1', 'US')];
prodBulkMirrorToRecords(['SP-1'], 'category_id', 999);   // id that no longer exists
t('an unknown category clears the names rather than leaking undefined',
  [records[0].category, records[0].subcategory], ['', '']);

// ⚠ THE guard. records resolve lead time as (inventory.X ?? products.X), so a
// region that has its own override must survive a master-level bulk edit.
records = [mk('SP-1', 'US', { lead_time_days: 21, lead_time_src: 'region' }),
           mk('SP-1', 'CA', { lead_time_days: 60, lead_time_src: 'default' })];
prodBulkMirrorToRecords(['SP-1'], 'lead_time_days', 45);
t('a region override is NOT stomped by a master-level edit',
  records.map(r => [r.lead_time_days, r.lead_time_src]), [[21, 'region'], [45, 'product']]);

records = [mk('SP-1', 'US', { safety_stock: 7, safety_src: 'region' }),
           mk('SP-1', 'CA')];
prodBulkMirrorToRecords(['SP-1'], 'safety_stock', 30);
t('  same for safety stock', records.map(r => r.safety_stock), [7, 30]);

// Clearing falls back to the built-in default, and says so.
records = [mk('SP-1', 'US')];
prodBulkMirrorToRecords(['SP-1'], 'lead_time_days', null);
t('clearing lead time returns to the 60d default',
  [records[0].lead_time_days, records[0].lead_time_src], [60, 'default']);

// Fields records[] does not carry are a silent no-op, not a crash.
records = [mk('SP-1', 'US')];
let threw = false;
try { prodBulkMirrorToRecords(['SP-1'], 'wholesale', 4.5); } catch (e) { threw = true; }
t('a field records[] does not carry is a safe no-op', threw, false);
try { prodBulkMirrorToRecords(['SP-1'], 'notes', 'x'); } catch (e) { threw = true; }
t('  same for notes', threw, false);

// Degenerate inputs.
for (const args of [[[], 'brand', 'X'], [['nope'], 'brand', 'X']]) {
  let th = false;
  records = [mk('SP-1', 'US')];
  try { prodBulkMirrorToRecords(...args); } catch (e) { th = true; }
  t('no throw on ' + JSON.stringify(args[0]), th, false);
}
t('  and an unmatched id changes nothing', records[0].brand, 'Meowijuana');

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
h2 = h2.replace('MIRROR', fn('prodBulkMirrorToRecords'))
tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1027_mirror.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip())
    fails.append('records mirror behaviour')


# ═════════ D. parsing ═════════
print('\nD. parsing — each field type lands in the right shape')

ok("if (PROD_BULK_BOOL_FIELDS[field])" in applier,
   'booleans parse off the map, not a hardcoded pair')
ok("PROD_BULK_INT_FIELDS[field]" in applier and 'parseInt(raw, 10)' in applier,
   'int fields use parseInt, not parseFloat')
ok("field === 'is_bundle' && !confirm" in applier,
   'flipping is_bundle asks first — it is structural')
ok("field === 'seasonal_type' || field === 'fulfillment_amazon'" in applier,
   'enum fields keep their raw string rather than being nulled when falsy')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.27 — all green')
