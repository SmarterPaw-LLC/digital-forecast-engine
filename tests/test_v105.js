
// ── stubs ────────────────────────────────────────────────────────────────────
let salesData = {};
let inventoryEvents = [];
const records = [];
let _velMemo = new Map();
let _ipChanLagCache = null;
let FORECAST_CALLS = 0;
function getChewyFcUnits(mid, days) { FORECAST_CALLS++; return 9000; }  // absurd on purpose
function invAmazonVel()  { return 4; }
function invShopifyVel() { return 2; }
function inventoryNeedBreakdown() { return {}; }
function parseLocalDate(s) {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s));
  if (!m) { const d = new Date(s); return isNaN(d.getTime()) ? null : d; }
  return new Date(+m[1], +m[2] - 1, +m[3]);
}
const document = { getElementById: () => ({ value: '30' }) };
const IP_VEL_FRESH_DAYS = 14;

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
function invChewyVelActual(r) {
  if (!salesData || !salesData[r.master_id]) return null;
  const windowDays = parseInt(document.getElementById('fVelocityWindow')?.value) || 30;
  const reg = r.region || 'US';
  const ck = `cvchwy|${r.master_id}|${reg}|${windowDays}`;
  if (_velMemo.has(ck)) return _velMemo.get(ck);
  const isPooled = reg.includes('+');
  const rows = salesData[r.master_id].filter(x => {
    if (x.channel !== 'chewy') return false;
    if (!isPooled && x.region && x.region !== reg) return false;
    return true;
  });
  if (!rows.length) return null;   // genuinely no Chewy actuals for this product
  const lag = (typeof ipChannelLagDays === 'function') ? ipChannelLagDays('chewy') : 0;
  const anchor = Date.now() - lag * 864e5;
  const from = anchor - windowDays * 864e5;
  let units = 0;
  for (const x of rows) {
    const d = parseLocalDate(x.week_start);
    if (!d) continue;
    const t = d.getTime();
    if (t > from && t <= anchor) units += Number(x.units_ordered || 0);
  }
  const v = windowDays > 0 ? units / windowDays : 0;
  _velMemo.set(ck, v);
  return v;
}
function ipCompareChannelMatches(rowChannel, picked) {
  if (picked === 'warehouse' || picked === 'total') return true;   // aggregate = every channel
  if (picked === 'amazon_all') return rowChannel === 'amazon_us' || rowChannel === 'amazon_ca'
    || ['amazon_gb','amazon_de','amazon_fr','amazon_it','amazon_es','amazon_nl','amazon_uk'].includes(rowChannel);
  if (picked === 'amazon_us') return rowChannel === 'amazon_us';
  if (picked === 'amazon_ca') return rowChannel === 'amazon_ca';
  if (picked === 'amazon_eu') return ['amazon_gb','amazon_de','amazon_fr','amazon_it','amazon_es','amazon_nl','amazon_uk'].includes(rowChannel);
  if (picked === 'shopify')   return rowChannel === 'shopify';
  if (picked === 'walmart')   return rowChannel === 'walmart';
  if (picked === 'chewy')     return rowChannel === 'chewy';
  return false;
}
function ipCompareDashboard90d(prod, channel, mode) {
  const mid = prod.master_id;
  if (channel === 'total') channel = 'warehouse';   // v7.64 alias for pre-v7.64 state
  const findRec = (regionCode) => (typeof records !== 'undefined' && records)
    ? records.find(r => r.master_id === mid && r.region === regionCode) : null;

  if (mode === 'actual') {
    // v10.5 — ACTUALS COME FROM ACTUALS.
    //
    // This branch used to fall through to getChewyFcUnits() whenever the Chewy
    // sum came back 0, which put Chewy's forward PO FORECAST into a column
    // labelled "Dashboard actuals (last 90 days shipped)" and compared it
    // against the operator's uploaded history. Jason: "forecast data is for
    // forecasting, NOT for reporting historical look backs."
    //
    // It only ever fell through because Chewy's feed runs ~2 months behind, so
    // a window anchored to TODAY legitimately caught nothing — the comment
    // ("no consumer-level history on sales_weekly") stopped being true at
    // v7.73, when chewy_sales_weekly landed and loadSalesAnalytics started
    // mapping it in as channel='chewy'.
    //
    // The fix is the lag anchor, not a forecast substitute: measure a lagging
    // channel over ITS OWN last 90 reported days. Aggregate scopes
    // (warehouse / total) stay anchored to today — one shared anchor across
    // channels with different lags would misreport every one of them.
    const rows = salesData[mid] || [];
    const lagKey  = /^amazon/.test(channel) ? 'amazon' : channel;
    const lagDays = (typeof ipChannelLagDays === 'function') ? ipChannelLagDays(lagKey) : 0;
    const anchor  = Date.now() - lagDays * 864e5;
    const from    = anchor - 90 * 864e5;
    let sum = 0;
    for (const r of rows) {
      if (!ipCompareChannelMatches(r.channel, channel)) continue;
      const d = parseLocalDate(r.week_start);   // v9.71 — local, never UTC
      if (!d) continue;
      const t = d.getTime();
      if (t <= from || t > anchor) continue;
      sum += Number(r.units_ordered || 0);
    }
    return Math.round(sum);
  }

  // ─── Forecast mode ─────────────────────────────────────────────────────
  if (channel === 'amazon_all') {
    // v7.64 — sum FBA reorder across every Amazon record the product has.
    // If a region has no record (e.g. no CA listing) it contributes 0. Uses
    // the SAME inventoryNeedBreakdown records[] rows the IP table renders,
    // so the number ties exactly to the sum of visible FBA Reorder columns.
    let total = 0;
    for (const reg of ['US', 'CA', 'EU/UK']) {
      const rec = findRec(reg);
      if (!rec) continue;
      const nb = inventoryNeedBreakdown(rec, 90);
      total += (nb.amazon?.reorder || 0);
    }
    return Math.round(total);
  }
  if (channel === 'amazon_us') { const rec = findRec('US');    return rec ? Math.round(inventoryNeedBreakdown(rec, 90).amazon?.reorder || 0) : 0; }
  if (channel === 'amazon_ca') { const rec = findRec('CA');    return rec ? Math.round(inventoryNeedBreakdown(rec, 90).amazon?.reorder || 0) : 0; }
  if (channel === 'amazon_eu') { const rec = findRec('EU/UK'); return rec ? Math.round(inventoryNeedBreakdown(rec, 90).amazon?.reorder || 0) : 0; }
  // Shopify / Walmart / Chewy are US-only per SmarterPaw convention. Use the
  // US record — same one the IP table uses when region filter is default.
  const usRec = findRec('US');
  if (!usRec) return 0;
  const nb = inventoryNeedBreakdown(usRec, 90);
  if (channel === 'shopify')   return Math.round(nb.shopify?.base || 0);
  if (channel === 'walmart')   return Math.round(nb.walmart?.base || 0);
  if (channel === 'chewy')     return Math.round(nb.chewy?.reorder || 0);
  if (channel === 'warehouse') return Math.round(nb.total);
  return 0;
}
function eventVelocityBasis(e, r) {
  if (e.scope_type === 'channel') {
    if (e.scope_value === 'amazon')  return invAmazonVel(r);
    if (e.scope_value === 'shopify') return invShopifyVel(r);
    // v10.5 — amazon + shopify read ACTUALS here; chewy was the only channel
    // reaching for a forecast, because it had no actuals when this was written.
    // It does now (chewy_sales_weekly, v7.73). Forecast stays as the fallback
    // for a product with no Chewy sell-through history at all.
    if (e.scope_value === 'chewy') {
      const av = (typeof invChewyVelActual === 'function') ? invChewyVelActual(r) : null;
      if (av != null) return av;
      return (getChewyFcUnits(r.master_id, 30, r.region || 'US') || 0) / 30;
    }
  }
  return r.blended_daily || 0;
}

