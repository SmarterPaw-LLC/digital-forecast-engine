# -*- coding: utf-8 -*-
r"""v10.63 / v10.64 — one bundle-attribution setting, and seasonal days of cover.

Jason: "if i uncheck bundle components the bundle still shows in the counts"
       "i also need to see the number of days of inventory based on the
        seasonal velocity on the inventory planning page"

v10.63 — THE SPLIT BRAIN. There were two independent "+ bundle components"
checkboxes (#fBundleAttr on Demand Forecast, #ip-bundle-attr on Inventory
Planning) driving DIFFERENT halves of one number:
    inventoryNeedBreakdown  -> read #ip-bundle-attr  (Need / Reorder / Gap)
    recomputeRecordVelocity -> read #fBundleAttr     (blended_daily, bundle_daily, adj_daily)
Both pages are in the DOM at once, so unchecking it on Inventory dropped the
bundle term from Need but left Vel/day showing "+B 1.1". Same shape as the
v10.2 velocity-compare-mode split; same fix: one persisted setting.

v10.64 — Cover (d). The seasonal burn-down already existed (meta.dos via
fbaSeasonalReorderPoint, v9.95) and only showed on hover. Surfaced as a
column, sourced from the SAME functions Status uses per mode so the two can
never contradict each other.
"""
import io, json, os, re, subprocess, sys

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


def run_node(body, name):
    p = os.path.join(HERE, '_%s.js' % name)
    io.open(p, 'w', encoding='utf-8', newline='\n').write(body)
    try:
        r = subprocess.run(['node', p], capture_output=True, text=True)
        if r.returncode != 0:
            return None, (r.stderr or '')[:300]
        return json.loads(r.stdout.strip().split('\n')[-1]), None
    except Exception as e:
        return None, str(e)
    finally:
        try: os.remove(p)
        except Exception: pass


# ============ A. ONE setting, not two checkboxes ============
print('A. static - bundle attribution is a single shared setting')

ok(JS.count('function bundleAttrOn(') == 1, 'bundleAttrOn is declared once')
ok(JS.count('function setBundleAttrOn(') == 1, 'setBundleAttrOn is declared once')

# the per-page DOM reads that caused the split must be gone
leftover_fc = JS.count("document.getElementById('fBundleAttr')?.checked ?? true")
leftover_ip = JS.count("document.getElementById('ip-bundle-attr')?.checked ?? true")
ok(leftover_fc == 0,
   'no Forecast-page read of the checkbox survives (was 9)', leftover_fc)
ok(leftover_ip == 0,
   'no Inventory-page read of the checkbox survives (was 2)', leftover_ip)

ok(JS.count('bundleAttrOn()') >= 11,
   'every consumer routes through the shared setting', JS.count('bundleAttrOn()'))

# the velocity recompute is what makes Vel/day move; it MUST read the setting
rec = fn('recomputeRecordVelocity')
ok('bundleAttrOn()' in rec,
   'recomputeRecordVelocity reads the shared setting (this is what moves Vel/day)')
ok("getElementById('fBundleAttr')" not in rec,
   '  and no longer reads the Forecast checkbox directly')

# both checkboxes must write through the setter
ok('setBundleAttrOn(this.checked' in RAW,
   'the Forecast checkbox writes the shared setting')
ok('setBundleAttrOn(ba.checked)' in JS,
   'the Inventory checkbox writes the shared setting')

# guard the guard
ok(len(re.findall(r"getElementById\('fBundleAttr'\)\?\.checked \?\? true", 'x')) == 0,
   '  (detector sanity: pattern does not match empty input)')


# ============ B. behaviour - the +B badge moves with the toggle ============
print('\nB. behaviour - unchecking it actually clears Vel/day and the +B badge')

# slice the real adj_daily renderer by brace balance
i = JS.index("{ key:'adj_daily'")
rs = JS.index('render:', i)
arrow = JS.index('r =>', rs)
bs = JS.index('{', JS.index('=>', rs))
k = bs; d = 0
while True:
    c = JS[k]
    if c == '{': d += 1
    elif c == '}':
        d -= 1
        if d == 0: break
    k += 1
ADJ = JS[arrow:k + 1]

H1 = r'''
const _store = {};
const localStorage = { getItem: k => (k in _store ? _store[k] : null),
                       setItem: (k, v) => { _store[k] = String(v); } };
const _els = { 'fVelocityWindow': { value: '30' },
               'fBundleAttr': { checked: true }, 'ip-bundle-attr': { checked: true } };
const document = { getElementById: id => _els[id] || null };
let records = [];
function clearVelMemo() {}
function fcWalmartVel() { return 0; }
function getAutoSeaIdx() { return 1; }
function rederiveNeeds() {}
function getBundleAttrDailyVelocity() { return 1.1; }
__REAL__
const ADJ = __ADJ__;
const mk = () => ({ master_id:'SP-X', region:'US', daily_v30: 53.32,
                    new_product_amazon:false, new_amazon_daily_units:0, sea_override:null });
const out = {};
setBundleAttrOn(true);  let r = mk(); records=[r]; recomputeRecordVelocity(r);
out.onBlended = r.blended_daily; out.onBundle = r.bundle_daily; out.onBadge = /\+B/.test(ADJ(r));
setBundleAttrOn(false); r = mk(); records=[r]; recomputeRecordVelocity(r);
out.offBlended = r.blended_daily; out.offBundle = r.bundle_daily; out.offBadge = /\+B/.test(ADJ(r));
out.fcBox = _els['fBundleAttr'].checked; out.ipBox = _els['ip-bundle-attr'].checked;
out.persisted = _store['bundleAttrOn'];
_els['fBundleAttr'].checked = true; _els['ip-bundle-attr'].checked = true;
restoreBundleAttrPref();
out.restoredFc = _els['fBundleAttr'].checked; out.restoredIp = _els['ip-bundle-attr'].checked;
console.log(JSON.stringify(out));
'''
real1 = '\n'.join([fn('bundleAttrOn'), fn('setBundleAttrOn'),
                   fn('restoreBundleAttrPref'), fn('recomputeRecordVelocity')])
