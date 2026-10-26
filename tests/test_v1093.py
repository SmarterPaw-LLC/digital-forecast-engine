# -*- coding: utf-8 -*-
r"""v10.93 - copy the Growth Model SQP coverage, and ONE clipboard writer.

Jason: "allow me to copy what is showing here so i can plug it into amazon"

The panel already lists the SQP ASIN-view months that ARE loaded. What he
needs in Seller Central is the inverse - the months still to pull - so the
copied block leads with the gaps.

Two things this suite pins:

  1. ONE clipboard writer. There were already two hand-rolled copies
     (pnlCopyAsin + copyQueryResults) and a third was about to be added -
     the divergence hard rule #1 exists to stop. Consolidating is also a
     real fix: copyQueryResults had NO fallback and NO catch, so on an
     http:// origin navigator.clipboard is null, it threw, and its status
     line never moved. A dead button on exactly the setups least likely to
     get debugged (the v7.53 silent-no-op class).

  2. The copied text reports the SNAPSHOT the panel rendered, never a
     recompute. A recompute could silently disagree with the panel it
     claims to be copying - the v8.00 pnlExportRows rule.

The month window is pure YYYY-MM index arithmetic with no Date involved, so
the v9.71 timezone class cannot reach it. It also ends at LAST COMPLETE
month: Amazon publishes SQP in arrears, so listing the current month as
"missing" would send him after a file that does not exist yet.
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
    """Drop // line comments and /* */ blocks.

    v10.92 lesson: the fixes DOCUMENT the old broken call in a comment, so a
    naive grep matches forever and the guard can never go green.
    """
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', src)

def fn(name):
    """Slice a function by brace balance, including any `async ` prefix.

    v10.85 / v10.91 trap: an anchor on `function X(` matches INSIDE
    `async function X(` and splits it.
    """
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

JS_CODE = strip_comments(JS)
WRITER  = fn('copyTextToClipboard')


# -- A. Exactly one clipboard writer --------------------------------------
print('\nA. one writer, and every path reports')

ok(bool(WRITER), 'copyTextToClipboard located')
ok(len(re.findall(r'function\s+copyTextToClipboard\s*\(', JS)) == 1,
   'declared exactly once')

# The sweep that keeps the consolidation from drifting back.
outside = strip_comments(JS.replace(WRITER, ' '))
ok(len(re.findall(r'\.writeText\s*\(', outside)) == 0,
   'no OTHER navigator.clipboard.writeText anywhere',
   re.findall(r'.{40}\.writeText\s*\(', outside)[:3])
ok(len(re.findall(r"execCommand\(\s*['\"]copy", outside)) == 0,
   'no OTHER execCommand("copy") anywhere',
   re.findall(r".{40}execCommand\(\s*['\"]copy", outside)[:3])
# Guard the sweep: it must still SEE the two calls inside the helper, or it
# passes vacuously (the v10.20 masking class).
ok(len(re.findall(r'\.writeText\s*\(', strip_comments(WRITER))) >= 1,
   'the sweep can still see writeText inside the helper')
ok(re.search(r"execCommand\(\s*['\"]copy", strip_comments(WRITER)) is not None,
   'the sweep can still see execCommand inside the helper')

# The fallback is the whole reason to consolidate - without it, copy is a dead
# button on any http:// origin.
W = strip_comments(WRITER)
ok('navigator.clipboard?.writeText' in W, 'feature-detects the modern API')
ok('createElement(\'textarea\')' in W, 'has the hidden-textarea fallback')
ok('.catch(legacy)' in W, 'a rejected promise falls back rather than failing silently')
ok(re.search(r'\}\s*else\s*\{\s*legacy\(\);', W) is not None,
   'a null navigator.clipboard goes straight to the fallback')
# Pin the GUARANTEE, not the mechanism: a throwing clipboard API must still
# attempt the fallback, and if that throws too it must report rather than
# swallow. v10.93c added the failed() report inside that catch.
ok(re.search(r'catch\s*\{\s*try\s*\{\s*legacy\(\);\s*\}\s*catch\s*\{', W) is not None,
   'a throwing clipboard API still attempts the fallback')
ok(re.search(r'catch\s*\{\s*try\s*\{\s*legacy\(\);\s*\}\s*catch\s*\{\s*failed\(\);', W) is not None,
   '...and a throwing fallback reports instead of failing silently')
# Reporting: a silent success is as bad as a silent failure.
ok('o.okHtml' in W and 'onOk' in W, 'reports via a button flash AND a callback')
# v10.93c - and the FAILURE path reports too. Both paths can legitimately fail
# (no user gesture, locked-down clipboard policy); staying silent there makes
# the button look dead, which is the exact symptom this release removed from
# three other call sites.
ok('const failed =' in W, 'has an explicit failure path')
ok('copy blocked' in W, 'the failure flash says what happened')
ok('onFail' in W, 'callers can supply their own failure handler')
ok('else failed();' in W, 'a false execCommand result reports failure')
ok(W.count('done()') >= 1 and 'okd !== false' in W,
   'success is only claimed when execCommand did not report failure')
# The hidden textarea must never be left in the DOM, even if select/exec throw.
ok('removeChild(ta)' in W, 'the fallback textarea is always removed')


# -- B. Both old writers delegate -----------------------------------------
print('\nB. the two previous copies now delegate')

ASIN = strip_comments(fn('pnlCopyAsin'))
ok('copyTextToClipboard(' in ASIN, 'pnlCopyAsin delegates')
ok('.writeText' not in ASIN and 'execCommand' not in ASIN,
   'pnlCopyAsin keeps no writer of its own')
# Kept as a named wrapper so existing call sites + greps still land.
ok(len(re.findall(r"pnlCopyAsin\(", RAW)) >= 2,
   'pnlCopyAsin is still called (markup + definition)')

QR = strip_comments(fn('copyQueryResults'))
ok('copyTextToClipboard(' in QR, 'copyQueryResults delegates')
ok('.writeText' not in QR, 'copyQueryResults keeps no writer of its own')
ok('onOk' in QR and 'query-status' in QR,
   'copyQueryResults still updates its own status line, via onOk')
ok('copyQueryResults()' in RAW, 'copyQueryResults is still wired in markup')

# A THIRD writer the sweep found: the Product modal's master_id copy button.
# It was the worst of the three - no fallback, no catch, and NO FEEDBACK even
# on success, so the operator could not tell whether the click landed.
ok("copyTextToClipboard('${mid}', { btn: this })" in RAW,
   'the product-modal master_id copy delegates, and flashes the button')
ok('navigator.clipboard.writeText(' + chr(39) + '${mid}' + chr(39) + ')' not in RAW,
   'the bare inline writeText on that button is gone')


# -- C. The copy button exists and is wired -------------------------------
print('\nC. the button')

ok('pnlGrowthCopyCoverage(this)' in RAW, 'the button calls the handler with itself')
ok(re.search(r'pnlGrowthCopyCoverage\(this\);event\.stopPropagation\(\)', RAW) is not None,
   'stopPropagation, so copying does not also fire the row/panel handler')
HANDLER = strip_comments(fn('pnlGrowthCopyCoverage'))
ok('copyTextToClipboard(' in HANDLER, 'the handler routes through the shared writer')
ok('okHtml' in HANDLER, 'the button flashes a confirmation')
ok('alert(' in HANDLER, 'an empty coverage block says so rather than copying nothing')
# It sits in the coverage row, beside the existing "grab more months" link.
ok(RAW.index('pnlGrowthCopyCoverage(this)') > RAW.index('grab more months'),
   'the button sits in the coverage row after the grab-more-months link')


# -- D. The copied text is the SNAPSHOT, not a recompute ------------------
print('\nD. what is copied is what is shown')

TXT = strip_comments(fn('pnlGrowthCoverageText'))
ok('_pnlGrowthCoverage' in TXT, 'reads the render-time snapshot')
for cache in ['amazonSqpAsinCache', 'amazonSpSearchTermCache']:
    ok(cache not in TXT,
       'does NOT recompute from %s - it could drift from the panel' % cache)
ok(len(re.findall(r'let\s+_pnlGrowthCoverage', JS)) == 1,
   'the snapshot var is declared exactly once')

RENDER = fn('pnlGrowthRender')
ok('_pnlGrowthCoverage = {' in RENDER, 'pnlGrowthRender stashes the snapshot')
for k in ['sqpMonths', 'spMonths', 'brandViewMonths', 'confidence', 'asin', 'sqpLink']:
    ok(k in RENDER.split('_pnlGrowthCoverage = {')[1][:700],
       'snapshot carries %s' % k)
# The snapshot must be built from the SAME locals the panel renders, or the
# whole point is lost.
snap = RENDER.split('_pnlGrowthCoverage = {')[1][:700]
ok('monthsLoadedList' in snap, 'sqpMonths comes from the list the panel renders')
ok('spMonthsAvail' in snap, 'spMonths comes from the list the panel renders')
ok('confidenceLabel' in snap, 'confidence comes from the label the panel renders')


# -- E. The month window, driven for real ---------------------------------
print('\nE. month-window arithmetic')

WIN = fn('pnlGrowthMonthWindow')
ok(bool(WIN), 'pnlGrowthMonthWindow located')
# Pure index arithmetic on the month STRINGS - no Date parsing of 'YYYY-MM',
# which is the v9.71 timezone class.
ok('new Date(' in WIN and WIN.count('new Date(') == 1,
   'exactly one Date use - for "today", never for parsing a YYYY-MM string',
   WIN.count('new Date('))
ok("new Date(m" not in WIN and "new Date(String" not in WIN,
   'never parses a month string through Date')

harness = r'''
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

__WIN__

const now = new Date();
const curIdx = now.getFullYear() * 12 + now.getMonth();
const toStr = (i) => String(Math.floor(i / 12)) + '-' + String((i % 12) + 1).padStart(2, '0');
const lastComplete = toStr(curIdx - 1);
const thisMonth    = toStr(curIdx);

// -- 1. The window ends at LAST COMPLETE month, never the current one.
let w = pnlGrowthMonthWindow([], 12);
t('E1 window ends at last complete month', w.end, lastComplete);
t('E2 the current month is never listed as missing', w.missing.includes(thisMonth), false);
t('E3 an empty history reports all 12 as missing', [w.all.length, w.missing.length], [12, 12]);
t('E4 window start is 11 months before the end', w.start, toStr(curIdx - 12));

// -- 2. Gaps inside the window.
const have = [toStr(curIdx - 1), toStr(curIdx - 2), toStr(curIdx - 5)];
w = pnlGrowthMonthWindow(have, 12);
t('E5 loaded months are not reported missing',
  have.every(m => !w.missing.includes(m)), true);
t('E6 the gaps are exactly the window minus what is loaded',
  w.missing.length, 12 - have.length);
t('E7 inWindow lists only what is both loaded and in range',
  w.inWindow.slice().sort(), have.slice().sort());
t('E8 missing is ordered oldest first, so it reads as a pull list',
  w.missing.slice().sort().join() === w.missing.join(), true);

// -- 3. Months older than the window are separated, not called gaps.
const old1 = toStr(curIdx - 30);
w = pnlGrowthMonthWindow([old1, toStr(curIdx - 1)], 12);
t('E9  an older month is reported separately', w.older, [old1]);
t('E10 ...and is NOT counted as missing', w.missing.includes(old1), false);
t('E11 ...and is NOT counted as in-window', w.inWindow.includes(old1), false);

// -- 4. If somehow NEWER than last-complete exists, extend rather than
//       calling a real upload "extra".
w = pnlGrowthMonthWindow([thisMonth], 12);
t('E12 a month newer than last-complete extends the window', w.end, thisMonth);
t('E13 ...and is counted as loaded, not older', [w.inWindow, w.older], [[thisMonth], []]);

// -- 5. Full coverage.
const full = pnlGrowthMonthWindow([], 12).all;
w = pnlGrowthMonthWindow(full, 12);
t('E14 full coverage reports no gaps', w.missing, []);
t('E15 ...and no spurious older months', w.older, []);

// -- 6. Year boundary + span + junk input.
t('E16 December rolls to January cleanly',
  pnlGrowthMonthWindow(['2025-12', '2026-01'], 12).have, ['2025-12', '2026-01']);
t('E17 span is honoured', pnlGrowthMonthWindow([], 6).all.length, 6);
t('E18 default span is 12', pnlGrowthMonthWindow([]).all.length, 12);
t('E19 duplicates collapse', pnlGrowthMonthWindow([lastComplete, lastComplete]).have, [lastComplete]);
t('E20 junk + blanks are dropped without throwing',
  pnlGrowthMonthWindow([null, '', 'nope', undefined, lastComplete]).inWindow, [lastComplete]);
t('E21 every emitted month is a valid YYYY-MM',
  pnlGrowthMonthWindow([], 12).all.every(m => /^\d{4}-(0[1-9]|1[0-2])$/.test(m)), true);

console.log(JSON.stringify(out));
'''
harness = harness.replace('__WIN__', WIN)
hp = os.path.join(SP, 'test_v1093_window.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True)
if r.returncode != 0:
    print('  FAIL  window harness did not run:\n' + (r.stderr or '')[:2500]); F += 1; fails.append('harness')
else:
    try: rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  window harness unparseable: %s\n%s' % (e, r.stdout[:800])); F += 1; fails.append('harness parse'); rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


# -- F. The copied block leads with the gaps ------------------------------
print('\nF. the text leads with what he needs in Seller Central')

ok('MISSING SQP ASIN-view months' in TXT, 'names the missing months explicitly')
ok(TXT.index('MISSING') < TXT.index('Already loaded'),
   'the gaps come BEFORE the already-loaded list - that is the point')
ok('Full coverage' in TXT, 'says so plainly when there is nothing to pull')
ok('Brand Analytics' in TXT and 'ASIN view' in TXT,
   'carries the download path, so the block is self-contained')
ok('sqpLink' in TXT, 'carries the Seller Central URL')
ok('BRAND-view' in TXT and 'not used by this per-ASIN model' in TXT,
   'Brand-view months are listed but flagged as not feeding this model')
ok('SP Search Term months' in TXT, 'carries the SP coverage too')


print('\n' + '=' * 62)
print('  v10.93  PASS %d   FAIL %d' % (P, F))
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
