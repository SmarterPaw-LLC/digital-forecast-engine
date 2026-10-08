# -*- coding: utf-8 -*-
"""v10.2 — Demand Forecast trend parity, per-channel trends, Growth filter.
Drives the REAL sliced engine + the REAL generated columns."""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

def span(a, b, label):
    i = js.find(a); j = js.find(b, i + 1)
    if i < 0 or j < 0:
        print('ANCHOR FAIL %s' % label); sys.exit(1)
    return js[i:j]

ENGINE = span('const IP_VEL_DEFAULT_CHANS', 'function ipVelTrendTip', 'trend engine')
SHARED = span('function velTrendCell(r, t) {', 'function ipVelTrendTip', 'shared renderers')
GEN    = span('for (const _c of TREND_CHANNELS) {', 'const FC_DEFAULT_VISIBLE', 'per-channel generator')

static = [
    ('Forecast page has its own trend channel resolver', 'function fcVelTrendChans()' in js),
    ('Forecast page has the VELOCITY TREND group',
     js.count("groupHdr:'VELOCITY TREND'") >= 6),
    ('the Forecast column picker lists vel-trend',
     "'velocity','vel-trend','velocity-lb'" in js),
    ('both pages carry a Growth dropdown',
     'id="fc-growth"' in RAW and 'id="ip-growth"' in RAW),
    ('Forecast page carries a Vel vs dropdown', 'id="fc-vel-cmp"' in RAW),
    ('the comparison window is one shared setting, not per-page DOM',
     "localStorage.getItem('velCmpMode')" in js
     and "function ipVelCompareMode() { return document.getElementById" not in js),
    ('Growth filter is applied on the Forecast page',
     'growthFilterPass(r, fcGrowthMode(), fcVelTrendChans())' in js),
    ('Growth filter is applied at all four Inventory Planning sites',
     js.count("growthFilterPass(r, ipGrowthMode(), ipVelTrendChans())") == 4),
    ('the IP trend column delegates to the shared renderer',
     'render:  r => velTrendCell(r, ipVelTrendFor(r)) }' in js),
    ('saved views capture the Growth filter', "growth:   document.getElementById('ip-growth')" in js),
]

