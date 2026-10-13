# -*- coding: utf-8 -*-
r"""v10.46 — category visibility: nothing can be hidden invisibly.

Jason, twice: "i don't know why buds jar is being hidden ... it wasn't one of
the hidden sub-categories" -> "'jar' is not one of the categories hidden".

v10.45 fixed ONE mechanism (a trailing space). It did not fix the CLASS. This
suite drives the real sliced engine against every variant that renders
identically on screen but compares as a different string, plus the two
structural guarantees that make the whole class non-recurring:

  * a value with no checkbox can never hide a product
  * the panel that answers "why did this vanish" does not truncate the answer
"""
import io, os, re, subprocess, sys, tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond:
        P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)

def fn(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m:
        raise SystemExit('FAIL: cannot slice function %s' % name)
    a = m.start() + 1
    i = js.index('{', a); depth = 0
    while True:
        c = js[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return js[a:i + 1]
        i += 1

def constline(name):
    m = re.search(r'^const %s\s*=.*$' % re.escape(name), js, re.M)
    if not m:
        raise SystemExit('FAIL: cannot find const %s' % name)
    return m.group(0)


# ══════════════ A. static — the normaliser really is harder ══════════════
print('A. static — normalisation + the universe guard')

norm = fn('catVisNorm')
ok('_CATVIS_INVISIBLE' in norm, 'catVisNorm strips the invisible characters')
ok('_CATVIS_SPACES' in norm,    '  and normalises unicode spaces')
ok(r'\s+' in norm,              '  and collapses internal runs')
ok('.trim()' in norm,           '  and still trims')

inv = constline('_CATVIS_INVISIBLE')
for cp in ['200B', '200D', 'FEFF', '2060', '00AD']:
    ok(cp.lower() in inv.lower(), '  covers U+%s' % cp)

ok('toLowerCase' in fn('catVisMatchKey'),
   "the comparison key folds case ('Jar' and 'jar' are not two categories)")

sethas = fn('catVisSetHas')
ok('catVisMatchKey' in sethas, 'catVisSetHas compares on the match key')

p_fn = fn('catVisPass')
ok('uni.cats.has(catVisMatchKey(cat))' in p_fn and 'uni.subs.has(catVisMatchKey(sub))' in p_fn,
   'the predicate only hides values that HAVE a checkbox')
ok('catVisUniverse()' in p_fn, '  resolved through the cached universe')

ok('_catVisUniv = null' in fn('catVisInvalidate'),
   'catVisInvalidate drops the universe cache too')

ded = fn('_catVisDedupe')
ok('catVisMatchKey' in ded, 'the universe de-dupes on the match key, not the display string')
ok('catVisAllCats' in js and '_catVisDedupe(' in fn('catVisAllCats'),
   '  and both universes go through it')
ok('_catVisDedupe(' in fn('catVisAllSubcats'), '  (sub-categories too)')


# ══════════════ B. static — the answer is no longer truncated ══════════════
print('\nB. static — the Active filters panel does not cut the answer off')

afr = fn('activeFiltersRenderControls')
ok('white-space:normal' in afr and 'word-break:break-word' in afr,
   'the value wraps instead of ellipsing')
ok('text-overflow:ellipsis' not in afr, '  the ellipsis is gone')
ok("'<span title=\"'" in afr or 'span title=' in afr,
   '  and it carries the full value as a tooltip')

ok('catVisSummaryNamed(pageKey)' in js,
   'the gear panel summary NAMES the hidden values')

ctrl = fn('catVisRenderControls')
ok('var(--sp-orange)' in ctrl and 'border-left:3px solid' in ctrl,
   'an unchecked row is visually marked (one off row in 33 was invisible)')


# ══════════════ C. static — the Products diagnostic ══════════════
print('\nC. static — the Products count line names the cause')

ok(js.count('opts.ignoreCatVis') == 1,
   'exactly one caller may skip category visibility')
ok("if (!(opts && opts.ignoreCatVis) && !catVisPass('products', p)) return false;" in js,
   '  and it is the predicate itself that honours the opt-out')
ok('hidden by category visibility' in js, 'the count line names the filter')
ok('catVisNameList([...subs, ...cats].sort(), 4)' in js,
   '  and names the sub-categories responsible')
ok("pcEl.style.color = cvNote ? 'var(--sp-orange)' : 'var(--text3)'" in js,
   '  and goes orange only when something is actually being removed')


# ══════════════ D. behaviour — the real sliced engine ══════════════
print('\nD. behaviour — every variant that renders identically on screen')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + '  got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)); }
};

const ZWSP = '\u200B', NBSP = '\u00A0';

// Four rows that render as three visually distinct names. 'Jar', 'Jar<ZWSP>'
// and 'jar' are ONE category to a human and three different strings to a Set.
let allCategories = [
  { id: 1, category: 'Blends',     subcategory: 'Jar' + ZWSP },   // <- invisible
  { id: 2, category: 'Blends',     subcategory: 'Jar'        },
  { id: 3, category: 'Blends',     subcategory: 'jar'        },   // <- case
  { id: 4, category: 'Clamshells', subcategory: 'Cigar' + NBSP + 'Box' },
  { id: 5, category: 'Clamshells', subcategory: 'Cigar  Box' },   // <- double space
  { id: 6, category: 'Other',      subcategory: 'Apparel'    },
];
let catVisConfig = {};
let _catVisCache = {};
let _catVisIdMap = null;
let _catVisUniv  = null;
const CATVIS_GLOBAL = '_global';
const _catVisSuppressed = new Set();
function catVisInvalidate() { _catVisCache = {}; _catVisIdMap = null; _catVisUniv = null; }

//<<INVISIBLE>>
//<<SPACES>>
//<<NORM>>
//<<MATCHKEY>>
//<<DEDUPE>>
//<<ALLCATS>>
//<<ALLSUBS>>
//<<UNIVERSE>>
//<<SETHAS>>
//<<IDMAP>>
//<<RESOLVED>>
//<<PASS>>
//<<HIDDEN>>
//<<NAMELIST>>
//<<SUMMARY>>

// ── the universe collapses to what a human sees ────────────────────────────
t('six category rows render as three distinct sub-categories',
  catVisAllSubcats(), ['Apparel', 'Cigar Box', 'Jar']);
t('  and two distinct categories plus one',
  catVisAllCats(), ['Blends', 'Clamshells', 'Other']);

// ── Jason's case: "Jar" is checked, so nothing on any Jar variant hides ────
catVisConfig['products'] = { cats: null, subcats: ['Jar', 'Cigar Box'] };
catVisInvalidate();
t('the zero-width variant is VISIBLE when Jar is checked',
  catVisPass('products', { master_id: 'buds-jar', category_id: 1 }), true);
t('  the clean variant too', catVisPass('products', { category_id: 2 }), true);
t('  and the lower-case variant', catVisPass('products', { category_id: 3 }), true);
t('the NBSP variant is VISIBLE when "Cigar Box" is checked',
  catVisPass('products', { category_id: 4 }), true);
t('  and the double-space variant', catVisPass('products', { category_id: 5 }), true);
t('a genuinely unchecked sub-category STILL hides (the fix is not a no-op)',
  catVisPass('products', { category_id: 6 }), false);

// ── the stored set can itself carry the junk ──────────────────────────────
catVisConfig['products'] = { cats: null, subcats: ['Jar' + ZWSP, 'Cigar  Box'] };
catVisInvalidate();
t('a junk value in the STORED set still matches a clean product',
  catVisPass('products', { category_id: 2 }), true);
t('  and a clean product on the other junk value', catVisPass('products', { category_id: 4 }), true);

// ── a value with no checkbox can never hide anything ──────────────────────
catVisConfig['products'] = { cats: null, subcats: ['Jar'] };
catVisInvalidate();
t('a records row whose sub-category is not in the universe at all is VISIBLE',
  catVisPass('products', { category: 'Blends', subcategory: 'Tins' }), true);
t('  same for a category outside the universe',
  (catVisConfig['products'] = { cats: ['Blends'], subcats: null }, catVisInvalidate(),
   catVisPass('products', { category: 'Ghost', subcategory: '' })), true);
t('  while one that IS in the universe and unchecked still hides',
  catVisPass('products', { category: 'Other', subcategory: 'Apparel' }), false);

// ── the names reported are the names the picker shows ─────────────────────
catVisConfig['products'] = { cats: null, subcats: ['Jar'] };
catVisInvalidate();
t('the hidden list names exactly the unchecked rows',
  catVisHiddenCount('products').subNames, ['Apparel', 'Cigar Box']);
t('  and the summary says which', catVisSummaryNamed('products'),
  'hiding sub Apparel, Cigar Box');

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

for tok, body in [('INVISIBLE', constline('_CATVIS_INVISIBLE')),
                  ('SPACES',    constline('_CATVIS_SPACES')),
                  ('NORM',      fn('catVisNorm')),
                  ('MATCHKEY',  fn('catVisMatchKey')),
                  ('DEDUPE',    fn('_catVisDedupe')),
                  ('ALLCATS',   fn('catVisAllCats')),
                  ('ALLSUBS',   fn('catVisAllSubcats')),
                  ('UNIVERSE',  fn('catVisUniverse')),
                  ('SETHAS',    fn('catVisSetHas')),
                  ('IDMAP',     fn('catVisIdMap')),
                  ('RESOLVED',  fn('catVisResolved')),
                  ('PASS',      fn('catVisPass')),
                  ('HIDDEN',    fn('catVisHiddenCount')),
                  ('NAMELIST',  fn('catVisNameList')),
                  ('SUMMARY',   fn('catVisSummaryNamed'))]:
    marker = '//<<%s>>' % tok
    if harness.count(marker) != 1:
        raise SystemExit('FAIL: placeholder %s appears %d times' % (marker, harness.count(marker)))
    harness = harness.replace(marker, body, 1)

tmp = os.path.join(tempfile.gettempdir(), 'test_v1046_catvis.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('catVis behaviour')


# ══════════════ E. the regression guard ══════════════
print('\nE. behaviour — the pre-v10.46 predicate really did hide it')

guard = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label); }
};
// Reproduce v10.45's predicate rather than describe it. Without this the fix
// could be asserting something that was never broken.
const ZWSP = '\u200B';
const oldNorm = (v) => String(v == null ? '' : v).trim();          // v10.45
const oldSetHas = (set, value) => {
  if (!set) return true;
  if (set.has(value)) return true;
  for (const v of set) if (oldNorm(v) === value) return true;
  return false;
};
const IDMAP = new Map([[1, { category: 'Blends', subcategory: 'Jar' + ZWSP }]]);
const CHECKED = new Set(['Jar']);           // what the operator ticked

