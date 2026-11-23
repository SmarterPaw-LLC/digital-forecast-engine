#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.59 - the sparkline ended on an EMPTY bucket, and it is named Sparkline.

- **Jason:** *"1. why is it named vel 12 w instead of sparkline? 2. this should
  be set based on the horizon #. 3. why is the end of the sparkline a dip? ...
  amazon should show increases in all of the products"*

He is right about (3) and right about the direction. Measured on the live
database, 2026-11-23:

    newest Amazon week in sales_weekly = 2026-11-16, age 7 days
    weekly units: 2,843 -> 2,828 -> 3,366 -> 3,813 -> 4,927   (strongly UP)

**There is no Amazon row at all for ages 0-6.** Bucket 0 spans age [0,7), so
it caught nothing and divided zero units by seven days: every Amazon line
ended on the floor. `ipChannelLagDays` did not catch it because 7 is inside
its 14-day tolerance - right for a 30/90-day window, fatal at a 7-day grain.
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


def const_line(name):
    m = re.search(r"^const %s = .*$" % re.escape(name), js, re.M)
    return m.group(0)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.59  a bucket with no rows in it is not a fall in demand")
print("=" * 70)

# ===========================================================================
print("\n(1) the name he used")
# ===========================================================================
eq("N1  the column is called Sparkline, on both pages",
   js.count("label:'Sparkline'"), 2)
ok("label:'Vel 12w'" not in js, "N2  ...and the coined one is gone")

# ===========================================================================
print("\n(2) the span follows the Horizon control")
# ===========================================================================
ok("VEL_SPARK_WEEKS" not in js,
   "H1  /!\\ the fixed 12-week constant is GONE, not left beside the new rule")
ok("ipSparkHorizon()" in js and "fcSparkHorizon()" in js,
   "H2  each page reads ITS OWN horizon control")
ok("'ip-horizon'" in fn_flat("ipSparkHorizon")
   and "'fHorizon'" in fn_flat("fcSparkHorizon"),
   "H3  ...and they are different controls, so one cannot answer for the other")

W = run_node(os.path.join(SP, "_v1259_w.js"),
             const_line("VEL_SPARK_BUCKET_DAYS") + "\n" + fn_flat("velSparkWeeks")
             + "\nconsole.log(JSON.stringify({"
               "h30: velSparkWeeks(30), h60: velSparkWeeks(60), h90: velSparkWeeks(90),"
               "h120: velSparkWeeks(120), junk: velSparkWeeks(null), tiny: velSparkWeeks(1),"
               "huge: velSparkWeeks(3650) }));\n")
eq("H4  a 90-day horizon draws 13 weeks", W["h90"], 13)
eq("H5  30-day draws 4", W["h30"], 4)
eq("H6  60-day draws 9", W["h60"], 9)
eq("H7  120-day draws 17", W["h120"], 17)
eq("H8  a missing horizon falls back to 90, not to NaN buckets", W["junk"], 13)
ok(W["tiny"] >= 3 and W["huge"] <= 26,
   "H9  clamped 3..26 - a shape needs points, and a hairline is not a shape",
   [W["tiny"], W["huge"]])

