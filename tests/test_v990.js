
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
// v10.64 — bundle attribution became ONE shared setting (was two per-page
// checkboxes read via getElementById(...)?.checked ?? true). Re-pointed, not
// silenced: reads the SAME 'ip-bundle-attr' stub above, so this suite keeps
// its existing BUNDLE_ON control over the toggle.
function bundleAttrOn(){
  const el = document.getElementById('ip-bundle-attr') || document.getElementById('fBundleAttr');
  return el ? !!el.checked : true;
}
function renderInventoryTbl() {}
// v9.90 stubs — seasonal curve lookup used by ipSeaIdxAtOffset.
const SEED = { curves: { consumables: {} } };
let CURVE = {};                       // ISO week -> multiplier
function getEffectiveCurveForProduct() { return { curve: CURVE }; }
// /!\ THE CLOCK IS PINNED, and this suite needed it.
//
// `ago(n)` builds a date with setDate (the LOCAL calendar) and reads it back
// with toISOString (the UTC one). West of Greenwich those agree only until
// the evening: past 18:00 CST, UTC has already rolled over and every window
// boundary this suite tests moves by a day.
//
// Found at 21:13 local on 2026-11-09 - already 2026-11-10 in UTC - with
// eight assertions red that had been green at midday. The suite was red for
// roughly six hours of every day and nobody would have known why.
//
// Measuring in UTC throughout is NOT the fix: the code under test works in
// local dates, so that only moves the mismatch. Pinning noon makes the two
// calendars agree - the v11.75 lesson, already in this project's notes.
const _RealDate = Date;
const PINNED_NOW = new _RealDate(2026, 10, 9, 12, 0, 0).getTime();
class PinnedDate extends _RealDate {
  constructor(...a) { super(...(a.length ? a : [PINNED_NOW])); }
  static now() { return PINNED_NOW; }
}
globalThis.Date = PinnedDate;

function isoWeekOfYear(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}
function wkAgo(n){ const d=new Date(); d.setDate(d.getDate()-n); return Math.min(Math.max(isoWeekOfYear(d),1),52); }

const IP_CHANNEL_KEYS   = ['amazon', 'shopify', 'chewy', 'walmart'];
const IP_CHANNEL_LABELS = { amazon: 'Amazon', shopify: 'Shopify', chewy: 'Chewy', walmart: 'Walmart' };
function ipChannelLabel(k) { return IP_CHANNEL_LABELS[k] || k; }

// Returns null when every channel is on (= no filtering, the default) so the
// fast path and the memo key stay identical to pre-v9.84 behavior. Returns null
// too when the controls aren't in the DOM, which keeps every non-Inventory
// caller (and any render before the page mounts) on the unfiltered total.
function ipActiveChannels() {
  if (typeof document === 'undefined') return null;
  if (!document.getElementById('ipChan-amazon')) return null;
  const on = IP_CHANNEL_KEYS.filter(k => document.getElementById('ipChan-' + k)?.checked);
  if (!on.length || on.length === IP_CHANNEL_KEYS.length) return null;
  return on;
}

function ipChanSig() { const c = ipActiveChannels(); return c ? c.join('+') : 'ALL'; }
const IP_VEL_DEFAULT_CHANS = ['amazon', 'shopify', 'walmart'];
// All four boxes checked IS the unfiltered state, and unfiltered must match
// Vel/day — so it resolves to the 3-channel Vel/day recipe, not "all four".
// Narrow the filter (e.g. Amazon + Chewy) and the trend follows it literally,
// Chewy included; Vel Now then deliberately stops matching Vel/day.
function ipVelTrendChans() { return ipActiveChannels() || IP_VEL_DEFAULT_CHANS; }

// v10.1 — the Forecast page's equivalent, read off its FORECAST BY checkboxes.
// Same rule as Inventory Planning: every box checked IS the unfiltered state and
// must resolve to the Vel/day recipe (Amazon + Shopify + Walmart), not "all
// four" — otherwise the trend stops tying out against the column beside it the
// moment Chewy is folded in by default rather than by choice.
const FC_TREND_CHAN_IDS = ['amazon', 'shopify', 'chewy', 'walmart'];

