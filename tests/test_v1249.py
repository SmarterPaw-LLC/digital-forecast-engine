#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.49 - a CASES column with no case qty is a GAP, not a row of dashes.

- **Jason:** *"what i really need is for the purrple passion sample tube to
  appear on the inhouse production list, it is the component produced in
  house, but it doesn't appear at all on the list"*

It WAS on the list. CF107 carries real demand - the Catnip Sampler Bundle
sold 404 units in 60 days and the BOM pulls one tube per bundle - and every
week still drew a dash, because `cases = ceil(units / case_qty)` cannot be
computed when case_qty is 0 and that branch drew the SAME glyph the
zero-demand branch draws.

v9.94 built the chip slot for exactly this ("a row of dashes is not an
answer"), and it only fired when the UNITS total was 0. This suite drives the
real row renderer so a row with units and no case qty can never again be
silent, and reproduces the pre-v12.49 renderer beside it.
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


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


def slice_between(start, end):
    """Lift a verbatim span of the shipped source. Never re-typed."""
    i = js.index(start)
    j = js.index(end, i)
    return js[i:j + len(end)]


print("\n" + "=" * 70)
print("  v12.49  the dash says which kind of nothing it is")
print("=" * 70)

# ===========================================================================
print("\nA. one sentence, in one place")
# ===========================================================================
ok("const IP_NO_CASE_QTY_TIP =" in js,
   "A1  IP_NO_CASE_QTY_TIP is declared")
eq("A2  declared exactly once", js.count("const IP_NO_CASE_QTY_TIP ="), 1)
ok("Set case_qty on this product to see cases." not in js,
   "A3  /!\\ the older, shorter spelling is GONE, not left standing beside it")
# chip + 2 week cells + Case Qty cell + the declaration
eq("A4  read by every surface that draws the gap",
   js.count("IP_NO_CASE_QTY_TIP"), 5)
ok("Switch Columns to Units" in js,
   "A5  and it names the control that makes the number readable")
ok("set Case qty" in js,
   "A6  ...and the field that makes the CASES column readable")

# ===========================================================================
print("\nB. the real row renderer, driven")
# ===========================================================================
# The per-row body of renderInhouseWeeklyPanel is a closure over the panel's
# settings, so it is LIFTED verbatim rather than re-typed (the v12.39 rule).
ROW = slice_between("    const cq = r.case_qty || 0;",
                    "    tr += '</tr>';")

HARNESS = r"""
const IP_NO_CASE_QTY_TIP =
  'Cases = ceil(units / case qty), and this product has no case qty set.'
  + '\n\nThe weekly demand is real. Switch Columns to Units to read it, or'
  + ' click the row to open the product card and set Case qty.';

function ipScheduleZeroReason(r, horizonDays) {
  return { txt: 'no demand', tip: 'NOTHING IS DRIVING PRODUCTION FOR THIS SKU.' };
}
function openProductModal() {}
function pnlCardBtn() { return '<a>card</a>'; }

const cell = v => `<td class="u">${v>0?Math.round(v).toLocaleString():'—'}</td>`;
const cellPlus = (v) => `<td class="u">${v>0?Math.round(v).toLocaleString():'—'}</td>`;
const cellConsumed = () => `<td class="c">0</td>`;
const cellConsumedCum = v => `<td class="c">${v > 0 ? Math.round(v).toLocaleString() : '—'}</td>`;

function renderRow(opts) {
  const { r, wkAll, weeks, showUnits, showCases, valMode,
          eventsActive, coverageByShipWeek, consumedWeeks, coverIndexByWeek } = opts;
  let tr = '', body = '';
  const __rows = [r];
  __rows.forEach(r => {
""" + ROW + r"""
    body += tr;
  });
  return body;
}

// 8 weeks of real demand - CF107's shape: ~6.7/day from bundle assembly.
const WK_REAL = Array.from({length: 8}, (_, i) => ({
  weekStart: '2026-11-15', units: 47, cumUnits: 47 * (i + 1) }));
const WK_ZERO = Array.from({length: 8}, () => ({
  weekStart: '2026-11-15', units: 0, cumUnits: 0 }));

function go(r, wkAll, showUnits, showCases) {
  return renderRow({ r, wkAll, weeks: 8, showUnits, showCases, valMode: 'weekly',
    eventsActive: false, coverageByShipWeek: new Map(),
    consumedWeeks: new Set(), coverIndexByWeek: new Map() });
}

const CF107  = { master_id: 'SP-0600', title: 'Purrple Passion Sampler Tubes',
                 short_name: '', case_qty: 0 };
const CASED  = { master_id: 'SP-0066', title: 'Catnip Sampler 3 Pack',
                 short_name: '', case_qty: 12 };

const out = {
  // the defect, exactly as reported: cases on, no case qty, real demand
  casesNoCq:    go(CF107, WK_REAL, false, true),
  // same row in Units mode - a missing case qty costs nothing there
  unitsNoCq:    go(CF107, WK_REAL, true, false),
  // both columns
  bothNoCq:     go(CF107, WK_REAL, true, true),
  // no demand AND no case qty - the zero reason has to win
  casesNoCqZero: go(CF107, WK_ZERO, false, true),
  // a product that CAN convert must be byte-identical to pre-v12.49
  casesWithCq:  go(CASED, WK_REAL, false, true),
  unitsWithCq:  go(CASED, WK_REAL, true, false),
};
console.log(JSON.stringify(out));
"""

A = run_node(os.path.join(SP, "_v1249_a.js"), HARNESS)

ok("no case qty" in A["casesNoCq"],
   "B1  /!\\ THE DEFECT: cases on, no case qty, real units -> the row SAYS so")
ok("⚠ no case qty" in A["casesNoCq"],
   "B2  ...in the chip slot v9.94 already built, with its glyph")
ok("Cases = ceil(units / case qty)" in A["casesNoCq"],
   "B3  ...and the tooltip is the one sentence")
# /!\ ASSERT ON THE CHIP, not on the words. The Case Qty cell's own tooltip
# carries the same sentence by design, so a bare substring test would pass on
# the tooltip and prove nothing about the chip.
CHIP_CQ   = "⚠ no case qty"
CHIP_ZERO = "⚠ no demand"
ok(CHIP_CQ not in A["unitsNoCq"],
   "B4  /!\\ UNITS MODE CARRIES NO CHIP. A missing case qty costs nothing "
   "there, so a chip would be noise")
ok(CHIP_CQ in A["bothNoCq"],
   "B5  'Both' shows cases, so it chips")
ok(CHIP_ZERO in A["casesNoCqZero"] and CHIP_CQ not in A["casesNoCqZero"],
   "B6  /!\\ THE ZERO REASON WINS. Both are true; 'nothing is driving "
   "production' is what decides what you do next")
ok(CHIP_CQ not in A["casesWithCq"] and CHIP_ZERO not in A["casesWithCq"],
   "B7  a product that CAN convert carries no chip at all")
ok("Cases = ceil(units / case qty)" in A["unitsNoCq"],
   "B7a ...but the Case Qty CELL still explains itself in Units mode - it is "
   "the cell that fixes the gap")

# The cells themselves must be untouched for a convertible product.
eq("B8  cases render for a product with a case qty",
   A["casesWithCq"].count('<td class="u">4</td>'), 8)   # ceil(47/12) = 4
eq("B9  units render unchanged", A["unitsWithCq"].count('<td class="u">47</td>'), 8)
ok(A["unitsNoCq"].count('<td class="u">47</td>') == 8,
   "B10 /!\\ AND THE UNITS WERE THERE THE WHOLE TIME - 47 a week on the row "
   "Jason read as empty")

# ===========================================================================
print("\nC. the pre-v12.49 renderer, reproduced")
# ===========================================================================
GUARD = HARNESS.replace(
    """    const cqGap = (!zr && showCases && cq <= 0)
      ? { txt: 'no case qty', tip: IP_NO_CASE_QTY_TIP }
      : null;
    const rowChip = zr || cqGap;
    const zeroChip = rowChip""",
    """    const rowChip = zr;
    const zeroChip = rowChip""")
ok(GUARD != HARNESS, "C0  the guard really did remove the fix")
B = run_node(os.path.join(SP, "_v1249_b.js"), GUARD)
ok(CHIP_CQ not in B["casesNoCq"],
   "C1  /!\\ pre-v12.49 the row carried NO CHIP with real demand behind it")
# The no-case-qty week cell is the one whose style ends `var(--border)" title=`;
# the Case Qty cell's own dash ends `var(--border);white-space:nowrap`.
WEEK_DASH = 'var(--border)" title="Cases = ceil'
eq("C2  ...and all 8 visible weeks drew the dash",
   B["casesNoCq"].count(WEEK_DASH), 8)
eq("C2a and v12.49 did not change that - the CELLS are honest, the ROW was not",
   A["casesNoCq"].count(WEEK_DASH), 8)
ok(CHIP_ZERO in B["casesNoCqZero"],
   "C3  the zero reason already worked, which is why this went unnoticed")

# ===========================================================================
print("\nD. the CSV is the other surface of the same measure")
# ===========================================================================
CSVLINE = [l for l in js.split("\n") if "wkCells.push(cq > 0" in l]
eq("D1  one cases writer in the export", len(CSVLINE), 1)
ok("'no case qty'" in CSVLINE[0],
   "D2  /!\\ a CSV cell cannot carry a tooltip, so it says it in the cell "
   "(rule #5 - two surfaces, one measure)", CSVLINE[0].strip())
ok("u > 0 ? Math.ceil(u / cq) : ''" in CSVLINE[0],
   "D3  ...and a REAL zero still writes blank, exactly as it always did")

# ===========================================================================
print("\nE. nothing else moved")
# ===========================================================================
ok("const zr = _visTotal > 0 ? null : ipScheduleZeroReason(r, weeks * 7);" in js,
   "E1  the v9.94 zero reason is still computed from UNITS, not from what the "
   "CASES column managed to render")
ok("showCases && cq <= 0" in js,
   "E2  the gap is gated on cases being on screen")
ok(js.count("const rowChip = zr || cqGap;") == 1,
   "E3  one decision about which reason the chip carries")
ok("v12.49" in s and "2026-11-18" in s,
   "E4  the version chip names this release")
chip = re.search(r"v12\.49[^<]{0,18}", s)
ok(chip is not None and "\\u" not in chip.group(0),
   "E5  /!\\ and it is REAL characters in markup, not the escape form "
   "(v12.42 shipped `v12.42 \\u00b7` as literal text)",
   chip.group(0) if chip else None)
C = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
ok("v12.49" in C, "E6  CLAUDE.md carries the entry for this release")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
