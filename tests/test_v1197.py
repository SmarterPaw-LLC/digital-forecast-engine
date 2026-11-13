#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.97 - the Units Sold chart joins the shared chart controls.

Jason: "can you add the functionality of the other charts to the units sold
page chart?"

  * A  static: the four controls come from the SHARED helpers, and VIEW is
       deliberately absent because this page has a superset of it.
  * B  the real salesBucketDays: the span a bucket key covers.
  * C  /!\ the goal proration - byte-identical on a week bucket, and a month
       bucket worth exactly that month's goal.
  * D  /!\ THE DEFECT A MONTHLY GRAIN WOULD HAVE CAUSED: a raw string compare
       puts '2026-10' BELOW '2026-10-05', so the coverage band would have
       missed the month holding the gap.
  * E  the bucket label, and one spelling of it.
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


def nocomment(t):
    return re.sub(r"(?m)^\s*//.*$", "", t)


def fn_flat(name):
    i = js.index("function " + name + "(")
    return js[i:js.index("\n}", i) + 2]


def line_of(pattern):
    return re.search(pattern, js, re.M).group(0)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.97  the Units Sold chart's controls")
print("=" * 68)

SALES = nocomment(fn_flat("updateSalesChart"))

# ===========================================================================
print("\nA. the controls come from the shared helpers")
# ===========================================================================
# v12.35 - the rerender ARGUMENT is refreshSalesChart now, because
# updateSalesChart is what BUILDS salesRawWeekData: repainting only the
# visible tab left By Channel drawing the PREVIOUS setting's buckets. The
# guarantee is that all five come from the SHARED helpers and that every
# one passes THE SAME rerender name - stronger than pinning the literal,
# and it is what keeps the strip coherent.
for h in ("pnlGrainStepperHtml('refreshSalesChart'", "pnlBandsStepperHtml('refreshSalesChart')",
          "pnlFillToggleHtml('refreshSalesChart')", "pnlScaleToggleHtml('refreshSalesChart')",
          "pnlCompareToggleHtml('refreshSalesChart', _salesCmp)"):
    ok(h in SALES, "A1  %s" % h.split("(")[0])
_names = set(re.findall(r"pnl(?:GrainStepper|BandsStepper|FillToggle|ScaleToggle|CompareToggle)Html\('([A-Za-z]+)'", SALES))
ok(_names == {'refreshSalesChart'},
   'A1b /!\\ every control in this strip passes the SAME rerender name', sorted(_names))

# /!\ VIEW IS DELIBERATELY ABSENT. This page's own chart-type picker is a
# SUPERSET of Line / Stacked, and injecting the shared toggle beside it would
# be two controls for one decision.
ok("pnlInjectChartModeToggle" not in SALES,
   "A2  /!\\ the shared VIEW toggle is NOT injected beside the page's own picker")
ok("salesChartType" in s, "A3  ...and that picker is still there")

# Week and month only, with the reason on the one it refuses.
ok("const SALES_GRAIN_ALLOWED = ['week', 'month'];" in js,
   "A4  /!\\ day is not a grain these feeds carry")
ok("SALES_GRAIN_WHY" in SALES, "A5  ...and the refused button carries the reason")
ok("only Shopify is daily" in js, "A6  ...which names why")

# FILL only where a fill exists (v11.74 / v10.19).
ok("(useArea || chartTypeReq === 'stacked') ? pnlFillToggleHtml" in SALES,
   "A7  /!\\ FILL renders only on a chart that HAS a fill")
# BANDS keeps its own v10.67 condition.
ok("_show ? pnlBandsStepperHtml" in SALES, "A8  BANDS keeps its own condition")
# The host is always shown now, because GROUP/SCALE/COMPARE always apply.
ok("_bandsHost.style.display = 'inline-flex';" in SALES,
   "A9  the control row is always rendered")

# The compare state is decided ONCE and read twice.
# v12.37 - all time now RESOLVES a `from` (the earliest row this page can
# draw), so "is there a start" stopped being the test. The guarantee is
# unchanged: decided once, read twice, and refused where there is nothing
# before the window to measure against.
ok("const _salesCmp = (from && to && !_salesWin.allTime)" in SALES,
   "A10 the compare state is decided once")
ok(SALES.count("_salesCmp.ok") == 1 and SALES.count("_salesCmp)") == 1,
   "A11 /!\\ ...and the control and the overlay read the same answer")
ok("getPnlPrevDateRange({ from: salesIsoOf(from), to: salesIsoOf(to) })" in SALES,
   "A12 /!\\ the prior window comes from the shared resolver")
ok("stack: '_prev'" in js, "A13 the overlay keeps its own stack group")
ok("if (_salesPrevDs) datasets.push(_salesPrevDs);" in SALES,
   "A14 /!\\ ...and is pushed LAST, after the goal")