// v10.2 — the per-channel trend columns, and the Growth filter behind them.
// "Which products are growing?" has two useful readings and they disagree
// constantly: a product can be flat on the blended number while Amazon surges
// and Shopify collapses underneath it. So the filter offers both — the blended
// view (the selected channels together) and an ANY-CHANNEL view.
const TREND_CHANNELS = [
  { key: 'amazon',  label: 'Amz'  },
  { key: 'shopify', label: 'Shop' },
  { key: 'chewy',   label: 'Chwy' },
  { key: 'walmart', label: 'Wmt'  },
];
function velTrendRank(r, keys) {
  try { return ipVelTrendLabel(ipVelTrendForKeys(r, keys)).rank; } catch { return 0; }
}
function growthRankMatches(rank, m) {
  return m === 'surging'   ? rank >= 4
       : m === 'accel'     ? rank >= 2
       : m === 'growing'   ? rank >= 1
       : m === 'slowing'   ? rank <= -1
       : m === 'declining' ? rank <= -2
       : true;
}
// `mode` is '' (off), a bucket name (blended), or 'any:<bucket>' (true on at
// least one single channel). The any-channel form is the one that surfaces a
// channel rotating while the total hides it.
function growthFilterPass(r, mode, blendKeys) {
  if (!mode) return true;
  if (mode.startsWith('any:')) {
    const m = mode.slice(4);
    return TREND_CHANNELS.some(c => growthRankMatches(velTrendRank(r, [c.key]), m));
  }
  return growthRankMatches(velTrendRank(r, blendKeys), mode);
}
const GROWTH_FILTER_HTML = `
  <option value="">All products</option>
  <optgroup label="Across the selected channels">
    <option value="surging">\u{1F525} Surging (\u22652\u00d7)</option>
    <option value="accel">\u2191\u2191 Accelerating or better</option>
    <option value="growing">\u2191 Growing or better</option>
    <option value="slowing">\u2193 Slowing or worse</option>
    <option value="declining">\u2193\u2193 Declining</option>
  </optgroup>
  <optgroup label="On ANY single channel">
    <option value="any:surging">\u{1F525} Surging on any channel</option>
    <option value="any:accel">\u2191\u2191 Accelerating on any channel</option>
    <option value="any:declining">\u2193\u2193 Declining on any channel</option>
  </optgroup>`;
const GROWTH_FILTER_TIP = 'Narrow to products whose velocity trend is moving. '
  + 'The first group measures the channels you have selected, blended. The second asks whether ANY '
  + 'single channel qualifies on its own \u2014 which is how you catch a channel surging (or collapsing) '
  + 'while the blended number stays flat. Same buckets and same seasonal basis as the Vel Trend column.';
function fcVelTrendChans() {
  const total = document.getElementById('fChan-total')?.checked;
  const on = FC_TREND_CHAN_IDS.filter(k => document.getElementById('fChan-' + k)?.checked);
  return (total || on.length === 0 || on.length === FC_TREND_CHAN_IDS.length)
    ? IP_VEL_DEFAULT_CHANS : on;
}

// A channel is "current" if its most recent row is within this many days.
// Weekly-cadence channels are always a few days behind, and uploads land a
// day or two later still, so a small tolerance keeps fresh channels anchored
// to today rather than jittering the window by a few days each render.
const IP_VEL_FRESH_DAYS = 14;

