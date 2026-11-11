#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.03 - the Walmart ads feed finally carries its own date.

Jason: "i want to upload walmart ads on a weekly basis. i found a new report
here. i need to be able to drive performance for walmart ads"

Ad Center -> Reports -> Advertiser -> Report type: Daily performance. ONE ROW
PER DAY, with the date ON the row - the one thing v11.25's two feeds do not
have, and the reason the Walmart ad grain has been monthly since v11.67.

/!\ AND IT IS THE ADVERTISER TOTAL. No campaign, no keyword, no orders, no
units, and no usable brand split. Most of this suite is about the things that
therefore have to REFUSE rather than render a measured-looking zero.

/!\ THE REAL EXPORT IS NOT COMMITTED - it is business data and this repo is
served publicly (the v11.87 rule). The fixture below carries the real HEADER
SHAPE, including the trailing space Walmart puts on the last column, with
invented figures. The shipped parser was driven over the real 10-day file
separately: 10 rows, 2026-11-01 -> 2026-11-10, $1,664.67, 0 bad dates.
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
print("  v12.03  Walmart ads, per day, from the file's own date")
print("=" * 70)

# /!\ The real export's header line, byte for byte INCLUDING the trailing
# space on the last column - which is the kind of thing a hand-written alias
# list gets wrong and nothing notices until a column reads null.
HDR = ('"Date","Impressions","Clicks","Average CPC","CTR",'
       '"Total Product Detail Page Views","Total Add to Cart","Ad Spend",'
       '"Total Attr. Sales Revenue","ROAS","In-store Attributed Sales "')

# /!\ A PREAMBLE LINE ABOVE THE HEADER, which the Custom export really
# ships. The Advertiser export does not, and both must parse.
PREAMBLE = '"Period Requested: Nov 08, 2026 - Nov 10, 2026 "'
FIX = "\n".join([
    HDR,
    '"Nov 10, 2026","54,365","243","$0.65","0.45%","0","0","$158.09","$235.70","$1.49","$12.43"',
    '"Nov 09, 2026","61,867","245","$0.63","0.40%","140","63","$154.48","$379.97","$2.46","$21.28"',
    '"Nov 08, 2026","69,060","264","$0.67","0.38%","209","87","$177.51","$357.73","$2.02","$20.52"',
])

PIECES = "\n".join([
    fn_flat("parseDelimited"),
    line_of("function parseCSV(line)"),
    line_of("function clean(s)"),
    fn_flat("_wmcNum"),
    line_of("function _wmcInt(v)"),
    fn_flat("_wmcCi"),
    # v12.05 - the header is FOUND now, through a helper both Walmart
    # daily parsers share. hdrNorm is a one-liner, so line_of.
    line_of("const hdrNorm ="),
    fn_flat("_wmcHeaderIdx"),
    const_obj("_WMC_SQL"),
    fn_flat("_wmcTableErr"),
    fn_flat("adsParseDate"),
    fn_flat("adsAdvertiserToBrand"),
    fn_flat("parseWalmartAdDaily"),
])

# ===========================================================================
print("\nA. the parser, driven")
# ===========================================================================
DRIVER = r"""
'use strict';
__PIECES__
const written = [];
let conflict = null, calls = 0;
async function getSB() {
  return { from: () => ({ upsert: (rows, o) => {
    calls++; written.push(...rows); conflict = o && o.onConflict;
    return Promise.resolve({ error: null });
  } }) };
}
const out = {};
const go = async (txt, acct) => {
  written.length = 0; conflict = null; calls = 0;
  try {
    const r = await parseWalmartAdDaily(txt, acct || 'Kitty Ka-Zoom (SmarterPaw LLC) (1p - SS)', 'US');
    return { r, rows: written.slice(), conflict, calls };
  } catch (e) { return { threw: e.message }; }
};
(async () => {
  const good = await go(__FIX__);
  out.result = good.r; out.rows = good.rows; out.conflict = good.conflict;

  // --- B refusals ---------------------------------------------------------
  // A Campaigns export: real columns, NO Date. It must be named, not parsed
  // into rows with no date - the one thing this table exists to carry.
  out.noDate = await go('"Campaign Name","Ad Spend"\n"SP - AUTO","$10.00"');
  out.empty  = await go('"Date","Ad Spend"');
  out.noSpend = await go('"Date","Clicks"\n"Nov 10, 2026","5"');
  // Every row's date unreadable -> refused, and the first bad value QUOTED.
  out.allBad = await go('"Date","Ad Spend"\n"week 45","$10.00"\n"week 46","$11.00"');
  // SOME unreadable -> the good rows land and the skipped ones are counted.
  out.someBad = await go('"Date","Ad Spend"\n"week 45","$10.00"\n"Nov 10, 2026","$11.00"');

  // --- C ISO dates, because Walmart has shipped both -----------------------
  out.iso = await go('"Date","Ad Spend"\n"2026-11-10","$9.00"');

  // --- D a blank metric cell is NOT a zero ---------------------------------
  out.blank = await go('"Date","Ad Spend","Clicks","In-store Attributed Sales "\n"Nov 10, 2026","$9.00","",""');

  console.log(JSON.stringify(out));
})();
"""

