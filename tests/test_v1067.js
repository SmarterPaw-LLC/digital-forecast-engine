
const _ls = {};
const localStorage = {
  getItem: k => (k in _ls ? _ls[k] : null),
  setItem: (k, v) => { _ls[k] = String(v); },
};
const window = {};
const PNL_CHART_TOPN = 8;
const PNL_CHART_BAND_STEPS = [8, 25, 50, 0];
function pnlChartBands() {
  let v;
  try { v = parseInt(localStorage.getItem('pnlChartBands'), 10); } catch (e) {}
  if (!PNL_CHART_BAND_STEPS.includes(v)) v = PNL_CHART_TOPN;
  return v === 0 ? Infinity : v;     // 0 = All
}
function pnlSetChartBands(nRaw, rerenderName) {
  const v = PNL_CHART_BAND_STEPS.includes(nRaw) ? nRaw : PNL_CHART_TOPN;
  try { localStorage.setItem('pnlChartBands', String(v)); } catch (e) {}
  const fn = window[rerenderName];
  if (typeof fn === 'function') fn();
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
function pnlSlotAdd(acc, s) {
  if (!s) return acc;
  for (const k in s) if (typeof s[k] === 'number') acc[k] = (acc[k] || 0) + s[k];
  return acc;
}
function pnlTrendSeries(cfg) {
  const { perProd, buckets, mids, metricOf, labelOf, colors, isPct } = cfg;
  const selectionActive = !!cfg.selectionActive;
  const topN = cfg.topN || pnlChartBands();   // v10.67 - one shared setting
  let mode = cfg.mode || 'line';
  let note = '';

  if (isPct && mode === 'stacked') {
    mode = 'line';
    note = 'stacking is off for a percentage metric \u2014 percentages do not sum';
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
        label: `Total \u00b7 ${mids.length} product${mids.length === 1 ? '' : 's'}`,
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
      label: `Other \u00b7 ${otherMids.length} SKUs`,
      data: sumAcross(otherMids).map(v => (mode === 'stacked' && v == null) ? 0 : v),
      borderColor: color, backgroundColor: mode === 'stacked' ? color + 'd9' : color + '22',
      borderWidth: 1, pointRadius: 0, tension: 0.3,
      fill: mode === 'stacked' ? '-1' : false, spanGaps: true,
    });
  }

  return { mode, note, datasets, bandCount: datasets.length };
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}

// ---- the setting ---------------------------------------------------------
t('defaults to 8', pnlChartBands() === 8, pnlChartBands());
_ls.pnlChartBands = '25'; t('honours 25', pnlChartBands() === 25);
_ls.pnlChartBands = '0';  t('0 means All (Infinity)', pnlChartBands() === Infinity);
_ls.pnlChartBands = '7';  t('a value not in the step list falls back to 8', pnlChartBands() === 8);
_ls.pnlChartBands = 'abc';t('junk falls back to 8', pnlChartBands() === 8);
delete _ls.pnlChartBands;

// ---- colours -------------------------------------------------------------
const P = ['#a','#b','#c'];
t('palette is used first', pnlBandColor(0,P)==='#a' && pnlBandColor(2,P)==='#c');
const past = [3,4,5,6,7,8,9,10].map(i => pnlBandColor(i,P));
t('past the palette it does NOT repeat', new Set(past).size === past.length, past);
t('past the palette it is hsl()', past.every(c => c.startsWith('hsl(')));
t('hex fill appends alpha', pnlBandFill('#a1b2c3','d9') === '#a1b2c3d9');
t('hsl fill becomes hsla()', /^hsla\(.*, 0\.\d+\)$/.test(pnlBandFill(past[0],'d9')), pnlBandFill(past[0],'d9'));
t('hsl fill never gets a hex alpha glued on', !/\)[0-9a-f]{2}$/i.test(pnlBandFill(past[0],'d9')));

// ---- the stepper applied to the real series builder ----------------------
const COLORS = ['#1','#2','#3','#4','#5','#6','#7','#8','#9','#10'];
const W = ['2026-01-05','2026-01-12','2026-01-19'];
const mids = [], perProd = {};
for (let i = 0; i < 30; i++) {
  const m = 'SP-' + String(i).padStart(2,'0');
  mids.push(m); perProd[m] = {};
  // descending size so the ranking is deterministic
  W.forEach((w, wi) => { perProd[m][w] = { units: (30 - i) * 10 + wi }; });
}
const metricOf = s => s.units;
const labelOf  = m => m;
const build = () => pnlTrendSeries({ perProd, buckets: W, mids, metricOf, labelOf,
                                     colors: COLORS, mode: 'stacked', selectionActive: false });

const grand = W.map(w => mids.reduce((a,m) => a + perProd[m][w].units, 0));
const stackSum = ds => W.map((_, i) => ds.reduce((a,d) => a + (Number(d.data[i]) || 0), 0));

_ls.pnlChartBands = '8';
const B8 = build();
t('bands=8 -> 8 product bands + Other', B8.datasets.length === 9, B8.datasets.length);
t('  the last band is Other', /^Other/.test(B8.datasets[8].label), B8.datasets[8].label);
t('  Other names the remaining count', B8.datasets[8].label.includes('22'), B8.datasets[8].label);

_ls.pnlChartBands = '25';
const B25 = build();
t('bands=25 -> 25 bands + Other', B25.datasets.length === 26, B25.datasets.length);
t('  Other shrank to 5 SKUs', B25.datasets[25].label.includes('5'), B25.datasets[25].label);

_ls.pnlChartBands = '0';
const BALL = build();
t('bands=All -> one band per product, no Other', BALL.datasets.length === 30, BALL.datasets.length);
t('  and no Other band at all', !BALL.datasets.some(d => /^Other/.test(d.label)));

// ---- THE INVARIANT: bands must still sum to the grand total --------------
[['8',B8],['25',B25],['All',BALL]].forEach(([n, B]) => {
  const got = stackSum(B.datasets);
  t('bands=' + n + ' -> stack still sums to the grand total at every bucket',
    got.every((v, i) => Math.abs(v - grand[i]) < 1e-6), { got, grand });
});

// ---- a selection ignores the band count (it IS the band list) ------------
_ls.pnlChartBands = '8';
const SEL = pnlTrendSeries({ perProd, buckets: W, mids: mids.slice(0,12), metricOf, labelOf,
                             colors: COLORS, mode: 'stacked', selectionActive: true });
t('an explicit selection is never truncated by the band count',
  SEL.datasets.length === 12 && !SEL.datasets.some(d => /^Other/.test(d.label)), SEL.datasets.length);

// ---- every band has a usable colour even at All --------------------------
t('every band at All has a usable colour',
  BALL.datasets.every(d => typeof d.borderColor === 'string' && d.borderColor.length
                        && !String(d.backgroundColor).includes('undefined')));
t('band colours at All are distinct',
  new Set(BALL.datasets.map(d => d.borderColor)).size === BALL.datasets.length);

// ---- stacked fill chain survives a bigger band count (v4.135) ------------
t('fill chain is origin then -1 all the way down at All',
  BALL.datasets[0].fill === 'origin' && BALL.datasets.slice(1).every(d => d.fill === '-1'));

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