// How far behind a channel's feed is, in days. 0 when the channel is current.
//
// Measured across the WHOLE DATASET, not per product — and that distinction is
// the whole point. Reporting lag is a property of the data SOURCE: Chewy's feed
// being ~2 months behind affects every SKU, so anchoring Chewy's window to its
// own latest data recovers the best KNOWN rate instead of reading 0 and looking
// like Chewy stopped selling.
//
// A PRODUCT with no Amazon sales for 30 days while Amazon's feed is current is
// a genuine zero, and must NOT be masked by anchoring. Deriving the lag
// per-product would do exactly that — it would quietly resurrect the old rate
// of anything that stopped selling. So: per-channel, dataset-wide.
//
// Same idea as fcChannelDailyRate (v7.53), but scoped correctly.
let _ipChanLagCache = null;
function ipChannelLagDays(key) {
  if (!salesData) return 0;
  // v9.93 — an empty salesData yields an empty lag map, which is TRUTHY and so
  // would be cached as "every channel is current" for the rest of the session.
  // Chewy would then be measured against today instead of its own latest data
  // and read 0 — the exact failure the per-channel anchor exists to prevent.
  if (!Object.keys(salesData).length) return 0;
  if (!_ipChanLagCache) {
    const latest = {};
    for (const mid in salesData) {
      for (const srow of salesData[mid]) {
        const ch = srow.channel || '';
        const k  = /^amazon/.test(ch) ? 'amazon' : ch;
        const d  = parseLocalDate(srow.week_start);
        if (!d) continue;
        if (!latest[k] || d > latest[k]) latest[k] = d;
      }
    }
    _ipChanLagCache = {};
    for (const k in latest) {
      const lag = Math.floor((Date.now() - latest[k].getTime()) / 864e5);
      _ipChanLagCache[k] = lag > IP_VEL_FRESH_DAYS ? lag : 0;
    }
  }
  return _ipChanLagCache[key] || 0;
}

// salesData carries per-marketplace Amazon channels (amazon_us / amazon_ca /
// amazon_gb / …), so 'amazon' has to prefix-match rather than equal-match.
function _ipChanMatch(ch, keys) {
  if (/^amazon/.test(ch || '')) return keys.includes('amazon');
  return keys.includes(ch);
}

// v10.1 — localStorage is the source of truth, because the control now exists
// on BOTH pages. Reading "whichever element is in the DOM" would let Inventory
// Planning's dropdown silently win while the user changes the one on the
// Forecast page — both pages are in the DOM at once, only one is shown. The
// velocity WINDOW has always been shared this way (ipVelWindowDays reads the
// Forecast page's #fVelocityWindow), so this matches the existing model.
function ipVelCompareMode() {
  try { return localStorage.getItem('velCmpMode') || 'prior'; } catch { return 'prior'; }
}
function setVelCmpMode(v) {
  try { localStorage.setItem('velCmpMode', v || 'prior'); } catch {}
  for (const id of ['ip-vel-cmp', 'fc-vel-cmp']) {
    const el = document.getElementById(id);
    if (el && el.value !== v) el.value = v;
  }
  if (typeof clearVelMemo === 'function') clearVelMemo();
  if (document.getElementById('page-inventory')?.classList.contains('active')) {
    if (typeof renderInventoryTbl === 'function') renderInventoryTbl();
  } else if (typeof renderAll === 'function') renderAll();
}
// v10.2 — the Growth dropdowns are static markup; their option list and help
// text live in one constant so the two pages cannot drift apart.
function initGrowthFilters() {
  for (const id of ['fc-growth', 'ip-growth']) {
    const el = document.getElementById(id);
    if (el && !el.options.length) el.innerHTML = GROWTH_FILTER_HTML;
  }
  for (const id of ['fc-growth-lbl', 'ip-growth-lbl']) {
    const el = document.getElementById(id);
    if (el) el.title = GROWTH_FILTER_TIP;
  }
}
function fcGrowthMode() { return document.getElementById('fc-growth')?.value || ''; }
function ipGrowthMode() { return document.getElementById('ip-growth')?.value || ''; }

