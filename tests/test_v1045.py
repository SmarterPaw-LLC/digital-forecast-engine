# -*- coding: utf-8 -*-
"""
v10.44 / v10.45 — Chewy fulfillment as a COGS building block, and the category
visibility bug that hid a product whose sub-category was visibly checked.

Jason:
  "what is chewy pulling from for cogs? the cogs field is empty. we should
   default chewy fulfilment to $.03"
  "i don't know why buds jar is being hidden based on these filter criteria.
   when i remove the category visibility tag, it appears, but it wasn't one of
   the hidden sub-categories"

⚠ THE CATEGORY-VISIBILITY BUG. The universe of sub-categories was the DISTINCT
RAW `categories.subcategory` values, so 'Jar' and 'Jar ' were two separate
rows — and HTML collapses the trailing space, so the checkbox list rendered
them IDENTICALLY. Uncheck one and a product carrying the other variant vanishes
while the list still shows a checked "Jar". Reproduced below against the real
predicate, then asserted fixed.

⚠ The reason Jason could not answer this himself is the other half: the Active
filters panel said "3 sub-categories hidden" and never said WHICH three. That
panel exists (v10.34) to answer "why did this product vanish". It names them now.
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
src = io.open(os.path.join(ROOT, 'index.html'), encoding='utf-8', newline='').read()
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
    d, j = 0, i
    while j < len(js):
        if js[j] == '{':
            d += 1
        elif js[j] == '}':
            d -= 1
            if d == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1]


# ═════════ A. v10.44 — the Chewy building block ═════════
print('\nA. static — fulfillment_chewy')
SQLF = os.path.join(ROOT, 'supabase_v10_44_fulfillment_chewy.sql')
ok(os.path.exists(SQLF), 'migration file exists')
sql = io.open(SQLF, encoding='utf-8').read() if os.path.exists(SQLF) else ''
ok('add column if not exists fulfillment_chewy' in sql.lower(), 'idempotent add column')
ok('default 0.03' in sql.lower(), 'defaults to $0.03, as asked')
ok('update product_cogs' in sql.lower() and 'is null' in sql.lower(),
   '  and backfills rows inserted with an explicit NULL')

# ⚠ ONE declaration. The two formulas were copy-pasted across seven sites and
# Chewy would have been an eighth copy — which is how duplicated formulas fall
# out of step.
decl = js[js.index('const COGS_DERIVED_INPUTS'):]
decl = decl[:decl.index('};') + 2]
ok("chewy_cogs:" in decl, 'chewy_cogs is a derived total now')
ok("'landed_cost', 'fulfillment_chewy', 'production_labor'" in decl,
   '  = landed + fulfill(Chwy) + labor, mirroring Amazon')
ok('amazon_cogs_eu' not in decl, 'Amazon EU stays manual (own freight + duty)')
for inline in ["sumOrNull('landed_cost', 'fulfillment_amazon', 'production_labor')",
               "sumOrNull('landed_cost', 'overhead_dtc', 'fulfillment_dtc', 'shipping_cost', 'production_labor')"]:
    ok(js.count(inline) == 0, 'no site restates a formula inline')
ok(js.count('COGS_DERIVED_INPUTS.chewy_cogs') >= 6,
   'every derive site computes Chewy too (found %d)' % js.count('COGS_DERIVED_INPUTS.chewy_cogs'))

# The surfaces that have to know about a new building block.
# These payloads ENUMERATE every cost field to preserve the ones the operation
# is not changing. A field missing from the list is written as absent, i.e. the
# upsert NULLS it. The suite caught exactly that on the first pass: bulk edit
# would have wiped fulfillment_chewy on every row it touched. Same class as
# Architecture Rule #8, one level down - a new COLUMN means auditing every site
# that enumerates columns, not just the ones that read the new value.
for _f in ['cogsBulkApply', 'cogsEditSave', 'cogsApplyBom', 'cogsCommitDerivedVisible', 'uploadCogsCSV']:
    _b = fn(_f)
    ok('fulfillment_chewy' in _b, '%s preserves fulfillment_chewy' % _f)
    ok(_b.count('fulfillment_chewy') <= _b.count('fulfillment_dtc'),
       '  and does not duplicate the key')
# ⚠ There is deliberately NO next_fulfillment_chewy: the v8.46 modeling columns
# are their own set and v10.44 did not add one. Writing that key would fail the
# upsert outright with "column does not exist".
# ⚠ Match the KEY, not the word. The comment at the preview call site names
# next_fulfillment_chewy to explain why it is absent, and matching that instead
# of a real reference is the v10.26 trap.
ok(not re.search(r'next_fulfillment_chewy\s*:', js),
   'nothing writes a next_fulfillment_chewy key (no such column)')
ok('COGS_DERIVED_INPUTS.chewy_cogs' in fn('applyCogsPreview'),
   'the COGS preview re-derives Chewy too')
# ⚠ v10.48 REVERSES this one. v10.45 had fulfillment_chewy rolling up per-unit
# alongside fulfillment_amazon. Both are FLAT per bundle (one shipment, one
# charge), which is what Jason flagged: "fulfillment amazon and fulfillment
# chewy are flat rate - they should not update from BOM". The assertion moves
# to the new guarantee rather than being deleted.
flat = js[js.index('const COGS_FLAT_PER_BUNDLE'):]
flat = flat[:flat.index(')')]
ok('fulfillment_chewy' in flat, 'fulfillment_chewy is FLAT per bundle, never BOM-summed')
ok('fulfillment_amazon' in flat, '  and so is fulfillment_amazon')
ok('shipping_cost' in flat, '  alongside shipping_cost (the v6.27 fix it now joins)')
ok('id="pf-cb-fulfill-chewy"' in src, 'the product card has the input')
ok("'pf-cb-fulfill-chewy':'fulfillment_chewy'" in js.replace(' ', ''), '  mapped to the column')
ok('Fulfill Chwy' in src, 'the COGS table has the column')
# The summable set is now DERIVED from the flat set, so the two cannot drift.
ok('new Set(COGS_BUILDING_BLOCKS.filter(f => !COGS_FLAT_PER_BUNDLE.has(f)))' in js,
   'the BOM-summable blocks are derived from it, not restated')

print('\nA2. static — what Chewy COGS was actually pulling from')
cpc = fn('chewyPnlCogs')
ok('c.chewy_cogs ?? c.landed_cost' in cpc, 'the fallback chain is unchanged')
ok('bare landed cost' in cpc or 'no fulfillment' in cpc,
   '  and the comment records what the fallback was costing us')


# ═════════ B. v10.45 — the category-visibility bug ═════════
print('\nB. behaviour — catVisPass (the real predicate)')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

// Jason's catalog shape: one row carries a trailing space on the sub-category.
let allCategories = [
  { id: 1, category: 'Blends',      subcategory: 'Jar ' },      // <- the trap
  { id: 2, category: 'Blends',      subcategory: 'Jar'  },
  { id: 3, category: 'Clamshells',  subcategory: 'Rollies' },
  { id: 4, category: 'Other',       subcategory: 'Apparel' },
];
let catVisConfig = {};
let _catVisCache = {};
let _catVisIdMap = null;
let _catVisUniv = null;
const CATVIS_GLOBAL = '_global';
const _catVisSuppressed = new Set();
function catVisInvalidate() { _catVisCache = {}; _catVisIdMap = null; _catVisUniv = null; }

//<<INVISIBLE>>
//<<SPACES>>
//<<NORM>>
//<<MATCHKEY>>
//<<DEDUPE>>
//<<UNIVERSE>>
//<<SETHAS>>
//<<IDMAP>>
//<<RESOLVED>>
//<<PASS>>
//<<ALLCATS>>
//<<ALLSUBS>>
//<<HIDDEN>>
//<<NAMELIST>>
//<<SUMMARY>>

// ⚠ THE UNIVERSE DE-DUPLICATES. Before v10.45 this returned ['Apparel','Jar',
// 'Jar ','Rollies'] — four rows, two of which render IDENTICALLY in the
// checkbox list because HTML collapses the trailing space.
t('the sub-category universe is trimmed and de-duplicated',
  catVisAllSubcats(), ['Apparel', 'Jar', 'Rollies']);
t('  and so is the category universe', catVisAllCats(), ['Blends', 'Clamshells', 'Other']);

// Jason's exact situation: Apparel hidden, everything else visible, and the
// product sits on the categories row whose sub-category carries the space.
catVisConfig['products'] = { cats: null, subcats: ['Jar', 'Rollies'] };
catVisInvalidate();
const budsJar = { master_id: 'SP-1', category_id: 1 };   // 'Jar ' row
t('a product on the whitespace variant is VISIBLE when "Jar" is checked',
  catVisPass('products', budsJar), true);
t('  and so is one on the clean variant', catVisPass('products', { category_id: 2 }), true);
t('  while a genuinely hidden sub-category still hides',
  catVisPass('products', { category_id: 4 }), false);

// The reverse direction: a STORED set written before v10.45 can itself hold an
// untrimmed name. Trimming only the incoming value would not be enough.
catVisConfig['products'] = { cats: null, subcats: ['Jar ', 'Rollies'] };
catVisInvalidate();
t('an untrimmed name in the STORED set still matches a clean product',
  catVisPass('products', { category_id: 2 }), true);

// Records rows carry the names directly rather than an id.
catVisConfig['products'] = { cats: null, subcats: ['Jar'] };
catVisInvalidate();
t('a records-shaped row with a padded name passes',
  catVisPass('products', { category: 'Blends', subcategory: ' Jar ' }), true);

// Unchanged guarantees.
t('an unclassifiable row stays visible', catVisPass('products', { master_id: 'x' }), true);
t('  and so does a null object', catVisPass('products', null), true);
catVisConfig['products'] = { cats: null, subcats: null };
catVisInvalidate();
t('nothing hidden -> everything passes', catVisPass('products', { category_id: 4 }), true);

// ⚠ NAMING. "3 sub-categories hidden" is the answer to a question nobody
// asked. This is the half that would have let Jason answer it himself.
catVisConfig['products'] = { cats: null, subcats: ['Jar'] };
catVisInvalidate();
const h = catVisHiddenCount('products');
t('the hidden count reports the NAMES', h.subNames, ['Apparel', 'Rollies']);
t('  and the count still matches', h.subs, 2);
t('the Active-filters summary names them',
  catVisSummaryNamed('products'), 'hiding sub Apparel, Rollies');
t('  the long list is capped rather than becoming a paragraph',
  catVisNameList(['a','b','c','d','e','f'], 4), 'a, b, c, d +2 more');
t('  and a short one is not', catVisNameList(['a','b'], 4), 'a, b');
t('nothing hidden says so', (catVisConfig['products'] = { cats: null, subcats: null },
  catVisInvalidate(), catVisSummaryNamed('products')), 'nothing hidden');

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
def constline(name):
    m = re.search(r'^const %s\s*=.*$' % re.escape(name), js, re.M)
    if not m:
        raise SystemExit('FAIL: cannot find const %s' % name)
    return m.group(0)

for tok, body in [('INVISIBLE', constline('_CATVIS_INVISIBLE')),
                  ('SPACES', constline('_CATVIS_SPACES')),
                  ('MATCHKEY', fn('catVisMatchKey')),
                  ('DEDUPE', fn('_catVisDedupe')),
                  ('UNIVERSE', fn('catVisUniverse')),
                  ('NORM', fn('catVisNorm')), ('SETHAS', fn('catVisSetHas')),
                  ('IDMAP', fn('catVisIdMap')), ('RESOLVED', fn('catVisResolved')),
                  ('PASS', fn('catVisPass')), ('ALLCATS', fn('catVisAllCats')),
                  ('ALLSUBS', fn('catVisAllSubcats')), ('HIDDEN', fn('catVisHiddenCount')),
                  ('NAMELIST', fn('catVisNameList')), ('SUMMARY', fn('catVisSummaryNamed'))]:
    marker = '//<<%s>>' % tok
    if harness.count(marker) != 1:
        raise SystemExit('FAIL: placeholder %s appears %d times' % (marker, harness.count(marker)))
    harness = harness.replace(marker, body, 1)

tmp = os.path.join(tempfile.gettempdir(), 'test_v1045_catvis.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('catVis behaviour')


# ═════════ C. the regression guard ═════════
print('\nC. behaviour — the pre-v10.45 predicate really did hide it')

guard = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label); }
};
// ⚠ Reproduce the OLD behaviour rather than describe it. Without this the fix
// above could be asserting something that was never broken.
const ROW = { category: '', subcategory: '', category_id: 1 };
const IDMAP = new Map([[1, { category: 'Blends', subcategory: 'Jar ' }]]);
const VISIBLE = new Set(['Jar', 'Rollies']);      // what the checkbox list showed

function oldPass(obj) {
  let cat = obj.category || '';
  let sub = obj.subcategory || '';
  if ((!cat || !sub) && obj.category_id != null) {
    const row = IDMAP.get(obj.category_id);
    if (row) { cat = cat || row.category || ''; sub = sub || row.subcategory || ''; }
  }
  if (!cat && !sub) return true;
  if (VISIBLE && sub && !VISIBLE.has(sub)) return false;
  return true;
}
t('the pre-v10.45 predicate HID a product whose sub-category read as checked',
  oldPass(ROW), false);
// And the universe really did carry both variants.
const oldUniverse = [...new Set(['Jar ', 'Jar', 'Rollies'])].sort();
t('  because the universe held both variants', oldUniverse.length, 3);
console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1045_guard.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(guard)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip()[:1200])
    fails.append('regression guard')


# ═════════ D. the checkbox id collision ═════════
print('\nD. static — checkbox ids cannot collide')
ctrl = fn('catVisRenderControls')
ok("'cv_' + kind + '_' + i" in ctrl, 'ids are index-based')
ok("replace(/[^a-z0-9]/gi, '_')" not in ctrl,
   "  not the name with punctuation stripped ('Stick n Lick' / 'Stick-n-Lick' collided)")
ok('catVisSetHas(wc, v)' in ctrl and 'catVisSetHas(ws, v)' in ctrl,
   'the checked state tolerates whitespace on either side')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.44 / v10.45 — all green')
