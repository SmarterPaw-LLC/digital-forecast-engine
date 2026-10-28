# -*- coding: utf-8 -*-
"""v11.16 - the Ads sub-tab, campaign level, on both P&Ls. ONE renderer.

Jason: "there is still no ads tab" - looking at the Amazon P&L after v11.15
shipped only the pipeline half.

The assertions that earn their keep:

  * A4 THE NO-CAMPAIGN BUCKET IS IN THE TOTALS. amazon_ad_spend only learned
    `campaign` in v11.15 and Amazon cannot retrofit the dimension onto a past
    pull, so most of the history has none. The guard reproduces the naive
    "filter out the nulls" and proves it really does understate total spend -
    on the exact page built to judge whether the spend pays, where a clean
    wrong number is worse than a messy right one.

  * A5 TOTALS ARE SUMMED FROM ROWS, NOT AVERAGED ACROSS CAMPAIGNS. A $2
    campaign must not weigh the same as a $20,000 one. Asserted against a
    fixture where the two readings differ by a factor the eye can check.

  * A6 EVERY RATIO IS NULL, NEVER Infinity/NaN, ON A ZERO DENOMINATOR. A
    campaign with impressions and no clicks is ordinary, and "$Infinity CPC"
    reads as a crash.

  * C1 ONE RENDERER. The whole point of the release. If a second
    renderAdsCampaigns-shaped function appears, this fails.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name, got=None):
    global passed, failed
    if cond: passed += 1; print('  ok    ' + name)
    else:    failed += 1; print('  FAIL  %s%s' % (name, '' if got is None else '  got: %r' % (got,)))

def eq(name, got, want):
    ok(got == want, name, None if got == want else got)

CORE = js[js.index('const ADS_NO_CAMPAIGN'):js.index('const CHEWY_PROGRAM_COLUMNS')]


print('\n== A. the REAL rollup, driven as a pure function ==')

FIXTURE = r"""
// Amazon: two campaigns, one of them under TWO ad products, plus legacy rows
// with no campaign at all (the pre-v11.15 shape).
const AMZ = [
  { date:'2026-10-01', region:'US', campaign:'SP - Exact',  ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:1000, clicks:50, spend:10, purchases:5, attributed_sales:100 },
  { date:'2026-10-02', region:'US', campaign:'SP - Exact',  ad_product:'sponsored_brands',
    asin:'B1', master_id:'M1', impressions:2000, clicks:50, spend:20, purchases:5, attributed_sales:100 },
  { date:'2026-10-02', region:'US', campaign:'SB - Defense', ad_product:'sponsored_brands',
    asin:'B2', master_id:'M2', impressions:1000, clicks:0,  spend:20, purchases:0, attributed_sales:0 },
  // legacy: no campaign, and it is the BIGGEST spender in the window
  { date:'2026-10-03', region:'US', campaign:null, ad_product:'sponsored_display',
    asin:'B3', master_id:'M3', impressions:6000, clicks:100, spend:450, purchases:10, attributed_sales:300 },
  // outside the window - must not be counted at all
  { date:'2026-09-01', region:'US', campaign:'SP - Exact',  ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:9999, clicks:999, spend:999, purchases:99, attributed_sales:999 },
];

const CHW = [
  { date:'2026-10-01', advertiser:'Kitty Ka-Zoom', campaign:'KKZ Max', campaign_type:'Chewy Max',
    campaign_status:'Active', chewy_sku:'S1', impressions:5000, clicks:100, spend:50,
    direct_units:20, total_orders:10, direct_sales:200, ntb_customers:8, autoship_signups:3 },
  { date:'2026-10-02', advertiser:'Kitty Ka-Zoom', campaign:'KKZ Max', campaign_type:'Chewy Max',
    campaign_status:'Active', chewy_sku:'S2', impressions:5000, clicks:100, spend:50,
    direct_units:10, total_orders:5, direct_sales:100, ntb_customers:2, autoship_signups:1 },
  { date:'2026-10-02', advertiser:'Meowijuana', campaign:'Meowi SP', campaign_type:'Sponsored Product',
    campaign_status:'Paused', chewy_sku:'S3', impressions:1000, clicks:10, spend:5,
    direct_units:1, total_orders:1, direct_sales:9, ntb_customers:1, autoship_signups:0 },
];
const W = { from:'2026-10-01', to:'2026-10-31' };
const run = (channel, rows, extra) => adsCampaignRollup(Object.assign(
  { channel, rows, from: W.from, to: W.to, regionOk: false }, extra || {}));
