
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

let _store = {};
const localStorage = {
  getItem: k => (k in _store ? _store[k] : null),
  setItem: (k, v) => { _store[k] = String(v); },
};
const hosts = {};
const document = { getElementById: id => hosts[id] || null };

function pnlChartMode() {
  return localStorage.getItem('pnlChartMode') === 'stacked' ? 'stacked' : 'line';
}

// Marker stub so the test can assert the BANDS stepper's presence/absence.
function pnlBandsStepperHtml(rerenderName) { return '<!--BANDS-->'; }

function pnlChartCompare() {
  try { return localStorage.getItem('pnlChartCompare') === '1'; } catch (_) { return false; }
}
function pnlCompareToggleHtml(rerenderName, cmp) {
  if (!cmp) return '';
  const off = cmp.ok === false;
  const on  = !off && pnlChartCompare();
  const tip = off
    ? (cmp.why || 'No previous period to compare against.')
    : 'Draw the block of the same length immediately before this window as a dashed line, paired bucket for bucket. The same previous period the scorecards above compare against.';
  return `<span style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-left:10px">Compare</span>
    <span style="display:inline-flex;gap:2px;background:var(--surface2);border:1px solid var(--border2);border-radius:5px;padding:2px">
      <button type="button" ${off ? '' : `onclick="pnlSetChartCompare(${on ? 'false' : 'true'},'${rerenderName}')"`} title="${esc2(tip)}"
        style="padding:3px 9px;font-size:10px;font-family:var(--display);font-weight:${on ? 700 : 600};
        background:${on ? 'var(--sp-green)' : 'transparent'};color:${on ? '#fff' : 'var(--text2)'};
        border:none;border-radius:4px;cursor:${off ? 'not-allowed' : 'pointer'};opacity:${off ? '.4' : '1'}">vs prev period</button>
    </span>`;
}
const PNL_GRAIN_ORDER = ['day', 'week', 'month'];
const PNL_FILL_ALPHA = { sheer: '55', solid: 'd9' };
const PNL_FILL_LINE = '22';
function pnlChartGrain() {
  try {
    const v = localStorage.getItem('pnlChartGrain');
    return PNL_GRAIN_ORDER.includes(v) ? v : 'auto';
  } catch (_) { return 'auto'; }
}
function pnlGrainAuto(win) {
  if (!win || !win.from || !win.to) return 'week';
  const days = Math.round((new Date(win.to + 'T00:00:00') - new Date(win.from + 'T00:00:00')) / 86400000) + 1;
  if (!isFinite(days) || days <= 0) return 'week';
  if (days <= 70) return 'day';
  if (days <= 400) return 'week';
  return 'month';
}
function pnlGrainResolve(win, allowed) {
  const can = (allowed && allowed.length) ? allowed : PNL_GRAIN_ORDER;
  const want = pnlChartGrain();
  if (want !== 'auto' && can.includes(want)) return want;
  const auto = pnlGrainAuto(win);
  if (can.includes(auto)) return auto;
  // Nearest the chart CAN do, COARSER first: a finer grain than the rows
  // carry would be invented, a coarser one is only a rollup.
  const i = PNL_GRAIN_ORDER.indexOf(auto);
  for (let k = i; k < PNL_GRAIN_ORDER.length; k++) if (can.includes(PNL_GRAIN_ORDER[k])) return PNL_GRAIN_ORDER[k];
  for (let k = i; k >= 0; k--) if (can.includes(PNL_GRAIN_ORDER[k])) return PNL_GRAIN_ORDER[k];
  return 'week';
}
function pnlGrainKey(d, grain) {
  const s = String(d || '');
  if (!/^\d{4}-\d{2}-\d{2}/.test(s)) return s;       // already a month key, or junk
  if (grain === 'month') return s.slice(0, 7);
  if (grain !== 'week') return s.slice(0, 10);
  const x = new Date(s.slice(0, 10) + 'T00:00:00');
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
}
function pnlGrainAdv(grain) {
  return grain === 'day' ? 'daily' : grain === 'week' ? 'weekly'
       : grain === 'month' ? 'monthly' : (grain + 'ly');
}
function pnlChartFill() {
  try { return localStorage.getItem('pnlChartFill') === 'solid' ? 'solid' : 'sheer'; }
  catch (_) { return 'sheer'; }
}
function pnlStackAlpha() { return PNL_FILL_ALPHA[pnlChartFill()] || PNL_FILL_ALPHA.sheer; }
function esc2(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function pnlGrainStepperHtml(rerenderName, grain) {
  if (!grain) return '';
  const allowed = (grain.allowed && grain.allowed.length) ? grain.allowed : PNL_GRAIN_ORDER;
  const eff = pnlGrainResolve(grain.win, allowed);
  const stored = pnlChartGrain();
  const b = (v, label, tip) => {
    const off = v !== 'auto' && !allowed.includes(v);
    // v10.77 - light the EFFECTIVE grain, never the stored one. A stored
    // 'day' on a chart built from weekly rows must not paint D green while
    // the chart draws weeks.
    const on = !off && (v === 'auto' ? stored === 'auto' : (stored !== 'auto' && v === eff));
    const why = off ? (grain.why || 'These rows do not carry that grain.') : tip;
    return `<button type="button" ${off ? '' : `onclick="pnlSetChartGrain('${v}','${rerenderName}')"`} title="${esc2(why)}"
      style="padding:3px 8px;font-size:10px;font-family:var(--display);font-weight:${on ? 700 : 600};
      background:${on ? 'var(--sp-green)' : 'transparent'};color:${on ? '#fff' : 'var(--text2)'};
      border:none;border-radius:4px;cursor:${off ? 'not-allowed' : 'pointer'};opacity:${off ? '.35' : '1'}">${label}</button>`;
  };
  return `<span style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-left:10px">Group</span>
    <span style="display:inline-flex;gap:2px;background:var(--surface2);border:1px solid var(--border2);border-radius:5px;padding:2px">
      ${b('auto', 'Auto', 'Pick the grain from the window: daily to 70 days, weekly to 400, monthly beyond. Currently ' + pnlGrainAdv(eff) + '.')}
      ${b('day', 'D', 'One bucket per day.')}
      ${b('week', 'W', 'One bucket per week, starting Monday.')}
      ${b('month', 'M', 'One bucket per calendar month.')}
    </span>`;
}
function pnlFillToggleHtml(rerenderName) {
  const cur = pnlChartFill();
  const b = (v, label, tip) => {
    const on = cur === v;
    return `<button type="button" onclick="pnlSetChartFill('${v}','${rerenderName}')" title="${esc2(tip)}"
      style="padding:3px 8px;font-size:10px;font-family:var(--display);font-weight:${on ? 700 : 600};
      background:${on ? 'var(--sp-green)' : 'transparent'};color:${on ? '#fff' : 'var(--text2)'};
      border:none;border-radius:4px;cursor:pointer">${label}</button>`;
  };
  return `<span style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-left:10px">Fill</span>
    <span style="display:inline-flex;gap:2px;background:var(--surface2);border:1px solid var(--border2);border-radius:5px;padding:2px">
      ${b('sheer', 'Sheer', 'Bands at 33% opacity, so a band behind another still reads through it.')}
      ${b('solid', 'Solid', 'Bands at 85% opacity, so each layer reads as its own distinct block.')}
    </span>`;
}
function pnlChartScaleLock() {
  try { return localStorage.getItem('pnlChartScaleLock') === '1'; } catch (_) { return false; }
}
function pnlScaleToggleHtml(rerenderName) {
  const locked = pnlChartScaleLock();
  const b = (v, label, tip) => {
    const on = (v === 'lock') === locked;
    return `<button type="button" onclick="pnlSetChartScaleLock(${v === 'lock'},'${rerenderName}')" title="${esc2(tip)}"
      style="padding:3px 8px;font-size:10px;font-family:var(--display);font-weight:${on ? 700 : 600};
      background:${on ? 'var(--sp-green)' : 'transparent'};color:${on ? '#fff' : 'var(--text2)'};
      border:none;border-radius:4px;cursor:pointer">${label}</button>`;
  };
  return `<span style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-left:10px">Scale</span>
    <span style="display:inline-flex;gap:2px;background:var(--surface2);border:1px solid var(--border2);border-radius:5px;padding:2px">
      ${b('fit', 'Fit', 'The Y axis follows whatever is drawn, so hiding bands in the legend rescales it. Read the shape of what is left.')}
      ${b('lock', 'Lock', 'The Y axis stays at the full population\'s ceiling however many bands are hidden, so an isolated band keeps the height it had. Read its size against the whole.')}
    </span>`;
}
function pnlInjectChartModeToggle(hostId, rerenderName, noStack, bandNoun, cmp, grain) {
  const host = document.getElementById(hostId);
  if (!host) return;
  // ⚠ v10.77 — render the EFFECTIVE mode, not the stored one.
  //
  // pnlTrendSeries forces line mode for a percentage metric (percentages do not
  // sum), but this toggle kept painting Stacked green and kept rendering the
  // BANDS stepper underneath it — TWO live-looking controls that did nothing.
  // Jason read that exactly the way it looks: "if i change the metric to
  // contribution %, the stacked chart doesn't render." It renders; it renders as
  // a LINE, and the subtitle already says so. The controls were the only liars.
  //
  // This is the v10.19 lesson the BANDS comment below already records, so the
  // fix lives HERE rather than in each caller. The STORED preference is left
  // untouched, so switching back to a $ metric restores stacked.
  const stored = pnlChartMode();
  const blockStack = !!noStack;
  const mode = (blockStack && stored === 'stacked') ? 'line' : stored;
  const btn = (m, label, tip) => {
    const on = mode === m;
    const off = (m === 'stacked' && blockStack);
    const offTip = 'Not available';
    return `<button type="button" ${off ? '' : `onclick="pnlSetChartMode('${m}','${rerenderName}')"`} title="${off ? offTip : tip}"
      style="padding:3px 9px;font-size:10px;font-family:var(--display);font-weight:${on ? 700 : 600};
      background:${on ? 'var(--sp-green)' : 'transparent'};color:${on ? '#fff' : 'var(--text2)'};
      border:none;border-radius:4px;cursor:${off ? 'not-allowed' : 'pointer'};opacity:${off ? '.4' : '1'}">${label}</button>`;
  };
  // v10.67 - the BANDS stepper. Only rendered in stacked mode: in line mode
  // there is either one Total line or one line per selected product, so a
  // band count would be a live-looking control that does nothing.
  host.innerHTML = `<span style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">View</span>
    <span style="display:inline-flex;gap:2px;background:var(--surface2);border:1px solid var(--border2);border-radius:5px;padding:2px">
      ${btn('line', '\u2197 Line', 'One line per product, or a single total line when nothing is selected.')}
      ${btn('stacked', '\u25e2 Stacked', 'Filled areas stacked to the total, so you can see which products make it up.')}
    </span>`
    + pnlGrainStepperHtml(rerenderName, grain)
    + (mode === 'stacked' ? pnlBandsStepperHtml(rerenderName, bandNoun) : '')
    + (mode === 'stacked' ? pnlFillToggleHtml(rerenderName) : '')
    + pnlScaleToggleHtml(rerenderName)
    + pnlCompareToggleHtml(rerenderName, cmp);
}

// Faithful copy of the PRE-v10.77 body, for the regression guard.
function oldInjectToggle(hostId, rerenderName) {
  const host = document.getElementById(hostId);
  if (!host) return;
  const mode = pnlChartMode();
  const btn = (m, label, tip) => {
    const on = mode === m;
    return `<button type="button" onclick="pnlSetChartMode('${m}','${rerenderName}')" title="${tip}"
      style="background:${on ? 'var(--sp-green)' : 'transparent'}">${label}</button>`;
  };
  host.innerHTML = btn('line', 'Line', '') + btn('stacked', 'Stacked', '')
    + (mode === 'stacked' ? pnlBandsStepperHtml(rerenderName) : '');
}

// --- helpers -------------------------------------------------------------
function render(isPct, stored, inject) {
  _store = { pnlChartMode: stored };
  hosts.h = { innerHTML: '' };
  (inject || pnlInjectChartModeToggle)('h', 'rerender', isPct);
  return hosts.h.innerHTML;
}
// The buttons render in order: Line then Stacked.
const parts  = html => html.split('<button').slice(1);
const green  = p => p.indexOf('var(--sp-green)') !== -1;
const bands  = html => html.indexOf('<!--BANDS-->') !== -1;

// C1 - a DOLLAR metric is untouched: stacked stays stacked, BANDS renders.
let h = render(false, 'stacked');
t('C1  $ metric + stored stacked -> Stacked active, BANDS rendered',
  [green(parts(h)[0]), green(parts(h)[1]), bands(h)], [false, true, true]);

// C2 - a PERCENTAGE metric shows LINE active, because that is what draws.
h = render(true, 'stacked');
t('C2  % metric + stored stacked -> Line active, Stacked NOT active',
  [green(parts(h)[0]), green(parts(h)[1])], [true, false]);

// C3 - and the Stacked button is visibly, and functionally, unavailable.
const st = parts(h)[1];
t('C3  % metric -> Stacked is dimmed, not-allowed, and has NO onclick',
  [st.indexOf('opacity:.4') !== -1, st.indexOf('not-allowed') !== -1, st.indexOf('onclick') !== -1],
  [true, true, false]);

// C4 - the BANDS stepper is a stacked-only control; it must disappear too.
t('C4  % metric -> BANDS stepper is not rendered', bands(h), false);

// C5 - THE REGRESSION GUARD. The pre-v10.77 toggle painted Stacked green and
// rendered BANDS on a percentage metric, with the chart drawing a line.
const oldHtml = render(true, 'stacked', oldInjectToggle);
t('C5  REGRESSION GUARD: pre-v10.77 painted Stacked active + BANDS on a % metric',
  [green(parts(oldHtml)[1]), bands(oldHtml)], [true, true]);

// C6 - the STORED preference must survive, so switching back to a $ metric
// restores stacked rather than silently demoting the user to line.
render(true, 'stacked');
t('C6  stored preference untouched by a % metric render', _store.pnlChartMode, 'stacked');

// C7 - stored=line on a % metric is just line; nothing weird.
h = render(true, 'line');
t('C7  % metric + stored line -> Line active, Stacked dimmed, no BANDS',
  [green(parts(h)[0]), green(parts(h)[1]), bands(h)], [true, false, false]);

// C8 - isPct omitted entirely (old 2-arg call shape) degrades to the $ path.
_store = { pnlChartMode: 'stacked' };
hosts.h = { innerHTML: '' };
pnlInjectChartModeToggle('h', 'rerender');
t('C8  isPct omitted -> behaves exactly as before (no accidental blocking)',
  [green(parts(hosts.h.innerHTML)[1]), bands(hosts.h.innerHTML)], [true, true]);

console.log(JSON.stringify(out));
