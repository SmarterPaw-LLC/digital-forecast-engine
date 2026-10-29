# -*- coding: utf-8 -*-
"""v11.23 - checkbox selection + a trend chart on every Ads view.

Jason: "i should be able to multiselect with checkboxes and have the
scorecards change. there should also be a line graph. i want functionality
like exists on the summary page."

The assertions that earn their keep:

  * A1 THE CONSOLIDATION IS A NO-OP. Three places were about to sum ads rows
    and derive the ratios (the window TOTAL, the footer, the selection). They
    now share one helper. The guard reproduces the pre-v11.23 hand-written
    total loop and requires a BYTE-IDENTICAL result, so "the refactor changed
    nothing" is checkable rather than read off a diff.

  * A2 AN UNBUCKETED ROLLUP RETURNS THE OLD OBJECT. The chart series rides
    along only when a bucket grain is asked for - and the rest of the result
    is deep-equal either way, so the chart cannot have changed the table.

  * B1 SELECTION RATIOS ARE SUMMED, NOT AVERAGED. Two campaigns an order of
    magnitude apart, where the mean of the two ROAS values and the ROAS of
    the sum are visibly different numbers. Averaging would weight a $20
    campaign the same as a $2,000 one.

  * C THE PRIOR PERIOD took neither the view nor the filters (both shipped in
    v11.22). The guard runs the old call shape and proves it really did read
    a DIFFERENT TABLE on the Keywords tab, and really did compare a filtered
    window against an unfiltered one.

  * D A MONTHLY VIEW'S PRIOR BLOCK. The naive day-shift is run through the
    REAL prev block lifted out of the renderer, and proved to land inside the
    month it is supposed to be compared against.

  * I THE EXPORTER WROTE NaN. v11.22b fixed text-detection in the table and
    left the CSV on the old rule; the guard reproduces it on a search-term
    row and gets the literal string 'NaN'.
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

def fnbody(name, kind='function'):
    i = js.index('%s %s(' % (kind, name))
    j = js.index('{', js.index(')', i))
    d, k = 0, j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k + 1]
        k += 1

CORE = js[js.index('const ADS_NO_CAMPAIGN'):js.index('const CHEWY_PROGRAM_COLUMNS')]
RENDER = fnbody('renderAdsCampaigns')

# ⚠ The REAL prev block, lifted out of the renderer by its own boundaries so
# the monthly-window assertions drive shipped code rather than a copy of it.
_pi = RENDER.index('  let prev = null;')
_pj = RENDER.index('  // The export reads this SNAPSHOT')
PREV_BLOCK = RENDER[_pi:_pj]


print('\n== A. the consolidation, and the unbucketed no-op ==')

FIXTURE = r"""
// Two campaigns an ORDER OF MAGNITUDE apart, so a summed ratio and an
// averaged one are visibly different numbers.
var amazonAdSpendData = [
  { date:'2026-10-01', region:'US', campaign:'Big', ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:100000, clicks:2000, spend:2000,
    purchases:200, attributed_sales:2000 },
  { date:'2026-10-08', region:'US', campaign:'Big', ad_product:'sponsored_brands',
    asin:'B1', master_id:'M1', impressions:50000, clicks:500, spend:0,
    purchases:0, attributed_sales:0 },
  { date:'2026-10-15', region:'US', campaign:'Small', ad_product:'sponsored_products',
    asin:'B2', master_id:'M2', impressions:1000, clicks:40, spend:20,
    purchases:8, attributed_sales:200 },
  { date:'2026-10-22', region:'US', campaign:'Quiet', ad_product:'sponsored_tv',
    asin:null, master_id:null, impressions:9000, clicks:0, spend:40,
    purchases:0, attributed_sales:0 },
];
// The Keywords view reads a DIFFERENT TABLE, which is what makes C1 provable.
var amazonSpSearchTermCache = [
  { reporting_month:'2026-09', reporting_date:'2026-09-30', customer_search_term:'catnip spray',
    match_type:'broad', campaign_name:'SP - Auto', ad_group_name:'AG1', asin:'B1',
    impressions:500, clicks:20, spend:30, orders_7d:2, units_7d:3, sales_7d:60 },
  { reporting_month:'2026-10', reporting_date:'2026-10-31', customer_search_term:'catnip spray',
    match_type:'exact', campaign_name:'SP - KW', ad_group_name:'AG2', asin:'B1',
    impressions:800, clicks:40, spend:70, orders_7d:6, units_7d:7, sales_7d:300 },
  { reporting_month:'2026-10', reporting_date:'2026-10-31', customer_search_term:'cat toys',
    match_type:'broad', campaign_name:'SP - Auto', ad_group_name:'AG1', asin:'B2',
    impressions:200, clicks:5, spend:9, orders_7d:0, units_7d:0, sales_7d:0 },
];
var pnlRegion = 'US';
const W = { from:'2026-10-01', to:'2026-10-31' };
const run = (opts) => adsCampaignRollup(Object.assign(
  { channel:'amazon', from:W.from, to:W.to, regionOk:false }, opts || {}));
