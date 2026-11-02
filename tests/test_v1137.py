#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.37 - make the seasonal share of a Need visible.

Jason, on a 30d Shopify need of 1,016 for a product selling about 104/week:
"why does the export show bubbles for shopify needed at 1000+ for 30 day when
the trend line doesn't support? ... I need a way to check issues like this"

It was seasonality, worth 2.29x, and nothing on screen said so.

  * A  the REAL seaForwardWeight / seaForwardAvg / forwardSeaDemand.
    A5 THE NO-MOVEMENT GUARD. The pre-v11.37 forwardSeaDemand is run beside
       the shipped one over the same curves and required to agree to the bit,
       so "no forecast number moved" is a measurement, not a claim.
  * B  the REAL ipVelTrendDivergent / ipVelTrendLabel, driven on the REAL
       Bubbles numbers (demand -24.2%, curve +67.7%) that rendered a green
       flaming "Surging +146%" over falling sell-through.
    B5 rank is carried through UNCHANGED, so sort order and the export are
       byte-identical. That was a decision; this pins it.
  * C  the REAL velTrendCell: the demand chip appears on BOTH render paths
       when divergent and on NEITHER when the two components agree.
  * D  static wiring: one weight definition, no curve walk left in
       forwardSeaDemand, all 16 tooltip call sites converted, the column
       registered with sort + csv + render.
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
# A. The forward curve weight.
# ---------------------------------------------------------------------------
# A curve the tests own, so the arithmetic is checkable by hand: every week
# 1.0 except weeks 45-48, which carry the real Bubbles mix values.
CURVE_STUB = """
const _CURVE = {};
for (let w = 1; w <= 52; w++) _CURVE[String(w)] = 1.0;
Object.assign(_CURVE, { '45': 2.18, '46': 2.45, '47': 2.54, '48': 2.21, '49': 1.58 });
let _CURVE_SOURCE = 'mix';
const SEED = { curves: { consumables: _CURVE } };
function getEffectiveCurveForProduct(p) {
  if (p && p.flatCurve) {
    const f = {}; for (let w = 1; w <= 52; w++) f[String(w)] = 1.0;
    return { curve: f, source: 'flat' };
  }
  return { curve: _CURVE, source: _CURVE_SOURCE };
}
function isoWeekOfYear(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil((((t - y0) / 86400000) + 1) / 7);
}
// The pre-v11.37 implementation, kept verbatim for A5.
function forwardSeaDemandOld(r, horizonDays) {
  const blended = r.blended_daily || 0;
  if (!blended || horizonDays <= 0) return 0;
  if (r.new_amazon_override) return blended * horizonDays;
  if (r.sea_override != null) return blended * Number(r.sea_override) * horizonDays;
  const eff = getEffectiveCurveForProduct(r);
  const curve = (eff && eff.curve) || SEED.curves?.consumables || {};
  let total = 0;
  const today = new Date();
  for (let i = 0; i < horizonDays; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    const wk = Math.min(Math.max(isoWeekOfYear(d), 1), 52);
    total += blended * Number(curve[String(wk)] ?? curve[wk] ?? 1.0);
  }
  return total;
}
"""

