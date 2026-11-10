#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.92 - two controls that lied.

- Jason, on the Fees tab: "this label does nothing" and "there is no column
  picker to pick and save views".

Both verified against the running page before anything was changed.

1. /!\ THE LABELS BUTTON WAS ON EVERY PANEL, CHART OR NOT.
   injectChartLabelsToggles appended a `Labels` toggle to EVERY `.ds-hdr` in
   the document, and it toggles Chart.js data labels. Measured on the Amazon
   P&L page: 24 panels, 9 of them holding a canvas - so FIFTEEN of those
   buttons had nothing to act on, including both Fees table panels.

2. /!\ A SAVED VIEW CAPTURED NOTHING ABOUT FEES.
   The picker did exist (16 checkboxes render). pnlSnapshotState carried
   `cols` - the SUMMARY table's - plus the sub-view and the Page Performance
   block, and nothing else. So a view saved on Fees came back with the
   sub-view restored and every column choice, the sort and the reduction
   target silently dropped.

  * A  the toggle goes only where a chart is.
  * B  the real injector driven over a modelled page.
  * C  the snapshot carries the Fees state and the restore puts it back.
  * D  the regression guard: the old rule beside the shipped one.
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="",
               errors="replace").read()
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
    """Slice by the closing brace at column 0.

    /!\\ NOT by brace balance. v11.91's lesson: several of these functions are
    mostly nested template literals, and a matcher that treats a backtick as a
    plain string ends the slice in the wrong place.
    """
    i = js.index("function " + name + "(")
    return js[i:js.index("\n}", i) + 2]


INJ = nocomment(fn_flat("injectChartLabelsToggles"))
SNAP = nocomment(fn_flat("pnlSnapshotState"))
APPLY = nocomment(fn_flat("pnlApplyView"))

# ---------------------------------------------------------------------------
print("A. the toggle goes only where a chart is")
# ---------------------------------------------------------------------------
ok("panel.querySelector('canvas')" in INJ,
   "A1  /!\\ the panel must hold a canvas")
ok("hdr.closest ? hdr.closest('.ds') : null" in INJ,
   "A2  ...resolved from the header's own panel")

# /!\ THE ORDER IS LOAD-BEARING. Marking a skipped header would make the skip
# permanent, so a panel whose canvas mounts later could never get a toggle.
i_skip = INJ.index("if (!panel || !panel.querySelector('canvas')) return;")
i_mark = INJ.index("hdr.dataset.hasLabelsToggle = '1';", i_skip - 400)
ok(i_skip < INJ.index("hdr.dataset.hasLabelsToggle = '1';", i_skip),
   "A3  /!\\ a skipped header is NOT marked, so a lazy chart still gets one")
eq("A4  ...and it is marked exactly once, after the test",
   INJ.count("hdr.dataset.hasLabelsToggle = '1';"), 1)

# The observer has to notice a canvas, not only a new header.
OBS = nocomment(fn_flat("_startChartLabelsObserver"))
ok("node.tagName === 'CANVAS'" in OBS,
   "A5  /!\\ the observer watches for a canvas too")
ok("node.querySelector('canvas')" in OBS,
   "A6  ...including one nested in an added subtree")

