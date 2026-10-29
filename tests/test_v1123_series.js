var localStorage = { getItem: () => null, setItem: () => {} };
function pnlSlotAdd(acc, s) {
  if (!s) return acc;
  for (const k in s) if (typeof s[k] === 'number') acc[k] = (acc[k] || 0) + s[k];
  return acc;
}
function pnlChartBands() {
  let v;
  try { v = parseInt(localStorage.getItem('pnlChartBands'), 10); } catch (e) {}
  if (!PNL_CHART_BAND_STEPS.includes(v)) v = PNL_CHART_TOPN;
  return v === 0 ? Infinity : v;     // 0 = All
}
function pnlBandColor(i, colors) {
  if (i < colors.length) return colors[i];
  const k = i - colors.length;
  const hue = (k * 137.508) % 360;                 // golden angle
  const sat = 55 + (k % 3) * 12;                   // 55 / 67 / 79
  const lit = 45 + (k % 4) * 7;                    // 45 / 52 / 59 / 66
  return `hsl(${hue.toFixed(1)}, ${sat}%, ${lit}%)`;
}
function pnlBandFill(c, aHex) {
  if (!c.startsWith('hsl')) return c + aHex;
  const a = (parseInt(aHex, 16) / 255).toFixed(2);
  return c.replace('hsl(', 'hsla(').replace(')', `, ${a})`);
}
function pnlChartMode() {
  return localStorage.getItem('pnlChartMode') === 'stacked' ? 'stacked' : 'line';
}
function pnlTrendSeries(cfg) {
  const { perProd, buckets, mids, metricOf, labelOf, colors, isPct } = cfg;
  // v11.23 - the band NOUN. Every caller before the Ads views charted
  // PRODUCTS, so 'product' / 'SKUs' stay the defaults and those callers are
  // untouched. An ads chart plots campaigns or search terms, and a legend
  // reading 'Other — 12 SKUs' over a campaign chart is simply wrong.
  const noun = cfg.noun || 'product';
  const otherNoun = cfg.otherNoun || 'SKUs';
  // ⚠ NOT EVERY UNSUMMABLE METRIC IS A PERCENTAGE. ROAS, CPC and CPA are
  // RATIOS: stacking 2.0x on 3.0x to read 5.0x is meaningless in exactly the
  // way stacking percentages is, and none of them is a percentage. isPct
  // stays the default, so no existing caller changes behaviour.
  const noStack = cfg.noStack != null ? !!cfg.noStack : !!isPct;
  const selectionActive = !!cfg.selectionActive;
  const topN = cfg.topN || pnlChartBands();   // v10.67 - one shared setting
  let mode = cfg.mode || 'line';
  let note = '';

  if (noStack && mode === 'stacked') {
    mode = 'line';
    // The note names the REASON, which differs: a percentage and a ratio are
    // both unsummable for their own reason, and 'percentages do not sum' over
    // a ROAS chart would read as a bug in the label.
    note = isPct
      ? 'stacking is off for a percentage metric \u2014 percentages do not sum'
      : 'stacking is off for a derived ratio \u2014 ratios do not sum';
  }

  const sumAcross = (midList) => buckets.map(b => {
    const acc = {};
    let any = false;
    for (const mid of midList) {
      const slot = perProd[mid] && perProd[mid][b];
      if (slot) { pnlSlotAdd(acc, slot); any = true; }
    }
    return any ? metricOf(acc) : null;
  });

  // Default state: no selection, line mode -> ONE total line. This is the
  // state Jason lands on, so it has to answer "how are sales trending" with
  // no clicks.
  if (!selectionActive && mode === 'line') {
    return {
      mode, note,
      datasets: [{
        label: `Total \u00b7 ${mids.length} ${noun}${mids.length === 1 ? '' : 's'}`,
        data: sumAcross(mids),
        borderColor: colors[0], backgroundColor: colors[0] + '22',
        borderWidth: 2, pointRadius: buckets.length > 52 ? 0 : 3,
        tension: 0.3, fill: false, spanGaps: true,
      }],
      bandCount: 1,
    };
  }

  // Which products get their own band. With a selection it is exactly those;
  // without one it would be every visible SKU, so the tail is rolled into a
  // single "Other" band rather than drawing 300 unreadable slivers.
  let banded = mids.slice();
  let otherMids = [];
  if (!selectionActive && banded.length > topN) {
    const total = mid => buckets.reduce((a, b) => {
      const sl = perProd[mid] && perProd[mid][b];
      const v = sl ? metricOf(sl) : null;
      return a + (typeof v === 'number' && isFinite(v) ? v : 0);
    }, 0);
    banded = mids.slice().sort((a, b) => total(b) - total(a));
    otherMids = banded.slice(topN);
    banded = banded.slice(0, topN);
  } else if (mode === 'stacked') {
    const total = mid => buckets.reduce((a, b) => {
      const sl = perProd[mid] && perProd[mid][b];
      const v = sl ? metricOf(sl) : null;
      return a + (typeof v === 'number' && isFinite(v) ? v : 0);
    }, 0);
    banded = banded.sort((a, b) => total(b) - total(a));   // biggest at the base
  }

  const datasets = banded.map((mid, i) => {
    const color = pnlBandColor(i, colors);   // v10.67 - distinct past the palette
    return {
      label: labelOf(mid),
      data: buckets.map(b => {
        const slot = perProd[mid] && perProd[mid][b];
        // A stacked band needs 0, not a gap: a null breaks the fill chain and
        // the bands above it detach from the one below.
        if (!slot) return mode === 'stacked' ? 0 : null;
        const v = metricOf(slot);
        return (mode === 'stacked' && v == null) ? 0 : v;
      }),
      borderColor: color,
      // Stacked bands are near-opaque so they read as distinct layers rather
      // than a translucent haze (the v9.99 / v4.135 lesson).
      backgroundColor: mode === 'stacked' ? pnlBandFill(color, 'd9') : pnlBandFill(color, '22'),
      borderWidth: mode === 'stacked' ? 1 : 2,
      pointRadius: mode === 'stacked' ? 0 : (buckets.length > 52 ? 0 : 3),
      tension: 0.3,
      fill: mode === 'stacked' ? (i === 0 ? 'origin' : '-1') : false,
      spanGaps: true,
    };
  });

  if (otherMids.length) {
    const color = '#6b7280';
    datasets.push({
      label: `Other \u00b7 ${otherMids.length} ${otherNoun}`,
      data: sumAcross(otherMids).map(v => (mode === 'stacked' && v == null) ? 0 : v),
      borderColor: color, backgroundColor: mode === 'stacked' ? color + 'd9' : color + '22',
      borderWidth: 1, pointRadius: 0, tension: 0.3,
      fill: mode === 'stacked' ? '-1' : false, spanGaps: true,
    });
  }

  return { mode, note, datasets, bandCount: datasets.length };
}
function pnlTrendSubtitle({ selectionActive, midCount, bandCount, buckets, from, to, mode, note, bucketNoun, extra, noun }) {
  // v11.23 - same noun as the series builder, same default.
  const _n = noun || 'product';
  const scope = selectionActive
    ? `${midCount} ${_n}${midCount === 1 ? '' : 's'} selected`
    : `all ${midCount} ${_n}${midCount === 1 ? '' : 's'} \u00b7 total`;
  const shape = mode === 'stacked' ? `stacked \u00b7 ${bandCount} band${bandCount === 1 ? '' : 's'}` : 'line';
  return [scope, shape, `${buckets} ${bucketNoun}${buckets === 1 ? '' : 's'}`, `${from} \u2192 ${to}`, extra, note]
    .filter(Boolean).join(' \u00b7 ');
}
const PNL_CHART_TOPN = 8;
const PNL_CHART_BAND_STEPS = [8, 25, 50, 0];