# ===========================================================================
print("\n(3) THE DIP, reproduced and fixed")
# ===========================================================================
HARNESS = (const_line("VEL_SPARK_BUCKET_DAYS") + "\n"
           + fn_flat("velSparkWeeks") + "\n" + fn_flat("velSparkChanAnchor") + "\n"
           + fn_flat("velSparkSeries") + r"""
// The live shape on 2026-11-23: Amazon is weekly-stamped and its newest row is
// age 7 - there is NOTHING for ages 0-6 - while Shopify is daily and current.
const AMZ_WEEKS = [[7,4927],[14,3813],[21,3366],[28,2828],[35,2843],
                   [42,2700],[49,2650],[56,2600],[63,2550],[70,2500],
                   [77,2450],[84,2400],[91,2350]];
const ROWS = [];
for (const [age, u] of AMZ_WEEKS) ROWS.push({ ageDays: age, channel: 'amazon', units: u });
for (let d = 0; d < 100; d++) ROWS.push({ ageDays: d, channel: 'shopify', units: 100 });

let RAWLAG = { amazon: 7, shopify: 0 };
function ipChannelLagRawDays(k) { return RAWLAG[k] || 0; }
// The REAL half-open age test ipVelWindowOne applies.
function ipVelWindowOne(r, windowDays, offsetDays, key) {
  let u = 0;
  for (const row of ROWS) {
    if (row.channel !== key) continue;
    if (row.ageDays >= offsetDays && row.ageDays < offsetDays + windowDays) u += row.units;
  }
  return u / windowDays;
}

const R = { master_id: 'SP-1', region: 'US' };

// The pre-v12.59 series: ONE shared offset, no per-channel anchor.
function oldSeries(keys, n) {
  const out = [];
  for (let i = n - 1; i >= 0; i--) {
    let v = 0;
    for (const k of keys) v += ipVelWindowOne(R, 7, i * 7, k);
    out.push(v);
  }
  return out;
}

const amzOld = oldSeries(['amazon'], 13);
const amzNew = velSparkSeries(R, ['amazon'], 90);
const bothOld = oldSeries(['amazon', 'shopify'], 13);
const bothNew = velSparkSeries(R, ['amazon', 'shopify'], 90);

console.log(JSON.stringify({
  anchorAmz: velSparkChanAnchor('amazon'),
  anchorShop: velSparkChanAnchor('shopify'),
  amzOldLast: amzOld[amzOld.length - 1],
  amzOldPrev: amzOld[amzOld.length - 2],
  amzNewLast: amzNew[amzNew.length - 1],
  amzNewPrev: amzNew[amzNew.length - 2],
  amzNewRising: amzNew[amzNew.length - 1] > amzNew[amzNew.length - 2],
  bothOldDips: bothOld[bothOld.length - 1] < bothOld[bothOld.length - 2],
  bothNewDips: bothNew[bothNew.length - 1] < bothNew[bothNew.length - 2],
  len90: amzNew.length,
  len30: velSparkSeries(R, ['amazon'], 30).length,
}));
""")
D = run_node(os.path.join(SP, "_v1259_d.js"), HARNESS)

eq("D1  /!\\ THE DEFECT: with one shared offset the newest Amazon bucket was "
   "EMPTY - zero units over seven days", D["amzOldLast"], 0)
ok(D["amzOldPrev"] > 0,
   "D2  ...while the bucket before it was full, which is the dip he saw",
   D["amzOldPrev"])
eq("D3  /!\\ THE FIX: Amazon's buckets are anchored to its own newest row",
   D["anchorAmz"], 7)
eq("D4  ...and a current channel is not shifted at all", D["anchorShop"], 0)
eq("D5  the newest bucket now holds the real 4,927-unit week",
   round(D["amzNewLast"], 3), round(4927 / 7, 3))
ok(D["amzNewRising"],
   "D6  /!\\ AND IT RISES AT THE END, which is what the data does: "
   "2,843 -> 2,828 -> 3,366 -> 3,813 -> 4,927")
ok(D["bothOldDips"] and not D["bothNewDips"],
   "D7  /!\\ mixed channels: the blended line dipped before and does not now - "
   "each channel keeps its own anchor rather than one shared shift",
   [D["bothOldDips"], D["bothNewDips"]])
eq("D8  13 buckets at a 90-day horizon", D["len90"], 13)
eq("D9  4 at a 30-day one", D["len30"], 4)

# ===========================================================================
print("\nE. the anchor is honest about itself")
# ===========================================================================
RAW = fn_flat("ipChannelLagRawDays")
ok("Object.keys(salesData).length" in RAW,
   "E1  /!\\ an empty salesData yields NO lag, never a cached 'everything is "
   "current' (the v9.93 trap this cache already had)")
ok("ipChannelLagDays(key)" in RAW,
   "E2  it builds through the existing scan rather than a second pass")
ok("_ipChanLagRawCache = null" in js
   and js.index("_ipChanLagRawCache = null") < js.index("function ipChannelLagDays"),
   "E3  /!\\ and clearVelMemo drops it WITH its sibling - a raw lag left behind "
   "would answer with the age from before the upload that just landed")
TIP = fn_flat("velSparkTip")
ok("is ' + x.d + 'd behind" in TIP or "d behind" in TIP,
   "E4  the tooltip NAMES a shifted channel, so a line ending earlier than "
   "today reads as a reporting lag rather than as a fall")
ok("Horizon control" in TIP, "E5  ...and says the span follows the horizon")

# ===========================================================================
print("\nF. the release names itself")
# ===========================================================================
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "F1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok("v12.59" in C_, "F2  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
