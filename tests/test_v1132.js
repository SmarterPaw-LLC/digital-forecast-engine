
'use strict';

// ── fixture ───────────────────────────────────────────────────────────────
// Three products. SP-C is deliberately absent from the ledger.
const walmartPnlData = [
  { master_id: 'SP-A', week_start: '2026-06-01', units: 600, net_sales: 3000, product_name: 'A', walmart_item_number: '1' },
  { master_id: 'SP-A', week_start: '2026-06-08', units: 400, net_sales: 2000, product_name: 'A', walmart_item_number: '1' },
  { master_id: 'SP-B', week_start: '2026-06-01', units: 500, net_sales: 2000, product_name: 'B', walmart_item_number: '2' },
  { master_id: 'SP-C', week_start: '2026-06-01', units: 100, net_sales:  600, product_name: 'C', walmart_item_number: '3' },
];
const allProducts = [
  { master_id: 'SP-A', title: 'Zoom Sticks',   short_name: 'Zoom Sticks',   brand: 'Kitty Ka-Zoom', category_id: 1 },
  { master_id: 'SP-B', title: 'Juananip Tub',  short_name: 'Juananip Tub',  brand: 'Meowijuana',    category_id: 1 },
  { master_id: 'SP-C', title: 'Tuffer Pizza',  short_name: 'Tuffer Pizza',  brand: 'Doggijuana',    category_id: 1 },
];
const allCategories = [{ id: 1, category: 'Toys' }];
// perEach: SP-A 7200/2400 = 3.00, SP-B 1200/960 = 1.25. SP-C absent.
const walmartCatalogData = [
  { walmart_case_sku: 'KA', master_id: 'SP-A', pack: 24, qty_cases: 100, amount: 7200 },
  { walmart_case_sku: 'KB', master_id: 'SP-B', pack: 12, qty_cases:  80, amount: 1200 },
  { walmart_case_sku: 'FEE', master_id: null, pack: null, qty_cases: 5, amount: 0.05, is_fee_line: true },
];
const cogsByMaster = {
  'SP-A': { landed_cost: 1.20 },
  'SP-B': { landed_cost: 0.50 },
  'SP-C': { landed_cost: 0.30 },
};

// ── stubs ─────────────────────────────────────────────────────────────────
let BRAND = '', CARDS = [];
function pnlCard(c) { CARDS.push(c); return '<card/>'; }
const renderPageFreshness = () => ({ catch: () => {} });
const getWalmartPnlDateRange = () => ({ from: '2026-01-01', to: '2026-12-31' });
const catVisPass = () => true;
const prodImgCell = () => '<td class="img"></td>';
const pnlCardBtn = () => '';
const colSrc = () => null;
const srcTipLine = () => '';
const fitTableWrapsSoon = () => {};
const updateWalmartPnlChart = () => {};
let walmartPnlSortKey = 'net_sales', walmartPnlSortDir = -1;
let walmartPnlSelectedMids = new Set(), walmartPnlVisibleMids = [];
let walmartPnlExportRows = [], walmartPnlExportCtx = {};

const EL = {
  'wmpnl-scorecards': { innerHTML: '' },
  'wmpnl-thead-row' : { innerHTML: '' },
  'wmpnl-tbody'     : { innerHTML: '' },
  'wmpnl-row-count' : { textContent: '' },
  'wmpnl-select-all': { checked: false, indeterminate: false },
  'wmpnl-cat'       : { value: '' },
  'wmpnl-search'    : { value: '' },
};
global.document = { getElementById: (id) => (id === 'wmpnl-brand' ? { value: BRAND } : (EL[id] || null)) };

