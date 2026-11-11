#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.05 - Walmart campaign x day, from the Custom report builder.

Ad Center -> Reports -> Custom, saved as "Campaign x Day - 14d". The feed the
Walmart ads work has been missing since v11.25: campaign rows that carry their
own DATE.

/!\ THE REAL EXPORT IS NOT COMMITTED - campaign names and spend are business
data and this repo is served publicly (the v11.87 rule). The fixture below
carries the real HEADER SHAPE, including the DOUBLE SPACE Walmart puts in
`In-store Attributed Sales  - 14 Days` and the literal word `null`, with
invented figures and campaign names.

The shipped parser was driven over the real file separately and reconciles to
the independently-pulled Advertiser export EXACTLY on all seven days, spend
AND sales:
    spend  155.65 161.49 181.39 190.83 177.51 154.48 158.09
    sales  430.00 441.84 408.92 521.68 357.73 379.97 235.70

/!\ AND THAT TIE-OUT IS THE ONLY REASON A BUG WAS CAUGHT: a broken regex made
every conversion column read as ABSENT, and the parser cheerfully returned 35
rows of spend-only. Spend matched on all seven days while sales read 0.00. A
PARTIAL tie-out is what a silent mapping failure looks like.
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0


def ok(cond, label, extra=None):
    global passed, failed
    if cond:
        passed += 1; print("  ok    %s" % label)
    else:
        failed += 1
        print("  FAIL  %s%s" % (label, ("  got: %s" % ascii(extra)) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("\n};", i) + 3]


def line_of(pat):
    for ln in js.split("\n"):
        if pat in ln:
            return ln
    raise SystemExit("not found: " + pat)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.05  Walmart campaigns, every day")
print("=" * 70)

# /!\ The real header, byte for byte: the preamble line above it, the
# abbreviated `Total Sales Rev.`, `Orders` without `Total`, and the DOUBLE
# SPACE in the in-store column. An exact-match header lookup reads that column
# as absent and drops in-store silently, which is why hdrNorm is used.
PRE = '"Period Requested: Nov 04, 2026 - Nov 06, 2026 "'
HDR = ("Date,Campaign Type Name,Campaign Name,Impressions,Clicks,Ad Spend,CTR,"
       "Total Units Sold - 14 Day,Orders - 14 Day,Total Sales Rev. - 14 Day,"
       "In-store Attributed Sales  - 14 Days,New-to-Brand Orders - 14 Days,"
       "New-to-Brand Sales - 14 Days")

FIX = "\n".join([
    PRE, HDR,
    '04-Nov-26,Sponsored Products (Auto),SP - AUTO - TEST - Kitty Ka zoom,"34,414",114,$ 67.77,0.33%,30,28,$ 209.48,$ 0.00,27,$ 201.90',
    # /!\ the literal word null, which this export really writes
    '04-Nov-26,Sponsored Products (Manual),SP - KW - TEST - DOGGIJUANA,"1,639",4,$ 3.00,0.24%,null,null,null,$ 0.00,0,$ 0.00',
    '05-Nov-26,Sponsored Videos,SBV - TEST - Mixed - Kitty Ka Zoom,"7,979",44,$ 26.47,0.55%,10,8,$ 70.31,$ 5.43,7,$ 49.40',
    # a genuinely EMPTY cell is still a null - only the literal word moves
    '05-Nov-26,Sponsored Products (Auto),SP - AUTO - TEST - Unbranded,"1,000",2,$ 1.00,0.20%,,,,$ 0.00,0,$ 0.00',
])

PIECES = "\n".join([
    fn_flat("parseDelimited"),
    line_of("function parseCSV(line)"),
    line_of("function clean(s)"),
    line_of("const hdrNorm ="),
    fn_flat("_wmcNum"),
    line_of("function _wmcInt(v)"),
    fn_flat("_wmcCi"),
    fn_flat("_wmcHeaderIdx"),
    fn_flat("_wmcAttrCol"),
    const_obj("_WMC_SQL"),
    fn_flat("_wmcTableErr"),
    fn_flat("parseLocalDate"),
    fn_flat("fmtLocalYMD"),
    fn_flat("adsParseDate"),
    fn_flat("adsAdvertiserToBrand"),
    fn_flat("parseWalmartAdCampaignDaily"),
])

DRIVER = r"""
'use strict';
__PIECES__
const written = [];
let conflict = null;
async function getSB() {
  return { from: () => ({ upsert: (rows, o) => { written.push(...rows); conflict = o && o.onConflict;
    return Promise.resolve({ error: null }); } }) };
}
const go = async (txt) => {
  written.length = 0; conflict = null;
  try {
    const r = await parseWalmartAdCampaignDaily(txt, 'Kitty Ka-Zoom (SmarterPaw LLC) (1p - SS)', 'US');
    return { r, rows: written.slice(), conflict };
  } catch (e) { return { threw: e.message }; }
};
const H = __HDR__;
(async () => {
  const out = {};
  out.good = await go(__FIX__);

  // --- the refusals -------------------------------------------------------
  // /!\ MIXED ATTRIBUTION WINDOWS. A 3-day Orders column beside a 14-day
  // Sales column makes ROAS and CPA describe different populations in one row.
  out.mixed = await go('Date,Campaign Name,Ad Spend,Orders - 3 Day,Total Sales Rev. - 14 Day\n'
                     + '04-Nov-26,X,$ 1.00,1,$ 2.00');
  // The ADVERTISER export dropped on this zone: a date, but no campaign.
  out.noCamp = await go('Date,Impressions,Clicks,Ad Spend\n"Nov 04, 2026","1",1,$ 1.00');
  out.noSpend = await go('Date,Campaign Name,Clicks\n04-Nov-26,X,5');
  // A file that is ONLY a preamble and a header.
  out.headerOnly = await go(__PRE__ + '\n' + H);

  // --- one window is fine however many measures declare it ----------------
  out.oneWin = await go('Date,Campaign Name,Ad Spend,Orders - 30 Day,Total Sales Rev. - 30 Day\n'
                      + '04-Nov-26,X,$ 1.00,1,$ 2.00');
  console.log(JSON.stringify(out));
})();
"""

A = run_node(os.path.join(SP, "_v1205_a.js"),
             DRIVER.replace("__PIECES__", PIECES)
                   .replace("__FIX__", json.dumps(FIX))
                   .replace("__HDR__", json.dumps(HDR))
                   .replace("__PRE__", json.dumps(PRE)))

G = A["good"]
if "threw" in G:
    print("  FAIL  the fixture threw: " + G["threw"]); raise SystemExit(1)
R, ROWS = G["r"], G["rows"]

# ===========================================================================
print("\nA. the parser, driven over the real header shape")
# ===========================================================================
eq("A1  four campaign-days", R["rows"], 4)
# /!\ FOUR, not three - my own miscount. The fixture carries an `Unbranded`
# campaign as well, which section C needs to prove an unrecognised name stays
# null rather than being guessed at.
eq("A2  four distinct campaigns", R["campaigns"], 4)
# /!\ THE HEADER IS ON LINE 2 - the Custom export puts a preamble above it.
eq("A3  /!\\ the preamble line is not read as a header", [R["from"], R["to"]],
   ["2026-11-04", "2026-11-05"])
eq("A4  04-Nov-26 becomes 2026-11-04", ROWS[0]["date"], "2026-11-04")
eq("A5  '$ 155.65' with a space parses", ROWS[0]["spend"], 67.77)
eq("A6  commas strip out of an integer", ROWS[0]["impressions"], 34414)
eq("A7  the campaign type comes across", ROWS[0]["campaign_type"], "Sponsored Products (Auto)")
eq("A8  units / orders / sales map", [ROWS[0]["units"], ROWS[0]["orders"], ROWS[0]["sales"]],
   [30, 28, 209.48])
eq("A9  NTB maps to its OWN two columns",
   [ROWS[0]["ntb_orders"], ROWS[0]["ntb_sales"]], [27, 201.90])
# /!\ THE DOUBLE SPACE. `In-store Attributed Sales  - 14 Days` - an exact
# header match reads this column as absent and drops in-store with no message.
eq("A10 /!\\ the DOUBLE-SPACE in-store header still resolves", ROWS[2]["in_store_sales"], 5.43)
eq("A11 the attribution window is read off the headers", R["attributionDays"], 14)
eq("A12 ...and stamped on every row",
   sorted({r["attribution_days"] for r in ROWS}), [14])
eq("A13 it upserts on date+region+account+campaign", A["good"]["conflict"],
   "date,region,account,campaign")
eq("A14 every measure was found", R["absent"], [])

print("\nB. the literal `null`, and the empty cell beside it")
# /!\ THE TIE-OUT IS THE EVIDENCE. Walmart writes the TEXT `null` where it
# means zero - the daily sums match the Advertiser export only when these
# count as 0. Stored as null, a campaign that spent $3.00 and returned nothing
# shows a BLANK ROAS, hiding a loser behind what reads as missing data.
eq("B1  /!\\ the literal word `null` is a reported ZERO",
   [ROWS[1]["units"], ROWS[1]["orders"], ROWS[1]["sales"]], [0, 0, 0])
eq("B2  ...and its spend is real", ROWS[1]["spend"], 3.00)
# /!\ AND AN EMPTY CELL IS STILL A NULL - v11.25's rule is not repealed, only
# the literal word moves.
eq("B3  /!\\ an EMPTY cell is still a gap, not a zero",
   [ROWS[3]["units"], ROWS[3]["orders"], ROWS[3]["sales"]], [None, None, None])

print("\nC. the brand comes from the CAMPAIGN NAME")
# /!\ Walmart's own Brand dimension split one campaign across the brand and an
# `unknown` bucket, so it is not a key. This is walmart_ad_campaign's rule.
eq("C1  a Kitty campaign under the Kitty account", ROWS[0]["advertiser_brand"], "Kitty Ka-Zoom")
eq("C2  /!\\ a DOGGIJUANA campaign inside the same account files under Doggijuana",
   ROWS[1]["advertiser_brand"], "Doggijuana")
eq("C3  an unrecognised name stays null rather than guessing",
   ROWS[3]["advertiser_brand"], None)

print("\nD. what it refuses")
ok("mixes attribution windows" in (A["mixed"].get("threw") or ""),
   "D1  /!\\ a file mixing 3-day and 14-day measures", A["mixed"].get("threw"))
ok("3 and 14" in (A["mixed"].get("threw") or ""),
   "D2  ...naming both windows it found", A["mixed"].get("threw"))
ok("Daily uploader" in (A["noCamp"].get("threw") or ""),
   "D3  /!\\ an Advertiser export is sent to its own uploader", A["noCamp"].get("threw"))
ok("Ad Spend" in (A["noSpend"].get("threw") or ""), "D4  no spend column")
ok("No dated campaign rows" in (A["headerOnly"].get("threw") or ""),
   "D5  a preamble and a header and nothing else", A["headerOnly"].get("threw"))
eq("D6  /!\\ ONE window is fine whatever it is - 30-day is not special",
   A["oneWin"]["r"]["attributionDays"], 30)

# ===========================================================================
print("\nE. the view, and the monthly rules it must NOT inherit")
# ===========================================================================
CFG = r"""
'use strict';
global.document = { getElementById: () => null };
const PNL_GRAIN_ORDER = ['day', 'week', 'month'];
__WMTIP__
__COL0__
__CHANNELS__
__VIEWS__
__COLUMNS__
__VIEWCFG__
__ALLOWED__
__WHY__
__BANDWHY__
const out = {};
const cd = adsViewCfg('walmart', 'campdaily');
const c  = adsViewCfg('walmart', undefined);
out.monthOf  = [typeof cd.monthOf, typeof c.monthOf];
out.inWindow = typeof cd.inWindow;
out.grains   = adsGrainAllowed(cd);
out.chanGrains = adsGrainAllowed(c);
out.groupBy  = cd.groupBy;
out.noun     = cd.noun;
out.host     = cd.host;
out.dateField = cd.dateField;
out.filters  = (cd.filters || []).map(f => f.k);
out.stateFields = (cd.stateFields || []).length;
out.band     = !!adsBandWhy(cd);
out.cols     = cd.columns.map(x => x.k);
out.mapped   = cd.map({ campaign: 'SP - X', campaign_type: 'Sponsored Videos',
                        advertiser_brand: 'Doggijuana', impressions: '10', clicks: '2',
                        spend: '1.5', orders: '3', units: '4', sales: '9',
                        in_store_sales: '2', ntb_orders: '1', ntb_sales: '5' });
out.mappedNoNtb = cd.map({ campaign: 'X', spend: '1' });
console.log(JSON.stringify(out));
"""
E = run_node(os.path.join(SP, "_v1205_b.js"),
             CFG.replace("__WMTIP__", const_obj("WM_ADS_TIP"))
                .replace("__COL0__", line_of("function col0(v)"))
                .replace("__CHANNELS__", const_obj("ADS_CHANNELS"))
                .replace("__VIEWS__", const_obj("ADS_VIEWS"))
                .replace("__COLUMNS__", const_obj("ADS_COLUMNS"))
                .replace("__VIEWCFG__", fn_flat("adsViewCfg"))
                .replace("__ALLOWED__", fn_flat("adsGrainAllowed"))
                .replace("__WHY__", fn_flat("_adsGrainWhy"))
                .replace("__BANDWHY__", fn_flat("adsBandWhy")))

eq("E1  /!\\ monthOf is SHADOWED, or the chart pins this feed to months",
   E["monthOf"], ["undefined", "function"])
eq("E2  /!\\ and so is inWindow", E["inWindow"], "undefined")
eq("E3  /!\\ so it offers day, week AND month", E["grains"], ["day", "week", "month"])
eq("E4  while the monthly campaigns feed is still month-only", E["chanGrains"], ["month"])
eq("E5  grouped by campaign, like the monthly one", E["groupBy"], "campaign")
eq("E6  and counted as campaigns", E["noun"], "campaign")
eq("E7  its own host", E["host"], "wmcd")
eq("E8  reading the row's own date", E["dateField"], "date")
# The export has Campaign Type Name but no status column.
eq("E9  one filter - there is no status in this export", E["filters"], ["type"])
# /!\ EMPTY, NOT ABSENT. adsViewCfg gives this view the walmart CHANNEL as its
# prototype, so omitting stateFields inherits dailyBudget + biddingStrategy
# over a feed whose export has neither column.
eq("E10 /!\\ stateFields declared EMPTY, shadowing the channel's two", E["stateFields"], 0)
# Unlike the account-total Daily view, a campaign IS something to band by.
eq("E11 /!\\ the band reading is NOT refused here - campaigns are real rows",
   E["band"], False)

print("\nF. NTB counts ORDERS here and CUSTOMERS on Chewy")
# /!\ rule 3a, caught at design time. The two render one tab apart.
eq("F1  /!\\ ntb is NOT populated - that slot means CUSTOMERS on Chewy",
   E["mapped"]["ntb"], None)
eq("F2  it lands in its own two slots",
   [E["mapped"]["ntbOrders"], E["mapped"]["ntbSales"]], [1, 5])
ok("ntbOrders" in E["cols"] and "ntbSales" in E["cols"],
   "F3  ...and both have a column")
ok("ntb" not in E["cols"], "F4  /!\\ while the bare `ntb` column is absent")
NTBCOL = [c for c in re.findall(r"\{ k: 'ntbOrders'[^}]*\}", js)]
ok(NTBCOL and "ORDERS, not customers" in NTBCOL[0],
   "F5  /!\\ and the header says so on its tooltip")
eq("F6  a feed with no NTB maps null, never 0",
   [E["mappedNoNtb"]["ntbOrders"], E["mappedNoNtb"]["ntbSales"]], [None, None])

# The rollup has to carry the two new slots, or the table reads zero.
ROLL = fn_flat("adsCampaignRollup")
ok("ntbOrders: 0, ntbSales: 0," in ROLL, "F7  the accumulator carries them")
ok("c.hasNtbOrders = true;" in ROLL, "F8  ...and records that the feed had them")
ok("if (!c.hasNtbOrders) { c.ntbOrders = null; c.ntbSales = null; }" in js,
   "F9  /!\\ a feed without them reads a GAP, never 0")
ok("sl.ntbOrders += (r.ntbOrders || 0);" in ROLL,
   "F10 and the per-bucket series sums them, so they are plottable")
for k in ("ntbOrders", "ntbSales"):
    ok("%s:" % k in const_obj("ADS_METRIC_SPEC"), "F11 %s is a chart metric" % k)
    ok("%s:" % k in const_obj("ADS_METRIC_COLOR"), "F12 ...with its own colour" % ())

print("\nG. every registry, and the four tabs")
for pat, label in [
    ("walmart_ad_campaign_daily: 'grp-walmart-ads',", "G1  upload group map"),
    ("'dz-walmart-ad-camp-daily': 'walmart_ad_campaign_daily',", "G2  recent-uploads rail"),
    ("walmart_ad_campaign_daily: { icon: '\\ud83d\\udce1'", "G3  source chip"),
    ("walmart_ad_campaign_daily: { label:'Walmart Ads — Campaign × Day'", "G4  coverage grid"),
    ('id="dz-walmart-ad-camp-daily"', "G5  dropzone"),
    ('id="st-walmart-ad-camp-daily"', "G6  status line"),
    ('id="last-walmart-ad-camp-daily"', "G7  latest-data line"),
    ("handleWalmartAdCampaignDailyUpload(this)", "G8  handler wired"),
    ('id="wmpnl-ads-tab-campdaily"', "G9  sub-tab"),
    ('id="wmpnl-ads-view-campdaily"', "G10 area"),
    ('id="wmcd-host"', "G11 host"),
    ("walmart_ad_campaign_daily: 'supabase_v12_05_walmart_ad_campaign_daily.sql',",
     "G12 the migration is named by the error"),
]:
    ok(pat in s, label, None if pat in s else pat)

SW = fn_flat("switchWalmartAdsView")
eq("G13 four areas, and campdaily among them",
   len(re.findall(r"'wmpnl-ads-view-\w+'", SW)), 4)
ok("'daily', 'campdaily', 'campaigns', 'keywords'" in SW,
   "G14 /!\\ and the validator knows all four, so none falls back silently")

# ===========================================================================
print("\nH. the migration - RLS, which v12.03 shipped without")
# ===========================================================================
SQLP = os.path.join(ROOT, "supabase_v12_05_walmart_ad_campaign_daily.sql")
ok(os.path.exists(SQLP), "H1  it is in the repo")
sql = io.open(SQLP, encoding="utf-8").read()
ok("alter table walmart_ad_campaign_daily enable row level security;" in sql, "H2  RLS enabled")
ok("create policy walmart_ad_campaign_daily_authenticated_all" in sql,
   "H3  /!\\ AND a policy - the half v12.03 forgot, which denied every insert")
ok("with check (true)" in sql, "H4  with check, or an INSERT is still refused")
ok("grant usage, select on sequence walmart_ad_campaign_daily_id_seq to authenticated;" in sql,
   "H5  the sequence grant a bigserial needs")
ok("on walmart_ad_campaign_daily (date, region, account, campaign)" in sql,
   "H6  /!\\ the unique index IS the parser's onConflict target")
for c in ("date", "region", "account", "campaign"):
    ok(re.search(r"\n  %s\s+\S+\s+not null" % c, sql) is not None,
       "H7  /!\\ %s is NOT NULL, so the index is plain and upsert can target it" % c)
# /!\ attribution_days is NOT in the key: a re-pull at another window must
# REPLACE the day rather than double its spend.
ok("attribution_days" in sql and "(date, region, account, campaign)" in sql
   and "attribution_days)" not in sql.split("create unique index")[1].split(";")[0],
   "H8  /!\\ attribution_days is NOT in the unique key")
ok("master_id" not in sql.split("create table")[1].split(");")[0],
   "H9  no master_id, so the merge registry is a no-op")
ok("walmart_ad_campaign_daily" not in const_obj("MERGE_MASTER_ID_TABLES"),
   "H10 ...and it is correctly absent from it")

print("\nI. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "I1  both declare a version")
eq("I2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
