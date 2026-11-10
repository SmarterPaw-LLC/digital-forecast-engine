#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.74 - a GROUP control on every trend chart, and the band fill as a setting.

Jason: "1. let me change the date grouping period so i can see down to daily
granularity and up to monthly. 2. the seo report has a transparency on the
stacked items, i like this but want it to be a toggle and available on other
reports as well"

Neither was a setting. The GRAIN rule existed twice - `adsGrain` picked
day/week/month off the window width, the SEO chart had its own cruder
`span > 70` that could not reach monthly at all - and neither could be
overridden. The FILL was two different alphas three call sites apart:
pnlTrendSeries painted 'd9', the SEO chart painted '55', and the one Jason
likes was the accident.

  * A  the real pnlGrainAuto / pnlGrainResolve: the width rule, the override,
       and the per-chart CLAMP - a chart cannot invent a grain its rows lack.
  * B  the real pnlGrainKey. /!\ A week_start is already a Monday, so the
       weekly default round-trips BYTE-IDENTICAL.
  * C  /!\ THE DEFECT REPRODUCED - both retired rules run beside the shared
       one.
  * D  the real fill setting: sheer by default, solid still reachable.
  * E  the real pnlGrainStepperHtml: it lights the EFFECTIVE grain, never the
       stored one, and refuses with the reason.
  * F  static: one alpha definition, no stray band literals, and every chart
       declares what its rows can carry.
"""
import io, os, re, sys, json, subprocess

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


def _bal(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ""
    while k < n:
        c = js[k]
        if c == "/" and k + 1 < n and js[k + 1] == "/":
            while k < n and js[k] != "\n":
                k += 1
            continue
        if c == "/" and k + 1 < n and js[k + 1] == "*":
            k = js.index("*/", k) + 2
            continue
        if c == "/" and prev in "(,=:[!&|?{};+-*%~^<>":
            k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == "[":
                    while k < n and js[k] != "]":
                        k += 2 if js[k] == "\\" else 1
                if js[k] == "/":
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = "x"
            continue
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = "x"
            continue
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise SystemExit("unbalanced at %d" % i)


def fn(name, kw="function"):
    pat = kw + " " + name + "("
    i = js.index(pat)
    head = js.index("{", i)
    j = i
    while j > 0 and js[j - 1] != "\n":
        j -= 1
    return js[j:head] + _bal(head)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])



print("\n" + "=" * 68)
print("v11.74 - group by day / week / month, and the fill as a setting")
print("=" * 68)

NC = nocomment(js)

CONSTS = (re.search(r"const PNL_GRAIN_ORDER = \[[^\]]*\];", js).group(0) + "\n"
          + re.search(r"const PNL_FILL_ALPHA = \{[^}]*\};", js).group(0) + "\n"
          + re.search(r"const PNL_FILL_LINE = '[^']*';", js).group(0) + "\n")
GRAIN = (CONSTS + fn("pnlChartGrain") + "\n" + fn("pnlGrainAuto") + "\n"
         + fn("pnlGrainResolve") + "\n" + fn("pnlGrainKey") + "\n" + fn("pnlGrainAdv") + "\n")
LS = """
const _ls = {};
const localStorage = { getItem: k => (k in _ls ? _ls[k] : null),
                       setItem: (k, v) => { _ls[k] = String(v); } };