function renderWalmartPnl() {
  // v7.13 — data-currency bar.
  if (typeof renderPageFreshness === 'function') renderPageFreshness('wmpnl-freshness', [
    { label: 'Walmart Weekly', table: 'walmart_sales_weekly', icon: '🛒' },
  ]).catch(console.warn);
  const { from, to } = getWalmartPnlDateRange();
  const brand  = document.getElementById('wmpnl-brand')?.value || '';
  const cat    = document.getElementById('wmpnl-cat')?.value || '';
  const search = (document.getElementById('wmpnl-search')?.value || '').toLowerCase();
  const prodById = {}; (allProducts || []).forEach(p => prodById[p.master_id] = p);

  const agg = {};
  for (const r of walmartPnlData) {
    if (from && r.week_start < from) continue;
    if (to && r.week_start > to) continue;
    const p = prodById[r.master_id];
    if (brand && (!p || p.brand !== brand)) continue;
    if (cat && (!p || (allCategories.find(c => c.id === p.category_id)?.category || '') !== cat)) continue;
    if (!catVisPass('pnl_walmart', p)) continue;                // v10.6
    if (search) {
      const blob = ((p?.title || '') + (p?.short_name || '') + (r.master_id || '') + (p?.sp_sku || '') + (r.product_name || '')).toLowerCase();
      if (!blob.includes(search)) continue;
    }
    if (!agg[r.master_id]) agg[r.master_id] = { master_id: r.master_id, units: 0, net_sales: 0, product_name: r.product_name, walmart_item_number: r.walmart_item_number };
    agg[r.master_id].units += r.units;
    agg[r.master_id].net_sales += r.net_sales;
  }

  // v11.32 - the ledger's per-each price, resolved ONCE for the whole render
  // rather than per row: walmartWholesalePerEach re-rolls the ledger on every
  // call, which over a few hundred products would be quadratic.
  const wholesaleBy = (typeof walmartLedgerByMaster === 'function') ? walmartLedgerByMaster().by : {};
  let rows = Object.values(agg).map(a => {
    const p = prodById[a.master_id] || {};
    const cogsPer = walmartPnlCogs(a.master_id);
    const cogsTotal = (cogsPer != null) ? cogsPer * a.units : null;
    const netProceeds = (cogsTotal != null) ? a.net_sales - cogsTotal : null;
    const marginPct = (a.net_sales > 0 && netProceeds != null) ? (netProceeds / a.net_sales) * 100 : null;
    // /!\ WHOLESALE basis. net_sales is RETAIL - what the shopper paid
    // Walmart - and we are 1P, so we never receive it. ourRev is what
    // Walmart pays US for the same units, at the ledger's per-each price.
    // A product the ledger never priced is NULL, never zero: zero would
    // render as selling at no revenue, on the page built to judge margin.
    const wholesalePer = wholesaleBy[a.master_id]?.perEach ?? null;
    const ourRev = (wholesalePer != null) ? wholesalePer * a.units : null;
    const gm = (ourRev != null && cogsTotal != null) ? ourRev - cogsTotal : null;
    const gmPct = (gm != null && ourRev > 0) ? (gm / ourRev) * 100 : null;
    return { ...a, prod: p, brand: p.brand || '—', title: p.short_name || p.title || a.product_name || a.master_id,
             cogsPer, cogsTotal, netProceeds, marginPct, avgPrice: a.units ? a.net_sales / a.units : 0,
             wholesalePer, ourRev, gm, gmPct,
             missingCogs: cogsPer == null && a.units > 0 };
  });

  const sv = (r) => {
    switch (walmartPnlSortKey) {
      case 'title':        return String(r.title || '').toLowerCase();
      case 'units':        return r.units;
      case 'net_sales':    return r.net_sales;
      case 'avg_price':    return r.avgPrice;
      case 'cogs':         return r.cogsTotal || 0;
      case 'net_proceeds': return r.netProceeds || 0;
      case 'margin_pct':   return r.marginPct == null ? -Infinity : r.marginPct;
      case 'our_rev':      return r.ourRev || 0;
      case 'gm':           return r.gm || 0;
      case 'gm_pct':       return r.gmPct == null ? -Infinity : r.gmPct;
      default:             return r.net_sales;
    }
  };
  rows.sort((a, b) => { const va = sv(a), vb = sv(b); if (typeof va === 'string' || typeof vb === 'string') return walmartPnlSortDir * String(va || '').localeCompare(String(vb || '')); return walmartPnlSortDir * ((va || 0) - (vb || 0)); });

  const tot = rows.reduce((t, r) => {
    t.units += r.units; t.net += r.net_sales; t.cogs += (r.cogsTotal || 0);
    if (r.cogsTotal != null) t.netProceeds += r.netProceeds;
    // v11.32 - the wholesale side sums only rows the ledger priced, and
    // records the retail those rows represent so the blend has an honest
    // denominator and the coverage can be STATED (the v11.01 argument).
    if (r.ourRev != null) { t.ourRev += r.ourRev; t.pricedNet += r.net_sales; t.pricedUnits += r.units; }
    if (r.gm != null) t.gm += r.gm;
    return t;
  }, { units: 0, net: 0, cogs: 0, netProceeds: 0, ourRev: 0, gm: 0, pricedNet: 0, pricedUnits: 0 });
  const totMargin = tot.net > 0 ? (tot.netProceeds / tot.net) * 100 : 0;
  const totGmPct  = tot.ourRev > 0 ? (tot.gm / tot.ourRev) * 100 : null;
  const wsCovPct  = tot.units > 0 ? (tot.pricedUnits / tot.units) * 100 : 0;
  const missingCount = rows.filter(r => r.missingCogs).length;

  const $ = (n) => '$' + (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sc = document.getElementById('wmpnl-scorecards');
  // v11.32 - six cards, and the two BASES sit side by side on purpose. Net
  // Sales is RETAIL (what the shopper paid Walmart, which we never see) and
  // Our Rev is WHOLESALE (what Walmart pays us). Showing one without the
  // other is what made this page read 77% when it is nearer 61%.
  if (sc) sc.innerHTML = [
    { l: 'Net Sales', src: 'walmart_sales_weekly', v: $(tot.net), s: `${tot.units.toLocaleString()} units`,
      t: 'RETAIL sell-through on walmart.com: what the shopper paid Walmart. We are 1P, so this is NOT revenue to us - see Our Rev.' },
    { l: 'Our Rev', src: ['walmart_sales_weekly', 'walmart_catalog'], v: $(tot.ourRev),
      s: wsCovPct >= 99.95 ? 'what Walmart pays us' : `priced on ${wsCovPct.toFixed(1)}% of units`,
      t: 'WHOLESALE revenue: these units at the per-each price from the Cost to Walmart ledger. A product the ledger never priced is excluded rather than counted at zero.' },
    { l: 'Total COGS (landed)', src: 'product_cogs', v: $(tot.cogs), s: missingCount ? `⚠ ${missingCount} missing COGS` : 'landed-cost basis' },
    { l: 'Net Proceeds', v: $(tot.netProceeds), s: 'Net Sales − COGS', src: 'ƒ Merch Sales − COGS',
      t: 'RETAIL basis. Kept because it is what this page has always reported; GM $ is the same subtraction on the wholesale side.' },
    { l: 'Contribution %', v: (tot.net > 0 ? totMargin.toFixed(1) + '%' : '—'), s: 'RETAIL basis', src: 'ƒ Net Proceeds ÷ Merch Sales (RETAIL basis)',
      t: 'Net Proceeds over RETAIL sell-through. Reads high because the denominator includes Walmart\u2019s own markup. GM % beside it is the one on our money.' },
    { l: 'GM %', v: (totGmPct == null ? '—' : totGmPct.toFixed(1) + '%'), s: 'before Walmart allowances',
      src: 'ƒ (Our Rev − COGS) ÷ Our Rev (WHOLESALE basis)',
      t: 'Margin on what Walmart actually pays us. ⚠ Walmart allowances are NOT deducted (the agreement has never been loaded) and neither is Walmart Connect ad spend.' },
  ].map(c => pnlCard({ label: c.l, val: c.v, sub: c.s, src: c.src, tip: c.t })).join('');

  const cols = [
    { k: 'title',        label: 'Product',        align: 'left' },
    { k: 'item',         label: 'Walmart Item #', align: 'left', nosort: true },
    { k: 'units',        label: 'Units',          align: 'right' },
    { k: 'net_sales',    label: 'Net Sales',      align: 'right' },
    { k: 'avg_price',    label: 'Avg Price',      align: 'right' },
    { k: 'cogs',         label: 'COGS',           align: 'right' },
    { k: 'net_proceeds', label: 'Net Proceeds',   align: 'right' },
    { k: 'margin_pct',   label: 'Contrib %',      align: 'right',
      t: 'Net Proceeds over RETAIL sell-through. RETAIL basis - not comparable with GM %.' },
    { k: 'our_rev',      label: 'Our Rev',        align: 'right',
      t: 'WHOLESALE revenue: these units at the Cost to Walmart per-each price. What Walmart pays us, as against Net Sales, which is what the shopper paid Walmart.' },
    { k: 'gm',           label: 'GM $',           align: 'right',
      t: 'Our Rev less COGS. WHOLESALE basis, before Walmart allowances and Connect ad spend.' },
    { k: 'gm_pct',       label: 'GM %',           align: 'right',
      t: 'GM $ over Our Rev. WHOLESALE basis - the margin on OUR money, not on Walmart\u2019s shelf price.' },
  ];
  const ind = (k) => walmartPnlSortKey === k ? (walmartPnlSortDir > 0 ? ' ↑' : ' ↓') : ' <span style="opacity:.3">↕</span>';
  const thr = document.getElementById('wmpnl-thead-row');
  if (thr) thr.innerHTML =
    '<th style="text-align:center;padding:6px 6px;width:28px"><input type="checkbox" id="wmpnl-select-all" onclick="walmartPnlToggleSelectAllVisible()" title="Select all visible products" style="cursor:pointer;margin:0;vertical-align:middle"></th>' +
    '<th style="padding:6px 8px"></th>' +
    cols.map(c => `<th title="${((c.t || c.label) + srcTipLine(colSrc('walmart_pnl', c.k))).replace(/"/g, '&quot;')}" onclick="${c.nosort ? '' : `walmartPnlSetSort('${c.k}')`}" style="cursor:help;padding:6px 10px;text-align:${c.align};font-size:10px;color:var(--text3);font-family:var(--mono);${c.nosort ? '' : 'cursor:pointer'};white-space:nowrap">${c.label}${c.nosort ? '' : ind(c.k)}</th>`).join('');

  const cc = (b) => b === 'Meowijuana' ? 'c-meow' : b === 'Doggijuana' ? 'c-doggi' : 'c-kkz';
  const bl = (b) => b === 'Kitty Ka-Zoom' ? 'KKZ' : (b || '').slice(0, 6);
  const tb = document.getElementById('wmpnl-tbody');
  if (tb) {
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="13" style="text-align:center;padding:24px;color:var(--text3);font-family:var(--mono);font-size:11px">No Walmart sales in this period. Widen the period, or import a current report (Data → Uploads → 🛒 Walmart).</td></tr>';
    } else {
      tb.innerHTML = rows.map(r => {
        const marginCol = r.marginPct == null ? 'var(--text3)' : r.marginPct >= 15 ? 'var(--sp-green)' : r.marginPct >= 5 ? 'var(--sp-orange)' : 'var(--red,#d63f2a)';
        // v11.32 - the only threshold that means anything on a wholesale GM
        // is ZERO. Reusing the retail bands above would invent cut-offs.
        const gmCol = r.gm == null ? 'var(--text3)' : (r.gm <= 0 ? 'var(--red,#d63f2a)' : 'var(--text)');
        const isSel = walmartPnlSelectedMids.has(r.master_id);
        return `<tr style="border-bottom:1px solid var(--border);cursor:pointer;transition:background .12s;background:${isSel ? 'rgba(0,113,220,0.10)' : ''}" onclick="walmartPnlToggleProduct('${r.master_id}')">
          <td style="text-align:center;padding:6px 6px;width:28px"><input type="checkbox" ${isSel ? 'checked' : ''} onclick="event.stopPropagation();walmartPnlToggleProduct('${r.master_id}')" style="cursor:pointer;margin:0;vertical-align:middle"></td>
          ${prodImgCell(r.prod, { size: 30 })}
          <td style="padding:6px 10px;text-align:left"><span class="chip ${cc(r.brand)}" style="margin-right:5px">${bl(r.brand)}</span>${String(r.title || '').replace(/</g, '&lt;')} ${pnlCardBtn(r.master_id)}</td>
          <td style="padding:6px 10px;text-align:left;font-family:var(--mono);font-size:10px;color:var(--text3)">${r.walmart_item_number || '—'}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono)">${r.units.toLocaleString()}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono)">${$(r.net_sales)}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono);color:var(--text3)">${$(r.avgPrice)}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono)">${r.cogsTotal == null ? '<span style="color:var(--red,#d63f2a)" title="No landed/DTC COGS set for this product — set it on the COGS page.">⚠ missing</span>' : $(r.cogsTotal)}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono)">${r.netProceeds == null ? '—' : $(r.netProceeds)}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono);color:${marginCol}">${r.marginPct == null ? '—' : r.marginPct.toFixed(1) + '%'}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono)">${r.ourRev == null ? '<span style="color:var(--text3)" title="No per-each price for this product in the Cost to Walmart ledger.">—</span>' : $(r.ourRev)}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono);color:${gmCol}">${r.gm == null ? '—' : $(r.gm)}</td>
          <td style="padding:6px 10px;text-align:right;font-family:var(--mono);color:${gmCol}">${r.gmPct == null ? '—' : r.gmPct.toFixed(1) + '%'}</td>
        </tr>`;
      }).join('');
    }
  }

  // Multi-select bookkeeping (drives the line chart).
  walmartPnlVisibleMids = rows.map(r => r.master_id);
  const hcb = document.getElementById('wmpnl-select-all');
  if (hcb) {
    const sel = walmartPnlVisibleMids.filter(m => walmartPnlSelectedMids.has(m)).length;
    hcb.checked       = walmartPnlVisibleMids.length > 0 && sel === walmartPnlVisibleMids.length;
    hcb.indeterminate = sel > 0 && sel < walmartPnlVisibleMids.length;
  }

  const rc = document.getElementById('wmpnl-row-count');
  if (rc) {
    const selN = walmartPnlSelectedMids.size;
    rc.textContent = `${rows.length} products · ${from} → ${to} · Walmart 1P${missingCount ? ` · ⚠ ${missingCount} missing COGS` : ''}${selN ? ` · ${selN} selected (check rows → chart)` : ' · check rows to chart a weekly trend'}`;
  }

  walmartPnlExportRows = rows;
  walmartPnlExportCtx = { from, to };

  updateWalmartPnlChart();
  fitTableWrapsSoon();   // v10.56
}