A = run_node(os.path.join(SP, "_v1203_a.js"),
             DRIVER.replace("__PIECES__", PIECES)
                   .replace("__FIX__", json.dumps(FIX)))

R = A["result"]
eq("A1  three dated rows", R["rows"], 3)
eq("A2  the window is read OFF THE FILE, not typed", [R["from"], R["to"]],
   ["2026-11-08", "2026-11-10"])
eq("A3  and the spend sums", round(R["spend"], 2), 490.08)
eq("A4  no unreadable dates", R["badDates"], 0)
# /!\ "Nov 10, 2026" through adsParseDate. _wmcDate takes ISO ONLY and would
# have returned null on every row of the real file.
eq("A5  /!\\ 'Nov 10, 2026' becomes 2026-11-10", A["rows"][0]["date"], "2026-11-10")
eq("A6  commas are stripped from an integer", A["rows"][0]["impressions"], 54365)
eq("A7  a dollar sign is stripped", A["rows"][0]["spend"], 158.09)
# /!\ The trailing space on the real header. clean() trims it; an alias list
# written without trimming would have left in_store_sales null on every row.
eq("A8  /!\\ the trailing-space header still resolves", A["rows"][0]["in_store_sales"], 12.43)
eq("A9  brand comes from the ACCOUNT, the only brand fact on the row",
   A["rows"][0]["advertiser_brand"], "Kitty Ka-Zoom")
# /!\ A REPORTED ZERO IS KEPT. The newest day in the real file carries 243
# clicks and 0 page views - a restating figure, not a blank.
eq("A10 /!\\ a reported 0 page views is stored as 0", A["rows"][0]["dpv"], 0)
eq("A11 ...and 0 add to cart beside it", A["rows"][0]["atc"], 0)

# /!\ UPSERT ON THE THREE KEY COLUMNS. The trailing days restate, so an
# overlapping weekly upload has to be able to CORRECT a day it already wrote.
eq("A12 /!\\ it upserts on (date, region, account)", A["conflict"], "date,region,account")

# The derived three are in the file and are NOT stored: a week of daily CTRs
# does not add up to the week's CTR (rule 3a).
for k in ("ctr", "cpc", "roas", "avg_cpc"):
    ok(k not in A["rows"][0], "A13 /!\\ %s is NOT stored - it is derived" % k)

print("\nB. what it refuses")
ok("Missing required column: Date" in (A["noDate"].get("threw") or ""),
   "B1  /!\\ a Campaigns export is named, not parsed", A["noDate"].get("threw"))
ok("own uploader" in (A["noDate"].get("threw") or ""),
   "B2  ...and sent to the right uploader")
ok("empty" in (A["empty"].get("threw") or "").lower(), "B3  a header-only file", A["empty"].get("threw"))
ok("Ad Spend" in (A["noSpend"].get("threw") or ""), "B4  no spend column", A["noSpend"].get("threw"))
ok("No dated rows" in (A["allBad"].get("threw") or ""), "B5  every date unreadable")
ok('"week 45"' in (A["allBad"].get("threw") or ""),
   "B6  /!\\ ...and the first bad value is QUOTED, not counted", A["allBad"].get("threw"))
