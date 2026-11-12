#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.18 - a marked-down unit was not replenished at standard cost.

Jason: "these numbers still don't make sense" ... "when i change the reporting
period the TACOS % looks more correct" ... "i'm not changing any more reports
until you get to the bottom of this".

The whole 47-week sell-through feed runs $6-8 a unit. TWO weeks do not:
2026-07-25 at $2.00 (3,021 units) and 2026-08-01 at $3.12 (710 units). A
clearance - SP-0204 and SP-0352 sold at $6.99 in every other week of the feed
and went to $1.14 in those two. A return the following week came back at $1.12,
so these are real transactions, not a parse error.

`our revenue = sell-through units x cost_per_each` assumes every unit sold out
was bought from us at the agreement price. On a clearance Walmart liquidates
stock it ALREADY paid for, so the model credits us again for goods already
invoiced.

/!\ AND THE TELL IS SELF-EVIDENT: the modelled revenue came out ABOVE the
retail it sold for - $13,205 against $8,255. On 1P that cannot happen.

/!\ WHAT IT WAS DOING TO THE CARD: 43% of the 24-week denominator was phantom,
so the WIDER window read 64.4% while the recent one - which holds no markdown
- read 175.3%. The wider period looked healthier only because it swallowed
the clearance.
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


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.18  the markdown cap")
print("=" * 70)

LOAD = fn_flat("adsLoadOurRev")
m = re.search(r"const sql = .(select w\.week_start,[\s\S]*?group by 1 order by 1).;", LOAD)
ok(m is not None, "A0  the Walmart revenue SQL was found")
SQL = m.group(1)

# ===========================================================================
print("\nA. the cap is IN THE SQL, per row")
# ===========================================================================
# /!\ Per ROW, not on the week total. A week holding one marked-down SKU and
# thirty normal ones must cap only the one - capping the week's total would
# let a big normal SKU hide a markdown beside it.
ok("case when w.net_sales > 0 and w.units * c.cost_per_each > w.net_sales" in SQL,
   "A1  /!\\ the impossible row is the one capped: modelled rev above the retail it sold for")
ok("then w.net_sales else w.units * c.cost_per_each end" in SQL,
   "A2  ...and it is capped at what the units ACTUALLY sold for")
# /!\ THE RETURNS TRAP. A return carries NEGATIVE units and negative sales;
# least() would make the refund LARGER than it was. The guard requires
# net_sales > 0, so a refund passes through untouched.
ok("w.net_sales > 0 and" in SQL,
   "A3  /!\\ only when net_sales > 0 - a return must not be 'capped' into a bigger refund")
ok("least(" not in SQL,
   "A4  /!\\ and least() is NOT used, which would have done exactly that")
ok("sum(w.units * c.cost_per_each) rev_raw" in SQL,
   "A5  the uncapped figure is kept, so the shortfall is a measurement")
ok("then 1 else 0 end) capped" in SQL,
   "A6  ...and the capped rows are counted")

# ===========================================================================
print("\nB. /!\\ THE DEFECT REPRODUCED on the real two weeks")
# ===========================================================================
DRIVER = r"""
'use strict';
// The two clearance weeks and their neighbours, as the feed holds them.
const ROWS = [
  // week          units  cost_per_each  net_sales
  ['2026-07-18',   192,  2.7590,         1400.39],   // normal, $7.29/u retail
  ['2026-07-25',  3021,  3.5592,         6042.55],   // /!\ clearance, $2.00/u
  ['2026-08-01',   710,  3.4545,         2213.21],   // /!\ clearance, $3.12/u
  ['2026-08-08',   120,  2.8804,          966.81],   // normal, $8.06/u retail
  ['2026-08-15',    -1,  3.0000,           -1.12],   // /!\ a RETURN
];
const modelled = (u, c) => u * c;
// the shipped rule, transcribed from the SQL
const capped = (u, c, net) => (net > 0 && u * c > net) ? net : u * c;

let raw = 0, cap = 0, nCapped = 0; const mdWeeks = [];
for (const [w, u, c, net] of ROWS) {
  raw += modelled(u, c);
  const v = capped(u, c, net);
  cap += v;
  if (v !== modelled(u, c)) { nCapped++; mdWeeks.push(w); }
}
const SPEND = 15998.47;
console.log(JSON.stringify({
  raw: +raw.toFixed(2), cap: +cap.toFixed(2), nCapped, mdWeeks,
  ret:  capped(-1, 3.00, -1.12),
  norm: +capped(192, 2.7590, 1400.39).toFixed(2),
  tacosRaw: +(100 * SPEND / raw).toFixed(1),
  tacosCap: +(100 * SPEND / cap).toFixed(1),
}));
"""
B = run_node(os.path.join(SP, "_v1218_b.js"), DRIVER)

ok(B["raw"] > B["cap"], "B1  /!\\ the uncapped model credits MORE than the capped one",
   (B["raw"], B["cap"]))
eq("B2  /!\\ both clearance weeks are caught", B["mdWeeks"], ["2026-07-25", "2026-08-01"])
eq("B3  ...and only those two", B["nCapped"], 2)
# /!\ THE REGRESSION GUARD. Uncapped, TACoS reads better than reality - which
# is exactly what made the WIDER window look healthier than the narrow one.
ok(B["tacosRaw"] < B["tacosCap"],
   "B4  /!\\ uncapped TACoS reads LOWER - the defect Jason saw",
   (B["tacosRaw"], B["tacosCap"]))
eq("B5  /!\\ a RETURN passes through untouched, sign intact", B["ret"], -3.0)
eq("B6  a normal row passes through untouched", B["norm"], 529.73)

# ===========================================================================
print("\nC. the shortfall is CARRIED, not swallowed")
# ===========================================================================
ok("cappedAmt: Math.max(0, (Number(x.rev_raw) || 0) - (Number(x.rev) || 0))" in LOAD,
   "C1  the per-week shortfall is derived from both figures")
ok("cappedWeeks: wk.filter(x => x.capped > 0).map(x => x.w)" in LOAD,
   "C2  ...and the markdown weeks are NAMED, not counted")
TAC = fn_flat("adsTacosFor")
ok("cappedRows: r.cappedRows || 0" in TAC and "cappedWeeks: r.cappedWeeks || []" in TAC,
   "C3  all three ride the TACoS result")

# ===========================================================================
print("\nD. /!\\ AND THE CARD SAYS IT IS A FLOOR, NOT THE FIGURE")
# ===========================================================================
# Capping at RETAIL is a true upper bound on revenue, so the printed TACoS is
# a true LOWER bound. Printing a bounded number as if it were the figure is
# the v10.19 defect; saying so is the whole difference.
ok("markdown week" in js, "D1  the sub-line marks a window holding a markdown")
ok("SO THIS IS A FLOOR" in js, "D2  /!\\ and the tooltip says the real figure is HIGHER")
ok("vendor remittance feed" in js,
   "D3  ...and names the feed that would settle it rather than implying this one can")
# /!\ NO STALE LITERAL. A percentage typed into a tooltip is wrong the next
# time the data moves - the v11.72 rule.
ok("131.6%" not in js, "D4  /!\\ no hardcoded percentage in the tooltip")

print("\nE. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "E1  both declare a version")
eq("E2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
