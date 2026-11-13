#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.37 - one set of date windows, and the scorecards leave the picker.

Jason: "units sold doesn't have the same date windows as other charts" ...
"also why are the scorecards in the product picker? if i hide the product
picker it hides the scorecards"

/!\ SIX PICKERS HAD BEEN HAND-WRITTEN SEPARATELY AND HAD ALREADY DRIFTED -
17 / 16 / 11 / 10 / 10 / 6 keys, two of them spelling `this-month` where the
others say `mtd`, and Units Sold using '0' for what everyone else calls
'all'. This suite is the registry's enforcement: a seventh copy, or a drift
in an existing one, fails the build.
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
        print("  FAIL  %s%s" % (label, ("  got: %s" % extra) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def const_src(name):
    i = js.index("const " + name + " = ")
    close = "];" if js.startswith("const " + name + " = [", i) else "};"
    return js[i:js.index(close, i) + 2]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


REG = const_src("PNL_PERIODS")
KEYS = re.findall(r"v: '([^']*)'", REG)

print("\n" + "=" * 70)
print("  v12.37  one set of date windows")
print("=" * 70)

# ===========================================================================
print("\nA. the registry")
# ===========================================================================
eq("A1  sixteen windows", len(KEYS), 16)
ok(KEYS == list(dict.fromkeys(KEYS)), "A2  no key declared twice")
ok(KEYS[-2:] == ["all", "custom"],
   "A3  /!\\ All time sits just before Custom range, as the v10.13 ordering "
   "rule already required of four of them", KEYS[-2:])
ok("this-month" not in KEYS,
   "A4  /!\\ `this-month` is NOT a window - it was Shopify's and Walmart's "
   "own spelling of `mtd`, one window under two names (rule 3a)")
ok("'this-month': 'mtd'" in js,
   "A5  ...it is an ALIAS, so a saved view holding it still resolves")
ok("'0': 'all'" in js,
   "A6  ...and so is Units Sold's old '0'")

# ===========================================================================
print("\nB. /!\\ EVERY PICKER OFFERS THE SAME WINDOWS")
# ===========================================================================
# This is the whole point. A seventh hand-written list fails here.
STATIC = ['pnl-period', 'spnl-period', 'wmpnl-period', 'chpnl-period', 'salesPeriod']
for sid in STATIC:
    i = s.index('id="%s"' % sid)
    blk = s[i:s.index('</select>', i)]
    vals = re.findall(r'<option value="([^"]*)"', blk)
    # pnl-period carries one extra, unreachable key (v7.25 dropped its option
    # but kept the code path), so it is allowed to be a superset of nothing.
    eq("B-%s  offers exactly the registry's windows" % sid, vals, KEYS)
    sel = re.findall(r'<option value="([^"]*)" selected', blk)
    ok(len(sel) <= 1, "B-%s  at most one default" % sid, sel)

# the sixth is GENERATED from the registry, which is stronger than matching it
seo = s[s.index("seo-tr-period"):s.index("seo-tr-custom-wrap")]
ok("pnlPeriodOptionsHtml('90')" in seo,
   "B-seo     /!\\ the one JS-built picker takes the registry's generator")
ok("<option value=" not in seo, "B-seo2    ...and writes no option of its own")
ok(js.count("function pnlPeriodOptionsHtml") == 1, "B1  one generator")

# ===========================================================================
print("\nC. /!\\ ONE RESOLVER - the week/month arithmetic existed FIVE times")
# ===========================================================================
for fname, feed in (("getShopifyPnlDateRange", "shopifyPnlData"),
                    ("getWalmartPnlDateRange", "walmartPnlData"),
                    ("getSalesPeriodDates",    "_salesAllTimeRows()")):
    body = fn_flat(fname)
    ok("computePnlDateRange(" in body, "C-%s goes through it" % fname)
    ok("allRows: " + feed in body,
       "C-%s /!\\ hands it ITS OWN feed, so all-time is that feed's floor "
       "and not sku_economics'" % fname)
    for gone in ("today.getMonth() - 1", "getFullYear(), 0, 1", "setDate(today.getDate() - parseInt"):
        ok(gone not in body,
           "C-%s  no copy of the arithmetic left: %s" % (fname, gone))

SEO = fn_flat("seoTrWindow")
ok("computePnlDateRange(" in SEO, "C-seo    the SEO page too, for the calendar windows")
ok("new Date(2000, 0, 1)" in SEO,
   "C-seo2   /!\\ ...keeping its documented exception: all-time floors before "
   "any GA4 data can exist, so an over-wide floor cannot overstate the record")
ok("- (parseInt(v, 10) || 90) + 1" in SEO,
   "C-seo3   /!\\ ...and its INCLUSIVE rolling window, which GA4's own day "
   "counts are")

# ===========================================================================
print("\nD. an unrecognised key is not an Invalid Date")
# ===========================================================================
CP = fn_flat("computePnlDateRange")
D = run_node(os.path.join(SP, "_v1237_d.js"),
             fn_flat("pnlPeriodKey") + "\n" + const_src("PNL_PERIOD_ALIAS") + "\n"
             + "function pnlAllTimeFrom(){ return '2024-01-01'; }\n"
             + "const pnlData = [];\n" + CP + r"""
const RealDate = Date;
const FIXED = new RealDate(2026, 10, 13);
globalThis.Date = class extends RealDate {
  constructor(...a) { if (!a.length) return new RealDate(FIXED); return new RealDate(...a); }
  static now() { return FIXED.getTime(); }
};
const warn = []; console.warn = (...a) => warn.push(a.join(' '));
const out = {};
for (const k of ['30', 'mtd', 'last-month', 'ytd', 'qtd', 'wtd', 'last-week'])
  out[k] = computePnlDateRange(k);
out.junk = computePnlDateRange('nonsense-value');
out.mtdViaAlias = computePnlDateRange(pnlPeriodKey('this-month'));
out.warned = warn.length;
console.log(JSON.stringify(out));
""")
eq("D1  a rolling window still counts back from today", D["30"]["from"], "2026-10-14")
eq("D2  month-to-date starts on the 1st", D["mtd"]["from"], "2026-11-01")
eq("D3  /!\\ and `this-month` resolves to exactly the same window",
   D["mtdViaAlias"], D["mtd"])
eq("D4  last month is the WHOLE previous month",
   [D["last-month"]["from"], D["last-month"]["to"]], ["2026-10-01", "2026-10-31"])
eq("D5  quarter-to-date", D["qtd"]["from"], "2026-10-01")
eq("D6  week-to-date starts Sunday", D["wtd"]["from"], "2026-11-08")
ok(D["junk"] and D["junk"]["from"] == "2026-10-14",
   "D7  /!\\ AN UNRECOGNISED KEY FALLS BACK TO 30 DAYS rather than becoming "
   "an Invalid Date - toISOString() THREW out of the resolver before, taking "
   "the whole render with it", D["junk"])
ok(D["warned"] >= 1, "D8  ...and says so, so a stale saved view is findable")

# ===========================================================================
print("\nE. the Units Sold page speaks the same vocabulary")
# ===========================================================================
SALES = fn_flat("getSalesPeriodDates")
ok("pnlPeriodKey(" in SALES, "E1  it resolves the key through the registry")
ok("parseLocalDate" in SALES,
   "E2  /!\\ ...and parses LOCALLY - a UTC parse moves both ends of the "
   "window by a day west of Greenwich (the v9.71 rule this page carries)")
ok("return { from: d(r && r.from), to: d(r && r.to) || now, allTime:" in SALES,
   "E3  it still returns Date objects, which is what its twenty callers "
   "compare against")
LBL = fn_flat("salesPeriodLabel")
ok("pnlPeriodLabelOf(v)" in LBL, "E4  one label builder, reading the registry")
ok(js.count("function salesPeriodLabel") == 1
   and js.count("salesPeriodLabel()") >= 4,
   "E5  /!\\ there were FOUR label builders on this page, three hardcoding "
   "`Last ${p} days` - which prints \"Last mtd days\" the moment the picker "
   "offers anything but a rolling window")
# /!\ COMMENTS STRIPPED. The comment explaining what was removed quotes it
# verbatim, which is the point of the comment (the v12.15 A7 trap).
_nc = re.sub(r"(?m)//.*$", " ", re.sub(r"/\*[\s\S]*?\*/", " ", js))
ok("`Last ${p} days`" not in _nc,
   "E6  ...and not one of them survives")

# ===========================================================================
print("\nF. the scorecards are not part of the picker")
# ===========================================================================
_cards = s.index('id="salesSummaryCards"')
_area  = s.index('id="sales-picker-area"')
ok(_cards < _area,
   "F1  /!\\ the scorecards render ABOVE sales-picker-area, so hiding the "
   "picker no longer takes the page's headline numbers with it")
_bar = s.index('id="sales-picker-bar"')
ok(_cards < _bar, "F2  ...and above the bar that collapses it")
COLL = fn_flat("applySalesPickerCollapseState")
ok("salesSummaryCards" not in COLL,
   "F3  the collapse handler does not touch them")
ok("Click to hide the product table" in s,
   "F4  and the button no longer promises to hide the cards")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
