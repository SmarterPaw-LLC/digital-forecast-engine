#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.30 - Cost to Walmart becomes the complete Walmart P&L.

Jason declined the Scintilla store export ("no, i'm not doing that") and said
"we just need to work with what we've got". What we've got is the v11.08 Items
Sold ledger, which is 100% of what we invoice Walmart, store and ecom. It was
only ever missing COGS.

  * A  the REAL renderWalmartCost is driven, with pnlCard stubbed to capture
       what the strip is ASKED to show (the v11.03 pattern).
  * A3 THE REGRESSION GUARD. The naive "no COGS means zero cost" read is run
       beside the shipped one and proven to overstate blended GM by ~4 points
       on a fixture where one product in three is unpriced. Zero-cost renders
       as a 100% margin, which is the one wrong answer on this page that looks
       like good news.
  * B  static: ONE COGS resolver (the Sales tab's), the loader fetches it, the
       basis is named on every new label, and the strip goes through pnlCard
       rather than growing a sixth bespoke card renderer (hard rule #1).
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
    r"""Slice one function out of the shipped script by BRACE BALANCE.

    Comments, strings AND REGEX LITERALS are skipped first. This file is full
    of braces inside all three (the v11.12 lesson), and the regex half is not
    optional here: v11.30 put `.replace(/"/g, '&quot;')` inside the function
    being sliced, and a slicer that does not know a regex from a division
    treats that `"` as the start of a string, swallows the rest of the line,
    and silently returns a TRUNCATED function. The first run of this suite did
    exactly that and node died on "Unexpected end of input".
    """
    i = js.index('function %s(' % name)
    k, n = i, len(js)
    depth, started = 0, False
    prev = ''          # last significant char, for the regex/division call
    while k < n:
        c = js[k]
        if c == '/' and k + 1 < n and js[k + 1] == '/':
            while k < n and js[k] != '\n':
                k += 1
            continue
        if c == '/' and k + 1 < n and js[k + 1] == '*':
            k = js.index('*/', k) + 2
            continue
        # A `/` opening a REGEX can only follow an operator or a delimiter;
        # after a value it is division. The standard heuristic, and enough for
        # this file.
        if c == '/' and prev in '(,=:[!&|?{};+-*%~^<>' + '':
            k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == '[':                     # a class can hold an unescaped /
                    while k < n and js[k] != ']':
                        k += 2 if js[k] == '\\' else 1
                if js[k] == '/':
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():          # flags
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


print('== A. the real renderWalmartCost, driven ==')

CORE = fn('renderWalmartCost') + '\n\n' + fn('walmartPnlCogs')

HARNESS = r"""
'use strict';
const esc2 = (v) => String(v == null ? '' : v)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// The ledger as v11.08 stores it: CASE grain, a fee line, an unmatched SKU,
// and one product deliberately left WITHOUT a COGS row.
const walmartCatalogData = [
  { walmart_case_sku: 'KC211',    master_id: 'SP-0353', pack: 24, qty_cases: 100, amount: 7426.00 },
  { walmart_case_sku: 'KC211-01', master_id: 'SP-0353', pack: 6,  qty_cases: 50,  amount: 933.00  },
  { walmart_case_sku: 'MC003',    master_id: 'SP-0101', pack: 12, qty_cases: 80,  amount: 2400.00 },
  { walmart_case_sku: 'DC217',    master_id: 'SP-0900', pack: 12, qty_cases: 40,  amount: 1200.00 },
  { walmart_case_sku: 'KD001',    master_id: null, pack: null, qty_cases: 19, amount: 0.19, is_fee_line: true },
  { walmart_case_sku: 'KF001',    master_id: null, pack: null, qty_cases: 10, amount: 100.00 },
];
const allProducts = [
  { master_id: 'SP-0353', title: 'Zoomie Multipack Fish Toy', brand: 'Kitty Ka-Zoom' },
  { master_id: 'SP-0101', title: 'Juananip Refill Bottle',    brand: 'Meowijuana' },
  { master_id: 'SP-0900', title: 'Tuffer Chewer Pizza',       brand: 'Doggijuana' },
];
// SP-0900 is ABSENT on purpose.
const cogsByMaster = {
  'SP-0353': { landed_cost: 1.20, dtc_cogs: 9.99 },
  'SP-0101': { landed_cost: null, dtc_cogs: 0.90 },
};

let BRAND = '', CARDS = [];
function pnlCard(c) { CARDS.push(c); return '<card/>'; }

const EL = {
  'wmpnl-cost-thead'     : { innerHTML: '' },
  'wmpnl-cost-tbody'     : { innerHTML: '' },
  'wmpnl-cost-note'      : { textContent: '' },
  'wmpnl-cost-scorecards': { innerHTML: 'STALE' },
};
global.document = { getElementById: (id) => (id === 'wmpnl-brand' ? { value: BRAND } : (EL[id] || null)) };

__CORE__

function run(brand) {
  BRAND = brand; CARDS = [];
  EL['wmpnl-cost-tbody'].innerHTML = '';
  EL['wmpnl-cost-note'].textContent = '';
  EL['wmpnl-cost-scorecards'].innerHTML = 'STALE';
  renderWalmartCost();
  const body = EL['wmpnl-cost-tbody'].innerHTML;
  return {
    head : EL['wmpnl-cost-thead'].innerHTML,
    body, note: EL['wmpnl-cost-note'].textContent,
    strip: EL['wmpnl-cost-scorecards'].innerHTML,
    cards: CARDS.map(c => ({ label: c.label, val: c.val, sub: c.sub, src: c.src, tip: c.tip })),
    rows : (body.match(/<tr>/g) || []).length,
  };
}

// A3 - the PRE-v11.30 naive read: an unpriced product counted at zero cost.
// Same arithmetic otherwise, so the only difference is the fallback.
function naiveBlendedGm() {
  const by = {};
  for (const r of walmartCatalogData) {
    if (r.is_fee_line || !r.master_id || !r.pack || !(r.qty_cases > 0)) continue;
    const a = by[r.master_id] || (by[r.master_id] = { eaches: 0, amount: 0 });
    a.eaches += r.qty_cases * r.pack;
    a.amount += r.amount;
  }
  let amount = 0, gm = 0;
  for (const mid of Object.keys(by)) {
    const a = by[mid];
    const per = walmartPnlCogs(mid) || 0;          // <- the defect: null becomes 0
    amount += a.amount;
    gm     += a.amount - per * a.eaches;
  }
  return { amount, gm, pct: (gm / amount) * 100 };
}

const all    = run('');
const meowi  = run('Meowijuana');
const dog    = run('Doggijuana');
const nobody = run('Nonexistent Brand');

console.log(JSON.stringify({
  all, meowi, dog, nobody,
  naive: naiveBlendedGm(),
}));
"""
HARNESS = HARNESS.replace('__CORE__', CORE)
hp = os.path.join(SP, 'test_v1130.js')
io.open(hp, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hp], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:3000]); sys.exit(1)
R = json.loads(res.stdout)
ALL = R['all']