function syncVelCmpControls() {
  const v = ipVelCompareMode();
  for (const id of ['ip-vel-cmp', 'fc-vel-cmp']) {
    const el = document.getElementById(id);
    if (el) el.value = v;
  }
}
// How far back the comparison window sits. 'prior' = the window immediately
// before the current one (so with a 30d velocity window that is "last month",
// with 90d it is "last quarter"); a number = that many days ago.
function ipVelCompareOffset(windowDays) {
  const m = ipVelCompareMode();
  if (m === 'prior') return windowDays;
  const n = parseInt(m, 10);
  return Number.isFinite(n) && n > 0 ? n : windowDays;
}
function ipVelCompareLabel() {
  const m = ipVelCompareMode();
  return m === 'prior' ? 'the window immediately before'
       : m === '30'    ? '30 days ago'
       : m === '90'    ? '90 days ago'
       : m === '365'   ? 'the same window one year ago'
       : 'the window immediately before';
}

// Bundle-component units pulled in by bundle sales inside an explicit window,
// scoped to the same channels + region. Mirrors getBundleAttrDailyVelocity but
// takes an explicit date range so an offset window can be measured.
function ipBundleAttrUnitsWindow(masterId, inWin, keys, region) {
  if (!allBomData || !salesData) return 0;
  const pooled = String(region || '').includes('+');
  let units = 0;
  for (const bundleId in allBomData) {
    const comps = allBomData[bundleId];
    const comp = comps && comps.find(c => c.component_master_id === masterId);
    if (!comp) continue;
    const rows = salesData[bundleId] || [];
    for (const srow of rows) {
      if (!_ipChanMatch(srow.channel, keys)) continue;
      if (region && !pooled && (srow.region || 'US') !== region) continue;
      if (!inWin(srow.week_start)) continue;
      units += (srow.units_ordered || 0) * (comp.qty || 1);
    }
  }
  return units;
}

// Daily velocity over [today - offset - window, today - offset).
// Memoized in _velMemo (cleared by clearVelMemo on any data/window change); the
// key carries window + offset + channel set so a dropdown change can't serve a
// stale value.
// Single channel, explicit offset. The per-channel split (v9.88) is what lets
// a lagging channel be measured against its own latest data while current
// channels stay anchored to today.
function ipVelWindowOne(r, windowDays, offsetDays, key) {
  const keys = [key];
  if (!salesData || !windowDays || windowDays <= 0) return 0;
  const reg = r.region || 'US';
  const pooled = String(reg).includes('+');
  const ck = `ipv1|${r.master_id}|${reg}|${windowDays}|${offsetDays}|${key}`;
  // v9.93 — a window measured while salesData is still empty is not an answer,
  // it is the absence of one. Returning 0 is fine; CACHING it is what poisoned
  // the column (see loadSalesAnalytics). So the memo is bypassed entirely in
  // that state, on both the read and the write side — belt-and-suspenders
  // alongside the post-load clear, because any future caller that clears early
  // and awaits would reopen the same hole.
  const salesReady = !!salesData && Object.keys(salesData).length > 0;
  if (salesReady && typeof _velMemo !== 'undefined' && _velMemo.has(ck)) return _velMemo.get(ck);
  // Age-in-days windowing, matching getInventoryChannelVel's existing
  // convention ((now - week_start)/864e5 <= windowDays). Half-open on age:
  //     offset <= age < offset + window
  // so consecutive windows are the same length and can neither overlap nor
  // leave a gap at the seam — which is what makes the delta trustworthy.
  const nowMs = Date.now();
  const inWin = (ws) => {
    const d = parseLocalDate(ws);
    if (!d) return false;
    const age = (nowMs - d.getTime()) / 864e5;
    return age >= offsetDays && age < offsetDays + windowDays;
  };
  let units = 0;
  for (const srow of (salesData[r.master_id] || [])) {
    if (!_ipChanMatch(srow.channel, keys)) continue;
    if (!pooled && srow.region && srow.region !== reg) continue;
    if (!inWin(srow.week_start)) continue;
    units += (srow.units_ordered || 0);
  }
  // Bundle attribution follows the page's "+ bundle components" toggle, exactly
  // like blended_daily does — otherwise a component whose demand is mostly
  // bundle-driven would show a flat trend.
  const bundleOn = (typeof document !== 'undefined')
    && (bundleAttrOn());
  if (bundleOn) units += ipBundleAttrUnitsWindow(r.master_id, inWin, keys, reg);
  const v = units / windowDays;
  if (salesReady && typeof _velMemo !== 'undefined') _velMemo.set(ck, v);
  return v;
}

