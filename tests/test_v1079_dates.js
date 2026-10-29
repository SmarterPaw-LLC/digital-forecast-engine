
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

let VALS = {};
const document = { getElementById: id => (id in VALS ? { value: VALS[id] } : null) };
// Three feeds with three different first days - that is the whole reason the
// shared resolver takes an all-time SOURCE rather than one global floor.
const chewyAdSpendData = [{ date: '2025-01-15' }, { date: '2026-03-01' }];
const chewyPnlSalesData = [{ week_start: '2025-02-03' }];
const chewyPnlData = [{ invoice_date: '2024-11-20' }];
const pnlData = [];
let _pnlSuppressDeltas = false;

function pnlAllTimeFrom(rows, field) {
  let min = null;
  for (const r of (rows || [])) {
    const v = r && r[field];
    if (v && (min === null || v < min)) min = v;
  }
  return min || '1970-01-01';
}
function computePnlDateRange(v, opts) {
  const today = new Date();
  const fmt = d => d.toISOString().split('T')[0];
  // v10.13 — all-time for the PDF builder. Deliberately does NOT touch
  // _pnlSuppressDeltas: this one stays pure so the PDF can loop periods.
  if (v === 'all') {
    // v11.02 — the caller may name its OWN feed. Chewy's tabs measure over
    // chewy_sales_weekly / chewy_ad_spend / chewy_rebates, which start on
    // different days, so an all-time floor taken from the Amazon source
    // would silently widen or narrow their windows. Absent the override the
    // behaviour is unchanged.
    if (opts && Array.isArray(opts.allRows)) {
      return { from: pnlAllTimeFrom(opts.allRows, opts.allField || 'week_start'), to: fmt(today), allTime: true };
    }
    const src = (typeof getPnlSource === 'function') ? getPnlSource() : { rows: pnlData };
    return { from: pnlAllTimeFrom(src.rows, 'week_start'), to: fmt(today), allTime: true };
  }
  if (v === 'custom') {
    return { from: (opts && opts.from) || fmt(today), to: (opts && opts.to) || fmt(today) };
  }
  if (v === 'last-report') {
    const isEu  = pnlRegion === 'EU';
    const table = isEu ? 'sku_economics_eu' : 'sku_economics';
    const cached = _pnlLastReportCache.get(`${table}|${pnlRegion}`);
    if (cached) return { from: cached.from, to: cached.to };
    return { from: fmt(today), to: fmt(today) };
  }
  if (v === 'ytd') {
    return { from: `${today.getFullYear()}-01-01`, to: fmt(today) };
  }
  // v7.24 — week/month/quarter presets. Sun-Sat week matches Amazon's
  // SKU Economics report convention (Amazon defines week 1 as Sun→Sat).
  // Calendar-month + calendar-quarter periods keep aggregation clean at
  // typical reporting boundaries.
  if (v === 'last-week') {
    // Previous COMPLETED Sun→Sat. If today is Tue, last week = last Sun..prior Sat.
    const d = new Date(today);
    const dow = d.getDay();  // 0 = Sun
    // Move back to this week's Sunday, then back 7 more days = last Sunday.
    const lastSun = new Date(d); lastSun.setDate(d.getDate() - dow - 7);
    const lastSat = new Date(lastSun); lastSat.setDate(lastSun.getDate() + 6);
    return { from: fmt(lastSun), to: fmt(lastSat) };
  }
  if (v === 'wtd') {
    // Current week: Sun through today.
    const d = new Date(today);
    const dow = d.getDay();
    const sun = new Date(d); sun.setDate(d.getDate() - dow);
    return { from: fmt(sun), to: fmt(today) };
  }
  if (v === 'mtd') {
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    return { from: fmt(first), to: fmt(today) };
  }
  if (v === 'last-month') {
    const first = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const last  = new Date(today.getFullYear(), today.getMonth(), 0);   // day 0 of current = last day of prev
    return { from: fmt(first), to: fmt(last) };
  }
  if (v === 'qtd') {
    const q = Math.floor(today.getMonth() / 3);   // 0..3
    const first = new Date(today.getFullYear(), q * 3, 1);
    return { from: fmt(first), to: fmt(today) };
  }
  if (v === 'last-quarter') {
    const curQ = Math.floor(today.getMonth() / 3);   // 0..3
    const prevQIdx = curQ === 0 ? 3 : curQ - 1;
    const yr = curQ === 0 ? today.getFullYear() - 1 : today.getFullYear();
    const first = new Date(yr, prevQIdx * 3, 1);
    const last  = new Date(yr, prevQIdx * 3 + 3, 0);   // last day of the 3rd month in that quarter
    return { from: fmt(first), to: fmt(last) };
  }
  if (v === 'last-year') {
    const yr = today.getFullYear() - 1;
    return { from: `${yr}-01-01`, to: `${yr}-12-31` };
  }
  // Rolling N-day window (7 / 30 / 60 / 90 / 180 / 365).
  const from = new Date(today); from.setDate(today.getDate() - parseInt(v));
  return { from: fmt(from), to: fmt(today) };
}
const CHEWY_PERIOD_SOURCES = {
  sales:     { field: 'week_start',   rows: () => chewyPnlSalesData },
  cost:      { field: 'week_start',   rows: () => chewyPnlSalesData },
  breakeven: { field: 'date',         rows: () => chewyAdSpendData },
  program:   { field: 'week_start',   rows: () => chewyPnlSalesData },
  ads:       { field: 'date',         rows: () => chewyAdSpendData },
  rebates:   { field: 'invoice_date', rows: () => chewyPnlData },
};
const CHEWY_PERIOD_DEFAULT = '365';
function chewyPeriodValue() {
  const el = document.getElementById('chpnl-period');
  return (el && el.value) || CHEWY_PERIOD_DEFAULT;
}
function getChewyPnlDateRange(sourceKey) {
  const v = chewyPeriodValue();
  // v10.13 - set here, in the DOM-reading entry point, exactly as Amazon's
  // getPnlDateRange does it. "Up 100% vs no prior period" is uniformly useless,
  // so every Chewy delta chip is suppressed on all-time. Previously only the
  // Sales tab did this; the other four showed a meaningless chip.
  _pnlSuppressDeltas = (v === 'all');
  const src = CHEWY_PERIOD_SOURCES[sourceKey] || CHEWY_PERIOD_SOURCES.sales;
  return computePnlDateRange(v, {
    from: document.getElementById('chpnl-from')?.value,
    to:   document.getElementById('chpnl-to')?.value,
    allRows:  src.rows() || [],
    allField: src.field,
  });
}
function getChewyPnlSalesDateRange()  { return getChewyPnlDateRange('sales'); }
function getChewyBreakevenDateRange() { return getChewyPnlDateRange('breakeven'); }
function getChewyPnlCostDateRange()   { return getChewyPnlDateRange('cost'); }
function getChewyProgramDateRange()   { return getChewyPnlDateRange('program'); }
function getChewyRebatesDateRange()   { return getChewyPnlDateRange('rebates'); }

