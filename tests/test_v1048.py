# -*- coding: utf-8 -*-
r"""v10.48 — Amazon + Chewy fulfilment are FLAT per bundle, never BOM-summed.

Jason: "fulfillment amazon and fulfillment chewy are flat rate - they should
not update from BOM."

Two bugs with one cause. The visible one is a red BOM-mismatch chip on a cell
that can never legitimately be summed. The silent one is bigger: every
component's stored amazon_cogs already bakes in its own fulfillment_amazon, so
rolling a bundle's Amazon COGS up off the BOM charged the FBA fee once per
component. v6.27 fixed exactly this shape for shipping_cost on dtc_cogs and
nowhere else.

Section B drives the REAL sliced bundleCogsFromBom. Section C reproduces the
pre-v10.48 roll-up and proves it really did triple-charge.
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
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)

def arrow(name):
    """Slice `const <name> = (...) => { ... };` — bundleCogsFromBom is a closure
    inside renderCogsTbl, so the function-declaration slicer does not reach it."""
    a = js.index('const %s = (' % name)
    i = js.index('{', js.index('=>', a)); depth = 0
    while True:
        c = js[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return js[a:i + 1] + ';'
        i += 1

def constblock(name):
    a = js.index('const %s = ' % name)
    b = js.index('\n', js.index(';', a))
    return js[a:b]


# ══════════════ A. static — one declaration, no restated lists ══════════════
print('A. static — the flat set is declared once and drives every consumer')

ok('const COGS_FLAT_PER_BUNDLE = new Set(' in js,
   'the flat-per-bundle blocks are one declaration')
flat = constblock('COGS_FLAT_PER_BUNDLE')
for f in ['shipping_cost', 'fulfillment_amazon', 'fulfillment_chewy']:
    ok("'%s'" % f in flat, '  includes %s' % f)
ok("'fulfillment_dtc'" not in flat,
   '  and NOT fulfillment_dtc (3PL pick/pack, deliberately left per-unit)')

ok('const COGS_FLAT_IN_CHANNEL = {' in js,
   'the channel totals that bake in a flat block are declared once')
chan = js[js.index('const COGS_FLAT_IN_CHANNEL'): js.index('};', js.index('const COGS_FLAT_IN_CHANNEL'))]
ok("amazon_cogs: ['fulfillment_amazon']" in chan, '  amazon_cogs -> fulfillment_amazon')
ok("chewy_cogs:  ['fulfillment_chewy']" in chan, '  chewy_cogs  -> fulfillment_chewy')
ok("dtc_cogs:    ['shipping_cost']" in chan,     '  dtc_cogs    -> shipping_cost (the v6.27 fix)')

ok('new Set(COGS_BUILDING_BLOCKS.filter(f => !COGS_FLAT_PER_BUNDLE.has(f)))' in js,
   'BLOCK_BOM_FIELDS is derived, not restated')
ok(js.count("...COGS_BUILDING_BLOCKS.filter(f => !COGS_FLAT_PER_BUNDLE.has(f))") == 2,
   '  and so are the mismatch-flag and sync-all lists')

# The literal lists that used to carry the two fields must be gone, or the
# derivation above is decoration sitting next to a stale copy.
ok("'landed_cost','fulfillment_amazon','fulfillment_chewy','fulfillment_dtc','overhead_dtc','production_labor'" not in js,
   'no restated list still carries the flat fields')

ok('if (COGS_FLAT_PER_BUNDLE.has(channelField)) return null;' in js,
   'asking a flat block for a BOM roll-up returns null (no mismatch chip)')


# ══════════════ B. behaviour — the real sliced roll-up ══════════════
print('\nB. behaviour — the real bundleCogsFromBom')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + '  got ' + g + ' want ' + w); }
};

//<<BLOCKS>>
//<<FLATSET>>
//<<FLATCHAN>>

// A 3-component bundle. Every component carries the SAME $0.15 FBA fee and the
// SAME $0.03 Chewy fee, already baked into its channel totals:
//   amazon_cogs = landed + fulfillment_amazon + production_labor
//   chewy_cogs  = landed + fulfillment_chewy  + production_labor
//   dtc_cogs    = landed + overhead + fulfillment_dtc + shipping + labor
const C = (landed) => ({
  landed_cost: landed, production_labor: 0.10,
  fulfillment_amazon: 0.15, fulfillment_chewy: 0.03,
  fulfillment_dtc: 0.40, overhead_dtc: 0.05, shipping_cost: 2.00,
  amazon_cogs: landed + 0.15 + 0.10,
  chewy_cogs:  landed + 0.03 + 0.10,
  dtc_cogs:    landed + 0.05 + 0.40 + 2.00 + 0.10,
});

let cogsByMaster = {
  'C1': C(1.00), 'C2': C(2.00), 'C3': C(3.00),
  // The bundle's OWN flat charges: one parcel, one FBA fee, one Chewy fee.
  'B1': { fulfillment_amazon: 0.15, fulfillment_chewy: 0.03, shipping_cost: 2.00 },
  // A bundle with no flat values set at all.
  'B2': {},
};
let allBomData = {
  'B1': [{ component_master_id: 'C1', qty: 1 },
         { component_master_id: 'C2', qty: 1 },
         { component_master_id: 'C3', qty: 1 }],
  'B2': [{ component_master_id: 'C1', qty: 2 }],
  'B3': [{ component_master_id: 'C1', qty: 1 },
         { component_master_id: 'CX', qty: 1 }],   // CX has no COGS at all
};

//<<ROLLUP>>

// ── Amazon: the fee lands ONCE, not once per component ────────────────────
// components ex-fee: 1.10 + 2.10 + 3.10 = 6.30, plus the bundle's own 0.15
t('a 3-component bundle carries the FBA fee ONCE',
  bundleCogsFromBom('B1', 'amazon_cogs').total, 6.45);
t('  Chewy the same (6.30 + 0.03)',
  bundleCogsFromBom('B1', 'chewy_cogs').total, 6.33);
// components ex-shipping: 1.65 + 2.65 + 3.65 = 7.95, plus the bundle's 2.00
t('  and DTC still carries one parcel of shipping (v6.27 unchanged)',
  bundleCogsFromBom('B1', 'dtc_cogs').total, 9.65);

// ── blocks that genuinely roll up are untouched ───────────────────────────
t('landed_cost still sums straight off the BOM', bundleCogsFromBom('B1', 'landed_cost').total, 6.00);
t('production_labor too', bundleCogsFromBom('B1', 'production_labor').total, 0.30);
t('fulfillment_dtc too (left per-unit on purpose)',
  bundleCogsFromBom('B1', 'fulfillment_dtc').total, 1.20);

// ── a flat block has no roll-up to show ───────────────────────────────────
t('fulfillment_amazon has no BOM value', bundleCogsFromBom('B1', 'fulfillment_amazon'), null);
t('fulfillment_chewy has no BOM value',  bundleCogsFromBom('B1', 'fulfillment_chewy'), null);
t('shipping_cost has no BOM value',      bundleCogsFromBom('B1', 'shipping_cost'), null);

// ── qty multiplies the component part, never the flat part ────────────────
// 2 x (1.00 + 0.10) = 2.20, and B2 has no flat fee set -> contributes 0
t('qty scales components but the flat charge is not multiplied',
  bundleCogsFromBom('B2', 'amazon_cogs').total, 2.20);

// ── a missing component is still reported ─────────────────────────────────
const b3 = bundleCogsFromBom('B3', 'amazon_cogs');
t('a component with no COGS is counted as missing', b3.missingCount, 1);
t('  and the partial total excludes it', b3.total, 1.10);
t('  componentCount still reports the full BOM', b3.componentCount, 2);

// ── no BOM at all ─────────────────────────────────────────────────────────
t('a bundle with no BOM returns null', bundleCogsFromBom('NOPE', 'amazon_cogs'), null);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

for tok, body in [('BLOCKS',   constblock('COGS_BUILDING_BLOCKS') + ';'),
                  ('FLATSET',  constblock('COGS_FLAT_PER_BUNDLE') + ';'),
                  ('FLATCHAN', js[js.index('const COGS_FLAT_IN_CHANNEL'):
                                  js.index('};', js.index('const COGS_FLAT_IN_CHANNEL')) + 2]),
                  ('ROLLUP',   arrow('bundleCogsFromBom'))]:
    marker = '//<<%s>>' % tok
    if harness.count(marker) != 1:
        raise SystemExit('FAIL: placeholder %s appears %d times' % (marker, harness.count(marker)))
    harness = harness.replace(marker, body, 1)

tmp = os.path.join(tempfile.gettempdir(), 'test_v1048_bom.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('bundleCogsFromBom behaviour')


# ══════════════ C. the regression guard ══════════════
print('\nC. behaviour — the pre-v10.48 roll-up really did multiply the fee')

guard = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + '  got ' + JSON.stringify(got)); }
};
// Reproduce v10.47's roll-up rather than describe it.
const C = (landed) => ({ amazon_cogs: landed + 0.15 + 0.10, shipping_cost: 2.00 });
const cogsByMaster = { C1: C(1.00), C2: C(2.00), C3: C(3.00) };
const bom = [{ component_master_id: 'C1', qty: 1 },
             { component_master_id: 'C2', qty: 1 },
             { component_master_id: 'C3', qty: 1 }];

function oldRollup(channelField) {          // v6.27 .. v10.47
  let total = 0;
  for (const c of bom) {
    const comp = cogsByMaster[c.component_master_id];
    let compCogs = comp?.[channelField];
    if (compCogs == null) continue;
    if (channelField === 'dtc_cogs' && comp?.shipping_cost != null) compCogs -= Number(comp.shipping_cost);
    total += compCogs * (c.qty || 1);
  }
  return parseFloat(total.toFixed(2));
}

t('the old roll-up charged the $0.15 FBA fee three times', oldRollup('amazon_cogs'), 6.75);
t('  which is 0.30 above the one-fee answer', parseFloat((6.75 - 6.45).toFixed(2)), 0.30);
t('  i.e. exactly 2 extra fees on a 3-component bundle',
  parseFloat((0.30 / 0.15).toFixed(2)), 2);
// And the fee scales with component count, so a 6-pack was 5 fees over.
t('a 6-component bundle would have been 5 fees over',
  parseFloat((0.15 * (6 - 1)).toFixed(2)), 0.75);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
tmp2 = os.path.join(tempfile.gettempdir(), 'test_v1048_guard.js')
io.open(tmp2, 'w', encoding='utf-8', newline='').write(guard)
r2 = subprocess.run(['node', tmp2], capture_output=True, text=True, encoding='utf-8')
print(r2.stdout.rstrip())
if r2.returncode != 0:
    print(r2.stderr.rstrip()[:1200])
    fails.append('regression guard')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d static, %d sections): %s' % (F, len(fails), ', '.join(fails[:6])))
    sys.exit(1)
print('v10.48 — all green (%d static assertions + 2 behaviour sections)' % P)
