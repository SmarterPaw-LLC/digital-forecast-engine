#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.42 - the comparison line names its own period, and a month's prior
year is the same month.

- **Jason:** *"the previous period data points never show in the hover
  window. i don't know what the comparison period was"*

Two findings, one measured on the way:

1. The VALUE was in the tooltip; the DATE behind it was not, on any chart in
   the app. `Sessions (prior year): 2,007` says nothing about which 2,007.
2. /!\ ON A MONTH GRAIN THE PAIRING WAS OFF BY ONE MONTH. The shift was 364
   days - 52 whole weeks, correct for a day or a week so a Monday still meets
   a Monday - applied to the bucket's FIRST day. 2025-09-01 + 364d is
   2026-08-31, which re-keys to `2026-08`. So September was drawn against
   last OCTOBER, every band one month early, and the newest month paired with
   nothing at all.
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


def strip_comments(t):
    t = re.sub(r"/\*[\s\S]*?\*/", "", t)
    return re.sub(r"^\s*//.*$", "", t, flags=re.M)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


SHIFT = fn_flat("pnlPriorYearShift")
OVER  = fn_flat("pnlPrevOverlay")

print("\n" + "=" * 70)
print("  v12.42  a comparison line that says which period it is")
print("=" * 70)

HARNESS = fn_flat("pnlGrainKey") + "\n" + fn_flat("pnlBucketRange") + "\n" + SHIFT + r"""
// /!\ THE DEFECT REPRODUCED: the pre-v12.42 shift, VERBATIM, beside the
// shipped one, over the same keys at the same grain.
function oldShift(k, grain) {
  const r = pnlBucketRange(k, grain);
  const x = new Date((r ? r.from : k) + 'T00:00:00'); x.setDate(x.getDate() + 364);
  const d = `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  return pnlGrainKey(d, grain);
}
"""

A = run_node(os.path.join(SP, "_v1242_a.js"), HARNESS + r"""
const out = {};

// A full year of months, which is what a 'Last 12 months' SEO chart draws.
const priorM = ['2025-09','2025-10','2025-11','2025-12','2026-01'];
const curM   = ['2026-09','2026-10','2026-11','2026-12','2027-01'];
out.monthOld  = priorM.map(k => oldShift(k, 'month'));
out.monthNew  = priorM.map(k => pnlPriorYearShift(k, 'month'));
out.monthOldHit = curM.filter(b => out.monthOld.includes(b));
out.monthNewHit = curM.filter(b => out.monthNew.includes(b));

// Mondays, which is what the week rollup keys on.
const priorW = ['2025-11-03','2025-11-10','2025-12-29'];
const curW   = ['2026-11-02','2026-11-09','2026-12-28'];
out.weekOld = priorW.map(k => oldShift(k, 'week'));
out.weekNew = priorW.map(k => pnlPriorYearShift(k, 'week'));
out.weekDow = out.weekNew.map(d => new Date(d + 'T00:00:00').getDay());
out.weekSame = JSON.stringify(out.weekOld) === JSON.stringify(out.weekNew);
out.weekWant = JSON.stringify(out.weekNew) === JSON.stringify(curW);

const priorD = ['2025-11-09','2026-02-28'];
out.dayOld = priorD.map(k => oldShift(k, 'day'));
out.dayNew = priorD.map(k => pnlPriorYearShift(k, 'day'));
out.daySame = JSON.stringify(out.dayOld) === JSON.stringify(out.dayNew);

// The INVERSE - what the tooltip pairs each drawn bucket with.
out.backMonth = curM.map(b => pnlPriorYearShift(b, 'month', true));
out.backWeek  = curW.map(b => pnlPriorYearShift(b, 'week', true));
out.backDay   = ['2026-11-08'].map(b => pnlPriorYearShift(b, 'day', true));
out.roundM = priorM.every(k => pnlPriorYearShift(pnlPriorYearShift(k,'month'),'month',true) === k);
out.roundW = priorW.every(k => pnlPriorYearShift(pnlPriorYearShift(k,'week'),'week',true) === k);
out.roundD = priorD.every(k => pnlPriorYearShift(pnlPriorYearShift(k,'day'),'day',true) === k);

// Guards.
out.junk    = pnlPriorYearShift('not-a-key', 'week');
out.blank   = pnlPriorYearShift('', 'week');
out.nullish = pnlPriorYearShift(null, 'month');
// A bare month key carries no day to shift, whatever the caller's grain says
// - the same rule pnlBucketRange already applies to one.
out.monthKeyUnderWeek = pnlPriorYearShift('2025-09', 'week');
// A day key under a MONTH grain is normalised first rather than shifted raw.
out.dayKeyUnderMonth  = pnlPriorYearShift('2025-09-15', 'month');
console.log(JSON.stringify(out));
""")

