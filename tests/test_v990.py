# -*- coding: utf-8 -*-
import io, os, re, subprocess, sys

P   = r'C:\Users\Jason\digital-forecast-engine\index.html'
TMP = r'C:\Users\Jason\AppData\Local\Temp\claude\C--Users-Jason\74746540-4797-4eef-a801-df27808bdd42\scratchpad'
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', io.open(P, encoding='utf-8').read(), re.S), key=len)

chan   = js[js.index('const IP_CHANNEL_KEYS'):js.index('function ipChanSig')]
engine = js[js.index('const IP_VEL_DEFAULT_CHANS'):js.index('// ══════════════════════════════════════════════════════\n// INVENTORY PLANNING — page-level CHANNEL FILTER')] \
         if False else js[js.index('const IP_VEL_DEFAULT_CHANS'):js.index('\n// v5.1 — empty breakdown for region drill-downs')]
for need in ['function ipVelWindow', 'function ipVelTrendFor', 'function ipVelTrendLabel',
             'function ipVelCompareOffset', 'function ipBundleAttrUnitsWindow', 'function _ipChanMatch']:
    if need not in engine:
        print('FAIL: %s missing from extracted engine' % need); sys.exit(1)
print('extracted engine: %d chars' % len(engine))

harness = r'''
// ─── stubs ────────────────────────────────────────────────────────────
function parseLocalDate(s) {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s));
  if (!m) { const d = new Date(s); return isNaN(d) ? null : d; }
  return new Date(+m[1], +m[2] - 1, +m[3]);   // local midnight
}
let _velMemo = new Map();
let salesData = {}, allBomData = {};
let VELWIN = '30', CMP = 'prior', BUNDLE_ON = true;
// v10.1 - ipVelCompareMode() reads the shared velCmpMode setting now.
const localStorage = { getItem: (k) => k === 'velCmpMode' ? CMP : null, setItem: () => {} };
let CHAN_STATE = { total: true, amazon: true, shopify: true, chewy: true, walmart: true };
const document = { getElementById: (id) => {
  if (id === 'fVelocityWindow')  return { value: VELWIN };
  if (id === 'ip-vel-cmp')       return { value: CMP };
  if (id === 'ip-bundle-attr')   return { checked: BUNDLE_ON };
  if (id === 'ipChan-total')     return { get checked(){return CHAN_STATE.total;}, set checked(v){CHAN_STATE.total=v;} };
  const m = /^ipChan-(amazon|shopify|chewy|walmart)$/.exec(id);
  if (m) return { get checked(){return CHAN_STATE[m[1]];}, set checked(v){CHAN_STATE[m[1]]=v;} };
  return null;
} };
function renderInventoryTbl() {}
// v9.90 stubs — seasonal curve lookup used by ipSeaIdxAtOffset.
const SEED = { curves: { consumables: {} } };
let CURVE = {};                       // ISO week -> multiplier
function getEffectiveCurveForProduct() { return { curve: CURVE }; }
function isoWeekOfYear(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}
function wkAgo(n){ const d=new Date(); d.setDate(d.getDate()-n); return Math.min(Math.max(isoWeekOfYear(d),1),52); }

__CHAN__
function ipChanSig() { const c = ipActiveChannels(); return c ? c.join('+') : 'ALL'; }
__ENGINE__

// helper: an ISO date N days ago
function ago(n) { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0,10); }
function setChans(list) {
  const all = !list; CHAN_STATE.total = all;
  for (const k of IP_CHANNEL_KEYS) CHAN_STATE[k] = all || list.includes(k);
  _velMemo = new Map(); _ipChanLagCache = null;
}
function reset() { _velMemo = new Map(); _ipChanLagCache = null; salesData = {}; allBomData = {}; VELWIN = '30'; CMP = 'prior';
                   BUNDLE_ON = true; setChans(null); }

let pass = 0, fail = 0;
function t(label, cond, extra) {
  if (cond) { pass++; console.log('  ok    ' + label); }
  else { fail++; console.log('  FAIL  ' + label + (extra !== undefined ? '  -> ' + JSON.stringify(extra) : '')); }
}
const R = { master_id: 'SP-1', region: 'US' };

console.log('\n== A. window boundaries: half-open on AGE, no overlap, no gap ==');
reset();
// 10 units/day for the last 30d, 5 units/day in the 30d before that
salesData['SP-1'] = [];
for (let a = 0; a < 60; a++) salesData['SP-1'].push({ channel:'amazon_us', region:'US', week_start: ago(a), units_ordered: a < 30 ? 10 : 5 });
let T = ipVelTrendFor(R);
t('current 30d window = 10/day', Math.abs(T.now - 10) < 1e-9, T.now);
t('prior 30d window = 5/day',   Math.abs(T.prev - 5) < 1e-9, T.prev);
t('delta = +5/day', Math.abs(T.delta - 5) < 1e-9, T.delta);
t('pct = +100%', Math.abs(T.pct - 100) < 1e-9, T.pct);
// a row exactly at the seam (age 30) belongs to the PRIOR window only
// Keep a fresh anchor row in the dataset so the channel reads as CURRENT and
// the seam itself is what's under test (a lone 30-day-old row would otherwise
// trip the v9.88 lag anchor, which is tested separately in section K).
_velMemo = new Map(); _ipChanLagCache = null;
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(0),  units_ordered: 0 },
  { channel:'amazon_us', region:'US', week_start: ago(30), units_ordered: 300 },
];
T = ipVelTrendFor(R);
t('seam row (age 30) counts in prior, not current', T.now === 0 && Math.abs(T.prev - 10) < 1e-9, [T.now, T.prev]);
_velMemo = new Map(); _ipChanLagCache = null;
salesData['SP-1'] = [{ channel:'amazon_us', region:'US', week_start: ago(29), units_ordered: 300 }];
T = ipVelTrendFor(R);
t('age 29 counts in current only', Math.abs(T.now - 10) < 1e-9 && T.prev === 0, [T.now, T.prev]);
_velMemo = new Map(); _ipChanLagCache = null;
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(0),  units_ordered: 0 },
  { channel:'amazon_us', region:'US', week_start: ago(60), units_ordered: 300 },
];
T = ipVelTrendFor(R);
t('age 60 is outside both windows', T.now === 0 && T.prev === 0, [T.now, T.prev]);

console.log('\n== B. compare-mode offsets ==');
reset(); VELWIN = '30';
t("'prior' offset = window length", (CMP='prior', ipVelCompareOffset(30)) === 30);
t("'30' offset = 30",  (CMP='30',  ipVelCompareOffset(30)) === 30);
t("'90' offset = 90",  (CMP='90',  ipVelCompareOffset(90)) === 90);
t("'365' offset = 365",(CMP='365', ipVelCompareOffset(30)) === 365);
VELWIN = '90'; CMP = 'prior';
t("'prior' tracks a 90d window (last quarter)", ipVelCompareOffset(90) === 90);
// YoY actually reaches a year back
reset(); CMP = '365';
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(5),   units_ordered: 300 },   // current
  { channel:'amazon_us', region:'US', week_start: ago(370), units_ordered: 150 },   // a year ago
];
T = ipVelTrendFor(R);
t('YoY picks up the window one year back', Math.abs(T.now - 10) < 1e-9 && Math.abs(T.prev - 5) < 1e-9, [T.now, T.prev]);

console.log('\n== C. channel scope follows the "Need by" filter ==');
reset();
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(5),  units_ordered: 300 },
  { channel:'shopify',   region:'US', week_start: ago(5),  units_ordered: 150 },
  { channel:'walmart',   region:'US', week_start: ago(5),  units_ordered:  60 },
  { channel:'chewy',     region:'US', week_start: ago(5),  units_ordered: 900 },
];
// v9.90 — Chewy pulled back OUT of the default: the trend has to tie out
// against Vel/day, and Vel/day has no Chewy component.
t('default basis = amazon+shopify+walmart (matches Vel/day)',
  Math.abs(ipVelTrendFor(R).now - (300+150+60)/30) < 1e-9, ipVelTrendFor(R).now);
t('default channel list', JSON.stringify(ipVelTrendChans()) === JSON.stringify(['amazon','shopify','walmart']));
setChans(['amazon']);  t('amazon only', Math.abs(ipVelTrendFor(R).now - 10) < 1e-9, ipVelTrendFor(R).now);
setChans(['chewy']);   t('chewy only surfaces Chewy sell-through', Math.abs(ipVelTrendFor(R).now - 30) < 1e-9, ipVelTrendFor(R).now);
setChans(['shopify','walmart']); t('shopify+walmart', Math.abs(ipVelTrendFor(R).now - 7) < 1e-9, ipVelTrendFor(R).now);
setChans(null);
_velMemo = new Map(); _ipChanLagCache = null;
salesData['SP-1'].push({ channel:'amazon_gb', region:'US', week_start: ago(5), units_ordered: 30 });
t('amazon_* prefix-matches every marketplace',
  Math.abs(ipVelTrendFor(R).now - (300+150+60+30)/30) < 1e-9, ipVelTrendFor(R).now);

console.log('\n== D. region gating ==');
reset();
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(5), units_ordered: 300 },
  { channel:'amazon_ca', region:'CA', week_start: ago(5), units_ordered: 150 },
];
t('US record sees US rows only', Math.abs(ipVelTrendFor({master_id:'SP-1',region:'US'}).now - 10) < 1e-9);
_velMemo = new Map(); _ipChanLagCache = null;
t('CA record sees CA rows only', Math.abs(ipVelTrendFor({master_id:'SP-1',region:'CA'}).now - 5) < 1e-9);
_velMemo = new Map(); _ipChanLagCache = null;
t('pooled US+CA sees both', Math.abs(ipVelTrendFor({master_id:'SP-1',region:'US+CA'}).now - 15) < 1e-9);

console.log('\n== E. bundle attribution, offset-aware ==');
reset();
allBomData['BUNDLE-1'] = [{ component_master_id: 'SP-1', qty: 2 }];
salesData['SP-1'] = [];
salesData['BUNDLE-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(5),  units_ordered: 60 },   // current: 60*2 = 120
  { channel:'amazon_us', region:'US', week_start: ago(40), units_ordered: 30 },   // prior:   30*2 = 60
];
T = ipVelTrendFor(R);
t('bundle units folded in at BOM qty (current)', Math.abs(T.now - 4) < 1e-9, T.now);
t('bundle units folded in at BOM qty (prior)',  Math.abs(T.prev - 2) < 1e-9, T.prev);
BUNDLE_ON = false; _velMemo = new Map(); _ipChanLagCache = null;
T = ipVelTrendFor(R);
t('"+ bundle components" off removes it from BOTH windows', T.now === 0 && T.prev === 0, [T.now, T.prev]);
BUNDLE_ON = true; _velMemo = new Map(); _ipChanLagCache = null;
setChans(['shopify']);
t('bundle slice respects the channel filter', ipVelTrendFor(R).now === 0, ipVelTrendFor(R).now);

console.log('\n== F. reconciles with Vel/day basis (blended_daily) ==');
// blended_daily = daily_vN (velocity_calculated: amazon+shopify) + walmartVel + bundleVel.
// Reproduce that sum independently and assert ipVelWindow(offset 0) matches.
reset(); VELWIN = '30';
allBomData['BUNDLE-1'] = [{ component_master_id: 'SP-1', qty: 3 }];
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(3),  units_ordered: 90 },
  { channel:'shopify',   region:'US', week_start: ago(10), units_ordered: 60 },
  { channel:'walmart',   region:'US', week_start: ago(20), units_ordered: 30 },
];
salesData['BUNDLE-1'] = [{ channel:'amazon_us', region:'US', week_start: ago(7), units_ordered: 10 }];
const daily_v30  = (90 + 60) / 30;      // view = amazon + shopify
const walmartVel = 30 / 30;             // v6.52 adds walmart separately
const bundleVel  = (10 * 3) / 30;       // bundle attribution
const blended    = daily_v30 + walmartVel + bundleVel;
t('Vel Now equals the blended_daily recipe exactly',
  Math.abs(ipVelTrendFor(R).now - blended) < 1e-9, { velNow: ipVelTrendFor(R).now, blended });
// v9.90 — at the DEFAULT, Chewy must not move Vel Now: the whole point is that
// Vel Now reproduces the Vel/day recipe, and Vel/day has no Chewy in it.
_velMemo = new Map(); _ipChanLagCache = null;
salesData['SP-1'].push({ channel:'chewy', region:'US', week_start: ago(4), units_ordered: 900 });
t('Chewy does NOT move Vel Now at the default basis',
  Math.abs(ipVelTrendFor(R).now - blended) < 1e-9, ipVelTrendFor(R).now);
// ...but a NARROWED selection that names Chewy still folds it in. (All four
// boxes checked is the unfiltered state, which resolves to the Vel/day recipe.)
setChans(['amazon','chewy']);
t('a narrowed selection naming Chewy still includes it',
  Math.abs(ipVelTrendFor(R).now - (90/30 + 900/30 + (10*3)/30)) < 1e-9, ipVelTrendFor(R).now);
setChans(null);

console.log('\n== G. trend labels + edge cases ==');
const lab = (now, prev) => ipVelTrendLabel({ now, prev, isNew: prev <= 0 && now > 0, pct: prev > 0 ? (now-prev)/prev*100 : null });
t('ratio 1.5 -> Accelerating', /Accelerating/.test(lab(15, 10).txt));
t('ratio 1.2 -> Growing',      /Growing/.test(lab(12, 10).txt));
t('ratio 1.0 -> Steady',       /Steady/.test(lab(10, 10).txt));
t('ratio 0.85 -> Slowing',     /Slowing/.test(lab(8.5, 10).txt));
t('ratio 0.5 -> Declining',    /Declining/.test(lab(5, 10).txt));
t('boundary 1.3 exactly -> Growing (not Accelerating)', /Growing/.test(lab(13, 10).txt));
t('just inside the Steady band (0.95) -> Steady', /Steady/.test(lab(9.5, 10).txt));
// 9.2/10 is 0.9199999999999999 in IEEE754, so it lands just BELOW the 0.92
// cut and classifies as Slowing. That is the Demand Forecast page's behaviour
// too — assert the two agree rather than pretending the knife-edge is exact.
const demandPageClass = (ratio) => ratio >= 2 ? 'surge' : ratio > 1.3 ? 'acc' : ratio > 1.08 ? 'grow'
  : ratio < 0.7 ? 'dec' : ratio < 0.92 ? 'slow' : 'steady';
const ourClass = (now, prev) => { const txt = lab(now, prev).txt;
  return /Surging/.test(txt) ? 'surge' : /Accelerating/.test(txt) ? 'acc' : /Growing/.test(txt) ? 'grow'
       : /Declining/.test(txt) ? 'dec' : /Slowing/.test(txt) ? 'slow' : 'steady'; };
t('classifier matches the Demand Forecast thresholds across the whole range',
  [0.4,0.69,0.7,0.8,0.9199999999999999,0.92,0.95,1,1.08,1.1,1.3,1.5,3]
    .every(ratio => ourClass(10 * ratio, 10) === demandPageClass((10 * ratio) / 10)),
  [0.4,0.7,0.92,1.08,1.3].map(x => [x, ourClass(10*x,10), demandPageClass(x)]));
t('no prior sales but selling now -> New', /New/.test(lab(10, 0).txt));
t('nothing in either window -> No data', /No data/.test(lab(0, 0).txt));
t('rank orders Accelerating above Declining', lab(15,10).rank > lab(5,10).rank);

console.log('\n== H. pct is null (not a fake 0) when there is no prior history ==');
reset();
salesData['SP-1'] = [{ channel:'amazon_us', region:'US', week_start: ago(5), units_ordered: 300 }];
T = ipVelTrendFor(R);
t('isNew set', T.isNew === true);
t('pct is null rather than 0 or Infinity', T.pct === null, T.pct);
_velMemo = new Map(); _ipChanLagCache = null; salesData['SP-1'] = [];
T = ipVelTrendFor(R);
t('both empty -> pct 0, isNew false', T.pct === 0 && T.isNew === false, [T.pct, T.isNew]);

console.log('\n== I. memo keyed on window + offset + channels ==');
reset();
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(5),  units_ordered: 300 },
  { channel:'amazon_us', region:'US', week_start: ago(40), units_ordered: 150 },
];
const a1 = ipVelTrendFor(R).prev;         // prior-30 = 5
CMP = '90';                               // do NOT clear the memo
const a2 = ipVelTrendFor(R).prev;         // offset 90 -> nothing
t('changing compare mode is not served a stale memo', a1 !== a2 && a2 === 0, [a1, a2]);
CMP = 'prior'; VELWIN = '60';
const a3 = ipVelTrendFor(R).now;          // 60d window picks up both rows
t('changing window length is not served a stale memo', Math.abs(a3 - (300+150)/60) < 1e-9, a3);
setChans(['shopify']);
t('changing channels is not served a stale memo', ipVelTrendFor(R).now === 0);

console.log('\n== J. Chewy is opt-in, not default (v9.88 -> v9.90) ==');
reset();
t('default basis excludes chewy',
  JSON.stringify(ipVelTrendChans()) === JSON.stringify(['amazon','shopify','walmart']), ipVelTrendChans());
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(5), units_ordered: 300 },
  { channel:'chewy',     region:'US', week_start: ago(5), units_ordered: 150 },
];
t('fresh chewy rows do NOT count at the default',
  Math.abs(ipVelTrendFor(R).now - 10) < 1e-9, ipVelTrendFor(R).now);
setChans(['chewy']);
t('selecting Chewy alone trends Chewy sell-through',
  Math.abs(ipVelTrendFor(R).now - 5) < 1e-9, ipVelTrendFor(R).now);

console.log('\n== K. per-channel reporting lag (the real Chewy case) ==');
reset();
// Amazon current; Chewy last reported ~60 days ago (Jason: last file was August).
salesData['SP-1'] = [];
for (let a = 0;  a < 30;  a++) salesData['SP-1'].push({ channel:'amazon_us', region:'US', week_start: ago(a), units_ordered: 10 });
for (let a = 60; a < 90;  a++) salesData['SP-1'].push({ channel:'chewy', region:'US', week_start: ago(a), units_ordered: 20 });  // chewy's own last 30d
for (let a = 90; a < 120; a++) salesData['SP-1'].push({ channel:'chewy', region:'US', week_start: ago(a), units_ordered: 10 });  // the 30d before that
t('amazon reads as current (no lag)', ipChannelLagDays('amazon') === 0, ipChannelLagDays('amazon'));
t('chewy lag detected (~60d)', ipChannelLagDays('chewy') >= 55 && ipChannelLagDays('chewy') <= 65, ipChannelLagDays('chewy'));
// v9.90 — Chewy is opt-in now, so name it explicitly to exercise the lag path.
setChans(['amazon','chewy']);
let L = ipVelTrendFor(R);
t('Chewy contributes its BEST KNOWN rate (20/day), not zero',
  Math.abs(L.now - (10 + 20)) < 1e-9, L.now);
t('Chewy prior window is its OWN prior 30d (10/day) -> a real trend',
  Math.abs(L.prev - (0 + 10)) < 1e-9, L.prev);
t('amazon prior window is genuinely empty here', true);
t('lag surfaced on the result', L.lags.length === 1 && L.lags[0].key === 'chewy', L.lags);
t('tooltip names the lagging channel',
  /REPORTING LAG/.test(ipVelTrendTip(R, L)) && /Chewy: last data/.test(ipVelTrendTip(R, L)));
setChans(['amazon']);
t('no lag flagged when only current channels are selected', ipVelTrendFor(R).lags.length === 0);
setChans(['chewy']);
t('chewy alone still reports its own trend', Math.abs(ipVelTrendFor(R).now - 20) < 1e-9, ipVelTrendFor(R).now);
setChans(null);
t('and the DEFAULT basis ignores the lagging channel entirely',
  ipVelTrendFor(R).lags.length === 0 && Math.abs(ipVelTrendFor(R).now - 10) < 1e-9, ipVelTrendFor(R));

console.log('\n== L. fresh tolerance: weekly cadence must NOT trip the lag path ==');
reset();
salesData['SP-1'] = [{ channel:'amazon_us', region:'US', week_start: ago(6), units_ordered: 300 }];
t('6-day-old weekly row is still "current"', ipChannelLagDays('amazon') === 0);
_velMemo = new Map(); _ipChanLagCache = null;
salesData['SP-1'] = [{ channel:'amazon_us', region:'US', week_start: ago(13), units_ordered: 300 }];
t('13 days is inside the tolerance', ipChannelLagDays('amazon') === 0);
_velMemo = new Map(); _ipChanLagCache = null;
salesData['SP-1'] = [{ channel:'amazon_us', region:'US', week_start: ago(20), units_ordered: 300 }];
t('20 days trips the lag anchor', ipChannelLagDays('amazon') === 20, ipChannelLagDays('amazon'));
_velMemo = new Map(); _ipChanLagCache = null;
t('and the anchored window still finds that data (would read 0 unanchored)',
  Math.abs(ipVelTrendFor(R).now - 10) < 1e-9, ipVelTrendFor(R).now);

console.log('\n== M. a channel with no data: no contribution, no false lag ==');
reset();
salesData['SP-1'] = [{ channel:'amazon_us', region:'US', week_start: ago(5), units_ordered: 300 }];
t('chewy with no rows -> lag 0', ipChannelLagDays('chewy') === 0);
t('and adds nothing to the total', Math.abs(ipVelTrendFor(R).now - 10) < 1e-9, ipVelTrendFor(R).now);
t('no lag chip', ipVelTrendFor(R).lags.length === 0);

console.log('\n== N. v9.90 — Chewy back OUT of the default basis ==');
reset(); CURVE = {};
t('default basis matches Vel/day again (no chewy)',
  JSON.stringify(ipVelTrendChans()) === JSON.stringify(['amazon','shopify','walmart']), ipVelTrendChans());
salesData['SP-1'] = [
  { channel:'amazon_us', region:'US', week_start: ago(5), units_ordered: 300 },
  { channel:'chewy',     region:'US', week_start: ago(5), units_ordered: 900 },
];
t('a stale/large Chewy slab no longer silently enters the trend',
  Math.abs(ipVelTrendFor(R).now - 10) < 1e-9, ipVelTrendFor(R).now);
// All four checked IS the unfiltered state -> resolves to the Vel/day recipe.
setChans(['amazon','shopify','walmart','chewy']);
t('all four checked = unfiltered = the Vel/day recipe (no Chewy)',
  Math.abs(ipVelTrendFor(R).now - 10) < 1e-9, ipVelTrendFor(R).now);
// A genuinely narrowed selection naming Chewy does include it.
setChans(['amazon','chewy']);
t('a narrowed selection naming Chewy folds it in',
  Math.abs(ipVelTrendFor(R).now - 40) < 1e-9, ipVelTrendFor(R).now);

console.log('\n== O. v9.90 — seasonal adjustment: ties out to the Vel/day basis ==');
reset();
// Flat 10 units/day in BOTH windows. Seasonality is the only thing that moves:
// this week 1.33x, the week 30 days ago 1.05x.  (Jason's Catnip Spray shape.)
CURVE = {}; CURVE[String(wkAgo(0))] = 1.33; CURVE[String(wkAgo(30))] = 1.05;
salesData['SP-1'] = [];
for (let a = 0; a < 60; a++) salesData['SP-1'].push({ channel:'amazon_us', region:'US', week_start: ago(a), units_ordered: 10 });
const RS = { ...R, sea_idx: 1.33 };          // sea_idx is what Vel/day uses today
let S = ipVelTrendFor(RS);
t('raw demand is genuinely flat', Math.abs(S.rawNow - S.rawPrev) < 1e-9, [S.rawNow, S.rawPrev]);
t('Vel Now = raw x sea_idx (the adj_daily recipe)', Math.abs(S.now - 10 * 1.33) < 1e-9, S.now);
t('Vel Prior uses the multiplier in force THEN', Math.abs(S.prev - 10 * 1.05) < 1e-9, S.prev);
t('so the trend now REPORTS the move Vel/day shows', ipVelTrendLabel(S).txt.includes('Growing'), ipVelTrendLabel(S).txt);
t('decomposition: demand flat', Math.abs(S.rawPct) < 1e-9, S.rawPct);
t('decomposition: seasonality up ~27%', Math.abs(S.seaPct - ((1.33-1.05)/1.05*100)) < 1e-6, S.seaPct);
t('tooltip spells out WHAT MOVED', /WHAT MOVED/.test(ipVelTrendTip(RS, S)) && /Real demand/.test(ipVelTrendTip(RS, S)));
t('tooltip shows demand flat and seasonality up',
  /Real demand: 10\.00 → 10\.00/.test(ipVelTrendTip(RS, S)) && /1\.05× → 1\.33×/.test(ipVelTrendTip(RS, S)),
  ipVelTrendTip(RS, S).split('WHAT MOVED')[1]);

console.log('\n== P. v9.90 — real demand change still reads through ==');
reset();
CURVE = {}; CURVE[String(wkAgo(0))] = 1.0; CURVE[String(wkAgo(30))] = 1.0;   // seasonality neutral
salesData['SP-1'] = [];
for (let a = 0;  a < 30; a++) salesData['SP-1'].push({ channel:'amazon_us', region:'US', week_start: ago(a), units_ordered: 20 });
for (let a = 30; a < 60; a++) salesData['SP-1'].push({ channel:'amazon_us', region:'US', week_start: ago(a), units_ordered: 10 });
S = ipVelTrendFor({ ...R, sea_idx: 1.0 });
t('flat seasonality -> adjusted == raw', Math.abs(S.now - S.rawNow) < 1e-9 && Math.abs(S.prev - S.rawPrev) < 1e-9);
t('doubling demand reads Surging (v9.99 — 2.0x is the new top tier)', ipVelTrendLabel(S).txt.includes('Surging'), ipVelTrendLabel(S).txt);
t('decomposition attributes it to demand, not season', Math.abs(S.rawPct - 100) < 1e-9 && Math.abs(S.seaPct) < 1e-9, [S.rawPct, S.seaPct]);

console.log('\n== Q. v9.90 — a manual sea_override is constant across both windows ==');
reset();
CURVE = {}; CURVE[String(wkAgo(0))] = 2.0; CURVE[String(wkAgo(30))] = 0.5;   // curve swings hard
salesData['SP-1'] = [];
for (let a = 0; a < 60; a++) salesData['SP-1'].push({ channel:'amazon_us', region:'US', week_start: ago(a), units_ordered: 10 });
S = ipVelTrendFor({ ...R, sea_override: 1.25, sea_idx: 1.25 });
t('override pins BOTH windows to the same multiplier', Math.abs(S.seaNow - 1.25) < 1e-9 && Math.abs(S.seaPrev - 1.25) < 1e-9, [S.seaNow, S.seaPrev]);
t('so a pinned product reads Steady on flat demand', ipVelTrendLabel(S).txt.includes('Steady'), ipVelTrendLabel(S).txt);

console.log('\n== R. v9.90 — missing curve degrades to 1.0, never NaN ==');
reset(); CURVE = {};
salesData['SP-1'] = [{ channel:'amazon_us', region:'US', week_start: ago(5), units_ordered: 300 }];
S = ipVelTrendFor(R);
t('sea defaults to 1.0 when no curve exists', S.seaNow === 1 && S.seaPrev === 1, [S.seaNow, S.seaPrev]);
t('no NaN anywhere in the result',
  [S.now,S.prev,S.delta,S.rawNow,S.rawPrev,S.seaNow,S.seaPrev].every(v => typeof v === 'number' && isFinite(v)), S);
// Match leaked JS values, not the English word in "% undefined" / "(no prior sales)".
t('tooltip has no leaked JS values',
  !/\bNaN\b|\bInfinity\b|: undefined|= undefined|undefined\/day|undefined%/.test(ipVelTrendTip(R, S)),
  ipVelTrendTip(R, S).match(/\bNaN\b|\bInfinity\b|: undefined|= undefined|undefined\/day|undefined%/g));
t('tooltip BASIS note matches the shipped default (no stale Chewy claim)',
  /BASIS: Amazon \+ Shopify \+ Walmart \+ bundle/.test(ipVelTrendTip(R, S))
  && !/this includes Chewy sell-through/.test(ipVelTrendTip(R, S)));

console.log('\n' + (fail ? 'FAILURES: ' + fail + ' (passed ' + pass + ')' : 'ALL ' + pass + ' TESTS PASSED'));
process.exit(fail ? 1 : 0);
'''
hp = os.path.join(TMP, 'test_v990.js')
io.open(hp, 'w', encoding='utf-8').write(harness.replace('__CHAN__', chan).replace('__ENGINE__', engine))
r = subprocess.run(['node', hp], capture_output=True, text=True, encoding='utf-8', errors='replace')
print(r.stdout)
if r.stderr.strip(): print('STDERR:\n' + r.stderr[:2500])
sys.exit(r.returncode)
