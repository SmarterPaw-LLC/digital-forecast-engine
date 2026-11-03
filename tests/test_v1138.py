#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.38 - the Season x link jumps in the SAME TAB.

Jason, on v11.37's new-tab link: "the click to open seasonality tab does not
work well. it takes forever to load, and loads to a blank screen." Then:
"maybe we should use the same tab."

index.html is a single ~4.2MB file that re-authenticates and re-fetches its
entire dataset on boot, so target="_blank" paid a full cold start to move one
screen sideways. The href survives - a MODIFIED click still opens a real tab
and routeApply still restores the product there.

  * A  the REAL seaOpenFromNeed, driven with real-shaped events: a plain
       click is handled in page, and every modifier is handed to the browser.
  * B  the REAL seaSelectProductDeferred: deferred, and guarded so a throw
       out of a timer cannot take the page down - which is the shape of the
       blank screen that was reported.
  * C  static: one definition of each helper, and routeApply shares the
       selector with the in-page jump rather than carrying its own copy.
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


# ---------------------------------------------------------------------------
# A. The click handler.
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, '_v1138_a.js'),
    # v11.43 - seaOpenFromNeed delegates to the shared ipDeepLinkClick now, so
    # the slice follows the dependency. The modifier contract below is
    # unchanged and is now being driven through the handler every in-table
    # deep link uses, which is the stronger claim.
    fn('ipDeepLinkClick') + '\n' + fn('seaOpenFromNeed') + '\n' + r"""
const out = { jumps: [] };
let defaulted = 0, bubbled = 0;
function seaOpenForProduct(mid) { out.jumps.push(mid); }
const ev = (o) => Object.assign({
  ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, button: 0,
  preventDefault() { defaulted++; }, stopPropagation() { bubbled++; },
}, o);

// a plain left click is handled HERE
out.a1_plain       = seaOpenFromNeed(ev({}), 'SP-0124');
out.a1_defaulted   = defaulted;
out.a1_bubbled     = bubbled;

// every modifier hands it back to the browser, untouched
const before = { d: defaulted, b: bubbled, n: out.jumps.length };
out.a2 = {
  ctrl:   seaOpenFromNeed(ev({ ctrlKey: true }),  'SP-0124'),
  meta:   seaOpenFromNeed(ev({ metaKey: true }),  'SP-0124'),
  shift:  seaOpenFromNeed(ev({ shiftKey: true }), 'SP-0124'),
  alt:    seaOpenFromNeed(ev({ altKey: true }),   'SP-0124'),
  middle: seaOpenFromNeed(ev({ button: 1 }),      'SP-0124'),
};
out.a2_untouched = (defaulted === before.d) && (bubbled === before.b)
                && (out.jumps.length === before.n);

// no event at all (a programmatic call) still jumps
out.a3 = seaOpenFromNeed(null, 'SP-0202');
out.a3_jumps = out.jumps.slice();
console.log(JSON.stringify(out));
""")

ok(A['a1_plain'] is False, 'A1 a plain click returns false, so the href does not navigate')
eq('A1b it preventDefaults exactly once', A['a1_defaulted'], 1)
eq('A1c and stops the row click behind it', A['a1_bubbled'], 1)
eq('A1d and jumps in page', A['a1_jumps'] if 'a1_jumps' in A else A['a3_jumps'][0], 'SP-0124')
for k in ('ctrl', 'meta', 'shift', 'alt', 'middle'):
    ok(A['a2'][k] is True, 'A2 a %s-click is handed to the browser' % k)
ok(A['a2_untouched'],
   'A2b THE POINT: a modified click is not preventDefaulted and does not jump')
ok(A['a3'] is False, 'A3 a programmatic call with no event still jumps')
eq('A3b and reached the right product', A['a3_jumps'], ['SP-0124', 'SP-0202'])

# ---------------------------------------------------------------------------
# B. The deferred selector.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, '_v1138_b.js'),
    fn('seaSelectProductDeferred') + '\n' + r"""
const out = { picked: [] };
let warned = 0;
console.warn = () => { warned++; };
let mode = 'ok';
function seaSetActive(mid) {
  if (mode === 'throw') throw new Error('records not ready');
  out.picked.push(mid);
}
seaSelectProductDeferred('SP-0124');
out.b1_syncPicked = out.picked.length;          // nothing yet: it defers

// blank / null / whitespace are no-ops, not a selection of ''
seaSelectProductDeferred('');
seaSelectProductDeferred(null);
seaSelectProductDeferred('   ');
seaSelectProductDeferred(undefined);

setTimeout(() => {
  out.b2_afterTick = out.picked.slice();
  mode = 'throw';
  let threw = false;
  try { seaSelectProductDeferred('SP-0202'); } catch (e) { threw = true; }
  setTimeout(() => {
    out.b3_callerSawThrow = threw;
    out.b3_warned = warned;
    out.b3_picked = out.picked.slice();
    console.log(JSON.stringify(out));
  }, 0);
}, 0);
""")

eq('B1 nothing is selected synchronously', B['b1_syncPicked'], 0)
eq('B2 the real selection lands a tick later', B['b2_afterTick'], ['SP-0124'])
ok('' not in B['b2_afterTick'], 'B2b and a blank id selected nothing at all')
ok(B['b3_callerSawThrow'] is False,
   'B3 a failing seaSetActive does NOT escape to the caller')
ok(B['b3_warned'] >= 1, 'B3b it warns instead', B['b3_warned'])
eq('B3c and nothing further was selected', B['b3_picked'], ['SP-0124'])

# ---------------------------------------------------------------------------
# C. Static wiring.
# ---------------------------------------------------------------------------
for name in ('seaSelectProductDeferred', 'seaOpenForProduct', 'seaOpenFromNeed'):
    eq('C1 exactly one %s' % name, js.count('function %s(' % name), 1)

_open = fn('seaOpenForProduct')
ok('switchForecastView' in _open, 'C2 the jump switches the forecast view')
ok('seaSelectProductDeferred' in _open, 'C2b then selects through the shared helper')
ok('showPage' not in _open,
   'C2c and does NOT also call showPage - switchForecastView activates the page itself (v5.81)')

_ra = fn('routeApply')
ok('seaSelectProductDeferred(filters.mid)' in _ra,
   'C3 the URL restore uses the SAME selector as the click')
ok('setTimeout' not in _ra[_ra.index('filters.mid') - 200:_ra.index('filters.mid') + 120],
   'C3b rather than carrying its own copy of the defer')

_cell = js[js.index("{ key:'sea_fwd'"):]
_cell = _cell[:_cell.index("\n  { key:'")]
_cellcode = re.sub(r'(?m)^\s*//.*$', '', _cell)
ok('target="_blank"' not in _cellcode, 'C4 the cell no longer forces a new tab')
ok('href="${href}"' in _cellcode, 'C4b but it is still a real link')
ok('NOT target="_blank" (v11.38)' in _cell,
   'C4c with the comment explaining why still present')

eq('C5 version chip', len(re.findall(r'>v11\.45 \u00b7 [\d-]+<', s)), 1)

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
