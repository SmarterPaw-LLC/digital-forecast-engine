# -*- coding: utf-8 -*-
"""v10.69 - Chewy Break-Even: show the working.

Jason told Blake, in writing: "I will add in the calculations used as tooltips
so that you can check them (as well as a viewer to see the data source)."

The column headers already stated the FORMULAS (v10.37 / v10.40), but no cell
stated ITS OWN NUMBERS — so a reviewer could read the method and still not
verify a single SKU. This ships three things:
  1. chewyPnlCogsSource() - names WHICH field won the COGS fallback chain,
     which is the open accuracy question on this tab (dtc_cogs / amazon_cogs
     carry fulfilment costs that a 1P pallet never incurs).
  2. per-row tooltips carrying that row's actual figures;
  3. an audit viewer: every input, its value, and the table it came from.

What is most worth guarding is that the viewer and the tooltips REPORT THE
ROW, not a recomputation of it. If they ever recompute, they can disagree with
the cell they are explaining — which is worse than no explanation at all.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond: passed += 1; print('  ok  ' + name)
    else:    failed += 1; print('  FAIL  ' + name)

def fn(name):
    i = js.index('function %s(' % name)
    j = js.index('{', i); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1

# ---------------------------------------------------------------- A. static
print('\n== A. ONE declaration each (hard rule #1) ==')

ok(js.count('const CHEWY_COGS_SOURCES') == 1, 'COGS-source labels declared once')
ok(js.count('function chewyPnlCogsSource(') == 1, 'chewyPnlCogsSource defined once')
ok(js.count('function openChewyBeAudit(') == 1, 'openChewyBeAudit defined once')
ok(js.count('function closeChewyBeAudit(') == 1, 'closeChewyBeAudit defined once')
ok(len(re.findall(r'(?:let|const|var)\s+chewyBeAuditRows', js)) == 1,
   'chewyBeAuditRows declared once')

# the v10.8 class: called-but-undefined. This is the bug I nearly shipped.
for f in ['openChewyBeAudit', 'closeChewyBeAudit', 'chewyPnlCogsSource']:
    ok(len(re.findall(r'(?<![\w.])' + f + r'\s*\(', js)) >= 2,
       '%s is both defined AND called' % f)

# the v10.65 class: self-referencing declaration (legal syntax, TDZ at runtime)
viewer = fn('openChewyBeAudit')
selfref = [m.group(1) for m in re.finditer(
    r'(?:let|const|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]{0,200})', viewer)
    if re.search(r'(?<![\w.])' + re.escape(m.group(1)) + r'\s*\(', m.group(2))]
ok(not selfref, 'no self-referencing declaration in the viewer (%s)' % (selfref or 'none'))

print('\n== B. the COGS fallback chain is reported, not re-invented ==')

src_fn = fn('chewyPnlCogsSource')
cogs_fn = fn('chewyPnlCogs')
# both must walk the SAME order, or the provenance label lies about the value
order_real = re.findall(r'c\.(chewy_cogs|landed_cost|dtc_cogs|amazon_cogs)', cogs_fn)
order_src  = re.findall(r"'(chewy_cogs|landed_cost|dtc_cogs|amazon_cogs)'", src_fn)
ok(order_real == ['chewy_cogs', 'landed_cost', 'dtc_cogs', 'amazon_cogs'],
   'chewyPnlCogs walks chewy -> landed -> dtc -> amazon')
ok(order_src == order_real,
   'chewyPnlCogsSource walks the IDENTICAL order (else the label lies)')

labels = js[js.index('const CHEWY_COGS_SOURCES'):]
labels = labels[:labels.index('\n};')]
ok(labels.count('warn: true') == 2 and labels.count('warn: false') == 2,
   'exactly the two wrong-basis fields are flagged warn:true')
ok(re.search(r'dtc_cogs:[^\n]*warn: true', labels) is not None,
   '  dtc_cogs is flagged (carries DTC shipping + overhead)')
ok(re.search(r'amazon_cogs:[^\n]*warn: true', labels) is not None,
   '  amazon_cogs is flagged (carries the FBA fulfilment fee)')
ok(re.search(r'chewy_cogs:[^\n]*warn: false', labels) is not None,
   '  chewy_cogs is NOT flagged (it is the true basis)')

print('\n== C. wiring ==')

be = js[js.index('function renderChewyBreakeven'):]
be = be[:be.index('\nfunction ', 10)]

ok('cogsSrc: (typeof chewyPnlCogsSource' in be, 'the row carries its cogsSrc')
ok('chewyBeAuditRows = allRows;' in be,
   'the viewer cache is ALL rows, not the quick-filtered subset')
ok(be.index('chewyBeAuditRows = allRows;') < be.index('rows.sort((x, y) => {'),
   '  and it is set before the sort')
ok('TIPS.contribution' in be and 'TIPS.beRoas' in be,
   'tooltips are wired into the GM $/u and BE ROAS cells')
ok("cell('right', $(r.contribution), r.contribution <= 0 ? 'color:' + RED : '', TIPS.contribution)" in be,
   '  via the 4th (tip) arg of the shared cell() helper, not a bespoke td')
ok(be.count("openChewyBeAudit('${String(r.chewy_sku") == 1,
   'exactly one audit button per row, keyed on chewy_sku')
ok('event.stopPropagation();openChewyBeAudit' in be,
   '  and it does not also toggle the row')

# v10.70 / v7.53 class: nested quotes in an onclick silently produce a NO-OP
# handler. Found by driving the real generated markup in a browser - a sku
# containing a double quote rendered a button whose click did nothing.
btn = be[be.index('openChewyBeAudit(${String') - 400:] if 'openChewyBeAudit(${String' in be       else be[be.index("openChewyBeAudit('${String") - 400:]
btn = btn[:btn.index('</button>')]
ok(r'.replace(/\\/g' in btn, 'onclick escapes BACKSLASH (JS string literal)')
ok(r'''.replace(/'/g''' in btn, 'onclick escapes APOSTROPHE (single-quoted JS string)')
ok(r'''.replace(/"/g''' in btn, 'onclick escapes DOUBLE QUOTE (double-quoted HTML attr)')
ok(btn.index(r'.replace(/\\/g') < btn.index(r'''.replace(/'/g'''),
   '  backslash is escaped FIRST (else it mangles the later escapes)')
ok(btn.index(r'''.replace(/'/g''') < btn.index(r'''.replace(/"/g'''),
   '  then apostrophe, then double quote (&quot; decodes inside the JS string)')

# the tooltips must read the row, never recompute the economics
tips = be[be.index('const TIPS = {'):be.index('const CELLS = {')]
ok('chewyBreakevenEcon' not in tips,
   'the tooltips do NOT re-run the economics (they report r.*)')
ok('r.beRoas' in tips and 'r.contribution' in tips and 'r.listPrice' in tips,
   '  they read the row fields the cells were rendered from')
ok('chewyBreakevenEcon' not in viewer,
   'the viewer does NOT re-run the economics either')

# v4.168 drag guard - a bare click handler closes on drag-out
ok('downOnBackdrop' in viewer,
   'backdrop close uses the v4.168 mousedown+mouseup drag guard')

# --------------------------------------------------------------- D. behaviour
print('\n== D. BEHAVIOUR (real sliced functions driven in node) ==')

HARNESS = r"""
let cogsByMaster = {};
__SOURCES__
__SRCFN__
__STACKSTUB__
let chewyBeAuditRows = [];

