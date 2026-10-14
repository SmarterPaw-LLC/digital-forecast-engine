# -*- coding: utf-8 -*-
"""
v10.11 — Chewy vendor-portal catalog (cost to Chewy).

Slices the REAL functions out of index.html and drives them, including against
the ACTUAL vendor-portal export bytes when that file is present.

The bug this release exists to prevent: Chewy's `Cost` column is quoted per
`Purchase UOM`. 106 of 127 rows on the first real export are CS (case), so
reading Cost as a unit price overstates our wholesale by the pack size. There
is a named regression guard for exactly that.
"""
import base64
import io
import json
import os
import re
import subprocess
import sys
import tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(os.path.dirname(HERE), 'index.html')
# The real export, if the operator still has it. Optional — the suite runs
# without it, it just skips the against-real-bytes section.
REAL_FILE = os.path.join(os.path.expanduser('~'), 'Downloads', 'Catalog Details.csv')

src = io.open(INDEX, encoding='utf-8', newline='').read()


def fn(name, src=src):
    """Slice a function declaration out by brace balance."""
    for pat in (r'\nfunction %s\s*\(' % re.escape(name),
                r'\nasync function %s\s*\(' % re.escape(name)):
        m = re.search(pat, src)
        if m:
            break
    if not m:
        raise SystemExit('FAIL: could not find function %s' % name)
    i = src.index('{', m.end() - 1)
    depth, j = 0, i
    while j < len(src):
        c = src[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return src[m.start() + 1:j + 1]


def const_line(prefix):
    m = re.search(r'\n(const %s\s*=\s*\[[^\]]*\];)' % re.escape(prefix), src)
    if not m:
        raise SystemExit('FAIL: could not find const %s' % prefix)
    return m.group(1)


SLICES = [
    const_line('CHEWY_STANDING_CATS'),
    const_line('CHEWY_PROMO_CATS'),
    fn('_chewyNormalizeBrand'),
    fn('chewyPricingDeriveAllowances'),
    fn('chewyAllowanceStack'),
    fn('chewyCatalogPricePerEach'),
    fn('chewyVendorUnitEcon'),
    fn('_chewyCatalogDecode'),
    fn('parseChewyCatalog'),
]
# _chewyCatNorm is an arrow const, not a function declaration.
m = re.search(r'\n(const _chewyCatNorm = [^\n]+)', src)
if not m:
    raise SystemExit('FAIL: could not find _chewyCatNorm')
SLICES.insert(2, m.group(1))

real_b64 = ''
if os.path.exists(REAL_FILE):
    real_b64 = base64.b64encode(open(REAL_FILE, 'rb').read()).decode('ascii')

HARNESS = r'''
// ───────── stubs ─────────
let chewyPnlData = [];
let _chewyPricingAllow = null;
let _chewyPricingDerived = null;
let _chewyPricingSrcNote = '';
let allProducts = [];
let _upserted = [];
let _upsertErr = null;
async function getSB() {
  return { from: (t) => ({ upsert: async (rows, opts) => { _upserted.push({ table: t, rows, opts }); return { error: _upsertErr }; } }) };
}
const console_warn = console.warn;

__SLICES__

// ───────── tiny test runner ─────────
let pass = 0, fail = 0;
const failures = [];
function ok(cond, label, extra) {
  if (cond) { pass++; }
  else { fail++; failures.push(label + (extra ? ' :: ' + extra : '')); }
}
function near(a, b, label, eps) {
  eps = eps == null ? 1e-6 : eps;
  const got = (a == null ? 'null' : Number(a).toFixed(6));
  ok(a != null && Math.abs(a - b) < eps, label, 'expected ' + b + ', got ' + got);
}
function isNull(v, label) { ok(v === null, label, 'expected null, got ' + JSON.stringify(v)); }

// ══════════ A. chewyCatalogPricePerEach — THE purchase-UOM requirement ══════
// Jason: "the purchase UOM indicates whether the Cost is by case or each, so
// this needs to be factored into the chewy P&L"

// A1 — the real CF007 row: 54.00 per CASE, MSRP 9.99.
const CF007 = { cost: 54.00, purchase_uom: 'CS' };
near(chewyCatalogPricePerEach(CF007, 12).price, 4.50, 'A1 CS/12 -> 4.50 each');
ok(chewyCatalogPricePerEach(CF007, 12).uom === 'CS', 'A1 uom reported CS');
ok(chewyCatalogPricePerEach(CF007, 12).caseQty === 12, 'A1 caseQty echoed');

// A1-REGRESSION — reading `cost` straight off the file (the pre-v10.11 /
// naive read) is 12x the true per-unit price. If this ever stops being true
// the normalisation has been bypassed somewhere.
const naive = CF007.cost;
const correct = chewyCatalogPricePerEach(CF007, 12).price;
near(naive / correct, 12, 'A1-REGRESSION naive cost read is 12x too high');
ok(naive > 9.99 && correct < 9.99,
   'A1-REGRESSION naive read exceeds MSRP (absurd), normalised does not',
   'naive ' + naive + ' vs msrp 9.99, normalised ' + correct);

// A2 — EA rows are already per-unit and must NOT be divided.
near(chewyCatalogPricePerEach({ cost: 8.49, purchase_uom: 'EA' }, 12).price, 8.49,
     'A2 EA ignores case_qty');
ok(chewyCatalogPricePerEach({ cost: 8.49, purchase_uom: 'EA' }, null).caseQty === 1,
   'A2 EA reports caseQty 1');
ok(chewyCatalogPricePerEach({ cost: 8.49, purchase_uom: 'ea' }, null).price === 8.49,
   'A2 EA is case-insensitive');

// A3 — CS with no case_qty: must be NULL with a nameable reason, never a guess.
const noCase = chewyCatalogPricePerEach(CF007, null);
isNull(noCase.price, 'A3 CS without case_qty -> null price');
ok(noCase.reason === 'no-case-qty', 'A3 reason names the gap', noCase.reason);
[0, -1, '', 'abc', undefined, NaN].forEach(q => {
  const r = chewyCatalogPricePerEach(CF007, q);
  ok(r.price === null && r.reason === 'no-case-qty',
     'A3 CS with bad case_qty ' + JSON.stringify(q) + ' -> null', JSON.stringify(r));
});

// A3b — MOQ must never be used as the case pack. The real CF007 row carries
// MOQ 1; if anything substituted it the price would come back at 54.00.
const moqTrap = chewyCatalogPricePerEach({ cost: 54.00, purchase_uom: 'CS', moq: 1 }, null);
isNull(moqTrap.price, 'A3b MOQ is NOT used as a case-pack fallback');

// A4 — unknown UOM: blank, not guessed. Guessing wrong misreads by pack size.
const badUom = chewyCatalogPricePerEach({ cost: 10, purchase_uom: 'PLT' }, 12);
isNull(badUom.price, 'A4 unknown UOM -> null');
ok(badUom.reason === 'unknown-uom', 'A4 reason unknown-uom', badUom.reason);
const blankUom = chewyCatalogPricePerEach({ cost: 10, purchase_uom: '' }, 12);
ok(blankUom.reason === 'unknown-uom', 'A4 blank UOM -> unknown-uom', blankUom.reason);

// A5 — missing catalog / missing cost are DIFFERENT gaps (different fixes).
ok(chewyCatalogPricePerEach(null, 12).reason === 'no-catalog', 'A5 no catalog row');
ok(chewyCatalogPricePerEach({ cost: null, purchase_uom: 'CS' }, 12).reason === 'no-cost', 'A5 no cost');
ok(chewyCatalogPricePerEach({ cost: 0, purchase_uom: 'CS' }, 12).reason === 'no-cost', 'A5 zero cost is no-cost');

// A6 — CS alias set.
['CS', 'CASE', 'CA', 'CTN', 'CT'].forEach(u => {
  near(chewyCatalogPricePerEach({ cost: 24, purchase_uom: u }, 6).price, 4,
       'A6 CS alias ' + u);
});
['EA', 'EACH', 'UN', 'UNIT', 'E'].forEach(u => {
  near(chewyCatalogPricePerEach({ cost: 24, purchase_uom: u }, 6).price, 24,
       'A6 EA alias ' + u);
});

// ══════════ B. chewyVendorUnitEcon — the margin that price leaves ══════════
// $4.50 to Chewy, $1.50 landed COGS, 23% standing allowances, 25% target.
const E = chewyVendorUnitEcon(4.50, 1.50, 23, 25);
near(E.allow, 4.50 * 0.23, 'B1 allowance dollars');
near(E.net, 4.50 * 0.77, 'B1 net invoice revenue');
near(E.gm, 4.50 * 0.77 - 1.50, 'B1 gross margin $');
near(E.gmPct, ((4.50 * 0.77 - 1.50) / 4.50) * 100, 'B1 gross margin % on invoice value');
near(E.floor, 1.50 / 0.77, 'B1 break-even price');
near(E.target, 1.50 / (1 - 0.23 - 0.25), 'B1 target price');
near(E.deltaToTarget, 1.50 / 0.52 - 4.50, 'B1 delta to target');

// B2 — the identity the Cost/u column leans on: cogs + allow@target
// == target x (1 - m). If this drifts the two columns would disagree.
const T = E.target;
near(1.50 + T * 0.23, T * (1 - 0.25), 'B2 cogs + allowance@target == target x (1-m)');

// B3 — at the floor price, margin is exactly zero.
const atFloor = chewyVendorUnitEcon(E.floor, 1.50, 23, 25);
near(atFloor.gm, 0, 'B3 pricing at the floor yields $0 margin', 1e-9);
// B3b — at the target price, margin is exactly the target.
const atTarget = chewyVendorUnitEcon(E.target, 1.50, 23, 25);
near(atTarget.gmPct, 25, 'B3b pricing at target yields exactly the target %', 1e-9);
near(atTarget.deltaToTarget, 0, 'B3b delta at target is zero', 1e-9);

// B4 — verdict ladder.
ok(chewyVendorUnitEcon(1.80, 1.50, 23, 25).verdict === 'losing',
   'B4 below floor -> losing');
ok(chewyVendorUnitEcon(2.50, 1.50, 23, 25).verdict === 'under-target',
   'B4 above floor, under target -> under-target');
ok(chewyVendorUnitEcon(5.00, 1.50, 23, 25).verdict === 'ok',
   'B4 above target -> ok');
ok(chewyVendorUnitEcon(E.floor * 1.000001, 1.50, 23, 25).verdict !== 'losing',
   'B4 just above the floor is not losing');

// B5 — missing inputs produce nulls, never a confident wrong number.
ok(chewyVendorUnitEcon(null, 1.50, 23, 25).gm === null, 'B5 no price -> no margin');
ok(chewyVendorUnitEcon(4.50, null, 23, 25).gm === null, 'B5 no cogs -> no margin');
ok(chewyVendorUnitEcon(4.50, null, 23, 25).allow !== null,
   'B5 allowance still computable without cogs');
ok(chewyVendorUnitEcon(null, 1.50, 23, 25).target !== null,
   'B5 target still computable without a current price');
ok(chewyVendorUnitEcon(null, 1.50, 23, 25).deltaToTarget === null,
   'B5 delta needs BOTH a price and a target');

// B6 — allowances + target >= 100% is unreachable, not a nonsense price.
const impossible = chewyVendorUnitEcon(4.50, 1.50, 80, 25);
isNull(impossible.target, 'B6 a+m >= 1 -> target null');
ok(impossible.floor !== null, 'B6 floor still solvable at 80% allowances');
const allGone = chewyVendorUnitEcon(4.50, 1.50, 100, 0);
isNull(allGone.floor, 'B6 100% allowances -> no floor at all');

// B7 — zero allowances degrades to plain cost-plus.
const noAllow = chewyVendorUnitEcon(4.00, 2.00, 0, 25);
near(noAllow.gm, 2.00, 'B7 0% allowances -> gm = price - cogs');
near(noAllow.floor, 2.00, 'B7 0% allowances -> floor = cogs');

// ══════════ C. chewyAllowanceStack — ONE resolver, two surfaces ════════════
// C1 — derived from invoices. Mirrors the real agreement shape the v9.81 doc
// records: FTAS 12 + AutoShip 5 + Damages 1.5 + Freight 2.5 + MDF 2 = 23.00%.
chewyPnlData = [
  { category: 'trade_allowance', rebate_name: 'FTAS',      rebate_pct_rate: 12,  invoice_date: '2026-09-01' },
  { category: 'autoship',        rebate_name: 'Auto Ship', rebate_pct_rate: 5,   invoice_date: '2026-09-01' },
  { category: 'damages',         rebate_name: 'Damages',   rebate_pct_rate: 1.5, invoice_date: '2026-09-01' },
  { category: 'freight',         rebate_name: 'Freight',   rebate_pct_rate: 2.5, invoice_date: '2026-09-01' },
  { category: 'coop_marketing',  rebate_name: 'MDF',       rebate_pct_rate: 2,   invoice_date: '2026-09-01' },
  { category: 'promo_bxgx',      rebate_name: 'B2G1',      rebate_pct_rate: 8,   invoice_date: '2026-09-01' },
];
_chewyPricingAllow = null;
let S = chewyAllowanceStack();
near(S.standingPct, 23.00, 'C1 standing floor derives to 23.00%');
near(S.promoPct, 8, 'C1 promo kept SEPARATE from the standing floor');
ok(S.source === 'invoices', 'C1 source names the invoices', S.source);

// C2 — the Pricing Scenarios working copy wins when present, and an edit is
// reported as such so the P&L can say the rates are not the raw invoice ones.
_chewyPricingDerived = { trade_allowance: 12, autoship: 5, damages: 1.5, freight: 2.5, coop_marketing: 2 };
_chewyPricingAllow = Object.assign({}, _chewyPricingDerived);
S = chewyAllowanceStack();
near(S.standingPct, 23.00, 'C2 working copy matching invoices -> 23.00%');
ok(S.source === 'invoices', 'C2 unedited copy still reads as invoices', S.source);
_chewyPricingAllow.trade_allowance = 15;
S = chewyAllowanceStack();
near(S.standingPct, 26.00, 'C2 edited copy -> 26.00%');
ok(S.source === 'edited', 'C2 edit is surfaced', S.source);

// C3 — no rate-bearing invoices: 0% and source 'none' so the UI can warn that
// the margins shown are BEFORE allowances rather than silently overstating.
_chewyPricingAllow = null; _chewyPricingDerived = null; chewyPnlData = [];
S = chewyAllowanceStack();
near(S.standingPct, 0, 'C3 no invoices -> 0%');
ok(S.source === 'none', 'C3 source none', S.source);

// C4 — a throwing derivation must not take the page down.
chewyPnlData = undefined;
let threw = false;
try { S = chewyAllowanceStack(); } catch (e) { threw = true; }
ok(!threw, 'C4 malformed rebate cache does not throw');

// ══════════ D. the real vendor-portal file ══════════
const REAL_B64 = '__REAL_B64__';
if (REAL_B64) {
  const bytes = Buffer.from(REAL_B64, 'base64');
  const buf = new Uint8Array(bytes).buffer;

  // D1 — UTF-16LE with a BOM, despite the .csv extension.
  ok(bytes[0] === 0xFF && bytes[1] === 0xFE, 'D1 real file is UTF-16LE BOM');
  const text = _chewyCatalogDecode(buf);
  ok(text.indexOf('Purchase UOM') >= 0, 'D1 decoded text contains the UOM header');
  ok(text.indexOf('\u0000') < 0, 'D1 decode left no NUL bytes (would mean UTF-8 misread)');

  // D2 — the header is NOT row 0: Chewy puts a spacer row above it.
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  ok(lines[0].indexOf('Chewy SKU') < 0, 'D2 row 0 is a spacer, not the header');
  ok(lines[1].indexOf('Chewy SKU') >= 0, 'D2 row 1 is the real header');
  ok(lines[1].indexOf('\t') >= 0, 'D2 file is TAB-delimited despite .csv');

  // D3 — parse the real bytes end to end.
  allProducts = [
    { master_id: 'SP-0001', sp_sku: 'CF007', chewy_sku: '125631', barcode: '859442005148' },
    { master_id: 'SP-0002', sp_sku: 'CF312', chewy_sku: null,     barcode: '714929800121' },
    { master_id: 'SP-0003', sp_sku: null,    chewy_sku: null,     barcode: '714929807373' },
  ];
  _upserted = [];
  parseChewyCatalog(text).then(r => {
    ok(r.rowCount === 127, 'D3 parses 127 data rows', 'got ' + r.rowCount);
    ok(r.caseRows === 106, 'D3 106 CS rows', 'got ' + r.caseRows);
    ok(r.eachRows === 21, 'D3 21 EA rows', 'got ' + r.eachRows);
    ok(r.caseRows + r.eachRows === r.rowCount, 'D3 every row classified CS or EA');
    ok(r.oddUom.length === 0, 'D3 no unknown UOM values in the real file');
    ok(r.delim === 'tab', 'D3 delimiter detected as tab', r.delim);

    // D4 — match keys. Vendor Part Number is sometimes an sp_sku (CF102) and
    // sometimes a bare UPC (714929807373) in the SAME export, so all three
    // routes have to resolve.
    ok(r.matched === 3, 'D4 three seeded products matched', 'got ' + r.matched);
    const rows = _upserted[0].rows;
    const bySku = {}; rows.forEach(x => bySku[x.chewy_sku] = x);
    ok(bySku['125631'] && bySku['125631'].master_id === 'SP-0001', 'D4 matched on chewy_sku');
    ok(bySku['156570'] && bySku['156570'].master_id === 'SP-0002', 'D4 matched on UPC');
    const viaVpnUpc = rows.filter(x => x.master_id === 'SP-0003');
    ok(viaVpnUpc.length === 1, 'D4 matched a UPC-shaped Vendor Part Number', 'got ' + viaVpnUpc.length);
    ok(rows.filter(x => !x.master_id).length === 124, 'D4 the rest stored with master_id null');

    // D5 — the field mapping on a known row (CF007).
    const cf007 = bySku['125631'];
    near(cf007.cost, 54.00, 'D5 CF007 cost 54.00');
    near(cf007.msrp, 9.99, 'D5 CF007 msrp 9.99');
    near(cf007.map_price, 8.99, 'D5 CF007 map 8.99');
    ok(cf007.purchase_uom === 'CS', 'D5 CF007 uom CS');
    ok(cf007.brand === 'Meowijuana', 'D5 brand normalised', cf007.brand);
    ok(cf007.published === true, 'D5 Published parsed as boolean true');
    ok(cf007.discontinued === false, 'D5 Discontinued parsed as boolean false');
    ok(cf007.vendor_part_number === 'CF007', 'D5 vendor part number');
    ok(cf007.upc === '859442005148', 'D5 upc');
    ok(cf007.moq === 1, 'D5 moq parsed (and NOT reused as case pack)');
    ok(/^https?:/.test(cf007.product_url || ''), 'D5 product url captured');

    // D6 — upsert targets chewy_catalog on the chewy_sku conflict key.
    ok(_upserted.every(u => u.table === 'chewy_catalog'), 'D6 upsert targets chewy_catalog');
    ok(_upserted.every(u => u.opts && u.opts.onConflict === 'chewy_sku'),
       'D6 onConflict is the plain chewy_sku column (no functional index)');
    ok(rows.length === 127, 'D6 all rows sent in one batch under the 500 chunk');

    // D7 — end-to-end: the real CF007 row through the UOM normaliser and the
    // margin model lands at a sane wholesale (45% of MSRP), where the naive
    // read would have claimed we charge 5.4x MSRP.
    const pe = chewyCatalogPricePerEach(cf007, 12);
    near(pe.price, 4.50, 'D7 real CF007 -> $4.50 each at a 12 pack');
    near((pe.price / cf007.msrp) * 100, 45.05, 'D7 $4.50 is ~45% of the $9.99 MSRP', 0.1);
    ok((cf007.cost / cf007.msrp) > 5, 'D7-REGRESSION naive read would claim >5x MSRP');

    finish();
  }).catch(e => { ok(false, 'D3 parse threw', e && e.message); finish(); });
} else {
  console.log('  (section D skipped — real export not present at ~/Downloads)');
  finish();
}

// ══════════ E. parser guards ══════════
function sectionE() {
  // E1 — a file with no Purchase UOM column must be REFUSED, not guessed at.
  // Without it a case cost silently reads as a unit cost.
  const noUom = 'Chewy SKU\tBrand\tCost\tMSRP\n1\tMeowijuana\t54.00\t9.99\n';
  return parseChewyCatalog(noUom).then(
    () => ok(false, 'E1 missing Purchase UOM should have thrown'),
    e => ok(/Purchase UOM/i.test(e.message), 'E1 missing Purchase UOM is refused with a named reason', e.message)
  ).then(() => {
    // E2 — a wrong file is rejected on content, not extension.
    const wrong = 'asin\tnet units sold\nB001\t12\n';
    return parseChewyCatalog(wrong).then(
      () => ok(false, 'E2 wrong file should have thrown'),
      e => ok(/header row/i.test(e.message), 'E2 wrong file names the real problem', e.message)
    );
  }).then(() => {
    // E3 — comma-delimited is handled too (Chewy has changed format before).
    allProducts = [];
    _upserted = [];
    const csv = 'junk,,,\nChewy SKU,Brand,Cost,MSRP,Purchase UOM,MOQ\n9001,Doggijuana,36.00,8.99,CS,6\n9002,Doggijuana,7.25,8.99,EA,1\n';
    return parseChewyCatalog(csv).then(r => {
      ok(r.delim === 'comma', 'E3 comma delimiter detected', r.delim);
      ok(r.rowCount === 2, 'E3 two rows', 'got ' + r.rowCount);
      ok(r.caseRows === 1 && r.eachRows === 1, 'E3 one CS one EA');
      near(chewyCatalogPricePerEach(_upserted[0].rows[0], 6).price, 6.00, 'E3 CS/6 -> 6.00');
      near(chewyCatalogPricePerEach(_upserted[0].rows[1], null).price, 7.25, 'E3 EA as-is');
    });
  }).then(() => {
    // E4 — duplicate Chewy SKUs collapse to one row. The table has a unique
    // index on chewy_sku; sending both would fail the whole upsert.
    _upserted = [];
    const dup = 'Chewy SKU\tCost\tPurchase UOM\n555\t10.00\tEA\n555\t99.00\tEA\n';
    return parseChewyCatalog(dup).then(r => {
      ok(r.rowCount === 1, 'E4 duplicate chewy_sku deduped', 'got ' + r.rowCount);
      near(_upserted[0].rows[0].cost, 10.00, 'E4 first occurrence wins');
    });
  }).then(() => {
    // E5 — currency decoration and thousands separators survive.
    _upserted = [];
    const money = 'Chewy SKU\tCost\tMSRP\tPurchase UOM\n777\t$1,234.56\t$19.99\tCS\n';
    return parseChewyCatalog(money).then(() => {
      near(_upserted[0].rows[0].cost, 1234.56, 'E5 $ and comma stripped from cost');
      near(_upserted[0].rows[0].msrp, 19.99, 'E5 $ stripped from msrp');
    });
  }).then(() => {
    // E6 — a missing table surfaces the migration filename, not a raw PG error.
    _upsertErr = { message: 'relation "public.chewy_catalog" does not exist' };
    const okFile = 'Chewy SKU\tCost\tPurchase UOM\n1\t5.00\tEA\n';
    return parseChewyCatalog(okFile).then(
      () => ok(false, 'E6 missing table should have thrown'),
      e => ok(/supabase_v10_11_chewy_catalog\.sql/.test(e.message),
              'E6 missing table names the migration file', e.message)
    );
  }).then(() => { _upsertErr = null; });
}

let _finished = 0;
function finish() {
  if (_finished++) return;
  sectionE().then(report).catch(e => { ok(false, 'section E threw', e && e.message); report(); });
}
function report() {
  console.log('\n  v10.11: ' + pass + ' passed, ' + fail + ' failed');
  if (fail) { failures.forEach(f => console.log('    FAIL ' + f)); process.exit(1); }
}
'''

harness = HARNESS.replace('__SLICES__', '\n\n'.join(SLICES)).replace('__REAL_B64__', real_b64)

tmpdir = tempfile.mkdtemp(prefix='v1011_')
jsp = os.path.join(tmpdir, 'test_v1011.js')
io.open(jsp, 'w', encoding='utf-8', newline='').write(harness)

print('=== v10.11 behaviour tests ===')
if not real_b64:
    print('  note: ~/Downloads/Catalog Details.csv not found - section D will skip')
r = subprocess.run([os.environ.get('NODE', 'node'), jsp], capture_output=True, text=True)
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
if r.returncode != 0:
    sys.exit(r.returncode)

# ───────────────────────── static assertions ─────────────────────────
print('\n=== v10.11 static assertions ===')
sfail = []


def sok(cond, label):
    if cond:
        print('  ok: ' + label)
    else:
        sfail.append(label)
        print('  FAIL: ' + label)


# The uploader must NOT be on the Uploads page (explicit instruction).
sok('id="f-chewy-catalog"' in src, 'catalog file input exists')
uploads_start = src.index('id="data-view-uploads"')
uploads_end = src.index('id="data-view-query"')
sok('f-chewy-catalog' not in src[uploads_start:uploads_end],
    'uploader is NOT on the Data -> Uploads page (per Jason)')
cost_start = src.index('id="chpnl-view-cost"')
cost_end = src.index('<!-- /chpnl-view-cost -->')
sok('f-chewy-catalog' in src[cost_start:cost_end],
    'uploader lives on the Cost to Chewy tab')
sok('handleChewyCatalogUpload' in src[cost_start:cost_end], 'uploader wired to its handler')

# Three sub-tabs, registry driven.
for t in ('chpnl-tab-sales', 'chpnl-tab-cost', 'chpnl-tab-rebates'):
    sok(src.count('id="%s"' % t) == 1, 'exactly one %s button' % t)
sok("key: 'cost',    panel: 'chpnl-view-cost'" in src, 'cost tab in the switch registry')

# Category-visibility predicate is wired for the new page (the v10.6 rule).
sok("catVisPass('pnl_chewy_cost'" in src, 'catVisPass wired on the Cost view')
sok(src.count("catVisPass('pnl_chewy_cost'") == 1, 'exactly one pnl_chewy_cost predicate site')
sok("navKeys: ['pnl_chewy_cost']" in src, 'pnl_chewy_cost in CATVIS_PAGES')
sok("pnl_chewy_cost: { id: 'chpnl-cost-search' }" in src, 'pnl_chewy_cost in GLOBAL_SEARCH_MAP')

# Architecture Rule #8 — merge + SP-TEMP promotion must carry the new FK.
sok("reassignMasterId('chewy_catalog')" in src, 'runMerge reassigns chewy_catalog')
sok("from('chewy_catalog').update({ master_id })" in src,
    'SP-TEMP promotion reassigns chewy_catalog')

# CSV export routing per sub-tab (the standing always-exportable rule).
sok('downloadChewyPnlCostCSV' in src, 'cost exporter exists')
sok('downloadChewyPnlSalesCSV' in src, 'sales exporter exists (was missing since v8.38)')
sok("if (cv === 'cost')  return downloadChewyPnlCostCSV();" in src, 'cost export routed')
sok("if (cv === 'sales') return downloadChewyPnlSalesCSV();" in src, 'sales export routed')

# Sales tab vendor columns + widened colspans.
sok("label: 'Our Rev'" in src, 'Sales tab has Our Rev column')
sok("label: 'Vendor Contrib'" in src, 'Sales tab has Vendor Contrib column')
sales_start = src.index('function renderChewyPnlSales()')
sales_end = src.index('function downloadChewyPnlCostCSV')
sok('colspan="9"' not in src[sales_start:sales_end],
    'no stale colspan=9 left in the Sales renderer (6 default / 11 with retail on)')
# v10.55 made the Sales column set filterable (6 by default, 11 with the retail
# detail toggle on), so a hardcoded colspan would under-span the empty state the
# moment the toggle flips. The guarantee this assertion wants is that the empty
# state spans the WHOLE table, which is now computed rather than counted.
sok("colspan=\"' + cols.length + '\"" in src[sales_start:sales_end],
    'Sales empty state spans the visible column count, not a hardcoded 11')
cost_fn_start = src.index('function renderChewyPnlCost()')
cost_fn_end = src.index('function downloadChewyPnlCostCSV')
sok('colspan="12"' in src[cost_fn_start:cost_fn_end], 'Cost renderer uses colspan=12 (12 columns)')

# One allowance resolver, two surfaces — no second copy of the stack math.
sok(src.count('function chewyAllowanceStack()') == 1, 'one chewyAllowanceStack definition')
sok(src.count('chewyAllowanceStack()') >= 3, 'allowance stack read by several surfaces')
sok(src.count('function chewyCatalogPricePerEach') == 1,
    'one UOM normaliser (no second copy to drift)')

# The MOQ trap is called out in the source so nobody "fixes" it later.
sok('NOT the case pack' in src or 'not the case pack' in src.lower(),
    'source warns that MOQ is not the case pack')

# Provenance, NOT the version chip. A suite that asserts the chip asserts
# "what release is it right now", which is false the moment the next one
# ships - so every past suite would break on every bump. Assert instead
# that this release's own markers, and its neighbours', survived.
sok(src.count('v10.11 —') >= 1, "v10.11's own provenance markers survive")
for marker in ('v10.10 —', 'v10.9 —', 'v10.6 —'):
    sok(marker in src, 'earlier provenance marker preserved: %s' % marker.split(' ')[0])

print('\n  static: %d failed' % len(sfail))
if sfail:
    sys.exit(1)
print('\n  v10.11 ALL GREEN')