"""

HARNESS = "\n".join([CORE, FIXTURE, r"""
const out = {};
const a = run('amazon', AMZ);
const c = run('chewy', CHW);

out.amzNames = a.campaigns.map(x => x.campaign).sort();
out.amzCount = a.coverage.campaignCount;          // NAMED campaigns only
out.amzRows  = a.campaigns.length;                 // including the bucket
out.amzSpend = a.totals.spend;
out.amzNoCampSpend = a.coverage.noCampaignSpend;
out.amzNoCampPct   = +a.coverage.noCampaignPct.toFixed(2);

// one campaign spanning TWO ad products collects both
const exact = a.campaigns.find(x => x.campaign === 'SP - Exact');
out.exactType  = exact.type;
out.exactSpend = exact.spend;
out.exactSkus  = exact.skus;
out.exactRoas  = exact.roas;
out.exactCtr   = +exact.ctr.toFixed(4);

// THE REGRESSION GUARD: the naive read that drops rows with no campaign.
const naive = a.campaigns.filter(x => !x.noCampaign)
  .reduce((t, x) => t + x.spend, 0);
out.naiveSpend = naive;
out.naiveUnderstatesBy = +(a.totals.spend - naive).toFixed(2);

// TOTALS ARE SUMMED, NOT AVERAGED. Mean of the per-campaign ROAS vs the real
// portfolio ROAS - the fixture is built so the two differ visibly.
const roasList = a.campaigns.map(x => x.roas).filter(v => v != null);
out.meanOfRoas  = +(roasList.reduce((s, v) => s + v, 0) / roasList.length).toFixed(4);
out.totalRoas   = +a.totals.roas.toFixed(4);

// ZERO DENOMINATORS
const sb = a.campaigns.find(x => x.campaign === 'SB - Defense');
out.zeroClicks = { cpc: sb.cpc, ctr: sb.ctr, roas: sb.roas, acos: sb.acos, cpa: sb.cpa };
out.zeroBlob   = JSON.stringify(a.campaigns) + JSON.stringify(a.totals);
out.zeroBad    = /Infinity|NaN|null,"?undefined/.test(out.zeroBlob);

// the window really excludes the September row
out.amzInWindow = a.coverage.inWindow;

// Chewy: brand filter narrows, metrics Amazon does not have are present
out.chwNames  = c.campaigns.map(x => x.campaign).sort();
out.chwNtb    = c.totals.ntb;
out.chwUnits  = c.totals.units;
out.chwStatus = (c.campaigns.find(x => x.campaign === 'Meowi SP') || {}).status;
const kkz = run('chewy', CHW, { brand: 'Kitty Ka-Zoom' });
out.chwBrandNames = kkz.campaigns.map(x => x.campaign);
out.chwBrandSpend = kkz.totals.spend;
out.chwSkus = c.campaigns.find(x => x.campaign === 'KKZ Max').skus;

// Amazon reports no units / no NTB: those stay NULL, never a fabricated 0.
out.amzUnits = a.totals.units;
out.amzNtb   = a.totals.ntb;

// adsTypeLabel de-slugs and keeps the acronyms upper
out.typeLabels = ['sponsored_products','sponsored_tv','dsp','some_new_format','', null]
  .map(adsTypeLabel);

// adsDiv guards
out.div = [adsDiv(1,0), adsDiv(0,0), adsDiv(1,'x'), adsDiv(null,2), adsDiv(10,4)];

