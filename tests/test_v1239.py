#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.39 - a month bucket is the row's OWN month, not its Monday's.

Jason: "i have year to date selected, so why is december in view?"

/!\ MEASURED FIRST. That December column held $2,125, and on the live
database it is four days of Shopify (1-4 January, $2,102) plus one Walmart
week stamped Saturday 3 January. All of it is JANUARY.

The page buckets by shifting a row's date back to the preceding Monday - the
right thing for a WEEK bucket, the wrong thing for a MONTH one, because two
of the five feeds are not stamped on a Monday:

    sales_weekly         dow 1  Monday      11,814 rows   (no-op)
    chewy_sales_weekly   dow 1  Monday       9,304 rows   (no-op)
    walmart_sales_weekly dow 6  SATURDAY       935 rows   shifts back 5 days
    shopify_sales_daily  every day                        shifts up to 6
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


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.39  a month bucket is the row's own month")
print("=" * 70)

# The real bucketOf, lifted out of updateSalesChart with its two closures
# supplied - it is defined inside that function, so it cannot be sliced by
# name. Taken VERBATIM from the source so it cannot drift from what ships.
SALES = fn_flat("updateSalesChart")
i = SALES.index("  const bucketOf = (dateStr) => {")
BUCKET = SALES[i:SALES.index("\n  };", i) + 5]
ok("salesGrain === 'month'" in BUCKET, "A0  the real bucketOf was sliced")

HARNESS = (fn_flat("parseLocalDate") + "\n" + fn_flat("pnlGrainKey") + "\n"
           + "let salesGrain = 'month';\nconst cutoffWeek = null;\n"
           + """
const toMondayKey = (dateStr) => {
  if (!dateStr) return null;
  const d = parseLocalDate(dateStr);
  if (!d || isNaN(d.getTime())) return null;
  const dow = d.getDay();
  const diff = dow === 0 ? -6 : (1 - dow);
  const m = new Date(d);
  m.setDate(d.getDate() + diff);
  const y = m.getFullYear(), mo = String(m.getMonth()+1).padStart(2,'0'), dd = String(m.getDate()).padStart(2,'0');
  return `${y}-${mo}-${dd}`;
};
""" + BUCKET)

A = run_node(os.path.join(SP, "_v1239_a.js"), HARNESS + r"""
const days = ['2026-01-01','2026-01-02','2026-01-03','2026-01-04','2026-01-05',
              '2026-01-31','2026-02-01','2025-12-31'];
const out = { month: {}, week: {} };
for (const d of days) out.month[d] = bucketOf(d);
salesGrain = 'week';
for (const d of days) out.week[d] = bucketOf(d);
salesGrain = 'month';
out.junk = bucketOf('not-a-date');
out.blank = bucketOf('');
out.monday = bucketOf('2026-03-02');
console.log(JSON.stringify(out));
""")

# ===========================================================================
print("\nA. /!\\ THE DEFECT: four days of January under December")
# ===========================================================================
for d in ('2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04'):
    eq("A1  %s is JANUARY" % d, A["month"][d], "2026-01")
eq("A2  ...and so is the Monday that used to swallow them",
   A["month"]["2026-01-05"], "2026-01")
eq("A3  the last day of a month stays in it", A["month"]["2026-01-31"], "2026-01")
eq("A4  ...and the first day of the next starts the next",
   A["month"]["2026-02-01"], "2026-02")
eq("A5  a genuinely December day is still December",
   A["month"]["2025-12-31"], "2025-12")
eq("A6  a Monday-stamped row is unaffected, which is 21,118 of the rows",
   A["monday"], "2026-03")

# ===========================================================================
print("\nB. /!\\ THE WEEK GRAIN IS DELIBERATELY UNTOUCHED")
# ===========================================================================
# The week of 29 December genuinely contains 1-4 January, and the bucket's
# label says which week it is - so drawing it at the edge of a window is
# honest, not a bug. Changing it would move every point on every weekly
# chart this page draws.
for d in ('2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04'):
    eq("B1  %s still belongs to the week of 29 Dec" % d, A["week"][d], "2025-12-29")
eq("B2  and the 5th starts the next week", A["week"]["2026-01-05"], "2026-01-05")

# ===========================================================================
print("\nC. the guards")
# ===========================================================================
eq("C1  an unparseable date is still a null bucket, not a junk one",
   A["junk"], None)
eq("C2  ...and so is a blank", A["blank"], None)
ok("/^\\d{4}-\\d{2}$/.test(own) ? own : pnlGrainKey(wk, 'month')" in BUCKET,
   "C3  /!\\ a date the shared helper cannot shape falls back to the Monday's "
   "month rather than becoming a bucket key of its own")
ok("pnlGrainKey(" in BUCKET,
   "C4  through the shared grain helper, not a second slice(0,7)")

# ===========================================================================
print("\nD. the reason is recorded where the next reader will be")
# ===========================================================================
ok("Walmart weeks are stamped SATURDAY" in js,
   "D1  /!\\ the feed that makes this non-obvious is named in the code")
ok("i have year to date selected" in js, "D2  and so is the report")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
