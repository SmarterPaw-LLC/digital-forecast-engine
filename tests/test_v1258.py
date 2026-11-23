#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.58 - a sparkline, on the channels the Need-by boxes select.

- **Jason:** *"i also need sparklines. it should be based on which channels
  are selected in the need by checkboxes"*

It is **not a new measure**. `ipVelWindow(r, days, offset, keys)` already
answers "units/day over this window, for these channels" - lag-anchored per
channel, bundle attribution folded in, memoized - so the sparkline is that
primitive at twelve consecutive offsets and cannot disagree with the Vel
Trend column beside it.

This suite drives the REAL cell against salesData shaped the way the live
table holds it, and proves the one property the picture depends on: twelve
7-day buckets PARTITION the 84 days, neither overlapping nor leaving a seam.
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
print("  v12.58  twelve buckets of the primitive the trend already uses")
print("=" * 70)

# ===========================================================================
print("\nA. it is the existing primitive, not a second one")
# ===========================================================================
SER = fn_flat("velSparkSeries")
ok("ipVelWindow(r, VEL_SPARK_BUCKET_DAYS" in SER,
   "A1  /!\\ the series goes through ipVelWindow - the SAME call the Vel Trend "
   "columns are built on (hard rule #1)")
ok("i * VEL_SPARK_BUCKET_DAYS" in SER,
   "A2  ...at consecutive offsets, which is all a sparkline is")
ok("for (let i = VEL_SPARK_WEEKS - 1; i >= 0; i--)" in SER,
   "A3  oldest bucket first, newest last - the direction the eye reads")
ok("salesData" not in SER and "chewy_sales" not in SER,
   "A4  /!\\ and it never reaches for the rows itself, so the basis, the "
   "per-channel lag and bundle attribution cannot drift from Vel Now")

# ===========================================================================
print("\nB. the Need-by boxes drive it, per page")
# ===========================================================================
eq("B1  the column exists on BOTH sibling registries", js.count("key:'vel_spark'"), 2)
ok("velSparkCell(r, ipVelTrendChans())" in js,
   "B2  Inventory Planning reads ITS Need-by boxes")
ok("velSparkCell(r, fcVelTrendChans())" in js,
   "B3  /!\\ and the Forecast page reads ITS OWN - one reader each, or a column "
   "on one page silently answers for the other")
ok("default:false" in js[js.index("key:'vel_spark'"):js.index("key:'vel_spark'") + 200],
   "B4  opt-in, like every other column in this group - twelve windowed scans "
   "a row is not a cost to levy on everyone")
ok("csv:     r => velSparkCsv(" in js,
   "B5  CSV-exportable before it ships (RULES.md #12)")

