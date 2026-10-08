# -*- coding: utf-8 -*-
"""v9.93 — prove the memo-poisoning race and that it is closed.
Drives the REAL sliced functions out of index.html."""
import io, os, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s = io.open(SRC, encoding='utf-8').read()

def grab(start, end, label):
    i = s.find(start); j = s.find(end, i + 1)
    if i < 0 or j < 0: print('ANCHOR FAIL ' + label); sys.exit(1)
    return s[i:j]

CHANS = grab('const IP_CHANNEL_KEYS', 'function inventoryNeedBreakdown', 'ipActiveChannels')
TREND = grab('const IP_VEL_DEFAULT_CHANS', 'function ipVelTrendTip', 'trend block')

HARNESS = r"""
// ── stubs ─────────────────────────────────────────────────────────────
const _velMemo = new Map();
let _nbMemo = new Map();
function clearVelMemo(){ _velMemo.clear(); _ipChanLagCache = null; }
function clearNbMemo(){ _nbMemo.clear(); }
let salesDataReady = true;
const SEED = { curves: { consumables: {} } };
for (let w = 1; w <= 52; w++) SEED.curves.consumables[String(w)] = 1.0;
function parseLocalDate(str) {
  if (!str) return null;
  const m = String(str).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) { const d = new Date(str); return isNaN(d) ? null : d; }
  return new Date(+m[1], +m[2] - 1, +m[3]);
}
function isoWeekOfYear(d) {
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  t.setDate(t.getDate() - ((t.getDay() + 6) % 7) + 3);
  const f = new Date(t.getFullYear(), 0, 4);
  f.setDate(f.getDate() - ((f.getDay() + 6) % 7) + 3);
  return 1 + Math.round((t - f) / 6048e5);
}
function getEffectiveCurveForProduct() { return { curve: SEED.curves.consumables }; }
let allBomData = {};
let salesData = {};
const DOM = {
  'ipChan-amazon': {checked:true}, 'ipChan-shopify': {checked:true},
  'ipChan-chewy':  {checked:true}, 'ipChan-walmart': {checked:false},
  'ip-vel-cmp': {value:'30'}, 'fVelocityWindow': {value:'60'}, 'ip-bundle-attr': {checked:true},
};
globalThis.document = { getElementById: (id) => DOM[id] || null };

__CHANS__
__TREND__

// ── the PRE-v9.93 ipVelWindowOne, as a regression guard ───────────────
const _oldMemo = new Map();
function ipVelWindowOne_OLD(r, windowDays, offsetDays, key) {
  const keys = [key];
  if (!salesData || !windowDays || windowDays <= 0) return 0;
  const reg = r.region || 'US';
  const pooled = String(reg).includes('+');
  const ck = `ipv1|${r.master_id}|${reg}|${windowDays}|${offsetDays}|${key}`;
  if (_oldMemo.has(ck)) return _oldMemo.get(ck);          // <- unguarded read
  const nowMs = Date.now();
  const inWin = (ws) => { const d = parseLocalDate(ws); if (!d) return false;
    const age = (nowMs - d.getTime()) / 864e5; return age >= offsetDays && age < offsetDays + windowDays; };
  let units = 0;
  for (const srow of (salesData[r.master_id] || [])) {
    if (!_ipChanMatch(srow.channel, keys)) continue;
    if (!pooled && srow.region && srow.region !== reg) continue;
    if (!inWin(srow.week_start)) continue;
    units += (srow.units_ordered || 0);
  }
  const v = units / windowDays;
  _oldMemo.set(ck, v);                                     // <- unguarded write
  return v;
}
// The pre-v9.93 lag cache too, otherwise the guard is not faithful: the NEW
// lag function refuses to cache an empty map, which changes Chewy's memo key
// between the two calls and lets the old path partially recover by accident.
let _oldLagCache = null;
function ipChannelLagDays_OLD(key) {
  if (!salesData) return 0;
  if (!_oldLagCache) {
    const latest = {};
    for (const mid in salesData) for (const srow of salesData[mid]) {
      const ch = srow.channel || '';
      const k = /^amazon/.test(ch) ? 'amazon' : ch;
      const d = parseLocalDate(srow.week_start);
      if (!d) continue;
      if (!latest[k] || d > latest[k]) latest[k] = d;
    }
    _oldLagCache = {};                       // <- cached even when empty
    for (const k in latest) {
      const lag = Math.floor((Date.now() - latest[k].getTime()) / 864e5);
      _oldLagCache[k] = lag > IP_VEL_FRESH_DAYS ? lag : 0;
    }
  }
  return _oldLagCache[key] || 0;
}
function ipVelWindow_OLD(r, w, off, keys) {
  let total = 0;
  for (const k of keys) total += ipVelWindowOne_OLD(r, w, off + ipChannelLagDays_OLD(k), k);
  return total;
}

// ── harness ───────────────────────────────────────────────────────────
let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const MID = 'SP-0121';
const rec = { master_id: MID, region: 'US+CA', sea_idx: 1.33 };
const ago = (d) => { const t = new Date(Date.now() - d * 864e5);
  return `${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')}`; };
function realSales() {
  const rows = [];
  for (const a of [2,9,16,23,30,37,44,51,58,65,72,79,86]) rows.push({channel:'amazon_us',region:'US',week_start:ago(a),units_ordered:420});
  for (const a of [1,3,5,10,20,30,40,50,60,70,80])        rows.push({channel:'shopify',  region:'US',week_start:ago(a),units_ordered:12});
  for (const a of [45,52,59,66,73,80,87])                 rows.push({channel:'chewy',    region:'US',week_start:ago(a),units_ordered:180});
  return { [MID]: rows };
}

console.log('\n== A. THE RACE: render lands while loadSalesAnalytics is still fetching ==');
// Exactly what happens on Units Sold -> Inventory Planning:
//   showPage('sales')        -> salesData = {}   (synchronous)
//   loadSalesAnalytics()     -> clearVelMemo()   (top of the function)
//   ...awaits the network...
//   user navigates           -> renderInventoryTbl() against an EMPTY salesData
//   load completes           -> salesData populated, re-render
salesData = {}; salesDataReady = false; clearVelMemo(); _oldMemo.clear(); _oldLagCache = null;
const duringLoad = ipVelTrendFor(rec);                 // the bad render
t('during the load the window reads 0', duringLoad.rawNow === 0, duringLoad.rawNow);
t('and it is labelled as LOADING, not as "No data"',
  ipVelTrendLabel(duringLoad).txt.includes('loading'), ipVelTrendLabel(duringLoad).txt);
ipVelWindow_OLD(rec, 60, 0, ['amazon','shopify','chewy']);   // old code caches its 0 too

// Load completes. salesData is populated and the view re-renders.
salesData = realSales(); salesDataReady = true;
const afterLoad = ipVelTrendFor(rec);
t('FIX: after the load the real rate is served, not the cached 0',
  afterLoad.rawNow > 0, afterLoad.rawNow);
t('FIX: the label is a real trend',
  !/No data|loading/.test(ipVelTrendLabel(afterLoad).txt), ipVelTrendLabel(afterLoad).txt);
const afterLoadOld = ipVelWindow_OLD(rec, 60, 0, ['amazon','shopify','chewy']);
t('REGRESSION GUARD: pre-v9.93 kept serving the poisoned 0',
  afterLoadOld === 0, afterLoadOld);

console.log('\n== B. The systemic half \u2014 clearing after salesData lands also fixes it ==');
_oldMemo.clear(); _oldLagCache = null; salesData = {}; clearVelMemo();
ipVelWindow_OLD(rec, 60, 0, ['amazon','shopify','chewy']);   // poison
salesData = realSales();
clearVelMemo(); _oldMemo.clear(); _oldLagCache = null;        // the v9.93 post-load clear
t('old code recovers once the memo is cleared after the load',
  ipVelWindow_OLD(rec, 60, 0, ['amazon','shopify','chewy']) > 0);

console.log('\n== C. The lag cache is not poisoned by an empty salesData ==');
salesData = {}; clearVelMemo();
t('no lag is recorded while salesData is empty', ipChannelLagDays('chewy') === 0);
t('and nothing is cached in that state', _ipChanLagCache === null, _ipChanLagCache);
salesData = realSales();
t('FIX: Chewy\u2019s real ~45d lag is picked up once data lands',
  ipChannelLagDays('chewy') >= 40 && ipChannelLagDays('chewy') <= 50, ipChannelLagDays('chewy'));
t('current channels still read as current', ipChannelLagDays('amazon') === 0);

console.log('\n== D. A genuine zero is still reported as "No data" ==');
salesData = { 'SP-OTHER': [] }; salesDataReady = true; clearVelMemo();
const genuine = ipVelTrendFor(rec);
t('loaded, but this product has no rows -> "No data"',
  ipVelTrendLabel(genuine).txt.includes('No data'), ipVelTrendLabel(genuine).txt);
t('ready flag is true there', genuine.ready === true);
salesData = {}; salesDataReady = false; clearVelMemo();
t('not loaded -> "loading", never "No data"',
  ipVelTrendLabel(ipVelTrendFor(rec)).txt.includes('loading'));

console.log('\n== E. Normal operation is unchanged ==');
salesData = realSales(); salesDataReady = true; clearVelMemo();
const good = ipVelTrendFor(rec);
t('ties out: now = rawNow \u00d7 seaNow',
  Math.abs(good.now - good.rawNow * good.seaNow) < 1e-9, [good.now, good.rawNow, good.seaNow]);
t('prior window is populated', good.rawPrev > 0, good.rawPrev);
t('a real trend label is produced',
  /Surging|Accelerating|Growing|Steady|Slowing|Declining/.test(ipVelTrendLabel(good).txt), ipVelTrendLabel(good).txt);
t('memo is actually in use (second call is identical)',
  ipVelTrendFor(rec).rawNow === good.rawNow);
t('no leaked JS values', [good.now, good.prev, good.rawNow, good.rawPrev].every(Number.isFinite), good);

console.log('\n== F. Channel selection still honoured ==');
DOM['ipChan-chewy'].checked = false; clearVelMemo();
const noChewy = ipVelTrendFor(rec);
t('dropping Chewy lowers the rate', noChewy.rawNow < good.rawNow, [noChewy.rawNow, good.rawNow]);
DOM['ipChan-chewy'].checked = true; clearVelMemo();

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

js = HARNESS.replace('__CHANS__', CHANS).replace('__TREND__', TREND)
p = os.path.join(SP, 'test_v993.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(js)
print('harness %d chars' % len(js))
sys.exit(subprocess.call(['node', p]))