"""

HARNESS = "\n".join([CORE, FIXTURE, r"""
const out = {};

// ── A1 the pre-v11.23 hand-written total loop, reproduced verbatim ────────
function oldTotals(campaigns, GROUP) {
  const t = { campaign: 'TOTAL', types: new Set(), statuses: new Set(), skuSet: new Set(),
              matches: new Set(), campaigns: new Set(), adgroups: new Set(),
              impressions: 0, clicks: 0, spend: 0, orders: 0, units: 0, sales: 0,
              ntb: 0, signups: 0, hasUnits: false, hasNtb: false, firstDate: '', lastDate: '' };
  for (const c of campaigns) {
    t.impressions += c.impressions; t.clicks += c.clicks; t.spend += c.spend;
    t.orders += c.orders; t.sales += c.sales; t.signups += c.signups;
    if (c.units != null) { t.units += c.units; t.hasUnits = true; }
    if (c.ntb   != null) { t.ntb   += c.ntb;   t.hasNtb   = true; }
    c.skuSet.forEach(s => t.skuSet.add(s));
    c.types.forEach(s => t.types.add(s));
    if (!t.firstDate || (c.firstDate && c.firstDate < t.firstDate)) t.firstDate = c.firstDate;
    if (c.lastDate > t.lastDate) t.lastDate = c.lastDate;
  }
  return adsDeriveRow(t, GROUP);
}
const plain = (o) => JSON.stringify(o, (k, v) =>
  (v instanceof Set) ? [...v].sort() : v);

const base = run();
out.oldVsNew = plain(oldTotals(base.campaigns.map(c => c), 'campaign'))
            === plain(base.totals);
out.totalSpend = base.totals.spend;
out.totalRoas  = +base.totals.roas.toFixed(4);

// ── A2 unbucketed vs bucketed ─────────────────────────────────────────────
const noB = run();
const wkB = run({ bucket: 'week' });
out.noSeriesKey   = !('series'  in noB);
out.noBucketsKey  = !('buckets' in noB);
out.hasSeriesKey  = ('series' in wkB) && ('buckets' in wkB);
const strip = (o) => { const c = Object.assign({}, o); delete c.series; delete c.buckets; return plain(c); };
out.bucketIsAdditive = strip(noB) === strip(wkB);

// ── B selection arithmetic ────────────────────────────────────────────────
const big   = base.campaigns.find(c => c.campaign === 'Big');
const small = base.campaigns.find(c => c.campaign === 'Small');
out.bigRoas   = +big.roas.toFixed(4);
out.smallRoas = +small.roas.toFixed(4);
out.meanRoas  = +((big.roas + small.roas) / 2).toFixed(4);
const selBoth = adsSumRows([big, small], 'campaign');
out.selRoas   = +selBoth.roas.toFixed(4);
out.selSpend  = selBoth.spend;
out.selSkus   = selBoth.skus;
const selOne  = adsSumRows([small], 'campaign');
out.oneSpend  = selOne.spend;
out.oneRoas   = +selOne.roas.toFixed(4);
const selNone = adsSumRows([], 'campaign');
out.noneShape = { spend: selNone.spend, roas: selNone.roas, ctr: selNone.ctr,
                  bad: /NaN|Infinity/.test(JSON.stringify(selNone)) };