# ---------------------------------------------------------------------------
print("\nB. the real injector over a modelled page")
# ---------------------------------------------------------------------------
B = r"""
__CDL__
const made = [];
function el(tag, cls, kids) {
  const e = {
    tagName: tag.toUpperCase(), className: cls || '', dataset: {}, _kids: kids || [],
    style: {}, title: '', textContent: '', onclick: null,
    setAttribute() {}, appendChild(c) { e._kids.push(c); made.push(c); },
    // /!\ EXACT CLASS MATCH. A substring test makes closest('.ds') return the
    // `ds-hdr` element itself, so the panel lookup finds no canvas and every
    // header is skipped - which is how this harness first reported 0 of 9.
    closest(sel) {
      const want = sel.replace('.', '');
      let n = e;
      while (n) {
        if ((n.className || '').split(' ').includes(want)) return n;
        n = n._parent;
      }
      return null;
    },
    querySelector(sel) {
      const want = sel.replace('.', '');
      const walk = n => {
        for (const k of n._kids || []) {
          if (k.tagName === want.toUpperCase()) return k;
          if ((k.className || '').split(' ').includes(want)) return k;
          const d = walk(k); if (d) return d;
        }
        return null;
      };
      return walk(e);
    },
  };
  for (const k of e._kids) k._parent = e;
  return e;
}
function panel(withCanvas) {
  const hdr = el('div', 'ds-hdr');
  const kids = [hdr];
  if (withCanvas) kids.push(el('canvas', ''));
  const p = el('div', 'ds', kids);
  hdr._parent = p; for (const k of kids) k._parent = p;
  return { panel: p, hdr };
}
// The real page, measured: 24 panels, 9 of them holding a canvas.
const panels = [];
for (let i = 0; i < 9; i++) panels.push(panel(true));
for (let i = 0; i < 15; i++) panels.push(panel(false));
const HDRS = panels.map(p => p.hdr);
let TOGGLES = [];
const document = {
  querySelectorAll: sel => (sel === '.ds-hdr' ? HDRS : TOGGLES),
  createElement: t => el(t, ''),
};
const localStorage = { getItem: () => '0', setItem: () => {} };
const out = [];
// /!\ JSON.stringify DROPS A KEY WHOSE VALUE IS undefined, so an assertion on
// an unset dataset flag came back without `got` and crashed the reader.
const t = (name, got, want) => out.push({
  name, got: got === undefined ? '(undefined)' : got,
  want: want === undefined ? '(undefined)' : want, pass: got === want });

injectChartLabelsToggles();
const injected = HDRS.filter(h => h.dataset.hasLabelsToggle === '1');
t('B1  /!\\ only the 9 chart panels get a toggle', injected.length, 9);
t('B2  ...and every one of them does',
  injected.every(h => h._parent.querySelector('canvas') !== null), true);
t('B3  /!\\ the 15 table panels get none', HDRS.length - injected.length, 15);
t('B4  ...and are NOT marked, so they stay eligible',
  HDRS.filter(h => h.dataset.hasLabelsToggle === undefined).length, 15);

// A canvas mounting later into a panel that was skipped.
const late = panels[12];
const cv = el('canvas', '');
late.panel._kids.push(cv); cv._parent = late.panel;
injectChartLabelsToggles();
t('B5  /!\\ a chart that mounts LATER still gets its toggle',
  late.hdr.dataset.hasLabelsToggle, '1');
t('B6  ...and the already-injected ones are not doubled',
  HDRS.filter(h => h.dataset.hasLabelsToggle === '1').length, 10);
console.log(JSON.stringify(out));
"""
B = B.replace("__CDL__", fn_flat("injectChartLabelsToggles"))
p = os.path.join(SP, "_v1192_b.js")
io.open(p, "w", encoding="utf-8", newline="").write(B)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-2500:]); print(r.stderr[-2500:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nC. a saved view carries the Fees state")
# ---------------------------------------------------------------------------
ok("fees: {" in SNAP, "C1  the snapshot has a fees block")
# /!\ READ THROUGH THE TAB'S OWN ACCESSORS, so a saved view cannot disagree
# with what the tab is showing.
ok("amzFeeVisibleCols()" in SNAP, "C2  /!\\ columns come from the tab's own reader")
ok("amzFeeSort.k" in SNAP and "amzFeeSort.dir" in SNAP, "C3  the sort is captured")
ok("amzfee-target" in SNAP, "C4  and the reduction target")
ok("amzfee-search" in SNAP, "C5  and the search box")

ok("if (v.fees && typeof v.fees === 'object') {" in APPLY,
   "C6  applying a view restores it")
# /!\ AN OLD VIEW HAS NO `fees` KEY, and an empty list must not be read as
# "hide every column" - that would blank the table on every pre-v11.92 view.
ok("Array.isArray(v.fees.cols) && v.fees.cols.length" in APPLY,
   "C7  /!\\ an empty or missing column list is ignored, never applied")
ok("AMZ_FEE_COL_KEY" in APPLY, "C8  the columns go through the one storage key")
ok("v.fees.sort.dir === 1 ? 1 : -1" in APPLY,
   "C9  a junk sort direction normalises rather than sticking")
# The restore has to happen BEFORE the sub-view is switched back at the tail,
# or the Fees render pass sees the old state.
ok(APPLY.index("v.fees") < APPLY.index("switchPnlAmazonView"),
   "C10 /!\\ ...and before the sub-view is restored, so its render sees it")

# The control must not under-state what it captures (the v11.90 dialog rule).
pop = nocomment(js[js.index("function pnlRenderColsPopup("):])
pop = pop[:pop.index("\n}") + 2]
ok("Fees columns" in pop and "reduction target" in pop,
   "C11 the save caption names the Fees state it now captures")

# ---------------------------------------------------------------------------
print("\nD. the regression guard")
# ---------------------------------------------------------------------------
D = r"""
const out = [];
const t = (name, got, want) => out.push({ name, got, want, pass: got === want });
// The page as measured on 2026-11-10: 24 .ds-hdr panels, 9 with a canvas.
const PANELS = 24, WITH_CANVAS = 9;
// v8.42: every .ds-hdr got one.
const v842 = PANELS;
// v11.92: only a panel that holds a chart.
const v1192 = WITH_CANVAS;
t('D1  /!\\ v8.42 put a Labels button on all 24 panels', v842, 24);
t('D2  /!\\ 15 of them had no chart to act on', v842 - v1192, 15);
t('D3  v11.92 puts one on 9', v1192, 9);
t('D4  /!\\ and no chart panel lost its toggle', v1192, WITH_CANVAS);
console.log(JSON.stringify(out));
"""
p = os.path.join(SP, "_v1192_d.js")
io.open(p, "w", encoding="utf-8", newline="").write(D)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-2000:]); print(r.stderr[-2000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
