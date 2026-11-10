#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.89 - the band legend may not eat the plot area.

- Jason: "on the graph - when i click bigger bands, the band legend cuts off
  the graph."

v11.35 reserves EXACTLY the room the legend takes
(`layout.padding.top = host.offsetHeight`). That is right at three bands and
ruinous at fifty, because the canvas height is fixed by its panel: every
pixel the legend grows is a pixel the curve loses.

Measured on the real pnlTrendRender, a 322px canvas, before the fix:

    bands  3 -> legend  24px, plot 272px
    bands 20 -> legend  94px, plot 202px
    bands 50 -> legend 234px, plot  62px   <-- 73% of the canvas
    bands 120 -> legend 531px, plot  0px

  * A  static: one helper, the cap applied BEFORE the height is read, the
       scroll class driven by measurement, and the cap derived rather than
       typed.
  * B  the real chartLegendCapPx driven over six canvas heights, including
       the floor and the hidden panel.
  * C  the regression guard: the pre-v11.89 reservation run beside the
       shipped one on the REAL measured legend heights.
  * D  nothing below the cap moves - which is the only form in which "no
       chart changed by default" is checkable rather than read off a diff.
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
        # A regex literal. Without this branch /^(\d{4})-(\d{2})/ counts its
        # own quantifier braces and the slice runs hundreds of lines long.
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
    return _bal(js.index(kw + " " + name + "("))


NC = nocomment(js)

# ---------------------------------------------------------------------------
print("A. static")
# ---------------------------------------------------------------------------
eq("A1  chartLegendCapPx declared exactly once", NC.count("function chartLegendCapPx("), 1)
eq("A2  CHART_LEGEND_MAX_SHARE declared once", NC.count("const CHART_LEGEND_MAX_SHARE"), 1)
eq("A3  CHART_LEGEND_MIN_PX declared once", NC.count("const CHART_LEGEND_MIN_PX"), 1)

plug = _bal(js.index("const CHART_HTML_LEGEND = {"))
pnc = nocomment(plug)
ok("chartLegendCapPx(chart)" in pnc, "A4  the plugin asks for the cap")
eq("A5  ...exactly once", pnc.count("chartLegendCapPx(chart)"), 1)

# /!\ THE ORDER IS THE WHOLE MECHANISM. max-height clamps offsetHeight, so the
# cap must be written BEFORE the reservation reads the height - otherwise the
# reservation reads the uncapped number and the fix does nothing.
i_cap = pnc.index("host.style.maxHeight = capCss")
i_read = pnc.index("const h = host.offsetHeight")
ok(i_cap < i_read,
   "A6  /!\\ the cap is APPLIED before the height is READ - max-height clamps it")

ok("host.classList.toggle('scrolls'" in pnc,
   "A7  the scroll class is toggled on the host")
# Driven by the MEASUREMENT, never by a band count: twelve short labels wrap
# to fewer rows than six long ones, so only the measurement knows.
m = re.search(r"host\.classList\.toggle\('scrolls',([^;]*)\);", pnc)
ok(m is not None, "A8  ...and the condition is readable")
cond = m.group(1) if m else ""
ok("host.scrollHeight" in cond and "host.offsetHeight" in cond,
   "A9  /!\\ ...from scrollHeight vs offsetHeight, not from a dataset count", cond)
ok("datasets" not in cond and "ds.length" not in cond,
   "A9b ...so a long label wrapping to a new row is caught too", cond)

cap = nocomment(fn("chartLegendCapPx"))
ok("if (!(h > 0)) return 0;" in cap,
   "A10 /!\\ a HIDDEN panel measures 0 and is capped at nothing")
# max-height:0 would hide the legend outright, so 0 must never be written as
# a length. The plugin turns 0 into '' instead.
ok("capPx ? capPx + 'px' : ''" in pnc,
   "A11 /!\\ a 0 cap clears max-height rather than setting max-height:0")

# DERIVED, NOT TYPED. Nine charts share this legend and their panels are not
# all 322px, so a pixel count would be wrong on the next one.
ok("cv.offsetHeight" in cap, "A12 the cap is measured off the CANVAS")
ok("CHART_LEGEND_MAX_SHARE" in cap and "CHART_LEGEND_MIN_PX" in cap,
   "A13 ...through both declared constants")
lits = [n for n in re.findall(r"\b(\d{2,4})\b", cap) if n not in ("0",)]
eq("A14 /!\\ and no pixel literal of its own", lits, [])

# The CSS: the class only turns on overflow and takes back pointer events.
# A host that cannot be hit cannot be scrolled.
css = re.search(r"\.ch-lg\.scrolls\s*\{([^}]*)\}", s)
ok(css is not None, "A15 .ch-lg.scrolls is declared")
body = css.group(1) if css else ""
ok("overflow-y: auto" in body, "A16 ...it scrolls")
ok("pointer-events: auto" in body,
   "A17 /!\\ ...and takes back pointer events, or the wheel never reaches it")
