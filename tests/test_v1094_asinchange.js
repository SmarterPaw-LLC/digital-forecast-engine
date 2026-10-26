
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// -- stubs ---------------------------------------------------------------
let pnlGrowthState = { asin: null, masterId: null, lastResult: null };
let RENDER_CALLS = [];
const CATALOG = new Map([
  ['B07OLD', { asin: 'B07OLD', master_id: 'SP-0001' }],
  ['B07KPRTSMT', { asin: 'B07KPRTSMT', master_id: 'SP-0002' }],
]);
function pnlGrowthEligibleAsins() { return CATALOG; }

// What the panel WOULD paint, given the state at render time. Stands in for
// the months-loaded / confidence / Brand-view readouts, which all key off
// pnlGrowthState.asin.
function pnlGrowthRender() { RENDER_CALLS.push(pnlGrowthState.asin); }

let resultDiv = { innerHTML: 'stale result' };
const document = { getElementById: () => resultDiv };

// -- the PRE-v10.94 handler, reproduced verbatim -------------------------
function pnlGrowthOnAsinChange_OLD(asin) {
  const catalog = pnlGrowthEligibleAsins();
  const p = catalog.get(asin);
  if (!p) return;
  pnlGrowthState.asin = asin;
  pnlGrowthState.masterId = p.master_id;
  pnlGrowthState.lastResult = null;
  document.getElementById('pnl-growth-result').innerHTML = '';
}

function pnlGrowthOnAsinChange(asin) {
  const catalog = pnlGrowthEligibleAsins();
  const p = catalog.get(asin);
  if (!p) return;
  pnlGrowthState.asin = asin;
  pnlGrowthState.masterId = p.master_id;
  pnlGrowthState.lastResult = null;
  // ⚠ v10.94 - RE-RENDER. Without this the <select> showed the new product
  // while every readout beneath it still described the PREVIOUS one: months
  // loaded, the Brand-view warning, the confidence badge, the uplift
  // "This ASIN:" hints, the recommendation bar. The model then ran on the
  // real selection and correctly reported no data, against a panel quietly
  // claiming a month was loaded - two numbers on one screen that could not
  // both be true. pnlGrowthRender() also rebuilds an empty result div, so the
  // manual clear this replaced is covered.
  pnlGrowthRender();
}

function reset(startAsin) {
  pnlGrowthState = { asin: startAsin, masterId: 'SP-0001', lastResult: { asin: startAsin } };
  RENDER_CALLS = [];
  resultDiv = { innerHTML: 'stale result' };
}

// -- 1. The bug, reproduced ---------------------------------------------
reset('B07OLD');
pnlGrowthOnAsinChange_OLD('B07KPRTSMT');
t('B1  OLD: state moved to the new product', pnlGrowthState.asin, 'B07KPRTSMT');
t('B2  OLD: but the panel was NEVER re-rendered - that is the bug',
  RENDER_CALLS.length, 0);

// -- 2. The fix ---------------------------------------------------------
reset('B07OLD');
pnlGrowthOnAsinChange('B07KPRTSMT');
t('B3  NEW: the panel is re-rendered exactly once', RENDER_CALLS.length, 1);
t('B4  NEW: ...and it renders the NEW product, not the old one',
  RENDER_CALLS[0], 'B07KPRTSMT');
t('B5  NEW: masterId follows too', pnlGrowthState.masterId, 'SP-0002');
t('B6  NEW: the previous result is dropped before the render',
  pnlGrowthState.lastResult, null);

// -- 3. An unknown ASIN must not render or mutate anything --------------
reset('B07OLD');
pnlGrowthOnAsinChange('B07NOPE');
t('B7  an unknown ASIN leaves the state alone', pnlGrowthState.asin, 'B07OLD');
t('B8  ...and does not re-render', RENDER_CALLS.length, 0);

// -- 4. Re-selecting the SAME product still repaints --------------------
// Cheap, and it is the natural way to recover a panel after an upload.
reset('B07KPRTSMT');
pnlGrowthOnAsinChange('B07KPRTSMT');
t('B9  re-picking the same product repaints', RENDER_CALLS, ['B07KPRTSMT']);

console.log(JSON.stringify(out));
