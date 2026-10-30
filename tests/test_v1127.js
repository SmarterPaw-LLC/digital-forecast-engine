
'use strict';
const esc2 = (v) => String(v == null ? '' : v)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// The ledger as v11.08 stores it: CASE grain, a fee line, and one row whose
// product was never matched.
const walmartCatalogData = [
  { walmart_case_sku: 'KC211',   master_id: 'SP-0353', pack: 24, qty_cases: 100, amount: 7426.00 },
  { walmart_case_sku: 'KC211-01',master_id: 'SP-0353', pack: 6,  qty_cases: 50,  amount: 933.00  },
  { walmart_case_sku: 'MC003',   master_id: 'SP-0101', pack: 12, qty_cases: 80,  amount: 2400.00 },
  { walmart_case_sku: 'DC217',   master_id: 'SP-0900', pack: 12, qty_cases: 40,  amount: 1200.00 },
  { walmart_case_sku: 'KD001',   master_id: null,      pack: null, qty_cases: 19, amount: 0.19, is_fee_line: true },
  { walmart_case_sku: 'KF001',   master_id: null,      pack: null, qty_cases: 10, amount: 100.00 },
];
const allProducts = [
  { master_id: 'SP-0353', title: 'Zoomie Multipack Fish Toy',  brand: 'Kitty Ka-Zoom' },
  { master_id: 'SP-0101', title: 'Juananip Refill Bottle',     brand: 'Meowijuana' },
  { master_id: 'SP-0900', title: 'Tuffer Chewer Pizza',        brand: 'Doggijuana' },
];

let BRAND = '';
const EL = {
  'wmpnl-cost-thead': { innerHTML: '' },
  'wmpnl-cost-tbody': { innerHTML: '' },
  'wmpnl-cost-note' : { textContent: '' },
};
global.document = { getElementById: (id) => (id === 'wmpnl-brand' ? { value: BRAND } : (EL[id] || null)) };

function renderWalmartCost() {
  const head = document.getElementById('wmpnl-cost-thead');
  const body = document.getElementById('wmpnl-cost-tbody');
  const note = document.getElementById('wmpnl-cost-note');
  if (!head || !body) return;
  // v11.27 - the page-level Brand control scopes this tab too. The brand was
  // already resolved per row below and rendered beside the title; it was only
  // ever missing the filter. A control above three tabs that bit on two of
  // them is the v10.19 case.
  const brand = document.getElementById('wmpnl-brand')?.value || '';
  const rows = walmartCatalogData || [];
  const COLS = [
    ['Product', 'left'], ['Master ID', 'left'], ['Case SKUs', 'right'],
    ['Cases', 'right'], ['Eaches', 'right'], ['Amount', 'right'], ['Cost/each', 'right'],
  ];
  head.innerHTML = COLS.map(c => `<th style="padding:6px 8px;text-align:${c[1]};font-family:var(--mono);`
    + `font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;`
    + `border-bottom:1px solid var(--border2)">${esc2(c[0])}</th>`).join('');
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="${COLS.length}" style="text-align:center;padding:24px;color:var(--text3);`
      + `font-family:var(--mono);font-size:11px">No Walmart cost uploaded yet — drop the Items Sold ledger above.</td></tr>`;
    if (note) note.textContent = '';
    return;
  }
  // ⚠ Derived the same way the SQL view derives it: total dollars over
  // total eaches. A second formula here would be a second answer (hard rule #1).
  const by = {};
  let unmapped = 0, feeLines = 0;
  for (const r of rows) {
    if (r.is_fee_line) { feeLines++; continue; }
    if (!r.master_id || !r.pack || !(r.qty_cases > 0)) { unmapped++; continue; }
    const a = by[r.master_id] || (by[r.master_id] = { skus: 0, cases: 0, eaches: 0, amount: 0 });
    a.skus++; a.cases += Number(r.qty_cases) || 0;
    a.eaches += (Number(r.qty_cases) || 0) * (Number(r.pack) || 0);
    a.amount += Number(r.amount) || 0;
  }
  const pmap = {};
  (allProducts || []).forEach(p => { pmap[p.map_id || p.master_id] = p; });
  const out = Object.keys(by).map(mid => {
    const a = by[mid], p = pmap[mid] || {};
    return { mid, title: p.title || p.short_name || mid, brand: p.brand || '',
             skus: a.skus, cases: a.cases, eaches: a.eaches, amount: a.amount,
             perEach: a.eaches > 0 ? a.amount / a.eaches : null };
  }).filter(r => !brand || r.brand === brand)
    .sort((x, y) => y.amount - x.amount);
  const money = (v, d) => v == null ? '—' : '$' + v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const td = (v, al) => `<td style="padding:6px 8px;text-align:${al};font-family:var(--mono);font-size:11px;`
    + `border-bottom:1px solid var(--border2)">${v}</td>`;
  // /!\ An empty result is a MESSAGE, never a bare header. The two reasons it
  // can be empty need different words: a brand filter that excluded every row
  // is the operator's own doing, an unmatched ledger is work still to do.
  if (!out.length) {
    body.innerHTML = `<tr><td colspan="${COLS.length}" style="text-align:center;padding:24px;color:var(--text3);`
      + `font-family:var(--mono);font-size:11px">`
      + (brand ? `No ${esc2(brand)} products in the Walmart cost ledger.`
               : 'No case SKU is matched to a product yet \u2014 open the uploader to match them.')
      + `</td></tr>`;
  }
  else body.innerHTML = out.map(r =>
    '<tr>' + td(esc2(r.brand ? r.brand + ' · ' + r.title : r.title), 'left')
    + td(esc2(r.mid), 'left') + td(r.skus, 'right')
    + td(r.cases.toLocaleString(), 'right') + td(r.eaches.toLocaleString(), 'right')
    + td(money(r.amount, 2), 'right') + td(money(r.perEach, 4), 'right') + '</tr>').join('');
  if (note) {
    note.textContent = `${out.length} products${brand ? ' · brand: ' + brand : ''} · ${rows.length} case SKUs on record`
      + (feeLines ? ` · ${feeLines} non-product line(s)` : '')
      + (unmapped ? ` · ⚠ ${unmapped} case SKU(s) still need a product or a pack` : '');
  }
}

function run(brand) {
  BRAND = brand;
  EL['wmpnl-cost-tbody'].innerHTML = '';
  EL['wmpnl-cost-note'].textContent = '';
  renderWalmartCost();
  const body = EL['wmpnl-cost-tbody'].innerHTML;
  return {
    rows: (body.match(/<tr>/g) || []).length,
    body, note: EL['wmpnl-cost-note'].textContent,
  };
}

// D1 - the PRE-v11.27 pair of reads, on a DOM where the operator has set the
// Sales picker only. This is what two controls for one concept looked like.
function legacyPair(salesPick) {
  const dom = { 'wmpnl-brand': salesPick, 'wmads-brand': '' };
  return { sales: dom['wmpnl-brand'], ads: dom['wmads-brand'] };
}

const all   = run('');
const meowi = run('Meowijuana');
const kkz   = run('Kitty Ka-Zoom');
const none  = run('Doggijuana');   // has a product, but check the count
const empty = run('Nonexistent Brand');

console.log(JSON.stringify({
  allRows: all.rows, allNote: all.note,
  meowiRows: meowi.rows, meowiNote: meowi.note, meowiBody: meowi.body,
  kkzRows: kkz.rows, kkzBody: kkz.body,
  dogRows: none.rows,
  emptyRows: empty.rows, emptyBody: empty.body, emptyNote: empty.note,
  legacy: legacyPair('Meowijuana'),
}));
