#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.75 - a coverage check means "we hold the period we should hold".

Jason, on a card whose own header read "thru Sat 2026-10-31 (1w ago)" over a
grid of green checks: "this data is ... out of date but still shows as
checks."

Two errors kept that mark green, and either alone was enough:

  1. the age was measured from the period's FIRST day, so a week_start of
     2026-10-26 - data running through Saturday 2026-10-31 - read as 14 days
     old instead of 9, and a reporting_month read a month early. The card
     line directly ABOVE the grid already measured from the Saturday, so one
     card carried two ages for one week, five days apart.
  2. the tolerance was TWO cycles wide and guessed from the NAME of the date
     column: "fresh within 14 days" for a weekly feed, and 400 days for
     digital_sales_tracker because its column is called `year`.

  * A  the real uploadGrain / uploadWeekEndOffset / uploadPeriodEnd /
       uploadDataThru over every registered source, including the two
       periods that are NOT dates.
  * B  the real uploadFreshDays: one cycle per grain, override honoured.
  * C  /!\ THE DEFECT REPRODUCED - the retired rule run beside the shipped
       one on the LIVE state Jason was looking at. Only feeds that are
       actually behind change mark.
  * D  the real uploadCoverageHtml: a behind region loses its check and shows
       its date, a current one keeps the check, a never-uploaded cell still
       shows the dash, and the tooltip says what the age was measured from.
  * E  static: one definition of the week end, the card sites converted, the
       offset declared only where the convention differs, and the chip
       agreeing with CLAUDE.md.
