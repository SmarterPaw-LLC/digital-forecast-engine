# -*- coding: utf-8 -*-
"""v10.10 — Amazon FBA status fires off the reorder threshold, per region."""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)


def fn(name):
    a = js.index('function %s(' % name)
    i = js.index('{', a); depth = 0
    while True:
        c = js[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return js[a:i + 1]
        i += 1


REAL = '\n'.join([
    js[js.index('const AMZ_TIER_RANK'): js.index('\n', js.index('const AMZ_TIER_RANK'))],
    fn('amazonRegionsOf'), fn('amazonStatusOne'), fn('amazonStatusRollup'),
    fn('amazonRegionSuffix'), fn('getStatusLabelFor'),
])

static = [
    ('Amazon status no longer uses lead_time + safety_stock',
     "if (mode === 'amazon') return amazonStatusRollup(r).tier;" in js),
    ('  it uses the per-region reorder threshold',
     'const threshold = rv.reorder_threshold_days ?? 90;' in js),
    ('  and the SAME seasonal cover the reorder QUANTITY uses',
     'inventoryNeedBreakdown(rv, 90).amazon.meta' in js),
    ('Warehouse / In-house keep the supplier Reorder Point',
     'const rop    = lead + safety;' in js and 'r.lead_time   || 60' in js),
    ('the Amazon label carries a region suffix',
     'base + amazonRegionSuffix(amazonStatusRollup(r))' in js),
    ('products.lead_time_days is read as a product-level default',
     'inv?.lead_time_days ?? p.lead_time_days ?? 0' in js),
    ('  with ?? so a deliberate 0 is not swallowed',
     'inv?.safety_stock   ?? p.safety_stock   ?? 14' in js),
    ('  and the source of the number is recorded for the tooltip',
     "lead_time_src: inv?.lead_time_days != null ? 'region'" in js),
    ('the product card exposes supplier lead time',
     'id="pf-lead-time"' in RAW and 'id="pf-safety-stock"' in RAW),
    ('  loaded on open and saved on save',
     "getElementById('pf-lead-time')" in js and 'lead_time_days: (() =>' in js),
    ('  and the card says it does NOT drive Amazon FBA',
     'does NOT drive Amazon FBA' in RAW),
    ('the Amazon tooltip stops printing a phantom lead time',
     'Trigger: the per-region Amazon REORDER THRESHOLD' in js),
    ('  and the warehouse tooltip names where lead time came from',
     '(from ${leadSrc})' in js),
    ('the migration exists', os.path.exists(
        r'C:\Users\Jason\digital-forecast-engine\supabase_v10_10_product_lead_time.sql')),
]

HARNESS = r"""
// ── stubs ────────────────────────────────────────────────────────────────────
let NB = {};           // master_id|region -> amazon.meta
function inventoryNeedBreakdown(rv) {
  const k = rv.master_id + '|' + (rv.region || 'US');
  if (!(k in NB)) throw new Error('no breakdown for ' + k);
  return { amazon: { meta: NB[k] } };
}
function ipEffectiveInbound(rv) { return rv.fba_inbound || 0; }
function regionViewOf(r, region) {
  if (r._byRegion && r._byRegion[region]) return r._byRegion[region];
  if ((r.region || 'US') === region) return r;
  return null;
}
function getStatusFor(r, mode) { return amazonStatusRollup(r).tier; }   // amazon only, here

__REAL__

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const reset = () => { NB = {}; };
const reg = (mid, region, o) => Object.assign(
  { master_id: mid, region, asin: 'B0TEST', fba_available: 0, fba_inbound: 0, reorder_threshold_days: 45 }, o);
const meta = (vel, dos) => ({ vel, dos });

console.log('\n== A. THE BUG: Jason\u2019s row \u2014 FBA cover 62d, threshold 45d ==');
// Screenshot: FBA stock 7,672 at 124.0u/day -> DOS 62d. Old math did
// lead 60 + safety 14 = ROP 74 -> slack -12 -> "Send to FBA" (red).
// The supplier lead time has nothing to do with shipping stock we already own.
reset();
const row = reg('SP-1', 'US', { fba_available: 7672, reorder_threshold_days: 45 });
NB['SP-1|US'] = meta(124.0, 62);
let roll = amazonStatusRollup(row);
t('slack is cover \u2212 threshold, not cover \u2212 (lead+safety)', Math.round(roll.perRegion[0].slack) === 17,
  roll.perRegion[0].slack);
t('  so the tier is FBA Soon, not Send to FBA', roll.tier === 'order-soon', roll.tier);
t('  REGRESSION GUARD: the old ROP math would have said order-now',
  (62 - (60 + 14)) <= 0);
t('  and the label names the region',
  getStatusLabelFor(row, 'amazon', roll.tier) === '\ud83d\udfe1 FBA Soon \u00b7 US',
  getStatusLabelFor(row, 'amazon', roll.tier));

console.log('\n== B. The threshold really is what moves the tier ==');
for (const [thr, want] of [[90, 'order-now'], [62, 'order-now'], [45, 'order-soon'], [20, 'plan'], [1, 'ok']]) {
  reset();
  const rr = reg('SP-1', 'US', { fba_available: 7672, reorder_threshold_days: thr });
  NB['SP-1|US'] = meta(124.0, 62);
  const got = amazonStatusRollup(rr).tier;
  t(`threshold ${String(thr).padStart(2)}d with 62d cover -> ${want}`, got === want, got);
}

console.log('\n== C. Per-region: a pooled row takes the WORST region ==');
reset();
const pooled = {
  master_id: 'SP-2', region: 'US+CA', asin: 'B0X',
  _byRegion: {
    US: reg('SP-2', 'US', { fba_available: 9000, reorder_threshold_days: 45 }),
    CA: reg('SP-2', 'CA', { fba_available: 50,   reorder_threshold_days: 45 }),
  },
};
NB['SP-2|US'] = meta(10, 900);   // flush
NB['SP-2|CA'] = meta(10, 5);     // nearly empty
roll = amazonStatusRollup(pooled);
t('regions enumerated from _byRegion',
  JSON.stringify(roll.allRegions) === JSON.stringify(['US', 'CA']), roll.allRegions);
t('row tier = the worst region', roll.tier === 'order-now', roll.tier);
t('  \u26a0 a pooled SUM would have read OK and hidden the empty region',
  (9000 + 50) / 20 > 45);
t('  and the label names only the region that needs action',
  getStatusLabelFor(pooled, 'amazon', roll.tier) === '\ud83d\udd34 Send to FBA \u00b7 CA',
  getStatusLabelFor(pooled, 'amazon', roll.tier));

console.log('\n== D. "All" when every region needs it ==');
reset();
NB['SP-2|US'] = meta(10, 5);
NB['SP-2|CA'] = meta(10, 5);
roll = amazonStatusRollup(pooled);
t('both regions at the worst tier', roll.regions.length === 2);
t('  label collapses to \u00b7 All',
  getStatusLabelFor(pooled, 'amazon', roll.tier) === '\ud83d\udd34 Send to FBA \u00b7 All',
  getStatusLabelFor(pooled, 'amazon', roll.tier));

console.log('\n== E. Per-region thresholds are honoured independently ==');
// Jason's settings: US 45 / CA 45 / EU 90.
reset();
const three = {
  master_id: 'SP-3', region: 'US+CA+EU/UK', asin: 'B0Y',
  _byRegion: {
    US:      reg('SP-3', 'US',      { fba_available: 100, reorder_threshold_days: 45 }),
    CA:      reg('SP-3', 'CA',      { fba_available: 100, reorder_threshold_days: 45 }),
    'EU/UK': reg('SP-3', 'EU/UK',   { fba_available: 100, reorder_threshold_days: 90 }),
  },
};
NB['SP-3|US']    = meta(1, 70);   // 70 - 45 = 25 -> order-soon
NB['SP-3|CA']    = meta(1, 70);   // same
NB['SP-3|EU/UK'] = meta(1, 70);   // 70 - 90 = -20 -> order-now
roll = amazonStatusRollup(three);
t('identical cover, different thresholds -> different tiers',
  roll.perRegion.map(p => p.tier).join() === 'order-soon,order-soon,order-now',
  roll.perRegion.map(p => p.tier));
t('  worst is the EU/UK row', roll.tier === 'order-now' && roll.regions.join() === 'EU/UK', roll.regions);
t('  and NOT "All", because only one region is at that tier',
  getStatusLabelFor(three, 'amazon', roll.tier) === '\ud83d\udd34 Send to FBA \u00b7 EU/UK',
  getStatusLabelFor(three, 'amazon', roll.tier));

console.log('\n== F. Suffix only on actionable tiers ==');
reset();
NB['SP-3|US'] = meta(1, 900); NB['SP-3|CA'] = meta(1, 900); NB['SP-3|EU/UK'] = meta(1, 900);
roll = amazonStatusRollup(three);
t('everything comfortable -> ok', roll.tier === 'ok');
t('  no region suffix on OK (it would be noise in a scanned column)',
  getStatusLabelFor(three, 'amazon', roll.tier) === '🟢 FBA OK',
  getStatusLabelFor(three, 'amazon', roll.tier));

console.log('\n== G. No velocity / no cover ==');
reset();
const noVel = reg('SP-4', 'US', { fba_available: 500 });
NB['SP-4|US'] = meta(0, null);
t('stock but no demand -> ok', amazonStatusRollup(noVel).tier === 'ok');
reset();
const empty = reg('SP-5', 'US', { fba_available: 0 });
NB['SP-5|US'] = meta(0, null);
t('no stock and no demand -> nodata', amazonStatusRollup(empty).tier === 'nodata');
reset();
const deep = reg('SP-6', 'US', { fba_available: 999999 });
NB['SP-6|US'] = meta(1, null);   // cover outlasts the look-ahead
t('cover beyond the look-ahead -> ok', amazonStatusRollup(deep).tier === 'ok');

console.log('\n== H. nodata never outranks a real signal ==');
reset();
const mixed = {
  master_id: 'SP-7', region: 'US+CA', asin: 'B0Z',
  _byRegion: { US: reg('SP-7','US',{ fba_available: 0 }), CA: reg('SP-7','CA',{ fba_available: 10 }) },
};
NB['SP-7|US'] = meta(0, null);    // nodata
NB['SP-7|CA'] = meta(10, 5);      // order-now
roll = amazonStatusRollup(mixed);
t('a nodata region does not mask an order-now one', roll.tier === 'order-now', roll.tier);
t('  and only the real one is named', roll.regions.join() === 'CA', roll.regions);

console.log('\n== I. Region enumeration edge cases ==');
t('single-region record', JSON.stringify(amazonRegionsOf({ region: 'CA' })) === '["CA"]');
t('pooled string with no _byRegion splits on +',
  JSON.stringify(amazonRegionsOf({ region: 'US+CA' })) === '["US","CA"]');
t('missing region defaults to US', JSON.stringify(amazonRegionsOf({})) === '["US"]');
t('null record does not throw', JSON.stringify(amazonRegionsOf(null)) === '["US"]');

console.log('\n== J. A broken breakdown cannot take the row down ==');
reset();   // NB empty -> inventoryNeedBreakdown throws
let threw = false, out;
try { out = amazonStatusRollup(reg('SP-9', 'US', { fba_available: 100 })); } catch { threw = true; }
t('a throwing breakdown is caught', !threw);
t('  and still yields a usable tier', out && out.tier === 'ok', out && out.tier);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

static_js = '\n'.join("t(%r, %s);" % (n, 'true' if v else 'false') for n, v in static)
out = (HARNESS.replace('__REAL__', REAL)
              .replace("console.log('\\n== A.",
                       "console.log('\\n== 0. Static assertions against the shipped source ==');\n"
                       + static_js + "\nconsole.log('\\n== A.", 1))
p = os.path.join(SP, 'test_v1010.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars' % len(out))
sys.exit(subprocess.call(['node', p]))