# ── A1 the columns ─────────────────────────────────────────────────────────
heads = re.findall(r'>([^<>]+)</th>', ALL['head'])
eq('A1a eleven columns now', len(heads), 11)
eq('A1b and in this order', heads,
   ['Product', 'Master ID', 'Case SKUs', 'Cases', 'Eaches', 'Invoiced $',
    'Cost/each', 'COGS/u', 'COGS', 'GM $', 'GM %'])
ok('Amount' not in heads,
   'A1c "Amount" was renamed to "Invoiced $". On a page that also shows COGS '
   'and GM, "Amount" does not say whose money it is')
ok(ALL['head'].count('cursor:help') == 6,
   'A1d every new column carries a tip, and so do the two it reframes',
   ALL['head'].count('cursor:help'))

# ── A2 the arithmetic ──────────────────────────────────────────────────────
eq('A2a the fee line and the unmatched SKU are still excluded', ALL['rows'], 3)
ok('$8,359.00' in ALL['body'],
   'A2b the two case configs of one product still collapse to ONE invoiced '
   'total - the v11.08 rule survives')
ok('$3.0959' in ALL['body'], 'A2c cost/each is still derived from the totals')
ok('$3,240.00' in ALL['body'], 'A2d COGS = COGS/u x eaches (1.20 x 2,700)')
ok('$5,119.00' in ALL['body'], 'A2e GM $ = invoiced less COGS (8,359 - 3,240)')
ok('61.2%' in ALL['body'], 'A2f GM % = GM $ / invoiced')
ok('$0.9000' in ALL['body'],
   'A2g COGS/u falls back landed -> dtc, the SAME chain the Sales tab uses: '
   'SP-0101 has a null landed_cost and resolves to its dtc_cogs')