// ── C the prior period dropped the view and the filters ───────────────────
const kwNow  = adsCampaignRollup({ channel:'amazon', view:'keywords', from:W.from, to:W.to, regionOk:false });
const oldPrev = adsCampaignRollup({ channel:'amazon', from:W.from, to:W.to, regionOk:false });
out.kwSpend      = kwNow.totals.spend;
out.oldPrevSpend = oldPrev.totals.spend;
out.kwReadsOtherTable = kwNow.totals.spend !== oldPrev.totals.spend;

const filt    = run({ filters: { type: new Set(['Sponsored Products']) } });
const unfilt  = run();
out.filtSpend   = filt.totals.spend;
out.unfiltSpend = unfilt.totals.spend;

// ── D the monthly prior block, through the REAL renderer code ─────────────
// A 15-day window inside one month: shifting it back 15 days lands in the
// SAME month, which is the bug.
function prevFor(view, win, res) {
  const ch = adsViewCfg('amazon', view);
  const channel = 'amazon', brand = '', picked = {};
  let __out = null;
  (function () {
__PREV__
    __out = prev;
  })();
  return __out;
}
const kwMid = adsCampaignRollup({ channel:'amazon', view:'keywords',
  from:'2026-10-15', to:'2026-10-29', regionOk:false });
out.kwMidMonths = kwMid.coverage.months;
const kwPrev = prevFor('keywords', { from:'2026-10-15', to:'2026-10-29' }, kwMid);
out.kwPrevMonths = kwPrev ? kwPrev.coverage.months : null;
out.kwPrevWindow = kwPrev ? [kwPrev.coverage.from, kwPrev.coverage.to] : null;
// the naive day-shift, reproduced
const d0 = new Date('2026-10-15T00:00:00'), d1 = new Date('2026-10-29T00:00:00');
const len = Math.round((d1 - d0) / 86400000) + 1;
const nTo = new Date(d0.getTime() - 86400000);
const nFrom = new Date(nTo.getTime() - (len - 1) * 86400000);
const naive = adsCampaignRollup({ channel:'amazon', view:'keywords',
  from: adsYmd(nFrom), to: adsYmd(nTo), regionOk:false });
out.naivePrevMonths = naive.coverage.months;

// a daily view still gets the day-shifted block
const dayPrev = prevFor('', { from:'2026-10-15', to:'2026-10-29' }, run());
out.dayPrevWindow = dayPrev ? [dayPrev.coverage.from, dayPrev.coverage.to] : null;

// ── F bucketing ───────────────────────────────────────────────────────────
const chAmz = adsViewCfg('amazon', '');
const chKw  = adsViewCfg('amazon', 'keywords');
out.grain14  = adsGrain({ from:'2026-10-01', to:'2026-10-14' }, chAmz);
out.grain180 = adsGrain({ from:'2026-05-01', to:'2026-10-27' }, chAmz);
out.grain500 = adsGrain({ from:'2025-06-01', to:'2026-10-13' }, chAmz);
out.grainKw  = adsGrain({ from:'2026-10-01', to:'2026-10-14' }, chKw);
out.grainNoWin = adsGrain({}, chAmz);

const wk = run({ bucket:'week' });
out.weekBuckets = wk.buckets;
out.allSundays  = wk.buckets.every(b => new Date(b + 'T00:00:00').getDay() === 0);
// the series must sum back to the campaign totals, or the chart and the
// table are describing different data
out.seriesMatchesTable = base.campaigns.every(c => {
  const by = wk.series[c.campaign] || {};
  const sum = Object.values(by).reduce((a, s) => a + s.spend, 0);
  return Math.abs(sum - c.spend) < 1e-9;
});
const dayR = run({ bucket:'day' });
out.dayBuckets = dayR.buckets;
const kwB = adsCampaignRollup({ channel:'amazon', view:'keywords', from:W.from, to:W.to,
  regionOk:false, bucket:'day' });
out.kwBuckets = kwB.buckets;   // a monthly feed buckets by MONTH whatever is asked