# One ceiling helper, on both charts.
# /!\ THREE, NOT TWO: pnlTrendRender has carried this since v11.63 and the two
# Units Sold charts join it. My first count forgot the one that existed.
eq("A15 both Units Sold charts joined the one that already had a ceiling",
   len(re.findall(r"grace: PNL_SCALE_GRACE, \.\.\.pnlScaleCeiling\(datasets", js)), 3)
# One bucket-label spelling.
eq("A16 /!\\ one bucket label, not one per chart",
   js.count("const fmtWeek = salesBucketLabel;"), 2)
ok("const fmtWeek = w => {" not in js, "A17 ...and the two copies are gone")
# The subtitle stops saying 'weeks' when it is drawing months.
ok("${salesGrain === 'month' ? 'months' : 'weeks'}" in SALES,
   "A18 the subtitle names the bucket it drew")
# /!\ A FLOOR UNDER THE TITLE COLUMN. `flex:1` with no min-width collapses to
# MIN-CONTENT when the row runs out of room, and three more controls was
# enough: measured at 1024px the title shrank to 63px and the subtitle wrapped
# into a 417px-tall vertical ribbon. Caught in a browser.
ok('style="flex:1 1 240px;min-width:240px"' in s,
   "A19 /!\\ the drill header's title column cannot collapse")
ok('<div class="ds-hdr" style="flex:0 0 auto;flex-wrap:wrap">' in s,
   "A20 ...and the controls wrap among themselves instead")

# ===========================================================================
print("\nB. the real salesBucketDays")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1197_b.js"),
    line_of(r"^const _salesDaysInMonth = .*$") + "\n"
    + fn_flat("parseLocalDate") + "\n" + fn_flat("salesBucketDays") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const iso = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const wk = salesBucketDays('2026-10-05');
t('B1  a week bucket is seven days', wk.length, 7);
t('B2  ...from its own Monday', iso(wk[0]), '2026-10-05');
t('B3  ...to the Sunday', iso(wk[6]), '2026-10-11');
const mo = salesBucketDays('2026-10');
t('B4  /!\\ a month bucket is that month’s days', mo.length, 31);
t('B5  ...the first', iso(mo[0]), '2026-10-01');
t('B6  ...and the last', iso(mo[30]), '2026-10-31');
t('B7  a short month is short', salesBucketDays('2026-02').length, 28);
t('B8  /!\\ and a leap February is not', salesBucketDays('2028-02').length, 29);
// A week that straddles a month boundary still walks seven real days.
const str = salesBucketDays('2026-09-28');
t('B9  a straddling week crosses the boundary',
  [iso(str[0]), iso(str[6])].join('..'), '2026-09-28..2026-10-04');
