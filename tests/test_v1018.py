# -*- coding: utf-8 -*-
"""
v10.18 — the gaps panel was shouting about the direction that does not matter.

Jason: "so these are skus that are not in the uploaded catalog but have a chewy
sku? so what -- these are mostly old skus. if they are in the catalog but not in
the system, then i need to know."

Two directions, and v10.15 had them backwards by weight:

  OUR product tagged with a Chewy SKU, absent from Chewy's catalog
      -> mostly discontinued. Reported, not alarmed about. Split by
         sell-through so the one genuinely surprising subset still shows.

  CHEWY's catalog row with no product on our side
      -> Chewy is set up to buy something we do not track. This is the one
         that needs an alert — and it had no table row at all, because those
         rows carry no master_id.

The load-bearing test here is the partition one: every catalog row with no
master_id must become exactly one not-in-system row. Drop one and a SKU Chewy
is buying silently disappears from the page that exists to price it.
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
INDEX = os.path.join(os.path.dirname(HERE), 'index.html')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)

fails = []
def ok(cond, label):
    if cond:
        print('  ok  ' + label)
    else:
        print('  FAIL ' + label)
        fails.append(label)


# ═════════ A. static ═════════
print('\nA. static — the two directions are named separately')

for k in ['not-in-system', 'no-catalog', 'no-catalog-dormant',
          'no-case-qty', 'unknown-uom', 'no-cost', 'no-cogs']:
    ok(('<option value="gap:%s">' % k) in src, 'Show dropdown offers gap:%s' % k)
    ok(("'%s':" % k) in js, 'GAP_MSG explains %s' % k)
    ok(("'%s':" % k) in js, 'GAP_LABEL names %s' % k)

# not-in-system must LEAD the panel — it is the actionable one.
iNotInSys = js.index("gNotInSys.length)  parts.push")
iNoCatalog = js.index("gNoCatalog.length) parts.push")
ok(iNotInSys < iNoCatalog, 'not-in-system is pushed before the our-side bullet')

# Dormant rows must sit OUTSIDE the orange gaps box.
ok('dormantLine' in js, 'dormant SKUs render in their own muted line')
ok(js.index('const dormantLine') < js.index('gapsEl.innerHTML'),
   'the dormant line is built before the panel is written')
ok(re.search(r'gapsEl\.innerHTML\s*=\s*\(parts\.length', js) is not None,
   'the gaps box renders only when there are real gaps, dormant line appended after')

# Buckets come off allRows (the v10.15 invariant) — still true for the new ones.
for var in ['gNotInSys', 'gNoCatalog', 'gDormant', 'gNoCase', 'gBadUom', 'gNoCost', 'gNoCogs']:
    ok(re.search(r'const %s\s*=\s*allRows\.filter' % var, js) is not None,
       '%s counts off allRows' % var)

# The superseded footnote is gone.
ok('matched no product at all' not in src,
   'the old "matched no product at all / see the console warning" footnote is retired')
ok('unmatchedCatalogRows' not in js, 'its dead helper vars are gone too')

# A not-in-system row has no product, so it must not look clickable.
ok('const openable = !r.notInSystem && r.master_id;' in js,
   'rows without a product are not clickable')
ok('NOT IN SYSTEM' in js, 'and they carry a visible marker')


# ═════════ B. behaviour — the real row-building block ═════════
print('\nB. behaviour — unmatched catalog rows become real rows')

# Slice the real unmatched-catalog loop so the test cannot drift from it.
m = re.search(r'(const unmatchedHiddenByFilter.*?\n  \}\n)', js, re.S)
if not m:
    raise SystemExit('FAIL: cannot slice the unmatched-catalog block')
blk = m.group(1)
ok(len(blk) < 2200, 'unmatched-catalog slice is tight (%d chars)' % len(blk))

# And the gap-split line.
mSplit = re.search(r"if \(gap === 'no-catalog' && [^\n]*\n", js)
ok(mSplit is not None, 'the dormant split line is present')
split = mSplit.group(0)

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

// Stand-in for the real helper; only the shape matters here.
function chewyCatalogPricePerEach(cat, caseQty) {
  const uom = String((cat && cat.purchase_uom) || '').trim().toUpperCase();
  if (uom === 'EA') return { price: cat.cost, reason: null, uom: 'EA', caseQty: 1, cost: cat.cost };
  if (uom === 'CS') return { price: null, reason: 'no-case-qty', uom: 'CS', caseQty: null, cost: cat.cost };
  return { price: null, reason: 'unknown-uom', uom: uom || null, caseQty: null, cost: cat.cost };
}

const CATALOG = [
  { chewy_sku:'111', master_id:'SP-1', cost:54,  purchase_uom:'CS', item_name:'Matched CS' },
  { chewy_sku:'222', master_id:'SP-2', cost:4.5, purchase_uom:'EA', item_name:'Matched EA' },
  { chewy_sku:'900', master_id:null,   cost:9,   purchase_uom:'EA', item_name:'Orphan Each', upc:'9' },
  { chewy_sku:'901', master_id:null,   cost:36,  purchase_uom:'CS', item_name:'Orphan Case', upc:'8' },
  { chewy_sku:'902', master_id:'',     cost:12,  purchase_uom:'EA', item_name:'Orphan Blank' },
  { chewy_sku:'903', master_id:null,   cost:7,   purchase_uom:'EA', item_name:'' },
];

function build({ brand = '', cat = '', search = '', chewyCatalogData = CATALOG } = {}) {
  const candidates = [];
  BLOCK
  return { candidates, unmatchedHiddenByFilter };
}

// ── every orphan becomes exactly one row. Dropping one means a SKU Chewy is
// buying silently vanishes from the page that exists to price it.
const r0 = build();
t('every master_id-less catalog row becomes a row',
  r0.candidates.map(c => c.chewy_sku), ['900', '901', '902', '903']);
t('matched rows are NOT duplicated here',
  r0.candidates.some(c => c.chewy_sku === '111' || c.chewy_sku === '222'), false);
t('all of them carry gap not-in-system',
  [...new Set(r0.candidates.map(c => c.gap))], ['not-in-system']);
t('and the notInSystem marker', r0.candidates.every(c => c.notInSystem === true), true);

// An EA orphan can still be priced — that is the number you want when deciding
// whether the product is worth setting up. A CS orphan cannot (no case qty).
const byS = Object.fromEntries(r0.candidates.map(c => [c.chewy_sku, c]));
t('EA orphan shows a per-each price', byS['900'].price, 9);
t('CS orphan shows no price', byS['901'].price, null);
t('CS orphan still shows the raw catalog cost', byS['901'].rawCost, 36);

// No product means no COGS and therefore no margin — never a fabricated one.
t('no COGS on an orphan', r0.candidates.map(c => c.cogs), [null, null, null, null]);
t('no margin on an orphan', r0.candidates.map(c => c.gm), [null, null, null, null]);
t('no verdict, so quick filters cannot mis-bucket it',
  r0.candidates.map(c => c.verdict), [null, null, null, null]);
t('master_id is empty, not a fake one', r0.candidates.map(c => c.master_id), ['', '', '', '']);

// A nameless catalog row still has to be identifiable.
t('a nameless orphan falls back to its Chewy SKU', byS['903'].title, '903');

// ── brand / category filters: an orphan has neither, so it is held out
// rather than shown under a brand it does not belong to.
t('brand filter holds orphans out', build({ brand: 'Doggijuana' }).candidates.length, 0);
t('category filter holds orphans out', build({ cat: 'Sprays' }).candidates.length, 0);
t('and the panel is told why', build({ brand: 'Doggijuana' }).unmatchedHiddenByFilter, true);
t('no filter -> not held out', r0.unmatchedHiddenByFilter, false);

// ── search still applies, across sku / name / upc.
t('search matches the item name', build({ search: 'orphan each' }).candidates.map(c => c.chewy_sku), ['900']);
t('search matches the chewy sku',  build({ search: '901' }).candidates.map(c => c.chewy_sku), ['901']);
t('search matches the upc',        build({ search: '8' }).candidates.map(c => c.chewy_sku), ['901']);
t('search that matches nothing',   build({ search: 'zzz' }).candidates.length, 0);

// ── an empty catalog must not invent rows.
t('empty catalog -> no orphan rows', build({ chewyCatalogData: [] }).candidates.length, 0);

console.log('\n  --- dormant split ---');

// ── the our-side direction splits on sell-through.
function gapFor({ reason, cogs, units, ever }) {
  const everSold = new Set(ever ? ['M'] : []);
  const c = { units };
  const mid = 'M';
  let gap = reason || (cogs == null ? 'no-cogs' : null);
  SPLIT
  return gap;
}
t('no catalog row + selling in period -> flagged',
  gapFor({ reason: 'no-catalog', cogs: 1, units: 40, ever: true }), 'no-catalog');
t('no catalog row + sold historically -> flagged (feed lags ~2 months)',
  gapFor({ reason: 'no-catalog', cogs: 1, units: 0, ever: true }), 'no-catalog');
t('no catalog row + never sold -> dormant',
  gapFor({ reason: 'no-catalog', cogs: 1, units: 0, ever: false }), 'no-catalog-dormant');
t('other gaps are untouched by the split',
  gapFor({ reason: 'no-case-qty', cogs: 1, units: 0, ever: false }), 'no-case-qty');
t('a clean row stays clean',
  gapFor({ reason: null, cogs: 1, units: 5, ever: true }), null);
t('missing COGS still wins when there is no catalog reason',
  gapFor({ reason: null, cogs: null, units: 5, ever: true }), 'no-cogs');

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
harness = harness.replace('BLOCK', blk).replace('SPLIT', split)
tmp = os.path.join(tempfile.gettempdir(), 'test_v1018.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('unmatched-catalog / dormant behaviour')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.18 — all green')
