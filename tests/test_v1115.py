# -*- coding: utf-8 -*-
"""v11.15 - amazon_ad_spend learns the campaign, so the Ads view has a grain.

Jason: "do you want me to reupload it after i add the campaign name? it pulls
everything for quarter to date"

The Ads sub-tab on each P&L is campaign-level. The weekly unified report is
daily, covers every ad product, and is already on a cadence - so adding
`Campaign name` as a dimension there gives campaign grain across all ad types
with no new upload. The parser had to learn the column, and the GRAIN had to
move with it.

The assertions that earn their keep:

  * A3 THE REGRESSION GUARD. It reproduces the pre-v11.15 key against two
    campaigns advertising the SAME ASIN on the SAME day and proves it really
    did collapse them into ONE row - which would have stamped the pair's whole
    spend with whichever campaign the file happened to list first. Carrying
    `campaign` on the row without putting it in the key looks identical in a
    diff and is wrong in exactly this way.

  * A4 SUMS ARE PRESERVED. Every consumer of amazonAdSpendData accumulates
    (+=) or set-adds, so a finer grain must leave every existing total
    byte-identical. Asserted against the same file parsed both ways.

  * A5 AN EXPORT WITH NO CAMPAIGN COLUMN IS UNCHANGED. Older uploads still
    parse to the same rows at the same grain, or this release breaks the
    weekly cadence it is meant to extend.

  * C2 THE SCHEMA PROBE RUNS BEFORE THE DELETE. The handler DELETEs the window
    and then INSERTs. On a pre-migration table the insert is what fails, so
    without an earlier probe an upload would empty the exact quarter it was
    replacing and put nothing back. Ordering is the whole guarantee.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SQL = r'C:\Users\Jason\digital-forecast-engine\supabase_v11_15_amazon_ad_spend_campaign.sql'
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

def fn(name, kw='function'):
    i = js.index('%s %s(' % (kw, name))
    k = js.index('(', i); d = 0
    while True:
        if js[k] == '(': d += 1
        elif js[k] == ')':
            d -= 1
            if d == 0: break
        k += 1
    j = js.index('{', k); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1


print('\n== A. the real parser, driven on a campaign-carrying export ==')

# Two campaigns on the SAME date / region / ad product / ASIN / brand. That is
# the ordinary case in Amazon Ads, not an edge case, and it is precisely what
# the pre-v11.15 key could not represent.
FIXTURE = r"""
var allProducts = [{ asin: 'B07KPRTSMT', master_id: 'SP-0001' },
                   { asin: 'B08ZZZZZZZ', master_id: 'SP-0002' }];

const HDR_CAMP = 'Date,Country,Advertised product id,Advertised product marketplace,'
  + 'Ad product,Advertiser account name,Campaign name,Budget currency,Total cost,'
  + 'Impressions,Clicks,Purchases,Sales';
const HDR_BARE = 'Date,Country,Advertised product id,Advertised product marketplace,'
  + 'Ad product,Advertiser account name,Budget currency,Total cost,'
  + 'Impressions,Clicks,Purchases,Sales';

// date, asin, ad product, campaign, cost, imp, clk, purch, sales
const DATA = [
  ['2026-10-01','B07KPRTSMT','Sponsored Products','SP - Meowi Exact',    10, 1000, 50, 5, 100],
  ['2026-10-01','B07KPRTSMT','Sponsored Products','SP - Meowi Broad',    20, 2000, 40, 3,  60],
  ['2026-10-01','B07KPRTSMT','Sponsored Brands',  'SB - Brand Defense',  30, 3000, 30, 2,  40],
  ['2026-10-02','B07KPRTSMT','Sponsored Products','SP - Meowi Exact',    15, 1500, 20, 1,  25],
  ['2026-10-02','B08ZZZZZZZ','Sponsored Products','SP - Meowi Exact',     5,  500, 10, 1,  11],
  ['2026-10-03',''          ,'Sponsored TV',      'TV - Awareness',      40, 9000,  0, 0,   0],
  // a blank campaign cell on an export that HAS the column
  ['2026-10-03','B07KPRTSMT','Sponsored Display', '',                     7,  700,  7, 0,   0],
];

