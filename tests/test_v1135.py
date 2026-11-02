#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.35 - an HTML chart legend with a hover "only" chip.

Jason, on the stacked trend charts:
"when i click an item it removes it from the report. i'd like an option for
'only' when i click that will select only that item, then cross through the
others. then i can click the others to add them back."

Chart.js draws its legend on the CANVAS, so there is nowhere to hang a second
affordance. This replaces it with an HTML overlay in the room the canvas
legend used to take.

  * A  the REAL CHART_HTML_LEGEND.afterUpdate, with a stub Chart and a
       recording DOM.
    A4 THE REBUILD GUARD. Item nodes are rebuilt only when the SERIES change.
       Rebuilding on every toggle replaces the node under the pointer, so the
       chip you just clicked vanishes until the mouse moves.
    A7 THE REGRESSION GUARD. The first cut deferred the padding update with
       requestAnimationFrame. Under a throttled rAF the callback never fires,
       the guard flag stays true FOREVER and the chart never reserves the
       room - so the plot draws under the legend for the life of the chart.
       The pre-fix scheduler is run beside the shipped one and proven stuck.
  * B  the REAL chartLegendOnly / chartLegendToggle, including the round trip
       Jason described: isolate, click others back, and "all" to restore.
  * C  the REAL delegated click listener: label -> toggle, chip -> only.
  * D  static: three charts opt in, the canvas legend is off on all three,
       and each keeps the exact show rule its canvas legend had.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0


def ok(cond, name, got=None):
    global passed, failed
    if cond:
        passed += 1; print('  ok    ' + name)
    else:
        failed += 1
        print('  FAIL  ' + name + ('' if got is None else '   got=' + ascii(got)))


def eq(name, got, want):
    ok(got == want, name, None if got == want else '%s want %s' % (ascii(got), ascii(want)))