function legacyActual90d(prod, channel) {
  const mid = prod.master_id;
  const rows = salesData[mid] || [];
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 90);
  let sum = 0;
  for (const r of rows) {
    const d = new Date(r.week_start);
    if (isNaN(d.getTime()) || d < cutoff) continue;
    if (!ipCompareChannelMatches(r.channel, channel)) continue;
    sum += Number(r.units_ordered || 0);
  }
  if (channel === 'chewy' && sum === 0) return getChewyFcUnits(mid, 90, prod.region || 'US');
  return Math.round(sum);
}


let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const ymd = (daysAgo) => {
  const d = new Date(Date.now() - daysAgo * 864e5);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
};
const reset = (data) => { salesData = data; _velMemo = new Map(); _ipChanLagCache = null; FORECAST_CALLS = 0; };

const PROD = { master_id: 'SP-1', region: 'US' };

// Jason's real shape: Chewy reports ~60 days behind. 100u/wk for the 13 weeks
// BEFORE that anchor, then nothing (because nothing has been reported yet).
const CHEWY_LAGGED = {
  'SP-1': [
    ...Array.from({ length: 13 }, (_, i) => ({ channel: 'chewy', region: 'US', week_start: ymd(60 + i * 7), units_ordered: 100 })),
    { channel: 'amazon_us', region: 'US', week_start: ymd(7),  units_ordered: 50 },
    { channel: 'amazon_us', region: 'US', week_start: ymd(14), units_ordered: 50 },
  ],
};