HARNESS = r"""
let salesData = {};
const allProducts = [], allBomData = [];
const _velMemo = new Map();
function clearVelMemo(){ _velMemo.clear(); }
let CHK = {};
const document = { getElementById: (id) => (id in CHK) ? CHK[id] : null };
const localStorage = { _d:{}, getItem(k){ return this._d[k] ?? null; }, setItem(k,v){ this._d[k]=v; } };
function ipActiveChannels(){ return null; }
function getEffectiveCurveForProduct(){ return { curve: {} }; }
function isoWeekOfYear(){ return 1; }
const SEED = { curves: {} };
function ipBundleAttrUnitsWindow(){ return 0; }
function ipChannelLabel(k){ return k; }
function parseLocalDate(d){ const [y,m,dd] = String(d).split('-').map(Number); return new Date(y, m-1, dd); }
function renderInventoryTbl(){ RENDERS.ip++; }
function renderAll(){ RENDERS.fc++; }
let RENDERS = { ip:0, fc:0 };
const IP_COLUMNS = [], FC_COLUMNS = [];

__ENGINE__
__SHARED__
function ipVelTrendTip(){ return 'tip'; }
__GEN__

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const ago = (d) => { const x = new Date(Date.now() - d * 864e5);
  return `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`; };
const MID = 'SP-1';
// Per-channel history: Amazon doubles, Shopify halves, Walmart flat.
function seed() {
  salesData = { [MID]: [] };
  const add = (ch, age, u) => salesData[MID].push({ channel: ch, region:'US', week_start: ago(age), units_ordered: u });
  for (let a = 0;  a < 30; a++) { add('amazon_us', a, 40); add('shopify', a, 5);  add('walmart', a, 10); }
  for (let a = 30; a < 60; a++) { add('amazon_us', a, 10); add('shopify', a, 20); add('walmart', a, 10); }
  clearVelMemo();
}
const R = { master_id: MID, region: 'US', sea_idx: 1 };
CHK = { fVelocityWindow: { value: '30' } };
seed();

console.log('\n== A. The engine answers for an EXPLICIT channel set ==');
const amz = ipVelTrendForKeys(R, ['amazon']);
const shp = ipVelTrendForKeys(R, ['shopify']);
const wmt = ipVelTrendForKeys(R, ['walmart']);
t('Amazon 10/day -> 40/day reads 4.0x', Math.abs(amz.now / amz.prev - 4) < 1e-6, amz.now / amz.prev);
t('  which is the top tier', ipVelTrendLabel(amz).txt.includes('Surging'), ipVelTrendLabel(amz).txt);
t('Shopify 20/day -> 5/day reads 0.25x', Math.abs(shp.now / shp.prev - 0.25) < 1e-6, shp.now / shp.prev);
t('  which is Declining', ipVelTrendLabel(shp).txt.includes('Declining'), ipVelTrendLabel(shp).txt);
t('Walmart flat reads Steady', ipVelTrendLabel(wmt).txt.includes('Steady'), ipVelTrendLabel(wmt).txt);

console.log('\n== B. THE POINT: the blend hides what the channels are doing ==');
const blend = ipVelTrendForKeys(R, ['amazon','shopify','walmart']);
t('blended (40+5+10 vs 10+20+10) = 55/40 = 1.375x',
  Math.abs(blend.now / blend.prev - 1.375) < 1e-6, blend.now / blend.prev);
t('  so the blend reads merely Accelerating...',
  ipVelTrendLabel(blend).txt.includes('Accelerating'), ipVelTrendLabel(blend).txt);
t('  ...while Amazon is Surging and Shopify is Declining underneath it',
  ipVelTrendLabel(amz).rank === 4 && ipVelTrendLabel(shp).rank === -2);

console.log('\n== C. Growth filter: blended vs any-channel ==');
const keys = ['amazon','shopify','walmart'];
t('blended "surging" does NOT match (blend is only 1.375x)',
  growthFilterPass(R, 'surging', keys) === false);
t('any-channel "surging" DOES match (Amazon qualifies alone)',
  growthFilterPass(R, 'any:surging', keys) === true);
t('blended "accel" matches', growthFilterPass(R, 'accel', keys) === true);
t('blended "declining" does not', growthFilterPass(R, 'declining', keys) === false);
t('any-channel "declining" does (Shopify collapsed)',
  growthFilterPass(R, 'any:declining', keys) === true);
t('empty mode is a pass-through', growthFilterPass(R, '', keys) === true);
t('  and so is undefined', growthFilterPass(R, undefined, keys) === true);

console.log('\n== D. Bucket ladder is monotonic ==');
const ranks = ['surging','accel','growing'].map(m => growthRankMatches(4, m));
t('rank 4 satisfies surging, accel AND growing', ranks.every(Boolean), ranks);
t('rank 2 satisfies accel + growing but not surging',
  !growthRankMatches(2,'surging') && growthRankMatches(2,'accel') && growthRankMatches(2,'growing'));
t('rank 1 satisfies growing only',
  !growthRankMatches(1,'accel') && growthRankMatches(1,'growing'));
t('rank -2 satisfies slowing AND declining',
  growthRankMatches(-2,'slowing') && growthRankMatches(-2,'declining'));
t('rank -1 satisfies slowing but not declining',
  growthRankMatches(-1,'slowing') && !growthRankMatches(-1,'declining'));
t('rank 0 satisfies nothing but "all"',
  !['surging','accel','growing','slowing','declining'].some(m => growthRankMatches(0, m)));

console.log('\n== E. Per-channel columns were generated for BOTH pages ==');
const ipKeys = IP_COLUMNS.map(c => c.key), fcKeys = FC_COLUMNS.map(c => c.key);
for (const ch of ['amazon','shopify','chewy','walmart']) {
  t(`vel_trend_${ch} on both registries`,
    ipKeys.includes('vel_trend_' + ch) && fcKeys.includes('vel_trend_' + ch));
}
t('all 8 are default OFF (nobody\u2019s column set shifts)',
  IP_COLUMNS.concat(FC_COLUMNS).filter(c => c.key.startsWith('vel_trend_')).every(c => c.default === false));
t('all 8 sit in the vel-trend group',
  IP_COLUMNS.concat(FC_COLUMNS).filter(c => c.key.startsWith('vel_trend_')).every(c => c.group === 'vel-trend'));

console.log('\n== F. The generated columns actually render the right channel ==');
const amzCol = FC_COLUMNS.find(c => c.key === 'vel_trend_amazon');
const shpCol = FC_COLUMNS.find(c => c.key === 'vel_trend_shopify');
t('Amz Trend cell says Surging', /Surging/.test(amzCol.render(R)), amzCol.render(R).slice(0,90));
t('Shop Trend cell says Declining', /Declining/.test(shpCol.render(R)));
t('they are NOT the same cell (the channel arg is live)',
  amzCol.render(R) !== shpCol.render(R));
t('Amz Trend sorts above Shop Trend', amzCol.sortVal(R) > shpCol.sortVal(R),
  { amz: amzCol.sortVal(R), shp: shpCol.sortVal(R) });
t('export carries label + magnitude', /Surging \+\d+%/.test(amzCol.csv(R)), amzCol.csv(R));

console.log('\n== G. Forecast channel resolver mirrors the Inventory rule ==');
CHK = { fVelocityWindow:{value:'30'}, 'fChan-total':{checked:true},
        'fChan-amazon':{checked:true}, 'fChan-shopify':{checked:true},
        'fChan-chewy':{checked:true}, 'fChan-walmart':{checked:true} };
t('everything checked resolves to the Vel/day recipe, not all four',
  JSON.stringify(fcVelTrendChans()) === JSON.stringify(IP_VEL_DEFAULT_CHANS), fcVelTrendChans());
CHK['fChan-total'].checked = false;
CHK['fChan-chewy'].checked = false; CHK['fChan-walmart'].checked = false;
t('a genuine narrowing is honoured',
  JSON.stringify(fcVelTrendChans()) === JSON.stringify(['amazon','shopify']), fcVelTrendChans());
CHK['fChan-amazon'].checked = false; CHK['fChan-shopify'].checked = false;
t('nothing checked falls back rather than returning an empty plan',
  JSON.stringify(fcVelTrendChans()) === JSON.stringify(IP_VEL_DEFAULT_CHANS), fcVelTrendChans());

console.log('\n== H. The comparison window is ONE setting ==');
CHK = { 'ip-vel-cmp': { value:'prior' }, 'fc-vel-cmp': { value:'prior' } };
setVelCmpMode('90');
t('writing from either page updates the stored mode', ipVelCompareMode() === '90');
t('  and syncs the other page\u2019s dropdown',
  CHK['ip-vel-cmp'].value === '90' && CHK['fc-vel-cmp'].value === '90');
t('  and clears the velocity memo (windows changed)', _velMemo.size === 0);
setVelCmpMode('prior');
t('round-trips back', ipVelCompareMode() === 'prior');

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

static_js = '\n'.join("t(%r, %s);" % (n, 'true' if v else 'false') for n, v in static)
out = (HARNESS.replace('__ENGINE__', ENGINE)
              .replace('__SHARED__', SHARED)
              .replace('__GEN__', GEN)
              .replace("console.log('\\n== A.",
                       "console.log('\\n== 0. Static assertions against the shipped source ==');\n"
                       + static_js + "\nconsole.log('\\n== A."))
p = os.path.join(SP, 'test_v102.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars' % len(out))
sys.exit(subprocess.call(['node', p]))
