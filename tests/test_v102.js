
let salesData = {};
const allProducts = [], allBomData = [];
const _velMemo = new Map();
function clearVelMemo(){ _velMemo.clear(); }
let CHK = {};
const document = { getElementById: (id) => (id in CHK) ? CHK[id] : null };
const localStorage = { _d:{}, getItem(k){ return this._d[k] ?? null; }, setItem(k,v){ this._d[k]=v; } };
function ipActiveChannels(){ return null; }
function getEffectiveCurveForProduct(){ return { curve: {} }; }
function isoWeekOfYear(){ return 1; }
const SEED = { curves: {} };
function ipBundleAttrUnitsWindow(){ return 0; }
function ipChannelLabel(k){ return k; }
function parseLocalDate(d){ const [y,m,dd] = String(d).split('-').map(Number); return new Date(y, m-1, dd); }
function renderInventoryTbl(){ RENDERS.ip++; }
function renderAll(){ RENDERS.fc++; }
let RENDERS = { ip:0, fc:0 };
const IP_COLUMNS = [], FC_COLUMNS = [];

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
    && (document.getElementById('ip-bundle-attr')?.checked ?? true);
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

// Same thresholds as the Demand Forecast Trend column so the two pages speak
// the same language (>1.3 accelerating · >1.08 growing · <0.7 declining ·
// <0.92 slowing · else steady).
function ipVelTrendLabel(t) {
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
  const tip = ipVelTrendTip(r, t).replace(/"/g, '&quot;');
  const base = 'padding:7px 8px;text-align:left;font-family:var(--mono);font-size:11px;cursor:help';
  if (l.strong) {
    return `<td style="${base}" title="${tip}"><span style="display:inline-block;background:${l.cls};color:#fff;font-weight:700;padding:2px 7px;border-radius:4px;letter-spacing:.2px">${l.txt}${mag}</span>${lagChip}</td>`;
  }
  return `<td style="${base};color:${l.cls}${l.quiet ? ';opacity:.6' : ''}" title="${tip}">${l.txt}${mag}${lagChip}</td>`;
}

// v10.1 — the sort key and the export cell, also shared.
function velTrendSortVal(t) {
  const l = ipVelTrendLabel(t);
  return l.rank * 1000 + (t.pct == null ? 0 : Math.max(-999, Math.min(999, t.pct)));
}
function velTrendCsv(t) {
  const l = ipVelTrendLabel(t);
  const base = l.txt.replace(/[\u2191\u2193\u2192\u2014\u{1F525}]/gu, '').trim();
  return (t.pct == null || l.rank === 0) ? base
    : `${base} ${t.pct > 0 ? '+' : ''}${Math.round(t.pct)}%`;
}


function velTrendCell(r, t) {
  const l = ipVelTrendLabel(t);
  const lagChip = t.lags.length ? ` <span style="font-size:9px;opacity:.75">\u23f3</span>` : '';
  // v9.99 \u2014 magnitude inline. Without it every row above 1.3\u00d7 looked the
  // same and the column could not be read without sorting it.
  const mag = (t.pct == null || l.rank === 0) ? ''
    : ` <span style="font-size:10px;opacity:.85">${t.pct > 0 ? '+' : ''}${Math.round(t.pct)}%</span>`;
  const tip = ipVelTrendTip(r, t).replace(/"/g, '&quot;');
  const base = 'padding:7px 8px;text-align:left;font-family:var(--mono);font-size:11px;cursor:help';
  if (l.strong) {
    return `<td style="${base}" title="${tip}"><span style="display:inline-block;background:${l.cls};color:#fff;font-weight:700;padding:2px 7px;border-radius:4px;letter-spacing:.2px">${l.txt}${mag}</span>${lagChip}</td>`;
  }
  return `<td style="${base};color:${l.cls}${l.quiet ? ';opacity:.6' : ''}" title="${tip}">${l.txt}${mag}${lagChip}</td>`;
}

// v10.1 — the sort key and the export cell, also shared.
function velTrendSortVal(t) {
  const l = ipVelTrendLabel(t);
  return l.rank * 1000 + (t.pct == null ? 0 : Math.max(-999, Math.min(999, t.pct)));
}
function velTrendCsv(t) {
  const l = ipVelTrendLabel(t);
  const base = l.txt.replace(/[\u2191\u2193\u2192\u2014\u{1F525}]/gu, '').trim();
  return (t.pct == null || l.rank === 0) ? base
    : `${base} ${t.pct > 0 ? '+' : ''}${Math.round(t.pct)}%`;
}


function ipVelTrendTip(){ return 'tip'; }
for (const _c of TREND_CHANNELS) {
  const mk = (forKeys) => ({
    key: 'vel_trend_' + _c.key, label: _c.label + ' Trend',
    group: 'vel-trend', groupHdr: 'VELOCITY TREND', w: '116px', align: 'left',
    default: false,
    tip: `Velocity trend for ${_c.label} ALONE \u2014 same windows, same seasonal basis and same buckets as the Vel Trend column, but measuring only this channel. A product can read Steady blended while this column shows one channel surging and another collapsing.`,
    // v10.4b — Inventory Planning reads `sortVal`, the Demand Forecast reads
    // `get`. One object is pushed to both registries, so it carries both names
    // for the same number rather than sorting on one page and not the other.
    sortVal: r => velTrendSortVal(ipVelTrendForKeys(r, [_c.key])),
    get:     r => velTrendSortVal(ipVelTrendForKeys(r, [_c.key])),
    csv:     r => velTrendCsv(ipVelTrendForKeys(r, [_c.key])),
    render:  r => velTrendCell(r, ipVelTrendForKeys(r, [_c.key])),
  });
  IP_COLUMNS.push(mk());
  FC_COLUMNS.push(mk());
}


let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const ago = (d) => { const x = new Date(Date.now() - d * 864e5);
  return `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`; };
const MID = 'SP-1';
// Per-channel history: Amazon doubles, Shopify halves, Walmart flat.
function seed() {
  salesData = { [MID]: [] };
  const add = (ch, age, u) => salesData[MID].push({ channel: ch, region:'US', week_start: ago(age), units_ordered: u });
  for (let a = 0;  a < 30; a++) { add('amazon_us', a, 40); add('shopify', a, 5);  add('walmart', a, 10); }
  for (let a = 30; a < 60; a++) { add('amazon_us', a, 10); add('shopify', a, 20); add('walmart', a, 10); }
  clearVelMemo();
}
const R = { master_id: MID, region: 'US', sea_idx: 1 };
CHK = { fVelocityWindow: { value: '30' } };
seed();

console.log('\n== 0. Static assertions against the shipped source ==');
t('Forecast page has its own trend channel resolver', true);
t('Forecast page has the VELOCITY TREND group', true);
t('the Forecast column picker lists vel-trend', true);
t('both pages carry a Growth dropdown', true);
t('Forecast page carries a Vel vs dropdown', true);
t('the comparison window is one shared setting, not per-page DOM', true);
t('Growth filter is applied on the Forecast page', true);
t('Growth filter is applied at all four Inventory Planning sites', true);
t('the IP trend column delegates to the shared renderer', true);
t('saved views capture the Growth filter', true);
console.log('\n== A. The engine answers for an EXPLICIT channel set ==');
const amz = ipVelTrendForKeys(R, ['amazon']);
const shp = ipVelTrendForKeys(R, ['shopify']);
const wmt = ipVelTrendForKeys(R, ['walmart']);
t('Amazon 10/day -> 40/day reads 4.0x', Math.abs(amz.now / amz.prev - 4) < 1e-6, amz.now / amz.prev);
t('  which is the top tier', ipVelTrendLabel(amz).txt.includes('Surging'), ipVelTrendLabel(amz).txt);
t('Shopify 20/day -> 5/day reads 0.25x', Math.abs(shp.now / shp.prev - 0.25) < 1e-6, shp.now / shp.prev);
t('  which is Declining', ipVelTrendLabel(shp).txt.includes('Declining'), ipVelTrendLabel(shp).txt);
t('Walmart flat reads Steady', ipVelTrendLabel(wmt).txt.includes('Steady'), ipVelTrendLabel(wmt).txt);

console.log('\n== B. THE POINT: the blend hides what the channels are doing ==');
const blend = ipVelTrendForKeys(R, ['amazon','shopify','walmart']);
t('blended (40+5+10 vs 10+20+10) = 55/40 = 1.375x',
  Math.abs(blend.now / blend.prev - 1.375) < 1e-6, blend.now / blend.prev);
t('  so the blend reads merely Accelerating...',
  ipVelTrendLabel(blend).txt.includes('Accelerating'), ipVelTrendLabel(blend).txt);
t('  ...while Amazon is Surging and Shopify is Declining underneath it',
  ipVelTrendLabel(amz).rank === 4 && ipVelTrendLabel(shp).rank === -2);

console.log('\n== C. Growth filter: blended vs any-channel ==');
const keys = ['amazon','shopify','walmart'];
t('blended "surging" does NOT match (blend is only 1.375x)',
  growthFilterPass(R, 'surging', keys) === false);
t('any-channel "surging" DOES match (Amazon qualifies alone)',
  growthFilterPass(R, 'any:surging', keys) === true);
t('blended "accel" matches', growthFilterPass(R, 'accel', keys) === true);
t('blended "declining" does not', growthFilterPass(R, 'declining', keys) === false);
t('any-channel "declining" does (Shopify collapsed)',
  growthFilterPass(R, 'any:declining', keys) === true);
t('empty mode is a pass-through', growthFilterPass(R, '', keys) === true);
t('  and so is undefined', growthFilterPass(R, undefined, keys) === true);

console.log('\n== D. Bucket ladder is monotonic ==');
const ranks = ['surging','accel','growing'].map(m => growthRankMatches(4, m));
t('rank 4 satisfies surging, accel AND growing', ranks.every(Boolean), ranks);
t('rank 2 satisfies accel + growing but not surging',
  !growthRankMatches(2,'surging') && growthRankMatches(2,'accel') && growthRankMatches(2,'growing'));
t('rank 1 satisfies growing only',
  !growthRankMatches(1,'accel') && growthRankMatches(1,'growing'));
t('rank -2 satisfies slowing AND declining',
  growthRankMatches(-2,'slowing') && growthRankMatches(-2,'declining'));
t('rank -1 satisfies slowing but not declining',
  growthRankMatches(-1,'slowing') && !growthRankMatches(-1,'declining'));
t('rank 0 satisfies nothing but "all"',
  !['surging','accel','growing','slowing','declining'].some(m => growthRankMatches(0, m)));

console.log('\n== E. Per-channel columns were generated for BOTH pages ==');
const ipKeys = IP_COLUMNS.map(c => c.key), fcKeys = FC_COLUMNS.map(c => c.key);
for (const ch of ['amazon','shopify','chewy','walmart']) {
  t(`vel_trend_${ch} on both registries`,
    ipKeys.includes('vel_trend_' + ch) && fcKeys.includes('vel_trend_' + ch));
}
t('all 8 are default OFF (nobody\u2019s column set shifts)',
  IP_COLUMNS.concat(FC_COLUMNS).filter(c => c.key.startsWith('vel_trend_')).every(c => c.default === false));
t('all 8 sit in the vel-trend group',
  IP_COLUMNS.concat(FC_COLUMNS).filter(c => c.key.startsWith('vel_trend_')).every(c => c.group === 'vel-trend'));

console.log('\n== F. The generated columns actually render the right channel ==');
const amzCol = FC_COLUMNS.find(c => c.key === 'vel_trend_amazon');
const shpCol = FC_COLUMNS.find(c => c.key === 'vel_trend_shopify');
t('Amz Trend cell says Surging', /Surging/.test(amzCol.render(R)), amzCol.render(R).slice(0,90));
t('Shop Trend cell says Declining', /Declining/.test(shpCol.render(R)));
t('they are NOT the same cell (the channel arg is live)',
  amzCol.render(R) !== shpCol.render(R));
t('Amz Trend sorts above Shop Trend', amzCol.sortVal(R) > shpCol.sortVal(R),
  { amz: amzCol.sortVal(R), shp: shpCol.sortVal(R) });
t('export carries label + magnitude', /Surging \+\d+%/.test(amzCol.csv(R)), amzCol.csv(R));

console.log('\n== G. Forecast channel resolver mirrors the Inventory rule ==');
CHK = { fVelocityWindow:{value:'30'}, 'fChan-total':{checked:true},
        'fChan-amazon':{checked:true}, 'fChan-shopify':{checked:true},
        'fChan-chewy':{checked:true}, 'fChan-walmart':{checked:true} };
t('everything checked resolves to the Vel/day recipe, not all four',
  JSON.stringify(fcVelTrendChans()) === JSON.stringify(IP_VEL_DEFAULT_CHANS), fcVelTrendChans());
CHK['fChan-total'].checked = false;
CHK['fChan-chewy'].checked = false; CHK['fChan-walmart'].checked = false;
t('a genuine narrowing is honoured',
  JSON.stringify(fcVelTrendChans()) === JSON.stringify(['amazon','shopify']), fcVelTrendChans());
CHK['fChan-amazon'].checked = false; CHK['fChan-shopify'].checked = false;
t('nothing checked falls back rather than returning an empty plan',
  JSON.stringify(fcVelTrendChans()) === JSON.stringify(IP_VEL_DEFAULT_CHANS), fcVelTrendChans());

console.log('\n== H. The comparison window is ONE setting ==');
CHK = { 'ip-vel-cmp': { value:'prior' }, 'fc-vel-cmp': { value:'prior' } };
setVelCmpMode('90');
t('writing from either page updates the stored mode', ipVelCompareMode() === '90');
t('  and syncs the other page\u2019s dropdown',
  CHK['ip-vel-cmp'].value === '90' && CHK['fc-vel-cmp'].value === '90');
t('  and clears the velocity memo (windows changed)', _velMemo.size === 0);
setVelCmpMode('prior');
t('round-trips back', ipVelCompareMode() === 'prior');

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