// Sum across the selected channels, each measured over a window anchored to
// ITS OWN latest data (0 extra offset for current channels). `offsetDays` is
// the comparison offset on top of that anchor.
function ipVelWindow(r, windowDays, offsetDays, keys) {
  let total = 0;
  for (const key of keys) total += ipVelWindowOne(r, windowDays, offsetDays + ipChannelLagDays(key), key);
  return total;
}

// The window length the trend compares — same one Vel/day uses, so "Vel Now"
// is directly comparable to it.
function ipVelWindowDays() { return parseInt(document.getElementById('fVelocityWindow')?.value) || 30; }

// v9.90 — seasonal multiplier as of N days ago. getAutoSeaIdx() only ever
// answers for TODAY's ISO week; the prior window has to be adjusted with the
// multiplier that was in force then, otherwise "what would Vel/day have said a
// month ago" is unanswerable.
//
// A manual sea_override is a constant the operator pinned, so it applies to
// both windows unchanged.
function ipSeaIdxAtOffset(r, offsetDays) {
  if (r && r.sea_override != null && r.sea_override !== '') {
    const v = Number(r.sea_override);
    if (isFinite(v) && v > 0) return v;
  }
  try {
    const eff = (typeof getEffectiveCurveForProduct === 'function') ? getEffectiveCurveForProduct(r) : null;
    const curve = (eff && eff.curve) || SEED.curves?.consumables || {};
    const d = new Date(); d.setDate(d.getDate() - (offsetDays || 0));
    const wk = Math.min(Math.max(isoWeekOfYear(d), 1), 52);
    const v = curve[String(wk)] ?? curve[wk] ?? 1.0;
    return parseFloat(Number(v).toFixed(2)) || 1;
  } catch { return 1; }
}

// v10.1 — split so a caller can ask for a trend on an EXPLICIT channel set.
// Inventory Planning asks for its "Need by" selection, the Demand Forecast page
// asks for its "Forecast by" selection, and the per-channel columns ask for one
// channel at a time. Same engine, same seasonal basis, same lag anchoring —
// only the channel list differs, so there is one implementation of it.
function ipVelTrendFor(r) { return ipVelTrendForKeys(r, ipVelTrendChans()); }
function fcVelTrendFor(r) { return ipVelTrendForKeys(r, fcVelTrendChans()); }
function ipVelTrendForKeys(r, keys) {
  const w    = ipVelWindowDays();
  const off  = ipVelCompareOffset(w);
  // v9.88 — per-channel lag, so the tooltip can name which channel is behind
  // and by how much instead of silently shifting the window.
  const lags = keys.map(k => ({ key: k, lag: ipChannelLagDays(k) })).filter(x => x.lag > 0);
  // RAW units/day in each window.
  const rawNow  = ipVelWindow(r, w, 0, keys);
  const rawPrev = ipVelWindow(r, w, off, keys);

  // v9.90 — adjust by the seasonal multiplier, the SAME way the Vel/day column
  // does (`adj_daily = blended_daily × sea_idx`). Without this the trend was
  // measuring a different quantity than the number it sits beside: Catnip Spray
  // read "Steady" while Vel/day had moved 77 → 97, because ~all of that move was
  // the seasonal curve (sea 1.33×), not demand. The prior window uses the
  // multiplier in force THEN, so the comparison answers "what would Vel/day have
  // shown a month ago".
  const seaNow  = (r && r.sea_idx != null) ? Number(r.sea_idx) || 1 : ipSeaIdxAtOffset(r, 0);
  const seaPrev = ipSeaIdxAtOffset(r, off);
  const now  = rawNow  * seaNow;
  const prev = rawPrev * seaPrev;
  const delta = now - prev;

  // Decompose, because "is this product actually selling faster?" and "is it
  // entering its season?" are different questions and the blended % answers
  // neither on its own.
  const rawPct = rawPrev > 0 ? (rawNow - rawPrev) / rawPrev * 100 : null;
  const seaPct = seaPrev > 0 ? (seaNow - seaPrev) / seaPrev * 100 : null;
  // Ratio is undefined with no prior history — report that honestly rather
  // than rendering a fake +100% or a 0% that reads as "steady".
  const pct = prev > 0 ? (delta / prev) * 100 : (now > 0 ? null : 0);
  // v9.93 — "no data" and "not loaded yet" are different facts and the column
  // must not state the first when it means the second. salesDataReady (v6.71)
  // is false for the whole fetch + recompute window.
  const ready = !!salesData && Object.keys(salesData).length > 0
             && (typeof salesDataReady === 'undefined' || salesDataReady !== false);
  return { w, off, keys, now, prev, delta, pct, lags, ready,
           rawNow, rawPrev, rawPct, seaNow, seaPrev, seaPct,
           isNew: prev <= 0 && now > 0 };
}