"""
import io, os, re, sys, json, subprocess

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


def nocomment(t):
    # LINE comments only. v11.63: stripping BLOCK comments from index.html
    # eats 824,674 characters, because a `/*` inside a string or a regex
    # literal pairs with a distant `*/`.
    return re.sub(r"(?m)^\s*//.*$", "", t)


def _bal(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ""
    while k < n:
        c = js[k]
        if c == "/" and k + 1 < n and js[k + 1] == "/":
            while k < n and js[k] != "\n":
                k += 1
            continue
        if c == "/" and k + 1 < n and js[k + 1] == "*":
            k = js.index("*/", k) + 2
            continue
        if c == "/" and prev in "(,=:[!&|?{};+-*%~^<>":
            k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == "[":
                    while k < n and js[k] != "]":
                        k += 2 if js[k] == "\\" else 1
                if js[k] == "/":
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = "x"
            continue
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = "x"
            continue
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise SystemExit("unbalanced at %d" % i)


def fn(name, kw="function"):
    pat = kw + " " + name + "("
    i = js.index(pat)
    head = js.index("{", i)
    j = i
    while j > 0 and js[j - 1] != "\n":
        j -= 1
    return js[j:head] + _bal(head)


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("{", i)] + _bal(js.index("{", i)) + ";"


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("v11.75 - the check means we hold the period we should hold")
print("=" * 68)

NC = nocomment(js)

# Sliced, never stubbed, so a default that moves fails this suite.
CORE = (const_obj("UH_SOURCES") + "\n"
        + fn("uploadGrain") + "\n"
        + fn("uploadWeekEndOffset") + "\n"
        + fn("uploadPeriodEnd") + "\n"
        + fn("uploadDataThru") + "\n"
        + fn("uploadFreshDays") + "\n")

# ---------------------------------------------------------------------------
print("\nA. the real grain and the real period END")
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "_v1175_a.js"), CORE + r"""
const grains = {};
for (const t of Object.keys(UH_SOURCES)) grains[t] = uploadGrain(t);
const out = {
  grains,
  // the three Amazon Sun->Sat feeds, and one that is not declared
  offAmz:   uploadWeekEndOffset('sku_economics'),
  offAmzEu: uploadWeekEndOffset('sku_economics_eu'),
  offAmzSt: uploadWeekEndOffset('amazon_sales_traffic'),
  offChewy: uploadWeekEndOffset('chewy_sales_weekly'),
  offNone:  uploadWeekEndOffset('no_such_table'),

  // THE WEEK Jason was looking at: a Monday week_start whose report runs
  // through the Saturday.
  wkAmz:    uploadDataThru('sku_economics', '2026-10-26'),
  wkAmzEu:  uploadDataThru('sku_economics_eu', '2026-10-26'),
  wkAmzNew: uploadDataThru('sku_economics', '2026-11-02'),
  wkChewy:  uploadDataThru('chewy_sales_weekly', '2026-09-28'),

  // a day grain is its own last day
  dayShop:  uploadDataThru('shopify_sales_daily', '2026-11-02'),
  dayAds:   uploadDataThru('amazon_ad_spend', '2026-10-29'),

  // a month runs to its own last day, including a short one and a leap one
  mSep:     uploadDataThru('amazon_query_performance_asin', '2026-09'),
  mOct:     uploadDataThru('walmart_ad_campaign', '2026-10'),
  mFeb26:   uploadPeriodEnd('2026-02', 'month'),
  mFeb28:   uploadPeriodEnd('2028-02', 'month'),
  mDec:     uploadPeriodEnd('2026-12', 'month'),
  mFromYmd: uploadPeriodEnd('2026-09-15', 'month'),

  // NOT dates: a fiscal week code and a bare year
  codeWm:   uploadDataThru('walmart_sales_weekly', '202639'),
  yearDst:  uploadDataThru('digital_sales_tracker', '2026'),

  // junk never throws and never invents a date
  nullIn:   uploadDataThru('sku_economics', null),
  blankIn:  uploadDataThru('sku_economics', ''),
  junkIn:   uploadDataThru('sku_economics', 'not-a-date'),
  numIn:    uploadPeriodEnd(20261026, 'week', 5),
  badGrain: uploadPeriodEnd('2026-10-26', 'quarter', 5),
};
console.log(JSON.stringify(out));
""")

eq("A1  week_start reads as a WEEK grain", A["grains"]["sku_economics"], "week")
eq("A2  reporting_month reads as a MONTH grain", A["grains"]["walmart_ad_campaign"], "month")
eq("A3  year reads as a YEAR grain", A["grains"]["digital_sales_tracker"], "year")
eq("A4  snapshot_date reads as a DAY grain", A["grains"]["fba_fee_preview"], "day")
eq("A5  walmart_calendar_week reads as a WEEK grain",
   A["grains"]["walmart_sales_weekly"], "week")
ok(set(A["grains"].values()) <= {"day", "week", "month", "year"},
   "A6  every registered source resolves to one of four grains",
   sorted(set(A["grains"].values())))
# v11.79 - amazon_storage_fees joined the registry. The count is pinned so
# a feed that lands WITHOUT a rail entry shows up here as a change.
# v12.03 - 24: walmart_ad_daily joined. /!\ Its dateField is a real DATE,
# so it resolves as a DAY grain and takes v11.75's 10-day daily tolerance -
# deliberately wider than one cycle, because a one-day tolerance would mark
# every daily feed late every single day.
eq("A7  24 sources registered", len(A["grains"]), 24)
eq("A7b /!\\ the new one resolves as a DAY, not a period code",
   A["grains"].get("walmart_ad_daily"), A["grains"].get("shopify_sales_daily"))

eq("A8  Amazon SKU Economics declares Mon+5", A["offAmz"], 5)
eq("A9  Amazon SKU Economics EU declares Mon+5", A["offAmzEu"], 5)
eq("A10 Amazon Sales & Traffic declares Mon+5", A["offAmzSt"], 5)
eq("A11 an undeclared weekly feed defaults to Mon+6", A["offChewy"], 6)
eq("A12 an unknown table defaults to Mon+6", A["offNone"], 6)

# /!\ This is the number Jason's card already printed above the grid.
eq("A13 2026-10-26 covers through Sat 2026-10-31", A["wkAmz"], "2026-10-31")
eq("A14 the EU card agrees with the US/CA one", A["wkAmzEu"], "2026-10-31")
eq("A15 2026-11-02 covers through Sat 2026-11-07", A["wkAmzNew"], "2026-11-07")
eq("A16 a Mon+6 weekly feed runs to the Sunday", A["wkChewy"], "2026-10-04")

eq("A17 a day grain ends on its own day", A["dayShop"], "2026-11-02")
eq("A18 ... and so does an ad day", A["dayAds"], "2026-10-29")

eq("A19 2026-09 runs through 2026-09-30", A["mSep"], "2026-09-30")
eq("A20 2026-10 runs through 2026-10-31", A["mOct"], "2026-10-31")
eq("A21 a non-leap February ends on the 28th", A["mFeb26"], "2026-02-28")
eq("A22 a LEAP February ends on the 29th", A["mFeb28"], "2028-02-29")
eq("A23 December rolls the year, not the month", A["mDec"], "2026-12-31")
eq("A24 a month grain ignores any day part", A["mFromYmd"], "2026-09-30")

# /!\ The whole reason the uploaded_at fallback survives.
eq("A25 a fiscal week CODE has no period end", A["codeWm"], None)
eq("A26 a bare YEAR has no period end", A["yearDst"], None)
ok(A["nullIn"] is None and A["blankIn"] is None and A["junkIn"] is None,
   "A27 null / blank / junk answer null rather than throwing",
   [A["nullIn"], A["blankIn"], A["junkIn"]])
eq("A28 a NUMBER is not read as a date", A["numIn"], None)
eq("A29 a grain nobody declares answers null", A["badGrain"], None)

# ---------------------------------------------------------------------------
print("\nB. the real uploadFreshDays - ONE cycle, not two")
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "_v1175_b.js"), CORE + r"""
const out = {};
for (const t of Object.keys(UH_SOURCES)) out[t] = uploadFreshDays(t);
out._override = (() => {
  UH_SOURCES.__probe = { dateField: 'week_start', freshDays: 3 };
  const v = uploadFreshDays('__probe');
  delete UH_SOURCES.__probe;
  return v;
})();
out._unknown = uploadFreshDays('no_such_table');
console.log(JSON.stringify(out));
""")

eq("B1  a WEEKLY feed is late one week after the week closes",
   B["sku_economics"], 7)
eq("B2  ... on every weekly source", B["sku_economics_eu"], 7)
eq("B3  a MONTHLY feed gets one month", B["walmart_ad_campaign"], 31)
eq("B4  a DAILY feed keeps 10 - these are hand uploads on a weekly rhythm",
   B["shopify_sales_daily"], 10)
eq("B5  a YEAR-keyed feed gets 45 against the UPLOAD date, not 400",
   B["digital_sales_tracker"], 45)
eq("B6  a per-source override still wins", B["_override"], 3)
eq("B7  an unknown table falls to the daily default", B["_unknown"], 10)
ok(max(B[k] for k in B if not k.startswith("_")) <= 45,
   "B8  no source is given more than 45 days of slack",
   max((B[k], k) for k in B if not k.startswith("_")))

# ---------------------------------------------------------------------------
print("\nC. /!\\ THE DEFECT REPRODUCED - the retired rule beside the shipped one")
# ---------------------------------------------------------------------------
# The LIVE state of every feed, read off the database on 2026-11-09 and
# pinned here. The clock is pinned with it, so this says the same thing
# tomorrow.
C = run_node(os.path.join(SP, "_v1175_c.js"), CORE + r"""
const TODAY = Date.parse('2026-11-09T00:00:00Z');

