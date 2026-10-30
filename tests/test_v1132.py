#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.32 - the Walmart Sales tab gets a WHOLESALE basis.

Jason: "i will not have access to the items sold ledger. that was a one-time
cost mapping."

So the ledger's DOLLARS are frozen, but its PER-EACH PRICE is durable - and
walmart.com sell-through refreshes weekly. Multiply the two and the one Walmart
feed that keeps updating gains a margin on the money we actually receive.

  * A  the REAL renderWalmartPnl is driven, pnlCard stubbed to capture the strip.
  * A3 THE REGRESSION GUARD. The retail-only read this page shipped before is
       computed beside the new one and proven to overstate: 76.0% against 60.0%
       on one product, because its denominator is Walmart's shelf price rather
       than our invoice.
  * A5 an unpriced product is NULL, never zero. Zero Our Rev would read as
       "sold at no revenue" and drag the blend toward a loss that never happened.
  * B  static: ONE ledger roll-up and ONE fetch shared with the Cost tab, the
       new columns declared in COLUMN_SOURCES so they do not inherit the
       sell-through feed as their only source, and the basis named on each.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0


def ok(cond, name, got=None):
    global passed, failed
    if cond:
        passed += 1; print('  ok    ' + name)
    else:
        failed += 1
        print('  FAIL  ' + name + ('' if got is None else '   got=' + ascii(got)))


def eq(name, got, want):
    ok(got == want, name, None if got == want else '%s want %s' % (ascii(got), ascii(want)))


def fn(name):
    r"""Brace-balance slice, with comments, strings and REGEX LITERALS skipped."""
    i = js.index('function %s(' % name)
    k, n = i, len(js)
    depth, started, prev = 0, False, ''
    while k < n:
        c = js[k]
        if c == '/' and k + 1 < n and js[k + 1] == '/':
            while k < n and js[k] != '\n':
                k += 1
            continue
        if c == '/' and k + 1 < n and js[k + 1] == '*':
            k = js.index('*/', k) + 2
            continue
        if c == '/' and prev in '(,=:[!&|?{};+-*%~^<>':
            k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == '[':
                    while k < n and js[k] != ']':
                        k += 2 if js[k] == '\\' else 1
                if js[k] == '/':
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = 'x'
            continue
        if c in '"\'`':
            q = c; k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = 'x'
            continue
        if c == '{':
            depth += 1; started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise RuntimeError('unbalanced: ' + name)


print('== A. the real renderWalmartPnl, driven ==')

CORE = '\n\n'.join(fn(x) for x in
                   ['renderWalmartPnl', 'walmartPnlCogs', 'walmartLedgerByMaster'])