function walmartPnlCogs(mid) {
  const c = (typeof cogsByMaster !== 'undefined') ? cogsByMaster[mid] : null;
  if (!c) return null;
  return (c.landed_cost ?? c.dtc_cogs ?? c.amazon_cogs) ?? null;
}

function walmartLedgerByMaster() {
  const by = {};
  let unmapped = 0, feeLines = 0, uploadedAt = null;
  for (const r of (walmartCatalogData || [])) {
    if (r.uploaded_at && (!uploadedAt || r.uploaded_at > uploadedAt)) uploadedAt = r.uploaded_at;
    if (r.is_fee_line) { feeLines++; continue; }
    if (!r.master_id || !r.pack || !(r.qty_cases > 0)) { unmapped++; continue; }
    const a = by[r.master_id] || (by[r.master_id] = { skus: 0, cases: 0, eaches: 0, amount: 0, perEach: null });
    a.skus++; a.cases += Number(r.qty_cases) || 0;
    a.eaches += (Number(r.qty_cases) || 0) * (Number(r.pack) || 0);
    a.amount += Number(r.amount) || 0;
  }
  for (const mid of Object.keys(by)) {
    const a = by[mid];
    a.perEach = a.eaches > 0 ? a.amount / a.eaches : null;
  }
  return { by, unmapped, feeLines, uploadedAt };
}

