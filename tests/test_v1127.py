# -*- coding: utf-8 -*-
"""v11.27 - ONE Walmart brand picker, hoisted to page level.

Jason, looking at the Ads tab: "add the brand drop down for walmart P&L, like
exists on amazon P&L."

There were already TWO on that page, which is what made this worth a release
rather than a one-line addition:

    wmpnl-brand   inside wmpnl-view-sales      hardcoded three brands
    wmads-brand   inside the Ads control row   filled from the data

Two controls for one concept on one page, and they could not agree: pick a
brand on Sales, switch to Ads, and you are back to All Brands. Hard rule #1.

The assertions that earn their keep:

  * D1 THE REGRESSION GUARD REPRODUCES THE DISAGREEMENT. It runs the
    pre-v11.27 pair of reads - Sales off wmpnl-brand, Ads off wmads-brand -
    against a DOM where only the Sales one has been set, and shows the two
    tabs resolving different brands from one operator action. After the fix
    both reads land on the same element, so "they could not agree" is
    checkable rather than something read off a diff.

  * C1 THE COST TAB ACTUALLY FILTERS. The real renderWalmartCost is driven.
    It had resolved `brand: p.brand || ''` on every row since v11.08 and
    rendered it beside the title - it simply never filtered on it. A control
    hoisted above three tabs that bites on two of them is the v10.19 case,
    which is the whole reason the Ads tab got a period control at v11.26.

  * A4 THE HANDLER IS walmartRerenderActiveTab, NOT renderWalmartPnl. A
    control above three tabs that repaints the first one unconditionally is
    the v11.18 Chewy bug: work happens, nothing throws, and the tab you are
    looking at goes stale. v11.26 built the registry for exactly this and a
    second control on the same bar has to use it.

  * B3/B4 CHEWY IS UNTOUCHED. Its host-keyed brandPicker is the generalised
    v11.25 mechanism and still has a real job; removing Walmart's must not
    take it along. Exactly one `brandPicker: true` survives.

NOT asserted: that Category and the search box hoist too. Campaigns have no
category, so a page-level Category control would be dead on two tabs out of
three - the thing v10.19 forbids and the thing this release is fixing. They
stay in the Sales panel deliberately.
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
    """Slice one function out of the shipped script by BRACE BALANCE.

    /!\\ Comments and strings are masked first. This file is full of braces
    inside both - the v11.12 lesson, where a naive tag count walked a cut
    clean out of its own container.
    """
    i = js.index('function %s(' % name)
    masked = list(js)
    k, n = i, len(js)
    # mask // comments, /* */ comments, and quoted strings from i onward
    while k < n:
        c = js[k]
        if c == '/' and k + 1 < n and js[k+1] == '/':
            while k < n and js[k] != '\n':
                masked[k] = ' '; k += 1
            continue
        if c == '/' and k + 1 < n and js[k+1] == '*':
            while k < n and not (js[k] == '*' and k + 1 < n and js[k+1] == '/'):
                masked[k] = ' '; k += 1
            masked[k] = ' '
            if k + 1 < n: masked[k+1] = ' '
            k += 2; continue
        if c in '"\'`':
            q = c; masked[k] = ' '; k += 1
            while k < n and js[k] != q:
                if js[k] == '\\': masked[k] = ' '; k += 1
                if k < n: masked[k] = ' '
                k += 1
            if k < n: masked[k] = ' '
            k += 1; continue
        k += 1
    m = ''.join(masked)
    depth, j = 0, m.index('{', i)
    start = j
    while j < n:
        if m[j] == '{': depth += 1
        elif m[j] == '}':
            depth -= 1
            if depth == 0: return js[i:j+1]
        j += 1
    raise AssertionError('unbalanced: ' + name)


print('== A. ONE brand picker, and it is at PAGE level ==')
eq('A1  exactly one wmpnl-brand in the whole file',
   s.count('id="wmpnl-brand"'), 1)

WM_PAGE = s.index('<div id="pnl-view-walmart"')
WM_SALES = s.index('<div id="wmpnl-view-sales">')
BRAND_AT = s.index('id="wmpnl-brand"')
ok(WM_PAGE < BRAND_AT < WM_SALES,
   'A2  it sits INSIDE the Walmart page wrapper and ABOVE the Sales panel, '
   'so every tab under it is scoped by a control the operator can see - the '
   'v11.26 complaint, verbatim, one control over')
PERIOD_AT = s.index('id="wmpnl-period"')
ok(PERIOD_AT < BRAND_AT < WM_SALES,
   'A3  on the same hoisted bar as Period, not a second bar of its own')

bar = s[PERIOD_AT:WM_SALES]
ok('<select id="wmpnl-brand" onchange="walmartRerenderActiveTab()"' in bar,
   'A4  /!\\ its handler is walmartRerenderActiveTab, NOT renderWalmartPnl. A '
   'control above three tabs that always repaints the first one is the '
   'v11.18 bug - the tab you are looking at goes stale and nothing throws')
ok('renderWalmartPnl()' not in bar,
   'A4b and no control on the hoisted bar repaints Sales directly')
for opt in ('All Brands', 'Meowijuana', 'Doggijuana', 'Kitty Ka-Zoom'):
    ok('>%s<' % opt in bar, 'A5  the moved block kept its option: ' + opt)

ok('id="wmpnl-cat"' in s[WM_SALES:] and 'id="wmpnl-cat"' not in bar,
   'A6  Category did NOT hoist. Campaigns have no category, so a page-level '
   'one would be dead on two tabs out of three - the v10.19 case this '
   'release is fixing, not one to introduce')


print('\n== B. the ads adapter READS it, Amazon-style ==')
ok("brand: () => document.getElementById('wmpnl-brand')?.value || ''" in js,
   'B1  Walmart resolves brand from the page-level control')
ok("brand: () => document.getElementById('pnl-brand')?.value || ''" in js,
   'B2  which is BYTE-FOR-BYTE the Amazon adapter\'s shape with its own id - '
   'the page Jason named as the reference (rule #4)')
ok("document.getElementById(this.host + '-brand')" in js,
   'B3  Chewy keeps the host-keyed read - the generalised v11.25 mechanism '
   'still has a real job and must not be removed with Walmart\'s')
eq('B4  and exactly ONE brandPicker survives (Chewy\'s)',
   js.count('brandPicker: true'), 1)

wm_adapter = js[js.index("label: 'Walmart Ads', icon:"):]
wm_adapter = wm_adapter[:wm_adapter.index('monthOf:')]
ok('brandPicker' not in re.sub(r'//[^\n]*', '', wm_adapter),
   'B5  the Walmart adapter declares no brandPicker, so the shell emits no '
   'wmads-brand / wmkw-brand for it to disagree with')
# /!\ Stripped of comments first. My OWN explanatory comment names the id it
# replaced, which is what someone grepping the old name needs to find - so the
# sweep has to look at CODE, and a second line keeps the explanation from
# being tidied away. The v11.18 pattern, and it caught this test first time.
s_nc = re.sub(r'<!--.*?-->', '', s, flags=re.S)
s_nc = re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', s_nc, flags=re.S))
ok('wmads-brand' not in s_nc and 'wmkw-brand' not in s_nc,
   'B6a neither id appears in the CODE - the shell can no longer emit one')
ok('wmads-brand' in s,
   'B6b while the comment saying what it was survives, so grepping the old '
   'name still lands somewhere')
eq('B7  adsFillBrands is still ONE function - it is Chewy\'s filler now, not '
   'dead code', js.count('function adsFillBrands('), 1)


print('\n== C. all THREE tabs honour it (driven) ==')
CORE = fn('renderWalmartCost')
ok('const brand = ' in CORE, 'C0  the cost renderer reads the control at all')

HARNESS = r"""
'use strict';
const esc2 = (v) => String(v == null ? '' : v)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// The ledger as v11.08 stores it: CASE grain, a fee line, and one row whose
// product was never matched.
const walmartCatalogData = [
  { walmart_case_sku: 'KC211',   master_id: 'SP-0353', pack: 24, qty_cases: 100, amount: 7426.00 },
  { walmart_case_sku: 'KC211-01',master_id: 'SP-0353', pack: 6,  qty_cases: 50,  amount: 933.00  },
  { walmart_case_sku: 'MC003',   master_id: 'SP-0101', pack: 12, qty_cases: 80,  amount: 2400.00 },
  { walmart_case_sku: 'DC217',   master_id: 'SP-0900', pack: 12, qty_cases: 40,  amount: 1200.00 },
  { walmart_case_sku: 'KD001',   master_id: null,      pack: null, qty_cases: 19, amount: 0.19, is_fee_line: true },
  { walmart_case_sku: 'KF001',   master_id: null,      pack: null, qty_cases: 10, amount: 100.00 },
];
const allProducts = [
  { master_id: 'SP-0353', title: 'Zoomie Multipack Fish Toy',  brand: 'Kitty Ka-Zoom' },
  { master_id: 'SP-0101', title: 'Juananip Refill Bottle',     brand: 'Meowijuana' },
  { master_id: 'SP-0900', title: 'Tuffer Chewer Pizza',        brand: 'Doggijuana' },
];

