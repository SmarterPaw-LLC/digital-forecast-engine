# -*- coding: utf-8 -*-
"""v11.22 - a Keywords (search terms) area on the Amazon Ads tab.

Jason: "give me another sub-page tab for keywords. do you have this data? I
need a way to see level of detail in the ads viewer for amazon, chewy,
walmart."

Amazon: yes - amazon_sp_search_term, MONTHLY grain, Sponsored Products only.
Chewy: no keyword dimension exists at all. Walmart: no ads feed. So the tab
exists only where the data does.

The assertions that earn their keep:

  * A1 THE CAMPAIGNS VIEW IS UNCHANGED BY CONSTRUCTION. A view-less rollup
    must be byte-identical to one before views existed, or this release
    silently moved the numbers on the tab Jason already uses. Asserted by
    running the same rows both ways and diffing the whole result.

  * A3 A MONTHLY FEED GETS A MONTHLY WINDOW. Comparing the report's
    period-END date against a daily window would include or drop a WHOLE
    month on where its last day fell. The guard reproduces that naive read
    and proves it really does disagree.

  * B2 TEXT IS DETECTED BY VALUE, NOT BY COLUMN NAME. The first cut
    special-cased campaign/type/status and sent everything else to the
    numeric formatter, so the Keywords table rendered `NaN` in its first two
    columns. Found by driving it, pinned here.
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
    else:    failed += 1; print('  FAIL  %s%s' % (name, '' if got is None else '  got: ' + ascii(got)))

def eq(name, got, want):
    ok(got == want, name, None if got == want else got)

CORE = js[js.index('const ADS_NO_CAMPAIGN'):js.index('const CHEWY_PROGRAM_COLUMNS')]


print('\n== A. the rollup, both views ==')

FIXTURE = r"""
var allProducts = [];
var amazonSpSearchTermCache = [];
const AMZ = [
  { date:'2026-10-01', region:'US', campaign:'C1', ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:1000, clicks:50, spend:100, purchases:5, attributed_sales:400 },
  { date:'2026-10-02', region:'US', campaign:'C2', ad_product:'sponsored_brands',
    asin:'B2', master_id:'M2', impressions:2000, clicks:25, spend:300, purchases:2, attributed_sales:150 },
];
// ONE term under TWO campaigns and TWO match types, plus a month outside.
const ST = [
  { reporting_month:'2026-10', reporting_date:'2026-10-31', customer_search_term:'catnip spray',
    match_type:'EXACT', campaign_name:'KW Exact', ad_group_name:'AG1', asin:'B1', master_id:'M1',
    impressions:12000, clicks:400, spend:520, orders_7d:60, units_7d:72, sales_7d:1800 },
  { reporting_month:'2026-10', reporting_date:'2026-10-31', customer_search_term:'catnip spray',
    match_type:'BROAD', campaign_name:'KW Broad', ad_group_name:'AG2', asin:'B1', master_id:'M1',
    impressions:30000, clicks:200, spend:260, orders_7d:10, units_7d:11, sales_7d:300 },
  { reporting_month:'2026-09', reporting_date:'2026-09-30', customer_search_term:'cat nip toys',
    match_type:'AUTO', campaign_name:'AUTO', ad_group_name:'AG3', asin:'B2', master_id:'M2',
    impressions:9000, clicks:90, spend:120, orders_7d:4, units_7d:4, sales_7d:60 },
  { reporting_month:'2026-06', reporting_date:'2026-06-30', customer_search_term:'old term',
    match_type:'EXACT', campaign_name:'OLD', ad_group_name:'AG4', asin:'B3', master_id:'M3',
    impressions:100, clicks:1, spend:2, orders_7d:0, units_7d:0, sales_7d:0 },
];
ADS_VIEWS.amazon.keywords.rows = () => ST;
const W = { from:'2026-09-01', to:'2026-10-28' };
"""

HARNESS = "\n".join([CORE, FIXTURE, r"""
const out = {};
// A1 - the campaigns path with and without the new `view` plumbing
const noView = adsCampaignRollup({ channel:'amazon', rows:AMZ, from:W.from, to:W.to, regionOk:false });
const asCamp = adsCampaignRollup({ channel:'amazon', view:'campaigns', rows:AMZ, from:W.from, to:W.to, regionOk:false });
const strip = (r) => JSON.stringify(r, (k, v) => v instanceof Set ? [...v].sort() : v);
out.campaignsIdentical = strip(noView) === strip(asCamp);
out.campaignsSpend = noView.totals.spend;