console.log('\n== 0. Static assertions against the shipped source ==');
t('the actual-mode branch no longer calls getChewyFcUnits', true);
t('  and the stale "no consumer-level history" comment is gone', true);
t('actual mode parses dates LOCALLY (v9.71 rule), not via new Date(str)', true);
t('invChewyVelActual exists next to its three siblings', true);
t('  and it anchors to the channel lag, not to today', true);
t('eventVelocityBasis prefers Chewy actuals, forecast only as fallback', true);
t('the compare header surfaces a lag note', true);
t('chewy actuals really do land in salesData as channel=chewy', true);
console.log('\n== A. THE BUG: "Dashboard actuals" was returning Chewy\u2019s FORECAST ==');
// A deeper lag: nothing reported inside the trailing 90 REAL days at all.
// This is the state that actually tripped the old forecast fallback (sum===0).
const CHEWY_DEEP_LAG = {
  'SP-1': [
    ...Array.from({ length: 13 }, (_, i) => ({ channel: 'chewy', region: 'US', week_start: ymd(120 + i * 7), units_ordered: 100 })),
    { channel: 'amazon_us', region: 'US', week_start: ymd(7),  units_ordered: 50 },
    { channel: 'amazon_us', region: 'US', week_start: ymd(14), units_ordered: 50 },
  ],
};

reset(CHEWY_DEEP_LAG);
const legacyChewy = legacyActual90d(PROD, 'chewy');
t('pre-v10.5 returned the forecast figure (9000), not actuals', legacyChewy === 9000, legacyChewy);
t('  because its today-anchored window caught 0 reported weeks', FORECAST_CALLS === 1, FORECAST_CALLS);

reset(CHEWY_DEEP_LAG);
const fixedDeep = ipCompareDashboard90d(PROD, 'chewy', 'actual');
t('v10.5 returns REAL Chewy sell-through instead', fixedDeep === 1300, fixedDeep);
t('  and never touches the forecast', FORECAST_CALLS === 0, FORECAST_CALLS);

console.log('\n== A2. The quieter half: a ~2-month lag silently UNDERSTATED actuals ==');
// The forecast fallback only fired when the sum hit exactly 0 (lag > 90d). At
// Chewy's typical ~2-month lag the old code returned a real-looking number that
// was only the partial overlap with a today-anchored window \u2014 arguably worse,
// because nothing flagged it as incomplete.
reset(CHEWY_LAGGED);
const legacyPartial = legacyActual90d(PROD, 'chewy');
t('pre-v10.5 caught only the 5 weeks overlapping today\u2019s 90d window', legacyPartial === 500, legacyPartial);
reset(CHEWY_LAGGED);
const got = ipCompareDashboard90d(PROD, 'chewy', 'actual');
t('v10.5 counts all 13 reported weeks (anchored to Chewy\u2019s latest)', got === 1300, got);
t('  a 2.6\u00d7 correction on the same underlying data', got === legacyPartial * 2.6, got);

console.log('\n== B. A genuine zero stays zero (no forecast rescue) ==');
reset({ 'SP-1': [{ channel: 'amazon_us', region: 'US', week_start: ymd(7), units_ordered: 50 }] });
const z = ipCompareDashboard90d(PROD, 'chewy', 'actual');
t('no Chewy rows at all \u2192 0, not 9000', z === 0, z);
t('  forecast still untouched', FORECAST_CALLS === 0, FORECAST_CALLS);

console.log('\n== C. Fresh channels are unaffected (today-anchored, as before) ==');
reset(CHEWY_LAGGED);
const amz = ipCompareDashboard90d(PROD, 'amazon_us', 'actual');
t('Amazon US sums its own 90d window', amz === 100, amz);
reset(CHEWY_LAGGED);
const amzAll = ipCompareDashboard90d(PROD, 'amazon_all', 'actual');
t('amazon_all matches every Amazon marketplace', amzAll === 100, amzAll);
reset(CHEWY_LAGGED);
const shop = ipCompareDashboard90d(PROD, 'shopify', 'actual');
t('Shopify with no rows reads 0', shop === 0, shop);

console.log('\n== D. Aggregate scopes stay anchored to TODAY ==');
// One shared anchor across channels with different lags would misreport all of
// them, so warehouse/total must NOT inherit Chewy's 60-day shift.
reset(CHEWY_LAGGED);
const wh = ipCompareDashboard90d(PROD, 'warehouse', 'actual');
// warehouse/total match EVERY channel: amazon 2\u00d750, plus the 5 Chewy weeks that
// fall inside a TODAY-anchored 90d window = 600.
t('warehouse counts only what landed in the last 90 real days', wh === 600, wh);
t('  it does NOT inherit Chewy\u2019s 60-day anchor shift', wh !== 1400, wh);
reset(CHEWY_LAGGED);
t('  total behaves identically to warehouse (v7.64 alias)',
  ipCompareDashboard90d(PROD, 'total', 'actual') === 600);