A = run_node(os.path.join(SP, '_v1137_a.js'), CURVE_STUB
    + fn('seaForwardWeight') + '\n' + fn('seaForwardAvg') + '\n' + fn('forwardSeaDemand') + '\n' + r"""
const out = {};
const R  = { blended_daily: 14.79 };
const FL = { blended_daily: 14.79, flatCurve: true };

// weight x rate IS the demand, by construction
out.a1_identity = [30, 60, 90, 120].every(n =>
  Math.abs(forwardSeaDemand(R, n) - R.blended_daily * seaForwardWeight(R, n)) < 1e-9);

// a flat curve weighs exactly the horizon - so 1.00x means "nothing applied"
out.a2_flatWeight = [1, 7, 30, 120].map(n => seaForwardWeight(FL, n));
out.a2_flatAvg    = seaForwardAvg(FL, 30);

// the v4.176 launch override and an explicit sea_override are both FLAT
out.a3_newAmz = seaForwardWeight({ ...R, new_amazon_override: true }, 30);
out.a4_over   = seaForwardWeight({ ...R, sea_override: 0.5 }, 30);
out.a4_overD  = forwardSeaDemand({ ...R, sea_override: 0.5 }, 30);

// A5 THE NO-MOVEMENT GUARD
const cases = [R, FL, { ...R, new_amazon_override: true }, { ...R, sea_override: 0.5 },
               { blended_daily: 0 }, { blended_daily: 3.2 }];
out.a5_drift = [];
for (const c of cases) for (const n of [0, 1, 7, 30, 60, 90, 120, 365]) {
  const d = forwardSeaDemand(c, n) - forwardSeaDemandOld(c, n);
  if (Math.abs(d) > 1e-9) out.a5_drift.push([JSON.stringify(c), n, d]);
}

// degenerate horizons must not divide by zero or return NaN
out.a6_zeroW   = seaForwardWeight(R, 0);
out.a6_zeroAvg = seaForwardAvg(R, 0);
out.a6_negW    = seaForwardWeight(R, -5);
out.a6_finite  = [seaForwardAvg(R, 0), seaForwardAvg(R, 30), seaForwardWeight(R, 0)].every(Number.isFinite);

// a zero-velocity row still has a real multiplier - the weight is a property
// of the CURVE, not of the rate, which is what lets the column render on a row
// whose Need is 0.
out.a7_zeroVel     = forwardSeaDemand({ blended_daily: 0 }, 30);
out.a7_zeroVelAvg  = seaForwardAvg({ blended_daily: 0 }, 30);
console.log(JSON.stringify(out));
""")

ok(A['a1_identity'], 'A1 forwardSeaDemand === rate x seaForwardWeight at every horizon')
eq('A2 a flat curve weighs exactly the horizon', A['a2_flatWeight'], [1, 7, 30, 120])
eq('A2b flat reads 1.00x', round(A['a2_flatAvg'], 6), 1.0)
eq('A3 new_amazon_override is flat (v4.176)', A['a3_newAmz'], 30)
eq('A4 sea_override scales the horizon', A['a4_over'], 15.0)
eq('A4b and forwardSeaDemand follows it', round(A['a4_overD'], 4), round(14.79 * 15, 4))
eq('A5 THE NO-MOVEMENT GUARD: zero drift vs the pre-v11.37 implementation',
   A['a5_drift'], [])
eq('A6 horizon 0 weighs 0', A['a6_zeroW'], 0)
eq('A6b seaForwardAvg(r, 0) does not divide by zero', A['a6_zeroAvg'], 1)
eq('A6c a negative horizon weighs 0', A['a6_negW'], 0)
ok(A['a6_finite'], 'A6d no NaN or Infinity escapes')
eq('A7 a zero-velocity row needs nothing', A['a7_zeroVel'], 0)
ok(A['a7_zeroVelAvg'] > 1, 'A7b but still reports its multiplier', A['a7_zeroVelAvg'])

# ---------------------------------------------------------------------------
# B. The trend label.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, '_v1137_b.js'),
    fn('ipVelTrendDivergent') + '\n' + fn('ipVelTrendLabel') + '\n' + fn('ipVelTrendLabelRaw')
    + '\n' + fn('velTrendSortVal') + '\n' + fn('velTrendCsv') + '\n' + r"""
const out = {};
const mk = (o) => Object.assign({ now: 0, prev: 0, pct: 0, rawPct: null, seaPct: null,
                                  lags: [], isNew: false, ready: true }, o);

// THE REAL BUBBLES ROW. Shopify demand 16.80 -> 12.73 units/day while the mix
// curve went 1.30x -> 2.18x. The badge rendered a green flaming Surging +146%.
const bubbles = mk({ now: 27.75, prev: 11.28, pct: 146, rawPct: -24.2, seaPct: 67.7 });
out.b1_divergent = ipVelTrendDivergent(bubbles);
out.b1_label     = ipVelTrendLabel(bubbles);
out.b1_raw       = ipVelTrendLabelRaw(bubbles);

// both components up: nothing changes, "Surging" is honest
const real = mk({ now: 40, prev: 10, pct: 300, rawPct: 180, seaPct: 42 });
out.b2_divergent = ipVelTrendDivergent(real);
out.b2_label     = ipVelTrendLabel(real);
out.b2_same      = JSON.stringify(ipVelTrendLabel(real)) === JSON.stringify(ipVelTrendLabelRaw(real));

// the OTHER direction: demand climbing while the curve falls away, so a muted
// blend understates a real gain. Same rule, same treatment.
const rev = mk({ now: 11, prev: 10, pct: 10, rawPct: 55, seaPct: -30 });
out.b3_divergent = ipVelTrendDivergent(rev);
out.b3_label     = ipVelTrendLabel(rev);

// no prior history -> the components are null -> do NOT guess
out.b4_nullRaw = ipVelTrendDivergent(mk({ rawPct: null, seaPct: 67.7 }));
out.b4_nullSea = ipVelTrendDivergent(mk({ rawPct: -24.2, seaPct: null }));
out.b4_undef   = ipVelTrendDivergent(undefined);
out.b4_label   = ipVelTrendLabel(mk({ now: 5, prev: 0, pct: null, isNew: true }));

// B5 rank is untouched, so sort order and the CSV are unchanged
out.b5_rankSame = ipVelTrendLabel(bubbles).rank === ipVelTrendLabelRaw(bubbles).rank;
out.b5_sortSame = velTrendSortVal(bubbles);
out.b5_csv      = velTrendCsv(bubbles);
out.b5_csvReal  = velTrendCsv(real);

// one zero-crossing component is not a divergence
out.b6_zeroRaw = ipVelTrendDivergent(mk({ rawPct: 0, seaPct: 67.7 }));
out.b6_zeroSea = ipVelTrendDivergent(mk({ rawPct: -24.2, seaPct: 0 }));
console.log(JSON.stringify(out));
""")