function oldPass(obj) {
  let cat = oldNorm(obj.category), sub = oldNorm(obj.subcategory);
  if ((!cat || !sub) && obj.category_id != null) {
    const row = IDMAP.get(obj.category_id);
    if (row) { cat = cat || oldNorm(row.category); sub = sub || oldNorm(row.subcategory); }
  }
  if (!cat && !sub) return true;
  if (CHECKED && sub && !oldSetHas(CHECKED, sub)) return false;
  return true;
}
t('v10.45 trim() does NOT strip a zero-width space',
  oldNorm('Jar' + ZWSP).length, 4);
t('  so the v10.45 predicate HID a product whose sub-category read as checked',
  oldPass({ master_id: 'buds-jar', category_id: 1 }), false);
t('  and it is unrecoverable: both rows render as the same four characters',
  'Jar' + ZWSP === 'Jar', false);

// And the out-of-universe case: v10.45 hid on a value with no checkbox at all.
t('v10.45 also hid a value that had no checkbox to untick',
  oldPass({ category: 'Blends', subcategory: 'Tins' }), false);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1046_guard.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(guard)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip()[:1200])
    fails.append('regression guard')


# ══════════════ F. behaviour — the Products opt-out ══════════════
print('\nF. behaviour — prodRowMatchesFilters honours ignoreCatVis')