// ── G partial edge buckets ────────────────────────────────────────────────
out.edgesDay  = adsBucketEdges(dayR.buckets, 'day', W);
out.edgesWeek = adsBucketEdges(wk.buckets, 'week', W);
// a window that starts AND ends on a week boundary has no partial edge
out.edgesAligned = adsBucketEdges(['2026-10-04','2026-10-11'], 'week',
  { from:'2026-10-04', to:'2026-10-17' });

// ── H metrics from the registry ───────────────────────────────────────────
const mAmz = adsChartMetrics(ADS_COLUMNS.amazon).map(m => m.k);
const mChw = adsChartMetrics(ADS_COLUMNS.chewy).map(m => m.k);
const mKw  = adsChartMetrics(adsViewCfg('amazon','keywords').columns).map(m => m.k);
out.mAmz = mAmz; out.mChw = mChw; out.mKw = mKw;
const roas = adsChartMetrics(ADS_COLUMNS.amazon).find(m => m.k === 'roas');
out.roasSpec = { unit: roas.unit, noStack: !!roas.noStack, isPct: !!roas.isPct };
const acos = adsChartMetrics(ADS_COLUMNS.amazon).find(m => m.k === 'acos');
out.acosSpec = { unit: acos.unit, noStack: !!acos.noStack, isPct: !!acos.isPct };
// derived from a SUMMED slot, never averaged
out.roasOfSum = roas.sum({ spend: 100, sales: 400 });
out.roasOfZero = roas.sum({ spend: 0, sales: 400 });
out.ctrOfSum = +adsChartMetrics(ADS_COLUMNS.amazon).find(m => m.k === 'ctr')
  .sum({ clicks: 25, impressions: 1000 }).toFixed(4);

// ── I the exporter's old text rule ────────────────────────────────────────
const f2 = (v) => v == null ? '' : Number(v).toFixed(2);
const i0 = (v) => v == null ? '' : String(Math.round(Number(v)));
const oldVal = (c, k) => {
  if (k === 'campaign' || k === 'type' || k === 'status') return c[k] || '';
  if (k === 'spend' || k === 'sales' || k === 'cpc' || k === 'cpa'
      || k === 'ctr' || k === 'acos' || k === 'roas') return f2(c[k]);
  return i0(c[k]);
};
const newVal = (c, k) => {
  const v = c[k];
  if (typeof v === 'string') return v;
  if (v == null) return '';
  if (k === 'spend' || k === 'sales' || k === 'cpc' || k === 'cpa'
      || k === 'ctr' || k === 'acos' || k === 'roas') return f2(v);
  return i0(v);
};
const kwRow = kwNow.campaigns.find(c => c.term === 'catnip spray');
// A WIDER window, so the same term's two match types merge into one row and
// the joined list is a real string rather than a single value.
const kwWide = adsCampaignRollup({ channel:'amazon', view:'keywords',
  from:'2026-09-01', to:'2026-10-31', regionOk:false });
const kwWideRow = kwWide.campaigns.find(c => c.term === 'catnip spray');
out.wideValMatch = newVal(kwWideRow, 'match');
out.wideValSpend = newVal(kwWideRow, 'spend');
out.wideOldMatch = oldVal(kwWideRow, 'match');
out.oldValTerm  = oldVal(kwRow, 'term');
out.oldValMatch = oldVal(kwRow, 'match');
out.newValTerm  = newVal(kwRow, 'term');
out.newValMatch = newVal(kwRow, 'match');
out.newValSpend = newVal(kwRow, 'spend');

// ── J the search haystack ─────────────────────────────────────────────────
const hay = (c, COLS) => COLS.map(col => c[col.k])
  .filter(v => typeof v === 'string').join(' ').toLowerCase();
const oldHay = (c) => (c.campaign + ' ' + c.type + ' ' + c.status).toLowerCase();
out.oldHayFindsTerm = oldHay(kwRow).indexOf('catnip spray') > -1;
out.newHayFindsTerm = hay(kwRow, adsViewCfg('amazon','keywords').columns).indexOf('catnip spray') > -1;

