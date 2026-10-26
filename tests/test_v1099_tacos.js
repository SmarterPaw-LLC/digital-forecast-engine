
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
function has(name, html, needle) {
  out.push({ name, pass: String(html).includes(needle),
             got: JSON.stringify(String(html).slice(0, 260)), want: JSON.stringify(needle) });
}

const pnlGrowthState = { lastResult: null, maxMonthlyTacosPct: 20, enforceTacosCeiling: true };
const document = { getElementById: () => null };

function pnlGrowthTacosStateHtml() {
  const r = pnlGrowthState.lastResult;
  const ceil = pnlGrowthState.maxMonthlyTacosPct;
  if (!r || !Array.isArray(r.months) || !r.months.length) {
    return '<span style="color:var(--text3)">Run the model to see whether this ceiling binds.</span>';
  }
  const H = r.months.length;
  const capped = r.months.filter(m => m.capped_by_ceiling).length;
  const over   = r.months.filter(m => m.over_ceiling).length;
  const peak   = Math.max(...r.months.map(m => m.tacos_pct || 0));

  if (!pnlGrowthState.enforceTacosCeiling) {
    return over > 0
      ? '<span style="color:var(--sp-red)">\u26a0 Not enforced \u2014 ' + over + ' of ' + H + ' months run over ' + ceil + '% (peak ' + peak.toFixed(1) + '%). Tick the box to cap the ramp.</span>'
      : '<span style="color:var(--text3)">Not enforced \u2014 nothing exceeds ' + ceil + '% anyway (peak ' + peak.toFixed(1) + '%).</span>';
  }
  if (capped > 0) {
    return '<span style="color:var(--sp-orange)">Binding \u2014 ' + capped + ' of ' + H + ' months capped at ' + ceil + '%, so achieved share falls short of target.</span>';
  }
  return '<span style="color:var(--text3)">Not binding \u2014 peak month is ' + peak.toFixed(1) + '%, under ' + ceil + '%, so nothing was capped. '
    + 'A ceiling caps; it does not hold TACOS at a value. Set it below ' + peak.toFixed(1) + '% to make it bite.</span>';
}

// --- Jason's exact shape: 12 months, 13.8% -> 17.9%, ceiling 20 ---------
const JASON = [13.8,14.9,15.7,16.3,16.8,17.2,17.5,17.7,17.8,17.9,17.9,17.9]
  .map(v => ({ tacos_pct: v, capped_by_ceiling: false, over_ceiling: false }));

pnlGrowthState.lastResult = { months: JASON };
const jasonHtml = pnlGrowthTacosStateHtml();
has('E1  his case reads NOT BINDING, not "ignored"', jasonHtml, 'Not binding');
has('E2  it names the peak month so the number is checkable', jasonHtml, '17.9%');
has('E3  it names the ceiling being compared against', jasonHtml, '20%');
has('E4  it states a ceiling caps rather than holds', jasonHtml, 'does not hold TACOS at a value');
// The actionable half: what to set it to.
has('E5  it names the value that would make it bite', jasonHtml, 'Set it below 17.9%');

// --- Same months, ceiling lowered under the peak -> gate fires ----------
pnlGrowthState.maxMonthlyTacosPct = 15;
const capped = JASON.map((m, i) => ({ ...m, capped_by_ceiling: i >= 2 }));
pnlGrowthState.lastResult = { months: capped };
const bindHtml = pnlGrowthTacosStateHtml();
has('E6  a binding ceiling reads BINDING', bindHtml, 'Binding');
has('E7  ...with the count of capped months', bindHtml, '10 of 12');
has('E8  ...and names the consequence (share falls short)', bindHtml, 'falls short');

// --- Enforcement OFF, months over the ceiling --------------------------
pnlGrowthState.maxMonthlyTacosPct = 15;
pnlGrowthState.enforceTacosCeiling = false;
pnlGrowthState.lastResult = { months: JASON.map((m, i) => ({ ...m, over_ceiling: i >= 2 })) };
const offHtml = pnlGrowthTacosStateHtml();
has('E9  not-enforced + over the ceiling warns', offHtml, 'Not enforced');
has('E10 ...names how many months blow through', offHtml, '10 of 12');
has('E11 ...and names the fix', offHtml, 'Tick the box');

// --- Enforcement OFF but nothing exceeds anyway ------------------------
pnlGrowthState.maxMonthlyTacosPct = 20;
pnlGrowthState.lastResult = { months: JASON };
const offQuiet = pnlGrowthTacosStateHtml();
has('E12 not-enforced + nothing over says so plainly', offQuiet, 'nothing exceeds');
t('E13 ...and does NOT cry wolf', /Tick the box/.test(offQuiet), false);

// --- Degenerate shapes must not throw ----------------------------------
pnlGrowthState.enforceTacosCeiling = true;
pnlGrowthState.lastResult = null;
has('E14 no result yet -> an honest prompt, not a verdict',
    pnlGrowthTacosStateHtml(), 'Run the model');
pnlGrowthState.lastResult = { months: [] };
has('E15 empty months -> same prompt, no crash',
    pnlGrowthTacosStateHtml(), 'Run the model');
pnlGrowthState.lastResult = { months: [{}] };
t('E16 a month with no tacos_pct does not produce NaN',
  /NaN/.test(pnlGrowthTacosStateHtml()), false);

console.log(JSON.stringify(out));
