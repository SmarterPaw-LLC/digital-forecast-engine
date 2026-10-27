
const chewyPnlData = [
  // 100-17384 ALLOWANCES
  { agreement_period_start:'2026-04-06', agreement_period_end:'2026-05-03',
    rebate_name:'Damages', category:'damages', rebate_pct_rate:2 },
  { agreement_period_start:'2026-05-04', agreement_period_end:'2026-05-31',
    rebate_name:'Damages', category:'damages', rebate_pct_rate:2 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'Damages', category:'damages', rebate_pct_rate:2 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'Freight', category:'freight', rebate_pct_rate:1.5 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'MDF/Coop', category:'coop_marketing', rebate_pct_rate:16 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'Satisfaction', category:'satisfaction_guarantee', rebate_pct_rate:2 },
  // the SAME period invoiced twice - must not charge its own rate twice
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'MDF/Coop', category:'coop_marketing', rebate_pct_rate:16 },
  // 100-17477 AUTOSHIP, running in PARALLEL over an overlapping range
  { agreement_period_start:'2026-05-04', agreement_period_end:'2026-05-31',
    rebate_name:'Auto Ship', category:'autoship', rebate_pct_rate:5 },
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-07-05',
    rebate_name:'Auto Ship', category:'autoship', rebate_pct_rate:5 },
  // a PROMO line - must never reach the standing floor
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-06-30',
    rebate_name:'HG Toys Buy 3 Get 1', category:'promo_bxgx', rebate_pct_rate:9 },
  // rate-less (the FTAS shape: rate lives in the NAME) - contributes nothing
  { agreement_period_start:'2026-06-01', agreement_period_end:'2026-06-30',
    rebate_name:'Treats 35% FTAS', category:'trade_allowance', rebate_pct_rate:null },
];
const chewyPnlSalesData = [
  { week_start:'2026-02-01', merch_sales:1000 },   // BEFORE any invoice: dark
  { week_start:'2026-04-12', merch_sales:1000 },   // Damages only      -> 2.0
  { week_start:'2026-05-10', merch_sales:1000 },   // + Auto Ship       -> 7.0
  { week_start:'2026-06-14', merch_sales:2000 },   // full stack        -> 26.5
];
let _chewyPricingAllow = null;
let _chewyPricingDerived = null;
let _chewyPricingSrcNote = '';

const CHEWY_STANDING_CATS = ['trade_allowance','autoship','damages','freight',
                             'coop_marketing','ad_spend','satisfaction_guarantee'];
