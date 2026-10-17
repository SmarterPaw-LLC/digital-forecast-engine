
let cogsByMaster = {};
const CHEWY_COGS_SOURCES = {
  chewy_cogs:  { label: 'product_cogs.chewy_cogs',  note: 'True Chewy cost (landed + Chewy fulfilment + labour).', warn: false },
  landed_cost: { label: 'product_cogs.landed_cost', note: 'Landed cost only, no fulfilment in it, so this slightly UNDERSTATES cost.', warn: false },
  dtc_cogs:    { label: 'product_cogs.dtc_cogs',    note: 'WRONG BASIS - carries DTC shipping, pick/pack and overhead that a 1P pallet never incurs. Overstates Chewy cost and inflates BE ROAS.', warn: true },
  amazon_cogs: { label: 'product_cogs.amazon_cogs', note: 'WRONG BASIS - carries the FBA fulfilment fee, which does not apply to Chewy 1P. Overstates Chewy cost and inflates BE ROAS.', warn: true },
};
function chewyPnlCogsSource(mid) {
  const c = (typeof cogsByMaster !== 'undefined' && cogsByMaster) ? cogsByMaster[mid] : null;
  if (!c) return { value: null, field: null, label: 'no product_cogs row', note: 'No COGS on file for this product, so no margin can be computed.', warn: true };
  for (const f of ['chewy_cogs', 'landed_cost', 'dtc_cogs', 'amazon_cogs']) {
    if (c[f] != null) return Object.assign({ value: c[f], field: f }, CHEWY_COGS_SOURCES[f]);
  }
  return { value: null, field: null, label: 'no COGS set', note: 'Every COGS field is empty for this product.', warn: true };
}
function chewyAllowanceStack() { return { standingPct: 26.5, byCat: { coop_marketing: 16, damages: 2, freight: 1.5, autoship: 5, satisfaction_guarantee: 2 }, source: 'invoices' }; }
let chewyBeAuditRows = [];