// --- minimal DOM so the viewer can mount
const _nodes = {};
function _mk(tag) {
  return {
    tagName: tag, id: '', style: { cssText: '', display: '' },
    innerHTML: '', children: [],
    addEventListener() {}, appendChild(c) { this.children.push(c); },
  };
}
const document = {
  getElementById: id => _nodes[id] || null,
  createElement: tag => _mk(tag),
  body: { appendChild(el) { if (el.id) _nodes[el.id] = el; } },
};
__VIEWER__
__CLOSER__

const out = { src: {}, viewer: {} };

// 1. the fallback chain, every position
const chains = {
  chewy:   { chewy_cogs: 1.11, landed_cost: 2, dtc_cogs: 3, amazon_cogs: 4 },
  landed:  { chewy_cogs: null, landed_cost: 2.22, dtc_cogs: 3, amazon_cogs: 4 },
  dtc:     { chewy_cogs: null, landed_cost: null, dtc_cogs: 3.33, amazon_cogs: 4 },
  amazon:  { chewy_cogs: null, landed_cost: null, dtc_cogs: null, amazon_cogs: 4.44 },
  allnull: { chewy_cogs: null, landed_cost: null, dtc_cogs: null, amazon_cogs: null },
  zero:    { chewy_cogs: 0,    landed_cost: 2,    dtc_cogs: 3,    amazon_cogs: 4 },
};
for (const [k, v] of Object.entries(chains)) {
  cogsByMaster = { 'SP-1': v };
  const r = chewyPnlCogsSource('SP-1');
  out.src[k] = { field: r.field, value: r.value, warn: r.warn, label: r.label };
}
cogsByMaster = {};
out.src.norow = (() => { const r = chewyPnlCogsSource('SP-NOPE');
  return { field: r.field, warn: r.warn, label: r.label }; })();