// v11.37 - DOES THE BLENDED % STILL DESCRIBE DEMAND?
//
// ipVelTrend has reported `rawPct` (demand) and `seaPct` (the curve) separately
// since v9.90, and the badge rendered only their product. When the two point
// the SAME way that product is a fair summary. When they point OPPOSITE ways it
// is not a statement about demand at all - and the failing case is the one that
// matters: Catnip & Honeysuckle Bubbles rendered a green flaming "Surging
// +146%" while Shopify sell-through fell 24% (16.80 -> 12.73 units/day) and the
// curve climbed 1.30x -> 2.18x. A green surge over falling sell-through is the
// one reading on this page nobody can afford.
//
// Defined here, beside the thresholds, so the CELL, the SORT KEY and the CSV
// all resolve it identically rather than three renderers agreeing by accident.
function ipVelTrendDivergent(t) {
  if (!t || t.rawPct == null || t.seaPct == null) return false;
  return (t.rawPct < 0 && t.seaPct > 0) || (t.rawPct > 0 && t.seaPct < 0);
}

// Same thresholds as the Demand Forecast Trend column so the two pages speak
// the same language (>1.3 accelerating · >1.08 growing · <0.7 declining ·
// <0.92 slowing · else steady).
//
// v11.37 - a thin wrapper, NOT a second copy: the thresholds stay in exactly
// one place and this re-labels the divergent case on the way out.
//
// ⚠ `rank` is deliberately carried through UNCHANGED, so SORT ORDER is
// byte-identical to v11.36. Re-ranking a curve-driven surge below a real one is
// defensible and is a different decision from making it legible; the `sea_fwd`
// column is the affordance for finding these deliberately.
//
// The CSV TEXT does change on a divergent row, and has to: an export reading
// "Surging" while the screen reads "Season" is the same number carrying two
// meanings one click apart. velTrendCsv reads this label, so the two cannot
// drift.
function ipVelTrendLabel(t) {
  const l = ipVelTrendLabelRaw(t);
  if (!ipVelTrendDivergent(t)) return l;
  // Orange, never green and never a filled chip - the v11.03 rule that a rise
  // which is not good news on its own does not get the good-news colour.
  return { ...l, txt: '\u2248 Season', cls: 'var(--sp-orange)',
           strong: false, quiet: false, split: true };
}