// --- minimal DOM so the viewer can mount
const _nodes = {};
function _mk(tag) {
  return {
    tagName: tag, id: '', style: { cssText: '', display: '' },
    innerHTML: '', children: [],
    addEventListener() {}, appendChild(c) { this.children.push(c); },
  };
}
const document = {
  getElementById: id => _nodes[id] || null,
  createElement: tag => _mk(tag),
  body: { appendChild(el) { if (el.id) _nodes[el.id] = el; } },
};
function openChewyBeAudit(sku) {
  const r = (chewyBeAuditRows || []).find(x => String(x.chewy_sku) === String(sku));
  if (!r) { alert('No break-even row loaded for Chewy SKU ' + sku + '. Re-run the tab and try again.'); return; }
  const stack = (typeof chewyAllowanceStack === 'function') ? chewyAllowanceStack() : { standingPct: 0, byCat: {}, source: 'none' };
  const m = (v, d) => (v == null || !isFinite(v)) ? '<span style=\"color:var(--text3)\">n/a</span>' : '$' + Number(v).toFixed(d == null ? 2 : d);
  const p = (v) => (v == null || !isFinite(v)) ? '<span style=\"color:var(--text3)\">n/a</span>' : Number(v).toFixed(1) + '%';
  const esc = (t) => String(t == null ? '' : t).replace(/</g, '&lt;');
  const aPct = (r.wholesale > 0 && r.net != null) ? (1 - r.net / r.wholesale) * 100 : stack.standingPct;

  const row = (what, val, src, warn) =>
    `<tr style=\"border-bottom:1px solid var(--border)\">`
    + `<td style=\"padding:6px 10px;font-family:var(--mono);font-size:11px;color:var(--text2);white-space:nowrap\">${what}</td>`
    + `<td style=\"padding:6px 10px;text-align:right;font-family:var(--mono);font-size:11px;white-space:nowrap\">${val}</td>`
    + `<td style=\"padding:6px 10px;font-family:var(--mono);font-size:10px;color:${warn ? 'var(--sp-orange)' : 'var(--text3)'}\">${src}</td></tr>`;

  const catLines = Object.keys(stack.byCat || {})
    .filter(k => Number(stack.byCat[k]) > 0)
    .map(k => `${k} ${Number(stack.byCat[k]).toFixed(2)}%`).join(' + ') || 'no rate-bearing rebate lines';

  const wholeSrc = r.uom && String(r.uom).toUpperCase().startsWith('CS')
    ? `chewy_catalog.cost ${r.rawCost == null ? '?' : '$' + Number(r.rawCost).toFixed(2)} per CS / products.case_qty ${r.caseQty || '(MISSING)'}`
    : `chewy_catalog.cost, quoted per EACH`;

  const html =
    `<div style=\"padding:16px 18px;border-bottom:1px solid var(--border2);display:flex;align-items:center;gap:12px\">`
    + `<div style=\"flex:1;min-width:0\">`
    + `<div style=\"font-family:var(--display);font-weight:800;font-size:15px;color:var(--text)\">${esc(r.title)}</div>`
    + `<div style=\"font-family:var(--mono);font-size:10px;color:var(--text3);margin-top:3px\">Chewy SKU ${esc(r.chewy_sku)}`
    + `${r.master_id ? ' - ' + esc(r.master_id) : ''} - where every number on this row comes from</div></div>`
    + `<button onclick=\"closeChewyBeAudit()\" style=\"background:var(--surface2);color:var(--text2);border:1px solid var(--border2);border-radius:5px;padding:5px 11px;font-size:11px;font-family:var(--display);font-weight:700;cursor:pointer\">Close</button></div>`

    + `<div style=\"padding:14px 18px;overflow:auto;max-height:62vh\">`
    + `<div style=\"font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px\">Inputs</div>`
    + `<table style=\"width:100%;border-collapse:collapse;margin-bottom:18px\">`
    + row('Wholesale / each', m(r.wholesale, 4), wholeSrc, !r.wholesale)
    + row('Standing allowances', p(aPct), `chewy_rebates: ${esc(catLines)}${stack.source === 'edited' ? ' (edited on Pricing Scenarios)' : ''}`, (stack.standingPct || 0) <= 0)
    + row('= Net to us', m(r.net, 4), 'wholesale x (1 - allowances)')
    + row('COGS / unit', m(r.cogs, 4), r.cogsSrc ? esc(r.cogsSrc.label) : 'product_cogs', !!(r.cogsSrc && r.cogsSrc.warn))
    + row('= GM $/u (contribution)', m(r.contribution, 4), 'net to us - COGS')
    + row('Chewy list price', m(r.listPrice), 'chewy_ad_spend, impression-weighted (falls back to catalog MSRP)')
    + row('Ad spend', m(r.spend), 'chewy_ad_spend')
    + row('Ad units (direct)', String(r.direct_units || 0), 'chewy_ad_spend')
    + row('Direct sales (retail)', m(r.direct_sales), 'chewy_ad_spend')
    + row('Recurring autoship', m(r.autoship_recurring), 'chewy_ad_spend, first orders excluded (v10.52)')
    + `</table>`

    + (r.cogsSrc && r.cogsSrc.warn
        ? `<div style=\"background:rgba(232,96,26,.12);border:1px solid var(--sp-orange);border-radius:7px;padding:9px 12px;margin-bottom:16px;font-family:var(--mono);font-size:11px;color:var(--text2)\">`
          + `COGS basis: ${esc(r.cogsSrc.note)}</div>`
        : '')

    + `<div style=\"font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px\">The math</div>`
    + `<pre style=\"background:var(--surface2);border:1px solid var(--border2);border-radius:7px;padding:11px 13px;font-family:var(--mono);font-size:11px;color:var(--text2);white-space:pre-wrap;margin:0 0 16px\">`
    + `wholesale/each        ${(r.wholesale == null ? 'n/a' : '$' + Number(r.wholesale).toFixed(4))}\n`
    + `  x (1 - ${(aPct == null ? '?' : Number(aPct).toFixed(1))}% allowances)\n`
    + `= net to us           ${(r.net == null ? 'n/a' : '$' + Number(r.net).toFixed(4))}\n`
    + `  - COGS              ${(r.cogs == null ? 'n/a' : '$' + Number(r.cogs).toFixed(4))}\n`
    + `= GM $/u              ${(r.contribution == null ? 'n/a' : '$' + Number(r.contribution).toFixed(4))}\n\n`
    + `BE ROAS = list ${(r.listPrice == null ? 'n/a' : '$' + Number(r.listPrice).toFixed(2))} / GM $/u = ${(r.beRoas == null ? 'n/a' : Number(r.beRoas).toFixed(1) + '%')}\n`
    + `Realised = (direct + recurring autoship) / spend = ${(r.realisedRoas == null ? 'n/a' : Number(r.realisedRoas).toFixed(1) + '%')}\n`
    + `Headroom = realised - break-even = ${(r.headroom == null ? 'n/a' : (r.headroom >= 0 ? '+' : '') + Math.round(r.headroom) + ' pts')}`
    + `</pre>`

    + `<div style=\"font-family:var(--mono);font-size:10px;color:var(--text3);line-height:1.6\">`
    + `BE ROAS reads higher than the Amazon equivalent by design: the numerator is CHEWY'S RETAIL dollar, `
    + `but we only keep the wholesale slice of it, less allowances and COGS. Both sides are per unit, so the `
    + `unit count cancels and this stays directly comparable to Realised ROAS.</div></div>`;

  let ov = document.getElementById('chewyBeAuditOverlay');
  if (!ov) {
    ov = document.createElement('div');
    ov.id = 'chewyBeAuditOverlay';
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10800;display:flex;align-items:center;justify-content:center;padding:24px';
    // v4.168 drag guard: only close when press AND release both land on the backdrop.
    let downOnBackdrop = false;
    ov.addEventListener('mousedown', e => { downOnBackdrop = (e.target === ov); });
    ov.addEventListener('mouseup',   e => { if (downOnBackdrop && e.target === ov) closeChewyBeAudit(); downOnBackdrop = false; });
    document.body.appendChild(ov);
  }
  ov.innerHTML = `<div style=\"background:var(--surface);border:1px solid var(--border2);border-radius:11px;width:min(760px,96vw);max-height:88vh;overflow:hidden;display:flex;flex-direction:column\" onmousedown=\"event.stopPropagation()\">${html}</div>`;
  ov.style.display = 'flex';
}
function closeChewyBeAudit() {
  const ov = document.getElementById('chewyBeAuditOverlay');
  if (ov) { ov.style.display = 'none'; ov.innerHTML = ''; }
}