prod = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + '  got ' + JSON.stringify(got)); }
};
let topProductFilterId = null;
let allCategories = [{ id: 1, category: 'Blends', subcategory: 'Tins' }];
let CATVIS_CALLS = 0;
function catVisPass(pageKey, p) { CATVIS_CALLS++; return false; }   // hide everything

//<<PRODMATCH>>

const CTX = { q: '', brand: '', filt: '', cat: '',
              needsReview: () => false, lifecycleByMaster: {} };
const ROW = { master_id: 'SP-1', title: 'Buds Jar', category_id: 1, active: true };

t('category visibility hides the row by default', prodRowMatchesFilters(ROW, CTX), false);
const before = CATVIS_CALLS;
t('ignoreCatVis lets the same row through',
  prodRowMatchesFilters(ROW, CTX, { ignoreCatVis: true }), true);
t('  without even consulting the predicate', CATVIS_CALLS, before);
t('and every OTHER filter still applies under the opt-out',
  prodRowMatchesFilters(ROW, { ...CTX, brand: 'Doggijuana' }, { ignoreCatVis: true }), false);
t('  search too',
  prodRowMatchesFilters(ROW, { ...CTX, q: 'zzz' }, { ignoreCatVis: true }), false);
t('  and a matching search still passes',
  prodRowMatchesFilters(ROW, { ...CTX, q: 'bud' }, { ignoreCatVis: true }), true);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
prod = prod.replace('//<<PRODMATCH>>', fn('prodRowMatchesFilters'), 1)
tmp3 = os.path.join(tempfile.gettempdir(), 'test_v1046_prod.js')
io.open(tmp3, 'w', encoding='utf-8', newline='').write(prod)
r3 = subprocess.run(['node', tmp3], capture_output=True, text=True, encoding='utf-8')
print(r3.stdout.rstrip())
if r3.returncode != 0:
    print(r3.stderr.rstrip()[:1200])
    fails.append('products opt-out')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d static, %d sections): %s' % (F, len(fails), ', '.join(fails[:6])))
    sys.exit(1)
print('v10.46 — all green (%d static assertions + 3 behaviour sections)' % P)
