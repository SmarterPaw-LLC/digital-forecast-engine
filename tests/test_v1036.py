# -*- coding: utf-8 -*-
"""
v10.36 — Chewy Ads ingest + the Chewy Break-Even tab.

Jason: "is there an uploader for it wired? also, i do not see the chewy break
even on the chewy p&l" — no to both.

⚠ THE CRUX, and the thing a reviewer will think is a bug: Chewy reports ROAS
against RETAIL sales (what the customer paid Chewy) while our contribution is
on the WHOLESALE side. Those look incommensurable. They are not:

  for N ad-driven units, break-even is   spend = N x contribution
  so   ROAS at break-even = (N x retail) / (N x contribution)
                          = retail / contribution

The N cancels, so the two sides never have to be reconciled unit-for-unit.
That identity is asserted directly below rather than left as a comment.

⚠ contribution <= 0 is reported as its OWN verdict with a NULL break-even
ROAS, not as a huge number. "You need 4,000% ROAS" reads like a target; this
is not one, it is "no ad spend can ever pay on this SKU".

⚠ LTV ROAS is absent on purpose — Chewy reports it per CAMPAIGN only, never
per SKU. Asserted that nothing on the page claims a SKU-level LTV.
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
SQLF = os.path.join(ROOT, 'supabase_v10_36_chewy_ad_spend.sql')
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


# ═════════ A. the SQL migration ═════════
print('\nA. static — supabase_v10_36_chewy_ad_spend.sql')
ok(os.path.exists(SQLF), 'migration file exists')
sql = io.open(SQLF, encoding='utf-8').read() if os.path.exists(SQLF) else ''
# v6.47 hard rule: RLS + policy + grants + anon revoke on EVERY new table.
ok('enable row level security' in sql.lower(), 'RLS enabled')
ok('create policy' in sql.lower() and 'to authenticated' in sql.lower(), 'authenticated policy')
ok(re.search(r'grant\s+select,\s*insert,\s*update,\s*delete', sql, re.I) is not None, 'DML granted to authenticated')
ok(re.search(r'revoke\s+all\s+on\s+table\s+chewy_ad_spend\s+from\s+anon', sql, re.I) is not None, 'anon revoked')
ok('create table if not exists' in sql.lower(), 'idempotent create')
# ⚠ Architecture Rule #5 only bites on FUNCTIONAL unique indexes. This one is
# plain-column on purpose, so an upsert would work — but the writer still
# DELETE+INSERTs so an overlapping weekly re-upload refreshes rather than
# half-updating. Assert the index has no coalesce() so the rule stays clear.
uniq = re.search(r'create unique index[^;]+chewy_ad_spend[^;]+;', sql, re.I | re.S)
ok(uniq is not None, 'unique index present')
ok(uniq is not None and 'coalesce' not in uniq.group(0).lower(),
   'unique index is plain-column (no coalesce) — Architecture Rule #5 does not apply')
ok('master_id' in sql and 'references products(master_id)' in sql, 'master_id FK to products')
# The honesty the schema has to carry forward.
ok(re.search(r'retail', sql, re.I) is not None,
   'schema says direct_sales is RETAIL, not our revenue')
ok(re.search(r'ltv', sql, re.I) is not None,
   'schema records that LTV ROAS is campaign-level only')


# ═════════ B. Architecture Rule #8 — FK migration coverage ═════════
print('\nB. static — Architecture Rule #8 (merge + SP-TEMP promotion)')
# ⚠ chewy_ad_spend.master_id is `on delete set null`. Omit it from the merge
# and the duplicate's ad rows survive with master_id nulled — every dollar of
# that SKU's Chewy ad spend silently drops out of the survivor's Break-Even
# tab. Same class as v4.145 / v5.44 / v5.76 / v6.98 / v10.11.
merge = fn('runMerge')
ok("reassignMasterId('chewy_ad_spend')" in merge, 'runMerge reassigns chewy_ad_spend')
save = fn('saveProduct')
ok(re.search(r"from\('chewy_ad_spend'\)\.update\(\{\s*master_id\s*\}\)", save) is not None,
   'SP-TEMP promotion re-points chewy_ad_spend')
# doRestore covers only products / bom / inventory / sales_weekly by design —
# the JSON backup's scope is narrower than the schema. Asserted so a future
# reader does not read the absence as the v6.98 bug.
restore = fn('doRestore')
ok('chewy_ad_spend' not in restore and 'chewy_catalog' not in restore,
   "doRestore's narrower backup scope is consistent (chewy_catalog is absent too)")


# ═════════ C. wiring — nothing invented ═════════
print('\nC. static — wiring')
for i in ['chpnl-tab-breakeven', 'chpnl-view-breakeven', 'f-chewy-ads', 'st-chewy-ads',
          'chpnl-be-tbody', 'chpnl-be-thead-row', 'chpnl-be-scorecards', 'chpnl-be-explain',
          'chpnl-be-gaps', 'chpnl-be-row-count', 'chpnl-be-freshness']:
    ok('id="%s"' % i in src, 'markup carries %s' % i)

# ⚠ THE ID SWEEP — the v10.34 lesson. A missing element fails SILENTLY
# (`?.value || ''` returns empty, so the filter just never applies), which is
# exactly the failure this tab would be blamed for.
rend = fn('renderChewyBreakeven')
read_ids = set(re.findall(r"getElementById\('(chpnl-be-[a-z-]+)'\)", rend))
ok(len(read_ids) >= 10, 'the renderer reads at least 10 controls (got %d)' % len(read_ids))
for i in sorted(read_ids):
    ok('id="%s"' % i in src, '  renderer reads a real control: %s' % i)
# Guard the guard (the v10.20 lesson): a bogus id must be flagged.
ok('id="chpnl-be-nope"' not in src, '  the sweep would flag a bogus id')

# Sub-tab + search + catVis + CSV routing all have to know about the new tab.
sw = fn('switchChewyPnlView')
ok("key: 'breakeven'" in sw and "panel: 'chpnl-view-breakeven'" in sw,
   'switchChewyPnlView has a breakeven row')
ok("loadChewyBreakeven()" in sw, '  and it loads on show')
ok("pnl_chewy_breakeven: { id: 'chpnl-be-search' }" in js,
   'global search bar is mapped (pnl_chewy_breakeven)')
ok("key: 'pnl_chewy_be'" in js and "selectId: 'chpnl-be-cat'" in js,
   'category visibility registered')
ok("renderChewyBreakeven()" in fn('catVisPageDef') or "renderChewyBreakeven" in js,
   '  with a real re-render')
ok("return downloadChewyBreakevenCSV()" in fn('exportCSV'),
   'top-bar CSV routes to the break-even exporter')
# feedback_always_csv_export — every data-bearing sub-view is exportable.
exp = fn('downloadChewyBreakevenCSV')
for col in ['break_even_roas_pct', 'contribution_per_unit', 'realised_roas_pct',
            'autoship_actualized_sales', 'wholesale_per_each', 'data_gap']:
    ok(col in exp, '  CSV exports %s' % col)
ok('RETAIL' in exp, '  CSV context line names direct_sales as RETAIL')
ok('campaign-level only' in exp, '  CSV context line says LTV ROAS is campaign-only')

# The uploader is inline on this tab, NOT on Data -> Uploads. Same call v10.11
# and v10.16 made, and Jason has said so twice.
up_markup = src[src.index('id="chpnl-view-breakeven"'):]
up_markup = up_markup[:up_markup.index('<!-- /chpnl-view-breakeven -->')]
ok('id="f-chewy-ads"' in up_markup, 'the uploader lives on the Break-Even tab')
uploads_page = src[src.index('id="data-view-uploads"'):] if 'id="data-view-uploads"' in src else ''
ok('f-chewy-ads' not in uploads_page.split('id="chpnl-view')[0],
   '  and NOT on Data -> Uploads')
# A dangling data-currency chip is worse than a plain one (v10.16).
tmap = js[js.index('const TABLE_TO_UPLOAD_GROUP'):]
tmap = tmap[:tmap.index('};')]
ok('chewy_ad_spend' not in tmap,
   'chewy_ad_spend is NOT in TABLE_TO_UPLOAD_GROUP (no dead-end chip)')
ok('chewy_catalog' not in tmap, '  consistent with chewy_catalog')
ok('chewyAdDrop' in js and 'ondrop="chewyAdDrop' in src,
   'drag-and-drop wired by hand (the v10.16 lesson — initUploadDropTargets does not run here)')


# ═════════ D. the escape trap that actually bit this release ═════════
print('\nD. static — no invalid \\U escapes in the v10.36 block')
# ⚠ The engine was authored through a Python RAW string, so `\U0001f4e3`
# survived verbatim into the JS. JS has NO `\U` escape, so that string
# evaluates to the literal text `U0001f4e3` — every icon would have rendered
# as garbage. Eighth-ish instance of the escape-mangling class (v9.99, v10.11,
# v10.20). Scoped to the v10.36 functions so pre-existing mentions inside
# comments elsewhere are left alone.
blk = js[js.index('function renderChewyBreakeven'):]
blk = blk[:blk.index('function downloadChewyPnlCostCSV')]
bad = [m.group(0) for m in re.finditer(r'\\U0001[0-9a-fA-F]{4}', blk)]
ok(not bad, 'no literal \\U escapes survive in the break-even block (found %s)' % bad[:4])
ok(re.search(r'\\U0001[0-9a-fA-F]{4}', 'x\\U0001f534y') is not None,
   '  the detector would catch one')


# ═════════ E. behaviour — the real sliced math ═════════
print('\nE. behaviour — chewyBreakevenEcon (the real function)')

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

// ── The worked example, hand-checkable end to end.
//   wholesale $4.50/each, 23% standing allowances, COGS $1.00
//   net to us     = 4.50 x 0.77           = 3.465
//   contribution  = 3.465 - 1.00          = 2.465
//   list price    = 9.99
//   BE ROAS       = 9.99 / 2.465          = 405.3%
const base = { wholesale: 4.50, cogs: 1.00, standingPct: 23, listPrice: 9.99 };
let e = chewyBreakevenEcon(Object.assign({}, base, { spend: 100, directSales: 500, autoshipSales: 0 }));
near('net to us = wholesale x (1 - allowances)', e.net, 3.465);
near('contribution = net - cogs', e.contribution, 2.465);
near('BE ROAS = list / contribution', e.beRoas, 405.274, 0.01);
near('direct ROAS = direct / spend', e.directRoas, 500);
// 500% is +94.7 pts over the 405.3% break-even, but that is only 1.23x BE —
// inside the 1.25x "tight" band. Worth asserting: a 94-point cushion LOOKS
// comfortable and the band deliberately says otherwise.
t('500% vs a 405% break-even reads TIGHT, not clear', e.verdict, 'tight');
near('headroom = realised - BE, in points', e.headroom, 94.726, 0.01);
e = chewyBreakevenEcon(Object.assign({}, base, { spend: 100, directSales: 900, autoshipSales: 0 }));
t('900% is comfortably clear', e.verdict, 'clear');

// ⚠ THE IDENTITY. Spend EXACTLY N x contribution against N units of retail
// and the realised ROAS must land exactly on the break-even ROAS. This is the
// retail-vs-wholesale reconciliation, asserted rather than argued.
const N = 37;
e = chewyBreakevenEcon(Object.assign({}, base, {
  spend: N * 2.465, directSales: N * 9.99, autoshipSales: 0 }));
near('spending exactly N x contribution lands ON break-even', e.realisedRoas - e.beRoas, 0, 1e-6);
t('  and reads as tight, not clear', e.verdict, 'tight');

// Autoship is what keeps a subscription-heavy SKU from being condemned.
e = chewyBreakevenEcon(Object.assign({}, base, { spend: 100, directSales: 300, autoshipSales: 250 }));
near('realised ROAS folds in autoship', e.realisedRoas, 550);
near('  while direct ROAS does not', e.directRoas, 300);
t('direct alone would read as losing', 300 < e.beRoas, true);
t('  but realised clears it', e.verdict, 'clear');

// Verdict boundaries: < BE losing, < 1.25x BE tight, else clear.
const atRoas = (roas) => chewyBreakevenEcon(Object.assign({}, base,
  { spend: 100, directSales: roas, autoshipSales: 0 })).verdict;
t('just under BE is losing',      atRoas(405), 'losing');
t('just over BE is tight',        atRoas(410), 'tight');
t('just under 1.25x BE is tight', atRoas(506), 'tight');
t('at 1.25x BE is clear',         atRoas(507), 'clear');

// ⚠ contribution <= 0 gets its OWN verdict and a NULL break-even ROAS.
// A huge number there reads like a target; this is "no ROAS can ever pay".
e = chewyBreakevenEcon({ wholesale: 1.20, cogs: 1.00, standingPct: 23, listPrice: 9.99,
                         spend: 100, directSales: 5000, autoshipSales: 0 });
t('contribution <= 0 -> verdict never', e.verdict, 'never');
t('  and BE ROAS is null, not a giant number', e.beRoas, null);
t('  even on an enormous realised ROAS', e.realisedRoas > 4000, true);

// Degenerate shapes must not fabricate a verdict.
e = chewyBreakevenEcon({ wholesale: 4.5, cogs: 1, standingPct: 23, listPrice: 9.99,
                         spend: 0, directSales: 0, autoshipSales: 0 });
t('zero spend -> null ROAS', [e.directRoas, e.realisedRoas], [null, null]);
t('  and no verdict', e.verdict, null);
e = chewyBreakevenEcon({ wholesale: null, cogs: 1, standingPct: 23, listPrice: 9.99,
                         spend: 100, directSales: 500 });
t('no wholesale -> null contribution', e.contribution, null);
t('  and null BE ROAS', e.beRoas, null);
t('  but realised ROAS still computes', e.realisedRoas, 500);
e = chewyBreakevenEcon({ wholesale: 4.5, cogs: null, standingPct: 23, listPrice: 9.99,
                         spend: 100, directSales: 500 });
t('no COGS -> null contribution', e.contribution, null);
e = chewyBreakevenEcon({ wholesale: 4.5, cogs: 1, standingPct: 23, listPrice: null,
                         spend: 100, directSales: 500 });
t('no list price -> null BE ROAS', e.beRoas, null);
t('  contribution still computes', e.contribution != null, true);
// A zero allowance stack must not silently flatter the number by throwing.
e = chewyBreakevenEcon({ wholesale: 4.5, cogs: 1, standingPct: 0, listPrice: 9.99,
                         spend: 100, directSales: 500 });
near('zero allowances -> net == wholesale', e.net, 4.5);
near('  contribution = 3.50', e.contribution, 3.5);
let threw = false;
try { chewyBreakevenEcon({}); } catch (err) { threw = true; }
t('an empty argument object does not throw', threw, false);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
harness = harness.replace('ECON', fn('chewyBreakevenEcon'))
tmp = os.path.join(tempfile.gettempdir(), 'test_v1036_econ.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('break-even math')


# ═════════ F. behaviour — the parser ═════════
print('\nF. behaviour — parseChewyAdSpend (the real function)')

PROMOTED = (
 'Date,Advertiser,Advertiser Name,Campaign Type,Campaign ID,Campaign,Current Status,'
 'Promoted Product,Promoted Product Name,Category,Chewy List Price,Impressions,Clicks,'
 'CTR,CPC,Spend,Direct Units,Direct Sales,Direct ROAS,Total Orders,NTB Customers,'
 'Autoship Sign Ups,Autoship Actualized Sales,Autoship Actualized Orders\n'
 '2026-10-01,A1,Meowijuana,Chewy Max,C9,Top Products,Active,'
 '125631,"Meowijuana Meowi-Waui Catnip, Large",Cat Treats,$9.99,"1,000",40,'
 '4.00%,$0.63,$25.20,3,$29.97,118.9%,3,2,1,$12.00,1\n'
 '2026-10-02,A1,Meowijuana,Chewy Max,C9,Top Products,Active,'
 '125631,"Meowijuana Meowi-Waui Catnip, Large",Cat Treats,$9.99,500,20,'
 '4.00%,$0.63,$12.60,2,$19.98,158.6%,2,1,0,--,0\n'
 '2026-10-02,A2,Kitty Ka-Zoom,Sponsored Brand,C7,KK Brand,Active,'
 '999999,Unknown KK Thing,Cat Toys,$14.99,200,5,'
 '2.50%,$0.80,$4.00,0,$0.00,0%,0,0,0,$0.00,0\n'
)
KEYWORDS = ('Date,Advertiser Name,Campaign ID,Keyword,Match Type,Promoted Product,'
            'Impressions,Clicks,Spend,Direct Sales\n'
            '2026-10-01,Meowijuana,C9,catnip,exact,125631,10,1,$1.00,$0.00\n')
PURCHASED = ('Date,Advertiser Name,Campaign ID,Promoted Product,Purchased Product,'
             'Impressions,Clicks,Spend,Direct Sales\n'
             '2026-10-01,Meowijuana,C9,125631,125632,10,1,$1.00,$0.00\n')
NODATE = ('Advertiser Name,Campaign ID,Promoted Product,Promoted Product Name,'
          'Impressions,Clicks,Spend,Direct Sales\n'
          'Meowijuana,C9,125631,Thing,10,1,$1.00,$0.00\n')

parser = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
const threwWith = (label, fnc, rx) => {
  let msg = null;
  try { fnc(); } catch (e) { msg = (e && e.message) || String(e); }
  if (msg && rx.test(msg)) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + JSON.stringify(msg)); }
};

let allProducts = [{ master_id: 'SP-0121', chewy_sku: '125631' }];

COL
NUM
PARSE

const PROMOTED = __PROMOTED__;
const KEYWORDS = __KEYWORDS__;
const PURCHASED = __PURCHASED__;
const NODATE = __NODATE__;

// ⚠ The three Chewy reports share most columns. Half-parsing the wrong one
// into nonsense rows is worse than refusing it, so each is named explicitly.
threwWith('the Keywords report is refused by name', () => parseChewyAdSpend(KEYWORDS), /Keywords report/i);
threwWith('the Purchased Products report is refused by name', () => parseChewyAdSpend(PURCHASED), /Purchased Products/i);
threwWith('a report with no Date names Group by = Day', () => parseChewyAdSpend(NODATE), /Group by = Day/i);
threwWith('an empty file is refused', () => parseChewyAdSpend(''), /empty/i);

const p = parseChewyAdSpend(PROMOTED);
t('parses every row', p.rows.length, 3);
t('spans both advertisers', p.advertisers.sort(), ['Kitty Ka-Zoom', 'Meowijuana']);
t('collects the covered days', p.dates, ['2026-10-01', '2026-10-02']);

const r1 = p.rows.find(r => r.date === '2026-10-01');
t('strips $ and thousands separators', [r1.spend, r1.impressions], [25.20, 1000]);
t('  and % from a rate column is never read as spend', r1.clicks, 40);
t('parses the retail list price', r1.chewy_list_price, 9.99);
t('direct_sales is retail revenue, carried as-is', r1.direct_sales, 29.97);
t('resolves master_id via products.chewy_sku', r1.master_id, 'SP-0121');
t('carries the campaign id for the unique key', r1.campaign_id, 'C9');

// `--` is Chewy's blank marker and must read as 0, not NaN.
const r2 = p.rows.find(r => r.date === '2026-10-02' && r.chewy_sku === '125631');
t('Chewy’s -- blank marker reads as 0', r2.autoship_actualized_sales, 0);

// A quote-wrapped product name containing a comma must not shift the columns.
t('a quoted product name with a comma does not shift columns',
  r1.product_name, 'Meowijuana Meowi-Waui Catnip, Large');

// An ad SKU with no product is STORED, unlinked, and surfaced — not dropped.
const orphan = p.rows.find(r => r.chewy_sku === '999999');
t('an unmatched Chewy SKU is stored with a null master_id', orphan.master_id, null);
t('  and reported so the operator can fix the catalog', p.unmatched.size, 1);

// ⚠ A duplicate on the unique key would break the write. Deduped in-file.
const dupe = PROMOTED + PROMOTED.split('\n')[1] + '\n';
const d = parseChewyAdSpend(dupe);
t('a duplicate on (date, advertiser, sku, campaign) is deduped', d.rows.length, 3);
t('  and counted', d.dupes, 1);

// Malformed dates are skipped rather than poisoning the window.
const junk = PROMOTED + '\n' + 'Oct 3 2026,A1,Meowijuana,Chewy Max,C9,T,Active,125631,X,Cat,$9.99,1,1,1%,$1,$1,0,$0,0%,0,0,0,$0,0\n';
const jp = parseChewyAdSpend(junk);
t('a non-ISO date is skipped, not guessed', jp.rows.length, 3);
t('  and counted as skipped', jp.skipped >= 1, true);

// Column renames: Chewy has done this before (v7.03 rebates).
t('resolves a column by normalised name', _chewyAdCol(['Chewy List Price'], 'chewy_list_price'), 0);
t('  and returns -1 when absent', _chewyAdCol(['Spend'], 'Impressions'), -1);
t('_chewyAdNum strips $ , % and whitespace', [_chewyAdNum(' $1,234.50 '), _chewyAdNum('4.00%')], [1234.5, 4]);
t('_chewyAdNum on blanks and -- is 0', [_chewyAdNum(''), _chewyAdNum('--'), _chewyAdNum(null)], [0, 0, 0]);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
import json as _json
parser = (parser
          .replace('COL', fn('_chewyAdCol'))
          .replace('NUM', fn('_chewyAdNum'))
          .replace('PARSE', fn('parseChewyAdSpend'))
          .replace('__PROMOTED__', _json.dumps(PROMOTED))
          .replace('__KEYWORDS__', _json.dumps(KEYWORDS))
          .replace('__PURCHASED__', _json.dumps(PURCHASED))
          .replace('__NODATE__', _json.dumps(NODATE)))
tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1036_parse.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(parser)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip()[:1500])
    fails.append('parser behaviour')


# ═════════ G. the writer, and the honesty the page has to carry ═════════
print('\nG. static — the write path and the stated caveats')
up = fn('handleChewyAdSpendUpload')
# ⚠ DELETE+INSERT over the covered date range, so a weekly re-upload of an
# OVERLAPPING window refreshes rather than duplicating. That is the whole
# reason the report is scheduled on a trailing window: Chewy backfills
# autoship attribution for weeks after the click.
ok(".delete()" in up and ".gte('date'" in up and ".lte('date'" in up,
   'the write deletes the covered date range first')
ok(".in('advertiser'" in up, '  scoped to the advertisers in the file')
ok('.insert(' in up and 'upsert' not in up, '  then plain INSERT (no upsert)')
ok('500' in up, '  chunked')
ok(re.search(r'supabase_v10_36_chewy_ad_spend\.sql', up) is not None,
   'a missing table names the migration file instead of a raw error')
ok('logAudit' in up, 'the upload is audited')
loader = fn('loadChewyAdSpend')
ok('.range(' in loader and 'page * 1000' in loader,
   'the loader paginates (Architecture Rule #4)')

# ⚠ LTV ROAS does not exist per SKU. Nothing may claim it does.
be_block = js[js.index('function renderChewyBreakeven'):]
be_block = be_block[:be_block.index('function downloadChewyPnlCostCSV')]
ok('campaign' in be_block.lower() and 'ltv' in be_block.lower(),
   'the page states LTV ROAS is campaign-level only')
ok(not re.search(r"label:\s*'[^']*LTV", be_block),
   '  and no column claims to be a SKU-level LTV ROAS')
# v9.94 — a blank cell names WHICH gap it is, because the fixes differ.
ok('CHEWY_BE_GAP_MSG' in js, 'a named message per data gap')
for g in ['no-case-qty', 'no-cogs', 'no-catalog', 'no-cost', 'unknown-uom', 'no-list-price']:
    ok("'%s'" % g in js, '  gap named: %s' % g)
    ok('gap:%s' % g in src, '  and filterable: %s' % g)
# Jason's actual blocker: 79 CS SKUs carrying 98% of the spend have no case qty.
ok('Cost to Chewy' in js, 'the no-case-qty message points at the tab that fixes it')
# The allowance stack has to be visible, and its absence has to be loud.
ok('stack.source' in be_block and 'none' in be_block,
   'an empty allowance stack is called out (margins would read too optimistic)')


# ═════════ H. the class node --check cannot see ═════════
print('\nH. static — called-but-undefined / undeclared-identifier sweep')
# ⚠ `node --check` passes on a call to a function that does not exist and on a
# read of an identifier that was never declared — both are RUNTIME errors.
# That blind spot bit v10.8 (a span replacement deleted a function still being
# called), v10.25 (a SQL column out of scope) and v10.31 (a deleted block took
# a declaration with it and killed a whole page). This sweep is the only guard
# for it, so it runs over every function v10.36 added.
NEW_FNS = ['parseChewyAdSpend', 'handleChewyAdSpendUpload', 'loadChewyAdSpend',
           'chewyBreakevenEcon', 'renderChewyBreakeven', 'loadChewyBreakeven',
           'downloadChewyBreakevenCSV', 'chewyAdDrop', 'chewyBeShowGap',
           'getChewyBreakevenDateRange', 'chewyBreakevenSetSort',
           '_chewyAdCol', '_chewyAdNum']


def _strip(code):
    code = re.sub(r'/\*.*?\*/', ' ', code, flags=re.S)
    code = re.sub(r'(?m)//.*$', ' ', code)
    code = re.sub(r'`(?:\\.|[^`\\])*`', '``', code, flags=re.S)
    code = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", code)
    code = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', code)
    return code


# ⚠ Guard the guard (the v10.20 lesson — a masking bug makes a sweep pass
# against an empty haystack).
_probe = _strip("realCall(1); // fakeCall(2)\nconst s = 'alsoFake(3)';")
ok('realCall(' in _probe, 'the stripper keeps a real call')
ok('fakeCall(' not in _probe and 'alsoFake(' not in _probe,
   '  and drops one that only appears in a comment or a string')

_defined = set(re.findall(r'(?:^|\n)\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)', js))
_defined |= set(re.findall(r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)', js))
_BUILTIN = set("""if for while switch catch return typeof new function Number String Boolean
Array Object Math JSON Set Map Date parseInt parseFloat isFinite isNaN Promise Blob URL
document window console alert confirm prompt Error RegExp encodeURIComponent
decodeURIComponent setTimeout clearTimeout requestAnimationFrame localStorage fetch
Infinity await async of in do else try finally throw delete void""".split())


def _locals(body, name):
    out = set(re.findall(r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)', body))
    for grp in re.findall(r'(?:const|let|var)\s*\{([^}]*)\}', body):
        for x in grp.split(','):
            x = x.strip()
            if x:
                out.add(x.split(':')[-1].strip().split('=')[0].strip())
    m = re.search(r'function\s+%s\s*\(([^)]*)\)' % re.escape(name), body)
    if m:
        out |= {p.strip().split('=')[0].strip().lstrip('.') for p in m.group(1).split(',') if p.strip()}
    out |= set(re.findall(r'([A-Za-z_$][\w$]*)\s*=>', body))
    for grp in re.findall(r'\(([^)]*)\)\s*=>', body):
        for x in grp.split(','):
            x = x.strip()
            if x:
                out.add(x.split('=')[0].strip())
    return out


_missing = {}
for _name in NEW_FNS:
    _body = _strip(fn(_name))
    _loc = _locals(_body, _name)
    for _call in sorted(set(re.findall(r'(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(', _body))):
        if _call in _BUILTIN or _call in _loc or _call in _defined or _call == _name:
            continue
        _missing.setdefault(_name, set()).add(_call)
ok(not _missing, 'every function called by the v10.36 code is defined (%s)'
   % ('; '.join('%s: %s' % (k, sorted(v)) for k, v in sorted(_missing.items())) or 'none missing'))

for _name in ['chewyAdSpendData', 'chewyCatalogData', 'chewyCatalogByMaster',
              'chewyPnlSalesData', '_chewyPricingAllow', 'chewyBreakevenSortKey',
              'chewyBreakevenSortDir', 'chewyBreakevenVisibleRows', 'CHEWY_BE_GAP_MSG',
              'chewyPnlView']:
    ok(re.search(r'(?:const|let|var)\s+%s\b' % re.escape(_name), js) is not None,
       '  declared: %s' % _name)



# ═════════ I. v10.37 — the explainer is a tooltip, the empty state names the blocker ═════════
print('\nI. static — v10.37 no UI text bloat')
# ⚠ Jason flagged the prose banner for the FIFTH time (v9.67, v9.96, v10.24,
# v10.28, v10.37): "i've asked so many times to stop the text bloat ... stop
# editorializing. i JUST need descriptions". Asserted structurally so it cannot
# creep back: the panel renders ONE short line, everything else is a tooltip,
# and the tooltip is descriptions only.
_expl = be_block[be_block.index("getElementById('chpnl-be-explain')"):]
_expl = _expl[:_expl.index('// ── aggregate')]
ok("title=" in _expl, 'the explainer renders a tooltip')
ok('cursor:help' in _expl, '  marked as hoverable')
# The visible body is the text OUTSIDE the title attribute. Long prose there is
# the thing being banned.
_visible = re.sub(r'title="[^"]*"', '', _expl)
_strings = re.findall(r'`([^`]{120,})`', _visible)
_prose = [x for x in _strings if x.count(' ') > 18 and '<' not in x]
ok(not _prose, 'the visible body ships no long prose string (%s)' % (_prose[:1] or 'none'))
# A tooltip states what a number IS. It does not argue.
_tip = be_block[be_block.index('const TIP = ['):]
_tip = _tip[:_tip.index("].join(")]
for banned in ['which is what', 'deliberately', 'on purpose', 'worth knowing',
               'the N cancels', 'so the two sides', 'condemns']:
    ok(banned.lower() not in _tip.lower(), '  tooltip does not editorialize: "%s"' % banned)
ok('Break-even ROAS =' in _tip and 'Contribution per unit =' in _tip,
   '  tooltip states the formulas')
ok('per campaign only' in _tip, '  and that LTV ROAS is campaign-level')
# ⚠ The ONE thing that stays visible: a silently wrong number is worse than a
# short chip. With no rate-bearing rebate lines every break-even ROAS is too low.
ok('BE reads too low' in _expl, 'a missing allowance stack still warns VISIBLY')
ok(len('BE reads too low') < 40, '  as a chip, not a sentence')

print('\nI2. static — the empty state names the actual blocker')
# ⚠ Jason: "no data is populating here, what needs to be uploaded?" A missing
# table and a not-yet-uploaded report rendered the SAME sentence, because the
# loader swallowed the error with a console.warn. Three distinct states now.
ok('let chewyAdSpendTableMissing' in js, 'the loader records the missing-table case')
_load = fn('loadChewyAdSpend')
ok('chewyAdSpendTableMissing =' in _load, '  set from the caught error')
ok('schema cache' in _load, '  recognising PostgREST wording as well as Postgres')
ok('chewyAdSpendTableMissing = false' in _load, '  and cleared on a good load')
_empty = be_block[be_block.index('const empty ='):]
_empty = _empty[:_empty.index(';')]
ok('chewyAdSpendTableMissing' in _empty, 'empty state branches on the missing table')
ok('supabase_v10_36_chewy_ad_spend.sql' in _empty, '  naming the migration to run')
ok('Promoted products' in _empty, '  or the report to upload')
ok('Widen Window' in _empty, '  or that the window is simply too narrow')


# ═════════ J. v10.38 — Advertiser was a duplicate of Brand ═════════
print('\nJ. static — no duplicate dimension')
# Jason: "what is this 'advertiser' drop down? unnecessary". Chewy's advertiser
# account IS the brand, and a Brand dropdown sat next to it.
ok('chpnl-be-adv' not in src, 'the Advertiser dropdown is gone from the markup')
ok('chpnl-be-adv' not in js, '  and nothing reads it')
ok("label: 'Advertiser'" not in be_block, '  and the Advertiser column is gone')
# ⚠ The one thing Advertiser carried that Brand did not: an unmatched Chewy SKU
# has no product, so no products.brand — but the ad file still names the
# account. Dropping the control without this would have lost that.
ok('advToBrand' in be_block, 'brand falls back to the advertiser name')
for b in ['Meowijuana', 'Doggijuana', 'Kitty Ka-Zoom']:
    ok(b in be_block[be_block.index('advToBrand'):be_block.index('advToBrand') + 700],
       '  resolves %s' % b)
ok('rowBrand !== brand' in be_block, '  and the Brand filter uses the resolved value')
# Still a column in the CSV: it is raw source data, just not a UI dimension.
ok('advertiser' in exp, 'advertiser is still exported to CSV')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.36 — all green')