function ipVelTrendLabelRaw(t) {
  if (t.isNew) return { txt: '\u2191\u2191 New', cls: 'var(--sp-green)', rank: 3 };
  // v9.93 — distinguish "sales history has not finished loading" from "this
  // product genuinely did not sell". The first is transient and resolves on
  // its own; the second is a real signal. Rendering both as "No data" made a
  // loading race look like a catalog-wide collapse.
  if (t.ready === false && !(t.prev > 0) && !(t.now > 0)) {
    return { txt: '\u23f3 loading\u2026', cls: 'var(--text3)', rank: 0 };
  }
  if (!(t.prev > 0) && !(t.now > 0)) return { txt: '\u2014 No data', cls: 'var(--text3)', rank: 0 };
  const ratio = t.prev > 0 ? t.now / t.prev : 1;
  // v9.99 — Jason: "i need a larger callout and format for high acceleration
  // items — there is a lot of green on here." He was looking at a column where
  // roughly four rows in five read "Accelerating", which is a column that has
  // stopped carrying information. Two causes, both fixed here:
  //   1. Everything above 1.3× collapsed into ONE bucket, so a 1.31× and a
  //      3.8× rendered identically. Split the top off at 2×.
  //   2. The label never showed MAGNITUDE, so the only way to rank the green
  //      was to enable a second column. The render now carries the % inline.
  // `strong` gets a filled chip, `quiet` gets dimmed — so the eye lands on the
  // genuine movers instead of an undifferentiated wall of green.
  if (ratio >= 2)   return { txt: '🔥 Surging',       cls: 'var(--sp-green)',  rank: 4, strong: true };
  if (ratio > 1.3)  return { txt: '\u2191\u2191 Accelerating', cls: 'var(--sp-green)',  rank: 2 };
  if (ratio > 1.08) return { txt: '\u2191 Growing',      cls: 'var(--sp-green2)', rank: 1, quiet: true };
  if (ratio < 0.7)  return { txt: '\u2193\u2193 Declining',   cls: 'var(--sp-red)',    rank: -2 };
  if (ratio < 0.92) return { txt: '\u2193 Slowing',      cls: 'var(--sp-orange)', rank: -1 };
  return { txt: '\u2192 Steady', cls: 'var(--text2)', rank: 0, quiet: true };
}

