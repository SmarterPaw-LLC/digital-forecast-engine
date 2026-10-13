# -*- coding: utf-8 -*-
"""
v10.35 — Break-Even: product card from a row, and saved views.

Jason, items 2 and 3 of four:
  "i should be able to save the view on the break-even like the patter on other pages"
  "i should be able to open the product card if i click on a card button"

⚠ The card button is the interesting half. The Summary tab calls
pnlCardBtn(master_id), but Break-Even rows come out of SQL carrying ASIN and
SKU — there is no master_id on them. Resolving it is the whole job, and the
button must render NOTHING when nothing matches: a button that opens a blank
modal is worse than no button. Both directions asserted.

Saved views deliberately store a RECIPE, not a result set. The four assumptions
are query parameters injected into the params CTE, so applying a view has to
re-run the query rather than re-sort numbers that no longer match.
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
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
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
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m:
        raise SystemExit('FAIL: cannot find %s' % name)
    i = js.index('{', m.end() - 1)
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


# ═════════ A. wiring — nothing invented ═════════
print('\nA. wiring')

for i in ['be-view-btn', 'be-view-popup']:
    ok('id="%s"' % i in src, 'markup carries %s' % i)
# ⚠ Every control the snapshot reads must exist, or a saved view silently
# stores blanks. Same class as v10.34's id sweep.
snap = fn('breakevenSnapshotView')
for i in re.findall(r"[vc]\('([a-z-]+)'\)", snap):
    ok('id="%s"' % i in src, '  snapshot reads a real control: %s' % i)
ok('pnlCardBtn' in js, 'reuses the Summary tab card button')


# ═════════ B. behaviour ═════════
print('\nB. behaviour — the real sliced functions')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

let allProducts = [
  { master_id: 'SP-1', asin: 'B01', sp_sku: 'CF100' },
  { master_id: 'SP-2', asin: '',    sp_sku: 'CF200' },
];
function pnlCardBtn(mid) { return '<btn:' + mid + '>'; }

const EL = {};
const mk = (id, v) => EL[id] = { id, value: v };
const mkc = (id, c) => EL[id] = { id, checked: c };
const document = { getElementById: id => EL[id] || null,
                   addEventListener(){}, removeEventListener(){} };
let breakevenSortKey = 'Non-Ad Profit', breakevenSortDir = -1;
let breakevenSavedViews = {};
let _stored = null;
const localStorage = { getItem: () => _stored, setItem: (k, v) => { _stored = v; } };
let ranBreakeven = 0;
async function runBreakeven() { ranBreakeven++; }
function renderBreakeven() {}
function breakevenRenderViewPopup() {}
function breakevenCloseViewPopup() {}
function prompt() { return 'x'; }
function confirm() { return true; }

CARDBTN
SNAPSHOT
PERSIST
APPLY

// ═════ card button ═════
t('resolves master_id by ASIN',
  breakevenCardBtn({ ASIN: 'B01', SKU: 'whatever' }), ' <btn:SP-1>');
t('falls back to SP SKU when there is no ASIN',
  breakevenCardBtn({ ASIN: '', SKU: 'CF200' }), ' <btn:SP-2>');
// ⚠ A button that opens a blank modal is worse than no button.
t('renders NOTHING when nothing matches',
  breakevenCardBtn({ ASIN: 'B99', SKU: 'NOPE' }), '');
t('  and on an empty row', breakevenCardBtn({}), '');
t('ASIN wins over a SKU pointing elsewhere',
  breakevenCardBtn({ ASIN: 'B01', SKU: 'CF200' }), ' <btn:SP-1>');
let threw = false;
try { breakevenCardBtn({ ASIN: null, SKU: undefined }); } catch (e) { threw = true; }
t('null/undefined ids do not throw', threw, false);

// ═════ snapshot ═════
mk('be-win-days', '180'); mk('be-fin-rate', '0.12'); mk('be-soh-mo', '3.5');
mk('be-min-units', '40'); mk('be-search', ' spray ');
mkc('be-only-under', true); mkc('be-show-audit', false);
const snap = breakevenSnapshotView();
t('captures all four assumptions',
  [snap.winDays, snap.finRate, snap.sohMo, snap.minUnits], ['180', '0.12', '3.5', '40']);
t('  plus the display toggles', [snap.onlyUnder, snap.showAudit], [true, false]);
t('  and the sort', [snap.sortKey, snap.sortDir], ['Non-Ad Profit', -1]);
// ⚠ A view is a RECIPE. Storing rows would hand back numbers that are stale
// the moment the view is applied.
t('does NOT capture the result set', 'rows' in snap || 'breakevenRows' in snap, false);

// ═════ apply ═════
(async () => {
  breakevenSavedViews = { 'Blake monthly': {
    winDays: '365', finRate: '0.08', sohMo: '2', minUnits: '25',
    search: 'catnip', onlyUnder: false, showAudit: true,
    sortKey: 'Contribution %', sortDir: 1 } };
  await breakevenApplyView('Blake monthly');
  t('apply restores every assumption',
    [EL['be-win-days'].value, EL['be-fin-rate'].value, EL['be-soh-mo'].value, EL['be-min-units'].value],
    ['365', '0.08', '2', '25']);
  t('  the toggles', [EL['be-only-under'].checked, EL['be-show-audit'].checked], [false, true]);
  t('  the search', EL['be-search'].value, 'catnip');
  t('  and the sort', [breakevenSortKey, breakevenSortDir], ['Contribution %', 1]);
  // ⚠ The assumptions are QUERY params, so a stale result set would be wrong.
  t('applying RE-RUNS the query rather than re-sorting stale rows', ranBreakeven, 1);

  const before = ranBreakeven;
  await breakevenApplyView('no such view');
  t('an unknown view is a no-op', ranBreakeven, before);

  // A junk direction normalises rather than leaking through.
  breakevenSavedViews['junk'] = { sortKey: 'SKU', sortDir: 'up' };
  await breakevenApplyView('junk');
  t('a junk sort direction normalises to desc', breakevenSortDir, -1);

  // A view saved before a field existed must not blow up or wipe the control.
  EL['be-win-days'].value = '90';
  breakevenSavedViews['legacy'] = { sortKey: null, sortDir: -1 };
  await breakevenApplyView('legacy');
  t('a legacy view missing fields leaves them alone', EL['be-win-days'].value, '90');

  console.log('\n  ' + P + ' passed, ' + F + ' failed');
  if (F) process.exit(1);
})();
"""
harness = (harness
           .replace('CARDBTN', fn('breakevenCardBtn'))
           .replace('SNAPSHOT', fn('breakevenSnapshotView'))
           .replace('PERSIST', fn('breakevenPersistViews'))
           .replace('APPLY', fn('breakevenApplyView')))
tmp = os.path.join(tempfile.gettempdir(), 'test_v1035_be.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('break-even behaviour')


# ═════════ C. the card button is wired into the row render ═════════
print('\nC. row render')
rend = fn('renderBreakeven')
ok("c === 'Product Title'" in rend and 'breakevenCardBtn(r)' in rend,
   'the card button renders in the Product Title cell')
ok('${card}' in rend, '  and is actually emitted into the cell')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.35 — all green')
