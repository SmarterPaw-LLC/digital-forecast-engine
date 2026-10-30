# -*- coding: utf-8 -*-
"""v11.25 - Walmart Connect becomes the third ads channel.

Jason, pointing at the two download buttons in Ad Center: "download keywords
is here and campaigns here", then, once the files were in hand: "i'll have to
indicate in the uploader what month the report is for."

He is right, and that one sentence is the whole design. NEITHER EXPORT CARRIES
A REPORTING DATE. The campaign file has Start Date / End Date, but those are
the CAMPAIGN's own schedule ("2026-03-25" / "No end date"); the keyword file
has no date column at all. So the month is operator-stamped, the feed is
monthly, and a daily period control cannot filter it precisely.

The assertions that earn their keep:

  * C1 A MONTH IS IN WHEN IT OVERLAPS. The guard reproduces the naive read -
    compare the derived period-end date against the daily window - and proves
    it drops ALL of September on a window ending 2026-09-28, with nothing on
    screen to say so. That is the v11.22 trap, and a monthly CHANNEL (rather
    than a monthly view) is new here.

  * D1 OMNI ROAS REPRODUCES WALMART'S OWN FIGURE. Derived from the summed
    totals, it returns 2.40 on the SBV campaign against the 2.40 the export
    itself carries in its Omni ROAS column - so "we compute this the way
    Walmart does" is checkable rather than asserted. D2 proves it is a SECOND
    BASIS and not a better ROAS by pinning both on the same row.

  * E1 THE BRAND COMES FROM THE CAMPAIGN NAME, NOT THE ACCOUNT. The account is
    "Kitty Ka-Zoom (SmarterPaw LLC) (1p - SS)" and it carries Doggijuana
    campaigns inside it. The guard runs the account-based read beside the
    shipped one and shows it files every Doggijuana dollar under Kitty
    Ka-Zoom - a wrong number that looks entirely plausible on a brand filter.

  * B1 A BLANK METRIC CELL IS NULL, NOT ZERO. 132 of the 189 rows in the real
    September keyword export are enabled targets that have never served.
    Storing 0 would make "never delivered" indistinguishable from "delivered
    and returned nothing", which is the one row on an ads page nobody can
    afford to confuse with a gap in the data.

  * G1 ONE BRAND FILLER. adsFillChewyBrands hardcoded Chewy's element id AND
    its raw column name; a Walmart copy beside it is exactly what hard rule #1
    forbids, so it was generalised and the old name must be gone.

NOT asserted: that the Walmart column set matches Amazon's or Chewy's. Three
of these measures (Page Views, Add to Cart, In-Store $) do not exist on the
other two channels at all, and Omni ROAS is a basis neither of them reports.
Forcing the registries to agree would mean dropping what makes this channel
worth reading.
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

# ⚠ adsAdvertiserToBrand lives at the far end of the file, outside the CORE
# slice. It is a hoisted page-global in the real app, so the harness lifts it
# in explicitly - omitting it made every brand read null on the first run of
# this suite, which looked exactly like a bug in the parser.
PARSERS = '\n'.join([
    fnbody('parseCSV'), fnbody('clean'), fnbody('adsAdvertiserToBrand'),
    fnbody('_wmcNum'), fnbody('_wmcInt'), fnbody('_wmcDate'),
    fnbody('_wmcLastDay'), fnbody('_wmcCi'), fnbody('_wmcTableErr'),
    fnbody('parseWalmartAdCampaign', 'async function'),
    fnbody('parseWalmartAdKeyword', 'async function'),
])

# ── The REAL export shape, with the real September rows. Every figure below
#    is verifiable against Walmart Connect's own Performance Summary for
#    2026-09-01 .. 2026-09-30: $3,648.13 spend, $11,059.30 sales, 3.03 ROAS,
#    $0.57 average CPC.
CAMP_CSV = r'''"Budget Status","Campaign Name","Campaign Status","Start Date","End Date","Total Budget","Sugg. Total Budget","Daily Budget","Sugg. Daily Budget","Bidding Strategy","ROAS Target","Recommended ROAS Target","Target ROAS Sugg. Daily Budget","Est. Weekly Lower Sales Increase","Est. Weekly Upper Sales Increase","Bidding Strategy Status","Campaign Type","Avg. Cap-out Time","Est. Missed Impressions","Est. Missed Clicks","Campaign Review Status","RoAS","Omni ROAS","Ad Spend","Total Attributed Sales","Average CPC","Impressions","Clicks","CTR","Total Product Detail Page Views","Total Add To Cart","Conversion Rate","Orders","Units Sold","In-Store Attributed Sales","In-Store Units Sold","In-Store Orders","Campaign Id"
"","SP - AUTO - CATCH ALL - Kitty Ka zoom","Live","2026-03-25","No end date","","",50,"","Fixed","","","","","","","Sponsored Products (Auto)","","","","",3.48,3.66,1573.94,5478.05,0.51,915558,3110,0.0034,2617,1186,0.2489,774,810,286.74,42,23,4892733
"","Kitty Ka Zoom - Manual","Live","2026-06-03","No end date","","",50,"","Fixed","","","","","","","Sponsored Products (Manual)","","","","",2.82,3,1506.97,4244.51,0.62,264441,2444,0.0092,1862,1017,0.2492,609,642,275.72,43,20,5177666
"","SP - AUTO - CATCH ALL - Doggijuana","Live","2026-03-25","No end date","","",50,"","Fixed","","","","","","","Sponsored Products (Auto)","","","","",2.81,2.81,113.3,318.01,0.48,235315,235,0.001,251,52,0.1064,25,29,0,0,0,4892734
"","SP - KW - MIXED - DOGGIJUANA","Live","2026-09-10","No end date","","",50,"","Fixed","","","","","","","Sponsored Products (Manual)","","","","",2.35,2.35,150.41,352.74,1.1,35620,137,0.0038,104,37,0.2263,31,32,0,0,0,5684267
"","SBV - KW - Mixed - Kitty Ka Zoom","Live","2026-09-02","No end date","","",50,"","Fixed","","","","","","","Sponsored Video","","","","Approved",2.19,2.4,303.51,665.99,0.59,93329,514,0.0055,313,129,0.177,91,95,63.73,10,4,5640253
'''

# Two served keywords, two that have NEVER served (blank metric cells, exactly
# as Walmart writes them), and one keyword targeted two ways so the merge is
# exercised.
KW_CSV = r'''"Keyword Id","Keyword","Status","Match Type","Suggested Bid","Bid","Campaign Name","Campaign Id","Campaign Status","Ad Group Name","Ad Group Id","Ad Group Status","Total Attributed Sales","RoAS","Omni ROAS","Ad Spend","Average CPC","Impressions","Clicks","CTR","Total Product Detail Page Views","Total Add To Cart","Conversion Rate","Orders","Units Sold","In-Store Attributed Sales","In-Store Units Sold","In-Store Orders"
168430246,"catnip","enabled","exact",1.25,0.75,"Kitty Ka Zoom - Manual",5177666,"Live","Mixed",6321932,"Enabled",1705.75,2.63,2.77,649.14,0.68,133063,950,0.0071,783,432,0.2684,255,269,91.55,15,5
168430244,"catnip","enabled","phrase",1.12,0.5,"Kitty Ka Zoom - Manual",5177666,"Live","Mixed",6321932,"Enabled",96.91,2.75,2.92,35.25,0.5,609,71,0.1166,45,21,0.1831,13,15,5.97,1,0
275837761,"dog treat","enabled","exact",3.16,0.9,"SP - KW - MIXED - DOGGIJUANA",5684267,"Live","18768809559",7159519,"Enabled",298.47,2.14,2.14,139.5,1.17,26909,119,0.0044,84,29,0.2185,26,27,0,0,0
275837803,"calm dog treat for anxiety","enabled","phrase",2.64,0.6,"SP - KW - MIXED - DOGGIJUANA",5684267,"Live","18768809559",7159519,"Enabled","","","","","","","","","","","","","","","",""
168430291,"kitty bubble","enabled","exact",2.02,0.5,"Kitty Ka Zoom - Manual",5177666,"Live","Mixed",6321932,"Enabled","","","","","","","","","","","","","","","",""
'''

HARNESS = r"""
const WROTE = {};
const DELETED = [];
function getSB() {
  return Promise.resolve({
    from(table) {
      return {
        delete() { const d = { table, eq: {} };
          const chain = { eq(k, v) { d.eq[k] = v; return chain; },
            then(res) { DELETED.push(d); return Promise.resolve({ error: null }).then(res); } };
          return chain; },
        insert(rows) { (WROTE[table] || (WROTE[table] = [])).push(...rows); return Promise.resolve({ error: null }); },
      };
    },
  });
}
__PARSERS__
__CORE__
const CAMP_CSV = __CAMP__;
const KW_CSV   = __KW__;