function line(r, withCamp) {
  const cells = ['' + r[0], 'US', r[1], 'AMAZON.COM', r[2], 'Meowijuana Store'];
  if (withCamp) cells.push('"' + r[3] + '"');
  cells.push('USD', r[4], r[5], r[6], r[7], r[8]);
  return cells.join(',');
}
const CSV_CAMP = [HDR_CAMP].concat(DATA.map(r => line(r, true ))).join('\n');
const CSV_BARE = [HDR_BARE].concat(DATA.map(r => line(r, false))).join('\n');
"""

HARNESS = "\n".join([
    fn('parseCSV'),
    fn('adsProductSlug'),
    fn('adsParseDate'),
    fn('adsStripExcel'),
    fn('adsMarketplaceToRegion'),
    fn('adsAdvertiserToBrand'),
    fn('parseAmazonAdsUnified'),
    FIXTURE,
    r"""
const out = {};
const sum = (rows, f) => +rows.reduce((a, r) => a + (+r[f] || 0), 0).toFixed(4);

const withC = parseAmazonAdsUnified(CSV_CAMP);
const noC   = parseAmazonAdsUnified(CSV_BARE);

out.withRows = withC.rows.length;
out.noRows   = noC.rows.length;
out.hasCol   = { withC: withC.hasCampaignCol, noC: noC.hasCampaignCol };
out.distinct = { withC: withC.distinctCampaigns, noC: noC.distinctCampaigns };

// The two SP campaigns on 2026-10-01 / B07KPRTSMT must be two rows.
const d1 = withC.rows.filter(r => r.date === '2026-10-01'
  && r.asin === 'B07KPRTSMT' && r.ad_product === 'sponsored_products');
out.d1Count     = d1.length;
out.d1Campaigns = d1.map(r => r.campaign).sort();
out.d1Spend     = d1.map(r => r.spend).sort((a, b) => a - b);

// THE REGRESSION GUARD: rebuild the pre-v11.15 key and group by it.
const oldKeys = new Map();
for (const r of withC.rows) {
  const k = [r.date, r.region, r.ad_product, r.asin || '', r.advertiser_brand || ''].join('|');
  if (!oldKeys.has(k)) oldKeys.set(k, []);
  oldKeys.get(k).push(r);
}
const collapsed = [...oldKeys.entries()].filter(([, v]) => v.length > 1);
out.oldRowCount        = oldKeys.size;
out.oldCollapsedGroups = collapsed.length;
// what the old key would have stamped the merged row with, and the spend it
// would have carried under that one name
out.oldCollapsedExample = collapsed.length
  ? { campaignKept: collapsed[0][1][0].campaign,
      campaignLost: collapsed[0][1].slice(1).map(r => r.campaign),
      spendUnderOneName: +collapsed[0][1].reduce((a, r) => a + r.spend, 0).toFixed(4) }
  : null;

// SUMS. Finer grain must not move a single total.
for (const f of ['spend', 'impressions', 'clicks', 'purchases', 'attributed_sales']) {
  out['sum_' + f] = { withC: sum(withC.rows, f), noC: sum(noC.rows, f) };
}

// The bare export must be unchanged at the OLD grain, and campaign must be
// null on every row rather than '' or absent.
out.noCampaignValues = [...new Set(noC.rows.map(r => r.campaign))];
out.noCampaignIsNull = noC.rows.every(r => r.campaign === null);
out.noCHasKey        = noC.rows.every(r => Object.prototype.hasOwnProperty.call(r, 'campaign'));
out.bareKeysMatchOld = noC.rows.length === oldKeys.size;

// A blank cell on a column-carrying export is NULL, never ''.
const blank = withC.rows.filter(r => r.ad_product === 'sponsored_display');
out.blankCampaign = blank.map(r => r.campaign);

// Brand-level (no ASIN) rows still carry their campaign.
const tv = withC.rows.filter(r => r.ad_product === 'sponsored_tv');
out.tvCampaign = tv.map(r => r.campaign);
out.tvAsin     = tv.map(r => r.asin);

// master_id resolution is untouched by the new key.
out.mastersWithC = [...new Set(withC.rows.map(r => r.master_id))].sort();
out.mastersNoC   = [...new Set(noC.rows.map(r => r.master_id))].sort();