eq("B7  a partly-bad file keeps the good rows", A["someBad"]["r"]["rows"], 1)
eq("B8  ...and counts the skipped ones", A["someBad"]["r"]["badDates"], 1)

print("\nC. the shapes Walmart has actually shipped")
eq("C1  an ISO date passes straight through", A["iso"]["rows"][0]["date"], "2026-11-10")
# /!\ v11.25's own rule: an empty metric cell is not a zero.
eq("C2  /!\\ a BLANK clicks cell is null, not 0", A["blank"]["rows"][0]["clicks"], None)
eq("C3  /!\\ and a blank in-store cell too", A["blank"]["rows"][0]["in_store_sales"], None)
eq("C4  ...while the spend beside it is real", A["blank"]["rows"][0]["spend"], 9.0)

# ===========================================================================
print("\nD. the view config - the monthly rules are SHADOWED, not inherited")
# ===========================================================================
CFG = r"""
'use strict';
global.document = { getElementById: (id) => (global.__BRAND && id === 'wmpnl-brand') ? { value: global.__BRAND } : null };
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
const d = adsViewCfg('walmart', 'daily');
const c = adsViewCfg('walmart', undefined);
const k = adsViewCfg('walmart', 'keywords');

// /!\ THE WHOLE POINT. `typeof ch.monthOf === 'function'` is what pins the
// walmart channel to a monthly grain - it buckets every row onto its month,
// refuses the D and W buttons and makes the coverage line say "monthly
// grain". The daily view must NOT inherit it.
out.dailyMonthOf = typeof d.monthOf;
out.chanMonthOf  = typeof c.monthOf;
out.kwMonthOf    = typeof k.monthOf;
out.dailyInWindow = typeof d.inWindow;
out.chanInWindow  = typeof c.inWindow;

out.dailyGrains = adsGrainAllowed(d);
out.chanGrains  = adsGrainAllowed(c);
out.kwGrains    = adsGrainAllowed(k);

out.dateField = [d.dateField, c.dateField];
out.groupBy   = [d.groupBy, c.groupBy || 'campaign'];
out.noun      = d.noun;
out.defaultSort = [d.defaultSort || null, c.defaultSort || null, k.defaultSort || null];
out.filters   = [(d.filters || []).length, (c.filters || []).length];
out.stateFields = [(d.stateFields || []).length, (c.stateFields || []).length];
out.host      = [d.host, c.host, k.host];
out.src       = d.src;
out.table     = d.table;

// /!\ THE PAGE BRAND CONTROL CANNOT NARROW AN ACCOUNT TOTAL.
global.__BRAND = '';
out.brandNone = d.brand();
out.blessNone = d.brandless();
global.__BRAND = 'Doggijuana';
out.brandPicked = d.brand();              // still '' - the filter is not applied
out.blessPicked = d.brandless();          // ...and it SAYS it is not applied
out.chanBrandPicked = c.brand();          // the campaigns view still honours it
global.__BRAND = '';

out.bandDaily = !!adsBandWhy(d);
out.bandChan  = !!adsBandWhy(c);
out.bandKw    = !!adsBandWhy(k);

// The column registry: no orders, no units, no CVR, no CPA - the export
// carries none of them and a derived 0.0% would be a measured-looking zero.
// /!\ The campaigns view carries NO `columns` of its own - it falls through
// to ADS_COLUMNS[channel], which is exactly the `ch.columns || ADS_COLUMNS[...]`
// the renderer resolves. Reading c.columns here returned [] and made F4b pass
// vacuously on my first run.
out.dailyCols = d.columns.map(x => x.k);
out.chanCols  = (c.columns || ADS_COLUMNS.walmart).map(x => x.k);

// The mapper, on one row.
out.mapped = d.map({ date: '2026-11-10', impressions: '54365', clicks: '243',
                     spend: '158.09', sales: '235.70', dpv: 0, atc: 0,
                     in_store_sales: '12.43', advertiser_brand: 'Kitty Ka-Zoom' });
out.mappedNullSales = d.map({ date: '2026-11-10', spend: '1' }).sales;
console.log(JSON.stringify(out));
"""