const CHEWY_PROMO_CATS    = ['promo_bxgx','promo_lumpsum','evergreen_promo'];
function chewyPricingDeriveAllowances() {
  const rows = (typeof chewyPnlData !== 'undefined' && Array.isArray(chewyPnlData)) ? chewyPnlData : [];
  const rated = rows.filter(r => r && r.rebate_pct_rate != null && Number(r.rebate_pct_rate) > 0);
  if (!rated.length) return { pct: {}, note: 'No rate-bearing lines found in chewy_rebates — showing zeros. Upload rebate invoices on Data → Uploads, or type the rates in by hand.' };

  // latest invoice per (category | rebate_name)
  const latest = new Map();
  for (const r of rated) {
    const key = (r.category || 'other') + '|' + String(r.rebate_name || '').toLowerCase().trim();
    const prev = latest.get(key);
    if (!prev || String(r.invoice_date || '') > String(prev.invoice_date || '')) latest.set(key, r);
  }
  const pct = {};
  let newest = '';
  for (const r of latest.values()) {
    const cat = r.category || 'other';
    pct[cat] = (pct[cat] || 0) + Number(r.rebate_pct_rate);
    if (String(r.invoice_date || '') > newest) newest = String(r.invoice_date || '');
  }
  const names = [...latest.values()].length;
  return { pct, note: `Derived from ${names} rate-bearing rebate line(s) across ${rows.length} invoice rows · latest ${newest || 'n/a'}. Each rate is the most recent one seen for that rebate name.` };
}
function chewyAllowancePeriods() {
  const rows = (typeof chewyPnlData !== 'undefined' && Array.isArray(chewyPnlData)) ? chewyPnlData : [];
  const seen = new Set(); const out = [];
  for (const r of rows) {
    const rate = Number(r && r.rebate_pct_rate);
    const st = r && r.agreement_period_start, en = r && r.agreement_period_end;
    if (!isFinite(rate) || rate <= 0 || !st || !en) continue;
    const name = String(r.rebate_name || '').toLowerCase().trim();
    // ⚠ Dedupe on (period, name). One period invoiced twice must not charge
    // its own rate twice — P7-26 and P8-26 both land in August on the raw rows.
    const k = String(st).slice(0, 10) + '|' + String(en).slice(0, 10) + '|' + name;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ start: String(st).slice(0, 10), end: String(en).slice(0, 10),
               name, cat: r.category || 'other', rate });
  }
  return out;
}
function chewyStandingRateOn(periods, ymd) {
  const seen = new Set(); let tot = 0;
  for (const p of periods) {
    if (!CHEWY_STANDING_CATS.includes(p.cat)) continue;
    if (ymd < p.start || ymd > p.end || seen.has(p.name)) continue;
    seen.add(p.name); tot += p.rate;
  }
  return tot;
}
function chewyAllowanceBlend(periods, from, to) {
  const rows = (typeof chewyPnlSalesData !== 'undefined' && Array.isArray(chewyPnlSalesData)) ? chewyPnlSalesData : [];
  let num = 0, covered = 0, uncovered = 0;
  for (const r of rows) {
    const wk = String((r && r.week_start) || '').slice(0, 10);
    const rev = Number(r && r.merch_sales) || 0;
    if (!wk || rev <= 0) continue;
    if (from && wk < from) continue;
    if (to && wk > to) continue;
    const rate = chewyStandingRateOn(periods, wk);
    if (rate > 0) { num += rate * rev; covered += rev; } else { uncovered += rev; }
  }
  const total = covered + uncovered;
  return {
    // Retained for the provenance note ONLY. No caller may read this as
    // the rate to charge; chewyAllowanceStack deliberately ignores it.
    observedRate: covered > 0 ? (num / covered) : null,
    revCovered: covered, revUncovered: uncovered,
    uncoveredPct: total > 0 ? (100 * uncovered / total) : 0,
  };
}
function chewyAllowanceStack(opts) {
  const sum = (obj, cats) => cats.reduce((a, c) => a + (Number(obj && obj[c]) || 0), 0);
  if (_chewyPricingAllow) {
    const allCats = [...CHEWY_STANDING_CATS, ...CHEWY_PROMO_CATS];
    const edited = !!_chewyPricingDerived && allCats.some(c =>
      Math.abs((Number(_chewyPricingAllow[c]) || 0) - (Number(_chewyPricingDerived[c]) || 0)) > 0.001);
    return {
      standingPct: sum(_chewyPricingAllow, CHEWY_STANDING_CATS),
      promoPct:    sum(_chewyPricingAllow, CHEWY_PROMO_CATS),
      // v10.51 — rates on categories in NO list. Reported, never silently
      // folded in or dropped; that silence is what hid Satisfaction.
      unclassifiedPct: Object.keys(_chewyPricingAllow)
        .filter(c => !CHEWY_STANDING_CATS.includes(c) && !CHEWY_PROMO_CATS.includes(c))
        .reduce((a, c) => a + (Number(_chewyPricingAllow[c]) || 0), 0),
      byCat:       Object.assign({}, _chewyPricingAllow),
      source:      edited ? 'edited' : 'invoices',
      note:        _chewyPricingSrcNote || '',
    };
  }
  let d = { pct: {}, note: '' };
  try { d = chewyPricingDeriveAllowances(); } catch (e) { console.warn('chewyAllowanceStack:', e && e.message); }
  const pct = d.pct || {};
  const base = {
    standingPct: sum(pct, CHEWY_STANDING_CATS),
    promoPct:    sum(pct, CHEWY_PROMO_CATS),
    unclassifiedPct: Object.keys(pct)
      .filter(c => !CHEWY_STANDING_CATS.includes(c) && !CHEWY_PROMO_CATS.includes(c))
      .reduce((a, c) => a + (Number(pct[c]) || 0), 0),
    byCat:       Object.assign({}, pct),
    source:      Object.keys(pct).length ? 'invoices' : 'none',
    note:        d.note || '',
    blended:     false,
  };
  // v11.05 ⚠ A window attaches COVERAGE, and changes NOTHING ELSE.
  // `standingPct` is the rate from the invoices and is the rate charged,
  // windowed or not. v11.04 let the window move it and that was the bug:
  // periods we simply have not uploaded read as cheap months.
  if (opts && opts.from && opts.to) {
    const periods = chewyAllowancePeriods();
    if (periods.length) {
      const b = chewyAllowanceBlend(periods, opts.from, opts.to);
      return Object.assign({}, base, {
        windowFrom:   opts.from,
        windowTo:     opts.to,
        revCovered:   b.revCovered,
        revUncovered: b.revUncovered,
        // What share of this window has NO rebate invoice behind it. A
        // provenance caveat for the reader, never an input to the maths.
        uncoveredPct: b.uncoveredPct,
        observedRate: b.observedRate,
      });
    }
  }
  return base;
}