d1, err = run_node(H1.replace('__REAL__', real1).replace('__ADJ__', ADJ), 'v1064a')
if err:
    ok(False, 'bundle-attr harness ran', err)
else:
    ok(abs(d1['onBlended'] - 54.42) < 0.001,
       'ON: blended includes the bundle slice (53.32 + 1.1)', d1['onBlended'])
    ok(d1['onBadge'], '  and the +B badge renders')
    ok(abs(d1['offBlended'] - 53.32) < 0.001,
       'OFF: blended drops it', d1['offBlended'])
    ok(d1['offBundle'] == 0, '  bundle_daily is 0')
    ok(not d1['offBadge'],
       '  and the +B badge is GONE  <- the reported symptom')
    ok(d1['fcBox'] is False and d1['ipBox'] is False,
       'both checkboxes mirror the one setting')
    ok(d1['persisted'] == '0', 'the choice persists')
    ok(d1['restoredFc'] is False and d1['restoredIp'] is False,
       'and restores to BOTH boxes on load')


# ============ C. Cover (d) ============
print('\nC. static + behaviour - seasonal days of cover')

ok(JS.count('function getCoverDays(') == 1, 'getCoverDays is declared once')
ok("key:'cover_days'" in JS, 'the Cover (d) column is registered')
ok("localStorage.getItem('ipCoverAutoShownV1064')" in JS,
   'a flag-guarded one-time migration surfaces it for existing saved column sets')

cov = fn('getCoverDays')
ok('amazonStatusRollup' in cov,
   'Amazon mode reads the SAME rollup Status uses (so they cannot disagree)')
ok('getStatusInputs' in cov,
   'other modes read the SAME inputs Status uses')

H2 = r'''
const SEED = { curves: { consumables: {} } };
let _seaWeekIdx = null, _seaWeekIdxDay = null;
let _curve = {};
function getEffectiveCurveForProduct() { return { curve: _curve, source: 't' }; }
const setCurve = f => { _curve = {}; for (let w=1; w<=52; w++) _curve[w] = f(w); };
let AMZ = null;
function amazonStatusRollup() { return AMZ; }
function getStatusInputs(r) { return r.__inp || null; }
__REAL__
const out = {};
setCurve(() => 1.0);
out.flat = fbaSeasonalReorderPoint({ blended_daily: 10 }, 900, 0, 365).coverDays;
setCurve(() => 2.0);
const rp = fbaSeasonalReorderPoint({ blended_daily: 10 }, 900, 0, 365);
out.peak = rp.coverDays; out.peakFlat = rp.flatCoverDays;
setCurve(() => 1.0);
AMZ = { tier:'order-soon', allRegions:['US','CA'], perRegion:[
  { region:'US', tier:'ok',        cover:120, threshold:90, vel:10, slack:30,  stock:1200 },
  { region:'CA', tier:'order-now', cover:40,  threshold:90, vel:5,  slack:-50, stock:200  }]};
const c = getCoverDays({}, 'amazon');
out.amzDays = c.days; out.amzRegion = c.region; out.amzSlack = c.slack;
AMZ = { tier:'nodata', allRegions:[], perRegion:[] };
out.amzNull = getCoverDays({}, 'amazon') === null;
const w = getCoverDays({ __inp:{ stock:900, need90:900 }, lead_time:60, safety_stock:14, blended_daily:10 }, 'warehouse');
out.whDays = w.days; out.whSlack = w.slack; out.whRop = w.rop;
let threw = false;
for (const bad of [null, undefined, {}]) {
  try { getCoverDays(bad, 'warehouse'); getCoverDays(bad, 'amazon'); } catch { threw = true; }
}
out.threw = threw;
console.log(JSON.stringify(out));
'''
real2 = '\n'.join([fn('isoWeekOfYear'), fn('seaWeekIndexFor'), fn('seaDailySeries'),
                   fn('fbaSeasonalReorderPoint'), fn('getCoverDays')])
d2, err2 = run_node(H2.replace('__REAL__', real2), 'v1064c')
if err2:
    ok(False, 'cover harness ran', err2)
else:
    ok(abs(d2['flat'] - 90) < 0.01,
       'flat curve: 900u at 10/day = 90d cover', d2['flat'])
    ok(abs(d2['peak'] - 45) < 0.01,
       'a 2x season HALVES it to 45d — the curve is really applied', d2['peak'])
    ok(abs(d2['peakFlat'] - 90) < 0.01,
       '  while flat cover still reports 90d for the tooltip contrast', d2['peakFlat'])
    ok(d2['amzDays'] == 40 and d2['amzRegion'] == 'CA',
       'Amazon mode reports the WORST region, matching the Status rollup', d2)
    ok(d2['amzSlack'] == -50,
       '  and carries the same slack Status tiers on')
    ok(d2['amzNull'] is True,
       'nothing to score -> null (cell renders an em-dash, not a 0)')
    ok(abs(d2['whDays'] - 90) < 0.01,
       'Warehouse mode: stock / (need90/90)', d2['whDays'])
    ok(abs(d2['whSlack'] - 16) < 0.01,
       '  slack = cover - (lead + safety), same as Status', d2['whSlack'])
    ok(d2['threw'] is False, 'malformed records degrade quietly')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d): %s' % (F, ', '.join(fails[:8])))
    sys.exit(1)
print('v10.63/v10.64 - all green (%d assertions)' % P)
