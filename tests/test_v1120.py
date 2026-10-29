# -*- coding: utf-8 -*-
"""v11.20 - Ads sub-page filters (ad type / status), and a readable icon.

Jason: "also i need ads sub-page filters for things like ad type etc." and
"change the icon for campaigns."

The assertions that earn their keep:

  * A2 THE FILTER NARROWS AT ROW LEVEL, INSIDE THE ROLLUP. A campaign can
    carry more than one ad product under one name, so filtering to Sponsored
    Products must drop that campaign's Brands spend and RE-DERIVE its totals.
    The guard builds exactly that campaign and proves the filtered row is
    smaller than the unfiltered one - a post-rollup filter would have kept the
    blended figure under a label claiming otherwise.

  * A4 THE OPTIONS SURVIVE BEING FILTERED. They are collected before the
    narrowing, and the renderer refills from an UNFILTERED pass, so picking a
    value cannot erase the others and strand the operator inside a filter
    they can no longer leave.

  * C1 OPTIONS COME FROM THE DATA. v11.14 passes an unrecognised Amazon ad
    product through as its own slug on purpose; a hardcoded filter list would
    hide exactly the thing that change exists to surface.
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


print('\n== A. the real rollup, filtered ==')

FIXTURE = r"""
var allProducts = [];
// ⚠ ONE campaign carrying TWO ad products - the case a post-rollup filter
// gets wrong. Plus a second campaign on a third type.
const AMZ = [
  { date:'2026-10-01', region:'US', campaign:'Dual', ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:1000, clicks:50, spend:100, purchases:5, attributed_sales:400 },
  { date:'2026-10-02', region:'US', campaign:'Dual', ad_product:'sponsored_brands',
    asin:'B1', master_id:'M1', impressions:2000, clicks:25, spend:300, purchases:2, attributed_sales:150 },
  { date:'2026-10-03', region:'US', campaign:'OnlyTV', ad_product:'sponsored_tv',
    asin:null, master_id:null, impressions:9000, clicks:5, spend:50, purchases:0, attributed_sales:0 },
  // an ad product the app has never seen: v11.14 passes it through as a slug
  { date:'2026-10-04', region:'US', campaign:'NewFmt', ad_product:'some_new_format',
    asin:'B2', master_id:'M2', impressions:500, clicks:4, spend:7, purchases:1, attributed_sales:20 },
];
const CHW = [
  { date:'2026-10-01', advertiser:'KKZ', campaign:'A', campaign_type:'Chewy Max',
    campaign_status:'ACTIVE', chewy_sku:'S1', impressions:100, clicks:10, spend:50,
    direct_units:5, total_orders:3, direct_sales:200, ntb_customers:2, autoship_signups:1 },
  { date:'2026-10-02', advertiser:'KKZ', campaign:'B', campaign_type:'Sponsored Product',
    campaign_status:'PAUSED', chewy_sku:'S2', impressions:200, clicks:5, spend:20,
    direct_units:1, total_orders:1, direct_sales:30, ntb_customers:1, autoship_signups:0 },
];
const W = { from:'2026-10-01', to:'2026-10-31' };
const run = (channel, rows, filters) => adsCampaignRollup(
  { channel, rows, from:W.from, to:W.to, regionOk:false, filters: filters || {} });
"""

HARNESS = "\n".join([CORE, FIXTURE, r"""
const out = {};
const all = run('amazon', AMZ);
out.allTypes   = all.options.type;
out.allSpend   = all.totals.spend;
out.allRows    = all.campaigns.length;

// ⚠ filter to Sponsored Products: the Dual campaign must SHRINK, not vanish
// and not keep its blended spend.
const sp = run('amazon', AMZ, { type: new Set(['Sponsored Products']) });
const dualAll = all.campaigns.find(c => c.campaign === 'Dual');
const dualSp  = sp.campaigns.find(c => c.campaign === 'Dual');
out.dualAllSpend  = dualAll.spend;
out.dualAllType   = dualAll.type;
out.dualSpSpend   = dualSp ? dualSp.spend : null;
out.dualSpType    = dualSp ? dualSp.type : null;
out.dualSpSales   = dualSp ? dualSp.sales : null;
out.dualSpRoas    = dualSp ? +dualSp.roas.toFixed(4) : null;
out.spRows        = sp.campaigns.map(c => c.campaign).sort();
out.spSpend       = sp.totals.spend;
out.spFilteredOut = sp.coverage.filteredOut;
out.spActive      = sp.coverage.filters;

// the OPTIONS must survive being filtered, or you cannot get back out
out.spOptions = sp.options.type;

// an unknown ad product is offered as itself, never bucketed away
out.hasNewFormat = all.options.type.indexOf('Some New Format') > -1;

// Chewy filters on two dimensions
const cAll = run('chewy', CHW);
out.chwTypes    = cAll.options.type;
out.chwStatuses = cAll.options.status;
const cPaused = run('chewy', CHW, { status: new Set(['PAUSED']) });
out.chwPausedRows  = cPaused.campaigns.map(c => c.campaign);
out.chwPausedSpend = cPaused.totals.spend;
const cBoth = run('chewy', CHW, { status: new Set(['PAUSED']), type: new Set(['Chewy Max']) });
out.chwBothRows = cBoth.campaigns.map(c => c.campaign);

// an unfiltered call is byte-identical to one with an empty filter map
const a1 = JSON.stringify(run('amazon', AMZ).totals);
const a2 = JSON.stringify(run('amazon', AMZ, {}).totals);
const a3 = JSON.stringify(run('amazon', AMZ, { type: new Set() }).totals);
out.emptyFilterIsNoop = (a1 === a2) && (a2 === a3);

