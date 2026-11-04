#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.54 - the global busy bar is taller, brighter, and sweeps while it works.

Jason: "can you make the loading bar a little taller and more visible? maybe
with a glint or something?"
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1154_")
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)
css = s[:s.index("</style>")]

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


def fn(name):
    i = js.index("function " + name + "(")
    d, started, k = 0, False, js.index("{", i)
    while k < len(js):
        if js[k] == "{":
            d += 1; started = True
        elif js[k] == "}":
            d -= 1
            if started and d == 0:
                return js[i:k + 1]
        k += 1
    raise SystemExit("unbalanced %s" % name)


def rule(sel):
    """The declaration block of a CSS rule, by its selector."""
    i = css.index(sel)
    return css[i:css.index("}", i) + 1]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 62)
print("  v11.54  the busy bar is taller, brighter, and sweeps")
print("=" * 62)

# ---------------------------------------------------------------------------
# A. The look is a CLASS now, because ::after is unreachable from cssText.
# ---------------------------------------------------------------------------
eq("A1 exactly one bar is ever created", js.count("id = 'globalBusyBar'"), 1)
ok("bar.className = 'gbb'" in js, "A1b and it takes the .gbb class")

# The retired inline look must be GONE, not merely overridden.
for dead in ("height:3px;width:0;z-index:99999", "box-shadow:0 0 8px rgba(232,96,26,.55)"):
    ok(dead not in s, "A2 the retired inline look is gone: %s" % dead[:28])
# /!\ Stripped of comments first, and the comment then required to survive -
# the v11.18 trap, which this file has now hit five times: the explanation of
# why cssText is gone contains the word cssText.
ok("cssText" not in nocomment(fn("ensureBusyBar")),
   "A2b and ensureBusyBar no longer writes a whole style string")
ok("a cssText string cannot" in fn("ensureBusyBar"),
   "A2c while the explanation of why is still there to grep for")

bar_rule = rule(".gbb {")
eq("A3 TALLER: 5px, where it was 3", re.search(r"height:\s*(\S+?);", bar_rule).group(1), "5px")
ok("overflow: hidden" in bar_rule,
   "A4 the bar clips its own glint - a 24% sweep at 420% would paint past it")
ok("position: fixed" in bar_rule and "top: 0" in bar_rule,
   "A5 still pinned to the top of the viewport")
ok("z-index: 99999" in bar_rule, "A5b and still above everything")
ok("pointer-events: none" in bar_rule, "A5c and still takes no clicks")
ok("transition: width .25s ease, opacity .3s ease" in bar_rule,
   "A5d the transition the renderer drives is unchanged")

# MORE VISIBLE: a third colour stop and a stronger glow than the 8px/.55 it had.
ok("var(--sp-green2)" in bar_rule, "A6 brighter: a third stop in the gradient")
m = re.search(r"box-shadow:\s*0 0 (\d+)px rgba\(232,96,26,\.(\d+)\)", bar_rule)
ok(m is not None and int(m.group(1)) > 8, "A6b a wider glow than the retired 8px",
   m and m.group(1))
ok(m is not None and float("0." + m.group(2)) > 0.55, "A6c and a stronger one than .55",
   m and m.group(2))

# ---------------------------------------------------------------------------
# B. The glint: scoped to BUSY, clipped, and off under reduced motion.
# ---------------------------------------------------------------------------
eq("B1 the keyframes are declared once", css.count("@keyframes gbbGlint"), 1)
kf = css[css.index("@keyframes gbbGlint"):]
kf = kf[:kf.index("}\n")]
ok("translateX(-110%)" in kf and "translateX(420%)" in kf,
   "B1b it sweeps from off the left edge to past the right")

glint = rule(".gbb::after {")
ok("content: ''" in glint, "B2 the glint is a pseudo-element, not a node")
ok("animation" not in glint,
   "B3 /!\\ the glint does NOT animate on the bar itself")
eq("B3b it is scoped to the busy class", css.count(".gbb-on::after {"), 2)
on = rule(".gbb-on::after {")
ok("animation: gbbGlint" in on and "infinite" in on, "B3c which runs it while busy")

rm = css[css.index("@media (prefers-reduced-motion"):]
rm = rm[:rm.index("}\n") + 2]
ok(".gbb-on::after" in rm and "animation: none" in rm,
   "B4 reduced motion turns the sweep off")