# ===========================================================================
print("\nC. the real cell, driven")
# ===========================================================================
HARNESS = ("\n".join([const_line("VEL_SPARK_WEEKS"), const_line("VEL_SPARK_BUCKET_DAYS"),
                      const_line("IP_VEL_DEFAULT_CHANS")])
           + "\n" + fn_flat("velSparkSeries") + "\n" + fn_flat("velSparkCell") + "\n"
           + fn_flat("velSparkTip") + "\n" + fn_flat("velSparkCsv") + r"""
const TREND_CHANNELS = [
  { key:'amazon', label:'Amz' }, { key:'shopify', label:'Shop' },
  { key:'chewy', label:'Chwy' }, { key:'walmart', label:'Wmt' },
];
// Stand-ins for the two things velSparkCell consults.
let READY = true;
function ipVelTrendForKeys() { return { ready: READY }; }
// The REAL half-open age windowing ipVelWindow uses, over rows shaped the way
// salesData holds them. One row per week, 14 weeks back.
const NOW = Date.now();
const ROWS = [];
for (let wk = 0; wk < 14; wk++) {
  ROWS.push({ ageDays: wk * 7 + 1, channel: 'amazon', units: (wk < 12 ? (12 - wk) * 10 : 5) });
}
let CALLS = [];
function ipVelWindow(r, windowDays, offsetDays, keys) {
  CALLS.push([windowDays, offsetDays, keys.join('+')]);
  if (!r.__rows) return 0;
  let u = 0;
  for (const row of r.__rows) {
    if (!keys.includes(row.channel)) continue;
    if (row.ageDays >= offsetDays && row.ageDays < offsetDays + windowDays) u += row.units;
  }
  return u / windowDays;
}

const R = { master_id: 'SP-1', region: 'US', __rows: ROWS };
const FLAT = { master_id: 'SP-2', region: 'US', __rows: [] };

CALLS = [];
const series = velSparkSeries(R, ['amazon']);
const offsets = CALLS.map(c => c[1]);
const cell = velSparkCell(R, ['amazon']);
const flatCell = velSparkCell(FLAT, ['amazon']);
const csv = velSparkCsv(R, ['amazon']);
READY = false;
const notReady = velSparkCell(R, ['amazon']);
READY = true;

console.log(JSON.stringify({
  series, offsets,
  windows: [...new Set(CALLS.map(c => c[0]))],
  points: (cell.match(/points="([^"]+)"/) || [])[1] || '',
  hasSvg: cell.includes('<svg'),
  hasDot: cell.includes('<circle'),
  flatHasSvg: flatCell.includes('<svg'),
  flatPoints: (flatCell.match(/points="([^"]+)"/) || [])[1] || '',
  notReady,
  csv,
  csvNotReady: (function () { READY = false; const c = velSparkCsv(R, ['amazon']); READY = true; return c; })(),
  tip: velSparkTip(R, ['amazon'], series),
}));
""")
C = run_node(os.path.join(SP, "_v1258_c.js"), HARNESS)

eq("C1  twelve buckets", len(C["series"]), 12)
eq("C2  /!\\ every bucket is 7 days - a GRAIN, not the velocity window",
   C["windows"], [7])
eq("C3  /!\\ THE PARTITION: offsets are 77,70,...,0 - consecutive, "
   "non-overlapping, no seam", C["offsets"],
   [77, 70, 63, 56, 49, 42, 35, 28, 21, 14, 7, 0])
ok(C["series"][0] < C["series"][-1],
   "C4  oldest first: a rising product rises left to right", C["series"][:3])
eq("C5  the newest bucket is the last value",
   round(C["series"][-1], 3), round(120 / 7, 3))
ok(C["hasSvg"] and C["hasDot"],
   "C6  it draws an inline SVG with the latest point marked")
eq("C7  twelve points plotted", len(C["points"].split()), 12)
ok("..." in C["notReady"] or "…" in C["notReady"],
   "C8  /!\\ NOT LOADED IS NOT NO SALES (v9.93) - it waits rather than drawing "
   "a flat line over an empty cache", C["notReady"][:120])
ok("still loading" in C["notReady"],
   "C9  ...and says so")
eq("C10 /!\\ a row that genuinely sold NOTHING gets a baseline, not a dash - "
   "zero across twelve weeks is a fact about the product",
   C["flatHasSvg"], True)
eq("C11 ...drawn flat", len(set(p.split(',')[1] for p in C["flatPoints"].split())), 1)

# ===========================================================================
print("\nD. the export and the tooltip")
# ===========================================================================
eq("D1  the CSV is the twelve numbers", len(C["csv"].split(";")), 12)
eq("D2  ...and is EMPTY while sales are loading, never twelve zeros",
   C["csvNotReady"], "")
ok("Channels: Amz" in C["tip"],
   "D3  the tooltip names the channels it was built from", C["tip"][:80])
ok("Need by" in C["tip"],
   "D4  ...and the control that chose them")
ok("own peak" in C["tip"] and "height is not" in C["tip"].lower(),
   "D5  /!\\ and states that HEIGHT is not comparable down the column, because "
   "each row is scaled to itself")
ok("Units/day" in C["tip"] and "7 days to a bucket" in C["tip"],
   "D6  the tooltip says how the value is DERIVED (RULES.md #3)")

# ===========================================================================
print("\nE. the release names itself")
# ===========================================================================
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "E1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok("v12.58" in C_, "E2  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