// A2 - keywords group by term, collecting campaigns and match types
const kw = adsCampaignRollup({ channel:'amazon', view:'keywords', from:W.from, to:W.to, regionOk:false });
out.terms = kw.campaigns.map(c => c.term).sort();
const spray = kw.campaigns.find(c => c.term === 'catnip spray');
out.sprayMatch    = spray.match;
out.sprayCampaign = spray.campaign;
out.spraySpend    = spray.spend;
out.sprayClicks   = spray.clicks;
out.sprayCvr      = +spray.cvr.toFixed(4);
out.sprayRoas     = +spray.roas.toFixed(4);
out.sprayAsins    = spray.skus;
out.kwMonths      = kw.coverage.months;
out.kwSpend       = kw.totals.spend;
out.kwTotalCvr    = +kw.totals.cvr.toFixed(4);

// A3 - THE MONTHLY WINDOW GUARD. The naive read compares reporting_date to the
// daily window; 2026-10-31 is AFTER a window ending 2026-10-28, so the whole
// October month would vanish.
const naive = ST.filter(r => r.reporting_date >= W.from && r.reporting_date <= W.to);
out.naiveMonths = [...new Set(naive.map(r => r.reporting_month))].sort();
out.naiveSpend  = naive.reduce((a, r) => a + r.spend, 0);

// A4 - a window with no overlapping month is honest, not a throw
const none = adsCampaignRollup({ channel:'amazon', view:'keywords', from:'2026-01-01', to:'2026-02-28', regionOk:false });
out.noneRows = none.campaigns.length;
out.noneMonths = none.coverage.months;
out.noneBad = /NaN|Infinity/.test(JSON.stringify(none.totals));

// A5 - the match filter narrows at row level here too
const ex = adsCampaignRollup({ channel:'amazon', view:'keywords', from:W.from, to:W.to,
                               regionOk:false, filters:{ match: new Set(['EXACT']) } });
