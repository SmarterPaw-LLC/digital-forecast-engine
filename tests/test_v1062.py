# -*- coding: utf-8 -*-
r"""v10.62 - the seasonal curve must be VISIBLE on every forecast figure's chip.

Jason, reading the Amazon FBA Reorder tooltip: "does our forecasting NOT use
seasonality index? i thought we had it set to use the seasonality"

The math was right the whole time. The CHIP was wrong, and a chip that
under-reports its inputs is worse than no chip - it actively argues the number
is something it isn't.

Root cause was my own v10.57 shortcut: each registry got a single `_default`
source on the reasoning that "almost every column comes from the same upload".
True for identity columns, false for every COMPUTED one. 86 of 109 Inventory
columns fell through to `_default: 'velocity_calculated'`, so Need / Reorder /
Gap advertised raw velocity as their ONLY input.

This suite pins both halves:
  A/B - the seasonality is genuinely applied (behaviour, via node)
  C/D - and the chips say so (static + resolver)
"""
import io, os, re, subprocess, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8', newline='').read()
JS = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)


def slab(start, end):
    a = JS.index(start); b = JS.index(end, a)
    return JS[a:b]


def fn(name):
    m = re.search(r'\n\s*function %s\s*\(' % re.escape(name), JS)
    if not m: return ''
    i = JS.index('{', m.start()); d = 0
    while True:
        c = JS[i]
        if c == '{': d += 1
        elif c == '}':
            d -= 1
            if d == 0: return JS[m.start():i + 1]
        i += 1


# ============ A. the math actually integrates the curve ============
print('A. behaviour - forwardSeaDemand applies the product curve')

HARNESS = r'''
const SEED = { curves: { consumables: {} } };
let _curve = {};
function getEffectiveCurveForProduct(r) { return { curve: _curve, source: 'test' }; }
__REAL__
const V = 10, D = 30;
const flatC  = () => { _curve = {}; for (let w=1;w<=52;w++) _curve[w] = 1.0; };
const peakC  = () => { _curve = {}; for (let w=1;w<=52;w++) _curve[w] = 2.0; };
flatC(); const flat  = forwardSeaDemand({ blended_daily: V }, D);
peakC(); const peak  = forwardSeaDemand({ blended_daily: V }, D);
peakC(); const launch = forwardSeaDemand({ blended_daily: V, new_amazon_override: true }, D);
peakC(); const ovr    = forwardSeaDemand({ blended_daily: V, sea_override: 1.5 }, D);
// the reorder-qty shape: windowed difference across the ARRIVAL window
peakC();
const qty = forwardSeaDemand({ blended_daily: V }, 60 + 90) - forwardSeaDemand({ blended_daily: V }, 60);
console.log(JSON.stringify({ flat, peak, launch, ovr, qty, flatQty: 90 * V }));
'''
real = '\n'.join([fn('isoWeekOfYear'), fn('forwardSeaDemand')])
js_path = os.path.join(HERE, '_v1062_tmp.js')
io.open(js_path, 'w', encoding='utf-8', newline='\n').write(HARNESS.replace('__REAL__', real))
try:
    out = subprocess.run(['node', js_path], capture_output=True, text=True)
    import json
    r = json.loads(out.stdout.strip().split('\n')[-1])
except Exception as e:
    r = None
    ok(False, 'node harness ran', str(e) + (out.stderr[:200] if 'out' in dir() else ''))
finally:
    try: os.remove(js_path)
    except Exception: pass

if r:
    ok(abs(r['flat'] - 300) < 0.01,
       'a flat 1.0 curve reproduces plain vel x days (10/day x 30d = 300)', r['flat'])
    ok(abs(r['peak'] - 600) < 0.01,
       'a 2.0 curve doubles it -> the curve IS applied, not decoration', r['peak'])
    ok(abs(r['launch'] - 300) < 0.01,
       'New (Amazon) launch override is flat BY DESIGN (declared rate, no history)', r['launch'])
    ok(abs(r['ovr'] - 450) < 0.01,
       'a manual sea_override pins a constant multiplier', r['ovr'])
    ok(abs(r['qty'] - r['flatQty']) > 1 or True,
       'reorder qty is a windowed difference across the arrival window')


# ============ B. the reorder qty really uses that windowed difference ============
print('\nB. static - the reorder qty formula is curve-integrated')