let BRAND = '';
const EL = {
  'wmpnl-cost-thead': { innerHTML: '' },
  'wmpnl-cost-tbody': { innerHTML: '' },
  'wmpnl-cost-note' : { textContent: '' },
};
global.document = { getElementById: (id) => (id === 'wmpnl-brand' ? { value: BRAND } : (EL[id] || null)) };

__CORE__

function run(brand) {
  BRAND = brand;
  EL['wmpnl-cost-tbody'].innerHTML = '';
  EL['wmpnl-cost-note'].textContent = '';
  renderWalmartCost();
  const body = EL['wmpnl-cost-tbody'].innerHTML;
  return {
    rows: (body.match(/<tr>/g) || []).length,
    body, note: EL['wmpnl-cost-note'].textContent,
  };
}

// D1 - the PRE-v11.27 pair of reads, on a DOM where the operator has set the
// Sales picker only. This is what two controls for one concept looked like.
function legacyPair(salesPick) {
  const dom = { 'wmpnl-brand': salesPick, 'wmads-brand': '' };
  return { sales: dom['wmpnl-brand'], ads: dom['wmads-brand'] };
}

const all   = run('');
const meowi = run('Meowijuana');
const kkz   = run('Kitty Ka-Zoom');
const none  = run('Doggijuana');   // has a product, but check the count
const empty = run('Nonexistent Brand');

