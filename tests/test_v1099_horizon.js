
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
const pnlGrowthState = { horizonMonths: 6 };
let reran = 0, hintRefreshed = 0;
function pnlGrowthReRunIfDirty() { reran++; }
function pnlGrowthRefreshHorizonHint() { hintRefreshed++; }
const document = { getElementById: () => null };

const PNL_GROWTH_HORIZON_MAX = 60;
const PNL_GROWTH_HORIZON_LONG = 24;

function pnlGrowthHorizonHint(h) {
  const n = Number(h) || 0;
  if (n > PNL_GROWTH_HORIZON_LONG) {
    // Make the compounding concrete rather than vague. At the v9.23 clamp of
    // 30%/mo, 36 months is ~1.3^36 - a number nobody should plan against.
    return '<span style="color:var(--sp-orange)">\u26a0 ' + n + ' months \u2014 the baseline trend compounds every month, '
      + 'so projections this far out swing hard on a small trend error. Treat the later months as a direction, not a forecast.</span>';
  }
  if (n >= 1 && n <= 2) {
    return '<span style="color:var(--text3)">Short horizon \u2014 the ramp has little room to build, so the end share stays close to today\u2019s.</span>';
  }
  return '<span style="color:var(--text3)">1\u2013' + PNL_GROWTH_HORIZON_MAX + ' months. 6\u201312 is the usual planning range.</span>';
}
function pnlGrowthOnHorizonInput(raw) {
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 1) return;
  pnlGrowthState.horizonMonths = Math.min(PNL_GROWTH_HORIZON_MAX, n);
  pnlGrowthRefreshHorizonHint();
  pnlGrowthReRunIfDirty();
}
function pnlGrowthOnHorizonCommit(el) {
  let n = parseInt(el && el.value, 10);
  if (!Number.isFinite(n)) n = pnlGrowthState.horizonMonths || 6;
  n = Math.max(1, Math.min(PNL_GROWTH_HORIZON_MAX, n));
  pnlGrowthState.horizonMonths = n;
  if (el) el.value = String(n);
  pnlGrowthRefreshHorizonHint();
  pnlGrowthReRunIfDirty();
}

// Typing a plain number.
pnlGrowthOnHorizonInput('18');
t('F1  typing sets the state', pnlGrowthState.horizonMonths, 18);

// Mid-edit empty box must NOT snap the state to 1.
const before = pnlGrowthState.horizonMonths;
pnlGrowthOnHorizonInput('');
t('F2  clearing the box mid-edit leaves the state alone', pnlGrowthState.horizonMonths, before);
pnlGrowthOnHorizonInput('0');
t('F3  a transient 0 is ignored while typing', pnlGrowthState.horizonMonths, before);

// Over the cap while typing is still capped.
pnlGrowthOnHorizonInput('9999');
t('F4  typing past the cap clamps the state', pnlGrowthState.horizonMonths, 60);

// Commit normalises the visible field.
let el = { value: '0' };
pnlGrowthOnHorizonCommit(el);
t('F5  commit floors at 1', [pnlGrowthState.horizonMonths, el.value], [1, '1']);
el = { value: '500' };
pnlGrowthOnHorizonCommit(el);
t('F6  commit caps at 60', [pnlGrowthState.horizonMonths, el.value], [60, '60']);
el = { value: 'abc' };
pnlGrowthState.horizonMonths = 24;
pnlGrowthOnHorizonCommit(el);
t('F7  junk falls back to the current value', [pnlGrowthState.horizonMonths, el.value], [24, '24']);
el = { value: '36' };
pnlGrowthOnHorizonCommit(el);
t('F8  36 months is allowed (the ask)', pnlGrowthState.horizonMonths, 36);
el = { value: '7.9' };
pnlGrowthOnHorizonCommit(el);
t('F9  a decimal truncates to a whole month', [pnlGrowthState.horizonMonths, el.value], [7, '7']);

// The hint flips at the long-horizon threshold.
t('F10 a 12-month hint is the plain one', /usual planning range/.test(pnlGrowthHorizonHint(12)), true);
t('F11 a 36-month hint warns about compounding', /compounds/.test(pnlGrowthHorizonHint(36)), true);
t('F12 a 1-month hint names the short-ramp caveat', /Short horizon/.test(pnlGrowthHorizonHint(1)), true);
t('F13 no hint leaks undefined', /undefined|NaN/.test(
    pnlGrowthHorizonHint(1) + pnlGrowthHorizonHint(12) + pnlGrowthHorizonHint(36)), false);

// Every path must have re-run the model.
t('F14 every change re-runs the model', reran > 0, true);

console.log(JSON.stringify(out));
