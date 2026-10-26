# -*- coding: utf-8 -*-
r"""v10.94 - the Growth Model panel described the PREVIOUS product.

Jason: "why is it giving me this error at the bottom" - the panel read
"1 ASIN-view month loaded / 2026-08" while the model underneath said
"No SQP ASIN view data found for B07KPRTSMT".

Both read the SAME cache with the SAME filter:

    (amazonSqpAsinCache || []).filter(r => r.view_type === 'asin' && r.asin === asin)

so they cannot legitimately disagree. The panel was describing a different
product. pnlGrowthOnAsinChange set pnlGrowthState.asin, cleared lastResult
and emptied the result div - but never re-rendered. So the <select> showed
the new product while every readout beneath it still belonged to the old
one: months loaded, the Brand-view warning, the confidence badge, the
uplift "This ASIN:" hints, the recommendation bar.

The model was the honest one. It ran on the real selection, found nothing,
and said so - against a panel quietly claiming otherwise.

Also: Jason asked to copy the ASIN, and v10.93 gave him a coverage report
instead. The ASIN is now on screen with its own copy button, and the v10.93
button says what it actually copies so the two cannot be confused.
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

def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', src)

def fn(name):
    m = re.search(r'(?:async\s+)?function\s+' + name + r'\s*\(', JS)
    if not m: return ''
    k = JS.index('(', m.end() - 1); d = 0
    while True:
        if JS[k] == '(': d += 1
        elif JS[k] == ')':
            d -= 1
            if d == 0: break
        k += 1
    j = JS.index('{', k); d = 0; k = j
    while True:
        if JS[k] == '{': d += 1
        elif JS[k] == '}':
            d -= 1
            if d == 0: return JS[m.start():k + 1]
        k += 1

HANDLER = fn('pnlGrowthOnAsinChange')
HCODE   = strip_comments(HANDLER)


# -- A. Switching product re-renders the panel ----------------------------
print('\nA. the panel follows the selection')

ok(bool(HANDLER), 'pnlGrowthOnAsinChange located')
ok('pnlGrowthRender()' in HCODE, 'it re-renders')
# Order matters: rendering BEFORE the state is set would paint the old
# product all over again.
ok(HCODE.index('pnlGrowthState.asin = asin') < HCODE.index('pnlGrowthRender()'),
   'the state is updated BEFORE the render, so the render sees the new product')
ok(HCODE.index('pnlGrowthState.lastResult = null') < HCODE.index('pnlGrowthRender()'),
   'lastResult is cleared first, so the render cannot auto-replay the old result')
# The render rebuilds an empty result div, so the old manual clear is covered.
ok("getElementById('pnl-growth-result').innerHTML = ''" not in HCODE,
   'the manual result-clear is gone - pnlGrowthRender rebuilds it')
ok("id=\"pnl-growth-result\"></div>" in fn('pnlGrowthRender'),
   '...and pnlGrowthRender really does emit a fresh empty result div')

# The two readouts that contradicted each other must still share one filter,
# or they can drift apart again by a different route.
RENDER = strip_comments(fn('pnlGrowthRender'))
MODEL  = strip_comments(fn('_pnlGrowthRunModelImpl'))
filt = r"view_type === 'asin' && r\.asin === "
ok(re.search(filt, RENDER) is not None, 'the panel filters SQP rows by view_type + asin')
ok(re.search(filt, MODEL) is not None, 'the model filters SQP rows by view_type + asin')
ok(re.search(filt + r'pnlGrowthState\.asin', RENDER) is not None,
   'the panel reads the CURRENT selection, not a captured copy')


# The fix re-renders the whole form, which is only safe because every
# settings input persists to pnlGrowthState as you change it - so the rebuild
# reads your edits back rather than resetting them. An input added later that
# only gets read at Run time would silently lose work on every product switch.
print()
ctrl = re.findall(r'(?:onchange|oninput)="([^"]*)"', RENDER)
settings = [h for h in ctrl if 'pnlGrowthOnAsinChange' not in h]
ok(len(settings) >= 9, 'found the settings inputs to check', len(settings))
bad = [h[:70] for h in settings if 'pnlGrowthState.' not in h]
ok(not bad,
   'EVERY settings input persists to pnlGrowthState, so the re-render cannot lose edits',
   bad)
# Guard the guard: it must be able to spot one that does not persist.
ok([h for h in ['pnlGrowthReRunIfDirty()'] if 'pnlGrowthState.' not in h] != [],
   'the check can detect a handler that does not persist')


# -- B. Regression guard: drive both versions -----------------------------
print('\nB. the old handler really did leave the panel stale')

harness = r'''
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// -- stubs ---------------------------------------------------------------
let pnlGrowthState = { asin: null, masterId: null, lastResult: null };
let RENDER_CALLS = [];
const CATALOG = new Map([
  ['B07OLD', { asin: 'B07OLD', master_id: 'SP-0001' }],
  ['B07KPRTSMT', { asin: 'B07KPRTSMT', master_id: 'SP-0002' }],
]);
function pnlGrowthEligibleAsins() { return CATALOG; }

// What the panel WOULD paint, given the state at render time. Stands in for
// the months-loaded / confidence / Brand-view readouts, which all key off
// pnlGrowthState.asin.
function pnlGrowthRender() { RENDER_CALLS.push(pnlGrowthState.asin); }

let resultDiv = { innerHTML: 'stale result' };
const document = { getElementById: () => resultDiv };

// -- the PRE-v10.94 handler, reproduced verbatim -------------------------
function pnlGrowthOnAsinChange_OLD(asin) {
  const catalog = pnlGrowthEligibleAsins();
  const p = catalog.get(asin);
  if (!p) return;
  pnlGrowthState.asin = asin;
  pnlGrowthState.masterId = p.master_id;
  pnlGrowthState.lastResult = null;
  document.getElementById('pnl-growth-result').innerHTML = '';
}

__HANDLER__

function reset(startAsin) {
  pnlGrowthState = { asin: startAsin, masterId: 'SP-0001', lastResult: { asin: startAsin } };
  RENDER_CALLS = [];
  resultDiv = { innerHTML: 'stale result' };
}

// -- 1. The bug, reproduced ---------------------------------------------
reset('B07OLD');
pnlGrowthOnAsinChange_OLD('B07KPRTSMT');
t('B1  OLD: state moved to the new product', pnlGrowthState.asin, 'B07KPRTSMT');
t('B2  OLD: but the panel was NEVER re-rendered - that is the bug',
  RENDER_CALLS.length, 0);

// -- 2. The fix ---------------------------------------------------------
reset('B07OLD');
pnlGrowthOnAsinChange('B07KPRTSMT');
t('B3  NEW: the panel is re-rendered exactly once', RENDER_CALLS.length, 1);
t('B4  NEW: ...and it renders the NEW product, not the old one',
  RENDER_CALLS[0], 'B07KPRTSMT');
t('B5  NEW: masterId follows too', pnlGrowthState.masterId, 'SP-0002');
t('B6  NEW: the previous result is dropped before the render',
  pnlGrowthState.lastResult, null);

// -- 3. An unknown ASIN must not render or mutate anything --------------
reset('B07OLD');
pnlGrowthOnAsinChange('B07NOPE');
t('B7  an unknown ASIN leaves the state alone', pnlGrowthState.asin, 'B07OLD');
t('B8  ...and does not re-render', RENDER_CALLS.length, 0);

// -- 4. Re-selecting the SAME product still repaints --------------------
// Cheap, and it is the natural way to recover a panel after an upload.
reset('B07KPRTSMT');
pnlGrowthOnAsinChange('B07KPRTSMT');
t('B9  re-picking the same product repaints', RENDER_CALLS, ['B07KPRTSMT']);

console.log(JSON.stringify(out));
'''
harness = harness.replace('__HANDLER__', HANDLER)
hp = os.path.join(SP, 'test_v1094_asinchange.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True)
if r.returncode != 0:
    print('  FAIL  handler harness did not run:\n' + (r.stderr or '')[:2000]); F += 1; fails.append('harness')
else:
    try: rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  handler harness unparseable: %s\n%s' % (e, r.stdout[:600])); F += 1; fails.append('harness parse'); rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


# -- C. The ASIN, with a copy button --------------------------------------
print('\nC. the ASIN is on screen and copyable')

ok("pnlCopyAsin('${pnlGrowthState.asin || ''}', this)" in RAW,
   'the copy button copies the SELECTED ASIN')
ok('pnlCopyAsin' in fn('pnlGrowthRender'),
   'the button lives in the Growth Model panel')
# Reuse, not a fourth copy affordance (hard rule #1).
ok(len(re.findall(r'function\s+copyTextToClipboard\s*\(', JS)) == 1,
   'still exactly one clipboard writer')
ok('copyTextToClipboard(' in strip_comments(fn('pnlCopyAsin')),
   'the ASIN button routes through the shared writer')
# The ASIN text itself is selectable, for people who drag-select rather than
# click a button.
R = fn('pnlGrowthRender')
ok('user-select:all' in R, 'the ASIN text is click-to-select as well')
ok(R.count('event.stopPropagation()') >= 2,
   'the ASIN span and its button both stop propagation')


# -- D. The two copy buttons cannot be confused ---------------------------
print('\nD. one concept, one label')

ok('\u2398 months</button>' in RAW, 'the v10.93 coverage button now says "months"')
ok('\u2398 copy</button>' not in RAW,
   'no button is labelled the ambiguous bare "copy" any more')
# The coverage tooltip points at the ASIN button, so neither is a dead end.
ok('To copy just the ASIN' in RAW,
   'the months tooltip names where to get just the ASIN')
ok(RAW.count('pnlGrowthCopyCoverage(this)') == 1,
   'the coverage handler is wired exactly once')


print('\n' + '=' * 62)
print('  v10.94  PASS %d   FAIL %d' % (P, F))
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