const out = { src: {}, viewer: {} };

// 1. the fallback chain, every position
const chains = {
  chewy:   { chewy_cogs: 1.11, landed_cost: 2, dtc_cogs: 3, amazon_cogs: 4 },
  landed:  { chewy_cogs: null, landed_cost: 2.22, dtc_cogs: 3, amazon_cogs: 4 },
  dtc:     { chewy_cogs: null, landed_cost: null, dtc_cogs: 3.33, amazon_cogs: 4 },
  amazon:  { chewy_cogs: null, landed_cost: null, dtc_cogs: null, amazon_cogs: 4.44 },
  allnull: { chewy_cogs: null, landed_cost: null, dtc_cogs: null, amazon_cogs: null },
  zero:    { chewy_cogs: 0,    landed_cost: 2,    dtc_cogs: 3,    amazon_cogs: 4 },
};
for (const [k, v] of Object.entries(chains)) {
  cogsByMaster = { 'SP-1': v };
  const r = chewyPnlCogsSource('SP-1');
  out.src[k] = { field: r.field, value: r.value, warn: r.warn, label: r.label };
}
cogsByMaster = {};
out.src.norow = (() => { const r = chewyPnlCogsSource('SP-NOPE');
  return { field: r.field, warn: r.warn, label: r.label }; })();

// 2. the viewer, driven on a hand-checkable row
//    wholesale 4.00, 25% allowances -> net 3.00, cogs 1.00 -> contribution 2.00
//    list 8.99 -> BE ROAS = 8.99/2.00 = 449.5%
const row = {
  master_id: 'SP-1', chewy_sku: '1365718', title: 'Test Product',
  wholesale: 4.0, uom: 'CS', caseQty: 12, rawCost: 48.0,
  cogs: 1.0, net: 3.0, contribution: 2.0,
  listPrice: 8.99, beRoas: 449.5, beAcos: 22.2, gmPct: 50.0,
  spend: 100.0, direct_units: 40, direct_sales: 359.6,
  autoship_recurring: 90.0, directRoas: 359.6, realisedRoas: 449.6,
  headroom: 0.1, cpu: 2.5,
  cogsSrc: { value: 1.0, field: 'dtc_cogs', label: 'product_cogs.dtc_cogs',
             note: 'WRONG BASIS - carries DTC shipping.', warn: true },
};
chewyBeAuditRows = [row];
openChewyBeAudit('1365718');
const ov = _nodes['chewyBeAuditOverlay'];
out.viewer.mounted = !!ov;
out.viewer.html = ov ? ov.innerHTML : '';
out.viewer.display = ov ? ov.style.display : '';

// a SKU that is not loaded must not throw
let alerted = false;
const alert = () => { alerted = true; };
try { openChewyBeAudit('NOPE'); out.viewer.missingThrew = false; }
catch (e) { out.viewer.missingThrew = true; }

closeChewyBeAudit();
out.viewer.closedDisplay = _nodes['chewyBeAuditOverlay'].style.display;
out.viewer.closedHtml = _nodes['chewyBeAuditOverlay'].innerHTML;

console.log(JSON.stringify(out));