// ---- the PRE-v11.75 rule, exactly as it stood -------------------------
function oldFresh(table) {
  const src = UH_SOURCES[table] || {};
  if (src.freshDays != null) return Number(src.freshDays);
  const f = String(src.dateField || '');
  if (/month/i.test(f)) return 45;
  if (/^year$/i.test(f)) return 400;
  if (/week/i.test(f)) return 14;
  return 10;
}
const isDate = (v) => /^\d{4}-\d{2}(-\d{2})?$/.test(String(v || ''));
const oldAge = (d) => {
  if (!isDate(d)) return null;
  const t = Date.parse((String(d).length === 7 ? d + '-01' : d) + 'T00:00:00Z');
  return Number.isFinite(t) ? Math.floor((TODAY - t) / 86400000) : null;
};
function oldOk(table, latest, up) {
  const age = isDate(latest) ? oldAge(latest) : oldAge(up);
  return !!(latest && age != null && age <= oldFresh(table));
}

// ---- the SHIPPED rule --------------------------------------------------
const newAge = (d) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(d || ''))) return null;
  const t = Date.parse(String(d).slice(0, 10) + 'T00:00:00Z');
  return Number.isFinite(t) ? Math.floor((TODAY - t) / 86400000) : null;
};
function newOk(table, latest, up) {
  const end = uploadDataThru(table, latest);
  const age = end ? newAge(end) : newAge(up);
  return !!(latest && age != null && age <= uploadFreshDays(table));
}