"""

# ---------------------------------------------------------------------------
print("\nA. the real pnlGrainAuto / pnlGrainResolve")
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "_v1174_a.js"), LS + GRAIN + r"""
const w = (f, t) => ({ from: f, to: t });
const W30  = w('2026-10-10', '2026-11-08');   // 30 days
const W180 = w('2026-05-11', '2026-11-08');   // 182 days
const W700 = w('2024-12-01', '2026-11-08');
const PNL = ['week', 'month'];                // the four P&L charts
const MON = ['month'];                        // Walmart ads (v11.67)
const set = v => { if (v == null) delete _ls.pnlChartGrain; else _ls.pnlChartGrain = v; };
const out = {};
set(null);
out.auto30  = pnlGrainAuto(W30);
out.auto180 = pnlGrainAuto(W180);
out.auto700 = pnlGrainAuto(W700);
out.autoNoWin = pnlGrainAuto(null);
out.auto70  = pnlGrainAuto(w('2026-09-01', '2026-11-09'));   // exactly 70
out.auto71  = pnlGrainAuto(w('2026-08-31', '2026-11-09'));   // 71
// AUTO everywhere = exactly what every chart did before this release.
out.resAuto30 = pnlGrainResolve(W30, PNL_GRAIN_ORDER);
out.resAuto180 = pnlGrainResolve(W180, PNL_GRAIN_ORDER);
// THE OVERRIDE
set('month'); out.pickMonth = pnlGrainResolve(W30, PNL_GRAIN_ORDER);
set('day');   out.pickDay   = pnlGrainResolve(W700, PNL_GRAIN_ORDER);
// THE CLAMP: a weekly-row chart cannot honour 'day'.
set('day');   out.pnlDay    = pnlGrainResolve(W30, PNL);
set('month'); out.pnlMonth  = pnlGrainResolve(W30, PNL);
set(null);    out.pnlAuto30 = pnlGrainResolve(W30, PNL);       // auto says day
// Walmart ads: monthly or nothing.
set('day');   out.wmDay     = pnlGrainResolve(W30, MON);
set(null);    out.wmAuto    = pnlGrainResolve(W30, MON);
// junk in the store is not a grain
set('fortnightly'); out.junk = pnlGrainResolve(W180, PNL_GRAIN_ORDER);
set(null);
out.noAllowed = pnlGrainResolve(W30, null);
out.emptyAllowed = pnlGrainResolve(W30, []);
out.adv = [pnlGrainAdv('day'), pnlGrainAdv('week'), pnlGrainAdv('month')];
console.log(JSON.stringify(out));
""")

eq("A1  under 70 days auto is daily", A["auto30"], "day")
eq("A2  180 days is weekly", A["auto180"], "week")
eq("A3  past 400 days is monthly", A["auto700"], "month")
eq("A4  no window answers weekly rather than throwing", A["autoNoWin"], "week")
eq("A5  the 70-day edge is inclusive", [A["auto70"], A["auto71"]], ["day", "week"])
ok(A["resAuto30"] == "day" and A["resAuto180"] == "week",
   "A6  /!\\ AUTO resolves to exactly the old rule - nothing moved by default",
   (A["resAuto30"], A["resAuto180"]))
eq("A7  a stored MONTH beats a 30-day window", A["pickMonth"], "month")
eq("A8  a stored DAY beats a two-year window", A["pickDay"], "day")
eq("A9  /!\\ a weekly-row chart CLAMPS 'day' to week", A["pnlDay"], "week")
eq("A10 and still honours 'month'", A["pnlMonth"], "month")
eq("A11 auto saying 'day' on a weekly chart clamps COARSER, never finer",
   A["pnlAuto30"], "week")
eq("A12 /!\\ Walmart ads refuse anything but monthly", A["wmDay"], "month")
eq("A13 and their auto is monthly too", A["wmAuto"], "month")
eq("A14 a junk stored value falls back to auto", A["junk"], "week")
ok(A["noAllowed"] == "day" and A["emptyAllowed"] == "day",
   "A15 no declared allow-list means every grain", (A["noAllowed"], A["emptyAllowed"]))
eq("A16 the adverb helper, one per grain", A["adv"], ["daily", "weekly", "monthly"])

# ---------------------------------------------------------------------------
print("\nB. the real pnlGrainKey")
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "_v1174_b.js"), LS + GRAIN + r"""
// Real week_start values out of this database: always a MONDAY.
const MONDAYS = ['2026-10-05', '2026-10-12', '2026-10-19', '2026-10-26'];
console.log(JSON.stringify({
  // /!\ THE WHOLE "nothing changed by default" CLAIM, measured.
  weekRoundTrip: MONDAYS.map(d => pnlGrainKey(d, 'week')),
  identical: MONDAYS.every(d => pnlGrainKey(d, 'week') === d),
  dayIsItself: pnlGrainKey('2026-11-08', 'day'),
  monthOf:     MONDAYS.map(d => pnlGrainKey(d, 'month')),
  // a mid-week day still files under its Monday
  wedToMonday: pnlGrainKey('2026-11-04', 'week'),
  sunToMonday: pnlGrainKey('2026-11-08', 'week'),
  // /!\ a week STRADDLING a month start files under the month it BEGINS in
  straddle:    pnlGrainKey('2026-10-26', 'month'),
  // already a month key, or junk, passes straight through
  monthKey:    pnlGrainKey('2026-10', 'week'),
  empty:       pnlGrainKey('', 'week'),
  nully:       pnlGrainKey(null, 'month'),
  // a timestamp is truncated to its day rather than refused
  stamped:     pnlGrainKey('2026-11-04T13:22:00Z', 'day'),
}));
""")

eq("B1  /!\\ a week_start round-trips BYTE-IDENTICAL on the weekly default",
   B["weekRoundTrip"], ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"])
ok(B["identical"], "B1b so every P&L chart's default buckets are unchanged")
eq("B2  a day is itself", B["dayIsItself"], "2026-11-08")
eq("B3  month keys are YYYY-MM", B["monthOf"], ["2026-10", "2026-10", "2026-10", "2026-10"])
eq("B4  a Wednesday files under its Monday", B["wedToMonday"], "2026-11-02")
eq("B5  and so does a Sunday", B["sunToMonday"], "2026-11-02")
eq("B6  /!\\ a straddling week files under the month it STARTS in",
   B["straddle"], "2026-10")
eq("B7  a month key is not re-keyed", B["monthKey"], "2026-10")
eq("B8  blank and null pass through rather than throwing", [B["empty"], B["nully"]], ["", ""])
eq("B9  a timestamp truncates to its day", B["stamped"], "2026-11-04")

# ---------------------------------------------------------------------------
print("\nC. /!\\ THE DEFECT REPRODUCED - both retired rules beside the shared one")
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, "_v1174_c.js"), LS + GRAIN + r"""
// The SEO chart's OWN rule, retired this release.
const seoOld = (w) => ((new Date(w.to) - new Date(w.from)) / 864e5) > 70 ? 'week' : 'day';
// adsGrain's rule, retired into pnlGrainAuto.
const adsOld = (win) => {
  if (!win || !win.from || !win.to) return 'week';
  const days = Math.round((new Date(win.to + 'T00:00:00') - new Date(win.from + 'T00:00:00')) / 86400000) + 1;
  if (!isFinite(days) || days <= 0) return 'week';
  if (days <= 70) return 'day';
  if (days <= 400) return 'week';
  return 'month';
};
const WINS = [['2026-10-10','2026-11-08'], ['2026-05-11','2026-11-08'], ['2024-12-01','2026-11-08']];
delete _ls.pnlChartGrain;
console.log(JSON.stringify({
  adsOld:   WINS.map(([f,t]) => adsOld({from:f,to:t})),
  adsNew:   WINS.map(([f,t]) => pnlGrainResolve({from:f,to:t}, PNL_GRAIN_ORDER)),
  seoOld:   WINS.map(([f,t]) => seoOld({from:f,to:t})),
  seoNew:   WINS.map(([f,t]) => pnlGrainResolve({from:f,to:t}, PNL_GRAIN_ORDER)),
}));
""")

eq("C1  /!\\ the Ads auto rule is UNCHANGED, window for window",
   C["adsNew"], C["adsOld"])
eq("C2  and that rule is day / week / month", C["adsOld"], ["day", "week", "month"])
eq("C3  /!\\ the SEO chart's own rule could never reach MONTHLY",
   C["seoOld"], ["day", "week", "week"])
eq("C4  the shared one does", C["seoNew"], ["day", "week", "month"])
ok(C["seoOld"][2] != C["seoNew"][2],
   "C5  /!\\ so a two-year SEO window was drawn in 104 weekly buckets")

# ---------------------------------------------------------------------------
print("\nD. the real fill setting")
# ---------------------------------------------------------------------------
D = run_node(os.path.join(SP, "_v1174_d.js"),
             CONSTS + LS + fn("pnlChartFill") + "\n" + fn("pnlStackAlpha") + "\n"
             + fn("pnlBandFill") + r"""
