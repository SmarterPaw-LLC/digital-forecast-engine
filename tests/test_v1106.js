
const chewyPnlSalesData = [
  { chewy_sku:'SZ', units_sold:5000, autoship_units:2000 },
  { chewy_sku:'SZ', units_sold:4496, autoship_units:1820 },   // -> 3820/9496 = 40.2%
  { chewy_sku:'SPIDER', units_sold:152, autoship_units:32 },  // -> 21.1%
  { chewy_sku:'NEVER',  units_sold:300, autoship_units:0   }, // -> 0%, not eligible
  { chewy_sku:'ALWAYS', units_sold:100, autoship_units:100 }, // -> 100%
  { chewy_sku:'ZEROVOL', units_sold:0, autoship_units:0 },    // no denominator
];

const CHEWY_STANDING_CATS = ['trade_allowance','autoship','damages','freight',
                             'coop_marketing','ad_spend','satisfaction_guarantee'];
const CHEWY_PROMO_CATS    = ['promo_bxgx','promo_lumpsum','evergreen_promo'];
const CHEWY_CONDITIONAL_CATS = ['autoship'];
function chewyAutoshipShareBySku() {
  const rows = (typeof chewyPnlSalesData !== 'undefined' && Array.isArray(chewyPnlSalesData)) ? chewyPnlSalesData : [];
  const u = {}, au = {};
  for (const r of rows) {
    const sku = String((r && r.chewy_sku) || '');
    if (!sku) continue;
    u[sku]  = (u[sku]  || 0) + (Number(r.units_sold) || 0);
    au[sku] = (au[sku] || 0) + (Number(r.autoship_units) || 0);
  }
  const out = {};
  for (const sku of Object.keys(u)) {
    if (u[sku] > 0) out[sku] = Math.min(1, au[sku] / u[sku]);
  }
  return out;
}
function chewySkuStandingPct(stack, sku, shares) {
  const base = Number(stack && stack.standingPct) || 0;
  const byCat = (stack && stack.byCat) || {};
  if (!sku || !shares || !Object.prototype.hasOwnProperty.call(shares, sku)) return base;
  const share = Number(shares[sku]);
  if (!isFinite(share) || share < 0) return base;
  let adj = base;
  for (const cat of CHEWY_CONDITIONAL_CATS) {
    const rate = Number(byCat[cat]) || 0;
    if (rate > 0) adj -= rate * (1 - share);   // charged on `share` of revenue, not all of it
  }
  return Math.max(0, adj);
}

const STACK = { standingPct: 26.5, byCat: {
  damages:2, freight:1.5, coop_marketing:16, satisfaction_guarantee:2, autoship:5 } };
const out = {};
const sh = chewyAutoshipShareBySku();
out.shares = {};
Object.keys(sh).forEach(k => out.shares[k] = +(sh[k]*100).toFixed(1));
out.zeroVolExcluded = !Object.prototype.hasOwnProperty.call(sh, 'ZEROVOL');

const R = (sku) => +chewySkuStandingPct(STACK, sku, sh).toFixed(3);
out.sz      = R('SZ');
out.spider  = R('SPIDER');
out.never   = R('NEVER');
out.always  = R('ALWAYS');
out.unknown = R('NOT_ON_RECORD');
out.noMap   = +chewySkuStandingPct(STACK, 'SZ', null).toFixed(3);
out.noSku   = +chewySkuStandingPct(STACK, '', sh).toFixed(3);

// Account reconciliation: allocate by share, weight by units, sum back.
const rows = [['SZ',9496],['SPIDER',152],['NEVER',300],['ALWAYS',100]];
let wsum = 0, usum = 0, asu = 0, uu = 0;
rows.forEach(([k,u]) => { wsum += R(k)*u; usum += u;
  asu += (sh[k]||0)*u; uu += u; });
out.weightedRate   = +(wsum/usum).toFixed(3);
out.acctShare      = +(asu/uu).toFixed(4);
out.acctRateDirect = +(21.5 + 5*(asu/uu)).toFixed(3);

// a stack with NO autoship line must be untouched by the split
const noAs = { standingPct: 21.5, byCat: { damages:2, freight:1.5,
  coop_marketing:16, satisfaction_guarantee:2 } };
out.noAsLine = +chewySkuStandingPct(noAs, 'NEVER', sh).toFixed(3);
console.log(JSON.stringify(out));