# ===========================================================================
print("\nA. /!\\ THE DEFECT: September was drawn against last OCTOBER")
# ===========================================================================
eq("A1  /!\\ the OLD shift lands every month one month EARLY",
   A["monthOld"], ["2026-08", "2026-09", "2026-10", "2026-11", "2026-12"])
eq("A2  /!\\ ...and the shipped one pairs a month with the same month",
   A["monthNew"], ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01"])
ok(A["monthOld"] != A["monthNew"],
   "A3  which is a different line on every monthly chart, not a rounding nudge")
eq("A4  /!\\ the OLD rule left the NEWEST month paired with nothing - four "
   "of five buckets hit", len(A["monthOldHit"]), 4)
eq("A5  ...and the shipped one pairs all five", len(A["monthNewHit"]), 5)
eq("A6  a year boundary is carried, not truncated",
   A["monthNew"][4], "2027-01")

# ===========================================================================
print("\nB. /!\\ DAY AND WEEK ARE BYTE-IDENTICAL - 364 was right there")
# ===========================================================================
ok(A["weekSame"], "B1  /!\\ the week grain answers exactly what it did before",
   A["weekOld"])
ok(A["daySame"], "B2  ...and so does the day grain", A["dayOld"])
eq("B3  a Monday still meets a Monday, which is the whole reason for 364",
   A["weekDow"], [1, 1, 1])
ok(A["weekWant"], "B4  and it is the right Monday", A["weekNew"])

# ===========================================================================
print("\nC. the inverse, which is what the tooltip reads")
# ===========================================================================
eq("C1  a drawn month names the same month a year back",
   A["backMonth"], ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01"])
eq("C2  a drawn week names the Monday 364 days before it",
   A["backWeek"], ["2025-11-03", "2025-11-10", "2025-12-29"])
eq("C3  and a drawn day names its own day", A["backDay"], ["2025-11-09"])
for k, lbl in (("roundM", "month"), ("roundW", "week"), ("roundD", "day")):
    ok(A[k], "C4  /!\\ forward then back is the identity on the %s grain, so "
             "the date in the tooltip is the row the point was built from" % lbl)

# ===========================================================================
print("\nD. the guards")
# ===========================================================================
eq("D1  an unparseable key is returned untouched, never an Invalid Date",
   A["junk"], "not-a-key")
eq("D2  ...and so is a blank", A["blank"], "")
eq("D3  ...and a null", A["nullish"], "")
eq("D4  /!\\ a bare month key has no day to shift whatever the grain says",
   A["monthKeyUnderWeek"], "2026-09")
eq("D5  /!\\ a day key under a month grain is normalised, not shifted raw - "
   "which is the exact arithmetic that produced the defect",
   A["dayKeyUnderMonth"], "2026-09")

# ===========================================================================
print("\nE. $pairKeys is PUBLISHED by both overlays and read in ONE place")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1242_b.js"), OVER + r"""
const cur  = ['2026-10-05','2026-10-12','2026-10-19'];
const prev = ['2026-09-14','2026-09-21','2026-09-28','2026-10-05'];
const ov = pnlPrevOverlay([11, 22, 33, 44], cur, prev);
// A prior window SHORTER than the current one: the tail has no pair.
const ov2 = pnlPrevOverlay([11, 22], cur, ['2026-09-21','2026-09-28']);
console.log(JSON.stringify({
  pairs: ov.$pairKeys, data: ov.data, len: ov.$pairKeys.length,
  stack: ov.stack, label: ov.label,
  pairs2: ov2.$pairKeys, data2: ov2.data,
  none: pnlPrevOverlay([null, null], cur, prev),
}));
""")
eq("E1  /!\\ one pair key per DRAWN bucket, aligned from the START the way "
   "the data is", B["pairs"], ["2026-09-14", "2026-09-21", "2026-09-28"])
eq("E2  ...so the array cannot run longer than the chart", B["len"], len(B["data"]))
eq("E3  the values it dates are unchanged", B["data"], [11, 22, 33])
eq("E4  /!\\ a bucket with no counterpart is NULL, not the last one repeated",
   B["pairs2"], ["2026-09-21", "2026-09-28", None])
eq("E5  ...and its value is null too, so the tooltip never shows a date "
   "without a number", B["data2"], [11, 22, None])
ok(B["stack"] == "_prev",
   "E6  it is still its own stack group, so it is not folded into the total")
ok(B["none"] is None, "E7  an all-null overlay is still no overlay at all")

NO_C = strip_comments(js)
eq("E8  /!\\ written by exactly the TWO overlay builders",
   NO_C.count("$pairKeys:"), 2)
eq("E9  /!\\ and read in exactly ONE place - the shared tooltip. A second "
   "reader is a second way to date a point",
   len(re.findall(r"dataset\.\$pairKeys", NO_C)), 2)
ok("$pairKeys: prevPairs" in NO_C, "E10 the SEO prior-year line publishes it")
ok("$pairKeys: curBuckets.map" in NO_C, "E11 ...and so does pnlPrevOverlay")

# ===========================================================================
print("\nF. the tooltip, driven")
# ===========================================================================
i = js.index("            label: c => {")
LAB = js[i:js.index("\n            },", i) + len("\n            },")]
ok("$pairKeys" in LAB, "F0  the real label callback was sliced")
C = run_node(os.path.join(SP, "_v1242_c.js"), r"""
const MON3 = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fmtBucket = b => {
  const [y, mo, d] = String(b || '').split('-');
  if (!y) return b;
  if (d === undefined) return (MON3[(+mo) - 1] || mo) + "'" + y.slice(2);
  return `${+mo}/${+d}/${y.slice(2)}`;
};
const fmtOf = () => (v) => Number(v).toLocaleString('en-US');
const cb = {
""" + LAB + r"""
};
const call = (ds, i, y) => cb.label({ dataset: ds, dataIndex: i, parsed: { y } });
console.log(JSON.stringify({
  band:    call({ label: 'Direct' }, 0, 1361),
  overlay: call({ label: 'Sessions (prior year)', $pairKeys: ['2025-11-10'] }, 0, 2007),
  month:   call({ label: 'Sessions (prior year)', $pairKeys: ['2025-09'] }, 0, 2007),
  gap:     call({ label: 'Previous period', $pairKeys: [null] }, 0, 5),
  past:    call({ label: 'Previous period', $pairKeys: ['2026-09-14'] }, 3, 5),
}));
""")
eq("F1  /!\\ an ordinary band is BYTE-IDENTICAL to v12.41 - this callback is "
   "on every chart in the app", C["band"], " Direct: 1,361")
eq("F2  /!\\ and the comparison line now says WHICH 2,007 it is",
   C["overlay"], " Sessions (prior year) · 11/10/25: 2,007")
eq("F3  a month pair reads as a month, through the same formatter the axis "
   "uses", C["month"], " Sessions (prior year) · Sep'25: 2,007")
eq("F4  a bucket with no counterpart prints no date rather than 'null'",
   C["gap"], " Previous period: 5")
eq("F5  ...and an index past the end of the array is the same",
   C["past"], " Previous period: 5")

# ===========================================================================
print("\nG. nothing still claims 364 days unconditionally")
# ===========================================================================
ok("shifted 364 days so a weekday" not in js or
   "the same month a year back on a monthly grain" in js,
   "G1  /!\\ the refused Compare control states the real rule, both grains")
ok("prior year shifted 364d (52 whole weeks)' : '')" not in js,
   "G2  /!\\ and the sub-line no longer prints '364d' under a monthly chart")
ok("grain === 'month' ? 'same month, one year back'" in js,
   "G3  ...it says what it actually did")
eq("G4  one shift function", js.count("function pnlPriorYearShift"), 1)
ok("x.setDate(x.getDate() + 364)" not in strip_comments(js),
   "G5  /!\\ the old unconditional +364 is GONE, not left standing beside it")
ok("pnlPriorYearShift(k, grain)" in js and "pnlPriorYearShift(b, grain, true)" in js,
   "G6  the SEO chart draws and dates through the same function")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
