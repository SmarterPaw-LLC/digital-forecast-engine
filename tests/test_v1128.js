
'use strict';
const LOG = [];
const WARN = [];
console.warn = (...a) => WARN.push(a.join(' '));

class Ev { constructor(t, o) { this.type = t; this.bubbles = !!(o && o.bubbles); } }
global.Event = Ev;

function mkSel(opts) {
  return {
    value: opts[0], options: opts.map(v => ({ value: v })), _id: null,
    dispatchEvent(e) { LOG.push(this._id + ':' + e.type); return true; },
  };
}
function mkInput(id) {
  return { value: '', _id: id, dispatchEvent(e) { LOG.push(id + ':' + e.type); return true; } };
}

let DOM = {};
global.document = { getElementById: (id) => DOM[id] || null };

function freshDom(host, opts) {
  const sel = mkSel(opts || ['90', 'all', 'custom']); sel._id = host + '-period';
  DOM = {};
  DOM[host + '-period'] = sel;
  DOM[host + '-from'] = mkInput(host + '-from');
  DOM[host + '-to'] = mkInput(host + '-to');
  DOM[host + '-custom-wrap'] = { style: { display: 'none' } };
  return DOM;
}

const PNL_PERIOD_HOSTS = {
  pnl:   'Amazon P&L',
  spnl:  'Shopify P&L',
  wmpnl: 'Walmart P&L',
  chpnl: 'Chewy P&L',
};
function pnlBucketRange(bucket, grain) {
  const m = String(bucket || '').match(/^(\d{4})-(\d{2})(?:-(\d{2}))?$/);
  if (!m) return null;
  const [, y, mo, d] = m;
  // Day 0 of the NEXT month is the last day of this one - leap years
  // included, with no table of month lengths to keep in step.
  const whole = () => {
    const last = new Date(Date.UTC(+y, +mo, 0)).getUTCDate();
    return { from: `${y}-${mo}-01`, to: `${y}-${mo}-${String(last).padStart(2, '0')}` };
  };
  // No day part means a MONTH whatever the caller thinks its grain is: the
  // string itself is unambiguous and the caller's hint is not.
  if (!d) return whole();
  if (grain === 'month') return whole();
  if (grain === 'week') {
    const dt = new Date(Date.UTC(+y, +mo - 1, +d));
    dt.setUTCDate(dt.getUTCDate() + 6);
    return { from: `${y}-${mo}-${d}`, to: dt.toISOString().slice(0, 10) };
  }
  return { from: `${y}-${mo}-${d}`, to: `${y}-${mo}-${d}` };
}
function pnlBucketGrain(buckets) {
  const b = (buckets || []).map(x => String(x || '')).filter(Boolean);
  if (!b.length) return 'day';
  if (/^\d{4}-\d{2}$/.test(b[0])) return 'month';
  let step = Infinity;
  for (let i = 1; i < b.length; i++) {
    const d = (Date.parse(b[i] + 'T00:00:00Z') - Date.parse(b[i - 1] + 'T00:00:00Z')) / 86400000;
    if (d > 0 && d < step) step = d;
  }
  if (!isFinite(step)) return 'day';   // one bucket cannot say which
  if (step >= 28) return 'month';
  if (step >= 2)  return 'week';
  return 'day';
}
function pnlPickBucket(host, bucket, grain) {
  // v11.18 - an unknown host is a BUG, not a case to default. Falling back to
  // some other page's control would move a window on a tab nobody is looking
  // at, which is the wrong-looking-right shape that hid for a release.
  if (!PNL_PERIOD_HOSTS[host]) {
    console.warn('pnlPickBucket: no period host "' + host + '" - add it to PNL_PERIOD_HOSTS');
    return false;
  }
  const range = pnlBucketRange(bucket, grain);
  if (!range) { console.warn('pnlPickBucket: unreadable bucket "' + bucket + '"'); return false; }
  const sel  = document.getElementById(host + '-period');
  const from = document.getElementById(host + '-from');
  const to   = document.getElementById(host + '-to');
  if (!sel || !from || !to) {
    console.warn('pnlPickBucket: "' + host + '" has no custom-range controls');
    return false;
  }
  // v11.02 - a <select> set to a value it does not offer shows its first
  // option while the resolver reads something else. Refuse rather than put
  // the control and the window out of step.
  if (![...sel.options].some(o => o.value === 'custom')) {
    console.warn('pnlPickBucket: "' + host + '" offers no custom range');
    return false;
  }
  sel.value  = 'custom';
  from.value = range.from;
  to.value   = range.to;
  // /!\ FIRE THE PAGE'S OWN HANDLERS, never a repaint picked here. Each of
  // the four selects opens its custom wrap and deliberately does NOT repaint
  // on `custom` (the v10.79 half-entered-range rule); each `to` input then
  // repaints - and on Chewy both persist to localStorage. Dispatching the two
  // changes IS the operator's own sequence, so a click and a typed date
  // cannot resolve differently, and nothing here has to know what any of the
  // four pages do.
  //
  // /!\ DEFERRED: that repaint destroys and rebuilds the very chart whose
  // click handler we are inside. One tick leaves Chart.js's dispatch first.
  setTimeout(() => {
    try {
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      to.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (e) { console.warn('pnlPickBucket:', e); }
  }, 0);
  return true;
}

// ── A. bucket -> window ───────────────────────────────────────────────
const A = {
  jasonAug:   pnlBucketRange('2026-08', 'month'),
  feb2026:    pnlBucketRange('2026-02', 'month'),
  feb2024:    pnlBucketRange('2024-02', 'month'),
  dec:        pnlBucketRange('2026-12', 'month'),
  monthWins:  pnlBucketRange('2026-08', 'day'),
  week:       pnlBucketRange('2026-08-09', 'week'),
  weekCross:  pnlBucketRange('2026-08-30', 'week'),
  weekYear:   pnlBucketRange('2026-12-28', 'week'),
  day:        pnlBucketRange('2026-08-15', 'day'),
  dayAsMonth: pnlBucketRange('2026-08-15', 'month'),
  junk:       pnlBucketRange('not a date', 'day'),
  empty:      pnlBucketRange('', 'day'),
  nul:        pnlBucketRange(null, 'day'),
};

// ── B. grain inference ────────────────────────────────────────────────
const daily   = ['2026-08-01','2026-08-02','2026-08-03','2026-08-04'];
const gapped  = ['2026-08-01','2026-08-08','2026-08-09','2026-08-10'];   // one hole at the front
const weekly  = ['2026-08-02','2026-08-09','2026-08-16','2026-08-23'];
const monthly = ['2026-06','2026-07','2026-08'];
const monthish= ['2026-06-01','2026-07-01','2026-08-01'];

// D1 - the NAIVE read: first pair only. On `gapped` it says week.
function naiveGrain(b) {
  if (!b.length) return 'day';
  if (/^\d{4}-\d{2}$/.test(b[0])) return 'month';
  if (b.length < 2) return 'day';
  const d = (Date.parse(b[1] + 'T00:00:00Z') - Date.parse(b[0] + 'T00:00:00Z')) / 86400000;
  if (d >= 28) return 'month';
  if (d >= 2) return 'week';
  return 'day';
}

const B = {
  daily: pnlBucketGrain(daily), gapped: pnlBucketGrain(gapped),
  weekly: pnlBucketGrain(weekly), monthly: pnlBucketGrain(monthly),
  monthish: pnlBucketGrain(monthish),
  one: pnlBucketGrain(['2026-08-05']), none: pnlBucketGrain([]), undef: pnlBucketGrain(undefined),
  naiveGapped: naiveGrain(gapped),
  naiveWindow: pnlBucketRange('2026-08-01', naiveGrain(gapped)),
  realWindow:  pnlBucketRange('2026-08-01', pnlBucketGrain(gapped)),
};

// ── C. the apply ──────────────────────────────────────────────────────
freshDom('pnl');
LOG.length = 0;
const okPick = pnlPickBucket('pnl', '2026-08', 'month');
const C = {
  ret: okPick,
  sel: DOM['pnl-period'].value,
  from: DOM['pnl-from'].value,
  to: DOM['pnl-to'].value,
  wrap: DOM['pnl-custom-wrap'].style.display,
  logBeforeTick: LOG.slice(),
};

// unknown host
freshDom('pnl'); LOG.length = 0; WARN.length = 0;
const badHost = pnlPickBucket('nope', '2026-08', 'month');
const C2 = { ret: badHost, sel: DOM['pnl-period'].value, warn: WARN.slice(), log: LOG.slice() };

// a control with no custom option
freshDom('pnl', ['90', 'all']); LOG.length = 0; WARN.length = 0;
const noCustom = pnlPickBucket('pnl', '2026-08', 'month');
const C3 = { ret: noCustom, sel: DOM['pnl-period'].value, warn: WARN.slice() };

// missing date inputs
freshDom('pnl'); delete DOM['pnl-to']; LOG.length = 0; WARN.length = 0;
const noInputs = pnlPickBucket('pnl', '2026-08', 'month');
const C4 = { ret: noInputs, warn: WARN.slice() };

// an unreadable bucket
freshDom('pnl'); LOG.length = 0; WARN.length = 0;
const badBucket = pnlPickBucket('pnl', 'August', 'month');
const C5 = { ret: badBucket, sel: DOM['pnl-period'].value, warn: WARN.slice() };

// every declared host applies
const hostOut = {};
for (const h of Object.keys(PNL_PERIOD_HOSTS)) {
  freshDom(h); LOG.length = 0;
  const r = pnlPickBucket(h, '2026-08-09', 'week');
  hostOut[h] = { ret: r, from: DOM[h + '-from'].value, to: DOM[h + '-to'].value };
}

// now let the deferred dispatch run
freshDom('pnl'); LOG.length = 0;
pnlPickBucket('pnl', '2026-08', 'month');
setTimeout(() => {
  console.log(JSON.stringify({
    A, B, C, C2, C3, C4, C5, hostOut,
    hosts: Object.keys(PNL_PERIOD_HOSTS),
    logAfterTick: LOG.slice(),
  }));
}, 5);
