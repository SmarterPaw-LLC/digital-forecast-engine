# -*- coding: utf-8 -*-
"""v10.0 — the export calls the top trend tier out. Drives the REAL csv()
and the REAL Excel styling branch, both lifted verbatim from index.html."""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', s, re.S), key=len)

def grab(a, b, label):
    i = js.find(a); j = js.find(b, i + 1)
    if i < 0 or j < 0:
        print('ANCHOR FAIL %s' % label); sys.exit(1)
    return js[i:j]

LABEL = grab('function ipVelTrendLabel(t) {', '\nfunction ', 'ipVelTrendLabel')

# The vel_trend csv function, verbatim.
# v10.1 moved this body into the shared velTrendCsv(t).
_a = js.index('function velTrendCsv(t) {')
_b = js.index('\n}', _a) + 2
CSVFN = js[_a:_b] + "\nconst _wrapCsv = { csv: r => velTrendCsv(ipVelTrendFor(r)) };\n" 

# The Excel palette + the trend styling branch, verbatim.
XLSX = js.index('async function downloadInventoryXlsx')
_pa = js.index('  const C = {', XLSX)
_pb = js.index('  const grpColor', _pa)
PAL = js[_pa:_pb]
m2 = re.search(r"        if \(keyOf\(col\) === 'vel_trend' && typeof v === 'string'\) \{.*?\n        \}\n", js, re.S)
if not m2:
    print('ANCHOR FAIL excel trend branch'); sys.exit(1)
STYLE = m2.group(0)

HARNESS = r"""
__LABEL__
function ipVelTrendFor(r){ return r.__t; }
__CSVFN__
const COL = _wrapCsv;
__PAL__

// The shipped styling branch, wrapped so it can be driven per value.
function styleFor(v) {
  const cell = {};
  const keyOf = () => 'vel_trend';
  const col = null;
__STYLE__
  return cell;
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const trend = (ratio) => { const prev = 10, now = 10 * ratio;
  return { __t: { now, prev, pct: (ratio - 1) * 100, lags: [], isNew: false, ready: true,
                  rawNow: now, rawPrev: prev, seaNow: 1, seaPrev: 1, w: 30, off: 30, keys: [] } }; };

console.log('\n== A. The exported VALUE carries label + magnitude ==');
for (const [ratio, want] of [[3.8,'Surging +280%'], [2.0,'Surging +100%'], [1.9,'Accelerating +90%'],
                             [1.15,'Growing +15%'], [0.85,'Slowing -15%'], [0.45,'Declining -55%']]) {
  const got = COL.csv(trend(ratio));
  t(`${ratio}x -> "${want}"`, got === want, got);
}
t('Steady carries no magnitude (a 0% delta is noise)', COL.csv(trend(1.0)) === 'Steady', COL.csv(trend(1.0)));
t('no arrows or glyphs survive into the cell',
  !/[\u2191\u2193\u2192\u2014\u{1F525}]/u.test([3.8,1.9,1.15,0.85,0.45,1.0].map(r => COL.csv(trend(r))).join(' ')));

console.log('\n== B. REGRESSION GUARD: Surging used to export GREY ==');
// Pre-v10.0 the branch tested /Accel|Growing|New/ and nothing else, so
// "Surging" fell through to C.mute - dimmer than Accelerating, inverting what
// the tier means.
const oldColor = (v) => /Accel|Growing|New/.test(v) ? C.up : /Declin|Slowing/.test(v) ? C.down : C.mute;
t('the old branch really did colour Surging grey', oldColor('Surging +280%') === C.mute);
t('  ...and it is no longer grey', styleFor('Surging +280%').font.color.argb !== C.mute);

console.log('\n== C. Surging is the only bucket with a FILL ==');
const sur = styleFor('Surging +280%');
t('Surging gets a solid fill', !!sur.fill && sur.fill.pattern === 'solid', sur.fill);
t('  in the surge green', sur.fill.fgColor.argb === C.surgeBg, sur.fill.fgColor);
t('  with white bold text', sur.font.color.argb === C.surgeFg && sur.font.bold === true, sur.font);
for (const v of ['Accelerating +90%', 'Growing +15%', 'Steady', 'Slowing -15%', 'Declining -55%', '\u2014 No data']) {
  t(`no fill on "${v}"`, !styleFor(v).fill, styleFor(v).fill);
}

console.log('\n== D. Everything below it is tiered, not one flat green ==');
t('Accelerating -> up green, bold',
  styleFor('Accelerating +90%').font.color.argb === C.up && styleFor('Accelerating +90%').font.bold === true);
t('Growing -> SOFTER green, not bold (recedes, as on screen)',
  styleFor('Growing +15%').font.color.argb === C.upSoft && styleFor('Growing +15%').font.bold === false);
t('  and upSoft is genuinely a different colour from up', C.upSoft !== C.up, { up: C.up, soft: C.upSoft });
t('Declining -> down red, bold',
  styleFor('Declining -55%').font.color.argb === C.down && styleFor('Declining -55%').font.bold === true);
t('Slowing -> amber, not bold',
  styleFor('Slowing -15%').font.color.argb === 'FFD68910' && styleFor('Slowing -15%').font.bold === false);
t('Steady -> mute', styleFor('Steady').font.color.argb === C.mute);
t('No data -> mute', styleFor('\u2014 No data').font.color.argb === C.mute);
t('New -> up green, bold (a launch is a mover)',
  styleFor('\u2191\u2191 New').font.color.argb === C.up && styleFor('\u2191\u2191 New').font.bold === true);

console.log('\n== E. The % suffix cannot break the matching ==');
t('"Growing +15%" does not match Accel', styleFor('Growing +15%').font.color.argb !== C.up);
t('"Declining -55%" does not match Growing', styleFor('Declining -55%').font.color.argb === C.down);
t('every bucket resolves to a real argb',
  ['Surging +280%','Accelerating +90%','Growing +15%','Steady','Slowing -15%','Declining -55%','\u2014 No data']
    .every(v => { const c = styleFor(v); const a = (c.font && c.font.color && c.font.color.argb) || (c.fill && C.surgeFg);
                  return typeof a === 'string' && /^FF[0-9A-F]{6}$/.test(a); }));

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

out = (HARNESS.replace('__LABEL__', LABEL)
              .replace('__CSVFN__', CSVFN.strip().rstrip(','))
              .replace('__PAL__', PAL.rstrip().rstrip(';') + ';')
              .replace('__STYLE__', STYLE))
p = os.path.join(SP, 'test_v100.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars' % len(out))
sys.exit(subprocess.call(['node', p]))