ok(B['b1_divergent'], 'B1 the real Bubbles row is detected as divergent')
eq('B1b it is relabelled off "Surging"', B['b1_label']['txt'], '\u2248 Season')
eq('B1c and rendered orange, not green', B['b1_label']['cls'], 'var(--sp-orange)')
ok(B['b1_raw']['txt'].endswith('Surging'), 'B1d the raw label still said Surging', B['b1_raw']['txt'])
eq('B1e the filled green chip is dropped', B['b1_label'].get('strong', False), False)
ok(B['b1_label'].get('split') is True, 'B1f and it is marked split for the cell')
ok(not B['b2_divergent'], 'B2 a genuinely surging row is NOT divergent')
ok(B['b2_same'], 'B2b so its label is byte-identical to v11.36')
ok(B['b3_divergent'], 'B3 demand up while the curve falls is divergent too')
eq('B3b and gets the same honest treatment', B['b3_label']['txt'], '\u2248 Season')
ok(not B['b4_nullRaw'], 'B4 a null demand component is not a divergence')
ok(not B['b4_nullSea'], 'B4b nor a null seasonal component')
ok(not B['b4_undef'], 'B4c nor an undefined trend')
ok('New' in B['b4_label']['txt'], 'B4d a new SKU keeps its own label', B['b4_label']['txt'])
ok(B['b5_rankSame'], 'B5 THE DECISION: rank is carried through unchanged')
eq('B5b so the sort key is the pre-v11.37 value', B['b5_sortSame'], 4146)
eq('B5c the CSV follows the SCREEN, glyph stripped like every other label',
   B['b5_csv'], 'Season +146%')
ok('Surging' in B['b5_csvReal'], 'B5d an agreeing row exports Surging, unchanged', B['b5_csvReal'])
ok('≈' not in B['b5_csv'], 'B5e and no raw glyph reaches the export', B['b5_csv'])
ok(not B['b6_zeroRaw'] and not B['b6_zeroSea'], 'B6 a zero component is not a sign flip')

# ---------------------------------------------------------------------------
# C. The cell.
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, '_v1137_c.js'),
    fn('ipVelTrendDivergent') + '\n' + fn('ipVelTrendLabel') + '\n' + fn('ipVelTrendLabelRaw')
    + '\n' + fn('velTrendCell') + '\n' + r"""
function ipVelTrendTip() { return 'tip'; }
const out = {};
const mk = (o) => Object.assign({ now: 0, prev: 0, pct: 0, rawPct: null, seaPct: null,
                                  lags: [], isNew: false, ready: true }, o);
const r = { master_id: 'SP-0124' };

// divergent, and above the Surging threshold -> the FILLED-CHIP path
out.c1 = velTrendCell(r, mk({ now: 27.75, prev: 11.28, pct: 146, rawPct: -24.2, seaPct: 67.7 }));
// divergent and quiet -> the PLAIN path
out.c2 = velTrendCell(r, mk({ now: 11, prev: 10, pct: 10, rawPct: 55, seaPct: -30 }));
// not divergent -> NO chip at all
out.c3 = velTrendCell(r, mk({ now: 40, prev: 10, pct: 300, rawPct: 180, seaPct: 42 }));
// no components -> no chip, no throw
out.c4 = velTrendCell(r, mk({ now: 5, prev: 4, pct: 25 }));
console.log(JSON.stringify(out));
""")