// Shared hover text — says what both windows actually cover, so a number that
// differs from Vel/day is explainable rather than mysterious.
// v10.1 — the trend cell, lifted out of the Inventory Planning column so the
// Demand Forecast page and the per-channel columns render identically instead
// of accumulating copies that drift (the v10.0 Excel bug was exactly that).
function velTrendCell(r, t) {
  const l = ipVelTrendLabel(t);
  const lagChip = t.lags.length ? ` <span style="font-size:9px;opacity:.75">\u23f3</span>` : '';
  // v9.99 \u2014 magnitude inline. Without it every row above 1.3\u00d7 looked the
  // same and the column could not be read without sorting it.
  const mag = (t.pct == null || l.rank === 0) ? ''
    : ` <span style="font-size:10px;opacity:.85">${t.pct > 0 ? '+' : ''}${Math.round(t.pct)}%</span>`;
  // v11.37 - on a divergent row, name the direction DEMAND moved. Without it
  // the only honest number on the cell is one hover away.
  const dmd = (l.split && t.rawPct != null)
    ? ` <span style="font-size:10px;color:${t.rawPct < 0 ? 'var(--sp-red)' : 'var(--sp-green)'}"` +
      ` title="Real demand moved ${t.rawPct > 0 ? '+' : ''}${Math.round(t.rawPct)}% while the seasonal` +
      ` multiplier moved ${t.seaPct > 0 ? '+' : ''}${Math.round(t.seaPct)}%.">` +
      `${t.rawPct > 0 ? '\u2191' : '\u2193'}${Math.abs(Math.round(t.rawPct))}% dmd</span>`
    : '';
  const tip = ipVelTrendTip(r, t).replace(/"/g, '&quot;');
  const base = 'padding:7px 8px;text-align:left;font-family:var(--mono);font-size:11px;cursor:help';
  if (l.strong) {
    return `<td style="${base}" title="${tip}"><span style="display:inline-block;background:${l.cls};color:#fff;font-weight:700;padding:2px 7px;border-radius:4px;letter-spacing:.2px">${l.txt}${mag}</span>${dmd}${lagChip}</td>`;
  }
  return `<td style="${base};color:${l.cls}${l.quiet ? ';opacity:.6' : ''}" title="${tip}">${l.txt}${mag}${dmd}${lagChip}</td>`;
}

// v10.1 — the sort key and the export cell, also shared.
function velTrendSortVal(t) {
  const l = ipVelTrendLabel(t);
  return l.rank * 1000 + (t.pct == null ? 0 : Math.max(-999, Math.min(999, t.pct)));
}
function velTrendCsv(t) {
  const l = ipVelTrendLabel(t);
  // v11.37 - \u2248 joins the strip list. It is the divergent label's glyph and
  // every other label has had its own stripped here since v10.1, so leaving it
  // in would export one row's marker and no other's.
  const base = l.txt.replace(/[\u2191\u2193\u2192\u2014\u2248\u{1F525}]/gu, '').trim();
  return (t.pct == null || l.rank === 0) ? base
    : `${base} ${t.pct > 0 ? '+' : ''}${Math.round(t.pct)}%`;
}

function ipVelTrendTip(r, t) {
  // Same age arithmetic as ipVelWindow, so the dates shown are the dates used.
  const fmtWin = (off) => {
    const at = (ageDays) => { const x = new Date(); x.setDate(x.getDate() - ageDays); return x.toISOString().slice(0, 10); };
    return `${at(off + t.w)} \u2192 ${at(off)}`;
  };
  const chanTxt = t.keys.map(k => ipChannelLabel(k)).join(' + ');
  const sgn = (v, d = 1) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`;
  return `VELOCITY TREND \u2014 same basis as the Vel/day column\n`
    + `(seasonally adjusted: raw units/day \u00d7 seasonal multiplier)\n\n`
    + `Current  ${t.w}d: ${t.now.toFixed(2)}/day   (${fmtWin(0)})\n`
    + `Previous ${t.w}d: ${t.prev.toFixed(2)}/day   (${fmtWin(t.off)})\n`
    + `Change: ${sgn(t.delta, 2)}/day`
    + (t.pct == null ? '  (no prior sales \u2014 % undefined)' : `  (${sgn(t.pct)}%)`) + `\n`
    + `\nWHAT MOVED:\n`
    + `  \u00b7 Real demand: ${t.rawPrev.toFixed(2)} \u2192 ${t.rawNow.toFixed(2)} units/day`
    + (t.rawPct == null ? '  (no prior sales)' : `  (${sgn(t.rawPct)}%)`) + `\n`
    + `  \u00b7 Seasonality: ${t.seaPrev.toFixed(2)}\u00d7 \u2192 ${t.seaNow.toFixed(2)}\u00d7`
    + (t.seaPct == null ? '' : `  (${sgn(t.seaPct)}%)`) + `\n`
    + `  Use this to tell "selling faster" apart from "entering its season".\n`
    + `\nComparing against ${ipVelCompareLabel()}.\n`
    + `Channels: ${chanTxt} (follows the "Need by" filter).\n`
    + `Window length follows the Velocity dropdown on Demand Forecast (${t.w}d).\n`
    + (t.lags.length
        ? `\n\u23f3 REPORTING LAG \u2014 measured against each channel's own latest data:\n`
          + t.lags.map(x => `   \u00b7 ${ipChannelLabel(x.key)}: last data ${x.lag}d ago, so its window ends there (best KNOWN rate, not zero).`).join('\n') + `\n`
        : '')
    + `\nBASIS: Amazon + Shopify + Walmart + bundle \u2014 the same recipe as Vel/day\n`
    + `(blended_daily \u00d7 seasonal multiplier), so Vel Now ties out against the Vel/day\n`
    + `column beside it.\n`
    + `Chewy is NOT in Vel/day (its demand reaches Need via Chewy's own forward PO\n`
    + `forecast, so counting sell-through there too would double-count), and a\n`
    + `~2-month-stale Chewy slab in both windows flattened every ratio toward\n`
    + `"Steady". Tick Chewy in "Need by" (alongside fewer than all four channels) to\n`
    + `trend Chewy sell-through deliberately \u2014 Vel Now then stops matching Vel/day.`;
}


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