const CUSTOM = { 'chpnl-period': 'custom', 'chpnl-from': '2026-02-01', 'chpnl-to': '2026-02-28' };

// B1 - custom range is read straight off the two shared inputs.
VALS = CUSTOM;
t('B1  custom range uses the shared from/to inputs',
  getChewyBreakevenDateRange(), { from: '2026-02-01', to: '2026-02-28' });

// B2 - THE ask: one control, so every tab resolves the SAME window. This is
// the guarantee v10.79's three-matching-copies check could only approximate.
VALS = CUSTOM;
t('B2  every Chewy tab resolves the same window from the one control',
  [getChewyPnlSalesDateRange(), getChewyPnlCostDateRange(), getChewyBreakevenDateRange(),
   getChewyProgramDateRange(), getChewyRebatesDateRange()]
    .map(r => r.from + '|' + r.to),
  ['2026-02-01|2026-02-28', '2026-02-01|2026-02-28', '2026-02-01|2026-02-28',
   '2026-02-01|2026-02-28', '2026-02-01|2026-02-28']);

// B3 - a blank "to" falls forward to today rather than emptying the window.
const today = new Date().toISOString().split('T')[0];
VALS = { 'chpnl-period': 'custom', 'chpnl-from': '2026-02-01', 'chpnl-to': '' };
t('B3  a blank end date falls forward to today', getChewyBreakevenDateRange().to, today);

// B4 - ⚠ all-time is the ONE period that is NOT shared: each tab floors at its
// own feed's first day. One global floor would silently widen or narrow a tab's
// window, which is exactly the kind of quiet disagreement the consolidation
// exists to prevent.
VALS = { 'chpnl-period': 'all' };
t('B4  all-time floors per feed, not globally',
  [getChewyBreakevenDateRange().from, getChewyPnlSalesDateRange().from,
   getChewyPnlCostDateRange().from, getChewyRebatesDateRange().from],
  ['2025-01-15', '2025-02-03', '2025-02-03', '2024-11-20']);
t('B4b all-time is flagged', getChewyBreakevenDateRange().allTime, true);
// and the delta chips go with it - previously only the Sales tab suppressed.
_pnlSuppressDeltas = false; getChewyPnlCostDateRange();
t('B4c all-time suppresses deltas on every tab, not just Sales', _pnlSuppressDeltas, true);
VALS = { 'chpnl-period': '90' }; _pnlSuppressDeltas = true; getChewyPnlCostDateRange();
t('B4d a bounded window does not suppress', _pnlSuppressDeltas, false);

VALS = { 'chpnl-period': 'ytd' };
t('B5  ytd still starts on Jan 1', getChewyBreakevenDateRange().from,
  new Date().getFullYear() + '-01-01');
VALS = { 'chpnl-period': '90' };
const d90 = new Date(); d90.setDate(d90.getDate() - 90);
t('B6  a trailing window still counts back from today',
  getChewyBreakevenDateRange().from, d90.toISOString().split('T')[0]);

// B7 - the Amazon-only keys the Chewy tabs inherited by sharing the resolver.
// Without the consolidation these nine options would have had no Chewy
// implementation at all.
VALS = { 'chpnl-period': 'last-month' };
const lmNow = new Date();
const lmFirst = new Date(lmNow.getFullYear(), lmNow.getMonth() - 1, 1);
const lmLast  = new Date(lmNow.getFullYear(), lmNow.getMonth(), 0);
const lmFmt = d => d.toISOString().split('T')[0];
t('B7  last-month resolves to the previous full calendar month',
  getChewyPnlSalesDateRange(), { from: lmFmt(lmFirst), to: lmFmt(lmLast) });

// B8 - no control in the DOM at all (the panel has not rendered yet) must
// fall back to the default rather than throw or resolve an empty window.
VALS = {};
t('B8  a missing control falls back to the 365-day default',
  getChewyPnlSalesDateRange().from,
  (() => { const d = new Date(); d.setDate(d.getDate() - 365); return d.toISOString().split('T')[0]; })());

console.log(JSON.stringify(out));