const out = {};
const P = chewyAllowancePeriods();
out.periodCount = P.length;
out.rateApr = chewyStandingRateOn(P, '2026-04-12');
out.rateMay = chewyStandingRateOn(P, '2026-05-10');
out.rateJun = chewyStandingRateOn(P, '2026-06-14');
out.rateDark = chewyStandingRateOn(P, '2026-02-01');
out.rateEdgeFirst = chewyStandingRateOn(P, '2026-06-01');
out.rateEdgeLast  = chewyStandingRateOn(P, '2026-07-05');
out.rateDayAfter  = chewyStandingRateOn(P, '2026-07-06');

out.blendAll  = chewyAllowanceBlend(P, '2026-01-01', '2026-12-31');
out.blendJun  = chewyAllowanceBlend(P, '2026-06-01', '2026-06-30');
out.blendDark = chewyAllowanceBlend(P, '2026-01-01', '2026-02-28');

// THE REGRESSION GUARD: what v11.03 did. Latest rate per name, flat.
const flat = chewyAllowanceStack();
out.flatPct = flat.standingPct;
out.flatBlended = flat.blended;
out.flatKeys = Object.keys(flat).sort();

const win = chewyAllowanceStack({ from:'2026-04-06', to:'2026-05-31' });
out.winPct = win.standingPct;
out.winBlended = win.blended;
out.winUncoveredPct = win.uncoveredPct;
out.winObserved = win.observedRate;
out.winSource = win.source;
out.winKeys = Object.keys(win).sort();

// the Pricing Scenarios working copy must still win, windowed or not
// 9 + 3 = 12, deliberately distinct from BOTH the 4.5 blend and the 26.5
// flat rate, so "the edit won" cannot be confused with either.
_chewyPricingAllow = { damages: 9, coop_marketing: 3 };
_chewyPricingDerived = { damages: 2, coop_marketing: 1 };
const edited = chewyAllowanceStack({ from:'2026-04-06', to:'2026-05-31' });
out.editedPct = edited.standingPct;
out.editedSource = edited.source;
out.editedBlended = !!edited.blended;
_chewyPricingAllow = null; _chewyPricingDerived = null;

// degenerate shapes must not throw or leak NaN
out.emptyWindow = chewyAllowanceBlend(P, '2030-01-01', '2030-12-31');
out.noPeriods   = chewyAllowanceBlend([], '2026-01-01', '2026-12-31');
console.log(JSON.stringify(out));
