
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
  // v11.30 - [label, align, tip]. The four new ones carry the BASIS in the
  // tip, because this page reports WHOLESALE while the Sales tab beside it
  // reports RETAIL, and one label meaning two things a click apart is the
  // rule 3a defect. 'GM' is the app's declared wholesale prefix (v10.53);
  // unlike Chewy's GM there is NO allowance term here, because Walmart's
  // agreement has never been loaded - so each tip says so rather than
  // letting the shared prefix imply a deduction that is not made.
  const COLS = [
    ['Product', 'left'], ['Master ID', 'left'], ['Case SKUs', 'right'],
    ['Cases', 'right'], ['Eaches', 'right'],
    ['Invoiced $', 'right', 'What we billed Walmart for these cases. This is REAL revenue to us, unlike the Sales tab\u2019s Net Sales, which is what the shopper paid Walmart.'],
    ['Cost/each', 'right', 'Invoiced $ over eaches. Derived from the totals, never averaged across rows, so a small pack cannot outweigh a large one.'],
    ['COGS/u', 'right', 'Our landed cost per each, from the COGS page. Falls back to DTC then Amazon COGS, exactly as the Sales tab resolves it.'],
    ['COGS', 'right', 'COGS/u x eaches invoiced.'],
    ['GM $', 'right', 'Invoiced $ less COGS. WHOLESALE basis. \u26a0 Walmart allowances are NOT deducted (the agreement has never been loaded) and neither is Walmart Connect ad spend.'],
    ['GM %', 'right', 'GM $ over Invoiced $. WHOLESALE basis, before Walmart allowances and ad spend. Not comparable with the Sales tab\u2019s Contrib %, which is a RETAIL basis.'],
  ];
  head.innerHTML = COLS.map(c => {
    // Concatenated, not a template nested inside a template's ${}: the
    // nested form reads badly and defeats a brace-balance slicer that
    // scans a template to its next backtick (test_v1130 sliced a
    // TRUNCATED function on its first run because of it).
    const open = c[2]
      ? '<th title="' + String(c[2]).replace(/"/g, '&quot;') + '" style="cursor:help;'
      : '<th style="';
    return open
      + `padding:6px 8px;text-align:${c[1]};font-family:var(--mono);`
      + `font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;`
      + `border-bottom:1px solid var(--border2)">${esc2(c[0])}</th>`;
  }).join('');
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="${COLS.length}" style="text-align:center;padding:24px;color:var(--text3);`
      + `font-family:var(--mono);font-size:11px">No Walmart cost uploaded yet — drop the Items Sold ledger above.</td></tr>`;
    if (note) note.textContent = '';
    const sc0 = document.getElementById('wmpnl-cost-scorecards');
    if (sc0) sc0.innerHTML = '';   // v11.30 - never leave a strip describing a load that is gone
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
    // v11.30 - the SAME resolver the Sales tab uses, so the two tabs cannot
    // disagree about a product's COGS (hard rule #1).
    const cogsPer = (typeof walmartPnlCogs === 'function') ? walmartPnlCogs(mid) : null;
    // /!\ A product with no COGS is UNPRICED, never zero-cost. Zero would
    // render as a 100% margin, which is the one wrong answer on this page
    // that looks like good news.
    const cogsTot = (cogsPer != null && a.eaches > 0) ? cogsPer * a.eaches : null;
    const gm      = (cogsTot != null) ? a.amount - cogsTot : null;
    const gmPct   = (gm != null && a.amount > 0) ? (gm / a.amount) * 100 : null;
    return { mid, title: p.title || p.short_name || mid, brand: p.brand || '',
             skus: a.skus, cases: a.cases, eaches: a.eaches, amount: a.amount,
             perEach: a.eaches > 0 ? a.amount / a.eaches : null,
             cogsPer, cogsTot, gm, gmPct };
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
  else body.innerHTML = out.map(r => {
    // /!\ Unpriced reads as a NAMED gap, not as an em dash that could be
    // mistaken for a zero. The Sales tab words it the same way.
    const miss = '<span style="color:var(--red,#d63f2a)" title="No landed/DTC COGS set for this product — set it on the COGS page.">⚠ missing</span>';
    const gmCol = r.gm == null ? 'var(--text3)' : (r.gm <= 0 ? 'var(--red,#d63f2a)' : 'var(--text)');
    return '<tr>' + td(esc2(r.brand ? r.brand + ' · ' + r.title : r.title), 'left')
    + td(esc2(r.mid), 'left') + td(r.skus, 'right')
    + td(r.cases.toLocaleString(), 'right') + td(r.eaches.toLocaleString(), 'right')
    + td(money(r.amount, 2), 'right') + td(money(r.perEach, 4), 'right')
    + td(r.cogsPer == null ? miss : money(r.cogsPer, 4), 'right')
    + td(r.cogsTot == null ? '—' : money(r.cogsTot, 2), 'right')
    + `<td style="padding:6px 8px;text-align:right;font-family:var(--mono);font-size:11px;`
    + `border-bottom:1px solid var(--border2);color:${gmCol}">${r.gm == null ? '—' : money(r.gm, 2)}</td>`
    + `<td style="padding:6px 8px;text-align:right;font-family:var(--mono);font-size:11px;`
    + `border-bottom:1px solid var(--border2);color:${gmCol}">${r.gmPct == null ? '—' : r.gmPct.toFixed(1) + '%'}</td>`
    + '</tr>';
  }).join('');
  // v11.30 - totals. COGS and GM are summed over PRICED rows only and the
  // coverage is STATED, never assumed: an unpriced product silently counted
  // at zero cost would lift the blended GM% and nothing on screen would say
  // why (the v11.01 pricedUnits argument).
  const tot = out.reduce((t, r) => {
    t.amount += r.amount; t.eaches += r.eaches; t.skus += r.skus;
    if (r.cogsTot != null) { t.cogs += r.cogsTot; t.gm += r.gm; t.pricedAmount += r.amount; }
    else t.unpriced++;
    return t;
  }, { amount: 0, eaches: 0, skus: 0, cogs: 0, gm: 0, pricedAmount: 0, unpriced: 0 });
  // /!\ The blended GM% divides by PRICED dollars, not by all of them.
  // Dividing by the whole would quietly charge no cost to the unpriced share.
  const gmPctTot = tot.pricedAmount > 0 ? (tot.gm / tot.pricedAmount) * 100 : null;
  const covPct   = tot.amount > 0 ? (tot.pricedAmount / tot.amount) * 100 : 0;
  const sc = document.getElementById('wmpnl-cost-scorecards');
  if (sc) sc.innerHTML = out.length ? [
    { label: 'Invoiced Revenue', val: money(tot.amount, 2),
      sub: `${tot.eaches.toLocaleString()} eaches · ${tot.skus} case SKUs`,
      src: 'walmart_catalog',
      tip: 'What we billed Walmart, store and ecom. This ledger is 100% of the channel, unlike the Sales tab, which is walmart.com sell-through only.' },
    { label: 'Total COGS', val: money(tot.cogs, 2),
      sub: tot.unpriced ? `⚠ ${tot.unpriced} product(s) unpriced` : 'landed-cost basis',
      src: 'product_cogs',
      tip: 'Landed cost x eaches invoiced, over the products that have a COGS. An unpriced product is EXCLUDED rather than counted at zero.' },
    { label: 'GM $', val: money(tot.gm, 2),
      sub: covPct >= 99.95 ? 'Invoiced − COGS' : `priced on ${covPct.toFixed(1)}% of invoiced $`,
      src: 'ƒ Invoiced − COGS (WHOLESALE basis)',
      tip: 'Invoiced Revenue less COGS. ⚠ Walmart allowances are NOT deducted (the agreement has never been loaded) and neither is Walmart Connect ad spend, so this reads optimistic.' },
    { label: 'GM %', val: gmPctTot == null ? '—' : gmPctTot.toFixed(1) + '%',
      sub: 'before Walmart allowances',
      src: 'ƒ GM $ ÷ priced Invoiced $ (WHOLESALE basis)',
      tip: 'Portfolio GM $ over the invoiced dollars that carry a COGS. Not comparable with the Sales tab\u2019s Contrib %, which is a RETAIL basis over walmart.com sell-through.' },
  ].map(pnlCard).join('') : '';
  if (note) {
    note.textContent = `${out.length} products${brand ? ' · brand: ' + brand : ''} · ${rows.length} case SKUs on record`
      + ` · cumulative, not scoped by Period`
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