# ---------------------------------------------------------------------------
# C. The REAL renderLoadingIndicator driven, busy -> idle.
# ---------------------------------------------------------------------------
HARNESS = r"""
const OPS = [];
function mkEl(id) {
  const st = {};
  const style = {};
  // /!\ The ops log names the element by its id AT CALL TIME. ensureBusyBar
  // creates the node and assigns the id a line later, so capturing it at
  // construction logs every one of the bar's writes under an empty name.
  const el = { id, style, textContent: '', title: '', className: '' };
  for (const k of ['width', 'opacity', 'color', 'background', 'borderColor', 'display']) {
    Object.defineProperty(style, k, {
      enumerable: true,
      get() { return st[k] === undefined ? '' : st[k]; },
      set(v) { st[k] = v; OPS.push(el.id + '.' + k + '=' + v); },
    });
  }
  el.classList = {
    add(c) { if (!el.className.split(' ').includes(c)) { el.className = (el.className + ' ' + c).trim(); OPS.push(el.id + '+' + c); } },
    remove(c) { el.className = el.className.split(' ').filter(x => x && x !== c).join(' '); OPS.push(el.id + '-' + c); },
    contains(c) { return el.className.split(' ').includes(c); },
  };
  return el;
}
const NODES = {};
NODES.loadingIndicator = mkEl('loadingIndicator');
globalThis.document = {
  body: { appendChild(n) { NODES[n.id] = n; OPS.push('append:' + n.id); } },
  getElementById: (id) => NODES[id] || null,
  createElement: () => mkEl(''),
};
let _sbReads = 0, _sbWrites = 0, _busyHideTimer = null, _loadingReadyFlashTimer = null;
const _pendingLoads = new Map();
"""

C = run_node(os.path.join(SP, "c.js"), HARNESS + fn("ensureBusyBar") + "\n"
             + fn("renderLoadingIndicator") + r"""
(async () => {
  const out = {};
  // Created cold, before any work: the class and nothing else.
  const bar = ensureBusyBar();
  out.created = { id: bar.id, cls: bar.className,
                  w: bar.style.width, op: bar.style.opacity };
  // One read in flight.
  _sbReads = 1; renderLoadingIndicator();
  out.busy = { cls: bar.className, w: bar.style.width, op: bar.style.opacity };
  out.busyPill = { text: NODES.loadingIndicator.textContent,
                   color: NODES.loadingIndicator.style.color };
  // A WRITE takes the label, and the bar is the same bar.
  _sbWrites = 1; renderLoadingIndicator();
  out.savingPill = { text: NODES.loadingIndicator.textContent,
                     color: NODES.loadingIndicator.style.color };
  out.savingBar = { cls: bar.className, w: bar.style.width };
  // Idle.
  _sbReads = 0; _sbWrites = 0;
  OPS.length = 0;
  renderLoadingIndicator();
  out.beforeDebounce = { cls: bar.className, w: bar.style.width };
  await new Promise(r => setTimeout(r, 420));
  out.afterDebounce = { cls: bar.className, w: bar.style.width };
  out.opsAtComplete = OPS.slice();
  await new Promise(r => setTimeout(r, 700));
  out.faded = { cls: bar.className, w: bar.style.width, op: bar.style.opacity };
  // Busy AGAIN - the glint has to come back.
  _sbReads = 1; renderLoadingIndicator();
  out.again = { cls: bar.className, w: bar.style.width };
  console.log(JSON.stringify(out));
})();
""")

eq("C1 the bar is created with the class and nothing inline", C["created"],
   {"id": "globalBusyBar", "cls": "gbb", "w": "", "op": ""})
eq("C2 a read in flight lights it and starts the glint", C["busy"],
   {"cls": "gbb gbb-on", "w": "85%", "op": "1"})
eq("C3 the pill is unchanged: Loading, in orange", C["busyPill"],
   {"text": "\U0001f504 Loading…", "color": "var(--sp-orange)"})
eq("C3b a write still takes the label", C["savingPill"],
   {"text": "\U0001f4be Saving…", "color": "var(--sp-green)"})
eq("C3c and the bar does not change for a write", C["savingBar"],
   {"cls": "gbb gbb-on", "w": "85%"})

eq("C4 going idle does NOT complete immediately - it is debounced",
   C["beforeDebounce"], {"cls": "gbb gbb-on", "w": "85%"})
eq("C5 past the debounce the bar completes and the glint stops",
   C["afterDebounce"], {"cls": "gbb", "w": "100%"})

# /!\ The order is the point: a bar still sweeping as it runs to 100% and
# fades reads as one more request starting, not as this one finishing.
ops = C["opsAtComplete"]
ok("globalBusyBar-gbb-on" in ops, "C6 the glint is removed on completion")
ok(ops.index("globalBusyBar-gbb-on") < ops.index("globalBusyBar.width=100%"),
   "C6b and removed BEFORE the bar runs to 100%", ops)

eq("C7 then it fades and resets to zero width", C["faded"],
   {"cls": "gbb", "w": "0", "op": "0"})
eq("C8 the next request lights it again", C["again"],
   {"cls": "gbb gbb-on", "w": "85%"})

# ---------------------------------------------------------------------------
# D. Wiring: started and stopped exactly once, in the right branches.
# ---------------------------------------------------------------------------
code = nocomment(js)
eq("D1 the glint is started in exactly one place", code.count("classList.add('gbb-on')"), 1)
eq("D1b and stopped in exactly one place", code.count("classList.remove('gbb-on')"), 1)
blk = code[code.index("function renderLoadingIndicator("):][:3000]
ok(blk.index("classList.add('gbb-on')") < blk.index("classList.remove('gbb-on')"),
   "D2 started in the busy branch, stopped in the idle one")

eq("D3 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)

for phrase in ("The sweep is not decoration",
               "the glint is a ::after pseudo-element"):
    ok(phrase in s, "D4 the reasoning survives: %s" % phrase[:38])

print("\n" + "=" * 62)
print("  v11.54  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