function run(brand) {
  BRAND = brand; CARDS = [];
  EL['wmpnl-tbody'].innerHTML = '';
  EL['wmpnl-scorecards'].innerHTML = '';
  renderWalmartPnl();
  return {
    heads: (EL['wmpnl-thead-row'].innerHTML.match(/>([^<>]*?)(?: ?[\u2191\u2193]| <span[^>]*>[\u2195])?<\/th>/g) || []).length,
    headText: EL['wmpnl-thead-row'].innerHTML,
    body: EL['wmpnl-tbody'].innerHTML,
    note: EL['wmpnl-row-count'].textContent,
    cards: CARDS.map(c => ({ label: c.label, val: c.val, sub: c.sub, src: c.src, tip: c.tip })),
    rows: walmartPnlExportRows.map(r => ({
      mid: r.master_id, units: r.units, net: r.net_sales,
      cogsTotal: r.cogsTotal, netProceeds: r.netProceeds, marginPct: r.marginPct,
      wholesalePer: r.wholesalePer, ourRev: r.ourRev, gm: r.gm, gmPct: r.gmPct,
    })),
  };
}

const all = run('');
const kkz = run('Kitty Ka-Zoom');

// A3 - the PRE-v11.32 read. The page reported margin over RETAIL sell-through,
// a denominator that includes Walmart's own markup and never reaches us.
const legacy = all.rows.map(r => ({ mid: r.mid, retailPct: r.marginPct }));

console.log(JSON.stringify({ all, kkz, legacy, ledger: walmartLedgerByMaster() }));