// a value that matches nothing yields an honest empty result, not a throw
const none = run('amazon', AMZ, { type: new Set(['Nope']) });
out.noMatch = { rows: none.campaigns.length, spend: none.totals.spend,
                bad: /NaN|Infinity/.test(JSON.stringify(none.totals)) };
console.log(JSON.stringify(out));
"""])

hpath = os.path.join(SP, 'test_v1120.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hpath], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:2500]); sys.exit(1)
R = json.loads(res.stdout)

# --- A1  options come from the data ---------------------------------------
eq('A1a every ad product in the window is offered, sorted', R['allTypes'],
   ['Some New Format', 'Sponsored Brands', 'Sponsored Products', 'Sponsored TV'])
ok(R['hasNewFormat'],
   'A1b including one the app has never seen - v11.14 passes an unrecognised '
   'ad product through as its own slug, and a hardcoded list would hide it')

# --- A2  THE ROW-LEVEL GUARD ----------------------------------------------
eq('A2a unfiltered, the dual-product campaign carries BOTH', R['dualAllType'],
   'Sponsored Brands \u00b7 Sponsored Products')
eq('A2b and both spends', R['dualAllSpend'], 400)
eq('A2c filtered to Sponsored Products it SURVIVES', R['dualSpType'], 'Sponsored Products')
eq('A2d but SHRINKS to just that product\'s spend - a post-rollup filter would '
   'have kept $400 under a label saying Sponsored Products', R['dualSpSpend'], 100)
eq('A2e with sales narrowed to match',      R['dualSpSales'], 400)
eq('A2f and the ratios RE-DERIVED, not carried over', R['dualSpRoas'], 4.0)
eq('A2g a campaign with none of that type drops out entirely',
   R['spRows'], ['Dual'])
eq('A2h totals follow',       R['spSpend'], 100)
eq('A2i and the rows dropped are counted', R['spFilteredOut'], 3)
eq('A2j the active filter is reported back for the coverage line and the CSV',
   R['spActive'], {'type': ['Sponsored Products']})

# --- A3  no-op guarantee ---------------------------------------------------
ok(R['emptyFilterIsNoop'],
   'A3  an absent, empty-object or empty-Set filter is byte-identical to no '
   'filter, so every existing caller is unaffected')

# --- A4  THE OPTIONS SURVIVE FILTERING ------------------------------------
eq('A4  the option list is collected BEFORE narrowing, so picking a value '
   'cannot erase the others and strand you inside a filter you cannot leave',
   R['spOptions'],
   ['Some New Format', 'Sponsored Brands', 'Sponsored Products', 'Sponsored TV'])

# --- A5  Chewy, two dimensions --------------------------------------------
eq('A5a Chewy offers its campaign types', R['chwTypes'], ['Chewy Max', 'Sponsored Product'])
eq('A5b and its statuses',                R['chwStatuses'], ['ACTIVE', 'PAUSED'])
eq('A5c filtering by status narrows',     R['chwPausedRows'], ['B'])
eq('A5d and the totals follow',           R['chwPausedSpend'], 20)
eq('A5e two filters AND together',        R['chwBothRows'], [])

# --- A6  degenerate --------------------------------------------------------
eq('A6a a value matching nothing yields an empty result', R['noMatch']['rows'], 0)
eq('A6b with zero spend, not NaN',  R['noMatch']['spend'], 0)
ok(not R['noMatch']['bad'], 'A6c and leaks no NaN/Infinity', R['noMatch'])


print('\n== B. the strip is built from the adapter ==')
ok("filters: [{ k: 'type', label: 'Ad type' }]" in CORE,
   'B1  Amazon declares one dimension - its unified report has no status')
ok("{ k: 'status', label: 'Status' }" in CORE,
   'B2  Chewy declares two')
shell = js[js.index('function adsEnsureShell('):js.index('function renderAdsCampaigns(')]
ok('(ch.filters || []).map' in shell,
   'B3  the strip is generated from that declaration, not hand-written per channel')
ok(shell.count('-f-${f.k}') >= 1, 'B4  one control per dimension, id\'d by it')
rend = js[js.index('function renderAdsCampaigns('):js.index('function downloadAdsCampaignsCSV(')]
ok('optsRes' in rend and 'Object.keys(picked).length' in rend,
   'B5  the renderer refills from an UNFILTERED pass over the same window')
ok("sel.value = opts.includes(keep) ? keep : ''" in rend,
   'B6  a pick the window no longer contains falls back to All rather than '
   'leaving the control on a value the table cannot show')
ok('res.coverage.filters' in rend,
   'B7  and the coverage line states what is active (the v10.99 rule)')
exp = js[js.index('function downloadAdsCampaignsCSV('):js.index('async function loadAdsCampaigns(')]
ok("'# filters: '" in exp,
   'B8  the CSV states them too, so an archived file can be re-derived')

print('\n== C. the Campaigns icon ==')
strip = s[s.index('id="pnl-amzn-ads-tab-campaigns"'):]
strip = strip[:strip.index('</div>')]
camp = re.search(r'>([^<]*)</button>', strip).group(1).strip()
glyph = camp.split(' ')[0]
others = re.findall(r'class="subtab[^"]*"[^>]*>([^<]*)</button>', s)
clash = [o.strip() for o in others
         if o.strip().startswith(glyph) and not o.strip().endswith('Campaigns')]
eq('C1  the new glyph is not already carrying another tab label (rule #2)', clash, [])
ok(glyph != '\U0001f5c2', 'C2  and it is not the old one', glyph)
ok(camp.endswith('Campaigns'), 'C3  the label is unchanged', camp)

print('\n' + '-' * 58)
print('v11.20: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