D = run_node(os.path.join(SP, "_v1203_b.js"),
             CFG.replace("__WMTIP__", const_obj("WM_ADS_TIP"))
                # /!\ line_of, not fn_flat: col0 is a ONE-LINER, and fn_flat
                # slices to the next "\n}" - which here is hundreds of lines
                # down, swallowing ADS_VIEWS whole.
                .replace("__COL0__", line_of("function col0(v)"))
                .replace("__CHANNELS__", const_obj("ADS_CHANNELS"))
                .replace("__VIEWS__", const_obj("ADS_VIEWS"))
                .replace("__COLUMNS__", const_obj("ADS_COLUMNS"))
                .replace("__VIEWCFG__", fn_flat("adsViewCfg"))
                .replace("__ALLOWED__", fn_flat("adsGrainAllowed"))
                .replace("__WHY__", fn_flat("_adsGrainWhy"))
                .replace("__BANDWHY__", fn_flat("adsBandWhy")))

eq("D1  /!\\ the daily view does NOT inherit monthOf", D["dailyMonthOf"], "undefined")
eq("D2  ...while the channel still has it", D["chanMonthOf"], "function")
eq("D3  ...and so does Keywords", D["kwMonthOf"], "function")
eq("D4  /!\\ nor inWindow", D["dailyInWindow"], "undefined")
eq("D5  ...which the channel still has", D["chanInWindow"], "function")

# THE DEFECT THIS RELEASE FIXES, as a measurement rather than a claim.
eq("D6  /!\\ the daily view offers day, week AND month",
   D["dailyGrains"], ["day", "week", "month"])
eq("D7  /!\\ while the campaign feed is still monthly ONLY", D["chanGrains"], ["month"])
eq("D8  ...and so is Keywords", D["kwGrains"], ["month"])

eq("D9  the date column is the row's own", D["dateField"], ["date", "reporting_date"])
eq("D10 rows are grouped by day", D["groupBy"], ["day", "campaign"])
eq("D11 and counted as days", D["noun"], "day")
eq("D12 it opens sorted by date; nothing else declares a default",
   D["defaultSort"], ["day", None, None])
eq("D13 no filters - there is no type and no status on this report", D["filters"][0], 0)
eq("D14 ...while the campaigns view keeps its two", D["filters"][1], 2)
eq("D15 no state fields - no budget and no bid strategy either", D["stateFields"], [0, 2])
eq("D16 its own host, so its table and chart are its own",
   D["host"], ["wmday", "wmads", "wmkw"])
eq("D17 one source", D["src"], ["walmart_ad_daily"])
eq("D18 one table", D["table"], "walmart_ad_daily")

print("\nE. the brand control, which cannot bite here")
eq("E1  /!\\ the daily view never applies a brand", D["brandPicked"], "")
eq("E2  ...not even when none is picked", D["brandNone"], "")
ok("NOT applied" in (D["blessPicked"] or ""),
   "E3  /!\\ and the coverage line SAYS a picked brand is not applied", D["blessPicked"])
ok("Doggijuana" in (D["blessPicked"] or ""),
   "E4  ...naming the one that was picked", D["blessPicked"])
ok(D["blessNone"] and "NOT applied" not in D["blessNone"],
   "E5  with none picked it just states the scope", D["blessNone"])
eq("E6  /!\\ and the CAMPAIGNS view still honours the brand",
   D["chanBrandPicked"], "Doggijuana")

print("\nF. nothing to band, and nothing to divide")
eq("F1  /!\\ the daily view refuses the band reading", D["bandDaily"], True)
eq("F2  the campaigns view does not", D["bandChan"], False)
eq("F3  nor does Keywords", D["bandKw"], False)

for k in ("orders", "units", "cvr", "cpa"):
    ok(k not in D["dailyCols"],
       "F4  /!\\ no %s column - the export carries none, and a derived 0 would be a lie" % k)
    ok(k in D["chanCols"], "F4b ...while the campaigns registry has %s" % k)