def _balance(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ''
    while k < n:
        c = js[k]
        if c == '/' and k + 1 < n and js[k + 1] == '/':
            while k < n and js[k] != '\n':
                k += 1
            continue
        if c == '/' and k + 1 < n and js[k + 1] == '*':
            k = js.index('*/', k) + 2
            continue
        if c == '/' and prev in '(,=:[!&|?{};+-*%~^<>':
            k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == '[':
                    while k < n and js[k] != ']':
                        k += 2 if js[k] == '\\' else 1
                if js[k] == '/':
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = 'x'
            continue
        if c in '"\'`':
            q = c; k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = 'x'
            continue
        if c == '{':
            depth += 1; started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise RuntimeError('unbalanced slice at %d' % i)


def fn(name):
    i = js.index('function %s(' % name)
    head = 'async ' if js[max(0, i - 6):i] == 'async ' else ''
    k = js.index('(', i)
    depth = 0
    while k < len(js):
        if js[k] == '(': depth += 1
        elif js[k] == ')':
            depth -= 1
            if depth == 0: break
        k += 1
    brace = js.index('{', k)
    return head + js[i:brace] + _balance(brace)


def const_obj(name):
    i = js.index('const %s = {' % name)
    return 'const %s = %s;' % (name, _balance(js.index('{', i)))


def run_node(path, src):
    io.open(path, 'w', encoding='utf-8', newline='\n').write(src)
    r = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print(r.stdout); print(r.stderr); sys.exit(1)
    return json.loads(r.stdout)


# A DOM small enough to read. innerHTML stays a STRING, so the markup can be
# asserted character for character; children are parsed out of it just far
# enough to give the in-place state refresh real nodes to work on.
DOM = r"""
const LOG = [];
function mkEl(tag) {
  const el = {
    tagName: (tag || 'DIV').toUpperCase(), id: '', className: '', title: '',
    textContent: '', style: {}, parentElement: null, _kids: [], _html: '',
    classList: {
      toggle(c, on) {
        const has = el.className.split(' ').filter(Boolean);
        const i = has.indexOf(c);
        if (on && i < 0) has.push(c);
        if (!on && i >= 0) has.splice(i, 1);
        el.className = has.join(' ');
      },
      contains(c) { return el.className.split(' ').indexOf(c) >= 0; },
    },
    get children() { return el._kids; },
    get innerHTML() { return el._html; },
    set innerHTML(v) {
      el._html = v;
      // Parse just the <span class="ch-lg-i" data-i="N"> items and the one
      // .ch-lg-only inside each, which is all the state refresh touches.
      el._kids = [];
      const re = /<span class="ch-lg-i" data-i="(\d+)">([\s\S]*?)<\/span><\/span>/g;
      let m;
      while ((m = re.exec(v))) {
        const item = mkEl('span');
        item.className = 'ch-lg-i';
        item._attrs = { 'data-i': m[1] };
        const chip = mkEl('span');
        chip.className = 'ch-lg-only';
        item._chip = chip;
        chip.parentElement = item;
        item.parentElement = el;
        el._kids.push(item);
      }
    },
    getAttribute(k) { return (el._attrs || {})[k] || null; },
    querySelector(sel) { return sel === '.ch-lg-only' ? (el._chip || null) : null; },
    closest(sel) {
      let n = el;
      while (n) {
        if (('.' + n.className).split(' ').join(' ').indexOf(sel) >= 0 ||
            n.className.split(' ').indexOf(sel.slice(1)) >= 0) return n;
        n = n.parentElement;
      }
      return null;
    },
    insertBefore(node, ref) { node.parentElement = el; el._kids.push(node); return node; },
    remove() {
      const p = el.parentElement; if (!p) return;
      const i = p._kids.indexOf(el); if (i >= 0) p._kids.splice(i, 1);
      if (BYID[el.id] === el) delete BYID[el.id];
      el.parentElement = null; LOG.push('remove:' + el.id);
    },
    addEventListener(t, h) { el['_on' + t] = h; },
    get offsetHeight() { return el._h == null ? 0 : el._h; },
    set offsetHeight(v) { el._h = v; },
  };
  return el;
}
const BYID = {};
global.getComputedStyle = el => ({ position: el._pos || 'static' });
global.document = {
  getElementById: id => BYID[id] || null,
  createElement: t => {
    const e = mkEl(t);
    // Registering on id-set is what lets chartLegendHost find it again.
    let _id = '';
    Object.defineProperty(e, 'id', {
      get: () => _id,
      set: v => { _id = v; BYID[v] = e; },
    });
    return e;
  },
};
function esc2(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
// A stub Chart with the four methods the plugin uses.
function mkChart(canvas, datasets) {
  const hidden = new Set();
  return {
    canvas, data: { datasets },
    options: {},
    updates: 0,
    isDatasetVisible: j => !hidden.has(j),
    setDatasetVisibility: (j, v) => { if (v) hidden.delete(j); else hidden.add(j); },
    update() { this.updates++; },
  };
}
function mkCanvas(id, parentPos) {
  const parent = mkEl('div');
  parent._pos = parentPos || 'relative';
  const cv = mkEl('canvas');
  cv.id = id; BYID[id] = cv;
  cv.parentElement = parent; parent._kids.push(cv);
  return cv;
}
"""

CORE = DOM + '\n' + fn('chartLegendHost') + '\n' + fn('chartLegendToggle') + '\n' \
     + fn('chartLegendOnly') + '\n' + const_obj('CHART_HTML_LEGEND') + '\n'


# ══════════════════════════════════════════════ A. the plugin's afterUpdate
print('== A. the real CHART_HTML_LEGEND.afterUpdate ==')

A = run_node(os.path.join(SP, '_v1135_a.js'), CORE + r"""
const out = {};
const DS = [
  { label: 'Super Zoomies', borderColor: '#4a9e38' },
  { label: 'Catnip Spray - 4 OZ', borderColor: '#f07830' },
  { label: 'Other \u00b7 140 SKUs', backgroundColor: '#6b7280' },
];
const cv = mkCanvas('pnl-chart-canvas');
const chart = mkChart(cv, DS.map(d => ({ ...d })));
const P = CHART_HTML_LEGEND;

P.afterUpdate(chart, {}, { show: true });
const host = document.getElementById('pnl-chart-canvas-legend');
out.a1_hostMade   = !!host;
out.a1_hostClass  = host.className;
out.a1_hostInside = host.parentElement === cv.parentElement;
out.a1_html       = host.innerHTML;
out.a1_items      = host.children.length;

// A1b a STATIC parent is given a containing block; a relative one is untouched
const cv2 = mkCanvas('static-canvas', 'static');
const ch2 = mkChart(cv2, DS.map(d => ({ ...d })));
P.afterUpdate(ch2, {}, { show: true });
out.a1b_staticFixed = cv2.parentElement.style.position;
out.a1b_relUntouched = cv.parentElement.style.position || '';

// A3 show:false and a single series both render nothing
const cv3 = mkCanvas('off-canvas');
const ch3 = mkChart(cv3, DS.map(d => ({ ...d })));
P.afterUpdate(ch3, {}, { show: false });
out.a3_showFalse = document.getElementById('off-canvas-legend').innerHTML;
const cv4 = mkCanvas('one-canvas');
const ch4 = mkChart(cv4, [{ label: 'Only one' }]);
P.afterUpdate(ch4, {}, { show: true });
out.a3_single = document.getElementById('one-canvas-legend').innerHTML;

// A4 THE REBUILD GUARD
const nodes0 = host.children.slice();
chart.setDatasetVisibility(1, false);
P.afterUpdate(chart, {}, { show: true });
out.a4_sameNodes = host.children.every((n, k) => n === nodes0[k]);
out.a5_classes   = host.children.map(n => n.className);
out.a5_titles    = host.children.map(n => n.title);
out.a6_chips     = host.children.map(n => n.querySelector('.ch-lg-only').textContent);

// A6b solo -> the chip offers the way back
chart.setDatasetVisibility(0, false);
chart.setDatasetVisibility(2, false);
chart.setDatasetVisibility(1, true);
P.afterUpdate(chart, {}, { show: true });
out.a6b_chips = host.children.map(n => n.querySelector('.ch-lg-only').textContent);
out.a6b_titles = host.children.map(n => n.querySelector('.ch-lg-only').title);

// A4b changing the SERIES does rebuild
chart.data.datasets = [{ label: 'Totally different', borderColor: '#000' }, { label: 'Second', borderColor: '#111' }];
P.afterUpdate(chart, {}, { show: true });
out.a4b_rebuilt = !host.children.some(n => nodes0.indexOf(n) >= 0);

// A8 a label carrying markup renders as TEXT
const cv5 = mkCanvas('nasty-canvas');
const ch5 = mkChart(cv5, [
  { label: 'O\'Brien "Max" <b>bold</b> & 50%', borderColor: 'red' },
  { label: 'plain', borderColor: 'blue' }]);
P.afterUpdate(ch5, {}, { show: true });
out.a8_html = document.getElementById('nasty-canvas-legend').innerHTML;

// A9 afterDestroy takes the host with it
P.afterDestroy(ch5);
out.a9_gone = !document.getElementById('nasty-canvas-legend');
out.a9_hostRef = ch5.$lgHost === null;

console.log(JSON.stringify(out));
""")

eq('A1a the host is created', A['a1_hostMade'], True)
eq('A1b with the shared class', A['a1_hostClass'], 'ch-lg')
eq('A1c inside the canvas\'s own parent, so it overlays the canvas', A['a1_hostInside'], True)
eq('A1d one item per dataset', A['a1_items'], 3)
ok('class="ch-lg-i" data-i="0"' in A['a1_html'], 'A1e items are addressed by INDEX', A['a1_html'])
ok('background:#4a9e38' in A['a1_html'] and 'background:#f07830' in A['a1_html'],
   'A1f the swatch takes the series\' own colour', A['a1_html'])
ok('background:#6b7280' in A['a1_html'],
   'A1g falling back to backgroundColor when there is no borderColor', A['a1_html'])
ok('Other &#183; 140 SKUs' in A['a1_html'] or 'Other \u00b7 140 SKUs' in A['a1_html'],
   'A1h the label is the series label', A['a1_html'])

eq('A2a a STATIC parent is given a containing block', A['a1b_staticFixed'], 'relative')
eq('A2b a parent that already has one is left alone', A['a1b_relUntouched'], '')

eq('A3a show:false renders nothing', A['a3_showFalse'], '')
eq('A3b and a single series renders nothing, the canvas legend\'s own rule',
   A['a3_single'], '')

eq('A4a THE REBUILD GUARD: a visibility change does NOT rebuild the nodes, so '
   'the chip cannot vanish from under the pointer', A['a4_sameNodes'], True)
eq('A4b but a change of SERIES does', A['a4b_rebuilt'], True)

eq('A5a the hidden series gains the off class', A['a5_classes'],
   ['ch-lg-i', 'ch-lg-i off', 'ch-lg-i'])
eq('A5b and each item says what a click will do', A['a5_titles'],
   ['Hide Super Zoomies', 'Show Catnip Spray - 4 OZ', 'Hide Other \u00b7 140 SKUs'])
eq('A6a the chip reads "only" while more than one is showing', A['a6_chips'],
   ['only', 'only', 'only'])
eq('A6b and "all" on the series that is already alone', A['a6b_chips'],
   ['only', 'all', 'only'])
eq('A6c the tooltip says which it will do', A['a6b_titles'],
   ['Show only Super Zoomies', 'Show every series again', 'Show only Other \u00b7 140 SKUs'])

ok('<b>' not in A['a8_html'], 'A8a a label carrying markup reaches no DOM as markup', A['a8_html'])
ok('&lt;b&gt;bold&lt;/b&gt;' in A['a8_html'], 'A8b it renders as text', A['a8_html'])
ok('&#39;Brien' in A['a8_html'] and '&quot;Max&quot;' in A['a8_html'],
   'A8c quotes and apostrophes escaped', A['a8_html'])

eq('A9a afterDestroy removes the host', A['a9_gone'], True)
eq('A9b and drops the reference', A['a9_hostRef'], True)


# ═══════════════════════════════════ A7. the padding reservation + the guard
print('== A7. the padding reservation, and the rAF regression ==')

A7 = run_node(os.path.join(SP, '_v1135_a7.js'), CORE + r"""
const out = {};
const DS = [{ label: 'a', borderColor: '#1' }, { label: 'b', borderColor: '#2' }];
const P = CHART_HTML_LEGEND;

// --- the SHIPPED scheduler, with a working timer -------------------------
const timers = [];
global.setTimeout = (f, ms) => { timers.push(f); return timers.length; };
const cv = mkCanvas('pad-canvas');
const chart = mkChart(cv, DS.map(d => ({ ...d })));
P.afterUpdate(chart, {}, { show: true });
document.getElementById('pad-canvas-legend').offsetHeight = 24;   // laid out
P.afterUpdate(chart, {}, { show: true });
out.padAfterMeasure = chart.options.layout.padding.top;
out.flagWhileQueued = chart.$lgPad;
out.queued = timers.length;
timers.splice(0).forEach(f => f());            // the deferred update runs
out.flagAfterRun = chart.$lgPad;
out.updatesAfterRun = chart.updates;
// CONVERGENCE: a further pass at the same height must schedule nothing more
P.afterUpdate(chart, {}, { show: true });
out.queuedAfterConverge = timers.length;
out.padAfterConverge = chart.options.layout.padding.top;
// and it follows the legend when it wraps to a second line
document.getElementById('pad-canvas-legend').offsetHeight = 46;
P.afterUpdate(chart, {}, { show: true });
timers.splice(0).forEach(f => f());
out.padAfterWrap = chart.options.layout.padding.top;

// --- a HIDDEN panel measures 0: a no-op, never a loop --------------------
const cvH = mkCanvas('hidden-canvas');
const chH = mkChart(cvH, DS.map(d => ({ ...d })));
P.afterUpdate(chH, {}, { show: true });          // offsetHeight stays 0
P.afterUpdate(chH, {}, { show: true });
out.hiddenQueued = timers.length;
out.hiddenPad = ((chH.options.layout && chH.options.layout.padding) || null) === null;

// --- THE REGRESSION GUARD ------------------------------------------------
// The pre-fix scheduler, reproduced exactly, under a rAF that never fires -
// which is what a non-compositing browser pane gives you.
function preFixReserve(chart, host) {
  const h = host.offsetHeight || 0;
  const lay = chart.options.layout || (chart.options.layout = {});
  const pad = lay.padding;
  const cur = (pad && typeof pad === 'object') ? (pad.top || 0) : 0;
  if (Math.abs(h - cur) > 1 && !chart.$lgPad) {
    chart.$lgPad = true;
    lay.padding = { top: h, right: 0, bottom: 0, left: 0 };
    const soon = (typeof requestAnimationFrame === 'function')
      ? requestAnimationFrame : (f => setTimeout(f, 16));
    soon(() => { chart.$lgPad = false; try { chart.update('none'); } catch (e) {} });
  }
}
global.requestAnimationFrame = () => {};         // throttled: never fires
const cvR = mkCanvas('raf-canvas');
const chR = mkChart(cvR, DS.map(d => ({ ...d })));
const hostR = mkEl('div'); hostR.offsetHeight = 24;
preFixReserve(chR, hostR);
out.raf_flagStuck = chR.$lgPad;
out.raf_updates = chR.updates;
// the legend then wraps - and the pre-fix version can never follow it
hostR.offsetHeight = 46;
preFixReserve(chR, hostR);
preFixReserve(chR, hostR);
out.raf_padStuckAt = chR.options.layout.padding.top;

console.log(JSON.stringify(out));
""")

eq('A7a the measured legend height lands in layout.padding.top', A7['padAfterMeasure'], 24)
eq('A7b the flag is held while the update is queued', A7['flagWhileQueued'], True)
eq('A7c exactly one update is scheduled', A7['queued'], 1)
eq('A7d the flag clears when it runs', A7['flagAfterRun'], False)
eq('A7e and the chart was re-laid out', A7['updatesAfterRun'], 1)
eq('A7f CONVERGENCE: the next pass at the same height schedules nothing',
   A7['queuedAfterConverge'], 0)
eq('A7g and leaves the padding where it was', A7['padAfterConverge'], 24)
eq('A7h a legend that wraps to a second line is followed', A7['padAfterWrap'], 46)
eq('A7i a HIDDEN panel measures 0 and schedules nothing', A7['hiddenQueued'], 0)
eq('A7j leaving its padding untouched', A7['hiddenPad'], True)

eq('A7k THE REGRESSION GUARD: under a throttled rAF the pre-fix scheduler '
   'leaves the guard flag stuck TRUE', A7['raf_flagStuck'], True)
eq('A7l so the deferred re-layout never ran', A7['raf_updates'], 0)
eq('A7m and the reservation is frozen at the first value for the life of the '
   'chart - the plot draws under the legend and nothing says so',
   A7['raf_padStuckAt'], 24)
# v11.18 / v11.27: assert against COMMENT-STRIPPED source, and require the
# comment to survive - otherwise the explanation of why rAF was wrong would
# itself fail the guard that keeps rAF out.
def _nocomment(t):
    t = re.sub(r'/\*[\s\S]*?\*/', '', t)
    return re.sub(r'(?m)^\s*//.*$', '', t)
_plug = const_obj('CHART_HTML_LEGEND')
ok('requestAnimationFrame' not in _nocomment(_plug),
   'A7n the shipped plugin calls no rAF')
ok('requestAnimationFrame' in _plug,
   'A7o but the comment saying WHY it does not is still there, so grepping '
   'for the trap lands on the explanation')


# ══════════════════════════════════════════════ B. the two actions
print('== B. the real chartLegendToggle / chartLegendOnly ==')

B = run_node(os.path.join(SP, '_v1135_b.js'), CORE + r"""
const vis = c => c.data.datasets.map((_, j) => c.isDatasetVisible(j));
const mk = () => mkChart(mkCanvas('b' + Math.random()), [
  { label: 'A' }, { label: 'B' }, { label: 'C' }, { label: 'D' }]);
const out = {};

let c = mk();
chartLegendToggle(c, 1);
out.b1 = vis(c);
chartLegendToggle(c, 1);
out.b1back = vis(c);

c = mk();
chartLegendOnly(c, 2);
out.b2 = vis(c);
// Jason's words: "then i can click the others to add them back"
chartLegendToggle(c, 0);
out.b2add = vis(c);
// and "only" again on the already-isolated one puts everything back
c = mk();
chartLegendOnly(c, 2);
chartLegendOnly(c, 2);
out.b3 = vis(c);

// "only" on a series that is currently HIDDEN shows it and hides the rest,
// rather than doing nothing because it reads as not-soloed.
c = mk();
chartLegendToggle(c, 3);
chartLegendOnly(c, 3);
out.b4 = vis(c);

// one update per action, never one per series
c = mk();
const before = c.updates;
chartLegendOnly(c, 1);
out.b5_updates = c.updates - before;

// a single-series chart: "only" is a no-op that cannot blank the chart
c = mkChart(mkCanvas('b-one'), [{ label: 'solo' }]);
chartLegendOnly(c, 0);
out.b6 = vis(c);

console.log(JSON.stringify(out));
""")

eq('B1a a plain toggle hides one', B['b1'], [True, False, True, True])
eq('B1b and shows it again', B['b1back'], [True, True, True, True])
eq('B2a "only" isolates', B['b2'], [False, False, True, False])
eq('B2b and the others can be clicked back in one at a time', B['b2add'],
   [True, False, True, False])
eq('B3 "only" on the already-isolated series restores everything', B['b3'],
   [True, True, True, True])
eq('B4 "only" on a HIDDEN series isolates it rather than doing nothing', B['b4'],
   [False, False, False, True])
eq('B5 one repaint per action, not one per series', B['b5_updates'], 1)
eq('B6 a single-series chart cannot be blanked', B['b6'], [True])


# ══════════════════════════════════════════════ C. the click routing
print('== C. the real delegated listener ==')

C = run_node(os.path.join(SP, '_v1135_c.js'), CORE + r"""
const out = {};
const cv = mkCanvas('c-canvas');
const chart = mkChart(cv, [{ label: 'A' }, { label: 'B' }, { label: 'C' }]);
CHART_HTML_LEGEND.afterUpdate(chart, {}, { show: true });
const host = document.getElementById('c-canvas-legend');
const fire = target => { let s = 0; host._onclick({ target, stopPropagation: () => { s = 1; } }); return s; };
const vis = () => chart.data.datasets.map((_, j) => chart.isDatasetVisible(j));

out.c1_stopped = fire(host.children[1]);      // click the item -> toggle
out.c1 = vis();
fire(host.children[1]);
out.c1back = vis();

fire(host.children[2].querySelector('.ch-lg-only'));   // click the chip -> only
out.c2 = vis();

// a click that lands on no item does nothing
const stray = mkEl('span'); stray.className = 'something-else';
fire(stray);
out.c3 = vis();

// one listener, wired once, surviving every rebuild
CHART_HTML_LEGEND.afterUpdate(chart, {}, { show: true });
chart.data.datasets = [{ label: 'X' }, { label: 'Y' }];
CHART_HTML_LEGEND.afterUpdate(chart, {}, { show: true });
out.c4_stillWired = typeof host._onclick === 'function';
out.c4_wiredFlag = host.$wired;

// an index past the end of the CURRENT series is refused, not thrown on
const ghost = mkEl('span');
ghost.className = 'ch-lg-i';
ghost._attrs = { 'data-i': '9' };
const c5before = chart.data.datasets.map((_, j) => chart.isDatasetVisible(j));
let threw = false;
try { fire(ghost); } catch (e) { threw = true; }
out.c5_threw = threw;
out.c5_unchanged = JSON.stringify(chart.data.datasets.map((_, j) => chart.isDatasetVisible(j)))
                 === JSON.stringify(c5before);

console.log(JSON.stringify(out));
""")

eq('C1a a click on the item toggles it', C['c1'], [True, False, True])
eq('C1b and toggles it back', C['c1back'], [True, True, True])
eq('C1c the click is stopped, so it cannot also reach the canvas beneath',
   C['c1_stopped'], 1)
eq('C2 a click on the chip isolates instead', C['c2'], [False, False, True])
eq('C3 a click on neither does nothing', C['c3'], [False, False, True])
eq('C4a the listener survives a rebuild', C['c4_stillWired'], True)
eq('C4b and is wired exactly once', C['c4_wiredFlag'], True)
eq('C5a a stale index is refused rather than thrown on', C['c5_threw'], False)
eq('C5b leaving the chart exactly as it was', C['c5_unchanged'], True)


# ═══════════════════════════════════════════════════════════════ D. static
print('== D. static wiring ==')

for name in ('chartLegendHost', 'chartLegendToggle', 'chartLegendOnly'):
    eq('D1 exactly one definition of %s' % name, js.count('function %s(' % name), 1)
eq('D1 exactly one CHART_HTML_LEGEND', js.count('const CHART_HTML_LEGEND = {'), 1)

eq('D2 exactly THREE charts opt in (7 surfaces via the shared renderer, '
   'plus the two on Units Sold)', js.count('CHART_HTML_LEGEND]'), 3)

ok('plugins: [CHART_HTML_LEGEND],' in js,
   'D3a pnlTrendRender passes it in the chart\'s own plugins array')
ok('plugins: [salesCoveragePlugin, CHART_HTML_LEGEND],' in js,
   'D3b Units Sold ADDS it beside the coverage plugin rather than replacing it')
eq('D3c and both Units Sold charts did', js.count('plugins: [salesCoveragePlugin, CHART_HTML_LEGEND],'), 2)
# v11.40 re-point. This pinned a CENSUS (`salesCoveragePlugin` alone appears
# zero times) while its label claimed a GUARANTEE about Units Sold. v11.40 gave
# the Seasonality chart the coverage band WITHOUT an HTML legend - it has its
# own canvas legend and did not ask for one - which is a legitimate new caller,
# not the regression this was written to catch.
#
# The guarantee it was really protecting is asserted directly by D3c above: the
# two Units Sold charts carry BOTH. What is added here is the other half of it -
# neither of those two may quietly lose the legend by being rewritten as a
# coverage-only opt-in.
eq('D3d exactly one coverage-only opt-in exists',
   js.count('plugins: [salesCoveragePlugin],'), 1)
ok('plugins: [salesCoveragePlugin],' in fn('seaRenderFitChart'),
   'D3d2 and it is the Seasonality chart, which has its own canvas legend')

eq('D4 the canvas legend is off on all three', js.count('legend: { display: false },'), 3)
ok("legend: { display: datasets.length > 1, labels:" not in js,
   'D4b THE GUARD: the retired canvas-legend config is gone')

# Each chart keeps the EXACT show rule its canvas legend had, so the only
# thing this release changed is the affordance.
for rule in ('htmlLegend: { show: datasets.length > 1 },',
             'htmlLegend: { show: salesSelected.size > 1 || _salesGoalDs.length > 0 },',
             'htmlLegend: { show: _chGoalDs.length > 0 },'):
    ok(rule in js, 'D5 the show rule is carried over verbatim: %s' % rule[22:-3])
eq('D5d three show rules, one per opted-in chart', js.count('htmlLegend: { show:'), 3)

ok('setTimeout(() => {\n        chart.$lgPad = false;' in js,
   'D6 THE REGRESSION: the padding update is deferred with setTimeout, not rAF')

for sel in ('.ch-lg {', '.ch-lg:empty', '.ch-lg-i {', '.ch-lg-sw {',
            '.ch-lg-i.off', '.ch-lg-only {', '.ch-lg-i:hover .ch-lg-only'):
    ok(sel in s, 'D7 the stylesheet declares %s' % sel)
ok('.ch-lg-only { visibility: hidden;' in s,
   'D7b the chip is hidden with VISIBILITY, so the item does not change width '
   'on hover and the legend cannot reflow out from under the pointer')
ok('pointer-events: none;' in s and 'pointer-events: auto;' in s,
   'D7c the overlay passes clicks through in the gaps, the items take them')
ok('text-decoration: line-through' in s,
   'D7d a hidden series is crossed through, which is what Chart.js drew')

ok('position: absolute; top: 0; left: 0; right: 0' in s,
   'D8 the legend overlays the top of the canvas, where the canvas legend was')

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