const out = {};
delete _ls.pnlChartFill;  out.dflt  = pnlStackAlpha();
_ls.pnlChartFill = 'solid'; out.solid = pnlStackAlpha();
_ls.pnlChartFill = 'sheer'; out.sheer = pnlStackAlpha();
_ls.pnlChartFill = 'nonsense'; out.junk = pnlStackAlpha();
delete _ls.pnlChartFill;
out.hexBand = pnlBandFill('#4a9e38', pnlStackAlpha());
out.hslBand = pnlBandFill('hsl(120.0, 55%, 45%)', pnlStackAlpha());
out.line    = PNL_FILL_LINE;
// A throwing store must not take the chart down with it.
out.thrown = (() => {
  const real = globalThis.localStorage;
  globalThis.localStorage = { get getItem() { throw new Error('blocked'); } };
  let v; try { v = pnlStackAlpha(); } catch (e) { v = 'THREW'; }
  globalThis.localStorage = real; return v;
})();
console.log(JSON.stringify(out));
""")

eq("D1  /!\\ SHEER is the default - the look Jason asked for, everywhere",
   D["dflt"], "55")
eq("D2  solid is still reachable", D["solid"], "d9")
eq("D3  and sheer round-trips", D["sheer"], "55")
eq("D4  junk in the store falls back to sheer", D["junk"], "55")
eq("D5  a hex band appends the alpha", D["hexBand"], "#4a9e3855")
ok(D["hslBand"].startswith("hsla(") and D["hslBand"].endswith("0.33)"),
   "D6  an hsl band converts it rather than appending (v10.67)", D["hslBand"])
eq("D7  the UNSTACKED wash is untouched at 22", D["line"], "22")
eq("D8  a blocked localStorage yields the default, never a throw", D["thrown"], "55")

# ---------------------------------------------------------------------------
print("\nE. the real pnlGrainStepperHtml")
# ---------------------------------------------------------------------------
E = run_node(os.path.join(SP, "_v1174_e.js"), LS + GRAIN + fn("esc2") + "\n"
             + fn("pnlGrainStepperHtml") + r"""
