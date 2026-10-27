# -*- coding: utf-8 -*-
"""
v11.00 — autoship LTV in the Chewy break-even model.

Jason: "can we build in the ltv in our model?"

The existing model prices the FIRST order plus whatever recurring autoship
already landed inside the window. It does not price FUTURE reorders, so a SKU
sitting just under break-even on first purchase can still pay over a
subscriber's life. v11.00 prices that life as a SECOND lens alongside the
first-purchase figure, never in place of it.

  attach     = autoship sign-ups / ad-driven units
  multiplier = 1 + attach x (ltvOrders - 1) x unitsPerOrder
  BE (LTV)   = list price / (contribution x multiplier)

⚠ THE ASSERTION THAT EARNS ITS KEEP is the REGRESSION GUARD: every
first-purchase field — net, contribution, beRoas, beAcos, directRoas,
realisedRoas, realisedSales, headroom, gmPct, ourRev, vendorContrib, verdict —
must come back BYTE-IDENTICAL with the LTV inputs present and absent. v11.00 is
purely additive, and the only way to make that a checkable claim rather than
something I verified by reading is to run both shapes and diff them.

⚠ THE SECOND ONE: the multiplier must NEVER touch the realised side. Realised
ROAS stays the retail dollars Chewy actually attributed. Lifetime value lowers
the BAR; it does not manufacture revenue that has not happened. A model that
multiplied both sides would look plausible and silently flatter every SKU.

⚠ A SKU's own attach rate is only trusted at or above the Min units threshold.
Below it, 2 sign-ups on 4 units reads as a 50% attach rate and would halve that
SKU's break-even off noise, so the fleet rate is used and the cell says so.
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


def ok(cond, label, got=None):
    if cond:
        print('  ok    ' + label)
    else:
        print('  FAIL  ' + label + ('' if got is None else '  got: %r' % (got,)))
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


def reg_segment(name):
    i = js.index('const %s = [' % name)
    return js[i: js.index(chr(10) + '];', i)]


# ═════════ A. the five columns are registered, keyed AND exportable ═════════
print('\nA. static — registry, body cells, CSV, vocabulary')

BE = reg_segment('CHEWY_BE_COLUMNS')
LTV_COLS = [
    ('attachPct',       'Autoship Attach %', 'autoship_attach_pct'),
    ('ltvMult',         'LTV mult',          'ltv_multiplier'),
    ('ltvContribution', 'LTV GM $/u',        'ltv_contribution_per_unit'),
    ('beRoasLtv',       'BE ROAS (LTV)',     'break_even_roas_ltv_pct'),
    ('headroomLtv',     'LTV Headroom',      'headroom_ltv_pts'),
]
for key, label, csvname in LTV_COLS:
    ok("{ key: '%s'" % key in BE, 'A  %s is a registry column' % key)
    ok("label: '%s'" % label in BE or 'label: %r' % label in BE
       or ("label: '" + label.replace("$", "$") + "'") in BE,
       'A  %s carries the label %s' % (key, label))
    ok("name: '%s'" % csvname in BE, 'A  %s exports as %s' % (key, csvname))

# ⚠ v10.54 made the body a KEYED map so header and body cannot drift. A
# registry column with no cell renders the fallback em-dash on EVERY row:
# present in the header, blank in the table. test_v1042 caught exactly that on
# the first cut of v11.00, so it is pinned here too, close to the change.
i = js.index('const CELLS = {', js.index('function renderChewyBreakeven'))
cells = js[i: js.index(chr(10) + '        };', i)]
for key, _, _ in LTV_COLS:
    ok(re.search(r'\b%s:' % re.escape(key), cells) is not None,
       'A  %s has a keyed body cell (not the fallback em-dash)' % key)

# CSV orders stay contiguous 1..N across the whole registry (the v10.80 rule).
orders = sorted(int(o) for o in re.findall(r"order: (\d+)", BE))
ok(orders == list(range(1, len(orders) + 1)),
   'A  CSV positions are still contiguous 1..%d' % len(orders), orders[-5:])

# One label one measure (the v10.53 rule) — every new label is declared.
VOCAB = js[js.index('const CHEWY_MEASURE_VOCAB'):]
VOCAB = VOCAB[:VOCAB.index(chr(10) + '};')]
for _, label, _ in LTV_COLS:
    ok("'%s':" % label in VOCAB, 'A  %s is declared in CHEWY_MEASURE_VOCAB' % label)

# The two columns worth reading by default; the other three are the working-out.
DEF = js[js.index("    cols: () => CHEWY_BE_COLUMNS"):]
DEF = DEF[:DEF.index('render:')]
ok("'beRoasLtv'" in DEF and "'headroomLtv'" in DEF,
   'A  beRoasLtv + headroomLtv are in the default visible set')
ok("'attachPct'" not in DEF and "'ltvMult'" not in DEF and "'ltvContribution'" not in DEF,
   'A  the three working-out columns are NOT in the default set')
# "Not hidden" means VISIBLE, so a new key shows for anyone carrying a hidden
# Set unless it is added to that Set once (the v10.80 / v10.82 shape).
ok("CHEWY_BE_COLS_HIDDEN_V1100" in js, 'A  flag-guarded hide migration exists')
ok("chewyBeColsMigratedV1100" in js, 'A  and it is flag-guarded so an un-hide sticks')
MIG = js[js.index('CHEWY_BE_COLS_HIDDEN_V1100'):]
MIG = MIG[:MIG.index('v10.82')]
ok("'beRoasLtv'" not in MIG and "'headroomLtv'" not in MIG,
   'A  the migration does NOT hide the two default-visible columns')


# ═════════ B. controls, readout, filter ═════════
print('\nB. static — the controls and the state readout')

ok('id="chpnl-be-ltv-orders"' in src, 'B  LTV orders/signup input exists')
ok('id="chpnl-be-ltv-upo"' in src, 'B  Units/order input exists')
ok('id="chpnl-be-ltv-state"' in src, 'B  state-readout host exists')
ok('value="ltv-flip"' in src, 'B  "Flips to clear on LTV" is a Show-filter option')
ok("quick === 'ltv-flip'" in js, 'B  and the filter is wired in the row loop')

# ⚠ v10.99: clamping on every keystroke means clearing the box to retype "1.3"
# snaps it to 1 under the cursor. State is clamped on input; the visible field
# is normalised on COMMIT only.
for el in ('chpnl-be-ltv-orders', 'chpnl-be-ltv-upo'):
    m = re.search(r'id="%s"[^>]*' % el, src)
    tag = m.group(0) if m else ''
    ok('oninput="chewyBeLtvOnInput()"' in tag, 'B  %s reads state on input' % el)
    ok('onblur="chewyBeLtvOnCommit()"' in tag, 'B  %s normalises the field on blur' % el)
COMMIT = fn('chewyBeLtvOnCommit')
ONINPUT = fn('chewyBeLtvOnInput')
ok('.value =' in COMMIT, 'B  commit rewrites the field')
ok('.value =' not in ONINPUT,
   'B  REGRESSION GUARD: input does NOT rewrite the field under the cursor')

# A literal uppercase-U escape is not a JS escape at all (the v10.36 trap)
# and in raw markup it renders as six characters (the v10.20 trap). Neither
# may come back.
#
# WARNING Scanned against LIVE CODE only. index.html carries an explanatory
# comment (v4.189) that QUOTES the bad escape to document a past bug, and a
# raw scan flags that comment. Strip line comments first, then REQUIRE the
# warning comment to survive so nobody 'optimises' the documentation away -
# the v10.93 guard-the-guard pattern.
_BS = chr(92)
_UPAT = re.escape(_BS) + 'U0001[0-9a-fA-F]{4}'
_live = re.sub(r'//[^\n]*', '', js)
ok(re.search(_UPAT, _live) is None,
   'B  no literal uppercase-U escape survives in LIVE code')
ok(re.search(_UPAT, js) is not None,
   'B  and the comment documenting that trap is still there (guard the guard)')
# One glyph one concept (rule #2): the repeat arrow already means
# "AutoShip Subscription", so the flip marker must not reuse it.
ok(js.count('\U0001F501') + src.count('\U0001F501') <= 2,
   'B  the flip marker does not reuse the AutoShip glyph',
   src.count('\U0001F501'))

# The assumptions ride along in the export context line, so an archived CSV
# can be re-derived (the v10.79 rule that a file must name its own scope).
ok('LTV assumptions' in js, 'B  CSV context line records the LTV assumptions')


# ═════════ C. behaviour — the real sliced function ═════════
print('\nC. behaviour — chewyBreakevenEcon (the real function)')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok    ' + label); }
  else { F++; console.log('  FAIL  ' + label + ' - got ' + g + ', want ' + w); }
};
const near = (label, got, want, tol) => {
  if (got != null && Math.abs(got - want) <= (tol || 0.005)) { P++; console.log('  ok    ' + label); }
  else { F++; console.log('  FAIL  ' + label + ' - got ' + got + ', want ~' + want); }
};

ECON

// ── The worked example, hand-checkable end to end.
//   wholesale $4.50/each, 26.5% standing allowances, COGS $1.00
//   net to us    = 4.50 x 0.735            = 3.3075
//   contribution = 3.3075 - 1.00           = 2.3075
//   list price   = 9.99
//   BE ROAS      = 9.99 / 2.3075           = 433.0%
// LTV layer, Jason's own fitted assumptions:
//   attach 0.12, ltvOrders 1.17, unitsPerOrder 1.14
//   multiplier   = 1 + 0.12 x 0.17 x 1.14  = 1.023256
//   LTV GM/u     = 2.3075 x 1.023256       = 2.36117
//   BE ROAS LTV  = 9.99 / 2.36117          = 423.1%
const base = {
  wholesale: 4.50, cogs: 1.00, standingPct: 26.5, listPrice: 9.99,
  spend: 100, directSales: 500, autoshipSales: 0,
  directUnits: 1000, autoshipSignups: 120,
  ltvOrders: 1.17, unitsPerOrder: 1.14,
  fleetAttachRate: 0.05, attachMinUnits: 50,
};
let e = chewyBreakevenEcon(base);
near('contribution (first purchase) = net - cogs', e.contribution, 2.3075);
near('attach rate = signups / ad units', e.attachRate, 0.12);
near('ltv multiplier = 1 + attach x (orders-1) x units/order', e.ltvMult, 1.023256, 1e-5);
near('LTV contribution = contribution x multiplier', e.ltvContribution, 2.36117, 1e-4);
near('BE ROAS (first purchase)', e.beRoas, 432.94, 0.05);
near('BE ROAS (LTV)', e.beRoasLtv, 423.10, 0.05);
t('BE ROAS (LTV) is at or below the first-purchase BE ROAS', e.beRoasLtv <= e.beRoas, true);

// ⚠ THE INVARIANT: the multiplier moves the BAR, never the realised side.
near('realised ROAS is NOT multiplied', e.realisedRoas, 500);
t('realised sales are NOT multiplied', e.realisedSales, 500);
near('LTV headroom = realised - BE(LTV)', e.headroomLtv, 500 - 423.10, 0.05);
near('first-purchase headroom is unchanged', e.headroom, 500 - 432.94, 0.05);

// ── ltvOrders = 1 means "no recurring", so the lens is OFF by identity.
e = chewyBreakevenEcon(Object.assign({}, base, { ltvOrders: 1 }));
t('ltvOrders = 1 -> multiplier exactly 1', e.ltvMult, 1);
t('ltvOrders = 1 -> BE(LTV) equals BE', e.beRoasLtv === e.beRoas, true);
t('ltvOrders = 1 -> headroom(LTV) equals headroom', e.headroomLtv === e.headroom, true);

// ── Zero attach also collapses the lens, independent of the assumptions.
e = chewyBreakevenEcon(Object.assign({}, base, { autoshipSignups: 0 }));
t('zero sign-ups -> attach 0', e.attachRate, 0);
t('zero sign-ups -> multiplier 1', e.ltvMult, 1);
t('zero sign-ups -> BE(LTV) equals BE', e.beRoasLtv === e.beRoas, true);

// ── A richer attach / longer life moves the bar further, monotonically.
const beAt = (attachUnits, orders) => chewyBreakevenEcon(Object.assign({}, base,
  { autoshipSignups: attachUnits, ltvOrders: orders })).beRoasLtv;
t('higher attach lowers the LTV bar', beAt(300, 1.17) < beAt(120, 1.17), true);
t('longer subscriber life lowers the LTV bar', beAt(120, 2.0) < beAt(120, 1.17), true);
t('a 1.0 life never lowers it', beAt(300, 1.0) === e.beRoas, true);

// ── Attach confidence: below Min units the SKU's OWN rate is NOT trusted.
//   2 sign-ups on 4 units would read as 50% attach and halve this SKU's
//   break-even off pure noise, so the fleet rate is used instead.
let low = chewyBreakevenEcon(Object.assign({}, base,
  { directUnits: 4, autoshipSignups: 2, fleetAttachRate: 0.05, attachMinUnits: 50 }));
t('below Min units, attachOwn is null', low.attachOwn, null);
near('below Min units, the FLEET rate is used', low.attachRate, 0.05);
let hi = chewyBreakevenEcon(Object.assign({}, base,
  { directUnits: 50, autoshipSignups: 25, fleetAttachRate: 0.05, attachMinUnits: 50 }));
near("at Min units, the SKU's own rate is used", hi.attachOwn, 0.5);
near('and attachRate follows it', hi.attachRate, 0.5);

// ── flipsOnLtv: does the ANSWER change, or only the number?
//   BE 432.94, BE(LTV) 423.10. A realised ROAS between the two flips.
const at = (roas) => chewyBreakevenEcon(Object.assign({}, base,
  { spend: 100, directSales: roas, autoshipSales: 0 }));
t('realised 500 (clears both) does not flip', at(500).flipsOnLtv, false);
t('realised 428 (between the two bars) FLIPS', at(428).flipsOnLtv, true);
t('realised 300 (clears neither) does not flip', at(300).flipsOnLtv, false);
t('a flipped row has negative headroom and positive LTV headroom',
  [at(428).headroom < 0, at(428).headroomLtv >= 0], [true, true]);

// ── Degenerate shapes must not throw or leak NaN.
const shapes = [
  { label: 'no wholesale', o: { wholesale: null } },
  { label: 'no cogs', o: { cogs: null } },
  { label: 'no list price', o: { listPrice: null } },
  { label: 'contribution <= 0', o: { wholesale: 1.20, cogs: 1.00 } },
  { label: 'no ad units', o: { directUnits: 0, autoshipSignups: 0 } },
  { label: 'no spend', o: { spend: 0 } },
  { label: 'ltv assumptions absent', o: { ltvOrders: undefined, unitsPerOrder: undefined } },
  { label: 'junk assumptions', o: { ltvOrders: NaN, unitsPerOrder: 'x' } },
  { label: 'no fleet rate and below min units',
    o: { directUnits: 1, autoshipSignups: 0, fleetAttachRate: undefined } },
];
for (const s of shapes) {
  let r = null, threw = false;
  try { r = chewyBreakevenEcon(Object.assign({}, base, s.o)); } catch (err) { threw = true; }
  const leaked = r && [r.ltvMult, r.ltvContribution, r.beRoasLtv, r.headroomLtv]
    .some(v => typeof v === 'number' && !isFinite(v));
  t('degenerate: ' + s.label + ' - no throw, no NaN/Infinity', [threw, !!leaked], [false, false]);
}
// contribution <= 0 keeps its own verdict and a NULL break-even on BOTH lenses:
// "you need 4,000% ROAS" reads like a target and this is not one.
let never = chewyBreakevenEcon(Object.assign({}, base, { wholesale: 1.20, cogs: 1.00 }));
t('contribution <= 0 -> verdict never', never.verdict, 'never');
t('contribution <= 0 -> BE(LTV) is null, not a huge number', never.beRoasLtv, null);
t('contribution <= 0 -> never flips', never.flipsOnLtv, false);

// ══ THE REGRESSION GUARD ══════════════════════════════════════════════════
// v11.00 is purely additive. Every first-purchase field must come back
// BYTE-IDENTICAL with the LTV inputs present and absent. Running both shapes
// and diffing them is what makes that a checkable claim rather than something
// verified by reading the diff.
const FIRST_PURCHASE_FIELDS = ['a', 'net', 'contribution', 'listPrice', 'beRoas',
  'beAcos', 'actualAcos', 'directRoas', 'realisedRoas', 'realisedSales', 'gmPct',
  'ourRev', 'vendorContrib', 'headroom', 'verdict'];
const scenarios = [
  { wholesale: 4.50, cogs: 1.00, standingPct: 26.5, listPrice: 9.99, spend: 100,
    directSales: 500, autoshipSales: 32, directUnits: 1000, autoshipSignups: 120 },
  { wholesale: 2.89, cogs: 1.51, standingPct: 26.5, listPrice: 5.99, spend: 751,
    directSales: 2546, autoshipSales: 0, directUnits: 425, autoshipSignups: 41 },
  { wholesale: 1.20, cogs: 1.00, standingPct: 26.5, listPrice: 9.99, spend: 10,
    directSales: 5, autoshipSales: 0, directUnits: 2, autoshipSignups: 0 },
  { wholesale: null, cogs: null, standingPct: 0, listPrice: null, spend: 0,
    directSales: 0, autoshipSales: 0, directUnits: 0, autoshipSignups: 0 },
];
let identical = true, firstDiff = null;
for (const sc of scenarios) {
  const without = chewyBreakevenEcon(sc);
  const withLtv = chewyBreakevenEcon(Object.assign({}, sc, {
    ltvOrders: 1.17, unitsPerOrder: 1.14, fleetAttachRate: 0.118, attachMinUnits: 25,
  }));
  for (const k of FIRST_PURCHASE_FIELDS) {
    if (JSON.stringify(without[k]) !== JSON.stringify(withLtv[k])) {
      identical = false;
      if (!firstDiff) firstDiff = k + ': ' + JSON.stringify(without[k]) + ' vs ' + JSON.stringify(withLtv[k]);
    }
  }
}
t('REGRESSION GUARD: all 15 first-purchase fields are byte-identical with and '
  + 'without the LTV inputs' + (firstDiff ? ' [' + firstDiff + ']' : ''), identical, true);

// And the mirror of it: with the LTV inputs ABSENT, the LTV fields are null
// rather than silently defaulting to some multiplier.
const bare = chewyBreakevenEcon(scenarios[0]);
t('LTV inputs absent -> ltvMult null', bare.ltvMult, null);
t('LTV inputs absent -> beRoasLtv null', bare.beRoasLtv, null);
t('LTV inputs absent -> flipsOnLtv false', bare.flipsOnLtv, false);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

code = harness.replace('ECON', fn('chewyBreakevenEcon'))
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
    fh.write(code)
    path = fh.name
try:
    r = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8')
    print(r.stdout.rstrip())
    if r.stderr.strip():
        print(r.stderr.strip()[:2000])
    ok(r.returncode == 0, 'C  node behaviour suite passed')
finally:
    os.unlink(path)


# ═════════ D. the assumption helpers, driven for real ═════════
print('\nD. behaviour — the assumption clamps')

h2 = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok    ' + label); }
  else { F++; console.log('  FAIL  ' + label + ' - got ' + g + ', want ' + w); }
};

// Minimal DOM + storage stubs: the helpers read the input, fall back to
// localStorage, then to the fitted default, and clamp the result.
let FIELD = { 'chpnl-be-ltv-orders': '', 'chpnl-be-ltv-upo': '' };
let STORE = {};
globalThis.document = { getElementById: (id) =>
  (id in FIELD) ? { get value() { return FIELD[id]; }, set value(v) { FIELD[id] = String(v); }, dataset: {} } : null };
globalThis.localStorage = {
  getItem: (k) => (k in STORE ? STORE[k] : null),
  setItem: (k, v) => { STORE[k] = String(v); },
};

__CONSTS__
__FN_ORDERS__
__FN_UPO__

t('empty field + empty storage -> fitted default', chewyBeLtvOrders(), 1.17);
t('empty field + empty storage -> fitted units/order', chewyBeLtvUnitsPerOrder(), 1.14);

FIELD['chpnl-be-ltv-orders'] = '1.40';
t('a typed value is read', chewyBeLtvOrders(), 1.40);
FIELD['chpnl-be-ltv-orders'] = '0.2';
t('below 1 clamps to 1 (a sign-up is always at least one order)', chewyBeLtvOrders(), 1);
FIELD['chpnl-be-ltv-orders'] = '999';
t('above 10 clamps to 10', chewyBeLtvOrders(), 10);
FIELD['chpnl-be-ltv-orders'] = 'abc';
t('junk falls back to the default', chewyBeLtvOrders(), 1.17);
FIELD['chpnl-be-ltv-orders'] = '';
STORE['chewyBeLtvOrders'] = '1.33';
t('empty field reads the saved value', chewyBeLtvOrders(), 1.33);

FIELD['chpnl-be-ltv-upo'] = '0';
t('units/order floors above zero (never a zero multiplier basis)',
  chewyBeLtvUnitsPerOrder() > 0, true);
FIELD['chpnl-be-ltv-upo'] = '2.5';
t('a typed units/order is read', chewyBeLtvUnitsPerOrder(), 2.5);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

consts = '\n'.join(
    re.search(r'^const %s = .*?;$' % k, js, re.M).group(0)
    for k in ('CHEWY_BE_LTV_ORDERS_DEFAULT', 'CHEWY_BE_LTV_UPO_DEFAULT'))
# WARNING Distinct bracketed tokens, NOT bare words. The first substitution
# inserts text containing the word ORDERS (CHEWY_BE_LTV_ORDERS_DEFAULT), so a
# later .replace('ORDERS', ...) matched INSIDE it and corrupted the harness
# into "const CHEWY_BE_LTV_function chewyBeLtvOrders() {". The v10.53
# wrong-haystack class, in a test.
code2 = (h2.replace('__CONSTS__', consts)
           .replace('__FN_ORDERS__', fn('chewyBeLtvOrders'))
           .replace('__FN_UPO__', fn('chewyBeLtvUnitsPerOrder')))
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
    fh.write(code2)
    path2 = fh.name
try:
    r2 = subprocess.run(['node', path2], capture_output=True, text=True, encoding='utf-8')
    print(r2.stdout.rstrip())
    if r2.stderr.strip():
        print(r2.stderr.strip()[:2000])
    ok(r2.returncode == 0, 'D  node clamp suite passed')
finally:
    os.unlink(path2)


# ═════════ E. the renderer wiring ═════════
print('\nE. static — renderer wiring')

REND = fn('renderChewyBreakeven')
ok('chewyBeLtvOrders()' in REND, 'E  renderer reads the orders assumption')
ok('chewyBeLtvUnitsPerOrder()' in REND, 'E  renderer reads the units/order assumption')
ok('chewyBeLtvRestore' in REND, 'E  renderer restores saved assumptions into the inputs')
ok('fleetAttach' in REND, 'E  renderer computes a fleet attach rate')
# The fleet rate must come from THIS window's own aggregate, not a constant, or
# narrowing the window would leave it stale.
m = re.search(r'let fleetSignups = 0, fleetAdUnits = 0;(.*?)const fleetAttach', REND, re.S)
ok(m is not None and 'bySku.values()' in m.group(1),
   'E  the fleet rate is summed over the window aggregate, not hardcoded')
ok('ltvOrders, unitsPerOrder: ltvUpo' in REND, 'E  the assumptions reach the econ call')
ok('fleetAttachRate: fleetAttach' in REND, 'E  and so does the fleet rate')
# attachMinUnits reuses the Min units control: one number governing both
# "dim this row" and "trust this row's own attach rate".
ok('attachMinUnits: Math.max(1, minUnits)' in REND,
   'E  attach confidence reuses the Min units control')
for f in ('beRoasLtv: e.beRoasLtv', 'headroomLtv: e.headroomLtv', 'flipsOnLtv: e.flipsOnLtv',
          'attachRate: e.attachRate', 'ltvMult: e.ltvMult'):
    ok(f in REND, 'E  row carries %s' % f.split(':')[0])

# ⚠ The readout's actionable half is the COUNT OF SKUS WHOSE ANSWER CHANGES,
# not the average multiplier (the v10.99 lesson: naming the state without
# naming the number that proves it leaves the reader guessing).
RO = REND[REND.index("getElementById('chpnl-be-ltv-state')"):]
RO = RO[:RO.index('gaps panel')]
ok('flip' in RO.lower(), 'E  readout names the flip count')
ok('spend-weighted' in RO or 'Math.max(r.spend' in RO,
   'E  the headline multiplier is spend-weighted, so one tiny SKU cannot swing it')
ok('ltvOrders <= 1.0001' in RO,
   'E  readout says so plainly when the lens is OFF rather than crying wolf')

print('\n' + '=' * 60)
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v11.00 — all green')