# ── A3 THE REGRESSION GUARD ────────────────────────────────────────────────
print('\n== A3. unpriced is NOT zero-cost (the guard) ==')
cards = {c['label']: c for c in ALL['cards']}
eq('A3a four scorecards', len(ALL['cards']), 4)
eq('A3b and they are these', sorted(cards), ['GM $', 'GM %', 'Invoiced Revenue', 'Total COGS'])
eq('A3c Invoiced Revenue is the WHOLE ledger, unpriced rows included - we '
   'billed Walmart for them whatever our cost records say',
   cards['Invoiced Revenue']['val'], '$11,959.00')
eq('A3d GM $ counts only the priced rows', cards['GM $']['val'], '$6,655.00')
eq('A3e /!\\ GM % divides by PRICED invoiced dollars, not by all of them',
   cards['GM %']['val'], '61.9%')
ok(abs(R['naive']['pct'] - 65.68) < 0.05,
   'A3f the naive "null COGS means zero" read really does return a different '
   'number', R['naive']['pct'])
ok(R['naive']['pct'] - 61.86 > 3.5,
   'A3g and it is HIGHER by ~4 points on a fixture where one product in three '
   'is unpriced - a zero-cost row reads as a 100% margin, so the defect '
   'always flatters the page', R['naive']['pct'])
ok('unpriced' in (cards['Total COGS']['sub'] or ''),
   'A3h the COGS card NAMES the unpriced products rather than leaving the '
   'shortfall silent', cards['Total COGS']['sub'])
ok('90.0%' in (cards['GM $']['sub'] or ''),
   'A3i and GM $ states the coverage, so a reader can see the denominator '
   'is not the whole ledger', cards['GM $']['sub'])
ok('missing' in ALL['body'],
   'A3j the unpriced ROW says missing rather than printing a zero')
ok(ALL['body'].count('\u2014') >= 3,
   'A3k its COGS, GM $ and GM % are em dashes, never 0.0%')

# ── A4 basis is stated everywhere it could be confused ─────────────────────
print('\n== A4. the basis is named, because Sales beside it is RETAIL ==')
for lbl in ['GM $', 'GM %']:
    ok('WHOLESALE' in (cards[lbl]['src'] or ''),
       'A4a %s carries the basis in its source chip' % lbl, cards[lbl]['src'])
ok('allowance' in (cards['GM %']['sub'] or '').lower(),
   'A4b GM % says the allowances are NOT in it. Chewy\'s GM deducts them; '
   'Walmart\'s agreement has never been loaded, so the shared prefix must not '
   'be left to imply a deduction that is not made', cards['GM %']['sub'])
ok('RETAIL' in (cards['GM %']['tip'] or ''),
   'A4c and the tip warns it is not comparable with the Sales tab')
ok('Period' in ALL['note'],
   'A4d the note says the figures are CUMULATIVE and not scoped by the period '
   'control, which is live on this page and cannot bite here - the ledger has '
   'no per-row date (the v10.19 rule, stated rather than silently dead)',
   ALL['note'])