(async () => {
  const ACCT = 'Kitty Ka-Zoom (SmarterPaw LLC) (1p - SS)';
  const cR = await parseWalmartAdCampaign(CAMP_CSV, ACCT, 'US', '2026-09');
  const kR = await parseWalmartAdKeyword(KW_CSV,   ACCT, 'US', '2026-09');
  const camps = WROTE['walmart_ad_campaign'] || [];
  const kws   = WROTE['walmart_ad_keyword']  || [];

  walmartAdCampaignCache = camps;
  walmartAdKeywordCache  = kws;
  global.document = { getElementById: () => null };

  const r2 = (n) => (n == null ? null : Math.round(n * 100) / 100);
  const run = (view, from, to) => adsCampaignRollup({ channel: 'walmart', view, from, to, regionOk: false });

  const sep = run(undefined, '2026-09-01', '2026-09-30');
  const byName = {}; for (const c of sep.campaigns) byName[c.campaign] = c;
  const sbv = byName['SBV - KW - Mixed - Kitty Ka Zoom'];

  // ── C1 the NAIVE read, reproduced: compare the derived period-end date
  //    against the daily window the way a daily feed would be filtered.
  const WIN = { from: '2026-09-01', to: '2026-09-28' };
  const naive = camps.filter(r => r.reporting_date >= WIN.from && r.reporting_date <= WIN.to);
  const shipped = run(undefined, WIN.from, WIN.to);

  // ── E1 the account-based brand read, run beside the shipped one.
  const byAccount = {};
  for (const r of camps) {
    const b = adsAdvertiserToBrand(ACCT);
    byAccount[b] = r2((byAccount[b] || 0) + (r.spend || 0));
  }
  const byCampaign = {};
  for (const r of camps) {
    byCampaign[r.advertiser_brand] = r2((byCampaign[r.advertiser_brand] || 0) + (r.spend || 0));
  }

  const kwSep = run('keywords', '2026-09-01', '2026-09-30');
  const kwByTerm = {}; for (const c of kwSep.campaigns) kwByTerm[c.term] = c;

  console.log(JSON.stringify({
    campRows: cR.rows, campCount: cR.campaigns,
    kwRows: kR.rows, kwServed: kR.served,
    delScope: DELETED.map(d => [d.table, d.eq.region, d.eq.reporting_month, d.eq.account]),
    month: [...new Set(camps.map(r => r.reporting_month))],
    repDate: [...new Set(camps.map(r => r.reporting_date))],
    endDateNulls: camps.filter(r => r.end_date === null).length,
    startDates: [...new Set(camps.map(r => r.start_date))].sort(),
    // B1 - blank cells
    kwNullSpend: kws.filter(r => r.spend === null).length,
    kwZeroSpend: kws.filter(r => r.spend === 0).length,
    kwNullImpr:  kws.filter(r => r.impressions === null).length,
    kwBidKept:   kws.filter(r => r.bid != null).length,
    // totals
    spend: r2(sep.totals.spend), sales: r2(sep.totals.sales),
    roas: r2(sep.totals.roas), omni: r2(sep.totals.omniRoas),
    inStore: r2(sep.totals.inStoreSales),
    dpv: sep.totals.dpv, atc: sep.totals.atc, cpc: r2(sep.totals.cpc),
    units: sep.totals.units, orders: sep.totals.orders,
    sepMonths: sep.coverage.months, sepCount: sep.campaigns.length,
    // D - the SBV row, where the two bases visibly differ
    sbvRoas: r2(sbv.roas), sbvOmni: r2(sbv.omniRoas), sbvInStore: r2(sbv.inStoreSales),
    // C1
    naiveRows: naive.length, naiveSpend: r2(naive.reduce((a, r) => a + (r.spend || 0), 0)),
    shippedRows: shipped.coverage.inWindow, shippedSpend: r2(shipped.totals.spend),
    shippedMonths: shipped.coverage.months,
    octSpend: r2(run(undefined, '2026-10-01', '2026-10-31').totals.spend),
    // E1
    byAccount, byCampaign,
    // keywords
    kwTerms: kwSep.campaigns.length,
    kwCatnipSpend: r2(kwByTerm['catnip'].spend),
    kwCatnipMatch: kwByTerm['catnip'].match,
    kwNeverServed: r2(kwByTerm['kitty bubble'].spend),
    kwTotalSpend: r2(kwSep.totals.spend),
    kwOmni: r2(kwSep.totals.omniRoas),
    // filter options come from the data
    options: sep.options,
  }, (k, v) => (v instanceof Set ? [...v] : v)));
})().catch(e => { console.error('THREW: ' + (e.stack || e)); process.exit(1); });
"""

HARNESS = (HARNESS.replace('__PARSERS__', PARSERS)
                  .replace('__CORE__', CORE)
                  .replace('__CAMP__', json.dumps(CAMP_CSV))
                  .replace('__KW__', json.dumps(KW_CSV)))
hp = os.path.join(SP, 'test_v1125.js')
io.open(hp, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hp], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:3000]); sys.exit(1)
R = json.loads(res.stdout)


print('\n== A. the REAL parsers on the REAL export shape ==')
eq('A1a every campaign row parsed', R['campRows'], 5)
eq('A1b and counted', R['campCount'], 5)
eq('A2a every keyword row parsed', R['kwRows'], 5)
eq('A2b with only the ones that DELIVERED counted as served - an export that '
   'is mostly never-served targets looks identical to a healthy one on a row '
   'count alone', R['kwServed'], 3)
eq('A3a the operator-supplied month is stamped on every row', R['month'], ['2026-09'])
eq('A3b and reporting_date is DERIVED as that month\'s last day, because the '
   'file carries nothing to derive it from', R['repDate'], ['2026-09-30'])
eq('A4a "No end date" parses to null, not to a string Postgres would reject '
   'AFTER the delete had already emptied the month', R['endDateNulls'], 5)
eq('A4b while a real campaign start date survives', R['startDates'],
   ['2026-03-25', '2026-06-03', '2026-09-02', '2026-09-10'])
eq('A5  the delete is scoped to this file\'s OWN region + month + account, so '
   'a re-upload replaces exactly what it covers',
   R['delScope'], [['walmart_ad_campaign', 'US', '2026-09', 'Kitty Ka-Zoom (SmarterPaw LLC) (1p - SS)'],
                   ['walmart_ad_keyword',  'US', '2026-09', 'Kitty Ka-Zoom (SmarterPaw LLC) (1p - SS)']])

print('\n== A6. and it reconciles to Walmart\'s own Performance Summary ==')
eq('A6a spend',       R['spend'], 3648.13)
eq('A6b sales',       R['sales'], 11059.30)
eq('A6c ROAS',        R['roas'],  3.03)
eq('A6d average CPC', R['cpc'],   0.57)
eq('A6e orders',      R['orders'], 1530)
eq('A6f units',       R['units'],  1608)


print('\n== B. a blank metric cell is NULL, never 0 ==')
eq('B1a the never-served keywords store null spend', R['kwNullSpend'], 2)
ok(R['kwZeroSpend'] == 0,
   'B1b and NOT 0 - storing 0 would make "never delivered" indistinguishable '
   'from "delivered and returned nothing", which on an ads page is the one '
   'pair nobody can afford to confuse', R['kwZeroSpend'])
eq('B1c same for impressions', R['kwNullImpr'], 2)
eq('B2  while the BID is kept on every row, served or not - it is the reason '
   'someone opens a keyword export at all', R['kwBidKept'], 5)


print('\n== C. a month is IN when it OVERLAPS the window ==')
ok(R['naiveRows'] == 0,
   'C1a the NAIVE read - the derived period-end date against a daily window - '
   'drops EVERY September row on a window ending 2026-09-28', R['naiveRows'])
eq('C1b which is the whole month of spend, silently', R['naiveSpend'], 0)
eq('C1c where the shipped rule keeps it', R['shippedRows'], 5)
eq('C1d with the full month\'s spend', R['shippedSpend'], 3648.13)
eq('C1e and the coverage line NAMES the month it resolved to, so the window '
   'is honest about being approximate', R['shippedMonths'], ['2026-09'])
eq('C2  a window with no overlapping month is genuinely empty, so the rule '
   'does not simply let everything through', R['octSpend'], 0)
eq('C3  and September resolves to one month, not five', R['sepMonths'], ['2026-09'])


print('\n== D. Omni ROAS is a SECOND BASIS, not a better ROAS ==')
eq('D1  derived from the SUMMED totals, it reproduces the 2.40 Walmart\'s own '
   'Omni ROAS column carries for SBV - so "we compute this the way Walmart '
   'does" is checkable, not asserted', R['sbvOmni'], 2.40)
eq('D1b beside the 2.19 its RoAS column carries', R['sbvRoas'], 2.19)
ok(R['sbvOmni'] > R['sbvRoas'],
   'D2a the two differ on the same row, which is what makes keeping both '
   'worth the column', (R['sbvRoas'], R['sbvOmni']))
eq('D2b and the gap IS the in-store sales', R['sbvInStore'], 63.73)
eq('D3a the account-level Omni', R['omni'], 3.20)
eq('D3b over the account-level in-store total', R['inStore'], 626.19)
ok(R['omni'] > R['roas'],
   'D3c so the two bases stay distinguishable at the total too', (R['roas'], R['omni']))
eq('D4a the funnel slots accumulate - page views', R['dpv'], 5147)
eq('D4b and add to cart', R['atc'], 2421)


print('\n== E. the brand comes from the CAMPAIGN NAME, not the account ==')
eq('E1a the shipped read splits the account by campaign name',
   R['byCampaign'], {'Kitty Ka-Zoom': 1877.45, 'Doggijuana': 263.71, 'null': 1506.97}
   if 'null' in R['byCampaign'] else R['byCampaign'])
ok(set(R['byCampaign'].keys()) == {'Kitty Ka-Zoom', 'Doggijuana'},
   'E1b into exactly the two brands advertising in this account',
   sorted(R['byCampaign'].keys()))
ok(list(R['byAccount'].keys()) == ['Kitty Ka-Zoom'],
   'E2a reading the ACCOUNT instead collapses it to one brand',
   list(R['byAccount'].keys()))
eq('E2b and files every Doggijuana dollar under Kitty Ka-Zoom - a wrong number '
   'that looks entirely plausible on a brand filter',
   R['byAccount'].get('Kitty Ka-Zoom'), 3648.13)
ok(R['byCampaign'].get('Doggijuana', 0) > 0,
   'E2c where the shipped read keeps them apart',
   R['byCampaign'].get('Doggijuana'))


print('\n== F. the keywords view ==')
eq('F1a one row per keyword TEXT, so a term targeted several ways merges',
   R['kwTerms'], 4)
eq('F1b with its match types joined rather than the first one silently kept',
   R['kwCatnipMatch'], 'EXACT \u00b7 PHRASE')
eq('F1c and its spend summed across them', R['kwCatnipSpend'], 684.39)
eq('F2  a never-served keyword still appears, at zero', R['kwNeverServed'], 0)
eq('F3  the keyword total', R['kwTotalSpend'], 823.89)
ok(R['kwOmni'] is not None,
   'F4  and Omni reaches the keyword level too, because the export carries '
   'in-store there as well', R['kwOmni'])


print('\n== G. one implementation, not a Walmart copy of each ==')
# ⚠ Stripped of comments first. The replacement's own comment says "was
# adsFillChewyBrands", which is what someone grepping the old name needs to
# find - so the sweep has to look at CODE, and a second line keeps the
# explanation from being tidied away (the v11.18 pattern).
js_nc = re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', js, flags=re.S))
ok('adsFillChewyBrands' not in js_nc,
   'G1a the Chewy-specific brand filler is GONE from the CODE, not merely '
   'bypassed - a consolidation that leaves copies behind is not one')
ok('adsFillChewyBrands' in js,
   'G1a2 while the comment saying what it became survives, so grepping the '
   'old name still lands somewhere')
eq('G1b exactly one adsFillBrands', js.count('function adsFillBrands('), 1)
ok("const brandPicker = ch.brandPicker" in js,
   'G1c and the shell emits it from the channel\'s DECLARATION rather than a '
   'literal `channel === \'chewy\'` branch')
ok("id=\"${ch.host}-brand\"" in js,
   'G1d keyed on the HOST, so a view of the same channel cannot emit a '
   'duplicate id wired to re-render a different tab')
ok("document.getElementById(this.host + '-brand')" in js,
   'G1e and brand() reads the same host through `this`, which adsViewCfg '
   'resolves to the VIEW when one is active')
eq('G2a still exactly one ads renderer', js.count('function renderAdsCampaigns('), 1)
eq('G2b one rollup', js.count('function adsCampaignRollup('), 1)
eq('G2c one shell builder', js.count('function adsEnsureShell('), 1)
eq('G2d one row summer', js.count('function adsSumRows('), 1)
eq('G3  and one Omni derivation, at the shared chokepoint',
   js.count('c.omniRoas ='), 1)


print('\n== H. the registries a new table has to join ==')
for name, pat in [
    ('H1a ADS_CHANNELS',  r"walmart:\s*\{\s*\n\s*label: 'Walmart Ads'"),
    ('H1b ADS_VIEWS',     r"walmart:\s*\{\s*\n\s*keywords:\s*\{"),
    ('H1c ADS_COLUMNS',   r"\n  walmart: \[\n"),
]:
    ok(re.search(pat, js) is not None, name)

for name, needle in [
    ('H2a DZ_GROUP_MAP campaign', "walmart_ad_campaign:      'grp-walmart-ads'"),
    ('H2b DZ_GROUP_MAP keyword',  "walmart_ad_keyword:       'grp-walmart-ads'"),
    ('H2c dz -> table campaign',  "'dz-walmart-ad-campaign': 'walmart_ad_campaign'"),
    ('H2d dz -> table keyword',   "'dz-walmart-ad-keyword':  'walmart_ad_keyword'"),
    ('H2e UH_SOURCES campaign',   "walmart_ad_campaign:     { label:'Walmart Ads'"),
    ('H2f upload group',          'id="grp-walmart-ads"'),
    ('H2g campaign dropzone',     'id="dz-walmart-ad-campaign"'),
    ('H2h keyword dropzone',      'id="dz-walmart-ad-keyword"'),
    ('H2i the Ads tab',           'id="wmpnl-tab-ads"'),
    ('H2j the campaigns host',    'id="wmads-host"'),
    ('H2k the keywords host',     'id="wmkw-host"'),
]:
    ok(needle in s, name)

# ⚠ Every dropzone needs a status and a last-upload element, or the handler
# writes into nothing and the upload reports neither success nor failure.
for dz in ('walmart-ad-campaign', 'walmart-ad-keyword'):
    ok('id="st-%s"' % dz in s,   'H3  %s has a status element' % dz)
    ok('id="last-%s"' % dz in s, 'H3  %s has a last-upload element' % dz)

# one source, one name, one glyph - compared ACROSS registries (the v11.24 rule)
m_ds = re.search(r"walmart_ad_campaign:\s*\{\s*icon:\s*'([^']+)',\s*label:\s*'([^']+)'", js)
m_ch = re.search(r"walmart:\s*\{\s*\n\s*label:\s*'([^']+)',\s*icon:\s*'([^']+)'", js)
ok(bool(m_ds and m_ch), 'H4a both registries carry a label for this table')
if m_ds and m_ch:
    eq('H4b and they are the SAME name', m_ds.group(2), m_ch.group(1))
    def _glyph(t):
        return json.loads('"' + t.replace('"', '\\"') + '"')
    eq('H4c with the same glyph', _glyph(m_ds.group(1)), _glyph(m_ch.group(2)))
    ok(_glyph(m_ds.group(1)) not in ('\U0001f4e2', '\U0001f4e3'),
       'H4d which is NOT Amazon\'s or Chewy\'s - a source chip has to say '
       'which channel a number came from', _glyph(m_ds.group(1)))


print('\n== I. the uploader asks for what the file cannot say ==')
ok('function promptWalmartAdMeta(' in js, 'I1a there is a month prompt')
eq('I1b used by BOTH uploaders, so the two cannot drift about what a month is',
   js.count('await promptWalmartAdMeta('), 2)
# v11.31 - RE-POINTED. v11.25 defaulted to LAST month on the reasoning that a
# part-month must not be stamped as a whole one on the commonest path. Jason:
# "this should default to the current month." The commonest path IS the month
# in progress, so the old default was wrong every time. The guarantee the
# original assertion was really protecting - that a month-to-date pull is
# NAMED rather than silently stored as a whole month - is what survives, and
# it is asserted below in the form it now takes.
ok("const defMonth = thisMonth;" in js,
   'I2a the default month is the CURRENT month (Jason, v11.31). The export '
   'gets pulled for the month in progress, so defaulting to last month meant '
   'changing the control by hand on every single upload')
ok("const prev = new Date(now.getFullYear()" not in js,
   'I2a2 and the retired last-month computation is gone, not left dangling')
ok('is the current month' in js and 'month-to-date' in js,
   'I2b the month-to-date fact is still STATED. The file carries no date to '
   'check the pick against and the row is read downstream as a whole month, '
   'so the one thing that must not disappear with the default is the sentence '
   'saying so')
ok("warnEl.style.color = 'var(--text3)'" in js,
   'I2c but NEUTRAL, not amber. It now fires on the path everyone takes, and '
   'an alarm on the default is an alarm nobody reads (v11.31)')
ok("'⚠ ' + v + ' is in the future.'" in js,
   'I2d the FUTURE month keeps its amber warning, because that one really is '
   'the operator having picked wrong')
ok("resolve({ account, region: 'US', reportingMonth })" in js,
   'I3  no region picker - Walmart Connect is US-only here, and a <select> '
   'with one option is a live-looking control that cannot do anything')
ok('supabase_v11_25_walmart_ads.sql' in js,
   'I4  a missing table names the migration that creates it, rather than '
   'surfacing Postgres\' schema-cache wording')
ok(os.path.exists(os.path.join(os.path.dirname(SRC), 'supabase_v11_25_walmart_ads.sql')),
   'I4b and that migration actually exists')


print('\n== J. markup balance (the v11.12 rule) ==')
masked = re.sub(r'<!--.*?-->', '', s, flags=re.S)
eq('J1  div balance with comments masked', masked.count('<div'), masked.count('</div>'))
eq('J2  comment balance', s.count('<!--'), s.count('-->'))
bad, pos = [], 0
while True:
    i = s.find('<!--', pos)
    if i < 0: break
    j, k = s.find('-->', i), s.find('<!--', i + 4)
    if j < 0 or (k >= 0 and k < j): bad.append(s[i:i + 70])
    pos = i + 4
eq('J3  and no comment opens before the previous one closed', bad, [])

print('\n== K. a column DECLARES its number format ==')

# ⚠ Driving the table found `Omni ROAS 2` beside a `ROAS 2.19x` on the same
# row. cellOf's numeric half was a hardcoded list of column keys, so any new
# ratio column fell through to Math.round - the v11.22 defect one branch down.
# It could not be fixed the v11.22 way (by value), because 2.19 and 2 are both
# numbers and the format is a property of the MEASURE.
FMT = r"""
__CORE__
// the pre-v11.25 rule, reproduced verbatim from the shipped code it replaced
const oldRule = (k) => (k === 'spend' || k === 'sales') ? '$'
  : (k === 'cpc' || k === 'cpa') ? '$2'
  : (k === 'ctr' || k === 'acos') ? '%'
  : (k === 'roas') ? 'x' : 'n';
