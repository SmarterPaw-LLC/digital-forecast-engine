# -*- coding: utf-8 -*-
"""
v10.41 / v10.42 — Break-Even column parity, and COGS on the product card.

Jason:
  "the chewy and amazon break even have different metrics - i understand why,
   but i would at least like the same columns to appear where similar measures
   overlap (in addition to blake's columns)"
  "i should be able to set cogs costs on the product card modal"

⚠ Blake's 60 Amazon columns are untouched. The two the Amazon tab gains are
computed in JS (the v10.23 call), so the `.sql` file and its embedded twin stay
byte-identical and the v10.19 drift guard keeps comparing like for like. That
is asserted, because adding them to the SQL is the obvious wrong move.

⚠ VOCABULARY. Chewy BE called `net - cogs` "Contrib/u" while the Cost to Chewy
tab calls the IDENTICAL number "GM $/u", one tab away. That is the v10.22
mistake and I introduced it in v10.36. Asserted that only one name survives.
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
sqlf = io.open(os.path.join(ROOT, 'query_amazon_breakeven_acos.sql'), encoding='utf-8').read()

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


be = js[js.index('function renderChewyBreakeven'):]
be = be[:be.index('function chewyBeShowGap')]
# v10.54 renamed the registry to ALL_COLS (COLS is now the filtered subset). The
# measure-parity assertions are about what the tab CAN show, so they read the
# full registry.
cols = js[js.index('const CHEWY_BE_COLUMNS = ['):]
cols = cols[:cols.index('\n  ];')]


# ═════════ A. the overlapping measures now exist on both tabs ═════════
print('\nA. static — overlapping measures, both directions')

# Amazon had these; Chewy now does too.
PAIRS = [
    # v10.53 scoped both labels: the bare forms live on the Chewy Sales tab over
    # ALL sell-through units, while these two are ad-driven units only. Same
    # measures as the Amazon columns beside them; the prefix names the scope.
    ('ourRev',        'Ad Our Rev',        'Net Sales window'),
    ('vendorContrib', 'Ad Vendor Contrib', 'Contribution Profit'),
    ('gmPct',         'GM %',          'Contribution %'),
    ('beAcos',        'BE ACOS %',     'Break Even ACOS pct'),
    ('actualAcos',    'Actual ACOS %', 'Actual ACOS pct'),
]
for key, label, amz in PAIRS:
    row = [l for l in cols.split('\n') if "key: '%s'" % key in l]
    ok(bool(row), 'Chewy has %s (Amazon: %s)' % (label, amz))
    ok(bool(row) and "label: '%s'" % label in row[0], '  labelled %s' % label)
    ok('"%s"' % amz in sqlf, '  Amazon really does emit %s' % amz)

# Chewy had these; Amazon now does too — computed in JS, not SQL.
amz_fn = fn('breakevenAttachAdUnitEcon')
ok("'Ad Cost / Unit'" in js, 'Amazon has Ad Cost / Unit (Chewy: Cost/unit)')
ok("'ACOS Headroom pts'" in js, 'Amazon has ACOS Headroom pts (Chewy: Headroom)')
ok("r['Actual Ad Spend window']" in amz_fn and "r['Net Units window']" in amz_fn,
   '  built from columns the query already returns')
ok("r['Break Even ACOS pct']" in amz_fn and "r['Actual ACOS pct']" in amz_fn,
   '  headroom from the two ACOS columns')
# ⚠ The v10.19 drift guard compares the .sql file against the embedded copy.
# Adding these to the SQL would have been the obvious wrong move.
ok('Ad Cost / Unit' not in sqlf and 'ACOS Headroom' not in sqlf,
   'neither was added to the SQL (the v10.19 drift guard stays intact)')
ok('breakevenAttachAdUnitEcon()' in fn('runBreakeven'), '  and the helper is called on every run')
# Blake's columns are all still there.
blake = ['Break Even ACOS pct', 'Break Even ROAS', 'Non-Ad Profit', 'Total Cost',
         'Should be FBA Fee', 'Confidence Flag', 'Contribution %', 'Stock Cover Months']
for c in blake:
    ok('"%s"' % c in sqlf, "Blake's column survives: %s" % c)


# ═════════ B. vocabulary — one name per number ═════════
print('\nB. static — vocabulary')
# `net - cogs` is "GM $/u" on the Cost to Chewy tab. v10.36 called it
# "Contrib/u" on the Break-Even tab — a second word for a number the app
# already names (the v10.22 rule).
ok("label: 'GM $/u'" in cols, 'Chewy Break-Even uses the Cost tab name: GM $/u')
ok("label: 'Contrib/u'" not in cols, '  and the coined name is gone')
ok("label: 'GM $/u'" in js[js.index('function renderChewyPnlCost'):][:40000]
   or 'GM $/u' in js, '  which is the Cost to Chewy tab name')
gm_row = [l for l in cols.split('\n') if "key: 'contribution'" in l][0]
ok('Non-Ad Profit' in gm_row, "  the tooltip names Amazon's word for the same concept")
ok('Non-Ad Profit' in sqlf, "  and Blake's column is NOT renamed")


# ═════════ C. the min-units gate (Amazon's Confidence Flag analogue) ═════════
print('\nC. static — low volume is dimmed, not hidden')
ok('id="chpnl-be-minunits"' in src, 'Chewy has a Min units control')
ok("getElementById('chpnl-be-minunits')" in be, '  read by the renderer')
ok('lowVol' in be and 'opacity:.5' in be, '  low-volume rows are dimmed')
ok('rows.push' in be and 'lowVol' not in be[:be.index('rows.push')],
   '  and NOT filtered out (a 3-unit SKU is noise, not a loser)')


# ═════════ D. behaviour — the new measures ═════════
print('\nD. behaviour — chewyBreakevenEcon (the real function)')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
const near = (label, got, want, tol) => {
  if (got != null && Math.abs(got - want) <= (tol || 0.005)) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + got + ', want ~' + want); }
};

ECON

// Jason's own row: wholesale backed out so contribution lands on $2.60.
//   list 8.99 · allowances 24.5% · contribution 2.60
//   spend 4517.15 · direct 19397.10 · autoship 3289.12 · units 2129
const W = (2.60 + 1.00) / (1 - 0.245);          // wholesale that yields 2.60 at cogs 1.00
let e = chewyBreakevenEcon({
  wholesale: W, cogs: 1.00, standingPct: 24.5, listPrice: 8.99,
  spend: 4517.15, directSales: 19397.10, autoshipSales: 3289.12, directUnits: 2129 });
near('contribution per unit', e.contribution, 2.60);
near('BE ROAS = list / contribution', e.beRoas, 345.77, 0.5);
// ⚠ ACOS is the reciprocal of ROAS. Asserted as an identity, not a formula
// copy — if either drifts this fails.
near('BE ACOS is the reciprocal of BE ROAS', e.beAcos, 10000 / e.beRoas, 0.01);
near('Actual ACOS is the reciprocal of Realised ROAS', e.actualAcos, 10000 / e.realisedRoas, 0.01);
near('  and reads ~19.9% on this row', e.actualAcos, 19.91, 0.05);
// The sign convention has to agree between the two tabs: clear of break-even
// means headroom POSITIVE and actual ACOS BELOW break-even ACOS.
t('clear of break-even', e.verdict, 'clear');
t('  headroom positive', e.headroom > 0, true);
t('  and actual ACOS below BE ACOS', e.actualAcos < e.beAcos, true);

// Window totals — the analogue of Amazon's Net Sales window / Contribution Profit.
near('Our Rev = units x wholesale', e.ourRev, 2129 * W, 0.01);
near('Vendor Contrib = units x contribution', e.vendorContrib, 2129 * 2.60, 0.01);
near('GM % is on the invoice value', e.gmPct, (2.60 / W) * 100, 0.01);

// Degenerate shapes must not fabricate the new measures either.
e = chewyBreakevenEcon({ wholesale: 1.20, cogs: 1.00, standingPct: 24.5, listPrice: 8.99,
                         spend: 100, directSales: 5000, directUnits: 10 });
t('contribution <= 0 -> BE ACOS null', e.beAcos, null);
t('  verdict never', e.verdict, 'never');
t('  Vendor Contrib still reports the loss', e.vendorContrib < 0, true);
e = chewyBreakevenEcon({ wholesale: 4.5, cogs: 1, standingPct: 23, listPrice: 9.99,
                         spend: 0, directSales: 0, autoshipSales: 0, directUnits: 0 });
t('zero spend -> null ACOS', e.actualAcos, null);
t('  zero units -> zero window totals', [e.ourRev, e.vendorContrib], [0, 0]);
e = chewyBreakevenEcon({ wholesale: null, cogs: 1, standingPct: 23, listPrice: 9.99,
                         spend: 100, directSales: 500, directUnits: 50 });
t('no wholesale -> null Our Rev and GM %', [e.ourRev, e.gmPct], [null, null]);
let threw = false;
try { chewyBreakevenEcon({}); } catch (err) { threw = true; }
t('an empty argument object does not throw', threw, false);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
harness = harness.replace('ECON', fn('chewyBreakevenEcon'))
tmp = os.path.join(tempfile.gettempdir(), 'test_v1042_econ.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('chewy econ behaviour')


# ═════════ E. the table still lines up ═════════
print('\nE. static — header and body agree')
# v10.54 made this structural rather than countable: the body row used to be a
# hardcoded sequence of cells in column order with nothing tying it to the
# registry, so a new column shifted every cell one to the left silently. It is
# now KEYED and emitted from the same filtered list the header reads, so the
# assertion moves from "the two counts match" to "every column has a cell".
col_keys = re.findall(r"\{ key: '([A-Za-z_0-9]+)'", cols)
body = be[be.index('tb.innerHTML = rows.map'):]
body = body[:body.index('</tr>`')]
cell_keys = set(re.findall(r'^\s{10}([A-Za-z_0-9]+):\s', body, re.M))
missing = [k for k in col_keys if k not in cell_keys]
ok(len(col_keys) >= 18 and not missing,
   'every one of the %d registry columns has a keyed body cell%s'
   % (len(col_keys), (' — MISSING: ' + ', '.join(missing)) if missing else ''))
ok('COLS.map(c => CELLS[c.key]' in body,
   '  and the row is emitted from the same filtered list the header reads')
# feedback_always_csv_export — the new measures reach the file too.
exp = fn('_writeChewyBreakevenCSV')   # v10.79 - writer split from the scope dialog
# v10.80 - the CSV header + body are derived from CHEWY_BE_COLUMNS now, so the
# column names live in the registry, not in the exporter. Search both. Sliced
# by index rather than regex so no escape can be mangled.
_i = js.index('const CHEWY_BE_COLUMNS = [')
exp = exp + js[_i: js.index(chr(10) + '];', _i)]
for c in ['our_revenue_wholesale', 'vendor_contribution', 'gm_per_unit', 'gm_pct',
          'break_even_acos_pct', 'actual_acos_pct']:
    ok(c in exp, 'CSV exports %s' % c)
# v10.80 - header and body are both mapped from CHEWY_BE_COLUMNS now, so they
# cannot differ in length by construction. The stronger guarantee that replaces
# the count-vs-count check: every csv descriptor declares a UNIQUE position, so
# no column can silently overwrite another's slot in the file.
_names  = re.findall(r"csv: \{ name: '([^']+)', order: (\d+)", js)
_orders = sorted(int(o) for _, o in _names)
ok(len(_names) > 0 and _orders == list(range(1, len(_names) + 1)),
   'CSV column positions are unique and contiguous (%d columns)' % len(_names))
ok(len(set(n for n, _ in _names)) == len(_names),
   'every CSV column name is unique')


# ═════════ F. v10.42 — COGS on the product card ═════════
print('\nF. static — every COGS field is on the product card')
for i in ['pf-cb-landed', 'pf-cb-fulfill-amz', 'pf-cb-fulfill-dtc', 'pf-cb-overhead-dtc',
          'pf-cb-shipping', 'pf-cb-labor',
          'pf-cogs', 'pf-cogs-dtc', 'pf-cogs-chewy', 'pf-cogs-eu']:
    ok('id="%s"' % i in src, 'the card carries %s' % i)
ok(re.search(r"'pf-cogs':\s*'amazon_cogs'", js) is not None,
   'pf-cogs still maps to amazon_cogs (id preserved for every existing reader)')
load = fn('pfCogsLoad')
save = fn('pfCogsPayload')
ok('PF_COGS_BLOCKS' in load and 'PF_COGS_TOTALS' in load, 'the loader fills all ten')
ok('PF_COGS_BLOCKS' in save and 'PF_COGS_TOTALS' in save, 'the save writes all ten')
ok('pfCogsLoad(' in fn('openProductModal'), 'openProductModal calls the loader')
ok('pfCogsPayload(' in fn('saveProduct'), 'saveProduct calls the payload builder')
# ⚠ v6.20 landed_cost gate: without landed cost a "total" is only fees.
rec = fn('pfCogsRecalc')
ok('b.landed_cost != null' in rec, 'the v6.20 landed_cost gate is enforced')
# ⚠ v10.44 — the formulas are ONE declaration now. They were copy-pasted
# across seven sites and Chewy would have been an eighth copy, which is how a
# set of duplicated formulas falls out of step. Assert the declaration, and
# that every site references it rather than restating it.
decl = js[js.index('const COGS_DERIVED_INPUTS'):]
decl = decl[:decl.index('};') + 2]
ok("'landed_cost', 'fulfillment_amazon', 'production_labor'" in decl,
   'Amazon = landed + fulfill(Amz) + labor')
ok("'landed_cost', 'overhead_dtc', 'fulfillment_dtc', 'shipping_cost', 'production_labor'" in decl,
   'DTC = landed + overhead + fulfill(DTC) + shipping + labor')
ok("'landed_cost', 'fulfillment_chewy', 'production_labor'" in decl,
   'Chewy = landed + fulfill(Chwy) + labor   (v10.44)')
ok('amazon_cogs_eu' not in decl,
   'Amazon EU is NOT derived (different freight + import duty, no blocks)')
ok(decl.count('landed_cost') == 3, '  landed cost gates all three')
# No site may restate a formula; they all spread the shared lists.
inline_amz = js.count("sumOrNull('landed_cost', 'fulfillment_amazon', 'production_labor')")
inline_dtc = js.count("sumOrNull('landed_cost', 'overhead_dtc', 'fulfillment_dtc', 'shipping_cost', 'production_labor')")
ok(inline_amz == 0 and inline_dtc == 0,
   'no site restates a formula inline (amz=%d dtc=%d)' % (inline_amz, inline_dtc))
ok(rec.count('COGS_DERIVED_INPUTS') == 3, 'the product card derives all three channels')
ok('pf-cogs-eu' not in rec, '  and never Amazon EU')
ok("dataset.manual" in rec, 'a manual override stops the live derive')
ok('pfCogsClearManual' in js, '  and can be cleared')
ok('Math.abs(Number(c[field]) - derived) > 0.005' in load,
   'a stored total that disagrees with the blocks is detected as an override on load')


# ═════════ G. behaviour — the derive rule ═════════
print('\nG. behaviour — pfCogsRecalc (the real function)')

h2 = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
const EL = {};
// A real <input> coerces .value to a String on assignment. The stub has to do
// the same or it both invents failures (type mismatch) and hides real ones
// (pfCogsNum calls .trim() on it).
const mk = (id, v) => {
  let _v = v == null ? '' : String(v);
  const el = { id, dataset: {} };
  Object.defineProperty(el, 'value', {
    get: () => _v,
    set: (nv) => { _v = nv == null ? '' : String(nv); },
    enumerable: true,
  });
  EL[id] = el;
  return el;
};
const document = { getElementById: id => EL[id] || null };

//<<DERIVED>>
//<<MAPS>>
//<<NUM>>
//<<MARK>>
//<<CLEAR>>
//<<RECALC>>
//<<NOTE>>
//<<LOAD>>
//<<PAYLOAD>>

const reset = (o) => {
  for (const id of ['pf-cb-landed','pf-cb-fulfill-amz','pf-cb-fulfill-chewy','pf-cb-fulfill-dtc',
                    'pf-cb-overhead-dtc','pf-cb-shipping','pf-cb-labor',
                    'pf-cogs','pf-cogs-dtc','pf-cogs-chewy','pf-cogs-eu']) mk(id, '');
  mk('pf-cogs-derived-note', '');
  EL['pf-cogs-derived-note'].textContent = '';
  for (const [k, v] of Object.entries(o || {})) EL[k].value = String(v);
};

// landed 1.40 + fulfill(Amz) 0.03 + labor 0.10 = 1.53
reset({ 'pf-cb-landed': 1.40, 'pf-cb-fulfill-amz': 0.03, 'pf-cb-labor': 0.10 });
pfCogsRecalc();
t('Amazon COGS derives from its blocks', EL['pf-cogs'].value, '1.53');
// DTC adds overhead + fulfill(DTC) + shipping: 1.40 + 0.05 + 0.85 + 2.00 + 0.10 = 4.40
reset({ 'pf-cb-landed': 1.40, 'pf-cb-fulfill-amz': 0.03, 'pf-cb-labor': 0.10,
        'pf-cb-overhead-dtc': 0.05, 'pf-cb-fulfill-dtc': 0.85, 'pf-cb-shipping': 2.00 });
pfCogsRecalc();
t('DTC COGS derives from its blocks', EL['pf-cogs-dtc'].value, '4.4');
t('  Amazon is unaffected by the DTC-only blocks', EL['pf-cogs'].value, '1.53');

// ⚠ v6.20 — no landed cost means NO derive. A total made only of fees is not
// COGS, and presenting it as one is what this gate exists to stop.
reset({ 'pf-cb-fulfill-amz': 0.03, 'pf-cb-labor': 0.10 });
pfCogsRecalc();
t('no landed cost -> Amazon total stays blank', EL['pf-cogs'].value, '');
t('  and DTC stays blank', EL['pf-cogs-dtc'].value, '');

// Manual override wins, and is reversible.
reset({ 'pf-cb-landed': 1.40, 'pf-cb-fulfill-amz': 0.03 });
pfCogsRecalc();
t('derived before override', EL['pf-cogs'].value, '1.43');
EL['pf-cogs'].value = '9.99';
pfCogsMarkManual(EL['pf-cogs']);
EL['pf-cb-landed'].value = '2.00';
pfCogsRecalc();
t('a manual override survives a block change', EL['pf-cogs'].value, '9.99');
t('  while the un-overridden total still moves', EL['pf-cogs-dtc'].value, '2');
pfCogsClearManual('pf-cogs');
t('clearing the override re-derives', EL['pf-cogs'].value, '2.03');

// ⚠ v10.44 — Chewy DERIVES now. Before this it was the only channel total
// with no blocks behind it, so it stayed null and chewyPnlCogs() fell back to
// bare landed_cost: Chewy units carried NO fulfillment and every Chewy margin
// read better than reality.
reset({ 'pf-cb-landed': 1.40, 'pf-cb-fulfill-chewy': 0.03, 'pf-cb-labor': 0.10 });
pfCogsRecalc();
t('Chewy COGS derives from landed + fulfill(Chwy) + labor', EL['pf-cogs-chewy'].value, '1.53');
t('  and does not pick up the DTC-only blocks', EL['pf-cogs-dtc'].value, '1.5');
// Amazon EU has its own freight and duty and no blocks — still never derived.
reset({ 'pf-cb-landed': 1.40, 'pf-cogs-eu': 4.44 });
pfCogsRecalc();
t('Amazon EU COGS is untouched', EL['pf-cogs-eu'].value, '4.44');
// The default Jason asked for: $0.03.
reset({ 'pf-cb-landed': 1.40, 'pf-cb-fulfill-chewy': 0.03 });
pfCogsRecalc();
t('the $0.03 default lands in Chewy COGS', EL['pf-cogs-chewy'].value, '1.43');

// The payload reads every field from the form, so a cleared input CLEARS.
reset({ 'pf-cb-landed': 1.40, 'pf-cb-fulfill-amz': 0.03, 'pf-cogs': 1.43, 'pf-cogs-chewy': 3.33 });
const p = pfCogsPayload('SP-0001');
t('payload carries the master_id', p.master_id, 'SP-0001');
t('  every set field', [p.landed_cost, p.fulfillment_amazon, p.amazon_cogs, p.chewy_cogs],
  [1.40, 0.03, 1.43, 3.33]);
t('  and nulls the cleared ones', [p.dtc_cogs, p.shipping_cost, p.amazon_cogs_eu],
  [null, null, null]);
t('  with all eleven fields present', Object.keys(p).length, 12);
t('  including fulfillment_chewy', 'fulfillment_chewy' in p, true);

// Negative / junk input reads as cleared rather than poisoning the sum.
reset({ 'pf-cb-landed': '-5', 'pf-cb-fulfill-amz': 'abc' });
pfCogsRecalc();
t('negative and junk inputs do not derive a total', EL['pf-cogs'].value, '');

// A stored total that disagrees with the blocks is treated as an override.
let cogsByMaster = { 'SP-9': { landed_cost: 1.40, fulfillment_amazon: 0.03,
                               production_labor: null, amazon_cogs: 5.00 } };
reset({});
globalThis.cogsByMaster = cogsByMaster;
pfCogsLoad('SP-9');
t('load flags a disagreeing stored total as manual', EL['pf-cogs'].dataset.manual, '1');
EL['pf-cb-landed'].value = '2.00';
pfCogsRecalc();
t('  so the live derive leaves it alone', EL['pf-cogs'].value, '5');

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
derived_decl = js[js.index('const COGS_BUILDING_BLOCKS'):]
derived_decl = derived_decl[:derived_decl.index('const COGS_ALL_FIELDS')]
maps = js[js.index('const PF_COGS_BLOCKS'):]
maps = maps[:maps.index('function pfCogsNum')]
# ⚠ Tokens, not bare words. A bare `.replace('NOTE', ...)` matched the NOTE
# inside `pfCogsSyncNote()` in an already-injected body, and `LOAD` ate the
# tail of `PAYLOAD`. Order-independent now.
for _tok, _body in [('DERIVED', derived_decl), ('MAPS', maps), ('NUM', fn('pfCogsNum')), ('MARK', fn('pfCogsMarkManual')),
                    ('CLEAR', fn('pfCogsClearManual')), ('RECALC', fn('pfCogsRecalc')),
                    ('NOTE', fn('pfCogsSyncNote')), ('PAYLOAD', fn('pfCogsPayload')),
                    ('LOAD', fn('pfCogsLoad'))]:
    _marker = '//<<%s>>' % _tok
    if h2.count(_marker) != 1:
        raise SystemExit('FAIL: placeholder %s appears %d times' % (_marker, h2.count(_marker)))
    h2 = h2.replace(_marker, _body, 1)
tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1042_cogs.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip()[:1500])
    fails.append('pfCogs behaviour')



# ═════════ H. v10.43 — the Break-Even column picker ═════════
print('\nH. static — column picker, in the View popup, button next to search')
# Jason: "allow me to pick the columns here" / "should be in the view" /
# "saved views should be up next to search - stay consistent with design
# patterns please". Two existing conventions, not a third:
#   v10.7 — one popup per page holding Saved views + Columns, labelled
#           "Customize columns" on every page that HAS a picker.
#   v10.9 — that button lives in the global search bar, between the search box
#           and the gear, driven by PAGE_COLUMN_BUTTONS.
bar = src[src.index('id="globalSearchBar"'):]
bar = bar[:bar.index('</div>', bar.index('id="pageSettingsBtn"'))]
ok('id="be-view-btn"' in bar, 'the Break-Even button lives in the global search bar')
ok('id="be-view-popup"' in bar, '  and so does its popup')
ok(bar.index('id="be-view-btn"') > bar.index('id="globalSearch"'), '  after the search input')
ok(bar.index('id="be-view-btn"') < bar.index('id="pageSettingsBtn"'), '  and before the gear')
ok('Customize columns</button>' in bar[bar.index('id="be-view-btn"'):bar.index('id="be-view-btn"') + 600],
   '  labelled "Customize columns" (v10.7 convention)')
ok("{ id: 'be-view-btn'" in js and "'pnl_amazon_breakeven'" in js,
   'registered in PAGE_COLUMN_BUTTONS for the Break-Even nav key')
# ⚠ v10.9's design note: the buttons MOVED and their ids did NOT, because the
# popups re-open themselves by getElementById. Same reasoning here.
ok(src.count('id="be-view-btn"') == 1, 'the id is preserved and appears exactly once')
ok("getElementById('be-view-btn')" in js, '  and is still looked up by id')
# The Amazon P&L picker must not also show on this sub-view.
pcb = js[js.index('const PAGE_COLUMN_BUTTONS'):]
pcb = pcb[:pcb.index('];')]
pnl_row = [l for l in pcb.split('\n') if "'pnl-cols-btn'" in l][0]
ok('pnl_amazon_breakeven' not in pnl_row, 'the Amazon P&L picker does not claim the Break-Even key')

print('\nH2. static — the picker itself')
ok('BREAKEVEN_COL_GROUPS' in js, 'columns are grouped')
# ⚠ Groups are derived by KEYWORD, not hardcoded. A picker that only knows a
# fixed list leaves a newly-added SQL column permanently unreachable once it
# defaults to hidden — the v6.61 bug.
grp = js[js.index('const BREAKEVEN_COL_GROUPS'):]
grp = grp[:grp.index('\n];')]
ok('test: c =>' in grp, '  by a predicate per group, not a fixed column list')
ok("return g ? g.key : 'other';" in fn('breakevenGroupOf'),
   '  with an Other bucket, so a new column can never vanish')
vis = fn('breakevenVisibleCols')
ok('breakevenHiddenCols' in vis, 'breakevenVisibleCols honours the picker')
ok('BREAKEVEN_AUDIT_PREFIX' in vis, '  and the audit toggle still works')
# null = "no explicit choice"; an empty Set is a real choice. Collapsing the
# two would make "hide everything" silently reset to the default.
ok('let breakevenHiddenCols = null;' in js, 'null means no explicit choice')
rst = fn('breakevenResetCols')
ok('breakevenHiddenCols = null' in rst and 'removeItem' in rst,
   '  and reset returns to it rather than to an empty Set')
ok('localStorage' in fn('breakevenPersistHiddenCols'), 'the choice persists')

print('\nH3. static — a view carries its columns')
snap = fn('breakevenSnapshotView')
ok('hiddenCols' in snap, 'the snapshot captures the column set')
apply_fn = fn('breakevenApplyView')
ok("'hiddenCols' in view" in apply_fn,
   'apply restores it, and leaves a pre-v10.43 view alone (no key = no change)')
ok('breakevenPersistHiddenCols()' in apply_fn, '  persisting the restored set')
pop = fn('breakevenRenderViewPopup')
ok('breakevenRenderColsSection()' in pop, 'the popup renders both sections')
ok('Saved views' in pop and 'cols hidden' in pop,
   '  and the view meta line names how many columns a view hides')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.41 / v10.42 — all green')
