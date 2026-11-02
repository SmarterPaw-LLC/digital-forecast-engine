#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.43 - Vel/day links to that product's Units Sold trend.

Jason: "the velocity/day should link to the units sold page filtered to that
product"

  * A  the REAL ipDeepLinkClick, now shared by every in-table deep link.
  * B  the REAL salesApplySelection. SELECTING is not SHOWING - the table
       filters on search, brand and category, and v11.41 learned that the
       hard way one page over.
  * C  THE HANDOFF. showPage('sales') CLEARS salesSelected and kicks off an
       async reload, so a selection made on the way in is wiped a moment
       later. C2 reproduces exactly that and proves the pending path survives
       it.
  * D  static: the link, its href, and routeApply arming the same selector.
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
# A. The shared click handler.
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, '_v1143_a.js'), fn('ipDeepLinkClick') + '\n' + r"""
const out = { ran: [] };
let defaulted = 0, bubbled = 0, warned = 0;
console.warn = () => { warned++; };
const ev = (o) => Object.assign({
  ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, button: 0,
  preventDefault() { defaulted++; }, stopPropagation() { bubbled++; },
}, o);

out.a1 = ipDeepLinkClick(ev({}), () => out.ran.push('plain'));
out.a1_defaulted = defaulted;
out.a1_bubbled = bubbled;

const before = { d: defaulted, b: bubbled, n: out.ran.length };
out.a2 = {
  ctrl:   ipDeepLinkClick(ev({ ctrlKey: true }),  () => out.ran.push('ctrl')),
  meta:   ipDeepLinkClick(ev({ metaKey: true }),  () => out.ran.push('meta')),
  shift:  ipDeepLinkClick(ev({ shiftKey: true }), () => out.ran.push('shift')),
  alt:    ipDeepLinkClick(ev({ altKey: true }),   () => out.ran.push('alt')),
  middle: ipDeepLinkClick(ev({ button: 1 }),      () => out.ran.push('middle')),
};
out.a2_untouched = (defaulted === before.d) && (bubbled === before.b)
                && (out.ran.length === before.n);

// a thunk that throws must not escape to the browser's default handler
let threw = false;
try { out.a3 = ipDeepLinkClick(ev({}), () => { throw new Error('boom'); }); }
catch (e) { threw = true; }
out.a3_escaped = threw;
out.a3_warned = warned;
out.a4 = ipDeepLinkClick(null, () => out.ran.push('noevent'));
out.ran_final = out.ran.slice();
console.log(JSON.stringify(out));
""")

ok(A['a1'] is False, 'A1 a plain click returns false, so the href does not navigate')
eq('A1b preventDefault exactly once', A['a1_defaulted'], 1)
eq('A1c and the row click behind it is stopped', A['a1_bubbled'], 1)
for k in ('ctrl', 'meta', 'shift', 'alt', 'middle'):
    ok(A['a2'][k] is True, 'A2 a %s-click is handed to the browser' % k)
ok(A['a2_untouched'], 'A2b THE POINT: a modified click neither preventDefaults nor navigates')
ok(A['a3_escaped'] is False, 'A3 a throwing destination does not escape the handler')
eq('A3b it warns instead', A['a3_warned'], 1)
ok(A['a4'] is False, 'A4 a programmatic call with no event still runs')
eq('A4b and only the unmodified clicks ran', A['ran_final'], ['plain', 'noevent'])

# ---------------------------------------------------------------------------
# B / C. The Units Sold selection.
# ---------------------------------------------------------------------------
BC = run_node(os.path.join(SP, '_v1143_bc.js'),
    'let salesDataReady = false;\nlet salesData = {};\n'
    'let salesSelected = new Set();\nlet _salesChipAdded = new Set();\n'
    + fn('salesApplySelection') + '\n' + fn('salesSelectPending') + '\n' + r"""
const out = { renders: 0, charts: 0 };
let allProducts = [];
const _els = {};
const el = (id, v, checked) => (_els[id] = { value: v || '', checked: !!checked });
const document = { getElementById: (id) => _els[id] || null };
function renderSalesTbl() { out.renders++; }
function updateSalesChart() { out.charts++; }
function globalSearchSyncFromTarget() { out.synced = true; }
console.warn = () => {};

function reset() {
  salesSelected = new Set(); _salesChipAdded = new Set();
  el('salesBrand', 'Doggijuana'); el('salesCat', 'toys');
  el('salesSrch', 'something else'); el('salesHideBundles', '', true);
  out.renders = 0; out.charts = 0;
}

// B1 a plain product
allProducts = [{ master_id: 'SP-0124', is_bundle: false },
               { master_id: 'SP-0615', is_bundle: true }];
reset();
salesSelected.add('SP-9999');            // something already picked
_salesChipAdded.add('SP-9999');
salesApplySelection('SP-0124');
out.b1 = { sel: [...salesSelected], chip: [..._salesChipAdded],
           brand: _els.salesBrand.value, cat: _els.salesCat.value,
           srch: _els.salesSrch.value, hideBundles: _els.salesHideBundles.checked,
           renders: out.renders, charts: out.charts };

// B2 a BUNDLE, with Hide bundles ticked
reset();
salesApplySelection('SP-0615');
out.b2_hideBundles = _els.salesHideBundles.checked;

// B3 a plain product must NOT untick it
reset();
salesApplySelection('SP-0124');
out.b3_hideBundles = _els.salesHideBundles.checked;

// B4 a blank id is a no-op, not a selection of ''
reset();
salesApplySelection('');
salesApplySelection(null);
out.b4 = { sel: [...salesSelected], renders: out.renders };

// C1 data already in hand -> applies at once
reset();
salesDataReady = true; salesData = { 'SP-0124': [] };
salesSelectPending('SP-0124');
out.c1 = { sel: [...salesSelected], renders: out.renders };

// C2 THE HANDOFF. This is the state right after showPage('sales'): the page
// cleared the selection and emptied salesData, and the reload has not landed.
reset();
salesDataReady = true; salesData = {};
salesSelectPending('SP-0124');
out.c2_immediate = { sel: [...salesSelected], renders: out.renders };
console.log(JSON.stringify(out));
""")