ok('dmd' in C['c1'], 'C1 the divergent row renders a demand chip')
ok('\u219324% dmd' in C['c1'], 'C1b naming the direction demand actually moved', C['c1'][-150:])
ok('var(--sp-red)' in C['c1'], 'C1c in red, because demand fell')
ok('Season' in C['c1'], 'C1d beside the relabelled badge')
ok('dmd' in C['c2'], 'C2 the plain render path carries the chip too')
ok('\u219155% dmd' in C['c2'] and 'var(--sp-green)' in C['c2'],
   'C2b up-arrow and green when demand rose', C['c2'][-150:])
ok('dmd' not in C['c3'], 'C3 an agreeing row renders NO chip')
ok('Surging' in C['c3'], 'C3b and keeps its green Surging badge')
ok('dmd' not in C['c4'], 'C4 a row with no components renders no chip')
for k in ('c1', 'c2', 'c3', 'c4'):
    ok('undefined' not in C[k] and 'NaN' not in C[k], 'C5 %s leaks no undefined/NaN' % k)

# ---------------------------------------------------------------------------
# D. Static wiring.
# ---------------------------------------------------------------------------
def nocomment(t):
    t = re.sub(r'/\*[\s\S]*?\*/', '', t)
    return re.sub(r'(?m)^\s*//.*$', '', t)

eq('D1 exactly one seaForwardWeight definition', js.count('function seaForwardWeight('), 1)
eq('D1b exactly one seaForwardAvg definition', js.count('function seaForwardAvg('), 1)
eq('D1c exactly one forwardSeaDemand definition', js.count('function forwardSeaDemand('), 1)

_fwd = nocomment(fn('forwardSeaDemand'))
ok('isoWeekOfYear' not in _fwd,
   'D2 forwardSeaDemand no longer walks the curve itself')
ok('seaForwardWeight' in _fwd, 'D2b it delegates')
ok('getEffectiveCurveForProduct' in nocomment(fn('seaForwardWeight')),
   'D2c and the walk moved WITH its curve resolution, not a copy of it')

eq('D3 all 16 Need tooltip call sites pass the record and its horizon',
   len(re.findall(r'pre\.tipBase\(pre\.nb(\d+), r, \1\)', js)), 16)
eq('D3b none left on the old signature',
   len(re.findall(r'pre\.tipBase\(pre\.nb\d+\)', js)), 0)
ok('const buildTipBase = (nb, r, seaDays) =>' in js,
   'D3c and the builder takes them')
ok('seaForwardAvg(r, seaDays)' in js, 'D3d the footer uses the cell OWN horizon')

_col = js[js.index("{ key:'sea_fwd'"):]
_col = _col[:_col.index("\n  { key:'")]
for bit in ('sortVal:', 'csv:', 'render:', 'tip:'):
    ok(bit in _col, 'D4 the Season column declares %s' % bit)
ok("label:'Season \u00d7'" in _col, 'D4b labelled with the multiplication sign')
# v11.39 re-point: v11.37 coined group:'seasonal' / 'SEASONAL' without checking,
# and the picker rendered it beside the SEASONALITY group that already existed
# (key 'sea-settings'). It joins that one now. Still NOT vel-trend.
ok("groupHdr:'SEASONALITY'" in _col and "group:'sea-settings'" in _col,
   'D4c in the SEASONALITY group that already existed')
ok("group:'vel-trend'" not in _col,
   'D4c2 and still not filed under VELOCITY TREND (rule 3a)')
eq('D4c3 exactly one group key carries the SEASONALITY header',
   len(set(re.findall(r"group:'([^']+)', groupHdr:'SEASONALITY'",
                      re.sub(r'(?m)^\s*//.*$', '', js)))), 1)
ok(_col.count('seaForwardAvg(r, 30)') >= 2,
   'D4d sort and csv read the same helper the cell renders')

eq('D5 the migration flag is unique', js.count('ipSeaFwdAutoShownV1137'), 2)
ok("ipVisibleCols.push('sea_fwd')" in js, 'D5b and it surfaces the column once')