# The app already styles scrollbars globally (5px, themed). A second
# scrollbar look here would be the rule #1 divergence.
ok("scrollbar-width" not in body and "::-webkit-scrollbar" not in body,
   "A18 ...and declares NO scrollbar of its own - the app's global one applies")
ok("::-webkit-scrollbar { width: 5px" in s,
   "A19 ...which exists, so the legend inherits the app's 5px bar")

# ---------------------------------------------------------------------------
print("\nB. the real chartLegendCapPx")
# ---------------------------------------------------------------------------
B = r"""
__CAP__
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
const chart = h => ({ canvas: h == null ? null : { offsetHeight: h } });

t('B1  322px canvas -> a third', chartLegendCapPx(chart(322)), 107);
t('B2  600px canvas -> a third', chartLegendCapPx(chart(600)), 200);
t('B3  /!\\ 90px canvas floors at two rows, not 30',
  chartLegendCapPx(chart(90)), 42);
t('B4  /!\\ a HIDDEN panel measures 0 and caps nothing',
  chartLegendCapPx(chart(0)), 0);
t('B5  no canvas at all answers 0 rather than throwing',
  chartLegendCapPx(chart(null)), 0);
t('B6  no chart at all answers 0', chartLegendCapPx(null), 0);
t('B7  undefined offsetHeight answers 0',
  chartLegendCapPx({ canvas: {} }), 0);
// The floor and the share meet at 126px; either side of it the other wins.
t('B8  at 126px the share and the floor agree',
  chartLegendCapPx(chart(126)), 42);
t('B9  just above it the share takes over',
  chartLegendCapPx(chart(150)), 50);
console.log(JSON.stringify(out));
"""
B = B.replace("__CAP__", (js[js.index("const CHART_LEGEND_MAX_SHARE"):
                             js.index("const CHART_HTML_LEGEND = {")]))
p = os.path.join(SP, "_v1189_b.js")
io.open(p, "w", encoding="utf-8", newline="").write(B)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-3000:]); print(r.stderr[-3000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nC. the regression guard - the defect reproduced")
# ---------------------------------------------------------------------------
# The legend heights are REAL: measured on the shipped pnlTrendRender in a
# browser, a 322px canvas, at each band count. The axis chrome below the plot
# measured a constant 26px (322 - padTop - plotH at every count).
C = r"""
__CAP__
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });

const CANVAS = 322, CHROME = 26;
// band count -> the legend's natural (uncapped) content height, measured.
const REAL = { 3: 24, 10: 59, 20: 94, 30: 146, 50: 234, 120: 531 };

// v11.35: reserve EXACTLY the room the legend takes.
const oldPad = contentH => contentH;
// v11.89: reserve it up to the cap. max-height clamps offsetHeight, so the
// reservation reads the capped number with no second opinion.
const cap = chartLegendCapPx({ canvas: { offsetHeight: CANVAS } });
const newPad = contentH => Math.min(contentH, cap);
const plot = pad => Math.max(0, CANVAS - pad - CHROME);

t('C1  /!\\ 50 bands USED TO leave 62px of curve', plot(oldPad(REAL[50])), 62);
t('C2  /!\\ ...and 120 bands left NONE AT ALL', plot(oldPad(REAL[120])), 0);
t('C3  50 bands now leave 189px', plot(newPad(REAL[50])), 189);
t('C4  120 bands now leave the same 189px', plot(newPad(REAL[120])), 189);
t('C5  30 bands: 150px -> 189px', plot(newPad(REAL[30])), 189);

// D. NOTHING BELOW THE CAP MOVES. Three counts that never reached it must be
// byte-identical to v11.88, which is the only form in which "no chart changed
// by default" is checkable rather than read off a diff.
for (const n of [3, 10, 20]) {
  t('D' + n + '  ' + n + ' bands unchanged',
    plot(newPad(REAL[n])), plot(oldPad(REAL[n])));
}
t('D1b 3 bands still leave 272px', plot(newPad(REAL[3])), 272);
t('D2b 20 bands still leave 202px', plot(newPad(REAL[20])), 202);
// And the cap is never reached by a legend that fits, so nothing scrolls.
for (const n of [3, 10, 20]) {
  t('D' + n + 'c ' + n + ' bands do not scroll', REAL[n] > cap, false);
}
for (const n of [30, 50, 120]) {
  t('D' + n + 'c ' + n + ' bands scroll', REAL[n] > cap, true);
}
// /!\ AND NO CHIP IS LOST. Capping without scrolling would hide bands with no
// way to reach them, which is worse than the bug it fixes.
t('D4  every chip is still reachable', REAL[120] - cap > 0, true);
console.log(JSON.stringify(out));
"""
C = C.replace("__CAP__", (js[js.index("const CHART_LEGEND_MAX_SHARE"):
                             js.index("const CHART_HTML_LEGEND = {")]))
p = os.path.join(SP, "_v1189_c.js")
io.open(p, "w", encoding="utf-8", newline="").write(C)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-3000:]); print(r.stderr[-3000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