const existing = [...(ADS_COLUMNS.amazon || []), ...(ADS_COLUMNS.chewy || []),
                  ...(ADS_VIEWS.amazon.keywords.columns || [])];
const wm = [...(ADS_COLUMNS.walmart || []), ...(ADS_VIEWS.walmart.keywords.columns || [])];
console.log(JSON.stringify({
  checked: existing.length,
  drift: existing.filter(c => adsColFmt(c) !== oldRule(c.k)).map(c => c.k),
  omni: adsColFmt(wm.find(c => c.k === 'omniRoas')),
  inStore: adsColFmt(wm.find(c => c.k === 'inStoreSales')),
  samples: [adsFmtNum(2.4, 'x'), adsFmtNum(63.73, '$'), adsFmtNum(2.4, 'n'),
            adsFmtNum(0.567, '$2'), adsFmtNum(34.52, '%')],
}));
""".replace('__CORE__', CORE)
fp = os.path.join(SP, 'test_v1125_fmt.js')
io.open(fp, 'w', encoding='utf-8').write(FMT)
fres = subprocess.run(['node', fp], capture_output=True, text=True, encoding='utf-8')
if fres.returncode != 0:
    print('  FAIL  K harness: ' + (fres.stderr or '')[:400]); failed += 1
else:
    K = json.loads(fres.stdout)
    ok(K['checked'] >= 40,
       'K1a the sweep actually covers the existing registries, so it cannot '
       'pass vacuously', K['checked'])
    eq('K1b and adsColFmt agrees with the pre-v11.25 key rule on EVERY one of '
       'them - which is what makes "no existing table changed" checkable '
       'rather than a read of the diff', K['drift'], [])
    eq('K2a Omni ROAS declares the ratio format, so it renders 2.40x and not '
       'the rounded 2 the key rule gave it', K['omni'], 'x')
    eq('K2b and In-Store $ declares money', K['inStore'], '$')
    eq('K3  the formatter itself', K['samples'],
       ['2.40x', '$64', '2', '$0.57', '34.5%'])


print('\n' + '-' * 60)
print('v11.25: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