const W30 = { from: '2026-10-10', to: '2026-11-08' };
const lit = (h) => [...h.matchAll(/background:var\(--sp-green\)[\s\S]*?>([^<]+)</g)]
  .map(m => m[1].trim());
const out = {};
delete _ls.pnlChartGrain;
out.none     = pnlGrainStepperHtml('r', null);
out.autoLit  = lit(pnlGrainStepperHtml('r', { win: W30, allowed: PNL_GRAIN_ORDER }));
_ls.pnlChartGrain = 'month';
out.monthLit = lit(pnlGrainStepperHtml('r', { win: W30, allowed: PNL_GRAIN_ORDER }));
// /!\ v10.77 - a stored 'day' on a weekly-row chart must light W, not D.
_ls.pnlChartGrain = 'day';
const weekly = pnlGrainStepperHtml('r', { win: W30, allowed: ['week','month'], why: 'ROWS ARE WEEKLY' });
out.weeklyLit = lit(weekly);
out.dayDisabled = /not-allowed/.test(weekly);
out.dayHasNoHandler = !/onclick="pnlSetChartGrain\('day'/.test(weekly);
out.reasonShown = weekly.indexOf('ROWS ARE WEEKLY') >= 0;
out.weekStillClickable = /onclick="pnlSetChartGrain\('week'/.test(weekly);
delete _ls.pnlChartGrain;
out.autoAlwaysOffered = /onclick="pnlSetChartGrain\('auto'/.test(
  pnlGrainStepperHtml('r', { win: W30, allowed: ['month'] }));
