# -*- coding: utf-8 -*-
"""v10.5 — "Dashboard actuals" reports actuals. Drives the REAL sliced functions."""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)


def fn(name):
    """Slice a top-level `function name(...) { ... }` by brace balance."""
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
    fn('ipChannelLagDays'),
    fn('invChewyVelActual'),
    fn('ipCompareChannelMatches'),
    fn('ipCompareDashboard90d'),
    fn('eventVelocityBasis'),
])

# --- the pre-v10.5 actual-mode branch, reproduced verbatim as a regression guard
LEGACY = r"""
function legacyActual90d(prod, channel) {
  const mid = prod.master_id;
  const rows = salesData[mid] || [];
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 90);
  let sum = 0;
  for (const r of rows) {
    const d = new Date(r.week_start);
    if (isNaN(d.getTime()) || d < cutoff) continue;
    if (!ipCompareChannelMatches(r.channel, channel)) continue;
    sum += Number(r.units_ordered || 0);
  }
  if (channel === 'chewy' && sum === 0) return getChewyFcUnits(mid, 90, prod.region || 'US');
  return Math.round(sum);
}
"""

static = [
    ('the actual-mode branch no longer calls getChewyFcUnits',
     "if (channel === 'chewy' && sum === 0) return getChewyFcUnits" not in js),
    ('  and the stale "no consumer-level history" comment is gone',
     'no consumer-level history on `sales_weekly`' not in js),
    ('actual mode parses dates LOCALLY (v9.71 rule), not via new Date(str)',
     'const d = parseLocalDate(r.week_start);   // v9.71' in js),
    ('invChewyVelActual exists next to its three siblings',
     'function invChewyVelActual(r)' in js
     and js.index('function invWalmartVel') < js.index('function invChewyVelActual')),
    ('  and it anchors to the channel lag, not to today',
     "ipChannelLagDays('chewy')" in js),
    ('eventVelocityBasis prefers Chewy actuals, forecast only as fallback',
     'invChewyVelActual(r) : null;' in js and 'if (av != null) return av;' in js),
    ('the compare header surfaces a lag note', 'lagNote' in js and 'window ends' in js),
    ('chewy actuals really do land in salesData as channel=chewy',
     "channel:        'chewy'," in js),
]