console.log(JSON.stringify(out));
"""]).replace('__PREV__', PREV_BLOCK)

hpath = os.path.join(SP, 'test_v1123.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hpath], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:3000]); sys.exit(1)
R = json.loads(res.stdout)

ok(R['oldVsNew'],
   'A1a adsSumRows is BYTE-IDENTICAL to the hand-written total loop it replaced')
eq('A1b and the window total is the real one', R['totalSpend'], 2060)
eq('A1c with the ratio derived from the sums', R['totalRoas'], 1.068)

ok(R['noSeriesKey'] and R['noBucketsKey'],
   'A2a an unbucketed rollup gains NO new key - every pre-v11.23 caller reads '
   'exactly the object it always did')
ok(R['hasSeriesKey'], 'A2b and a bucketed one carries the series')
ok(R['bucketIsAdditive'],
   'A2c with everything else deep-equal, so asking for a chart cannot have '
   'moved a number in the table')


print('\n== B. selection narrows the cards, and sums before it divides ==')
eq('B1a the big campaign returns 1.00x', R['bigRoas'], 1.0)
eq('B1b the small one returns 10.00x',   R['smallRoas'], 10.0)
eq('B1c their MEAN would be 5.50x',      R['meanRoas'], 5.5)
eq('B1d selecting both reads 1.09x - summed, not averaged. An average weights '
   'a $20 campaign the same as a $2,000 one', R['selRoas'], 1.0891)
eq('B2a selecting one narrows the spend',  R['oneSpend'], 20)
eq('B2b and re-derives its ratio',         R['oneRoas'], 10.0)
eq('B2c distinct SKUs come from the union', R['selSkus'], 2)
eq('B3  an empty selection is zeroes and nulls, never NaN or Infinity',
   R['noneShape'], {'spend': 0, 'roas': None, 'ctr': None, 'bad': False})


print('\n== C. the prior period dropped the view and the filters ==')
eq('C1a the Keywords view reads amazon_sp_search_term', R['kwSpend'], 79)
eq('C1b the old prev call, with no view, read amazon_ad_spend',
   R['oldPrevSpend'], 2060)
ok(R['kwReadsOtherTable'],
   'C1c so the Keywords delta chips were comparing SEARCH-TERM spend against '
   'UNIFIED-REPORT spend - two different tables under one chip')
eq('C2a a filtered window is narrower',   R['filtSpend'], 2020)
eq('C2b than the unfiltered one',         R['unfiltSpend'], 2060)
ok(R['filtSpend'] != R['unfiltSpend'],
   'C2c so dropping the filters from the prev call made every chip read as a '
   'collapse the moment an ad type was picked')
ok("prev = adsCampaignRollup({ channel, view, from: adsYmd(pFrom), to: adsYmd(pTo), brand, filters: picked });"
   in PREV_BLOCK,
   'C3  the shipped prev call now passes BOTH')
ok('toISOString' not in PREV_BLOCK,
   'C4  and formats its dates locally - toISOString over a LOCAL-midnight date '
   'rolls back a day east of Greenwich')


print('\n== D. a monthly view needs a monthly prior block ==')
eq('D1a a 15-day window inside October resolves to one month',
   R['kwMidMonths'], ['2026-10'])
eq('D1b the NAIVE day-shift lands back inside October - the period would have '
   'contained the period it is compared against',
   R['naivePrevMonths'], ['2026-09', '2026-10'])
eq('D1c the shipped block resolves the whole month before',
   R['kwPrevWindow'], ['2026-09-01', '2026-09-30'])
eq('D1d and reads only September',  R['kwPrevMonths'], ['2026-09'])
eq('D2  a DAILY view still gets the day-shifted block',
   R['dayPrevWindow'], ['2026-09-30', '2026-10-14'])


print('\n== E. the shared trend engine, unchanged for products ==')
SERIES = "\n".join([
    'var localStorage = { getItem: () => null, setItem: () => {} };',
    fnbody('pnlSlotAdd'), fnbody('pnlChartBands'), fnbody('pnlBandColor'),
    fnbody('pnlBandFill'), fnbody('pnlChartMode'), fnbody('pnlTrendSeries'),
    fnbody('pnlTrendSubtitle'),
    'const PNL_CHART_TOPN = 8;',
    'const PNL_CHART_BAND_STEPS = [8, 25, 50, 0];',
    r"""