// 2. the viewer, driven on a hand-checkable row
//    wholesale 4.00, 25% allowances -> net 3.00, cogs 1.00 -> contribution 2.00
//    list 8.99 -> BE ROAS = 8.99/2.00 = 449.5%
const row = {
  master_id: 'SP-1', chewy_sku: '1365718', title: 'Test Product',
  wholesale: 4.0, uom: 'CS', caseQty: 12, rawCost: 48.0,
  cogs: 1.0, net: 3.0, contribution: 2.0,
  listPrice: 8.99, beRoas: 449.5, beAcos: 22.2, gmPct: 50.0,
  spend: 100.0, direct_units: 40, direct_sales: 359.6,
  autoship_recurring: 90.0, directRoas: 359.6, realisedRoas: 449.6,
  headroom: 0.1, cpu: 2.5,
  cogsSrc: { value: 1.0, field: 'dtc_cogs', label: 'product_cogs.dtc_cogs',
             note: 'WRONG BASIS - carries DTC shipping.', warn: true },
};
chewyBeAuditRows = [row];
openChewyBeAudit('1365718');
const ov = _nodes['chewyBeAuditOverlay'];
out.viewer.mounted = !!ov;
out.viewer.html = ov ? ov.innerHTML : '';
out.viewer.display = ov ? ov.style.display : '';

// a SKU that is not loaded must not throw
let alerted = false;
const alert = () => { alerted = true; };
try { openChewyBeAudit('NOPE'); out.viewer.missingThrew = false; }
catch (e) { out.viewer.missingThrew = true; }

closeChewyBeAudit();
out.viewer.closedDisplay = _nodes['chewyBeAuditOverlay'].style.display;
out.viewer.closedHtml = _nodes['chewyBeAuditOverlay'].innerHTML;

