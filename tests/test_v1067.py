# -*- coding: utf-8 -*-
"""v10.67 - expandable "Other" band (BANDS stepper) on every stacked chart.

Jason: "on the stacked area charts, i'd like to be able to see the 'other'
chunk - a toggle to see what it is made up of - on all channels."

The thing most worth guarding is NOT the stepper itself, it is that stepping
the band count must not break the v10.12 invariant: the stacked bands still sum
to the true grand total at every bucket. If that drifts, the chart lies while
looking fine.
"""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond: passed += 1; print('  ok  ' + name)
    else:    failed += 1; print('  FAIL  ' + name)

def fn(name):
    i = js.index('function %s(' % name)
    j = js.index('{', i); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1

print('\n== A. ONE rule, one place (hard rule #1) ==')

ok(js.count('const PNL_CHART_BAND_STEPS') == 1, 'the band-step list is declared exactly once')
ok('const SALES_CHART_TOPN = pnlChartBands();' in js,
   'Units Sold reads the SHARED setting (was a second hardcoded 8)')
ok(not re.search(r'const SALES_CHART_TOPN = \d', js),
   '  and no hardcoded Units Sold top-N survives')
ok('const topN = cfg.topN || pnlChartBands();' in js,
   'pnlTrendSeries reads the same shared setting')

# both charts must render the SAME control, not two lookalikes
ok(js.count('function pnlBandsStepperHtml') == 1, 'one stepper renderer')
ok(js.count("pnlBandsStepperHtml('updateSalesChart')") == 1,
   '  reused by Units Sold')
inj = fn('pnlInjectChartModeToggle')
ok("mode === 'stacked' ? pnlBandsStepperHtml(rerenderName)" in inj,
   '  and injected into all four P&L charts via the shared toggle')
ok("mode === 'stacked' ?" in inj,
   'the stepper is hidden in line mode (where a band count does nothing)')
ok('id="sales-chart-bands-host"' in s, 'Units Sold has a host for it')

print('\n== B. BEHAVIOUR (real sliced functions driven in node) ==')

steps = re.search(r'\n(const PNL_CHART_BAND_STEPS = \[[^\]]*\];)', js).group(1)
topn  = re.search(r'\n(const PNL_CHART_TOPN = \d+;)', js).group(1)

HARNESS = r"""
const _ls = {};
const localStorage = {
  getItem: k => (k in _ls ? _ls[k] : null),
  setItem: (k, v) => { _ls[k] = String(v); },
};
const window = {};
__TOPN__
__STEPS__
__BANDS__
__SETB__
__COLOR__
__FILL__
__SLOTADD__
__SERIES__

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
"""

harness = (HARNESS
  .replace('__TOPN__', topn).replace('__STEPS__', steps)
  .replace('__BANDS__', fn('pnlChartBands')).replace('__SETB__', fn('pnlSetChartBands'))
  .replace('__COLOR__', fn('pnlBandColor')).replace('__FILL__', fn('pnlBandFill'))
  .replace('__SLOTADD__', fn('pnlSlotAdd')).replace('__SERIES__', fn('pnlTrendSeries')))

p = os.path.join(SP, 'test_v1067.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(harness)
rc = subprocess.call(['node', p])

print('\n' + '=' * 60)
print('static: %d passed, %d failed' % (passed, failed))
sys.exit(1 if (failed or rc) else 0)