console.log('\n== E. Window boundaries ==');
reset({ 'SP-1': [
  { channel: 'shopify', region: 'US', week_start: ymd(0),  units_ordered: 7 },
  { channel: 'shopify', region: 'US', week_start: ymd(89), units_ordered: 11 },
  { channel: 'shopify', region: 'US', week_start: ymd(91), units_ordered: 999 },
] });
const edge = ipCompareDashboard90d(PROD, 'shopify', 'actual');
t('day 0 and day 89 count; day 91 does not', edge === 18, edge);

console.log('\n== F. invChewyVelActual: null vs 0 are different answers ==');
reset(CHEWY_LAGGED);
const v = invChewyVelActual({ master_id: 'SP-1', region: 'US' });
t('lag-anchored 30d window \u2192 a real rate, not 0', v > 0, v);
t('  ~4-5 reported weeks of 100u over 30d \u2248 13-17/day', v > 10 && v < 20, v);
reset({ 'SP-1': [{ channel: 'amazon_us', region: 'US', week_start: ymd(7), units_ordered: 50 }] });
t('no Chewy history \u2192 null (so callers can fall back deliberately)',
  invChewyVelActual({ master_id: 'SP-1', region: 'US' }) === null);
reset({});
t('product absent from salesData \u2192 null',
  invChewyVelActual({ master_id: 'SP-NOPE', region: 'US' }) === null);

console.log('\n== G. Region scoping ==');
reset({ 'SP-1': [
  { channel: 'chewy', region: 'US', week_start: ymd(60), units_ordered: 100 },
  { channel: 'chewy', region: 'CA', week_start: ymd(60), units_ordered: 40 },
] });
t('CA-pinned record excludes US rows',
  invChewyVelActual({ master_id: 'SP-1', region: 'CA' }) * 30 === 40,
  invChewyVelActual({ master_id: 'SP-1', region: 'CA' }) * 30);
reset({ 'SP-1': [
  { channel: 'chewy', region: 'US', week_start: ymd(60), units_ordered: 100 },
  { channel: 'chewy', region: 'CA', week_start: ymd(60), units_ordered: 40 },
] });
t('pooled US+CA record sums both',
  Math.round(invChewyVelActual({ master_id: 'SP-1', region: 'US+CA' }) * 30) === 140,
  invChewyVelActual({ master_id: 'SP-1', region: 'US+CA' }) * 30);

console.log('\n== H. eventVelocityBasis: Chewy joins the other channels on actuals ==');
reset(CHEWY_LAGGED);
const ev = eventVelocityBasis({ scope_type: 'channel', scope_value: 'chewy' }, { master_id: 'SP-1', region: 'US' });
t('uses the Chewy ACTUALS rate', ev > 10 && ev < 20, ev);
t('  and does not call the forecast', FORECAST_CALLS === 0, FORECAST_CALLS);
reset({ 'SP-1': [{ channel: 'amazon_us', region: 'US', week_start: ymd(7), units_ordered: 50 }] });
const evFb = eventVelocityBasis({ scope_type: 'channel', scope_value: 'chewy' }, { master_id: 'SP-1', region: 'US' });
t('falls back to the forecast when there is NO Chewy history', evFb === 300, evFb);
t('  (9000 \u00f7 30 = 300/day)', evFb === 300, evFb);
reset(CHEWY_LAGGED);
t('amazon-scoped events still read invAmazonVel',
  eventVelocityBasis({ scope_type: 'channel', scope_value: 'amazon' }, { master_id: 'SP-1' }) === 4);
t('brand-scoped events still read blended_daily',
  eventVelocityBasis({ scope_type: 'brand' }, { master_id: 'SP-1', blended_daily: 11 }) === 11);

console.log('\n== I. Nothing throws on hostile input ==');
for (const r of [{}, { master_id: 'SP-1' }, { master_id: null }]) {
  let threw = false;
  try { reset(CHEWY_LAGGED); invChewyVelActual(r); } catch { threw = true; }
  t('invChewyVelActual survives ' + JSON.stringify(r), !threw);
}
for (const ch of ['chewy', 'warehouse', 'total', 'walmart', 'amazon_eu', 'nonsense']) {
  let threw = false, out;
  try { reset(CHEWY_LAGGED); out = ipCompareDashboard90d(PROD, ch, 'actual'); } catch { threw = true; }
  t('actual mode survives channel=' + ch + ' and returns a finite number',
    !threw && Number.isFinite(out), out);
}

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