eq("F5  it leads with the date", D["dailyCols"][0], "day")
for k in ("spend", "sales", "roas", "acos", "inStoreSales", "omniRoas", "dpv", "atc"):
    ok(k in D["dailyCols"], "F6  %s survives" % k)

eq("F7  the mapper reads the row", D["mapped"]["day"], "2026-11-10")
eq("F8  /!\\ brand is nulled on the ROW too, or any brand filter would bite",
   D["mapped"]["brand"], None)
eq("F9  in-store is carried across", D["mapped"]["inStoreSales"], 12.43)
eq("F10 /!\\ a reported 0 page views stays 0", D["mapped"]["dpv"], 0)
eq("F11 /!\\ an absent sales figure stays NULL, never 0", D["mappedNullSales"], None)

# ===========================================================================
print("\nG. the renderer rules, asserted in the file - v12.01's lesson")
# ===========================================================================
ok("const chartBy = adsChartByResolve(ch, channel, view);" in js,
   "G1  /!\\ the card strip clamps the band reading")
ok("const by = adsChartByResolve(ch, channel, view);" in js,
   "G2  /!\\ and so does the chart - a disabled button is bypassable")
# /!\ ONE, not zero: the resolver's own read is the single place the stored
# setting is consulted. Asserted as 1 so a fourth consumer reaching past the
# clamp fails here rather than being absorbed into a count that looked right.
eq("G3  /!\\ exactly one raw read survives - inside the resolver",
   len(re.findall(r"=\s*adsChartBy\(channel, view\)", js)), 1)
ok("  const by = adsChartBy(channel, view);\n  return (by === 'campaign'" in js,
   "G3b ...and that one IS the resolver")

INJ = fn_flat("adsInjectChartBy")
ok("const bandWhy = adsBandWhy(ch);" in INJ, "G4  the control asks why")
ok("dis ? ' disabled'" in INJ, "G5  /!\\ and renders DISABLED rather than hidden")
ok("dis ? 'not-allowed'" in INJ, "G6  ...with the cursor to match")
ok("onclick=" in INJ and "dis ? ' disabled' : `" in INJ,
   "G7  /!\\ the onclick is STRIPPED, not left to be ignored")

ok("].concat(COLS.some(c => c.k === 'orders') ? [{" in js,
   "G8  /!\\ the Orders card is gated on the column registry")
COV = js[js.index("  const cov = document.getElementById(ch.host + '-cov');"):]
COV = COV[:COV.index("\n  }\n") + 4]
ok("typeof ch.brandless === 'function'" in COV,
   "G9  /!\\ the coverage line asks the view whether a brand can apply")
ok("} else if (brand) parts.push(brand);" in COV,
   "G10 ...and every other view is byte-identical")

ST = fn_flat("adsState")
ok("cfg.defaultSort" in ST, "G11 a view may open on its own column")
ok("|| 'spend'" in ST, "G12 /!\\ ...and every existing view still opens on spend")

# ===========================================================================
print("\nH. every registry a new source has to be in")
# ===========================================================================
for pat, label in [
    ("walmart_ad_daily:         'grp-walmart-ads',", "H1  the upload group map"),
    ("'dz-walmart-ad-daily':    'walmart_ad_daily',", "H2  the recent-uploads rail"),
    ("walmart_ad_daily:         { icon: '\\ud83d\\udcc6', label: 'Walmart Ads — Daily' },", "H3  the source chip"),
    ("walmart_ad_daily:        { label:'Walmart Ads — Daily',", "H4  upload history + coverage grid"),
    ("id=\"dz-walmart-ad-daily\"", "H5  the dropzone"),
    ("id=\"st-walmart-ad-daily\"", "H6  its status line"),
    ("id=\"last-walmart-ad-daily\"", "H7  its latest-data line"),
    ("handleWalmartAdDailyUpload(this)", "H8  its handler is wired"),
    ("id=\"wmpnl-ads-tab-daily\"", "H9  the sub-tab"),
    ("id=\"wmpnl-ads-view-daily\"", "H10 the area"),
    ("id=\"wmday-host\"", "H11 the host"),
    ("walmart_ad_daily:    'supabase_v12_03_walmart_ad_daily.sql',", "H12 the migration is named by the error"),
]:
    ok(pat in s, label, None if pat in s else pat)

