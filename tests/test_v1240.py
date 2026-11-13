#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.40 - the scorecard and the chart disagreed by one day.

Spotted in Jason's Year-to-date screenshot rather than reported: the
scorecard read $1,931,213 and the table under the chart read $1,931,747.
The $534 between them is EXACTLY Shopify's 1 January on the live database.

/!\ TWO PARSERS, ONE WINDOW. The chart's `inRange` uses parseLocalDate;
`sumUnits` used `new Date(r.week_start)`, a UTC parse - so west of
Greenwich a row stamped 2026-01-01 reads as 2025-12-31 18:00 local and
falls OUTSIDE a window that starts on 2026-01-01.
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


def run_node(path, body, env=None):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(["node", path], capture_output=True, text=True,
                       encoding="utf-8", env=e)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.40  one window, one parser")
print("=" * 70)

SUM = fn_flat("sumUnits")
HARNESS = (fn_flat("parseLocalDate") + "\n" + fn_flat("salesRowVal") + "\n" + SUM
           + r"""
// /!\ THE DEFECT, REPRODUCED: the pre-v12.40 filter, verbatim, beside the
// shipped one, over the same rows and the same window.
function sumUnitsUtc(rows, fromDate, toDate, channels) {
  return rows.filter(r => {
    const d = new Date(r.week_start);
    if (fromDate && d < fromDate) return false;
    if (toDate   && d > toDate)   return false;
    if (channels && !channels.includes(r.channel)) return false;
    return true;
  }).reduce((s, r) => s + (r.units_ordered || 0), 0);
}
const rows = [
  { week_start: '2025-12-31', units_ordered: 7,  channel: 'shopify' },
  { week_start: '2026-01-01', units_ordered: 534, channel: 'shopify' },
  { week_start: '2026-01-02', units_ordered: 368, channel: 'shopify' },
  { week_start: '2026-11-13', units_ordered: 11, channel: 'shopify' },
];
const from = parseLocalDate('2026-01-01');
const to   = parseLocalDate('2026-11-13');
console.log(JSON.stringify({
  tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  offsetMin: new Date('2026-01-01T12:00:00').getTimezoneOffset(),
  shipped: sumUnits(rows, from, to, null),
  old: sumUnitsUtc(rows, from, to, null),
  shippedAll: sumUnits(rows, null, null, null),
  oldAll: sumUnitsUtc(rows, null, null, null),
  lastDay: sumUnits(rows, from, to, null) - sumUnits(rows, from, parseLocalDate('2026-11-12'), null),
  bad: sumUnits([{ week_start: 'not-a-date', units_ordered: 99, channel: 'shopify' }], from, to, null),
  badAll: sumUnits([{ week_start: null, units_ordered: 99, channel: 'shopify' }], null, null, null),
}));
""")

# ===========================================================================
print("\nA. /!\\ THE DEFECT, west of Greenwich")
# ===========================================================================
# TZ is forced, because the whole bug is an offset and a UTC CI box would
# have shown nothing wrong.
A = run_node(os.path.join(SP, "_v1240_a.js"), HARNESS, {"TZ": "America/Chicago"})
eq("A0  the harness really is in a UTC-negative zone", A["offsetMin"] > 0, True)
eq("A1  /!\\ the OLD filter drops the first day of the window",
   A["old"], 368 + 11)
eq("A2  /!\\ ...and the shipped one keeps it - $534 to the dollar, which is "
   "what separated the scorecard from the table on Jason's screen",
   A["shipped"], 534 + 368 + 11)
eq("A3  the difference IS the first day", A["shipped"] - A["old"], 534)
eq("A4  a row genuinely before the window stays out", A["shipped"], 913)
eq("A5  /!\\ and the LAST day of the window is in it too", A["lastDay"], 11)
eq("A6  an unwindowed total is unchanged by any of this",
   [A["shippedAll"], A["oldAll"]], [920, 920])

# ===========================================================================
print("\nB. /!\\ AND IT CUT THE OTHER END EAST OF GREENWICH")
# ===========================================================================
# My first read of this was wrong and the harness caught it: the UTC parse
# does not only drop the FIRST day. East of Greenwich it drops the LAST -
# `new Date('2026-11-13')` is 01:00 local in Berlin, which is past a `to` of
# local midnight. Only a box running in UTC itself sees neither end move,
# which is exactly why a UTC CI would never have caught this.
B = run_node(os.path.join(SP, "_v1240_b.js"), HARNESS, {"TZ": "Europe/Berlin"})
eq("B1  the shipped filter answers the same everywhere", B["shipped"], 913)
eq("B2  /!\\ the OLD one drops the LAST day here, not the first",
   B["old"], 534 + 368)
U = run_node(os.path.join(SP, "_v1240_u.js"), HARNESS, {"TZ": "UTC"})
eq("U1  in UTC the shipped filter still answers the same", U["shipped"], 913)
eq("U2  /!\\ ...and so did the old one - the one place it looked "
   "correct", U["old"], 913)

# ===========================================================================
print("\nC. the guards")
# ===========================================================================
eq("C1  /!\\ an unparseable date is DROPPED, not counted at the epoch - "
   "`new Date('not-a-date')` is Invalid and every comparison against it is "
   "false, so it used to slip through every window", A["bad"], 0)
eq("C2  ...and a null one, even with no window at all", A["badAll"], 0)
ok("const d = parseLocalDate(r.week_start);" in SUM,
   "C3  the shared local parser, not a second one")
ok("new Date(r.week_start)" not in SUM,
   "C4  /!\\ and the UTC parse is GONE, not left standing beside it")
ok("if (!d) return false;" in SUM, "C5  with the null guard the parse needs")

# ===========================================================================
print("\nD. one window, one parser")
# ===========================================================================
TOT = fn_flat("updateSalesChart")
ok("const d = parseLocalDate(w);" in TOT,
   "D1  the chart's own inRange was already local (v9.71)")
ok("parseLocalDate" in fn_flat("getSalesPeriodDates"),
   "D2  ...and so is the window both of them are handed")
ok(js.count("function sumUnits") == 1,
   "D3  one aggregator, so there is one answer to fix")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