t('B10 junk answers null rather than a bad span', salesBucketDays('nope'), null);
t('B11 ...and so does nothing at all', salesBucketDays(''), null);
console.log(JSON.stringify(out));
""")
for c in B:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nC. /!\\ the goal proration, beside the rule it replaced")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1197_c.js"),
    line_of(r"^const _salesMonthKey\s+= .*$") + "\n"
    + line_of(r"^const _salesDaysInMonth = .*$") + "\n"
    + fn_flat("parseLocalDate") + "\n" + fn_flat("salesBucketDays") + "\n"
    + "let salesGoals = {}, salesGoalsOn = true;\n"
    + fn_flat("salesGoalWeeklyFor") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
// October 2026: 31 days. 3,100 units => exactly 100/day.
// /!\ THE TWO MONTHS MUST NOT SHARE A DAILY RATE, or the straddling-week
// assertion below cannot tell the two prorations apart - my first fixture set
// November to 3,000 over 30 days, which is also 100/day, so a week spanning
// the boundary came out identical to a whole October week and the assertion
// proved nothing. November is 1,500 over 30 days: 50/day.
salesGoals = { amazon_us: { '2026-10': 3100, '2026-11': 1500 } };

// The RETIRED rule, restated: always seven days from the Monday.
function v1196(weeks, chans) {
  const covered = mk => chans.some(ch => (salesGoals[ch] || {})[mk] != null);
  let any = false;
  const out = weeks.map(w => {
    const mon = parseLocalDate(w);
    if (!mon) return null;
    let total = 0;
    for (let i = 0; i < 7; i++) {
      const d = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + i);
      const mk = _salesMonthKey(d);
      if (!covered(mk)) return null;
      const dim = _salesDaysInMonth(d.getFullYear(), d.getMonth());
      chans.forEach(ch => { const g = (salesGoals[ch] || {})[mk]; if (g != null) total += Number(g) / dim; });
    }
    any = true;
    return Math.round(total * 10) / 10;
  });
  return any ? out : null;
}

const WEEKS = ['2026-10-05', '2026-10-12', '2026-10-19', '2026-10-26'];
const now = salesGoalWeeklyFor(WEEKS, ['amazon_us'], false);
const was = v1196(WEEKS, ['amazon_us']);
// /!\ THE ONLY FORM IN WHICH "NO WEEKLY GOAL MOVED" IS CHECKABLE.
t('C1  /!\\ a week bucket is byte-identical to the retired rule',
  JSON.stringify(now), JSON.stringify(was));
t('C2  ...and it is the real number', now[0], 700);
// The week of 10-26 straddles into November, which is prorated at ITS rate.
// 26-31 Oct at 100/day = 600, plus 1 Nov at 50 = 650.
t('C3  /!\\ a straddling week mixes the two months’ rates', now[3], 650);

// /!\ A MONTH BUCKET IS WORTH THAT MONTH'S GOAL, EXACTLY.
const mo = salesGoalWeeklyFor(['2026-10', '2026-11'], ['amazon_us'], false);
t('C4  /!\\ October is its own goal', mo[0], 3100);
t('C5  /!\\ November too', mo[1], 1500);
t('C6  ...so the two bases agree on the month',
  Math.round(mo[0]) , 3100);

// A month with no goal set is null, not zero - the same refusal as a week.
const gap = salesGoalWeeklyFor(['2026-10', '2026-12'], ['amazon_us'], false);
t('C7  an uncovered month is null, never zero', gap[1], null);
t('C8  ...and the covered one still reports', gap[0], 3100);
console.log(JSON.stringify(out));
""")
for c in C:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nD. /!\\ the coverage trap a monthly grain would have sprung")
# ===========================================================================
D = run_node(os.path.join(SP, "_v1197_d.js"),
    "const SALES_CHANNELS = { amazon_us: { label: 'Amazon US', color: '#4a9e38' },"
    " chewy: { label: 'Chewy', color: '#a855f7' } };\n"
    + "let salesLatestByChannel = {};\n" + fn_flat("salesCoverage") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
salesLatestByChannel = { amazon_us: '2026-11-02', chewy: '2026-09-28' };

// /!\ THE RAW COMPARE, restated: a month key is a PREFIX of a week key in
// that month, and a prefix sorts BELOW it.
t('D1  /!\\ the string trap is real', '2026-10' > '2026-09-28', true);
t('D2  /!\\ ...and this is the half that breaks', '2026-10' > '2026-10-05', false);

const WEEKS = ['2026-09-07', '2026-10-05', '2026-11-02'];
const cw = salesCoverage(WEEKS, ['amazon_us', 'chewy'], null);
t('D3  weekly: Chewy’s gap opens at the next week',
  cw.channels.find(c => c.ch === 'chewy').firstGap, '2026-10-05');
t('D4  ...and a current channel has none',
  cw.channels.find(c => c.ch === 'amazon_us').firstGap, null);

const MONTHS = ['2026-09', '2026-10', '2026-11'];
const cm = salesCoverage(MONTHS, ['amazon_us', 'chewy'], null);
t('D5  /!\\ monthly: the gap lands on the month AFTER the last report',
  cm.channels.find(c => c.ch === 'chewy').firstGap, '2026-10');
t('D6  /!\\ and the up-to-date channel still has none',
  cm.channels.find(c => c.ch === 'amazon_us').firstGap, null);
// The DISPLAY date stays the real week - the bucketing is for the find only.
t('D7  /!\\ the channel still reports its real last WEEK',
  cm.channels.find(c => c.ch === 'chewy').last, '2026-09-28');
t('D8  ...and the stale count is right', cm.staleCount, 1);
// An empty chart answers rather than throwing.
t('D9  no buckets, no coverage', salesCoverage([], ['chewy'], null).channels.length, 0);
console.log(JSON.stringify(out));
""")
for c in D:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ===========================================================================
print("\nE. the bucket label")
# ===========================================================================
E = run_node(os.path.join(SP, "_v1197_e.js"), fn_flat("salesBucketLabel") + r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
// /!\ A WEEK LABEL IS UNCHANGED, which is how "nothing moved by default" is
// checkable on the axis as well as in the data.
t('E1  /!\\ a week reads exactly as it did', salesBucketLabel('2026-10-05'), '10/5/26');
t('E2  ...including a two-digit day', salesBucketLabel('2026-10-26'), '10/26/26');
t('E3  /!\\ a month reads as a month', salesBucketLabel('2026-10'), 'Oct 26');
t('E4  ...and January is not December', salesBucketLabel('2027-01'), 'Jan 27');
t('E5  junk does not throw', typeof salesBucketLabel(''), 'string');
console.log(JSON.stringify(out));
""")
for c in E:
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

chip = re.search(r'margin-left:4px">v(\d+\.\d+)', s).group(1)
cmd = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", errors="replace").read()
doc = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cmd).group(1)
eq("E6  the chip and CLAUDE.md agree", doc, chip)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
