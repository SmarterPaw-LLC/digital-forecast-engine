
// ---- real code, sliced out of index.html ----
function parseLocalDate(s) {
  if (!s) return null;
  const str = String(s).trim();
  // ISO YYYY-MM-DD (optionally with time — we discard the time component)
  let m = str.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  // M/D/YYYY or MM/DD/YYYY (US format)
  m = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) return new Date(+m[3], +m[1] - 1, +m[2]);
  // D-Mon-YYYY or similar — fall back to native parse but pin to local
  // midnight (use the date parts, drop time).
  const d = new Date(str);
  if (isNaN(d)) return null;
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}
const _salesMonthKey   = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
const _salesDaysInMonth = (y, m0) => new Date(y, m0 + 1, 0).getDate();

const SALES_CHANNELS = {
  amazon_us: { label: 'Amazon US',   color: '#4a9e38' },
  amazon_ca: { label: 'Amazon CA',   color: '#f97316' },
  // v7.61 — Shopify DTC moved from blue (#3b82f6) → cyan (#06b6d4). Walmart's
  // brand color is a near-identical blue (#0071dc), so at chart scale — and
  // especially in stacked-area mode — Shopify and Walmart layers blurred into
  // one indistinguishable blue mass. Cyan stays in the Shopify-teal family
  // (their gradient runs mint→teal) and is distinct from every other channel.
  shopify:   { label: 'Shopify DTC', color: '#06b6d4' },
  chewy:     { label: 'Chewy',       color: '#a855f7' },
  walmart:   { label: 'Walmart',     color: '#0071dc' },
};
function salesGoalWeeklyFor(weeks, chanKeys, strict) {
  const chans = (chanKeys || []).filter(ch => Object.keys(salesGoals[ch] || {}).length > 0);
  if (!chans.length) return null;
  const has = (ch, mk) => (salesGoals[ch] || {})[mk] != null;
  const covered = (mk) => strict ? chans.every(ch => has(ch, mk)) : chans.some(ch => has(ch, mk));
  let any = false;
  const out = weeks.map(w => {
    // Local parse — the v9.71 rule. `new Date('2026-09-21')` is UTC midnight
    // and reads back as the previous day in any UTC-negative timezone, which
    // would walk the wrong seven days.
    const mon = parseLocalDate(w);
    if (!mon) return null;
    let total = 0;
    for (let i = 0; i < 7; i++) {
      const d  = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + i);
      const mk = _salesMonthKey(d);
      if (!covered(mk)) return null;
      const dim = _salesDaysInMonth(d.getFullYear(), d.getMonth());
      chans.forEach(ch => {
        const g = (salesGoals[ch] || {})[mk];
        if (g != null) total += Number(g) / dim;
      });
    }
    any = true;
    return Math.round(total * 10) / 10;
  });
  return any ? out : null;
}
function salesGoalChannels() {
  return Object.keys(SALES_CHANNELS).filter(ch => Object.keys(salesGoals[ch] || {}).length > 0);
}
function salesGoalDatasets(weeks, chanKeys, mode) {
  if (!salesGoalsOn || !weeks || !weeks.length) return [];
  const mk = (label, data, color) => ({
    type: 'line',
    label, data,
    borderColor: color,
    backgroundColor: 'transparent',
    borderDash: [6, 4],
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 3,
    tension: 0,
    fill: false,
    spanGaps: false,
    stack: '_goal',
    order: -1,
    _isGoal: true,
  });
  if (mode === 'channel') {
    return (chanKeys || [])
      .filter(ch => Object.keys(salesGoals[ch] || {}).length > 0)
      .map(ch => {
        const series = salesGoalWeeklyFor(weeks, [ch], true);
        return series
          ? mk(`\u{1F3AF} ${SALES_CHANNELS[ch]?.label || ch} goal`, series, SALES_CHANNELS[ch]?.color || '#9ca3af')
          : null;
      })
      .filter(Boolean);
  }
  const chans = salesGoalChannels();
  if (!chans.length) return [];
  const series = salesGoalWeeklyFor(weeks, chans, false);
  if (!series) return [];
  return [mk(`\u{1F3AF} Goal \u00b7 ${chans.length} channel${chans.length === 1 ? '' : 's'}`, series, '#eab308')];
}
function salesGoalSubNote(goalDs, actual) {
  if (!goalDs || !goalDs.length) return '';
  const goal = goalDs.reduce((s, d) => s + d.data.reduce((a, b) => a + (Number(b) || 0), 0), 0);
  if (!(goal > 0)) return '';
  const pct = Math.round((Number(actual) || 0) / goal * 100);
  return ` \u00b7 \u{1F3AF} goal ${Math.round(goal).toLocaleString()} (${pct}% of goal)` + salesGoalScopeNote();
}
function salesGoalScopeNote() {
  if (!salesGoalsOn || !salesGoalChannels().length) return '';
  const bits = [];
  if (salesSelected.size > 0) bits.push(`${salesSelected.size} product${salesSelected.size === 1 ? '' : 's'} selected`);
  if (document.getElementById('salesBrand')?.value) bits.push('brand filter');
  if (document.getElementById('salesCat')?.value) bits.push('category filter');
  if ((document.getElementById('salesSrch')?.value || '').trim()) bits.push('search');
  if (document.getElementById('salesHideBundles')?.checked) bits.push('bundles hidden');
  if (typeof topProductFilterId !== 'undefined' && topProductFilterId) bits.push('top-product chip');
  if (!bits.length) return '';
  return ` \u00b7 \u26a0 goal is business-wide \u2014 ${bits.join(' + ')} narrows the actuals, not the goal`;
}