// degenerate shapes
out.degenerate = [];
for (const rows of [[], [{}], [{ date:'2026-10-01' }]]) {
  try {
    const r = adsCampaignRollup({ channel:'amazon', rows, from:W.from, to:W.to, regionOk:false });
    out.degenerate.push({ rows: r.campaigns.length, spend: r.totals.spend,
      bad: /Infinity|NaN/.test(JSON.stringify(r.totals)) });
  } catch (e) { out.degenerate.push({ threw: String(e.message || e) }); }
}
console.log(JSON.stringify(out));
"""])

hpath = os.path.join(SP, 'test_v1116.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
# The middle dot in a joined type list comes back through this pipe. Without
# an explicit encoding, Python decodes node's UTF-8 stdout as the console
# codepage and every non-ASCII value silently changes - the v10.77 trap,
# in a harness. It failed A2a on a string that was correct all along.
res = subprocess.run(['node', hpath], capture_output=True, text=True,
                     encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:2500]); sys.exit(1)
R = json.loads(res.stdout)

# --- A1  grouping ----------------------------------------------------------
eq('A1a one row per campaign name, plus the no-campaign bucket',
   R['amzNames'], ['(no campaign)', 'SB - Defense', 'SP - Exact'])
eq('A1b the campaign COUNT excludes the bucket', R['amzCount'], 2)
eq('A1c while the row list includes it',         R['amzRows'],  3)
eq('A1d the window really excludes the September row', R['amzInWindow'], 4)

# --- A2  one campaign under two ad products -------------------------------
eq('A2a a campaign spanning two ad products collects BOTH',
   R['exactType'], 'Sponsored Brands \u00b7 Sponsored Products')
eq('A2b and sums across them', R['exactSpend'], 30)
eq('A2c counting the product once', R['exactSkus'], 1)
eq('A2d ROAS is sales over spend', R['exactRoas'], 200 / 30)
eq('A2e CTR is a percentage, not a fraction', R['exactCtr'], round(100 * 100 / 3000, 4))

# --- A3  type labels -------------------------------------------------------
eq('A3  adsTypeLabel de-slugs and keeps DSP/TV upper',
   R['typeLabels'],
   ['Sponsored Products', 'Sponsored TV', 'DSP', 'Some New Format', '', ''])

# --- A4  THE REGRESSION GUARD ---------------------------------------------
eq('A4a the no-campaign bucket carries real spend', R['amzNoCampSpend'], 450)
eq('A4b totals INCLUDE it',                         R['amzSpend'],       500)
eq('A4c the naive "drop the nulls" read really does understate',
   R['naiveSpend'], 50)
eq('A4d by the whole bucket', R['naiveUnderstatesBy'], 450)
eq('A4e and the coverage line states the share', R['amzNoCampPct'], 90.0)

# --- A5  summed, not averaged ---------------------------------------------
eq('A5a portfolio ROAS is total sales / total spend', R['totalRoas'], round(500 / 500, 4))
ok(abs(R['meanOfRoas'] - R['totalRoas']) > 0.5,
   'A5b and it is NOT the mean of the per-campaign ROAS, which the fixture '
   'makes visibly different', (R['meanOfRoas'], R['totalRoas']))

# --- A6  zero denominators -------------------------------------------------
eq('A6a a campaign with no clicks has NULL cpc, not Infinity',
   R['zeroClicks']['cpc'], None)
eq('A6b a campaign that SPENT and returned nothing has ROAS 0, not null - '
   'null would hide the worst row on the page', R['zeroClicks']['roas'], 0)
eq('A6c and NULL acos',            R['zeroClicks']['acos'], None)
eq('A6d no orders means NULL cpa', R['zeroClicks']['cpa'],  None)
eq('A6e CTR over real impressions is still a number', R['zeroClicks']['ctr'], 0)
eq('A6f nothing in the output leaks Infinity or NaN', R['zeroBad'], False)
eq('A6g adsDiv guards every bad denominator',
   R['div'], [None, None, None, None, 2.5])

# --- A7  per-channel metrics ----------------------------------------------
eq('A7a Chewy carries NTB, which Amazon does not report', R['chwNtb'], 11)
eq('A7b and ad units',                                    R['chwUnits'], 31)
eq('A7c Amazon leaves units NULL rather than a fabricated 0', R['amzUnits'], None)
eq('A7d and NTB likewise',                                    R['amzNtb'],   None)
eq('A7e Chewy carries campaign status', R['chwStatus'], 'Paused')
eq('A7f a Chewy campaign counts its distinct promoted SKUs', R['chwSkus'], 2)

# --- A8  brand filter ------------------------------------------------------
eq('A8a the brand filter narrows to that advertiser', R['chwBrandNames'], ['KKZ Max'])
eq('A8b and the totals follow it',                    R['chwBrandSpend'], 100)

# --- A9  degenerate --------------------------------------------------------
for i, d in enumerate(R['degenerate']):
    ok('threw' not in d, 'A9  degenerate shape %d does not throw' % i, d)
    ok(not d.get('bad'), 'A9  degenerate shape %d leaks no NaN/Infinity' % i, d)


print('\n== B. static - the registries ==')
ok("const ADS_CHANNELS = {" in js, 'B1  one channel registry')
for ch in ('amazon:', 'chewy:'):
    ok(ch in CORE, 'B2  %s channel is registered' % ch.rstrip(':'))
ok(CORE.count('host:') == 2, 'B3  exactly two hosts today', CORE.count('host:'))
ok("const ADS_COLUMNS = {" in js, 'B4  one column registry, keyed by channel')
ok("'(no campaign)'" in CORE, 'B5  the bucket is a NAMED constant, not a magic string')
_adsLabels = re.findall(r"label: '([^']+)'", CORE)
ok('Direct ACOS %' in _adsLabels and 'Actual ACOS %' not in _adsLabels,
   'B6  the Chewy tab scopes its ACOS rather than reusing the Break-Even label '
   'for a narrower population (rule 3a). Asserted on LABELS, not on the source '
   'text - the tip legitimately NAMES Actual ACOS % to say it is not that.',
   _adsLabels)
ok(any('Actual ACOS %' in t for t in re.findall(r"tip: '([^']*)'", CORE))
   or 'Actual ACOS %' in CORE,
   'B6b and the tip still explains the distinction, so nobody re-merges them')
vocab = js[js.index('const CHEWY_MEASURE_VOCAB = {'):js.index('const CHEWY_MEASURE_ALIASES')]
for lab in ['Campaign', 'Campaign Type', 'Status', 'SKUs', 'CTR %', 'CPC', 'CPA', 'Direct ACOS %']:
    ok("'%s':" % lab in vocab, 'B7  %r is declared in the vocabulary' % lab)

print('\n== C. static - ONE renderer, wired on both pages ==')
ok(js.count('function renderAdsCampaigns(') == 1,
   'C1  exactly ONE renderer', js.count('function renderAdsCampaigns('))
ok(js.count('function adsCampaignRollup(') == 1, 'C2  and ONE rollup')
ok(js.count('function adsEnsureShell(') == 1,
   'C3  and ONE shell builder - the markup is not duplicated per channel')
ok(js.count('function downloadAdsCampaignsCSV(') == 1, 'C4  and ONE exporter')
ok("loadAdsCampaigns('amazon')" in js and "loadAdsCampaigns('chewy')" in js,
   'C5  both P&Ls call the same loader')
ok("'pnl-amzn-tab-ads',        'ads'" in js, 'C6  the Amazon tab is in subtabApply')
ok("btn: 'chpnl-tab-ads'" in js,             'C7  the Chewy tab is in its TABS registry')
ok("'ads','adactivity'" in js.replace(" ", "") or "'ads'," in js,
   'C8  the Amazon view whitelist accepts it')
ok("ads:       { field: 'date'" in js,
   'C9  the Chewy Ads tab names its own feed for the shared period control')

print('\n== D. static - the standing rules ==')
ok("downloadAdsCampaignsCSV('amazon')" in js and "downloadAdsCampaignsCSV('chewy')" in js,
   'D1  both tabs are reachable from the top-bar CSV button')
ok("pnl_amazon_ads:   { id: 'amzads-search' }" in js
   and "pnl_chewy_ads:    { id: 'chads-search' }" in js,
   'D2  both page searches are registered with the global search bar')
ok("if (av === 'ads')       return 'pnl_amazon_ads';" in js,
   'D3  and the Amazon sub-view routes to its own key')
body = js[js.index('function renderAdsCampaigns('):js.index('function downloadAdsCampaignsCSV(')]
ok("pnlCardStrip" in body, 'D4  scorecards use the SHARED card renderer (rule #1)')
ok("pnlDeltaChip" in body, 'D5  and the shared delta chip')
ok(re.search(r"label: 'Ad Spend'[^}]*?null\)", body, re.S) is not None,
   'D6  the Ad Spend chip is NEUTRAL - a red chip there reads as "cut it"')
exp = js[js.index('function downloadAdsCampaignsCSV('):js.index('async function loadAdsCampaigns(')]
ok('_adsExport[channel]' in exp and 'adsCampaignRollup' not in exp,
   'D7  the CSV reads the render SNAPSHOT and never recomputes (the v8.00 rule)')
ok('# window:' in exp and '# brand:' in exp,
   'D8  and states its scope, so an archived file can be re-derived')
ok('no campaign on record' in exp,
   'D9  including how much of it predates campaign tracking')
ok('COLS.map' in body and 'tfoot' in body,
   'D10 the TOTAL row is KEYED off the same registry the header reads')

print('\n== E. static - the glyph rule ==')
amz = re.search(r'id="pnl-amzn-tab-ads".*?>([^<]*)</button>', s, re.S).group(1)
chw = re.search(r'id="chpnl-tab-ads".*?>([^<]*)</button>', s, re.S).group(1)
eq('E1  both Ads tabs carry the SAME glyph and label (rule #2)', amz.strip(), chw.strip())
ok(amz.strip().endswith('Ads'), 'E2  and the label is just "Ads"', amz)

print('\n' + '-' * 58)
print('v11.16: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