// Live state, 2026-11-09. [table, region, latest period, max uploaded_at]
const LIVE = [
  ['sku_economics', 'US', '2026-11-02', '2026-11-09'],
  ['sku_economics', 'CA', '2026-11-02', '2026-11-09'],
  ['sku_economics_eu', 'DE', '2026-10-26', '2026-11-02'],
  ['sku_economics_eu', 'ES', '2026-10-26', '2026-11-02'],
  ['sku_economics_eu', 'FR', '2026-10-26', '2026-11-02'],
  ['sku_economics_eu', 'GB', '2026-10-26', '2026-11-02'],
  ['sku_economics_eu', 'IT', '2026-10-26', '2026-11-02'],
  ['sku_economics_eu', 'NL', '2026-10-26', '2026-11-02'],
  ['chewy_ad_spend', '', '2026-10-25', '2026-10-26'],
  ['amazon_ad_spend', 'US', '2026-10-29', '2026-10-29'],
  ['amazon_ad_spend', 'CA', '2026-10-29', '2026-10-29'],
  ['amazon_ad_spend', 'MX', '2026-10-27', '2026-10-29'],
  ['fba_fee_preview', 'US', '2026-11-02', '2026-11-02'],
  ['fba_fee_preview', 'CA', '2026-11-02', '2026-11-02'],
  ['fba_fee_preview', 'MX', '2026-11-02', '2026-11-02'],
  ['fba_inventory_snapshots', 'US', '2026-11-02', '2026-11-02'],
  ['fba_inventory_snapshots', 'CA', '2026-11-03', '2026-11-03'],
  ['fba_inventory_snapshots', 'EU/UK', '2026-11-02', '2026-11-02'],
  ['fba_shipment_summaries', 'US', '2026-10-27', '2026-11-02'],
  ['fba_shipment_summaries', 'CA', '2026-10-21', '2026-10-26'],
  ['walmart_sales_weekly', '', '202639', '2026-11-02'],
  ['shopify_sales_daily', '', '2026-11-09', '2026-11-09'],
  ['chewy_forecasts', '', '2026-11-02', '2026-11-02'],
  ['digital_sales_tracker', '', '2026', '2026-07-08'],
  ['chewy_rebates', '', '2026-10-07', '2026-10-12'],
  ['amazon_sales_traffic', 'US', '2026-11-02', '2026-11-09'],
  ['chewy_sales_weekly', '', '2026-09-28', '2026-10-08'],
  ['fba_shipments', 'US', '2026-10-27', '2026-11-02'],
  ['fba_shipments', 'CA', '2026-10-21', '2026-10-26'],
  ['amazon_ads_bulk_upload', 'US', '2026-09-21', '2026-09-21'],
  ['amazon_query_performance_asin', 'US', '2026-09', '2026-10-26'],
  ['walmart_ad_campaign', 'US', '2026-10', '2026-10-30'],
  ['walmart_ad_keyword', 'US', '2026-10', '2026-10-30'],
  ['amazon_sp_search_term', 'US', '2026-10', '2026-11-02'],
  ['amazon_sp_campaign_snapshot', 'US', '2026-08', '2026-09-20'],
];

