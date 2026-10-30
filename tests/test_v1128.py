# -*- coding: utf-8 -*-
"""v11.28 - click a point on any trend chart to scope the window to it.

Jason: "on all of the timeline graphs, it would be nice if i could click on a
time and filter to that time. so, for example here, if i clicked on August, it
would change the date picker to custom : aug 1 - aug 31"

"All of the timeline graphs" is ONE function - pnlTrendRender, the engine
behind six charts - so the handler lives there and each caller opts in with a
single declared host.

The assertions that earn their keep:

  * D1 THE GRAIN IS THE MINIMUM STEP, NOT THE FIRST PAIR. The guard runs the
    naive first-pair read against a daily series with ONE missing day and
    shows it returns 'week' - which would turn a click on a single day into a
    seven-day window, silently, on a chart that looks entirely normal.

  * A1 JASON'S OWN EXAMPLE, literally: '2026-08' resolves to 2026-08-01 ->
    2026-08-31. A2/A3 pin February in a leap year and a common one, because
    the month length is derived (day 0 of the next month) rather than read off
    a table that can drift.

  * C3 THE DISPATCH IS DEFERRED. pnlPickBucket is called from inside the
    chart's own click handler and the repaint DESTROYS that chart - v10.66's
    overlapping-render trap from the other direction. The guard asserts the
    events have NOT fired when the call returns, and have fired a tick later.

  * C2 IT FIRES THE PAGE'S OWN HANDLERS, in the operator's order: the select
    first (which opens the custom wrap and deliberately does not repaint - the
    v10.79 half-entered-range rule), then `to` (which repaints, and on Chewy
    persists). Nothing here knows what any of the four pages do.

  * E3 EVERY DECLARED HOST HAS ALL FOUR CONTROLS IN THE MARKUP, and a custom
    option to put them behind. That is the registry/markup drift guard: a
    fifth host added to PNL_PERIOD_HOSTS without its bar fails here rather
    than on a click nobody tries.

NOT asserted: how it looks, or that a real Chart.js click lands on the right
index. The login gate leaves the app container hidden (v10.87) so the canvas
measures 0, and Chart.js hit-testing is Chart.js's own. What is pinned is that
the handler is wired, opt-in, and resolves a bucket to the right window.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name, got=None):
    global passed, failed
    if cond:
        passed += 1; print('  ok    ' + name)
    else:
        failed += 1
        print('  FAIL  ' + name + ('' if got is None else '   got=' + ascii(got)))

def eq(name, got, want):
    ok(got == want, name, None if got == want else '%s want %s' % (ascii(got), ascii(want)))


def fn(name):
    """Slice one function out by BRACE BALANCE, comments and strings masked."""
    i = js.index('function %s(' % name)
    m = list(js); k, n = i, len(js)
    while k < n:
        c = js[k]
        if c == '/' and k + 1 < n and js[k+1] == '/':
            while k < n and js[k] != '\n': m[k] = ' '; k += 1
            continue
        if c == '/' and k + 1 < n and js[k+1] == '*':
            while k < n and not (js[k] == '*' and k + 1 < n and js[k+1] == '/'):
                m[k] = ' '; k += 1
            m[k] = ' '
            if k + 1 < n: m[k+1] = ' '
            k += 2; continue
        if c in '"\'`':
            q = c; m[k] = ' '; k += 1
            while k < n and js[k] != q:
                if js[k] == '\\': m[k] = ' '; k += 1
                if k < n: m[k] = ' '
                k += 1
            if k < n: m[k] = ' '
            k += 1; continue
        k += 1
    mm = ''.join(m)
    depth, j = 0, mm.index('{', i)
    while j < n:
        if mm[j] == '{': depth += 1
        elif mm[j] == '}':
            depth -= 1
            if depth == 0: return js[i:j+1]
        j += 1
    raise AssertionError('unbalanced ' + name)


REG = js[js.index('const PNL_PERIOD_HOSTS'):]
REG = REG[:REG.index('};') + 2]
CORE = REG + '\n' + fn('pnlBucketRange') + '\n' + fn('pnlBucketGrain') + '\n' + fn('pnlPickBucket')

HARNESS = r"""
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

