#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.12 - my month-split guard refused a real day split.

Jason dropped two files at once. v12.10's guard was RIGHT about one and WRONG
about the other, and because one throw aborted the batch, NEITHER loaded.

    CustomReport_11_12_2026.csv        30 rows,   9 dates, ALL on the 1st
                                       -> a month split. Correctly refused.
    CustomReport_11_12_2026 (1).csv   217 rows, 100 dates, 25-Mar .. 02-Jul
                                       -> a real DAY split. WRONGLY refused.

/!\ THE RATIO WAS THE WRONG TEST. v12.10 compared the distinct-date count
against the window the file SAYS it covers - but "Period Requested" is the
range the operator ASKED for, not the range that has data. Those campaigns did
not exist for most of Sep 2025 - Nov 2026, so 100 days out of a claimed 436 is
a perfectly good day split, and 23% tripped a 33% threshold.

Sparseness is normal. Month-starts are not.
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
print("  v12.12  sparseness is normal; month-starts are not")
print("=" * 70)

HDR = ("Date,Campaign Type Name,Campaign Name,Impressions,Clicks,Ad Spend,CTR,"
       "Total Units Sold - 14 Day,Orders - 14 Day,Total Sales Rev. - 14 Day,"
       "In-store Attributed Sales  - 14 Days,New-to-Brand Orders - 14 Days,"
       "New-to-Brand Sales - 14 Days")
ROW = ('%s,Sponsored Products (Auto),%s,"1,165",33,$ 20.32,0.3%%,'
       '8,7,$ 58.98,$ 2.59,7,$ 53.78')
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]

# /!\ THE REGRESSION. A real day split over a window far longer than the data:
# a long "Period Requested", 100 distinct dates, none of them a month-start.
# This is the shape v12.10 refused.
SPARSE = "\n".join(['"Period Requested: Sep 01, 2025 - Nov 10, 2026 "', HDR]
                   + [ROW % ("%02d-Apr-26" % d, "SP - A") for d in range(2, 31)]
                   + [ROW % ("%02d-May-26" % d, "SP - A") for d in range(2, 31)])
# The month split that must still be refused.
MONTH = "\n".join(['"Period Requested: Sep 01, 2025 - Nov 10, 2026 "', HDR]
                  + [ROW % ("01-%s-26" % m, "SP - A") for m in MON])
# A lone 1st across a month-long window: still a month split.
LONE = "\n".join(['"Period Requested: Oct 01, 2026 - Oct 31, 2026 "', HDR,
                  ROW % ("01-Oct-26", "SP - A")])
# /!\ A lone 1st across a ONE-DAY window is a legitimate pull of the 1st.
ONEDAY = "\n".join(['"Period Requested: Oct 01, 2026 - Oct 01, 2026 "', HDR,
                    ROW % ("01-Oct-26", "SP - A")])
# A day split that HAPPENS to include some 1sts, among other days.
MIXED = "\n".join(['"Period Requested: Sep 01, 2026 - Nov 10, 2026 "', HDR]
                  + [ROW % (d, "SP - A") for d in
                     ["01-Sep-26", "15-Sep-26", "01-Oct-26", "20-Oct-26", "01-Nov-26"]])

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
  console.log(JSON.stringify({
    sparse: await go(__SPARSE__),
    month:  await go(__MONTH__),
    lone:   await go(__LONE__),
    oneday: await go(__ONEDAY__),
    mixed:  await go(__MIXED__),
  }));
})();
"""

A = run_node(os.path.join(SP, "_v1212_a.js"),
             DRIVER.replace("__PIECES__", PIECES)
                   .replace("__SPARSE__", json.dumps(SPARSE))
                   .replace("__MONTH__", json.dumps(MONTH))
                   .replace("__LONE__", json.dumps(LONE))
                   .replace("__ONEDAY__", json.dumps(ONEDAY))
                   .replace("__MIXED__", json.dumps(MIXED)))

# ===========================================================================
print("\nA. THE REGRESSION - a real day split over a long window")
# ===========================================================================
ok(A["sparse"].get("r") is not None,
   "A1  /!\\ 58 dates inside a 436-day window is ACCEPTED",
   A["sparse"].get("threw"))
eq("A2  ...all of them", A["sparse"]["r"]["days"], 58)
# /!\ THE POINT: 58 of 436 is 13% - far under v12.10's one-third threshold,
# and a perfectly good file. Campaigns do not exist for every day of a window.
ok(A["sparse"]["r"]["days"] / 436 < 0.33,
   "A3  /!\\ and it is well under the ratio that used to refuse it")

print("\nB. the month split is still refused")
why = A["month"].get("threw") or ""
ok(A["month"].get("r") is None, "B1  /!\\ every date a month-start is refused")
ok("the 1st of a month" in why, "B2  ...named as the tell", why[:80])
ok("11 distinct dates" in why, "B3  with the count")
ok("Set Split to Date (Day)" in why, "B4  and the fix")
ok("double-count" in why, "B5  and the consequence")

print("\nC. the ambiguous lone 1st")
# One date, the 1st - which is BOTH what a month split of October looks like
# and what a legitimate single-day pull of the 1st looks like. The window the
# file claims is the only thing that separates them.
ok(A["lone"].get("r") is None,
   "C1  /!\\ a lone 1st across a 31-day window is a month split",
   A["lone"].get("threw"))
ok("one date, the 1st" in (A["lone"].get("threw") or ""),
   "C2  ...and says so in those terms")
eq("C3  /!\\ but a lone 1st across a ONE-DAY window is a real pull",
   A["oneday"]["r"]["rows"], 1)

print("\nD. a day split that happens to include 1sts")
eq("D1  /!\\ 1sts MIXED with other days is a day split", A["mixed"]["r"]["days"], 5)

# ===========================================================================
print("\nE. one bad file no longer takes the batch down")
# ===========================================================================
HAND = fn_flat("handleWalmartAdCampaignDailyUpload")
ok("const refused = [];" in HAND, "E1  refusals are collected")
ok("} catch (e) {\n        refused.push({ name: files[i].name" in HAND,
   "E2  /!\\ per FILE, so a bad one does not abort the good ones")
ok("continue;" in HAND, "E3  ...and the loop carries on")
ok("if (!totalRows && refused.length)" in HAND,
   "E4  /!\\ but ALL files refused is still an error - there is nothing to report")
# /!\ NAMED, not counted. With several files dropped at once the operator has
# to know WHICH one to re-pull.
ok("refused.map(x => x.name).join(', ')" in HAND,
   "E5  /!\\ the status line NAMES the refused files, not just a count")
ok("refused.length ? 'dz-err' : 'dz-ok'" in HAND,
   "E6  ...and a partial load does not render as a clean one")
ok("alert(" in HAND and "refused.map(x => x.name + '\\n' + x.why)" in HAND,
   "E7  the reason reaches the operator, per file")

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