const rows = LIVE.map(([t, r, latest, up]) => ({
  t, r, latest,
  old: oldOk(t, latest, up),
  nu:  newOk(t, latest, up),
  end: uploadDataThru(t, latest),
}));
console.log(JSON.stringify({
  rows,
  flips: rows.filter(x => x.old !== x.nu).map(x => x.t + '/' + x.r + ' ' + x.old + '->' + x.nu),
  oldChecks: rows.filter(x => x.old).length,
  newChecks: rows.filter(x => x.nu).length,
}));
""")

rows = {r["t"] + "/" + r["r"]: r for r in C["rows"]}

# /!\ Jason's card. A full week behind, and the old rule called it fresh.
ok(rows["sku_economics_eu/DE"]["old"] is True and rows["sku_economics_eu/DE"]["nu"] is False,
   "C1  EU SKU Economics: a full week behind, was a CHECK, now shows its date",
   rows["sku_economics_eu/DE"])
eq("C2  ... and the period it actually covers ends on the Saturday",
   rows["sku_economics_eu/DE"]["end"], "2026-10-31")
ok(all(rows["sku_economics_eu/" + r]["nu"] is False for r in ("DE", "ES", "FR", "GB", "IT", "NL")),
   "C3  every EU country moves, because every one is the same week behind")

# /!\ Fresh within 400 days because its column is called `year`.
ok(rows["digital_sales_tracker/"]["old"] is True and rows["digital_sales_tracker/"]["nu"] is False,
   "C4  the Digital Sales tracker: last uploaded 2026-07-08, was a CHECK",
   rows["digital_sales_tracker/"])

# The feed Jason uploaded today keeps its check, which is the control case.
ok(rows["sku_economics/US"]["nu"] is True and rows["sku_economics/CA"]["nu"] is True,
   "C5  the week uploaded today keeps its check")
eq("C6  ... covering through Saturday 2026-11-07",
   rows["sku_economics/US"]["end"], "2026-11-07")
ok(rows["amazon_sales_traffic/US"]["nu"] is True,
   "C7  Sales & Traffic, uploaded the same day, keeps its check")

# /!\ The claim that matters: nothing CURRENT went orange.
eq("C8  exactly SEVEN marks change", len(C["flips"]), 7)
ok(all(f.endswith("true->false") for f in C["flips"]),
   "C9  every change is a check LOST, never one invented", C["flips"])
ok(all(f.split("/")[0] in ("sku_economics_eu", "digital_sales_tracker") for f in C["flips"]),
   "C10 and only on the two feeds that are actually behind", C["flips"])
eq("C11 checks before", C["oldChecks"], 22)
eq("C12 checks after", C["newChecks"], 15)

# Every mark that did NOT move is pinned, so this is a measurement rather
# than a count. A monthly feed holding last month stays fresh; one holding
# the month before does not.
ok(rows["walmart_ad_campaign/US"]["nu"] is True,
   "C13 a monthly feed holding October is fresh on 2026-11-09")
ok(rows["amazon_query_performance_asin/US"]["nu"] is False,
   "C14 ... and one holding September is not")
eq("C15 September runs through 2026-09-30, not 2026-09-01",
   rows["amazon_query_performance_asin/US"]["end"], "2026-09-30")
ok(rows["amazon_ad_spend/US"]["old"] is False and rows["amazon_ad_spend/US"]["nu"] is False,
   "C16 a daily feed 11 days behind was orange and stays orange")
ok(rows["shopify_sales_daily/"]["nu"] is True,
   "C17 a daily feed loaded today stays a check")
ok(rows["walmart_sales_weekly/"]["nu"] is True,
   "C18 a fiscal-week CODE still answers from its upload date")

# ---------------------------------------------------------------------------
print("\nD. the real uploadCoverageHtml")
# ---------------------------------------------------------------------------
D = run_node(os.path.join(SP, "_v1175_d.js"), CORE + "\n"
             + fn("uploadCoverageAxes") + "\n" + fn("esc2") + "\n" + r"""
// Pinned to the day Jason reported it. LOCAL midnight, because ageOf parses
// its dates as local too - a UTC pin against a local parse reads a day short.
const _now = new Date('2026-11-09T00:00:00').getTime();
Date.now = () => _now;

""" + fn("uploadAgeDays") + chr(10) + fn("uploadCoverageHtml") + r"""