// ---- stubs ----
let salesGoals = {};
let salesGoalsOn = true;
let salesSelected = new Set();
let topProductFilterId = null;
let _dom = {};
const document = { getElementById: (id) => (_dom[id] || null) };

const out = [];
const T = (name, got, want) => out.push({ name, got, want, pass: JSON.stringify(got) === JSON.stringify(want) });

// 3100 over a 31-day January = exactly 100 units/day.
// 2800 over a 28-day February = exactly 100 units/day too.
// Same daily rate, different monthly number: the weekly line must be FLAT.
const JAN_FEB = { amazon_us: { '2026-01': 3100, '2026-02': 2800 } };
const JAN_ONLY = { amazon_us: { '2026-01': 3100 } };
const JAN_FEB_FAST = { amazon_us: { '2026-01': 3100, '2026-02': 5600 } };   // Feb = 200/day

// Mondays: 2026-01-05 is fully inside January.
// 2026-01-26 covers Jan 26-31 (6 days) + Feb 1 (1 day).
// 2026-02-02 is fully inside February.
const W_JAN  = '2026-01-05';
const W_EDGE = '2026-01-26';
const W_FEB  = '2026-02-02';

salesGoals = JAN_ONLY;
T('B1 full week inside a month = 7 x daily rate',
  salesGoalWeeklyFor([W_JAN], ['amazon_us'], true), [700]);

salesGoals = JAN_FEB;
T('B2 same daily rate across a 31d and a 28d month = FLAT weekly line',
  salesGoalWeeklyFor([W_JAN, W_EDGE, W_FEB], ['amazon_us'], true), [700, 700, 700]);

salesGoals = JAN_FEB_FAST;
T('B3 straddling week blends per DAY (6 x 100 + 1 x 200)',
  salesGoalWeeklyFor([W_EDGE], ['amazon_us'], true), [800]);

// --- THE REGRESSION GUARD ---------------------------------------------------
// Pre-fix behaviour: sum whatever days happen to be covered, with no
// all-days-covered gate. The straddling week then reports 6/7 of a full week,
// which draws as a goal CRASH at the end of the goal range.
function naiveWeekly(weeks, chans) {
  return weeks.map(w => {
    const mon = parseLocalDate(w);
    let total = 0;
    for (let i = 0; i < 7; i++) {
      const d = new Date(mon.getFullYear(), mon.getMonth(), mon.getDate() + i);
      const mk = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      const dim = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
      chans.forEach(ch => {
        const g = (salesGoals[ch] || {})[mk];
        if (g != null) total += Number(g) / dim;
      });
    }
    return Math.round(total * 10) / 10;
  });
}
salesGoals = JAN_ONLY;   // February has NO goal at all
T('B4a GUARD: the naive version really does report a partial week (600)',
  naiveWeekly([W_EDGE], ['amazon_us']), [600]);
T('B4b shipped code refuses to draw that week at all (no series)',
  salesGoalWeeklyFor([W_EDGE], ['amazon_us'], true), null);
T('B4c and the fully-covered week before it is unaffected',
  salesGoalWeeklyFor([W_JAN, W_EDGE], ['amazon_us'], true), [700, null]);

// --- strict vs loose coverage ----------------------------------------------
// Shopify has January only. Amazon has January AND February.
salesGoals = { amazon_us: { '2026-01': 3100, '2026-02': 2800 },
               shopify:   { '2026-01':  620 } };