const exSpray = ex.campaigns.find(c => c.term === 'catnip spray');
out.exactSpend = exSpray ? exSpray.spend : null;
out.exactMatch = exSpray ? exSpray.match : null;
out.exactOptions = ex.options.match;
console.log(JSON.stringify(out));
"""])

hpath = os.path.join(SP, 'test_v1122.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hpath], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:2500]); sys.exit(1)
R = json.loads(res.stdout)

# --- A1  THE CAMPAIGNS VIEW IS UNCHANGED ----------------------------------
ok(R['campaignsIdentical'],
   'A1a a view-less rollup is byte-identical to view="campaigns", so the tab '
   'Jason already uses cannot have moved')
eq('A1b and still totals the same', R['campaignsSpend'], 400)

# --- A2  keywords -----------------------------------------------------------
eq('A2a rows are grouped by SEARCH TERM', R['terms'], ['cat nip toys', 'catnip spray'])
eq('A2b a term targeted two ways collects BOTH match types',
   R['sprayMatch'], 'BROAD \u00b7 EXACT')
eq('A2c and both campaigns', R['sprayCampaign'], 'KW Broad \u00b7 KW Exact')
eq('A2d summing their spend',  R['spraySpend'], 780)
eq('A2e and their clicks',     R['sprayClicks'], 600)
eq('A2f CVR is derived from the window totals, not averaged across rows',
   R['sprayCvr'], round(100 * 70 / 600, 4))
eq('A2g ROAS likewise', R['sprayRoas'], round(2100 / 780, 4))
eq('A2h counting the advertised product once', R['sprayAsins'], 1)
eq('A2i the totals CVR is derived too', R['kwTotalCvr'], round(100 * 74 / 690, 4))

# --- A3  THE MONTHLY WINDOW GUARD -----------------------------------------
eq('A3a the monthly rule keeps both overlapping months',
   R['kwMonths'], ['2026-09', '2026-10'])
eq('A3b and their spend', R['kwSpend'], 900)
eq('A3c while the naive period-END read drops October entirely - its last day '
   'falls outside a window ending 2026-10-28', R['naiveMonths'], ['2026-09'])
eq('A3d losing most of the spend with nothing on screen to say so',
   R['naiveSpend'], 120)

# --- A4  honest empty ------------------------------------------------------
eq('A4a a window overlapping no month yields no rows', R['noneRows'], 0)
eq('A4b and says which months it found', R['noneMonths'], [])
ok(not R['noneBad'], 'A4c leaking no NaN/Infinity')

# --- A5  filters -----------------------------------------------------------
eq('A5a the match filter narrows at row level', R['exactSpend'], 520)
eq('A5b re-deriving the match cell',            R['exactMatch'], 'EXACT')
eq('A5c with the options still complete',       R['exactOptions'], ['AUTO', 'BROAD', 'EXACT'])


print('\n== B. the renderer is still ONE renderer ==')
ok(js.count('function renderAdsCampaigns(') == 1, 'B1a one renderer')
ok(js.count('function adsCampaignRollup(') == 1,  'B1b one rollup')
ok(js.count('function adsEnsureShell(') == 1,     'B1c one shell')
ok(js.count('function downloadAdsCampaignsCSV(') == 1, 'B1d one exporter')
rend = js[js.index('function renderAdsCampaigns('):js.index('function downloadAdsCampaignsCSV(')]
ok("typeof v === 'string'" in rend,
   'B2a TEXT IS DETECTED BY VALUE - the first cut named campaign/type/status '
   'and sent everything else to the numeric formatter, so Keywords rendered '
   'NaN in its first two columns')
ok("const NAMECOL = ch.groupBy || 'campaign'" in rend,
   'B2b and the name column comes from the view, not assumed to be "campaign"')
ok('shown[NAMECOL]' in rend,
   'B2c so the footer row-count lands in the right column')
ok('adsViewCfg(channel, view)' in rend, 'B3  the renderer resolves a view config')

print('\n== C. the view registry ==')
ok('const ADS_VIEWS = {' in js, 'C1  there is a view registry')
ok("chewy:" not in CORE[CORE.index('const ADS_VIEWS'):CORE.index('function adsViewCfg')],
   'C2  Chewy has NO keywords view - the vendor export carries no keyword '
   'dimension, and a tab that could only ever say "no data" is a live-looking '
   'control that does nothing (the v10.19 rule)')
cfg = js[js.index('const ADS_VIEWS'):js.index('function adsViewCfg')]
ok("noun: 'search term'" in cfg,
   'C3  the view declares its own NOUN, so the page does not call search terms '
   '"campaigns" next to a real campaign column (rule 3a)')
ok('inWindow:' in cfg and 'monthOf:' in cfg,
   'C4  and its own window rule, because its feed is monthly')
ok('sponsored_products' not in cfg.lower() or 'SPONSORED PRODUCTS ONLY' in cfg.upper(),
   'C5  the Sponsored-Products-only limit is stated where the view is defined')

print('\n== D. wiring ==')
ads = js[js.index('function switchPnlAdsView('):]
ads = ads[:ads.index('\n}\n')]
ok("'keywords'" in ads, 'D1  switchPnlAdsView knows the area')
ok("loadAdsCampaigns('amazon', 'keywords')" in ads, 'D2  and loads it')
ok('id="pnl-amzn-ads-tab-keywords"' in s and 'id="amzkw-host"' in s,
   'D3  the tab and its host exist')
ok("return 'adskeywords'" in js, 'D4  it names itself in the URL')
ok("view === 'adskeywords'" in js, 'D5  and is accepted back')
ok("pnlAdsView === 'keywords' ? 'keywords' : ''" in js,
   'D6  the top-bar CSV follows the active area')
rp = js[js.index('function renderPnl('):js.index('function renderPnlReport(')]
ok("renderAdsCampaigns('amazon', 'keywords')" in rp,
   'D7  and so does the filter-bar repaint - repainting only Campaigns would '
   'leave Keywords on a window nobody selected, the v11.17 bug one level down')

print('\n' + '-' * 58)
print('v11.22: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
