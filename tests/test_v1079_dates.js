
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

let VALS = {};
const document = { getElementById: id => (id in VALS ? { value: VALS[id] } : null) };
const chewyAdSpendData = [{ date: '2025-01-15' }, { date: '2026-03-01' }];
const chewyPnlSalesData = [{ week_start: '2025-02-03' }];
function pnlAllTimeFrom(rows, field) {
  return rows.map(r => r[field]).sort()[0];
}
let _pnlSuppressDeltas = false;

function getChewyBreakevenDateRange() {
  const v = document.getElementById('chpnl-be-period')?.value || '90';
  const today = new Date();
  const fmt = d => d.toISOString().split('T')[0];
  if (v === 'custom') return { from: document.getElementById('chpnl-be-from')?.value, to: document.getElementById('chpnl-be-to')?.value || fmt(today) };
  if (v === 'all') return { from: pnlAllTimeFrom(chewyAdSpendData, 'date'), to: fmt(today), allTime: true };
  if (v === 'ytd') return { from: `${today.getFullYear()}-01-01`, to: fmt(today) };
  const f = new Date(today); f.setDate(today.getDate() - parseInt(v, 10));
  return { from: fmt(f), to: fmt(today) };
}
function getChewyPnlCostDateRange() {
  const v = document.getElementById('chpnl-cost-period')?.value || '90';
  const today = new Date();
  const fmt = d => d.toISOString().split('T')[0];
  // v10.13 — all time. This window only scopes the Units / weighting context;
  // the per-unit cost math is period-independent either way.
  if (v === 'custom') return { from: document.getElementById('chpnl-cost-from')?.value, to: document.getElementById('chpnl-cost-to')?.value || fmt(today) };
  if (v === 'all') return { from: pnlAllTimeFrom(chewyPnlSalesData, 'week_start'), to: fmt(today), allTime: true };
  if (v === 'ytd') return { from: `${today.getFullYear()}-01-01`, to: fmt(today) };
  const f = new Date(today); f.setDate(today.getDate() - parseInt(v, 10));
  return { from: fmt(f), to: fmt(today) };
}

// B1 - custom range is read straight off the two inputs.
VALS = { 'chpnl-be-period': 'custom', 'chpnl-be-from': '2026-02-01', 'chpnl-be-to': '2026-02-28' };
t('B1  Break-Even custom range uses the from/to inputs',
  getChewyBreakevenDateRange(), { from: '2026-02-01', to: '2026-02-28' });

VALS = { 'chpnl-cost-period': 'custom', 'chpnl-cost-from': '2026-04-01', 'chpnl-cost-to': '2026-04-30' };
t('B2  Cost custom range uses the from/to inputs',
  getChewyPnlCostDateRange(), { from: '2026-04-01', to: '2026-04-30' });

// B3 - a blank "to" falls forward to today rather than emptying the window.
const today = new Date().toISOString().split('T')[0];
VALS = { 'chpnl-be-period': 'custom', 'chpnl-be-from': '2026-02-01', 'chpnl-be-to': '' };
t('B3  a blank end date falls forward to today', getChewyBreakevenDateRange().to, today);

// B4 - every other option is untouched by the new branch.
VALS = { 'chpnl-be-period': 'all' };
t('B4  all-time still reads the earliest ad day', getChewyBreakevenDateRange().from, '2025-01-15');
VALS = { 'chpnl-be-period': 'ytd' };
t('B5  ytd still starts on Jan 1', getChewyBreakevenDateRange().from,
  new Date().getFullYear() + '-01-01');
VALS = { 'chpnl-be-period': '90' };
const d90 = new Date(); d90.setDate(d90.getDate() - 90);
t('B6  a trailing window still counts back from today',
  getChewyBreakevenDateRange().from, d90.toISOString().split('T')[0]);

console.log(JSON.stringify(out));