// EU, exactly as the rollup returns it: one week behind on every country.
const eu = {
  err: null, unmapped: false,
  regions: ['DE', 'GB'], brands: ['Doggijuana', 'Meowijuana'],
  byRegion:      { DE: '2026-10-26', GB: '2026-10-26' },
  byRegionFresh: { DE: '2026-11-02', GB: '2026-11-02' },
  cells: { 'DE|Doggijuana': '2026-10-26', 'DE|Meowijuana': '2026-10-26',
           'GB|Doggijuana': '2026-10-26' },
  fresh: {},
};
// US/CA after today's upload.
const usca = {
  err: null, unmapped: false,
  regions: ['CA', 'US'], brands: ['Doggijuana', 'Meowijuana'],
  byRegion:      { CA: '2026-11-02', US: '2026-11-02' },
  byRegionFresh: { CA: '2026-11-09', US: '2026-11-09' },
  cells: { 'CA|Doggijuana': '2026-11-02', 'CA|Meowijuana': '2026-11-02',
           'US|Doggijuana': '2026-11-02', 'US|Meowijuana': '2026-11-02' },
  fresh: {},
};
// A region that has never been uploaded at all keeps its dash.
const never = {
  err: null, unmapped: false,
  regions: ['DE', 'MX'], brands: ['Meowijuana'],
  byRegion:      { DE: '2026-10-26' },
  byRegionFresh: { DE: '2026-11-02' },
  cells: { 'DE|Meowijuana': '2026-10-26' }, fresh: {},
};
const dst = {
  err: null, unmapped: false, regions: [], brands: ['Meow'],
  byRegion: { '': '2026' }, byRegionFresh: { '': '2026-07-08' },
  cells: { '|Meow': '2026' }, fresh: {},
};