console.log(JSON.stringify(out));
""")

eq("E1  /!\\ no grain declared -> NO control at all (the v10.19 rule)", E["none"], "")
eq("E2  with nothing stored, Auto is lit", E["autoLit"], ["Auto"])
eq("E3  a stored month lights M", E["monthLit"], ["M"])
eq("E4  /!\\ a stored DAY on a weekly chart lights W - the EFFECTIVE grain",
   E["weeklyLit"], ["W"])
ok(E["dayDisabled"], "E5  and D renders not-allowed")
ok(E["dayHasNoHandler"], "E6  /!\\ with its handler REMOVED, not just greyed")
ok(E["reasonShown"], "E7  the chart's own reason is on the refused button")
ok(E["weekStillClickable"], "E8  the grains it CAN do stay live")
ok(E["autoAlwaysOffered"], "E9  Auto is offered even where only one grain is allowed")

# ---------------------------------------------------------------------------
print("\nF. static")
# ---------------------------------------------------------------------------
eq("F1  one alpha definition", NC.count("const PNL_FILL_ALPHA"), 1)
eq("F2  one grain order", NC.count("const PNL_GRAIN_ORDER"), 1)
eq("F3  pnlGrainResolve declared once", NC.count("function pnlGrainResolve("), 1)
eq("F4  pnlGrainKey declared once", NC.count("function pnlGrainKey("), 1)
# /!\ rule #5: the alphas were three literals in three places. Zero may remain.
eq("F5  /!\\ no stacked band still carries a LITERAL alpha",
   len(re.findall(r"backgroundColor:[^,\n]*'(?:d9|55)'", NC)), 0)
# Five call sites plus the helper's own declaration.
# /!\ SEVEN SINCE v11.97: the Units Sold stacked-area fill joined the setting
# instead of keeping its own 'd9' literal.
eq("F6  and every stacked fill reads the shared setting",
   NC.count("pnlStackAlpha()"), 7)
eq("F7  the four P&L charts declare weekly rows",
   len(re.findall(r"pnlGrainResolve\(\{ from, to \}, \['week', 'month'\]\)", NC)), 4)
eq("F8  the SEO chart offers all three",
   NC.count("pnlGrainResolve({ from: w.from, to: w.to }, PNL_GRAIN_ORDER)"), 1)
eq("F9  the Ads allow-list is declared once", NC.count("function adsGrainAllowed("), 1)
ok("const weekly = span > 70;" not in NC,
   "F10 /!\\ the SEO chart's own grain rule is GONE, not left beside the new one")
# The fill toggle is stacked-only, same rule the BANDS stepper follows.
ok("(mode === 'stacked' ? pnlFillToggleHtml(rerenderName) : '')" in NC,
   "F11 the fill toggle renders in STACKED mode only")
ok("pnlGrainStepperHtml(rerenderName, grain)" in NC,
   "F12 the grain stepper renders in both modes - it describes the X AXIS")
# Four P&L + SEO + both Ads readings = seven charts that resolve a grain.
# /!\ NINE SINCE v11.97, when Units Sold joined - and it resolves ONCE for
# both its tabs, through salesChartGrain, so the Total and By Channel charts
# cannot draw different buckets.
eq("F13 every chart that groups resolves through the one rule",
   NC.count("pnlGrainResolve("), 9)
# /!\ ONE survives, and it is correct: the Digital Sales tracker is not on
# pnlTrendRender at all (v11.60's list of six) and its feed is monthly by
# construction, so its title states a fact rather than guessing at a grain.
_rem = re.findall(r".{0,60}\b(?:weekly|daily|monthly) trend`", NC)
eq("F14 exactly one hardcoded grain word survives", len(_rem), 1)
ok("ds-chart-title" in _rem[0],
   "F14b and it is the Digital Sales tracker, monthly by construction", _rem[0])

m = re.search(r">v(\d+\.\d+) \u00b7 [\d-]+<", s)
cl = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
mc = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cl)
eq("F15 the chip and CLAUDE.md agree (v11.63's rule)",
   m and m.group(1), mc and mc.group(1))

print("\n" + "-" * 68)
print("  passed %d   failed %d" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