# --- the deep link ------------------------------------------------------
_colcode = re.sub(r'(?m)^\s*//.*$', '', _col)
eq('D7 the cell is exactly one anchor', (_colcode.count('<a '), _colcode.count('</a>')), (1, 1))
# v11.38 re-point. A PLAIN click no longer opens a tab: this file is ~4.2MB and
# cold-boots its entire dataset, so a new tab paid a full reload to move one
# screen sideways. The href SURVIVES, which is what keeps ctrl/middle-click
# working, so that is what these now assert.
ok('target="_blank"' not in _colcode,
   'D7b a plain click no longer forces a new tab (v11.38)')
ok('rel="noopener"' in _colcode,
   'D7b2 the link keeps the noopener the other 29 links in this file use')
ok('seaOpenFromNeed(event,' in _colcode,
   'D7b3 and routes through the modifier-aware handler')
ok('#forecast/seasonality?mid=' in _colcode, 'D7c pointing at the seasonality page')
ok('encodeURIComponent(mid)' in _colcode and "const mid = String(r.master_id" in _colcode,
   'D7d with the id escaped, even though master_id is app data (the v11.23 rule)')
ok('esc2(mid)' in _colcode,
   'D7e and escaped AGAIN for the attribute, through the one global escaper (v11.08)')
ok('NOT target="_blank" (v11.38)' in _col,
   'D7f the comment saying why a plain click stays in page survives')

# The href has to name a sub the router will actually accept, or the new tab
# silently falls back to the default forecast view.
_subs = js[js.index('const ROUTE_SUBS = {'):]
_subs = _subs[:_subs.index('};')]
ok("'seasonality'" in _subs.split('forecast:')[1].split(']')[0],
   'D8 THE DRIFT GUARD: the router accepts the sub the link points at')

# E. THE ROUND TRIP. The column writes an href and the router reads it; this
# drives the REAL routeParse on the REAL href the REAL renderer emits, so a
# link the router cannot understand fails the build instead of opening a tab on
# the wrong product.
E = run_node(os.path.join(SP, '_v1137_e.js'), r"""
const out = {};
""" + fn('routeParse') + r"""
// the href exactly as the sea_fwd renderer builds it
const mid = "SP-0124";
const href = `#forecast/seasonality?mid=${encodeURIComponent(mid)}`;
out.e1_href = href;
global.window = { location: { hash: href } };
out.e2 = routeParse();
// an id with characters that would break a naive href
const nasty = 'SP/0124?x=1&y=2 #z';
global.window = { location: { hash: `#forecast/seasonality?mid=${encodeURIComponent(nasty)}` } };
out.e3 = routeParse();
out.e3_want = nasty;
console.log(JSON.stringify(out));
""")

eq('E1 the href the column writes', E['e1_href'], '#forecast/seasonality?mid=SP-0124')
eq('E2 the REAL router reads it as forecast/seasonality',
   (E['e2']['page'], E['e2']['sub']), ('forecast', 'seasonality'))
eq('E2b and hands routeApply the product', E['e2']['filters'].get('mid'), 'SP-0124')
ok(E['e2']['view'] is None, 'E2c without inventing a saved view')
eq('E3 an id full of route punctuation still round-trips',
   E['e3']['filters'].get('mid'), E['e3_want'])
eq('E3b and does not leak into the path', E['e3']['sub'], 'seasonality')

_ra = fn('routeApply')
ok("sub === 'seasonality'" in _ra and 'filters.mid' in _ra,
   'D9 routeApply consumes the mid')
# v11.38 re-point: routeApply no longer inlines the defer. It calls the ONE
# shared selector that the in-page jump also calls, which is the stronger
# claim - the URL restore and the click cannot select differently.
ok('seaSelectProductDeferred' in _ra, 'D9b through the one shared selector')
_sel = fn('seaSelectProductDeferred')
ok('setTimeout' in _sel,
   'D9c which defers, so initSeasonalityView has populated the picker first')
ok('catch' in _sel,
   'D9d and catches, because a throw out of a timer has no caller and blanks the page')
eq('D9e exactly one definition of it', js.count('function seaSelectProductDeferred('), 1)

eq('D6 version chip', s.count('>v11.40 \u00b7 2026-11-02<'), 1)
eq('D6b exactly one chip, and no older one survives',
   len(re.findall(r'>v11\.\d+ \u00b7 [\d-]+<', s)), 1)

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