T('B5 single-channel line does NOT draw 0 for a month it has no goal for',
  salesGoalWeeklyFor([W_FEB], ['shopify'], true), null);
T('B5b and in a mixed window that month is a gap beside a real week',
  salesGoalWeeklyFor([W_JAN, W_FEB], ['shopify'], true), [140, null]);
T('B6 business total still draws in February off the channel that HAS a goal',
  salesGoalWeeklyFor([W_FEB], ['amazon_us', 'shopify'], false), [700]);
T('B7 business total sums both channels in a month both cover (700 + 140)',
  salesGoalWeeklyFor([W_JAN], ['amazon_us', 'shopify'], false), [840]);

// --- degenerate shapes -----------------------------------------------------
salesGoals = {};
T('B8 no goals at all returns null (no series), not an array of zeros',
  salesGoalWeeklyFor([W_JAN], ['amazon_us'], true), null);
salesGoals = { amazon_us: { '2026-01': 3100 } };
T('B9 a channel with no goal data is dropped from the request',
  salesGoalWeeklyFor([W_JAN], ['walmart'], true), null);
T('B10 an all-null window returns null rather than a line of gaps',
  salesGoalWeeklyFor([W_FEB], ['amazon_us'], true), null);
T('B11 a malformed week key is a gap beside a good week, not a throw',
  salesGoalWeeklyFor([W_JAN, 'not-a-date'], ['amazon_us'], true), [700, null]);

// ---------------------------------------------------------------------------
// C. dataset shape
// ---------------------------------------------------------------------------
salesGoals = { amazon_us: { '2026-01': 3100 }, shopify: { '2026-01': 620 } };

salesGoalsOn = false;
T('C1 toggle OFF produces no dataset at all',
  salesGoalDatasets([W_JAN], null, 'total'), []);
salesGoalsOn = true;

const tot = salesGoalDatasets([W_JAN], null, 'total');
T('C2 total mode = exactly ONE line', tot.length, 1);
T('C3 stack is isolated so a stacked chart cannot add the target into the stack',
  tot[0].stack, '_goal');
T('C4 flagged _isGoal so unit totals can exclude it', tot[0].isGoal_flag = tot[0]._isGoal, true);
T('C5 drawn as a dashed, unfilled line even inside a bar/area chart',
  [tot[0].type, tot[0].fill, Array.isArray(tot[0].borderDash)], ['line', false, true]);
T('C6 total line value = sum across both channels (700 + 140)', tot[0].data, [840]);
T('C7 gaps are NOT spanned, so the line ends where the goals do',
  tot[0].spanGaps, false);

const perCh = salesGoalDatasets([W_JAN], ['amazon_us', 'shopify', 'walmart'], 'channel');
T('C8 channel mode emits one line per channel WITH goals (walmart dropped)',
  perCh.length, 2);
T('C9 each channel line carries its own channel colour',
  perCh.map(d => d.borderColor), [SALES_CHANNELS.amazon_us.color, SALES_CHANNELS.shopify.color]);
T('C10 per-channel values are that channel alone', perCh.map(d => d.data), [[700], [140]]);
T('C11 no weeks = no dataset (cannot divide an empty window)',
  salesGoalDatasets([], null, 'total'), []);

// ---------------------------------------------------------------------------
// D. subtitle note + scope warning
// ---------------------------------------------------------------------------
T('D1 % of goal is actual/goal, and the goal is NOT added to actual',
  salesGoalSubNote(tot, 420).indexOf('50% of goal') > -1, true);
T('D2 no goal series = no note', salesGoalSubNote([], 420), '');

salesSelected = new Set();
_dom = {};
T('D3 a clean, unfiltered view carries no scope warning', salesGoalScopeNote(), '');
salesSelected = new Set(['SP-0001', 'SP-0002']);
const note = salesGoalScopeNote();
T('D4 a product selection warns that the goal is business-wide',
  [note.indexOf('business-wide') > -1, note.indexOf('2 products selected') > -1], [true, true]);
salesSelected = new Set();
_dom = { salesBrand: { value: 'Meowijuana' }, salesSrch: { value: 'spray' } };
const note2 = salesGoalScopeNote();
T('D5 every narrowing filter is named, not just the first',
  [note2.indexOf('brand filter') > -1, note2.indexOf('search') > -1], [true, true]);
salesGoalsOn = false;
T('D6 no warning when the overlay is off', salesGoalScopeNote(), '');
salesGoalsOn = true;

console.log(JSON.stringify(out));