HARNESS = r"""
'use strict';

// ── fixture ───────────────────────────────────────────────────────────────
// Three products. SP-C is deliberately absent from the ledger.
const walmartPnlData = [
  { master_id: 'SP-A', week_start: '2026-06-01', units: 600, net_sales: 3000, product_name: 'A', walmart_item_number: '1' },
  { master_id: 'SP-A', week_start: '2026-06-08', units: 400, net_sales: 2000, product_name: 'A', walmart_item_number: '1' },
  { master_id: 'SP-B', week_start: '2026-06-01', units: 500, net_sales: 2000, product_name: 'B', walmart_item_number: '2' },
  { master_id: 'SP-C', week_start: '2026-06-01', units: 100, net_sales:  600, product_name: 'C', walmart_item_number: '3' },
];
const allProducts = [
  { master_id: 'SP-A', title: 'Zoom Sticks',   short_name: 'Zoom Sticks',   brand: 'Kitty Ka-Zoom', category_id: 1 },
  { master_id: 'SP-B', title: 'Juananip Tub',  short_name: 'Juananip Tub',  brand: 'Meowijuana',    category_id: 1 },
  { master_id: 'SP-C', title: 'Tuffer Pizza',  short_name: 'Tuffer Pizza',  brand: 'Doggijuana',    category_id: 1 },
];
const allCategories = [{ id: 1, category: 'Toys' }];
// perEach: SP-A 7200/2400 = 3.00, SP-B 1200/960 = 1.25. SP-C absent.
const walmartCatalogData = [
  { walmart_case_sku: 'KA', master_id: 'SP-A', pack: 24, qty_cases: 100, amount: 7200 },
  { walmart_case_sku: 'KB', master_id: 'SP-B', pack: 12, qty_cases:  80, amount: 1200 },
  { walmart_case_sku: 'FEE', master_id: null, pack: null, qty_cases: 5, amount: 0.05, is_fee_line: true },
];
const cogsByMaster = {
  'SP-A': { landed_cost: 1.20 },
  'SP-B': { landed_cost: 0.50 },
  'SP-C': { landed_cost: 0.30 },
};

// ── stubs ─────────────────────────────────────────────────────────────────
let BRAND = '', CARDS = [];
function pnlCard(c) { CARDS.push(c); return '<card/>'; }
const renderPageFreshness = () => ({ catch: () => {} });
const getWalmartPnlDateRange = () => ({ from: '2026-01-01', to: '2026-12-31' });
const catVisPass = () => true;
const prodImgCell = () => '<td class="img"></td>';
const pnlCardBtn = () => '';
const colSrc = () => null;
const srcTipLine = () => '';
const fitTableWrapsSoon = () => {};
const updateWalmartPnlChart = () => {};
let walmartPnlSortKey = 'net_sales', walmartPnlSortDir = -1;
let walmartPnlSelectedMids = new Set(), walmartPnlVisibleMids = [];
let walmartPnlExportRows = [], walmartPnlExportCtx = {};

const EL = {
  'wmpnl-scorecards': { innerHTML: '' },
  'wmpnl-thead-row' : { innerHTML: '' },
  'wmpnl-tbody'     : { innerHTML: '' },
  'wmpnl-row-count' : { textContent: '' },
  'wmpnl-select-all': { checked: false, indeterminate: false },
  'wmpnl-cat'       : { value: '' },
  'wmpnl-search'    : { value: '' },
};
global.document = { getElementById: (id) => (id === 'wmpnl-brand' ? { value: BRAND } : (EL[id] || null)) };

__CORE__

function run(brand) {
  BRAND = brand; CARDS = [];
  EL['wmpnl-tbody'].innerHTML = '';
  EL['wmpnl-scorecards'].innerHTML = '';
  renderWalmartPnl();
  return {
    heads: (EL['wmpnl-thead-row'].innerHTML.match(/>([^<>]*?)(?: ?[\u2191\u2193]| <span[^>]*>[\u2195])?<\/th>/g) || []).length,
    headText: EL['wmpnl-thead-row'].innerHTML,
    body: EL['wmpnl-tbody'].innerHTML,
    note: EL['wmpnl-row-count'].textContent,
    cards: CARDS.map(c => ({ label: c.label, val: c.val, sub: c.sub, src: c.src, tip: c.tip })),
    rows: walmartPnlExportRows.map(r => ({
      mid: r.master_id, units: r.units, net: r.net_sales,
      cogsTotal: r.cogsTotal, netProceeds: r.netProceeds, marginPct: r.marginPct,
      wholesalePer: r.wholesalePer, ourRev: r.ourRev, gm: r.gm, gmPct: r.gmPct,
    })),
  };
}

const all = run('');
const kkz = run('Kitty Ka-Zoom');

// A3 - the PRE-v11.32 read. The page reported margin over RETAIL sell-through,
// a denominator that includes Walmart's own markup and never reaches us.
const legacy = all.rows.map(r => ({ mid: r.mid, retailPct: r.marginPct }));

console.log(JSON.stringify({ all, kkz, legacy, ledger: walmartLedgerByMaster() }));
"""
HARNESS = HARNESS.replace('__CORE__', CORE)
hp = os.path.join(SP, 'test_v1132.js')
io.open(hp, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hp], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:3000]); sys.exit(1)
R = json.loads(res.stdout)
ALL = R['all']
byMid = {r['mid']: r for r in ALL['rows']}

# ── A1 the ledger roll-up ──────────────────────────────────────────────────
eq('A1a the shared roll-up prices SP-A at 7200/2400', R['ledger']['by']['SP-A']['perEach'], 3.0)
eq('A1b and SP-B at 1200/960', R['ledger']['by']['SP-B']['perEach'], 1.25)
ok('SP-C' not in R['ledger']['by'], 'A1c a product the ledger never held is ABSENT, not zero-priced')
eq('A1d the fee line is excluded and counted', R['ledger']['feeLines'], 1)

# ── A2 the columns ─────────────────────────────────────────────────────────
for lbl in ['Our Rev', 'GM $', 'GM %']:
    ok('>' + lbl in ALL['headText'], 'A2a the table carries a %s column' % lbl)
ok('Net Sales' in ALL['headText'] and 'Contrib %' in ALL['headText'],
   'A2b and ADDITIVELY - every retail column is still there, so nothing a '
   'reader already relies on changed meaning')

# ── A3 THE REGRESSION GUARD ────────────────────────────────────────────────
print('\n== A3. retail overstates, and by how much ==')
eq('A3a SP-A wholesale revenue is units x per-each (1,000 x 3.00)',
   byMid['SP-A']['ourRev'], 3000)
eq('A3b its GM $ is that less COGS (3,000 - 1,200)', byMid['SP-A']['gm'], 1800)
eq('A3c GM % = 60.0', round(byMid['SP-A']['gmPct'], 1), 60.0)
eq('A3d /!\\ the RETAIL read this page shipped before says 76.0% on the same '
   'product, because its denominator is Walmart\'s $5.00 shelf price and not '
   'our $3.00 invoice',
   round([x for x in R['legacy'] if x['mid'] == 'SP-A'][0]['retailPct'], 1), 76.0)
ok(byMid['SP-A']['marginPct'] - byMid['SP-A']['gmPct'] > 15,
   'A3e a 16-point overstatement on one product. On the live data the gap is '
   '77.4% against 60.9%',
   byMid['SP-A']['marginPct'] - byMid['SP-A']['gmPct'])