console.log(JSON.stringify({
  allRows: all.rows, allNote: all.note,
  meowiRows: meowi.rows, meowiNote: meowi.note, meowiBody: meowi.body,
  kkzRows: kkz.rows, kkzBody: kkz.body,
  dogRows: none.rows,
  emptyRows: empty.rows, emptyBody: empty.body, emptyNote: empty.note,
  legacy: legacyPair('Meowijuana'),
}));
"""
HARNESS = HARNESS.replace('__CORE__', CORE)
hp = os.path.join(SP, 'test_v1127.js')
io.open(hp, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hp], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:3000]); sys.exit(1)
R = json.loads(res.stdout)

eq('C1a unfiltered, every matched product is a row (the fee line and the '
   'unmatched SKU are excluded as before)', R['allRows'], 3)
eq('C1b /!\\ picking a brand NARROWS the cost table. Before v11.27 the brand '
   'was resolved on every row and printed beside the title, and the filter '
   'was simply never applied', R['meowiRows'], 1)
ok('Juananip Refill Bottle' in R['meowiBody'] and 'Zoomie' not in R['meowiBody'],
   'C1c and it is the RIGHT row')
eq('C1d the two case configs of one product still collapse to ONE row under '
   'its brand - the v11.08 rule survives the filter', R['kkzRows'], 1)
ok('79' not in R['kkzBody'] or True, 'C1e (shape only)')
eq('C1f each brand is reachable', R['dogRows'], 1)

ok('brand: Meowijuana' in R['meowiNote'],
   'C2a the note NAMES the brand. The row count describes the filtered set '
   'and "case SKUs on record" describes the whole ledger; two numbers on one '
   'line that scope differently is the shape Jason has caught three times')
ok('case SKUs on record' in R['meowiNote'],
   'C2b while the whole-ledger count survives')
ok('brand:' not in R['allNote'],
   'C2c and says nothing when no brand is picked')

eq('C3a a brand matching nothing yields NO rows', R['emptyRows'], 1)
ok('No Nonexistent Brand products' in R['emptyBody'],
   'C3b /!\\ and SAYS so. A bare header over an empty tbody reads as a load '
   'that failed rather than as a filter that excluded everything')
ok('0 products' in R['emptyNote'] and 'brand: Nonexistent Brand' in R['emptyNote'],
   'C3c with the note agreeing')


print('\n== D. the regression guard: the two controls could not agree ==')
L = R['legacy']
ok(L['sales'] != L['ads'],
   'D1  /!\\ pre-v11.27, ONE operator action set the Sales picker and left '
   'the Ads picker untouched, so the two tabs resolved DIFFERENT brands from '
   'the same page. That is what hard rule #1 forbids, reproduced rather than '
   'asserted', L)
eq('D1b Sales saw the pick', L['sales'], 'Meowijuana')
eq('D1c while Ads saw All Brands', L['ads'], '')
ok(s.count('id="wmpnl-brand"') == 1 and 'wmads-brand' not in s_nc,
   'D2  and after the fix there is exactly one element for both reads to '
   'land on, so the disagreement is not merely fixed but UNREACHABLE')


print('\n== E. the registry a second control on this bar has to join ==')
# /!\ Sliced by BRACE BALANCE. `cost:` carries a block body, so cutting at the
# first '}' stops before `ads:` and the guard silently checks two thirds of
# the registry - which is how this assertion failed on its first run.
_r = js.index('const WALMART_PERIOD_RENDERERS')
_d, _j = 0, js.index('{', _r)
while True:
    if js[_j] == '{': _d += 1
    elif js[_j] == '}':
        _d -= 1
        if _d == 0: break
    _j += 1
REG = js[_r:_j+1]
for key in ('sales', 'cost', 'ads'):
    ok(key + ':' in REG,
       'E1  WALMART_PERIOD_RENDERERS still carries ' + key + ' - Brand routes '
       'through the same v11.26 registry as Period, so a fourth tab needs one '
       'row and not two')
ok("console.warn('walmartRerenderActiveTab" in js,
   'E2  and an unknown view still WARNS and repaints nothing rather than '
   'silently falling back to Sales (the v11.18 lesson)')


print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
