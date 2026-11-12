#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.10 - a MONTH-split export is refused by the day-grain uploader.

Jason: "also the taco isn't populating for walmart".

The card was right and the data was wrong. Read off the live table the moment
he said it:

    2026-03-01 .. 2026-10-01   ONE row per campaign per MONTH, on the 1st
    2026-11-01                 $1,664.67  = the whole Nov 1-10 period
    2026-11-04 .. 2026-11-10   $1,179.44  = the real daily rows

/!\ SO NOVEMBER WAS DOUBLE-COUNTED BY $1,179.44 - the 11-01 row is a Nov 1-10
aggregate and the daily rows repeat seven of those ten days. Nothing refused
it, because every row DID carry a date. Just not a day.

Ad Center's Custom builder offers Date (Day) and Date (Month), both produce a
Date column, and both parse. The only thing that can tell them apart is the
file's own preamble: "Period Requested: Oct 01, 2026 - Oct 31, 2026".
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


def line_of(pat):
    for ln in js.split("\n"):
        if pat in ln:
            return ln
    raise SystemExit("not found: " + pat)


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("\n};", i) + 3]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.10  a month split is not daily data")
print("=" * 70)

HDR = ("Date,Campaign Type Name,Campaign Name,Impressions,Clicks,Ad Spend,CTR,"
       "Total Units Sold - 14 Day,Orders - 14 Day,Total Sales Rev. - 14 Day,"
       "In-store Attributed Sales  - 14 Days,New-to-Brand Orders - 14 Days,"
       "New-to-Brand Sales - 14 Days")
ROW = ('%s,Sponsored Products (Auto),%s,"1,165,041",3303,$ 2032.00,0.3%%,'
       '840,791,$ 5898.00,$ 259.00,719,$ 5378.00')
CAMPS = ["SP - AUTO - A", "SP - AUTO - B", "SP - KW - C", "SBV - D", "SP - E"]

# The real shape that landed: a whole month on the 1st.
MONTH = "\n".join(['"Period Requested: Oct 01, 2026 - Oct 31, 2026 "', HDR]
                  + [ROW % ("01-Oct-26", c) for c in CAMPS])
# /!\ A LEGITIMATE ONE-DAY PULL. A naive "every date is the 1st" rule would
# refuse this, and it is a perfectly good file.
ONEDAY = "\n".join(['"Period Requested: Oct 01, 2026 - Oct 01, 2026 "', HDR,
                    ROW % ("01-Oct-26", CAMPS[0])])
# No preamble: the check cannot run, and that must not be an error.
NOPRE = "\n".join([HDR, ROW % ("01-Oct-26", CAMPS[0])])
# A real week, which must sail through.
WEEK = "\n".join(['"Period Requested: Nov 04, 2026 - Nov 10, 2026 "', HDR]
                 + [ROW % ("%02d-Nov-26" % d, CAMPS[0]) for d in range(4, 11)])
# A HALF-COVERED window is accepted: holes are a coverage question, not a
# grain one, and the TACoS card is what reports those (v12.08).
HALF = "\n".join(['"Period Requested: Nov 01, 2026 - Nov 10, 2026 "', HDR]
                 + [ROW % ("%02d-Nov-26" % d, CAMPS[0]) for d in range(4, 11)])

PIECES = "\n".join([
    fn_flat("parseDelimited"), line_of("function parseCSV(line)"),
    line_of("function clean(s)"), line_of("const hdrNorm ="),
    fn_flat("_wmcNum"), line_of("function _wmcInt(v)"), fn_flat("_wmcCi"),
    fn_flat("_wmcHeaderIdx"), fn_flat("_wmcAttrCol"), fn_flat("_wmcPeriodRequested"),
    const_obj("_WMC_SQL"), fn_flat("_wmcTableErr"),
    fn_flat("parseLocalDate"), fn_flat("fmtLocalYMD"), fn_flat("adsParseDate"),
    fn_flat("adsAdvertiserToBrand"), fn_flat("parseWalmartAdCampaignDaily"),
])