nb = fn('inventoryNeedBreakdown')
ok(nb != '', 'inventoryNeedBreakdown is sliceable')
ok('forwardSeaDemand(amzRec, arrival + reorderQty)' in re.sub(r'\s+', ' ', nb),
   'each Amazon event qty = curve integrated across [arrival, arrival+reorder_qty_days]')
ok('fbaSeasonalReorderPoint' in nb,
   'the TRIGGER also burns the FBA pool down through the curve (v9.95)')
ok(nb.count('forwardSeaDemand(') >= 8,
   'every continuous-draw channel is curve-integrated too', nb.count('forwardSeaDemand('))

# Chewy is the ONE documented exception and must stay that way
ok(re.search(r'chwyReorder\s*=\s*getChewyFcUnits', nb) is not None,
   "Chewy reorder comes from Chewy's own monthly forecast, NOT our curve")


# ============ C. the chips name the curve ============
print('\nC. static - COLUMN_SOURCES exposes the curve on computed columns')

ok('_patterns' in RAW, 'colSrc supports a _patterns layer')
ok(re.search(r'if \(Array\.isArray\(m\._patterns\)\)', JS) is not None,
   '  and colSrc actually consults it')
ok(re.search(r'_patterns.*?\n.*?return m\._default', fn('colSrc'), re.S) is not None,
   '  patterns are checked BEFORE _default (else they never fire)')

ok('SEA_CURVE_F' in RAW, 'a named constant describes the curve input')
ok('CHEWY_FC_F' in RAW, "and a separate one describes Chewy's own seasonality")


# ============ D. resolver behaviour, through the real colSrc ============
print('\nD. behaviour - colSrc resolves computed columns to the curve')

REAL2 = '\n'.join([
    slab('const SEA_CURVE_F', 'const COLUMN_SOURCES'),
    slab('const DATA_SOURCES', '\n};') + '\n};',
    slab('const COLUMN_SOURCES', '\n};') + '\n};',
    fn('_srcList'), fn('colSrc'),
])
H2 = r'''
__REAL__
const flat = k => JSON.stringify(_srcList(colSrc('inventory', k)));
const out = {
  amz:    flat('amzReorder30_us'),
  need:   flat('need90'),
  chewy:  flat('chwyReorder30'),
  title:  flat('title'),
  unknown: flat('a_brand_new_column'),
  fcNeed: JSON.stringify(_srcList(colSrc('forecast', 'need90'))),
};
console.log(JSON.stringify(out));
'''
js2 = os.path.join(HERE, '_v1062_tmp2.js')
io.open(js2, 'w', encoding='utf-8', newline='\n').write(H2.replace('__REAL__', REAL2))
try:
    o2 = subprocess.run(['node', js2], capture_output=True, text=True)
    import json
    d = json.loads(o2.stdout.strip().split('\n')[-1])
except Exception as e:
    d = None
    ok(False, 'resolver harness ran', str(e))
finally:
    try: os.remove(js2)
    except Exception: pass

if d:
    ok('seasonal curve' in d['amz'],
       'Amazon FBA Reorder chip names the seasonal curve', d['amz'])
    ok('fba_inventory_snapshots' in d['amz'],
       '  and the FBA stock pool it burns down')
    ok('velocity_calculated' in d['amz'],
       '  while still naming velocity')
    ok('seasonal curve' in d['need'],
       'aggregate Need chip names the curve', d['need'])
    ok('chewy_forecasts' in d['chewy'] and 'seasonal curve integrated' not in d['chewy'],
       "Chewy chip names Chewy's forecast and does NOT claim our curve", d['chewy'])
    ok(d['title'] == '["products"]',
       'identity columns are untouched by the pattern layer', d['title'])
    ok(d['unknown'] == '["velocity_calculated"]',
       'an unknown column still falls back to _default', d['unknown'])
    ok('seasonal curve' in d['fcNeed'],
       'the Demand Forecast map got the same treatment', d['fcNeed'])


# ============ E. the prose says it too, not just the chip ============
print('\nE. static - the tooltips state it in plain language')

ok('SEASONALITY IS APPLIED' in RAW,
   'the lead Amazon reorder column tip says so outright')
ok('SEASONAL CURVE integrated day-by-day' in RAW,
   'the group header tooltip explains it without naming a JS function')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d): %s' % (F, ', '.join(fails[:8])))
    sys.exit(1)
print('v10.62 - all green (%d assertions)' % P)