__CORE__

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
"""
HARNESS = HARNESS.replace('__CORE__', CORE)
hp = os.path.join(SP, 'test_v1128.js')
io.open(hp, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hp], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:3000]); sys.exit(1)
R = json.loads(res.stdout)
A, B, C = R['A'], R['B'], R['C']


print('== A. a bucket resolves to the window it stands for ==')
eq("A1  Jason's own example: clicking August gives Aug 1 - Aug 31",
   A['jasonAug'], {'from': '2026-08-01', 'to': '2026-08-31'})
eq('A2  February in a COMMON year ends on the 28th', A['feb2026'],
   {'from': '2026-02-01', 'to': '2026-02-28'})
eq('A3  and on the 29th in a leap year - derived as day 0 of the next month, '
   'never a table of month lengths that can drift', A['feb2024'],
   {'from': '2024-02-01', 'to': '2024-02-29'})
eq('A4  December rolls the YEAR over correctly', A['dec'],
   {'from': '2026-12-01', 'to': '2026-12-31'})
eq('A5  /!\\ a YYYY-MM bucket is a MONTH whatever grain the caller claims - '
   'the string is unambiguous and the hint is not', A['monthWins'],
   {'from': '2026-08-01', 'to': '2026-08-31'})
eq('A6  a week start gives its seven days, inclusive', A['week'],
   {'from': '2026-08-09', 'to': '2026-08-15'})
eq('A7  and a week that crosses a month boundary does not stop at the month',
   A['weekCross'], {'from': '2026-08-30', 'to': '2026-09-05'})
eq('A8  nor at a year boundary', A['weekYear'],
   {'from': '2026-12-28', 'to': '2027-01-03'})
eq('A9  a day is itself', A['day'], {'from': '2026-08-15', 'to': '2026-08-15'})
eq('A10 a dated bucket declared monthly takes the whole month', A['dayAsMonth'],
   {'from': '2026-08-01', 'to': '2026-08-31'})
for k in ('junk', 'empty', 'nul'):
    eq('A11 an unreadable bucket returns null, never a half window (%s)' % k,
       A[k], None)


print('\n== B. the grain is inferred from the SERIES ==')
eq('B1  a daily series reads day', B['daily'], 'day')
eq('B2  a weekly series reads week', B['weekly'], 'week')
eq('B3  a YYYY-MM series reads month', B['monthly'], 'month')
eq('B4  and so does a dated series stepping a month at a time', B['monthish'], 'month')
eq('B5  one bucket cannot say which, so it stays the narrow reading',
   B['one'], 'day')
eq('B6  an empty series does not throw', B['none'], 'day')
eq('B7  nor an absent one', B['undef'], 'day')


print('\n== D. the regression guard: first-pair vs minimum step ==')
eq('D1a /!\\ the NAIVE first-pair read calls a daily series with ONE missing '
   'day a WEEKLY one', B['naiveGapped'], 'week')
eq('D1b so a click on 2026-08-01 would have scoped SEVEN days', B['naiveWindow'],
   {'from': '2026-08-01', 'to': '2026-08-07'})
eq('D1c where the shipped minimum-step read scopes the one day actually '
   'clicked', B['realWindow'], {'from': '2026-08-01', 'to': '2026-08-01'})
eq('D1d and the series is still correctly daily', B['gapped'], 'day')


print('\n== C. the apply fires the PAGE\'S OWN handlers ==')
eq('C1a the call reports success', C['ret'], True)
eq('C1b the select moves to custom', C['sel'], 'custom')
eq('C1c from', C['from'], '2026-08-01')
eq('C1d to', C['to'], '2026-08-31')
# /!\ My first expectation here was WRONG about the design, not about the
# code. pnlPickBucket deliberately does NOT touch the custom wrap: the four
# period selects each already set it from their own `change` handler, so
# opening it here would be a SECOND owner of that one piece of state - the
# divergence hard rule #1 exists to stop. It opens a tick later, through the
# page's own code, which is why the stub (whose dispatchEvent only records)
# correctly leaves it shut.
eq('C1e the wrap is NOT opened here - each page\'s own period handler already '
   'owns that, and a second owner of one piece of state is the thing hard '
   'rule #1 forbids', C['wrap'], 'none')
wrap_owner = js[js.index('function pnlPickBucket('):]
wrap_owner = wrap_owner[:wrap_owner.index('\n}\n')]
ok('custom-wrap' not in re.sub(r'//[^\n]*', '', wrap_owner),
   'C1f asserted against the CODE, so the wrap cannot quietly gain a second '
   'owner here later')

eq('C2a /!\\ NOTHING has been dispatched when the call returns. The repaint '
   'destroys the chart whose click handler we are inside, so it is deferred '
   '(v10.66, from the other direction)', C['logBeforeTick'], [])

# /!\ Every pick in this harness queues its own deferred dispatch, and they
# all land before the read. So the assertion is on the SHAPE of the whole log
# rather than on its length - which is the stronger claim anyway: the select
# always fires first and its own `to` always follows immediately.
LAT = R['logAfterTick']
eq('C2b the last pick dispatched exactly two events', LAT[-2:],
   ['pnl-period:change', 'pnl-to:change'])
pairs_ok = (len(LAT) % 2 == 0) and all(
    LAT[i].endswith('-period:change')
    and LAT[i + 1] == LAT[i].replace('-period:change', '-to:change')
    for i in range(0, len(LAT), 2))
ok(pairs_ok,
   'C2c and EVERY pick fires the select first and then its own `to` - the '
   'operator\'s own order, so a click and a typed date cannot resolve '
   'differently, and no host\'s events interleave with another\'s', LAT)

C2, C3, C4, C5 = R['C2'], R['C3'], R['C4'], R['C5']
eq('C3a an unknown host returns false', C2['ret'], False)
ok(any('PNL_PERIOD_HOSTS' in w for w in C2['warn']),
   'C3b and WARNS by name rather than defaulting to some other page\'s '
   'control, which would move a window on a tab nobody is looking at '
   '(v11.18)', C2['warn'])
eq('C3c touching nothing', C2['sel'], '90')
eq('C3d and dispatching nothing', C2['log'], [])

eq('C4a a control with no custom option is REFUSED', C3['ret'], False)
eq('C4b and left alone - a <select> set to a value it does not offer shows '
   'its first option while the resolver reads something else (v11.02)',
   C3['sel'], '90')
ok(any('custom' in w for w in C3['warn']), 'C4c with a warning that says why', C3['warn'])

eq('C5a a missing date input is refused', C4['ret'], False)
ok(any('custom-range controls' in w for w in C4['warn']), 'C5b and named', C4['warn'])
eq('C6a an unreadable bucket is refused', C5['ret'], False)
eq('C6b before the control is touched', C5['sel'], '90')

for h in R['hosts']:
    o = R['hostOut'][h]
    ok(o['ret'] is True and o['from'] == '2026-08-09' and o['to'] == '2026-08-15',
       'C7  every declared host applies the same window: ' + h, o)


print('\n== E. the registry, the callers and the markup agree ==')
eq('E1a exactly one trend renderer still', js.count('async function pnlTrendRender('), 1)
eq('E1b and one click handler on it', js.count('onClick: (evt, els, chart)'), 1)
eq('E1c and one bucket->window helper', js.count('function pnlBucketRange('), 1)
ok('if (!cfg.periodHost) return;' in js,
   'E1d /!\\ OPT-IN: a caller that declares no periodHost behaves exactly as '
   'it did at v11.27, which is the only way "no existing chart changed" is '
   'checkable rather than read off a diff')

CALLERS = [
    ("spnl-chart-canvas", "'spnl'"), ("pnl-chart-canvas", "'pnl'"),
    ("wmpnl-chart-canvas", "'wmpnl'"), ("chpnl-chart-canvas", "'chpnl'"),
    ("chpnl-pg-chart-canvas", "'chpnl'"),
]
for canvas, host in CALLERS:
    line = [l for l in js.split('\n') if "canvasId: '" + canvas + "'" in l]
    ok(len(line) == 1 and 'periodHost: ' + host in line[0],
       'E2  %s declares periodHost %s' % (canvas, host), line)
ok("periodHost: ch.periodHost" in js,
   'E2f and the Ads chart takes its host off the ADAPTER - one renderer, '
   'three channels, so the host cannot be written in')
for ch, host in [('pnl', "periodHost: 'pnl',"), ('chpnl', "periodHost: 'chpnl',"),
                 ('wmpnl', "periodHost: 'wmpnl',")]:
    ok(host in js, 'E2g ADS_CHANNELS declares ' + host)

# /!\ THE DRIFT GUARD. A fifth host added to the registry without its control
# bar fails HERE rather than on a click nobody tries.
for host in R['hosts']:
    for suffix in ('-period', '-custom-wrap', '-from', '-to'):
        ok('id="%s%s"' % (host, suffix) in s,
           'E3  %s declares host "%s" and the markup has %s%s'
           % ('PNL_PERIOD_HOSTS', host, host, suffix))
    i = s.index('id="%s-period"' % host)
    blk = s[i:s.index('</select>', i)]
    ok('value="custom"' in blk,
       'E3b and its period control offers a custom range to put them behind')

used = set(re.findall(r"periodHost: '([a-z]+)'", js))
ok(used <= set(R['hosts']),
   'E4  every periodHost written anywhere is one the registry declares, so a '
   'typo fails the build instead of warning at click time', sorted(used))

ok("canvas.title = 'Click a point to set the period to that '" in js,
   'E5  the explanation rides on the native tooltip rather than as another '
   'line of prose on a panel that already has a subtitle and a coverage line')
ok("c.style.cursor = cfg.periodHost ? 'pointer' : 'default'" in js,
   'E6  and the pointer cursor is the affordance, only where it does '
   'something (the v10.19 rule)')


print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