const perProd = { A: { w1: { v: 10 }, w2: { v: 20 } }, B: { w1: { v: 5 }, w2: { v: 7 } } };
const many = {}; const manyMids = [];
for (let i = 0; i < 12; i++) { const m = 'P' + i; manyMids.push(m); many[m] = { w1: { v: 12 - i } }; }
const C = ['#111','#222','#333','#444','#555','#666','#777','#888','#999','#aaa'];
const o = {};
const base = { perProd, buckets: ['w1','w2'], mids: ['A','B'], metricOf: s => s.v,
               labelOf: m => m, colors: C };
o.defaultTotal = pnlTrendSeries(Object.assign({}, base, { mode:'line', selectionActive:false })).datasets[0].label;
o.nounTotal    = pnlTrendSeries(Object.assign({}, base, { mode:'line', selectionActive:false, noun:'campaign' })).datasets[0].label;
const defOther = pnlTrendSeries({ perProd: many, buckets:['w1'], mids: manyMids, metricOf: s=>s.v,
  labelOf: m=>m, colors: C, mode:'stacked', selectionActive:false });
o.defaultOther = defOther.datasets[defOther.datasets.length-1].label;
const adsOther = pnlTrendSeries({ perProd: many, buckets:['w1'], mids: manyMids, metricOf: s=>s.v,
  labelOf: m=>m, colors: C, mode:'stacked', selectionActive:false,
  noun:'campaign', otherNoun:'campaigns' });
o.adsOther = adsOther.datasets[adsOther.datasets.length-1].label;
const pct = pnlTrendSeries(Object.assign({}, base, { mode:'stacked', selectionActive:false, isPct:true }));
o.pctMode = pct.mode; o.pctNote = pct.note;
const ratio = pnlTrendSeries(Object.assign({}, base, { mode:'stacked', selectionActive:false, noStack:true }));
o.ratioMode = ratio.mode; o.ratioNote = ratio.note;
const stack = pnlTrendSeries(Object.assign({}, base, { mode:'stacked', selectionActive:true }));
o.stackMode = stack.mode;
o.subDefault = pnlTrendSubtitle({ selectionActive:false, midCount:3, bandCount:1, buckets:4,
  from:'a', to:'b', mode:'line', bucketNoun:'week' });
o.subNoun = pnlTrendSubtitle({ selectionActive:true, midCount:3, bandCount:1, buckets:4,
  from:'a', to:'b', mode:'line', bucketNoun:'week', noun:'search term' });
console.log(JSON.stringify(o));