HARNESS = r"""
// ── stubs ────────────────────────────────────────────────────────────────────
let salesData = {};
let inventoryEvents = [];
const records = [];
let _velMemo = new Map();
let _ipChanLagCache = null;
let FORECAST_CALLS = 0;
function getChewyFcUnits(mid, days) { FORECAST_CALLS++; return 9000; }  // absurd on purpose
function invAmazonVel()  { return 4; }
function invShopifyVel() { return 2; }
function inventoryNeedBreakdown() { return {}; }
function parseLocalDate(s) {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s));
  if (!m) { const d = new Date(s); return isNaN(d.getTime()) ? null : d; }
  return new Date(+m[1], +m[2] - 1, +m[3]);
}
const document = { getElementById: () => ({ value: '30' }) };
const IP_VEL_FRESH_DAYS = 14;

__REAL__
__LEGACY__

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const ymd = (daysAgo) => {
  const d = new Date(Date.now() - daysAgo * 864e5);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
};
const reset = (data) => { salesData = data; _velMemo = new Map(); _ipChanLagCache = null; FORECAST_CALLS = 0; };

const PROD = { master_id: 'SP-1', region: 'US' };

// Jason's real shape: Chewy reports ~60 days behind. 100u/wk for the 13 weeks
// BEFORE that anchor, then nothing (because nothing has been reported yet).
const CHEWY_LAGGED = {
  'SP-1': [
    ...Array.from({ length: 13 }, (_, i) => ({ channel: 'chewy', region: 'US', week_start: ymd(60 + i * 7), units_ordered: 100 })),
    { channel: 'amazon_us', region: 'US', week_start: ymd(7),  units_ordered: 50 },
    { channel: 'amazon_us', region: 'US', week_start: ymd(14), units_ordered: 50 },
  ],
};

console.log('\n== A. THE BUG: "Dashboard actuals" was returning Chewy\u2019s FORECAST ==');
// A deeper lag: nothing reported inside the trailing 90 REAL days at all.
// This is the state that actually tripped the old forecast fallback (sum===0).
const CHEWY_DEEP_LAG = {
  'SP-1': [
    ...Array.from({ length: 13 }, (_, i) => ({ channel: 'chewy', region: 'US', week_start: ymd(120 + i * 7), units_ordered: 100 })),
    { channel: 'amazon_us', region: 'US', week_start: ymd(7),  units_ordered: 50 },
    { channel: 'amazon_us', region: 'US', week_start: ymd(14), units_ordered: 50 },
  ],
};

reset(CHEWY_DEEP_LAG);
const legacyChewy = legacyActual90d(PROD, 'chewy');
t('pre-v10.5 returned the forecast figure (9000), not actuals', legacyChewy === 9000, legacyChewy);
t('  because its today-anchored window caught 0 reported weeks', FORECAST_CALLS === 1, FORECAST_CALLS);

reset(CHEWY_DEEP_LAG);
const fixedDeep = ipCompareDashboard90d(PROD, 'chewy', 'actual');
t('v10.5 returns REAL Chewy sell-through instead', fixedDeep === 1300, fixedDeep);
t('  and never touches the forecast', FORECAST_CALLS === 0, FORECAST_CALLS);

console.log('\n== A2. The quieter half: a ~2-month lag silently UNDERSTATED actuals ==');
// The forecast fallback only fired when the sum hit exactly 0 (lag > 90d). At
// Chewy's typical ~2-month lag the old code returned a real-looking number that
// was only the partial overlap with a today-anchored window \u2014 arguably worse,
// because nothing flagged it as incomplete.
reset(CHEWY_LAGGED);
const legacyPartial = legacyActual90d(PROD, 'chewy');
t('pre-v10.5 caught only the 5 weeks overlapping today\u2019s 90d window', legacyPartial === 500, legacyPartial);
reset(CHEWY_LAGGED);
const got = ipCompareDashboard90d(PROD, 'chewy', 'actual');
t('v10.5 counts all 13 reported weeks (anchored to Chewy\u2019s latest)', got === 1300, got);
t('  a 2.6\u00d7 correction on the same underlying data', got === legacyPartial * 2.6, got);

console.log('\n== B. A genuine zero stays zero (no forecast rescue) ==');
reset({ 'SP-1': [{ channel: 'amazon_us', region: 'US', week_start: ymd(7), units_ordered: 50 }] });
const z = ipCompareDashboard90d(PROD, 'chewy', 'actual');
t('no Chewy rows at all \u2192 0, not 9000', z === 0, z);
t('  forecast still untouched', FORECAST_CALLS === 0, FORECAST_CALLS);

console.log('\n== C. Fresh channels are unaffected (today-anchored, as before) ==');
reset(CHEWY_LAGGED);
const amz = ipCompareDashboard90d(PROD, 'amazon_us', 'actual');
t('Amazon US sums its own 90d window', amz === 100, amz);
reset(CHEWY_LAGGED);
const amzAll = ipCompareDashboard90d(PROD, 'amazon_all', 'actual');
t('amazon_all matches every Amazon marketplace', amzAll === 100, amzAll);
reset(CHEWY_LAGGED);
const shop = ipCompareDashboard90d(PROD, 'shopify', 'actual');
t('Shopify with no rows reads 0', shop === 0, shop);

console.log('\n== D. Aggregate scopes stay anchored to TODAY ==');
// One shared anchor across channels with different lags would misreport all of
// them, so warehouse/total must NOT inherit Chewy's 60-day shift.
reset(CHEWY_LAGGED);
const wh = ipCompareDashboard90d(PROD, 'warehouse', 'actual');
// warehouse/total match EVERY channel: amazon 2\u00d750, plus the 5 Chewy weeks that
// fall inside a TODAY-anchored 90d window = 600.
t('warehouse counts only what landed in the last 90 real days', wh === 600, wh);
t('  it does NOT inherit Chewy\u2019s 60-day anchor shift', wh !== 1400, wh);
reset(CHEWY_LAGGED);
t('  total behaves identically to warehouse (v7.64 alias)',
  ipCompareDashboard90d(PROD, 'total', 'actual') === 600);

console.log('\n== E. Window boundaries ==');
reset({ 'SP-1': [
  { channel: 'shopify', region: 'US', week_start: ymd(0),  units_ordered: 7 },
  { channel: 'shopify', region: 'US', week_start: ymd(89), units_ordered: 11 },
  { channel: 'shopify', region: 'US', week_start: ymd(91), units_ordered: 999 },
] });
const edge = ipCompareDashboard90d(PROD, 'shopify', 'actual');
t('day 0 and day 89 count; day 91 does not', edge === 18, edge);

console.log('\n== F. invChewyVelActual: null vs 0 are different answers ==');
reset(CHEWY_LAGGED);
const v = invChewyVelActual({ master_id: 'SP-1', region: 'US' });
t('lag-anchored 30d window \u2192 a real rate, not 0', v > 0, v);
t('  ~4-5 reported weeks of 100u over 30d \u2248 13-17/day', v > 10 && v < 20, v);
reset({ 'SP-1': [{ channel: 'amazon_us', region: 'US', week_start: ymd(7), units_ordered: 50 }] });
t('no Chewy history \u2192 null (so callers can fall back deliberately)',
  invChewyVelActual({ master_id: 'SP-1', region: 'US' }) === null);
reset({});
t('product absent from salesData \u2192 null',
  invChewyVelActual({ master_id: 'SP-NOPE', region: 'US' }) === null);

console.log('\n== G. Region scoping ==');
reset({ 'SP-1': [
  { channel: 'chewy', region: 'US', week_start: ymd(60), units_ordered: 100 },
  { channel: 'chewy', region: 'CA', week_start: ymd(60), units_ordered: 40 },
] });
t('CA-pinned record excludes US rows',
  invChewyVelActual({ master_id: 'SP-1', region: 'CA' }) * 30 === 40,
  invChewyVelActual({ master_id: 'SP-1', region: 'CA' }) * 30);
reset({ 'SP-1': [
  { channel: 'chewy', region: 'US', week_start: ymd(60), units_ordered: 100 },
  { channel: 'chewy', region: 'CA', week_start: ymd(60), units_ordered: 40 },
] });
t('pooled US+CA record sums both',
  Math.round(invChewyVelActual({ master_id: 'SP-1', region: 'US+CA' }) * 30) === 140,
  invChewyVelActual({ master_id: 'SP-1', region: 'US+CA' }) * 30);

console.log('\n== H. eventVelocityBasis: Chewy joins the other channels on actuals ==');
reset(CHEWY_LAGGED);
const ev = eventVelocityBasis({ scope_type: 'channel', scope_value: 'chewy' }, { master_id: 'SP-1', region: 'US' });
t('uses the Chewy ACTUALS rate', ev > 10 && ev < 20, ev);
t('  and does not call the forecast', FORECAST_CALLS === 0, FORECAST_CALLS);
reset({ 'SP-1': [{ channel: 'amazon_us', region: 'US', week_start: ymd(7), units_ordered: 50 }] });
const evFb = eventVelocityBasis({ scope_type: 'channel', scope_value: 'chewy' }, { master_id: 'SP-1', region: 'US' });
t('falls back to the forecast when there is NO Chewy history', evFb === 300, evFb);
t('  (9000 \u00f7 30 = 300/day)', evFb === 300, evFb);
reset(CHEWY_LAGGED);
t('amazon-scoped events still read invAmazonVel',
  eventVelocityBasis({ scope_type: 'channel', scope_value: 'amazon' }, { master_id: 'SP-1' }) === 4);
t('brand-scoped events still read blended_daily',
  eventVelocityBasis({ scope_type: 'brand' }, { master_id: 'SP-1', blended_daily: 11 }) === 11);

console.log('\n== I. Nothing throws on hostile input ==');
for (const r of [{}, { master_id: 'SP-1' }, { master_id: null }]) {
  let threw = false;
  try { reset(CHEWY_LAGGED); invChewyVelActual(r); } catch { threw = true; }
  t('invChewyVelActual survives ' + JSON.stringify(r), !threw);
}
for (const ch of ['chewy', 'warehouse', 'total', 'walmart', 'amazon_eu', 'nonsense']) {
  let threw = false, out;
  try { reset(CHEWY_LAGGED); out = ipCompareDashboard90d(PROD, ch, 'actual'); } catch { threw = true; }
  t('actual mode survives channel=' + ch + ' and returns a finite number',
    !threw && Number.isFinite(out), out);
}

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

static_js = '\n'.join("t(%r, %s);" % (n, 'true' if v else 'false') for n, v in static)
out = (HARNESS.replace('__REAL__', REAL)
              .replace('__LEGACY__', LEGACY)
              .replace("console.log('\\n== A.",
                       "console.log('\\n== 0. Static assertions against the shipped source ==');\n"
                       + static_js + "\nconsole.log('\\n== A."))
p = os.path.join(SP, 'test_v105.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars' % len(out))
sys.exit(subprocess.call(['node', p]))