# /!\ THE GLYPH IS ITS OWN (rule #2). The calendar must mean this feed and
# nothing else, anywhere in the app.
eq("H13 /!\\ the calendar glyph is used for this and nothing else",
   s.count(chr(0x1F4C6)), 2)   # the sub-tab button and the dropzone icon

# The SQL file exists and declares the same key the parser upserts on.
SQLP = os.path.join(ROOT, "supabase_v12_03_walmart_ad_daily.sql")
ok(os.path.exists(SQLP), "H14 the migration is in the repo")
sql = io.open(SQLP, encoding="utf-8").read()
ok("on walmart_ad_daily (date, region, account)" in sql,
   "H15 /!\\ and its unique index IS the parser's onConflict target")
for c in ("date", "region", "account"):
    ok(re.search(r"\n  %s\s+\S+\s+not null" % c, sql) is not None,
       "H16 /!\\ %s is NOT NULL, so the index is plain and upsert can target it" % c)
# /!\ No master_id -> MERGE_MASTER_ID_TABLES gains nothing. Audited (v11.90),
# and asserted so a later column cannot sneak one in unnoticed.
ok("master_id" not in sql.split("create table")[1].split(");")[0],
   "H17 /!\\ no master_id, so the merge registry is a no-op here")
ok("walmart_ad_daily" not in const_obj("MERGE_MASTER_ID_TABLES"),
   "H18 ...and it is correctly absent from the merge registry")

# ===========================================================================
print("\nI. the loader can actually read it")
# ===========================================================================
LOAD = fn_flat("_wmcLoad")
ok("orderBy || 'reporting_month'" in LOAD,
   "I1  /!\\ the order column is a parameter - this table has no reporting_month")
ok("'walmart_ad_daily',    walmartAdDailyCache,    force, 'date'" in js,
   "I2  ...and the daily loader passes its own")
ok("walmartAdCampaignCache, force)" in js,
   "I3  /!\\ the two existing callers are unchanged")
ok("let walmartAdDailyCache    = [];" in js, "I4  it has its own cache")
ok("walmartAdDailyCache = [];" in fn_flat("handleWalmartAdDailyUpload"),
   "I5  which the upload invalidates")

# ===========================================================================
print("\nK. RLS - the grants alone are not enough")
# ===========================================================================
# /!\ SHIPPED WITHOUT A POLICY, AND JASON'S FIRST UPLOAD FAILED WITH
#     new row violates row-level security policy for table "walmart_ad_daily"
# Supabase turns RLS ON for a new table by itself, and `authenticated` already
# holds the privileges from default grants - so the grants I wrote were the
# no-op half and the policy, the half that mattered, was missing. The EXACT
# message is documented inside supabase_v11_25_walmart_ads.sql, which I had
# open while writing this migration.
#
# Hard rule since v6.47: enable RLS + a policy + grants on EVERY new table.
ok("alter table walmart_ad_daily enable row level security;" in sql,
   "K1  /!\\ RLS is enabled")
ok("create policy walmart_ad_daily_authenticated_all" in sql,
   "K2  /!\\ ...and a policy exists, which is the half that was missing")
ok("for all to authenticated using (true) with check (true)" in sql,
   "K3  /!\\ with check (true) - an INSERT is refused without it")
ok("to authenticated" in sql and "to anon" not in sql,
   "K4  /!\\ written for `authenticated`: the app signs in, so that is the role")
ok("grant select, insert, update, delete on table walmart_ad_daily to authenticated;" in sql,
   "K5  the table grant")
ok("grant usage, select on sequence walmart_ad_daily_id_seq to authenticated;" in sql,
   "K6  /!\\ and the SEQUENCE grant - bigserial needs it to allocate an id")
ok("if not exists (" in sql and "from pg_policies" in sql,
   "K7  re-running the file is safe")

# ===========================================================================
print("\nJ. the chip agrees with CLAUDE.md")
# ===========================================================================
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "J1  both declare a version")
eq("J2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
