# -*- coding: utf-8 -*-
"""
v10.15 — Cost to Chewy: the gaps panel names a count; now it SHOWS the rows.

Jason: "i have no way of seeing what the unfound skus are."

The panel said "35 SKUs are not in the uploaded catalog" and stopped there.
Every bullet is now a button that filters the table to exactly those rows,
and the counts are computed off the PRE-filter row set so the panel stays a
stable index of every gap while you are looking at one of them.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(os.path.dirname(HERE), 'index.html')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)

fails = []
def ok(cond, label):
    if cond:
        print('  ok  ' + label)
    else:
        print('  FAIL ' + label)
        fails.append(label)


def fn(name):
    for pat in (r'\nfunction %s\s*\(' % re.escape(name),
                r'\nasync function %s\s*\(' % re.escape(name)):
        m = re.search(pat, js)
        if m:
            break
    else:
        raise SystemExit('FAIL: cannot find %s' % name)
    k = m.end() - 1
    pdepth = 0
    while k < len(js):
        if js[k] == '(':
            pdepth += 1
        elif js[k] == ')':
            pdepth -= 1
            if pdepth == 0:
                break
        k += 1
    i = js.index('{', k)
    depth, j = 0, i
    while j < len(js):
        if js[j] == '{':
            depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1]


# ═════════════════ A. static assertions ═════════════════
print('\nA. static — the wiring exists and points the right way')

GAP_KINDS = ['no-catalog', 'no-case-qty', 'unknown-uom', 'no-cost', 'no-cogs']
for k in GAP_KINDS:
    ok(('<option value="gap:%s">' % k) in src,
       'Show dropdown offers gap:%s' % k)

# The pre-existing options must survive — a gap filter is additive, not a swap.
ok('<option value="gaps">' in src, 'the any-gap option still exists')
ok('<option value="priced">' in src, 'the priced option still exists')
ok('<option value="losing">' in src, 'the losing option still exists')
ok('<option value="under">' in src, 'the under-target option still exists')

# Counts must read allRows. Reading `rows` is the bug this release fixes:
# the panel would collapse to the one gap being viewed.
for k, var in [('no-catalog', 'gNoCatalog'), ('no-case-qty', 'gNoCase'),
               ('unknown-uom', 'gBadUom'), ('no-cost', 'gNoCost'), ('no-cogs', 'gNoCogs')]:
    ok(re.search(r'const %s\s*=\s*allRows\.filter' % var, js) is not None,
       '%s counts off allRows, not the filtered set' % var)
ok(len(re.findall(r'=\s*rows\.filter\(r => r\.gap ===', js)) == 0,
   'no gap bucket still counts off the post-filter rows')

# One handler, defined once.
ok(len(re.findall(r'\nfunction chewyPnlCostShowGap\s*\(', js)) == 1,
   'chewyPnlCostShowGap defined exactly once')
ok(len(re.findall(r'chewyPnlCostShowGap\(', src)) >= 2,
   'chewyPnlCostShowGap is actually wired to the chips')

# The dead end is gone.
ok('see the console warning from the upload for the list' not in src,
   'the "see the console warning" dead end is gone')
ok('unmatchedCatalogRows' in js,
   'unmatched catalog rows are captured so they can be listed inline')

# allRows is pushed BEFORE the quick filters, or the panel loses rows the
# active filter excluded — which is the whole point.
mPush = re.search(r'allRows\.push\(row\);', js)
mQuick = re.search(r"if \(quick === 'losing'\)", js)
ok(mPush is not None and mQuick is not None and mPush.start() < mQuick.start(),
   'allRows.push happens BEFORE the quick-filter chain')

ok("quick.startsWith('gap:')" in js, 'the gap: prefix is handled in the filter chain')


# ═════════════════ B. the filter chain, lifted verbatim ═════════════════
print('\nB. behaviour — the real filter chain, sliced out of the shipped file')

mChain = re.search(
    r"(allRows\.push\(row\);.*?rows\.push\(row\);)", js, re.S)
if not mChain:
    raise SystemExit('FAIL: cannot slice the quick-filter chain')
chain = mChain.group(1)
# Guard: the slice must be small. A runaway match would silently test nothing.
ok(len(chain) < 700, 'filter chain slice is tight (%d chars)' % len(chain))

FIXTURE = """
const FIXTURE = [
  { id:'a', gap:'no-catalog',  verdict:'losing' },
  { id:'b', gap:'no-catalog',  verdict:'ok' },
  { id:'c', gap:'no-case-qty', verdict:'ok' },
  { id:'d', gap:'no-case-qty', verdict:'ok' },
  { id:'e', gap:'no-case-qty', verdict:'ok' },
  { id:'f', gap:'unknown-uom', verdict:'ok' },
  { id:'g', gap:'no-cost',     verdict:'ok' },
  { id:'h', gap:'no-cogs',     verdict:'under-target' },
  { id:'i', gap:null,          verdict:'ok' },
  { id:'j', gap:null,          verdict:'losing' },
  { id:'k', gap:null,          verdict:'under-target' },
];
function run(quick) {
  const allRows = [], rows = [];
  for (const row of FIXTURE) {
    CHAIN
  }
  return { allRows, rows };
}
"""

harness = FIXTURE.replace('CHAIN', chain) + r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + '\n        got  ' + g + '\n        want ' + w); }
};
const ids = rs => rs.map(r => r.id);

// allRows is the whole universe no matter what the quick filter says —
// that is what keeps the gaps panel a stable index.
for (const q of ['', 'losing', 'under', 'gaps', 'priced',
                 'gap:no-catalog', 'gap:no-case-qty', 'gap:unknown-uom',
                 'gap:no-cost', 'gap:no-cogs']) {
  t('allRows is the full set under quick=' + JSON.stringify(q),
    run(q).allRows.length, 11);
}

// Each gap filter selects exactly its own rows.
t('gap:no-catalog  -> a,b',   ids(run('gap:no-catalog').rows),  ['a','b']);
t('gap:no-case-qty -> c,d,e', ids(run('gap:no-case-qty').rows), ['c','d','e']);
t('gap:unknown-uom -> f',     ids(run('gap:unknown-uom').rows),  ['f']);
t('gap:no-cost     -> g',     ids(run('gap:no-cost').rows),      ['g']);
t('gap:no-cogs     -> h',     ids(run('gap:no-cogs').rows),      ['h']);

// The counts the panel prints must equal what clicking the chip shows.
// If these ever diverge the chip is a lie.
const all = run('').allRows;
for (const k of ['no-catalog','no-case-qty','unknown-uom','no-cost','no-cogs']) {
  t('panel count matches the filtered table for ' + k,
    all.filter(r => r.gap === k).length, run('gap:' + k).rows.length);
}

// Pre-existing filters are untouched by the if -> else-if rewrite.
t('no filter -> everything',      ids(run('').rows).length, 11);
t('gaps  -> every gap row',       ids(run('gaps').rows),   ['a','b','c','d','e','f','g','h']);
t('priced -> only gap-free rows', ids(run('priced').rows), ['i','j','k']);
t('losing -> verdict losing',     ids(run('losing').rows), ['a','j']);
t('under  -> verdict under',      ids(run('under').rows),  ['h','k']);

// gaps == the union of the five per-gap filters, with no overlap. A row that
// landed in two buckets, or in none, would mean a gap kind went unnamed.
const union = [].concat(...['no-catalog','no-case-qty','unknown-uom','no-cost','no-cogs']
  .map(k => ids(run('gap:' + k).rows)));
t('per-gap filters partition the any-gap set', union.sort(), ids(run('gaps').rows).sort());

// An unknown gap kind selects nothing rather than everything — a typo in a
// chip must not silently show the whole table as if it were one gap.
t('gap:bogus -> empty', ids(run('gap:bogus').rows), []);

// ── regression guard: the pre-v10.15 panel counted off the FILTERED rows,
// so clicking into one gap erased every other bullet and there was no way
// back. Reproduce that and assert it really did collapse.
const OLD = (quick) => {
  const r = run(quick).rows;
  return ['no-catalog','no-case-qty','unknown-uom','no-cost','no-cogs']
    .filter(k => r.filter(x => x.gap === k).length).length;
};
const NEW = (quick) => {
  const a = run(quick).allRows;
  return ['no-catalog','no-case-qty','unknown-uom','no-cost','no-cogs']
    .filter(k => a.filter(x => x.gap === k).length).length;
};
t('OLD: viewing one gap collapsed the panel to 1 bullet', OLD('gap:no-catalog'), 1);
t('NEW: viewing one gap still lists all 5 bullets',       NEW('gap:no-catalog'), 5);
t('OLD and NEW agree when no gap filter is active', OLD(''), NEW(''));

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

tmp = os.path.join(tempfile.gettempdir(), 'test_v1015_chain.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('filter-chain behaviour')


# ═════════════════ C. the chip handler, sliced ═════════════════
print('\nC. behaviour — chewyPnlCostShowGap (the real function)')

handler = fn('chewyPnlCostShowGap')
h2 = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  if (String(got) === String(want)) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + got + ', want ' + want); }
};

let renders = 0;
let SEL = { value: '' };
const document = {
  getElementById: (id) => id === 'chpnl-cost-filter' ? SEL
    : id === 'chpnl-cost-row-count' ? { scrollIntoView() {} } : null,
};
function renderChewyPnlCost() { renders++; }

HANDLER

// Picking a gap sets the dropdown and repaints.
SEL.value = ''; renders = 0;
chewyPnlCostShowGap('no-catalog');
t('sets the dropdown to gap:no-catalog', SEL.value, 'gap:no-catalog');
t('re-renders once', renders, 1);

// Clicking the SAME gap again clears it — the chip is its own undo.
chewyPnlCostShowGap('no-catalog');
t('clicking the active gap clears the filter', SEL.value, '');
t('re-renders again', renders, 2);

// Switching straight from one gap to another does not require a clear first.
SEL.value = 'gap:no-cogs';
chewyPnlCostShowGap('no-case-qty');
t('switches directly between gaps', SEL.value, 'gap:no-case-qty');

// Clicking a gap while a NON-gap filter is active replaces it rather than
// silently composing into something the panel never claimed.
SEL.value = 'losing';
chewyPnlCostShowGap('no-cost');
t('replaces a non-gap filter', SEL.value, 'gap:no-cost');

// A missing dropdown must not throw — the Cost tab may not be mounted.
SEL = null;
const docNull = { getElementById: () => null };
let threw = false;
try { (function(document){ @@CALL@@ })(docNull); } catch (e) { threw = true; }
t('no throw when the dropdown is absent', threw, false);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
h2 = h2.replace('@@CALL@@', handler + ' chewyPnlCostShowGap("no-cogs");')
h2 = h2.replace('HANDLER', handler)
h2 = h2.replace('HANDLER', handler)

tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1015_handler.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(h2)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip())
    fails.append('chewyPnlCostShowGap behaviour')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.15 — all green')