const perProd = { A: { w1: { v: 10 }, w2: { v: 20 } }, B: { w1: { v: 5 }, w2: { v: 7 } } };
const many = {}; const manyMids = [];
for (let i = 0; i < 12; i++) { const m = 'P' + i; manyMids.push(m); many[m] = { w1: { v: 12 - i } }; }
const C = ['#111','#222','#333','#444','#555','#666','#777','#888','#999','#aaa'];
const o = {};
const base = { perProd, buckets: ['w1','w2'], mids: ['A','B'], metricOf: s => s.v,
               labelOf: m => m, colors: C };
o.defaultTotal = pnlTrendSeries(Object.assign({}, base, { mode:'line', selectionActive:false })).datasets[0].label;
o.nounTotal    = pnlTrendSeries(Object.assign({}, base, { mode:'line', selectionActive:false, noun:'campaign' })).datasets[0].label;
const defOther = pnlTrendSeries({ perProd: many, buckets:['w1'], mids: manyMids, metricOf: s=>s.v,
  labelOf: m=>m, colors: C, mode:'stacked', selectionActive:false });
o.defaultOther = defOther.datasets[defOther.datasets.length-1].label;
const adsOther = pnlTrendSeries({ perProd: many, buckets:['w1'], mids: manyMids, metricOf: s=>s.v,
  labelOf: m=>m, colors: C, mode:'stacked', selectionActive:false,
  noun:'campaign', otherNoun:'campaigns' });
o.adsOther = adsOther.datasets[adsOther.datasets.length-1].label;
const pct = pnlTrendSeries(Object.assign({}, base, { mode:'stacked', selectionActive:false, isPct:true }));
o.pctMode = pct.mode; o.pctNote = pct.note;
const ratio = pnlTrendSeries(Object.assign({}, base, { mode:'stacked', selectionActive:false, noStack:true }));
o.ratioMode = ratio.mode; o.ratioNote = ratio.note;
const stack = pnlTrendSeries(Object.assign({}, base, { mode:'stacked', selectionActive:true }));
o.stackMode = stack.mode;
o.subDefault = pnlTrendSubtitle({ selectionActive:false, midCount:3, bandCount:1, buckets:4,
  from:'a', to:'b', mode:'line', bucketNoun:'week' });
o.subNoun = pnlTrendSubtitle({ selectionActive:true, midCount:3, bandCount:1, buckets:4,
  from:'a', to:'b', mode:'line', bucketNoun:'week', noun:'search term' });