console.log(JSON.stringify(out));
"""

sources = js[js.index('const CHEWY_COGS_SOURCES'):]
sources = sources[:sources.index('\n};') + 3]

HARNESS = (HARNESS
  .replace('__SOURCES__', sources)
  .replace('__SRCFN__', src_fn)
  .replace('__VIEWER__', viewer)
  .replace('__CLOSER__', fn('closeChewyBeAudit'))
  # v11.04 ⚠ openChewyBeAudit now resolves the allowance over its own
  # window, so the harness has to supply that dep or the REAL function cannot
  # run. Harness drift of the documented v10.43 / v10.45 / v10.97 kind: the
  # stub is lifted in so every original assertion still exercises the real
  # code path rather than being re-pointed at a copy.
  .replace('__STACKSTUB__',
           "function getChewyBreakevenDateRange() { "
           "return { from: '2026-01-01', to: '2026-10-27' }; }\n"
           "function chewyAllowanceStack() { return "
           "{ standingPct: 26.5, byCat: { coop_marketing: 16, damages: 2, "
           "freight: 1.5, autoship: 5, satisfaction_guarantee: 2 }, "
           "source: 'invoices' }; }"))

hpath = os.path.join(SP, 'test_v1069.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
res = json.loads(subprocess.run(['node', hpath],
    capture_output=True, text=True, check=True).stdout)

print('\n-- the fallback chain --')
S = res['src']
ok(S['chewy']['field'] == 'chewy_cogs' and S['chewy']['warn'] is False,
   'chewy_cogs wins first, not flagged')
ok(S['landed']['field'] == 'landed_cost' and S['landed']['warn'] is False,
   'landed_cost is next, not flagged (it UNDERSTATES, it is not wrong-basis)')
ok(S['dtc']['field'] == 'dtc_cogs' and S['dtc']['warn'] is True,
   'dtc_cogs is flagged as wrong basis')
ok(S['amazon']['field'] == 'amazon_cogs' and S['amazon']['warn'] is True,
   'amazon_cogs is flagged as wrong basis')
ok(S['chewy']['value'] == 1.11 and S['dtc']['value'] == 3.33,
   'the reported VALUE is the one the chain actually resolved')
ok(S['zero']['field'] == 'chewy_cogs' and S['zero']['value'] == 0,
   'a genuine 0 chewy_cogs still wins (?? not ||)')
ok(S['allnull']['field'] is None and S['allnull']['warn'] is True,
   'all-null reports no field and flags it')
ok(res['src']['norow']['warn'] is True and 'no product_cogs' in res['src']['norow']['label'],
   'a missing product_cogs row is named, not silently zero')

print('\n-- the viewer --')
V = res['viewer']
ok(V['mounted'], 'the overlay mounts')
ok(V['display'] == 'flex', '  and is shown')
h = V['html']
ok('1365718' in h and 'Test Product' in h, 'it names the SKU + product')

# every INPUT must appear with its value AND its source table
for label, val, src in [
    ('Wholesale / each',        '$4.0000', 'chewy_catalog.cost'),
    ('Standing allowances',     '25.0%',   'chewy_rebates'),
    ('COGS / unit',             '$1.0000', 'product_cogs.dtc_cogs'),
    ('Chewy list price',        '$8.99',   'chewy_ad_spend'),
    ('Recurring autoship',      '$90.00',  'chewy_ad_spend'),
]:
    ok(label in h, 'input listed: %s' % label)
    ok(val in h,   '  value shown: %s' % val)
    ok(src in h,   '  source named: %s' % src)

ok('$3.0000' in h, 'net-to-us is shown ($4.00 x (1 - 25%))')
ok('$2.0000' in h, 'GM $/u is shown (net - COGS)')
ok('449.5%' in h,  'BE ROAS is shown')
ok('wholesale x (1 - allowances)' in h, 'the net-to-us formula is named')
ok('net to us - COGS' in h, 'the contribution formula is named')
ok('BE ROAS = list' in h, 'the BE ROAS formula is named')

# the allowance stack must be itemised, not just totalled
for cat in ['coop_marketing', 'damages', 'freight', 'autoship', 'satisfaction_guarantee']:
    ok(cat in h, '  allowance itemised: %s' % cat)

# the wrong-basis warning has to be loud, since it is the accuracy question
ok('WRONG BASIS' in h, 'a wrong-basis COGS surfaces its warning in the viewer')
ok('--sp-orange' in h, '  and it is coloured, not buried in body text')

# the retail-vs-wholesale explanation is the thing Blake actually asked about
ok('RETAIL' in h and 'wholesale' in h,
   'the viewer explains why BE ROAS reads higher than Amazon (retail vs wholesale)')
ok('unit count cancels' in h, '  including why it stays comparable to Realised ROAS')

ok('undefined' not in h, 'no leaked undefined')
ok('NaN' not in h, 'no leaked NaN')
ok('[object' not in h, 'no leaked [object Object]')

ok(V['missingThrew'] is False, 'an unloaded SKU does not throw')
ok(V['closedDisplay'] == 'none', 'close hides the overlay')
ok(V['closedHtml'] == '', '  and clears its content')

# ------------------------------------------------------------------- report
print('\n%s' % ('-' * 58))
print('v10.69/70: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