DRIVER = r"""
'use strict';
__PIECES__
const written = [];
async function getSB() {
  return { from: () => ({ upsert: (r) => { written.push(...r); return Promise.resolve({ error: null }); } }) };
}
const go = async (txt) => {
  written.length = 0;
  try { const r = await parseWalmartAdCampaignDaily(txt, 'acct', 'US'); return { r }; }
  catch (e) { return { threw: e.message }; }
};
(async () => {
  const out = {
    month:  await go(__MONTH__),
    oneday: await go(__ONEDAY__),
    nopre:  await go(__NOPRE__),
    week:   await go(__WEEK__),
    half:   await go(__HALF__),
  };
  // The preamble reader, on its own.
  out.pr   = _wmcPeriodRequested(['"Period Requested: Oct 01, 2026 - Oct 31, 2026 "', 'Date,X']);
  out.prNo = _wmcPeriodRequested(['Date,X', 'a,b']);
  console.log(JSON.stringify(out));
})();
"""

A = run_node(os.path.join(SP, "_v1210_a.js"),
             DRIVER.replace("__PIECES__", PIECES)
                   .replace("__MONTH__", json.dumps(MONTH))
                   .replace("__ONEDAY__", json.dumps(ONEDAY))
                   .replace("__NOPRE__", json.dumps(NOPRE))
                   .replace("__WEEK__", json.dumps(WEEK))
                   .replace("__HALF__", json.dumps(HALF)))

# ===========================================================================
print("\nA. the preamble is read")
# ===========================================================================
eq("A1  the stated window comes off the preamble",
   A["pr"], {"from": "2026-10-01", "to": "2026-10-31"})
eq("A2  /!\\ and a file without one answers null rather than throwing",
   A["prNo"], None)

# ===========================================================================
print("\nB. THE DEFECT REFUSED")
# ===========================================================================
why = A["month"].get("threw") or ""
ok(A["month"].get("r") is None, "B1  /!\\ a MONTH split is refused")
ok("MONTH split" in why, "B2  ...named as what it is", why[:70])
ok("31 days" in why and "1 distinct date" in why,
   "B3  /!\\ with the window it claims and the dates it holds", why[:110])
ok("all on the 1st" in why, "B4  ...and the tell")
ok("Set Split to Date (Day)" in why, "B5  /!\\ and the fix, in the console's own words")
# /!\ THE CONSEQUENCE IS NAMED. This is not a tidiness refusal: the two grains
# land in the SAME table on different keys, so a month row and the daily rows
# inside it both count.
ok("double-count" in why, "B6  /!\\ and WHY it matters - the two grains overlap")

# ===========================================================================
print("\nC. what it must NOT refuse")
# ===========================================================================
# /!\ A naive "every date is the 1st" rule breaks this, and it is a good file.
eq("C1  /!\\ a legitimate ONE-DAY pull is accepted", A["oneday"]["r"]["rows"], 1)
eq("C2  ...and reports one day", A["oneday"]["r"]["days"], 1)
eq("C3  /!\\ a file with no preamble is accepted - the check simply cannot run",
   A["nopre"]["r"]["rows"], 1)
eq("C4  a real week sails through", A["week"]["r"]["rows"], 7)
eq("C5  ...with its seven days", A["week"]["r"]["days"], 7)
# /!\ A WINDOW WITH HOLES IS A COVERAGE QUESTION, NOT A GRAIN ONE - 7 of 10
# days is a thin pull, and v12.08's TACoS guard is what reports that.
eq("C6  /!\\ 7 days of a 10-day window is NOT treated as a month split",
   A["half"]["r"]["rows"], 7)

# ===========================================================================
print("\nD. the day count reaches the operator")
# ===========================================================================
PAR = fn_flat("parseWalmartAdCampaignDaily")
ok("days: days.length," in PAR, "D1  the result carries the distinct-day count")
HAND = fn_flat("handleWalmartAdCampaignDailyUpload")
ok("days += (r.days || 0);" in HAND, "D2  the handler totals it")
ok("${days} day${days === 1 ? '' : 's'}" in HAND,
   "D3  /!\\ and the status line says how many DAYS landed, not just rows - "
   "which is the number that would have shown this at upload time")

# /!\ The guard runs BEFORE the write. A refusal after the upsert would have
# left the rows in place.
ok(PAR.index("MONTH split") < PAR.index("const sb = await getSB();"),
   "D4  /!\\ it refuses BEFORE anything is written")

# ===========================================================================
print("\nE. the threshold")
# ===========================================================================
ok("span >= 3" in PAR,
   "E1  /!\\ a window under three days cannot be judged, so it is not")
ok("Math.max(2, span / 3)" in PAR,
   "E2  under a third of the window is not a day split")

print("\nF. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "F1  both declare a version")
eq("F2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
