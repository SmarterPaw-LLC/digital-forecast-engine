# -*- coding: utf-8 -*-
r"""v10.99 - open planning horizon + a TACOS ceiling that says whether it binds.

(A) Jason: "planning horizon should be input, not a drop down. i should be
    able to model on any number of months"

    Same ask and same fix as v10.16, which did this to Target supply on
    Inventory Planning. Two things move with it or "any number of months" is
    only half true: the M1..MN pickers were a non-wrapping flex row, and the
    baseline trend COMPOUNDS monthly, so a long horizon extrapolates hard.
    That is not a reason to cap the field at 12; it is a reason to say so.

(B) Jason: "i don't think monthly taco % is being honored in the table"

    It is. tacos_pct on every month row IS the plan.tacosPct the ceiling gate
    compares - one value, read twice - so the table and the gate cannot
    disagree. His months ran 13.8-17.9% against a 20% ceiling, so the gate
    never fired: a CEILING is a cap, not a target.

    The defect was that none of this was readable from the control. The input
    said "20" and nothing said whether 20 was doing anything, so "not binding"
    and "silently ignored" looked identical. The fix is a state readout next
    to the number that sets it - not more prose in the footer.
"""
import io, os, re, sys, json, subprocess

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8', newline='').read()
JS  = max(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond:
        P += 1; print('  ok  ' + label)
    else:
        F += 1; fails.append(label)
        print('  FAIL ' + label + (('  -> ' + str(got)) if got is not None else ''))


def fn(name):
    """Slice a function body by brace balance (params first, then body)."""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\(', JS)
    if not m:
        return ''
    i = m.end() - 1
    depth = 0
    while i < len(JS):                      # balance the PARAMETER list first
        if JS[i] == '(': depth += 1
        elif JS[i] == ')':
            depth -= 1
            if depth == 0: break
        i += 1
    j = JS.index('{', i)
    depth = 0
    k = j
    while k < len(JS):
        if JS[k] == '{': depth += 1
        elif JS[k] == '}':
            depth -= 1
            if depth == 0: break
        k += 1
    return JS[m.start():k + 1]


# -- A. The horizon control is an open field ------------------------------
print('\nA. planning horizon is a numeric input')

ok('<select id="pnl-growth-horizon"' not in JS,
   'the dropdown is gone')
ok(re.search(r'<input id="pnl-growth-horizon" type="number"', JS) is not None,
   'replaced by a numeric input')
ok('PNL_GROWTH_HORIZON_MAX' in JS and 'const PNL_GROWTH_HORIZON_MAX = 60' in JS,
   'the cap is a named constant, not a magic number')
# The old option set must not survive as dead markup.
for v in ('3', '6', '9', '12'):
    ok(('<option value="%s" ${s.horizonMonths === %s' % (v, v)) not in JS,
       'no leftover <option value="%s">' % v)

ok('pnlGrowthOnHorizonInput' in JS and 'pnlGrowthOnHorizonCommit' in JS,
   'input and commit handlers both exist')

# The commit handler must NOT fire on every keystroke - clearing the box to
# retype "12" would snap it to 1 under the cursor.
inp = fn('pnlGrowthOnHorizonInput')
ok('el.value' not in inp and 'this.value =' not in inp,
   'typing never rewrites the field (clamp happens on commit)')
ok('Math.min(PNL_GROWTH_HORIZON_MAX' in inp,
   '...but the state is still capped while typing')

com = fn('pnlGrowthOnHorizonCommit')
ok('Math.max(1' in com and 'Math.min(PNL_GROWTH_HORIZON_MAX' in com,
   'commit clamps to [1, MAX]')
ok('el.value = String(n)' in com,
   'commit normalises the visible field')

# horizonMonths must still round-trip through saved strategies.
ok("'horizonMonths'" in JS, 'horizonMonths still a saved-strategy field')


# -- B. The long-horizon caveat is stated, not enforced -------------------
print('\nB. a long horizon warns rather than being forbidden')

hint = fn('pnlGrowthHorizonHint')
ok(bool(hint), 'the hint function exists')
ok('PNL_GROWTH_HORIZON_LONG' in hint, 'it keys off a named threshold')
ok('compounds' in hint, 'it names compounding as the actual limit')
# The whole point: a long horizon is ALLOWED, just flagged. If the cap ever
# drops back to 12 "to be safe", that silently re-breaks Jason's ask.
ok(60 == int(re.search(r'const PNL_GROWTH_HORIZON_MAX = (\d+)', JS).group(1)),
   'the cap is 60, so 36 months is reachable')
ok('return' in hint and 'throw' not in hint,
   'the long-horizon path warns and returns - it never blocks')


# -- C. Month pickers can hold a long horizon -----------------------------
print('\nC. the M1..MN strips wrap')

# Both strips (Keyword Allocation + Execution Plan) are the same markup.
wrapped = len(re.findall(
    r'gap:5px;margin-left:auto;flex-wrap:wrap', JS))
ok(wrapped == 2, 'both month-picker strips wrap', 'found %d' % wrapped)
ok('gap:5px;margin-left:auto"' not in JS,
   'no non-wrapping strip survives')

# Clamping already existed; make sure it still does, or a shrinking horizon
# strands execPlanMonth past the end of the array.
ok(re.search(r'Math\.min\(r\.months\.length, monthIdx', JS) is not None,
   'selected month clamps to the months actually computed')
ok(re.search(r'Math\.min\(result\.horizonMonths,\s*pnlGrowthState\.execPlanMonth', JS) is not None,
   '...and clamps again at render')


# -- D. The ceiling-vs-table claim, settled -------------------------------
print("\nD. the table's TACOS IS the value the ceiling gate compares")

# This is the assertion that answers Jason's report. If these two ever read
# different fields, the table really could disagree with the gate.
ok(re.search(r'tacos_pct:\s*plan\.tacosPct', JS) is not None,
   'the month row reports plan.tacosPct')
ok(re.search(r'plan\.tacosPct > s\.maxMonthlyTacosPct', JS) is not None,
   'the ceiling gate compares plan.tacosPct')
n_tacos_field = len(re.findall(r'tacos_pct:', JS))
ok(n_tacos_field == 1,
   'exactly ONE site assigns tacos_pct, so the table cannot drift from the gate',
   'found %d' % n_tacos_field)

# Enforcement must stay gated on the ceiling being EXCEEDED. A ceiling that
# fired unconditionally would be a target, which is a different feature.
ok('s.enforceTacosCeiling && revPerUnit > 0 && plan.tacosPct > s.maxMonthlyTacosPct' in JS,
   'enforcement fires only when the ceiling is actually exceeded')


# -- E. The ceiling now says whether it binds -----------------------------
print('\nE. binding state is readable from the control')

ok('pnl-growth-tacos-state' in JS, 'the readout element exists')
ok('pnlGrowthTacosStateHtml' in JS and 'pnlGrowthRefreshTacosState' in JS,
   'builder + refresher both exist')
ok(re.search(r'pnlGrowthRenderResult\(result\);\s*\n\s*pnlGrowthRefreshTacosState\(\);', JS) is not None,
   'the readout refreshes after every run (binding state needs the months)')

harness = r'''
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

__STATE_FN__

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
'''

state_fn = fn('pnlGrowthTacosStateHtml')
if not state_fn:
    print('  FAIL  could not slice pnlGrowthTacosStateHtml'); F += 1; fails.append('slice')
else:
    hp = os.path.join(SP, 'test_v1099_tacos.js')
    io.open(hp, 'w', encoding='utf-8', newline='').write(
        harness.replace('__STATE_FN__', state_fn))
    r = subprocess.run(['node', hp], capture_output=True, text=True)
    if r.returncode != 0:
        print('  FAIL  tacos harness did not run:\n' + (r.stderr or '')[:2000])
        F += 1; fails.append('tacos harness')
    else:
        try: rows = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception as e:
            print('  FAIL  tacos harness unparseable: %s\n%s' % (e, r.stdout[:600]))
            F += 1; fails.append('tacos parse'); rows = []
        for row in rows:
            ok(row['pass'], row['name'],
               None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


# -- F. Horizon handlers, driven --------------------------------------------
print('\nF. horizon clamping, driven')

h2 = r'''
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

__CONSTS__
__HINT__
__INPUT__
__COMMIT__

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
'''

consts = ''
for cname in ('PNL_GROWTH_HORIZON_MAX', 'PNL_GROWTH_HORIZON_LONG'):
    mm = re.search(r'const ' + cname + r' = [^;]+;', JS)
    if mm: consts += mm.group(0) + '\n'

h2 = (h2.replace('__CONSTS__', consts)
        .replace('__HINT__', fn('pnlGrowthHorizonHint'))
        .replace('__INPUT__', fn('pnlGrowthOnHorizonInput'))
        .replace('__COMMIT__', fn('pnlGrowthOnHorizonCommit')))
hp2 = os.path.join(SP, 'test_v1099_horizon.js')
io.open(hp2, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', hp2], capture_output=True, text=True)
if r2.returncode != 0:
    print('  FAIL  horizon harness did not run:\n' + (r2.stderr or '')[:2000])
    F += 1; fails.append('horizon harness')
else:
    try: rows2 = json.loads(r2.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  horizon harness unparseable: %s\n%s' % (e, r2.stdout[:600]))
        F += 1; fails.append('horizon parse'); rows2 = []
    for row in rows2:
        ok(row['pass'], row['name'],
           None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


print('\n' + '=' * 62)
print('  v10.99  PASS %d   FAIL %d' % (P, F))
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