eq('B1 the product is isolated, not added to what was there', BC['b1']['sel'], ['SP-0124'])
eq('B1b chip-added tracking is cleared with it', BC['b1']['chip'], [])
eq('B1c the brand filter that could hide the row is cleared', BC['b1']['brand'], '')
eq('B1d and the category filter', BC['b1']['cat'], '')
eq('B1e the search is set to the product (v11.41 lesson)', BC['b1']['srch'], 'SP-0124')
eq('B1f the table repaints once', BC['b1']['renders'], 1)
eq('B1g and so does the chart', BC['b1']['charts'], 1)
# B1h is static: the sync is DEFERRED a tick (the v11.34 pattern, so it runs
# after the render it describes), and this harness logs synchronously.
_apply = re.sub(r'(?m)^\s*//.*$', '', fn('salesApplySelection'))
ok('globalSearchSyncFromTarget' in _apply,
   'B1h the top bar is told what the table narrowed by')
ok('setTimeout(globalSearchSyncFromTarget, 0)' in _apply,
   'B1i deferred a tick, so it runs after the render it describes')
eq('B2 Hide bundles is unticked for a BUNDLE', BC['b2_hideBundles'], False)
eq('B3 but left alone for a plain product - it is a deliberate view choice',
   BC['b3_hideBundles'], True)
eq('B4 a blank id selects nothing', BC['b4']['sel'], [])
eq('B4b and repaints nothing', BC['b4']['renders'], 0)
eq('C1 with data in hand the selection applies at once', BC['c1']['sel'], ['SP-0124'])
eq('C2 THE HANDOFF: with salesData emptied by showPage, nothing is selected yet',
   BC['c2_immediate']['sel'], [])
eq('C2b and nothing repaints on a table that has no data',
   BC['c2_immediate']['renders'], 0)

# ---------------------------------------------------------------------------
# D. Static wiring.
# ---------------------------------------------------------------------------
def nocomment(t):
    t = re.sub(r'/\*[\s\S]*?\*/', '', t)
    return re.sub(r'(?m)^\s*//.*$', '', t)

code = nocomment(js)
for f in ('ipDeepLinkClick', 'salesApplySelection', 'salesSelectPending',
          'salesOpenForProduct', 'seaOpenFromNeed'):
    eq('D1 exactly one %s' % f, code.count('function %s(' % f), 1)

# ONE modifier list in the whole file, now that the third page shares it.
eq('D2 exactly one click-modifier check in the file',
   code.count('ev.button === 1'), 1)
_sea = code[code.index('function seaOpenFromNeed('):]
_sea = _sea[:_sea.index('\n}') + 2]
ok('ipDeepLinkClick' in _sea and 'ctrlKey' not in _sea,
   'D2b the Season x handler delegates rather than carrying its own copy')

# The loader must CLEAR the pending id before using it, or a throw re-arms it
# to fire again on the next load.
_load = nocomment(fn('loadSalesAnalytics'))
i = _load.index('_salesPendingSelect = null;')
j = _load.index('salesApplySelection(')
ok(i < j, 'D3 the pending id is cleared BEFORE the apply, so a throw cannot re-arm it')
ok('salesDataReady = true;' in _load, 'D3b and the loader still marks itself ready')

_cell = js[js.index("{ key:'adj_daily'"):]
_cell = _cell[:_cell.index("\n  { key:'")]
_cellcode = nocomment(_cell)
eq('D4 the Vel/day cell is exactly one anchor',
   (_cellcode.count('<a '), _cellcode.count('</a>')), (1, 1))
ok('#sales?mid=' in _cellcode, 'D4b pointing at Units Sold')
ok('encodeURIComponent(_vmid)' in _cellcode, 'D4c with the id escaped for the href')
ok('esc2(_vmid)' in _cellcode, 'D4d and again for the attribute (v11.08 escaper)')
ok('target="_blank"' not in _cellcode, 'D4e a plain click does not open a tab')
ok('ipDeepLinkClick(event,' in _cellcode, 'D4f routing through the shared handler')
# The +B badge is a DIFFERENT number with its own tooltip and must stay out.
ok(_cellcode.index('</a>') < _cellcode.index('${bBadge}'),
   'D4g the +B badge sits OUTSIDE the link, so one link cannot claim both')

_ra = nocomment(fn('routeApply'))
ok("page === 'sales'" in _ra and 'salesSelectPending(filters.mid)' in _ra,
   'D5 routeApply arms the SAME selector for a bookmarked #sales?mid=')

eq('D6 version chip', s.count('>v11.43 \u00b7 2026-11-02<'), 1)
eq('D6b exactly one chip', len(re.findall(r'>v11\.\d+ \u00b7 [\d-]+<', s)), 1)

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