const h = {
  eu:    uploadCoverageHtml('sku_economics_eu', eu),
  usca:  uploadCoverageHtml('sku_economics', usca),
  never: uploadCoverageHtml('sku_economics_eu', never),
  dst:   uploadCoverageHtml('digital_sales_tracker', dst),
};
const CHECK = '&#10003;';
const DASH  = '&#8212;';
console.log(JSON.stringify({
  euChecks:   (h.eu.match(/&#10003;/g) || []).length,
  euDates:    (h.eu.match(/>2026-10-26</g) || []).length,
  euOrange:   (h.eu.match(/var\(--orange\)/g) || []).length,
  euGreen:    (h.eu.match(/var\(--sp-green\)/g) || []).length,
  euTip:      (h.eu.match(/title="([^"]*)"/) || [])[1] || '',
  uscaChecks: (h.usca.match(/&#10003;/g) || []).length,
  uscaGreen:  (h.usca.match(/var\(--sp-green\)/g) || []).length,
  uscaTip:    (h.usca.match(/title="([^"]*)"/) || [])[1] || '',
  neverDash:  (h.never.match(/&#8212;/g) || []).length,
  neverTip:   /Nothing has ever been uploaded/.test(h.never),
  dstChecks:  (h.dst.match(/&#10003;/g) || []).length,
  dstCell:    />2026</.test(h.dst),
  dstTip:     (h.dst.match(/title="([^"]*)"/) || [])[1] || '',
}));
""")

eq("D1  the EU grid draws NO checks", D["euChecks"], 0)
eq("D2  ... it shows the week it actually holds, once per cell", D["euDates"], 4)
eq("D3  ... in the not-fresh colour", D["euOrange"], 4)
eq("D4  ... and nothing green survives", D["euGreen"], 0)
ok("covers through 2026-10-31" in D["euTip"],
   "D5  the tooltip states the LAST DAY the period covers", D["euTip"])
ok("(9 days ago)" in D["euTip"],
   "D6  ... and the age measured from it, not the 14 the old rule read",
   D["euTip"])
ok("late after 7 days" in D["euTip"],
   "D7  ... and the tolerance it was judged against", D["euTip"])

eq("D8  the US/CA grid still draws a check per cell", D["uscaChecks"], 4)
eq("D9  ... in green", D["uscaGreen"], 4)
ok("covers through 2026-11-07" in D["uscaTip"] and "(2 days ago)" in D["uscaTip"],
   "D10 ... measured from the same Saturday the card line prints",
   D["uscaTip"])

eq("D11 a region never uploaded still renders the dash", D["neverDash"], 1)
ok(D["neverTip"], "D12 ... with its own sentence, not a staleness one")

eq("D13 the Digital Sales tracker loses its check", D["dstChecks"], 0)
ok(D["dstCell"], "D14 ... and still shows the period it holds")
ok("uploaded 2026-07-08" in D["dstTip"] and "late after 45 days" in D["dstTip"],
   "D15 ... with the age taken from the UPLOAD, because a year has no end",
   D["dstTip"])
# Caught in a browser, not by an assertion I had written: the age sat
# directly after the period, so "124 days ago" read as a fact about the
# YEAR 2026 rather than about the upload. It follows what it measures now.
ok("2026 " + chr(0x00b7) + " uploaded 2026-07-08 (124 days ago)" in D["dstTip"],
   "D15b the age follows what it was MEASURED from", D["dstTip"])
ok("2026-10-31 (9 days ago)" in D["euTip"],
   "D15c ... which for a dated period is the period end", D["euTip"])
ok("covers through" not in D["dstTip"],
   "D16 ... and it never claims a period end it cannot compute", D["dstTip"])

# ---------------------------------------------------------------------------
print("\nE. static")
# ---------------------------------------------------------------------------
ok("const endOfWeek = (mondayStr" not in js,
   "E1  the local endOfWeek is GONE, not left beside the shared helper")
ok(len(re.findall(r"endOfWeek\(", NC)) == 0,
   "E2  ... and nothing calls it any more",
   re.findall(r".{40}endOfWeek\(.{20}", NC))
ok("endOfWeek(wk, 5)" in js,
   "E3  the retired call survives in a COMMENT, so grepping it still lands "
   "on the explanation")

thru = re.findall(r"uploadDataThru\(", NC)
ok(len(thru) >= 4,
   "E4  the card line and the grid both read the shared definition", len(thru))
for site in ("uploadDataThru('sku_economics', wk)",
             "uploadDataThru('sku_economics_eu', wk)",
             "uploadDataThru('sku_economics', amzAll[0])"):
    ok(site in js, "E5  converted: %s" % site)

offs = re.findall(r"weekEndOffset:\s*(\d+)", js)
eq("E6  exactly three sources declare a week-end offset", len(offs), 3)
ok(set(offs) == {"5"}, "E7  ... and all three declare the Sun-Sat convention", offs)
REG = const_obj("UH_SOURCES")
for t in ("sku_economics:", "sku_economics_eu:", "amazon_sales_traffic:"):
    i = REG.index(chr(10) + "  " + t)
    ok("weekEndOffset:5" in REG[i:i + 400], "E8  declared on %s" % t.rstrip(":"))

fresh_fn = fn("uploadFreshDays")
ok("400" not in fresh_fn and "return 14;" not in fresh_fn,
   "E9  the two-cycle numbers are gone from the tolerance", fresh_fn)
ok(fresh_fn.count("uploadGrain(table)") == 1,
   "E10 the tolerance reads the ONE grain helper, not a second sniff")
ok("src.freshDays" in fresh_fn,
   "E11 the per-source override is kept")

html_fn = fn("uploadCoverageHtml")
ok("isDate" not in html_fn,
   "E12 the old date sniff is gone from the cell, not left shadowing the new rule")
ok(html_fn.count("uploadDataThru(table, d)") == 1,
   "E13 the cell resolves the period end exactly once")
ok("age <= fresh" in html_fn,
   "E14 the mark is still one comparison, in one place")

# v11.63: the chip and CLAUDE.md's current-version line must AGREE.
doc = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", newline="").read()
chip = re.findall(r">v(\d+\.\d+) " + chr(0x00b7) + r" ([\d-]+)<", s)
eq("E15 exactly one version chip", len(chip), 1)
docv = re.search(r"current version \*\*v(\d+\.\d+)\*\*", doc)
ok(docv is not None, "E16 CLAUDE.md names a current version")
eq("E17 the chip agrees with CLAUDE.md", chip[0][0], docv.group(1) if docv else None)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