console.log(JSON.stringify(o));
"""])
spath = os.path.join(SP, 'test_v1123_series.js')
io.open(spath, 'w', encoding='utf-8').write(SERIES)
r2 = subprocess.run(['node', spath], capture_output=True, text=True, encoding='utf-8')
if r2.returncode != 0:
    print('SERIES HARNESS FAILED:\n' + (r2.stderr or '')[:2500]); sys.exit(1)
S = json.loads(r2.stdout)

eq('E1a a caller passing no noun still reads "products" - every pre-v11.23 '
   'chart is unchanged', S['defaultTotal'], 'Total \u00b7 2 products')
eq('E1b and its tail band still reads "SKUs"', S['defaultOther'], 'Other \u00b7 4 SKUs')
eq('E2a the ads chart names campaigns', S['nounTotal'], 'Total \u00b7 2 campaigns')
eq('E2b in the tail band too',          S['adsOther'],  'Other \u00b7 4 campaigns')
eq('E3a a PERCENTAGE still falls back to line', S['pctMode'], 'line')
ok('percentages do not sum' in S['pctNote'], 'E3b saying why', S['pctNote'])
eq('E4a a RATIO falls back too - stacking 2.0x on 3.0x to read 5.0x is '
   'meaningless in exactly the way stacking percentages is', S['ratioMode'], 'line')
ok('ratios do not sum' in S['ratioNote'],
   'E4b and says so in its own words, not the percentage one', S['ratioNote'])
eq('E5  a summable metric still stacks', S['stackMode'], 'stacked')
ok(S['subDefault'].startswith('all 3 products'),
   'E6a the subtitle default is unchanged', S['subDefault'])
ok(S['subNoun'].startswith('3 search terms selected'),
   'E6b and takes the view noun', S['subNoun'])


print('\n== F. bucket grain, chosen from the window and stated ==')
eq('F1a a two-week window is drawn per DAY',    R['grain14'],  'day')
eq('F1b a six-month window per WEEK',           R['grain180'], 'week')
eq('F1c a 500-day window per MONTH',            R['grain500'], 'month')
eq('F1d a MONTHLY feed is always per month, whatever the window length',
   R['grainKw'], 'month')
eq('F1e no window falls back to weekly',        R['grainNoWin'], 'week')
ok(R['allSundays'],
   'F2a every week bucket is a SUNDAY - the week definition computePnlDateRange '
   'already uses, because it is Amazon\'s own')
eq('F2b four October weeks', R['weekBuckets'],
   ['2026-09-27', '2026-10-04', '2026-10-11', '2026-10-18'])
ok(R['seriesMatchesTable'],
   'F3  the per-bucket series sums back to each row\'s own total, so the chart '
   'and the table cannot be describing different data')
eq('F4a a daily grain keeps the dates', R['dayBuckets'],
   ['2026-10-01', '2026-10-08', '2026-10-15', '2026-10-22'])
eq('F4b and a monthly FEED ignores a request for days rather than drawing one '
   'spike per month on the day the report closed', R['kwBuckets'], ['2026-10'])


print('\n== G. a partial edge bucket is named, never silently drawn ==')
eq('G1  day grain has no partial edge by construction', R['edgesDay'], [])
eq('G2a the week straddling the window START says how much of it is real - '
   'Sep 27 to Oct 3 contributes only its last three days',
   R['edgesWeek'], ['first week partial \u00b7 3 of 7 days'])
ok(len(R['edgesWeek']) == 1,
   'G2b and the LAST bucket is not called partial: it sits wholly inside '
   'the window. The data ending before the window does is a different fact, reported separately as a data-through note', R['edgesWeek'])
eq('G3  a window aligned to its buckets reports nothing', R['edgesAligned'], [])


print('\n== H. the chart metric list is the TABLE\'s column registry ==')
eq('H1a Amazon offers every numeric column and no text one', R['mAmz'],
   ['impressions', 'clicks', 'ctr', 'cpc', 'spend', 'orders', 'cpa', 'sales', 'roas', 'acos'])
ok('units' in R['mChw'] and 'ntb' in R['mChw'],
   'H1b Chewy picks up its own measures from its own registry', R['mChw'])
ok('cvr' in R['mKw'],
   'H1c and Keywords picks up CVR, which only that view has', R['mKw'])
ok('campaign' not in R['mAmz'] and 'skus' not in R['mAmz'],
   'H1d while text and count-of-distinct columns are left out', R['mAmz'])
eq('H2a ROAS is a MULTIPLE and cannot be stacked', R['roasSpec'],
   {'unit': 'x', 'noStack': True, 'isPct': False})
eq('H2b ACOS is a percentage and cannot be stacked either', R['acosSpec'],
   {'unit': '%', 'noStack': True, 'isPct': True})
eq('H3a every metric derives from a SUMMED slot', R['roasOfSum'], 4)
eq('H3b and returns null on a zero denominator, never Infinity',
   R['roasOfZero'], None)
eq('H3c percentages are scaled once, at the metric', R['ctrOfSum'], 2.5)


print('\n== I. the exporter wrote NaN into the Keywords CSV ==')
eq('I1a the OLD val() ran Math.round over a search term', R['oldValTerm'], 'NaN')
eq('I1b and over a match type',                           R['oldValMatch'], 'NaN')
eq('I2a text is detected by VALUE now',  R['newValTerm'], 'catnip spray')
eq('I2b the single-month row reads its ONE match type', R['newValMatch'], 'EXACT')
eq('I2c and that month\'s own spend',      R['newValSpend'], '70.00')
eq('I2d over TWO months the same term merges, and the JOINED match list '
   'survives the exporter intact', R['wideValMatch'], 'BROAD \u00b7 EXACT')
eq('I2e which the old rule turned into NaN as well', R['wideOldMatch'], 'NaN')
eq('I2f while the numbers are untouched either way', R['wideValSpend'], '100.00')
ok("if (k === 'campaign' || k === 'type' || k === 'status') return c[k] || '';" not in js,
   'I3  the old rule is gone from the file, not merely bypassed')

ok(not R['oldHayFindsTerm'],
   'I4a the OLD search haystack could not find a search term - it was campaign '
   '+ type + status, and on Keywords that is the campaign LIST and two blanks')
ok(R['newHayFindsTerm'], 'I4b the new one searches every text column the view renders')


print('\n== J. the wiring ==')
for f in ('adsDeriveRow', 'adsSumRows', 'adsYmd', 'adsBucketFn', 'adsGrain',
          'adsChartMetrics', 'adsBucketEdges', 'adsUpdateChart',
          'adsToggleRow', 'adsToggleAllVisible', 'adsClearSelection', 'adsSelName'):
    ok(len(re.findall(r'(?:async\s+)?function\s+%s\s*\(' % f, js)) == 1,
       'J1  exactly one %s' % f)

eq('J2a the renderer hands the chart ONE context, once',
   RENDER.count('adsUpdateChart('), 1)
ok('adsUpdateChart({ ch, channel, view, COLS, res, win, list, sel, grain, totals: t })' in RENDER,
   'J2b built from the same res / win / list the table just rendered, so the '
   'two cannot describe different slices')

ok('_adsRendered[_adsKey(channel, view)] = list;' in RENDER,
   'J3a the rendered rows are recorded for the checkboxes')
ok(RENDER.index('_adsRendered[_adsKey(channel, view)] = list;')
   < RENDER.index('const sel = st.sel;'),
   'J3b BEFORE the selection resolves, so a checkbox index always addresses '
   'the list it was drawn from')
ok("adsToggleRow('${channel}',${i},'${view || ''}')" in RENDER,
   'J4  a checkbox addresses its row by INDEX. A campaign name can contain '
   'quotes and backslashes; interpolating one into an onclick breaks on the '
   'first apostrophe and is an injection besides')

ok('const cardT = selRows ? adsSumRows(selRows, NAMECOL) : t;' in RENDER,
   'J5a the cards read the selection when there is one')
ok('adsSumRows(prev.campaigns.filter(c => sel.has(c[NAMECOL])), NAMECOL)' in RENDER,
   'J5b and the PRIOR period is narrowed to the same rows, or the chip compares '
   'three campaigns now against a hundred and forty then')
_cov = RENDER[RENDER.index("const cov = document.getElementById(ch.host + '-cov');"):]
ok('cardT' not in _cov,
   'J5c while the coverage line still describes the WINDOW - selection moves '
   'the cards and the chart, never the period')
ok("$0(t.spend) + ' spend'" in _cov,
   'J5d reading the window total by name')

ok('const shown = adsSumRows(list, NAMECOL);' in RENDER,
   'J6a the footer goes through the same summer')
ok('shown.ctr  = adsDiv(' not in RENDER,
   'J6b and no hand-written re-derivation survives beside it')

ok('colspan="${COLS.length + 1}"' in RENDER,
   'J7a the empty state spans the checkbox column')
eq('J7b and so do both tbody placeholders',
   js.count('(ch.columns || ADS_COLUMNS[channel]).length + 1}"'), 2)
ok('id="${ch.host}-selall"' in js, 'J7c there is a select-all box')
ok('selAllEl.indeterminate = onCount > 0 && onCount < list.length;' in RENDER,
   'J7d which goes indeterminate on a partial selection, like the Summary table\'s')

ok("window['_adsRe_' + ch.host] = () => renderAdsCampaigns(channel, view);" in js,
   'J8a the shared Line/Stacked toggle can re-render an ads view')
ok("pnlInjectChartModeToggle(ch.host + '-chart-mode-host', '_adsRe_' + ch.host, !!m.noStack)" in js,
   'J8b and is told whether THIS metric can be stacked')

ok("lines.push('# ' + ch.label + ' \u00b7 ' + (ch.noun || 'campaign') + ' level');" in js,
   'J9a the CSV names the level it is at')
ok('if (snap.sel && snap.sel.length) {' in js,
   'J9b and states an active selection rather than silently exporting a '
   'different population than the cards above it')

print('\n' + '-' * 60)
print('v11.23: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