// Degenerate shapes must not throw or leak a bad value.
out.degenerate = [];
const BAD = [
  [HDR_CAMP, 'Date,Country,Advertised product id,Advertised product marketplace,Ad product,Advertiser account name,Campaign name,Budget currency,Total cost,Impressions,Clicks,Purchases,Sales'].join('\n'),
  HDR_CAMP + '\n2026-10-01,US,,,Sponsored Products,,,,0,0,0,0,0',
  HDR_CAMP + '\n2026-10-01,US,B07KPRTSMT,AMAZON.COM,Sponsored Products,Meowijuana Store,"   ",USD,1,1,1,0,0',
];
for (const csv of BAD) {
  try {
    const r = parseAmazonAdsUnified(csv);
    const blob = JSON.stringify(r.rows);
    out.degenerate.push({ rows: r.rows.length,
      bad: /NaN|Infinity|undefined/.test(blob),
      camps: [...new Set(r.rows.map(x => x.campaign))] });
  } catch (e) { out.degenerate.push({ threw: String(e.message || e) }); }
}
console.log(JSON.stringify(out));
""",
])

hpath = os.path.join(SP, 'test_v1115.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hpath], capture_output=True, text=True)
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:2500]); sys.exit(1)
R = json.loads(res.stdout)

# --- A1  the column is read -------------------------------------------------
eq('A1a hasCampaignCol is true when the export carries it', R['hasCol']['withC'], True)
eq('A1b and false when it does not',                        R['hasCol']['noC'],   False)
eq('A1c four distinct campaigns counted', R['distinct']['withC'], 4)
eq('A1d and none on the bare export',     R['distinct']['noC'],   0)

# --- A2  two campaigns on one ASIN-day are two rows ------------------------
eq('A2a the same ASIN on the same day under two SP campaigns is TWO rows',
   R['d1Count'], 2)
eq('A2b each keeping its own campaign name',
   R['d1Campaigns'], ['SP - Meowi Broad', 'SP - Meowi Exact'])
eq('A2c and its own spend, not a merged figure', R['d1Spend'], [10, 20])

# --- A3  THE REGRESSION GUARD ---------------------------------------------
ok(R['oldCollapsedGroups'] >= 1,
   'A3a the pre-v11.15 key really did collapse campaigns together',
   R['oldCollapsedGroups'])
eq('A3b it produced FEWER rows than the campaign grain',
   R['oldRowCount'] < R['withRows'], True)
ok(R['oldCollapsedExample'] and R['oldCollapsedExample']['campaignLost'],
   'A3c and the collapsed row would have DROPPED a campaign name',
   R['oldCollapsedExample'])
eq('A3d stamping $30 of two campaigns with whichever came first',
   R['oldCollapsedExample']['spendUnderOneName'], 30)
ok(R['oldCollapsedExample']['campaignKept']
   not in R['oldCollapsedExample']['campaignLost'],
   'A3e the kept name is one of the real campaigns, which is what makes the '
   'defect invisible on screen')

# --- A4  SUMS ARE PRESERVED ------------------------------------------------
for f, want in [('spend', 127), ('impressions', 17700), ('clicks', 157),
                ('purchases', 12), ('attributed_sales', 236)]:
    eq('A4  %s is identical at either grain' % f,
       R['sum_' + f]['withC'], R['sum_' + f]['noC'])
    eq('A4  %s totals the file exactly' % f, R['sum_' + f]['withC'], want)

# --- A5  the bare export is unchanged -------------------------------------
eq('A5a an export with no campaign column parses to the OLD row count',
   R['bareKeysMatchOld'], True)
eq('A5b every row carries the campaign key', R['noCHasKey'], True)
eq('A5c and its value is NULL, never the empty string', R['noCampaignIsNull'], True)
eq('A5d so there is exactly one distinct value', R['noCampaignValues'], [None])
eq('A5e master_id resolution is identical at either grain',
   R['mastersWithC'], R['mastersNoC'])

# --- A6  blanks, brand-level rows, degenerate shapes ----------------------
eq('A6a a BLANK campaign cell is null, not an empty-named campaign',
   R['blankCampaign'], [None])
eq('A6b a brand-level row (no ASIN) still carries its campaign',
   R['tvCampaign'], ['TV - Awareness'])
eq('A6c and still has no ASIN', R['tvAsin'], [None])
for i, d in enumerate(R['degenerate']):
    ok('threw' not in d, 'A6d degenerate shape %d does not throw' % i, d)
    ok(not d.get('bad'), 'A6e degenerate shape %d leaks no NaN/Infinity/undefined' % i, d)
eq('A6f a whitespace-only campaign is null too, not "   "',
   R['degenerate'][2]['camps'], [None])


print('\n== B. static - the parser ==')
body = fn('parseAmazonAdsUnified')
ok("ci('campaign name', 'campaign')" in body,
   'B1  the column is detected under both spellings Amazon uses')
ok('${campaign' in body,
   'B2  campaign is INTERPOLATED INTO THE KEY, not just stored on the row')
ok(body.index('${campaign') < body.index('agg.get(key)'),
   'B3  and into the key that builds the aggregation bucket')
ok('hasCampaignCol' in body and 'distinctCampaigns' in body,
   'B4  coverage is reported out of the parser, so the card can say what landed')
ok("|| null) : null" in body or "'').trim() || null" in body,
   'B5  a blank cell resolves to null rather than the empty string')

print('\n== C. static - the handler ==')
h = fn('handleAmazonAdsUpload', kw='async function')
iProbe = h.index("select('campaign')")
iDel   = h.index('.delete()')
iIns   = h.index('.insert(')
ok(iProbe < iDel,
   'C1  the schema probe runs BEFORE the delete')
ok(iDel < iIns, 'C2  and the delete still precedes the insert, so C1 is the '
   'only thing standing between a stale schema and an emptied window')
ok('supabase_v11_15_amazon_ad_spend_campaign.sql' in h,
   'C3  the refusal names the migration to run')
ok('Nothing was deleted' in h,
   'C4  and says the window is intact, so the operator does not re-upload in a panic')
ok('campSummary' in h,
   'C5  the status line reports the campaign read')
ok('no Campaign name column' in h,
   'C6  an export missing the column is CALLED OUT - it parses fine and leaves '
   'the Ads view empty, which is invisible otherwise')
ok('Campaign column empty' in h,
   'C7  and a present-but-empty column is a DIFFERENT message, because the '
   'operator\'s next move differs')
ok('hasCampaignCol: parsed.hasCampaignCol' in h,
   'C8  the audit log records whether campaign landed')

print('\n== D. static - the migration ==')
ok(os.path.exists(SQL), 'D1  the migration file exists')
q = io.open(SQL, encoding='utf-8').read() if os.path.exists(SQL) else ''
ql = q.lower()
ok('add column if not exists campaign' in ql,
   'D2  it adds the column idempotently')
ok("coalesce(campaign,'')" in ql.replace(' ', '').replace("coalesce(campaign,'')", "coalesce(campaign,'')")
   or "coalesce(campaign, '')" in ql,
   'D3  the unique index includes the campaign')
ok('drop index if exists amazon_ad_spend_uniq' in ql,
   'D4  and the OLD narrower unique index is dropped - leaving it would make '
   'two campaigns on one ASIN-day a unique violation that fails the upload '
   'AFTER the delete')
iNew = ql.index('create unique index')
iDrop = ql.index('drop index')
ok(iNew < iDrop,
   'D5  the new index is created BEFORE the old one is dropped, so the table is '
   'never without a uniqueness guard')
ok('amazon_ad_spend_campaign_idx' in ql,
   'D6  and the Ads view gets an index to group on')
ok('null' in ql and 'no campaign' in ql,
   'D7  the migration states that historical rows carry NULL and must be '
   'shown rather than filtered out')

print('\n== E. static - nothing else had to change ==')
ok(js.count("from('amazon_ad_spend').insert(") == 1,
   'E1  amazon_ad_spend still has exactly ONE writer',
   js.count("from('amazon_ad_spend').insert("))
buck = fn('buildAdSpendBuckets')
ok('+ spend' in buck and '+ attSales' in buck,
   'E2  buildAdSpendBuckets ACCUMULATES, so the finer grain cannot drop a row')
ok(buck.count('.set(') >= 6 and '.set(k, (' in buck,
   'E3  every bucket write reads its own prior value first')
ok(re.search(r'v11\.15\s*\u00b7\s*2026-10-28', js) is not None
   or 'v11.15' in s,
   'E4  the version chip reads v11.15')

print('\n' + '-' * 58)
print('v11.15: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