cards = {c['label']: c for c in ALL['cards']}
eq('A3f six scorecards now', len(ALL['cards']), 6)
eq('A3g and they are these', sorted(cards),
   ['Contribution %', 'GM %', 'Net Proceeds', 'Net Sales', 'Our Rev', 'Total COGS (landed)'])
eq('A3h Net Sales still reports RETAIL, unchanged', cards['Net Sales']['val'], '$7,600.00')
eq('A3i Our Rev reports what Walmart pays us (3,000 + 625)',
   cards['Our Rev']['val'], '$3,625.00')
eq('A3j GM % blends over PRICED wholesale revenue (2,175 / 3,625)',
   cards['GM %']['val'], '60.0%')
ok(cards['Contribution %']['val'] != cards['GM %']['val'],
   'A3k the two bases are shown side by side and do NOT agree, which is the '
   'whole point of showing both',
   (cards['Contribution %']['val'], cards['GM %']['val']))

# ── A4 the basis is named on every new surface ─────────────────────────────
print('\n== A4. one label, one measure (rule 3a) ==')
ok('RETAIL' in (cards['Net Sales']['tip'] or ''),
   'A4a Net Sales says it is retail AND that it is not revenue to us')
ok('WHOLESALE' in (cards['Our Rev']['tip'] or ''), 'A4b Our Rev says wholesale')
ok('WHOLESALE' in (cards['GM %']['src'] or ''), 'A4c GM % carries the basis in its chip')
ok('RETAIL' in (cards['Contribution %']['src'] or ''),
   'A4d and Contribution % still carries RETAIL, so the pair cannot be read '
   'as the same measure one card apart')
ok('allowance' in (cards['GM %']['tip'] or '').lower(),
   'A4e GM % says the Walmart allowances are NOT deducted - Chewy\'s GM '
   'deducts them and that agreement has never been loaded for Walmart')

# ── A5 unpriced is NULL, never zero ────────────────────────────────────────
print('\n== A5. a product the ledger never priced ==')
eq('A5a SP-C has no wholesale price', byMid['SP-C']['wholesalePer'], None)
eq('A5b so no Our Rev - NOT zero, which would read as selling at no revenue',
   byMid['SP-C']['ourRev'], None)
eq('A5c and no GM', byMid['SP-C']['gm'], None)
ok(byMid['SP-C']['netProceeds'] == 570,
   'A5d while its RETAIL figures are untouched, so an unpriced product still '
   'reports everything this page reported before', byMid['SP-C']['netProceeds'])
ok('93.8% of units' in (cards['Our Rev']['sub'] or ''),
   'A5e and the COVERAGE is stated, so the blend\'s denominator is visible '
   'rather than assumed (1,500 of 1,600 units)', cards['Our Rev']['sub'])

# ── A6 the brand filter reaches all of it ──────────────────────────────────
kc = {c['label']: c for c in R['kkz']['cards']}
eq('A6a filtering to one brand narrows Our Rev with everything else',
   kc['Our Rev']['val'], '$3,000.00')
ok('what Walmart pays us' in (kc['Our Rev']['sub'] or ''),
   'A6b and a fully priced brand reports no coverage shortfall',
   kc['Our Rev']['sub'])

# ── B. static ──────────────────────────────────────────────────────────────
print('\n== B. one implementation ==')
eq('B1 ONE ledger roll-up in the whole file (hard rule #1)',
   js.count('a.eaches += (Number(r.qty_cases)'), 1)
eq('B2 ONE fetch of walmart_catalog', js.count("from('walmart_catalog').select('*')"), 1)
RP = fn('renderWalmartPnl')
ok('walmartLedgerByMaster().by' in RP,
   'B3 the Sales tab reads the SHARED roll-up rather than re-deriving a price')
ok(RP.count('walmartLedgerByMaster()') == 1,
   'B4 /!\\ and resolves it ONCE per render, not per row - the helper re-rolls '
   'the whole ledger on every call, so a per-row read would be quadratic',
   RP.count('walmartLedgerByMaster()'))
ok('walmartWholesalePerEach' in js,
   'B5 the single-product accessor exists for callers that want one price')

m = re.search(r'walmart_pnl: \{(.*?)\n  \},', js, re.S)
blk = m.group(1)
for k in ['our_rev', 'gm:', 'gm_pct']:
    ok(k in blk,
       'B6 %s is declared in COLUMN_SOURCES. Falling through to _default would '
       'credit the whole figure to walmart_sales_weekly and hide the ledger '
       'the PRICE comes from' % k.rstrip(':'))
ok("'walmart_catalog'" in blk,
   'B7 and the ledger is named as a source of the wholesale columns')

ok('grid-template-columns:repeat(3,1fr)' in s[s.index('id="wmpnl-scorecards"') - 200:
                                              s.index('id="wmpnl-scorecards"') + 200],
   'B8 the strip is a 3-wide grid, so six cards land as two clean rows')
ok('colspan="13"' in s,
   'B9 the empty state spans all thirteen columns. A colspan left at 10 puts '
   'the message under the wrong part of the table')

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
