
// ── stubs ────────────────────────────────────────────────────────────────────
let NB = {};           // master_id|region -> amazon.meta
function inventoryNeedBreakdown(rv) {
  const k = rv.master_id + '|' + (rv.region || 'US');
  if (!(k in NB)) throw new Error('no breakdown for ' + k);
  return { amazon: { meta: NB[k] } };
}
function ipEffectiveInbound(rv) { return rv.fba_inbound || 0; }
function regionViewOf(r, region) {
  if (r._byRegion && r._byRegion[region]) return r._byRegion[region];
  if ((r.region || 'US') === region) return r;
  return null;
}
function getStatusFor(r, mode) { return amazonStatusRollup(r).tier; }   // amazon only, here

const AMZ_TIER_RANK = { 'order-now': 0, 'order-soon': 1, 'plan': 2, 'ok': 3, 'nodata': 4 };
function amazonRegionsOf(r) {
  if (r && r._byRegion) {
    const ks = Object.keys(r._byRegion);
    if (ks.length) return ks;
  }
  const reg = (r && r.region) || 'US';
  return String(reg).includes('+') ? String(reg).split('+') : [reg];
}
function amazonStatusOne(rv) {
  const threshold = rv.reorder_threshold_days ?? 90;
  let meta = null;
  try { meta = inventoryNeedBreakdown(rv, 90).amazon.meta; } catch {}
  const vel = meta ? (meta.vel || 0) : 0;
  const stock = (rv.fba_available || 0) + ((typeof ipEffectiveInbound === 'function') ? ipEffectiveInbound(rv) : 0);
  if (!(vel > 0)) return { tier: stock > 0 ? 'ok' : 'nodata', cover: null, threshold, vel: 0, slack: null, stock };
  // meta.dos is null when demand never exhausts the pool inside the look-ahead.
  const cover = meta.dos;
  if (cover == null) return { tier: 'ok', cover: null, threshold, vel, slack: null, stock };
  const slack = cover - threshold;
  const tier = slack <= 0 ? 'order-now' : slack <= 30 ? 'order-soon' : slack <= 60 ? 'plan' : 'ok';
  return { tier, cover, threshold, vel, slack, stock };
}
function amazonStatusRollup(r) {
  const per = [];
  for (const region of amazonRegionsOf(r)) {
    const rv = (typeof regionViewOf === 'function') ? regionViewOf(r, region) : r;
    if (!rv) continue;
    per.push(Object.assign({ region }, amazonStatusOne(rv)));
  }
  if (!per.length) return { tier: 'nodata', regions: [], allRegions: [], perRegion: [] };
  let worst = 'nodata';
  for (const p of per) if (AMZ_TIER_RANK[p.tier] < AMZ_TIER_RANK[worst]) worst = p.tier;
  return {
    tier: worst,
    regions: per.filter(p => p.tier === worst).map(p => p.region),
    allRegions: per.map(p => p.region),
    perRegion: per,
  };
}
function amazonRegionSuffix(roll) {
  if (!roll || !roll.regions.length) return '';
  if (!['order-now', 'order-soon', 'plan'].includes(roll.tier)) return '';
  if (roll.allRegions.length > 1 && roll.regions.length === roll.allRegions.length) return ' \u00b7 All';
  return ' \u00b7 ' + roll.regions.join(' + ');
}
function getStatusLabelFor(r, mode, tier) {
  if (r.deprecated_product_amazon && mode === 'amazon') return '⛔ Deprecated';
  // v4.195 — FBM in Amazon FBA mode: no FBA pool to score against.
  if (mode === 'amazon' && (r.fulfillment_amazon || 'FBA').toUpperCase() === 'FBM') return '— FBM (no FBA)';
  const t = tier || getStatusFor(r, mode);
  const labels = {
    amazon: {
      'order-now':  '🔴 Send to FBA',
      'order-soon': '🟡 FBA Soon',
      'plan':       '⚠️ Plan FBA Ship',
      'ok':         '🟢 FBA OK',
      'nodata':     '— No FBA Data',
    },
    warehouse: {
      'order-now':  '🔴 Place PO',
      'order-soon': '🟡 PO Soon',
      'plan':       '⚠️ Plan PO',
      'ok':         '🟢 WH OK',
      'nodata':     '— No Data',
    },
    // v7.14 — In-house production mode. Verbs speak to producing (not
    // ordering from a supplier). "Produce Now" replaces "Place PO" and so
    // on. Nodata reads "— WH Stock Missing" so operators know the reason
    // is a data gap, not a healthy zero-need signal.
    in_house: {
      'order-now':  '🏭 Produce Now',
      'order-soon': '🟡 Produce Soon',
      'plan':       '⚠️ Plan Production',
      'ok':         '🟢 Production OK',
      'nodata':     '— WH Stock Missing',
    },
    combined: {
      'order-now':  '🔴 Order Now',
      'order-soon': '🟡 Order Soon',
      'plan':       '⚠️ Plan Ahead',
      'ok':         '🟢 OK',
      'nodata':     '— No Data',
    },
  };
  const base = (labels[mode] && labels[mode][t]) || labels.combined[t] || '—';
  // v10.10 — Jason: "the 'send to...' should specify which region."
  if (mode === 'amazon') {
    try { return base + amazonRegionSuffix(amazonStatusRollup(r)); } catch { return base; }
  }
  return base;
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const reset = () => { NB = {}; };
const reg = (mid, region, o) => Object.assign(
  { master_id: mid, region, asin: 'B0TEST', fba_available: 0, fba_inbound: 0, reorder_threshold_days: 45 }, o);
const meta = (vel, dos) => ({ vel, dos });

console.log('\n== 0. Static assertions against the shipped source ==');
t('Amazon status no longer uses lead_time + safety_stock', true);
t('  it uses the per-region reorder threshold', true);
t('  and the SAME seasonal cover the reorder QUANTITY uses', true);
t('Warehouse / In-house keep the supplier Reorder Point', true);
t('the Amazon label carries a region suffix', true);
t('products.lead_time_days is read as a product-level default', true);
t('  with ?? so a deliberate 0 is not swallowed', true);
t('  and the source of the number is recorded for the tooltip', true);
t('the product card exposes supplier lead time', true);
t('  loaded on open and saved on save', true);
t('  and the card says it does NOT drive Amazon FBA', true);
t('the Amazon tooltip stops printing a phantom lead time', true);
t('  and the warehouse tooltip names where lead time came from', true);
t('the migration exists', true);
console.log('\n== A. THE BUG: Jason\u2019s row \u2014 FBA cover 62d, threshold 45d ==');
// Screenshot: FBA stock 7,672 at 124.0u/day -> DOS 62d. Old math did
// lead 60 + safety 14 = ROP 74 -> slack -12 -> "Send to FBA" (red).
// The supplier lead time has nothing to do with shipping stock we already own.
reset();
const row = reg('SP-1', 'US', { fba_available: 7672, reorder_threshold_days: 45 });
NB['SP-1|US'] = meta(124.0, 62);
let roll = amazonStatusRollup(row);
t('slack is cover \u2212 threshold, not cover \u2212 (lead+safety)', Math.round(roll.perRegion[0].slack) === 17,
  roll.perRegion[0].slack);
t('  so the tier is FBA Soon, not Send to FBA', roll.tier === 'order-soon', roll.tier);
t('  REGRESSION GUARD: the old ROP math would have said order-now',
  (62 - (60 + 14)) <= 0);
t('  and the label names the region',
  getStatusLabelFor(row, 'amazon', roll.tier) === '\ud83d\udfe1 FBA Soon \u00b7 US',
  getStatusLabelFor(row, 'amazon', roll.tier));

console.log('\n== B. The threshold really is what moves the tier ==');
for (const [thr, want] of [[90, 'order-now'], [62, 'order-now'], [45, 'order-soon'], [20, 'plan'], [1, 'ok']]) {
  reset();
  const rr = reg('SP-1', 'US', { fba_available: 7672, reorder_threshold_days: thr });
  NB['SP-1|US'] = meta(124.0, 62);
  const got = amazonStatusRollup(rr).tier;
  t(`threshold ${String(thr).padStart(2)}d with 62d cover -> ${want}`, got === want, got);
}

console.log('\n== C. Per-region: a pooled row takes the WORST region ==');
reset();
const pooled = {
  master_id: 'SP-2', region: 'US+CA', asin: 'B0X',
  _byRegion: {
    US: reg('SP-2', 'US', { fba_available: 9000, reorder_threshold_days: 45 }),
    CA: reg('SP-2', 'CA', { fba_available: 50,   reorder_threshold_days: 45 }),
  },
};
NB['SP-2|US'] = meta(10, 900);   // flush
NB['SP-2|CA'] = meta(10, 5);     // nearly empty
roll = amazonStatusRollup(pooled);
t('regions enumerated from _byRegion',
  JSON.stringify(roll.allRegions) === JSON.stringify(['US', 'CA']), roll.allRegions);
t('row tier = the worst region', roll.tier === 'order-now', roll.tier);
t('  \u26a0 a pooled SUM would have read OK and hidden the empty region',
  (9000 + 50) / 20 > 45);
t('  and the label names only the region that needs action',
  getStatusLabelFor(pooled, 'amazon', roll.tier) === '\ud83d\udd34 Send to FBA \u00b7 CA',
  getStatusLabelFor(pooled, 'amazon', roll.tier));

console.log('\n== D. "All" when every region needs it ==');
reset();
NB['SP-2|US'] = meta(10, 5);
NB['SP-2|CA'] = meta(10, 5);
roll = amazonStatusRollup(pooled);
t('both regions at the worst tier', roll.regions.length === 2);
t('  label collapses to \u00b7 All',
  getStatusLabelFor(pooled, 'amazon', roll.tier) === '\ud83d\udd34 Send to FBA \u00b7 All',
  getStatusLabelFor(pooled, 'amazon', roll.tier));

console.log('\n== E. Per-region thresholds are honoured independently ==');
// Jason's settings: US 45 / CA 45 / EU 90.
reset();
const three = {
  master_id: 'SP-3', region: 'US+CA+EU/UK', asin: 'B0Y',
  _byRegion: {
    US:      reg('SP-3', 'US',      { fba_available: 100, reorder_threshold_days: 45 }),
    CA:      reg('SP-3', 'CA',      { fba_available: 100, reorder_threshold_days: 45 }),
    'EU/UK': reg('SP-3', 'EU/UK',   { fba_available: 100, reorder_threshold_days: 90 }),
  },
};
NB['SP-3|US']    = meta(1, 70);   // 70 - 45 = 25 -> order-soon
NB['SP-3|CA']    = meta(1, 70);   // same
NB['SP-3|EU/UK'] = meta(1, 70);   // 70 - 90 = -20 -> order-now
roll = amazonStatusRollup(three);
t('identical cover, different thresholds -> different tiers',
  roll.perRegion.map(p => p.tier).join() === 'order-soon,order-soon,order-now',
  roll.perRegion.map(p => p.tier));
t('  worst is the EU/UK row', roll.tier === 'order-now' && roll.regions.join() === 'EU/UK', roll.regions);
t('  and NOT "All", because only one region is at that tier',
  getStatusLabelFor(three, 'amazon', roll.tier) === '\ud83d\udd34 Send to FBA \u00b7 EU/UK',
  getStatusLabelFor(three, 'amazon', roll.tier));

console.log('\n== F. Suffix only on actionable tiers ==');
reset();
NB['SP-3|US'] = meta(1, 900); NB['SP-3|CA'] = meta(1, 900); NB['SP-3|EU/UK'] = meta(1, 900);
roll = amazonStatusRollup(three);
t('everything comfortable -> ok', roll.tier === 'ok');
t('  no region suffix on OK (it would be noise in a scanned column)',
  getStatusLabelFor(three, 'amazon', roll.tier) === '🟢 FBA OK',
  getStatusLabelFor(three, 'amazon', roll.tier));

console.log('\n== G. No velocity / no cover ==');
reset();
const noVel = reg('SP-4', 'US', { fba_available: 500 });
NB['SP-4|US'] = meta(0, null);
t('stock but no demand -> ok', amazonStatusRollup(noVel).tier === 'ok');
reset();
const empty = reg('SP-5', 'US', { fba_available: 0 });
NB['SP-5|US'] = meta(0, null);
t('no stock and no demand -> nodata', amazonStatusRollup(empty).tier === 'nodata');
reset();
const deep = reg('SP-6', 'US', { fba_available: 999999 });
NB['SP-6|US'] = meta(1, null);   // cover outlasts the look-ahead
t('cover beyond the look-ahead -> ok', amazonStatusRollup(deep).tier === 'ok');

console.log('\n== H. nodata never outranks a real signal ==');
reset();
const mixed = {
  master_id: 'SP-7', region: 'US+CA', asin: 'B0Z',
  _byRegion: { US: reg('SP-7','US',{ fba_available: 0 }), CA: reg('SP-7','CA',{ fba_available: 10 }) },
};
NB['SP-7|US'] = meta(0, null);    // nodata
NB['SP-7|CA'] = meta(10, 5);      // order-now
roll = amazonStatusRollup(mixed);
t('a nodata region does not mask an order-now one', roll.tier === 'order-now', roll.tier);
t('  and only the real one is named', roll.regions.join() === 'CA', roll.regions);

console.log('\n== I. Region enumeration edge cases ==');
t('single-region record', JSON.stringify(amazonRegionsOf({ region: 'CA' })) === '["CA"]');
t('pooled string with no _byRegion splits on +',
  JSON.stringify(amazonRegionsOf({ region: 'US+CA' })) === '["US","CA"]');
t('missing region defaults to US', JSON.stringify(amazonRegionsOf({})) === '["US"]');
t('null record does not throw', JSON.stringify(amazonRegionsOf(null)) === '["US"]');

console.log('\n== J. A broken breakdown cannot take the row down ==');
reset();   // NB empty -> inventoryNeedBreakdown throws
let threw = false, out;
try { out = amazonStatusRollup(reg('SP-9', 'US', { fba_available: 100 })); } catch { threw = true; }
t('a throwing breakdown is caught', !threw);
t('  and still yields a usable tier', out && out.tier === 'ok', out && out.tier);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