# ── A5 the brand filter reaches the strip too ──────────────────────────────
print('\n== A5. the brand control narrows the strip, not just the table ==')
mc = {c['label']: c for c in R['meowi']['cards']}
eq('A5a one Meowijuana product', R['meowi']['rows'], 1)
eq('A5b and the strip follows it', mc['Invoiced Revenue']['val'], '$2,400.00')
eq('A5c GM $ with it', mc['GM $']['val'], '$1,536.00')
ok('unpriced' not in (mc['Total COGS']['sub'] or ''),
   'A5d a brand whose products are all priced reports no shortfall',
   mc['Total COGS']['sub'])
dc = {c['label']: c for c in R['dog']['cards']}
eq('A5e the all-unpriced brand reports GM % as an em dash, never 0%',
   dc['GM %']['val'], '\u2014')
eq('A5f and its GM $ is zero dollars of PRICED margin, which the sub explains',
   dc['GM $']['val'], '$0.00')
ok('0.0% of invoiced' in (dc['GM $']['sub'] or ''),
   'A5g coverage 0% is stated, so $0.00 cannot read as "we made nothing"',
   dc['GM $']['sub'])

# ── A6 empty states ────────────────────────────────────────────────────────
print('\n== A6. an empty result leaves no stale strip ==')
ok(R['nobody']['rows'] == 1 and 'colspan' in R['nobody']['body'],
   'A6a a brand matching nothing renders ONE row and it is the message row, '
   'never a bare header over an empty tbody (my first expectation here was '
   'the wrong one - the empty state IS a <tr>)', R['nobody']['body'][:120])
eq('A6b and the strip is CLEARED, never left describing the last brand',
   R['nobody']['strip'], '')
ok('No Nonexistent Brand products' in R['nobody']['body'],
   'A6c with the v11.27 message intact')

# ── B. static ──────────────────────────────────────────────────────────────
print('\n== B. one implementation, not a second one ==')
RW = fn('renderWalmartCost')
ok('walmartPnlCogs(mid)' in RW,
   'B1 /!\\ the COGS comes from the SALES tab\'s resolver. A second chain here '
   'would let one tab price a product the other does not (hard rule #1)')
ok('cogsByMaster[' not in RW and 'landed_cost' not in RW,
   'B2 and this function reads neither the cache nor the column directly')
ok('.map(pnlCard)' in RW,
   'B3 the strip goes through pnlCard. v10.49/v10.60: a sixth bespoke card '
   'renderer is how the app ended up with four card markups')
ok('border-radius:10px;padding:14px 16px' not in RW,
   'B4 and no card markup is inlined here')

LW = fn('loadWalmartCost')
ok('loadProductCogs' in LW,
   'B5 the loader fetches COGS. This tab can be entered directly, so it cannot '
   'assume the Sales tab\'s loader has run')
ok(LW.index('loadProductCogs') < LW.index("from('walmart_catalog')"),
   'B6 before the ledger query, so one await chain covers both')

eq('B7 exactly one scorecard host for this tab',
   s.count('id="wmpnl-cost-scorecards"'), 1)
cost_panel = s[s.index('<div id="wmpnl-view-cost"'):s.index('<!-- /wmpnl-view-cost -->')]
ok('wmpnl-cost-scorecards' in cost_panel,
   'B8 and it lives INSIDE the cost panel, so switching tabs hides it. The '
   'v11.12 bug put a Walmart panel outside its own page')
ok(cost_panel.index('wmpnl-cost-scorecards') < cost_panel.index('wmpnl-cost-thead'),
   'B9 above the table, where every other P&L strip sits (rule #4)')

nocom = re.sub(r'<!--.*?-->', '', s, flags=re.S)
ok('What Walmart pays us per each' not in nocom,
   'B10 the tab subtitle no longer describes a cost sheet. It is the P&L now')
ok('Invoiced revenue, COGS and margin' in nocom,
   'B11 and says what it actually reports')

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
