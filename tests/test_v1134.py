#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.34 - the uploader's "not in catalog" report becomes clickable.

Jason, on the line an upload leaves behind:
"whenever i see a report like this in the uploader tool, allow me to click to
that product on the products page."

Four uploaders report that shape, so it is ONE renderer and ONE destination.

  * A  the REAL uploadUnmatchedChips, with a recording DOM.
    A4 THE INJECTION GUARD. Every id in these lists comes out of an uploaded
       file. A chip addresses its item by INDEX (the v11.23 checkbox rule),
       so a Chewy SKU carrying quotes, a backslash and markup renders as
       TEXT and reaches no attribute.
  * B  the REAL openProductsForTerm, with a recording DOM.
    B2 pins the ORDER against showPage, which repaints the page it navigates
       to - setting the controls first would have them overwritten.
  * C  THE DRIFT GUARD. The REAL prodRowMatchesFilters and the REAL
       prodFindByTerm are driven over a product carrying all nine searchable
       fields, and required to agree on every one. A field the table searches
       and the chip does not is the rule #1 divergence this release exists to
       avoid - one chip and one table apart.
  * D  THE v8.76 REGRESSION GUARD. clearPageFiltersForTopProductChip aimed at
       prod-brand / prod-search / prod-filter, which have never existed. The
       pre-v11.34 ids are run against the real markup and proven dead.
  * E  static: one definition each, all four uploaders clearing AND rendering,
       the status lines still on textContent, .dz-warn finally given a rule.
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


def _balance(i):
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
    raise RuntimeError('unbalanced slice at %d' % i)


def fn(name):
    i = js.index('function %s(' % name)
    head = 'async ' if js[max(0, i - 6):i] == 'async ' else ''
    k = js.index('(', i)
    depth = 0
    while k < len(js):
        if js[k] == '(': depth += 1
        elif js[k] == ')':
            depth -= 1
            if depth == 0: break
        k += 1
    brace = js.index('{', k)
    return head + js[i:brace] + _balance(brace)


def run_node(path, src):
    io.open(path, 'w', encoding='utf-8', newline='\n').write(src)
    r = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print(r.stdout); print(r.stderr); sys.exit(1)
    return json.loads(r.stdout)


# A recording DOM small enough to read, big enough to drive these two
# functions: elements remember what was set on them and what order it
# happened in, and innerHTML stays a STRING so a chip's markup can be
# asserted character for character rather than through a parser.
DOM = r"""
const LOG = [];
function mkEl(id) {
  const kids = [];
  const el = {
    id, value: '', className: '', innerHTML: '', textContent: '',
    style: {}, children: kids, parentElement: null,
    scrollIntoView() { LOG.push('scroll:' + id); },
    remove() {
      const p = el.parentElement; if (!p) return;
      const i = p.children.indexOf(el); if (i >= 0) p.children.splice(i, 1);
      el.parentElement = null; if (EL[el.id] === el) delete EL[el.id];
      LOG.push('remove:' + el.id);
    },
    insertBefore(node, ref) {
      node.parentElement = el;
      const i = ref ? kids.indexOf(ref) : -1;
      if (i >= 0) kids.splice(i, 0, node); else kids.push(node);
      if (node.id) EL[node.id] = node;          // so getElementById can find it
      LOG.push('insert:' + (node.id || '?'));
      return node;
    },
    get nextSibling() {
      const p = el.parentElement; if (!p) return null;
      const i = p.children.indexOf(el);
      return (i >= 0 && i + 1 < p.children.length) ? p.children[i + 1] : null;
    },
  };
  return el;
}
const EL = {};
const HOST = mkEl('host');
function mount(id) { const e = mkEl(id); e.parentElement = HOST; HOST.children.push(e); EL[id] = e; return e; }
global.document = {
  getElementById: id => EL[id] || null,
  createElement: () => mkEl(''),
};
global.getComputedStyle = () => ({ display: 'block' });
function esc2(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
"""

CHIPS = DOM + '\n' + fn('prodSearchHaystack') + '\n' + fn('prodFindByTerm') + '\n' \
      + js[js.index('const _uploadUnmatched = {};'):js.index('const UPLOAD_UNMATCHED_SHOWN = 12;') + 34] \
      + '\n' + fn('uploadUnmatchedGo') + '\n' + fn('uploadUnmatchedChips') + '\n'


# ═════════════════════════════════════════════════ A. uploadUnmatchedChips
print('== A. the real uploadUnmatchedChips ==')

A = run_node(os.path.join(SP, '_v1134_a.js'), CHIPS + r"""
let allProducts = [
  { master_id: 'SP-0353', title: 'Zoomie Multipack Fish Toy', asin: 'B01AAAA111',
    sp_sku: 'SP-0353', shopify_sku: '', chewy_sku: '', walmart_item_id: '', barcode: '', short_name: '' },
  { master_id: 'SP-0999', title: 'Catnip Spray 4oz', asin: '',
    sp_sku: 'KC-SPRAY-4', shopify_sku: 'SHOP-SPRAY', chewy_sku: '', walmart_item_id: '', barcode: '', short_name: '' },
];
const out = {};

// --- A1 an EMPTY list clears a row that is already there -----------------
mount('st-a');
uploadUnmatchedChips('st-a', [{ id: 'B0ZZZZ' }], 'ASIN');
out.a1_rowAfterFirst = !!document.getElementById('st-a-unmatched');
uploadUnmatchedChips('st-a', [], 'ASIN');
out.a1_rowAfterClear = !!document.getElementById('st-a-unmatched');
out.a1_cacheAfterClear = (_uploadUnmatched['st-a'] || []).length;

// --- A2 an id nothing carries ------------------------------------------
mount('st-b');
uploadUnmatchedChips('st-b', [{ id: 'B0NOPE999', label: 'Mystery Parent Listing' }], 'ASIN');
const b = document.getElementById('st-b-unmatched');
out.a2_html = b.innerHTML;
out.a2_class = b.className;
out.a2_marginTop = b.style.marginTop;
out.a2_go = _uploadUnmatched['st-b'][0].go;

// --- A3 resolves through the SECOND id (the FBA seller-SKU case) --------
mount('st-c');
uploadUnmatchedChips('st-c', [{ id: 'B0NOTANASIN', label: 'Catnip Spray 4oz', alt: 'SHOP-SPRAY' }], 'ASIN');
out.a3_html = document.getElementById('st-c-unmatched').innerHTML;
out.a3_go = _uploadUnmatched['st-c'][0].go;

// --- A3b resolves on the FIRST id ---------------------------------------
mount('st-d');
uploadUnmatchedChips('st-d', [{ id: 'B01AAAA111' }], 'ASIN');
out.a3b_html = document.getElementById('st-d-unmatched').innerHTML;
out.a3b_go = _uploadUnmatched['st-d'][0].go;

// --- A4 THE INJECTION GUARD ---------------------------------------------
const NASTY = 'O\'Brien "Max" \\ <b>bold</b> & 50% , ;';
mount('st-e');
uploadUnmatchedChips('st-e', [{ id: NASTY, label: NASTY }], 'Chewy SKU');
out.a4_html = document.getElementById('st-e-unmatched').innerHTML;
out.a4_go = _uploadUnmatched['st-e'][0].go;

// --- A5 the cap ----------------------------------------------------------
const many = [];
for (let i = 0; i < 15; i++) many.push({ id: 'SKU-' + i });
mount('st-f');
uploadUnmatchedChips('st-f', many, 'Chewy SKU');
const f = document.getElementById('st-f-unmatched').innerHTML;
out.a5_buttons = (f.match(/<button/g) || []).length;
out.a5_cacheLen = _uploadUnmatched['st-f'].length;
out.a5_more = /\+(\d+) more/.exec(f) ? Number(/\+(\d+) more/.exec(f)[1]) : null;
out.a5_moreTitleHasLast = f.indexOf('SKU-14') >= 0;
out.a5_moreTitleHasShown = f.indexOf('SKU-0,') >= 0;

// --- A6 placement + the click handler ------------------------------------
mount('st-g'); const after = mount('last-g');
uploadUnmatchedChips('st-g', [{ id: 'SKU-X' }], 'Chewy SKU');
out.a6_order = HOST.children.map(c => c.id).filter(x => /^(st-g|st-g-unmatched|last-g)$/.test(x));
let went = null;
global.openProductsForTerm = t => { went = t; };
uploadUnmatchedGo('st-g', 0);
out.a6_went = went;
uploadUnmatchedGo('st-g', 99);     // out of range must be a no-op, not a throw
out.a6_wentAfterBadIndex = went;
uploadUnmatchedGo('st-nonexistent', 0);

// --- A7 a flex parent drops the top margin -------------------------------
global.getComputedStyle = () => ({ display: 'flex' });
mount('st-h');
uploadUnmatchedChips('st-h', [{ id: 'SKU-Y' }], 'Chewy SKU');
out.a7_marginTop = document.getElementById('st-h-unmatched').style.marginTop || '';

// --- A8 a missing status element is a no-op ------------------------------
uploadUnmatchedChips('st-does-not-exist', [{ id: 'X' }], 'ASIN');
out.a8_ok = true;

console.log(JSON.stringify(out));
""")

eq('A1a a list renders a row', A['a1_rowAfterFirst'], True)
eq('A1b an EMPTY list removes it', A['a1_rowAfterClear'], False)
eq('A1c and empties the cache with it', A['a1_cacheAfterClear'], 0)

ok('<button' in A['a2_html'], 'A2a an unresolved id gets a chip')
ok('class="miss"' in A['a2_html'], 'A2b marked as a miss (dashed)', A['a2_html'])
ok('>B0NOPE999</button>' in A['a2_html'], 'A2c the chip shows the raw id', A['a2_html'])
ok('Nothing in the catalog carries ASIN B0NOPE999' in A['a2_html'],
   'A2d the tooltip says nothing carries it', A['a2_html'])
ok('the file calls it &quot;Mystery Parent Listing&quot;' in A['a2_html'],
   'A2e and names what the FILE called it', A['a2_html'])
eq('A2f the row carries the shared class', A['a2_class'], 'dz-unmatched')
eq('A2g a block parent keeps the top margin', A['a2_marginTop'], '6px')
eq('A2h an unresolved chip searches the id itself', A['a2_go'], 'B0NOPE999')

ok('class=""' in A['a3_html'], 'A3a resolved through alt is NOT a miss', A['a3_html'])
ok('>Catnip Spray 4oz</button>' in A['a3_html'],
   'A3b the chip shows the PRODUCT title, not the id', A['a3_html'])
ok('B0NOTANASIN is on no product, but SHOP-SPRAY matches' in A['a3_html'],
   'A3c the tooltip names which id resolved', A['a3_html'])
eq('A3d and the click searches THAT id', A['a3_go'], 'SHOP-SPRAY')
ok('>Zoomie Multipack Fish Toy</button>' in A['a3b_html'],
   'A3e a first-id hit resolves too', A['a3b_html'])
eq('A3f and searches the first id', A['a3b_go'], 'B01AAAA111')

ok('<b>' not in A['a4_html'], 'A4a THE INJECTION GUARD: no raw <b> reaches the DOM', A['a4_html'])
ok('&lt;b&gt;bold&lt;/b&gt;' in A['a4_html'], 'A4b it renders as TEXT', A['a4_html'])
ok('&#39;Brien' in A['a4_html'], 'A4c the apostrophe is escaped', A['a4_html'])
ok('&quot;Max&quot;' in A['a4_html'], 'A4d so are the quotes', A['a4_html'])
ok('uploadUnmatchedGo(&quot;st-e&quot;,0)' in A['a4_html'],
   'A4e the onclick carries only the status id and an INDEX', A['a4_html'])
ok('O\'Brien' in A['a4_go'] and 'bold' in A['a4_go'],
   'A4f while the cache keeps the value intact for the search', A['a4_go'])

eq('A5a the cap renders 12 chips', A['a5_buttons'], 12)
eq('A5b and caches 12', A['a5_cacheLen'], 12)
eq('A5c the overflow names the remaining 3', A['a5_more'], 3)
eq('A5d which are listed in its tooltip', A['a5_moreTitleHasLast'], True)
eq('A5e and the shown ones are NOT repeated there', A['a5_moreTitleHasShown'], False)

eq('A6a the row is inserted directly after the status line',
   A['a6_order'], ['st-g', 'st-g-unmatched', 'last-g'])
eq('A6b a click resolves its term through the cache', A['a6_went'], 'SKU-X')
eq('A6c an out-of-range index is a no-op, not a throw', A['a6_wentAfterBadIndex'], 'SKU-X')
eq('A7 a flex parent drops the top margin', A['a7_marginTop'], '')
eq('A8 a missing status element is a no-op', A['a8_ok'], True)


# ═════════════════════════════════════════════════ B. openProductsForTerm
print('== B. the real openProductsForTerm ==')

B = run_node(os.path.join(SP, '_v1134_b.js'), DOM + '\n' + fn('openProductsForTerm') + r"""
['prodSrch', 'prodBrand', 'prodFilter', 'prodCat', 'prodCount'].forEach(mount);
EL.prodBrand.value = 'Doggijuana';
EL.prodFilter.value = 'needs_review';
EL.prodCat.value = 'Toys';
EL.prodSrch.value = 'old search';

let topProductFilterId = 'SP-0001';
function setTopProductFilter(v) { LOG.push('setTopProductFilter:' + v); topProductFilterId = v || null; }
function showPage(page, el) { LOG.push('showPage:' + page + ':' + (el ? el.id : 'null')); }
function navTabElFor(id) { return { id: 'nav-' + id }; }
function renderProductsTbl() { LOG.push('renderProductsTbl:' + EL.prodSrch.value); }
function globalSearchSyncFromTarget() { LOG.push('globalSync'); }
global.requestAnimationFrame = cb => cb();

const out = {};
openProductsForTerm('  B01AAAA111  ');
out.b_srch   = EL.prodSrch.value;
out.b_brand  = EL.prodBrand.value;
out.b_filter = EL.prodFilter.value;
out.b_cat    = EL.prodCat.value;
out.b_logSync = LOG.slice();          // before any timer runs
out.b_chip   = topProductFilterId;

// B4 a blank term changes NOTHING
LOG.length = 0;
EL.prodSrch.value = 'kept';
openProductsForTerm('   ');
out.b4_log = LOG.slice();
out.b4_srch = EL.prodSrch.value;
openProductsForTerm(null);
out.b4_logAfterNull = LOG.slice();

// B5 a page with NO top-product chip must not touch the setter
LOG.length = 0;
topProductFilterId = null;
openProductsForTerm('SP-0353');
out.b5_log = LOG.slice();

setTimeout(() => {
  out.b_logAfterTick = LOG.slice();
  console.log(JSON.stringify(out));
}, 260);
""")

eq('B1a the term lands on the search box, trimmed', B['b_srch'], 'B01AAAA111')
eq('B1b the brand filter is cleared', B['b_brand'], '')
eq('B1c the Show filter is cleared', B['b_filter'], '')
eq('B1d the legacy category select is cleared', B['b_cat'], '')

L = B['b_logSync']
ok('showPage:products:nav-products' in L, 'B2a it navigates through showPage', L)
ok(L.index('showPage:products:nav-products') < L.index('renderProductsTbl:B01AAAA111'),
   'B2b THE ORDER: navigate FIRST, then set and render - showPage repaints the page '
   'it enters, so controls set before it would be painted over', L)
ok('setTopProductFilter:null' in L,
   'B3a an active Top Products chip is cleared through its own setter '
   '(which clears the localStorage copy too)', L)
ok(L.index('setTopProductFilter:null') < L.index('renderProductsTbl:B01AAAA111'),
   'B3b before the render, not after', L)
eq('B3c and the chip really is off', B['b_chip'], None)
ok('renderProductsTbl:B01AAAA111' in L,
   'B3d the render sees the term already set', L)
ok('globalSync' not in L,
   'B3e the global-bar sync is DEFERRED, not run inside the call', L)
ok('globalSync' in B['b_logAfterTick'],
   'B3f and has fired a tick later - #prodSrch is hidden (v8.43), so without it '
   'nothing on screen says what the table filtered by', B['b_logAfterTick'])
ok(any(x.startswith('scroll:') for x in B['b_logAfterTick']),
   'B3g the table is scrolled into view', B['b_logAfterTick'])

eq('B4a a whitespace term does nothing at all', B['b4_log'], [])
eq('B4b and leaves the search box alone', B['b4_srch'], 'kept')
eq('B4c null likewise', B['b4_logAfterNull'], [])
ok(not any(x.startswith('setTopProductFilter') for x in B['b5_log']),
   'B5 with no chip active the setter is left alone - no gratuitous '
   'localStorage write or panel repaint', B['b5_log'])


# ═══════════════════════════════════════════════════════ C. the drift guard
print('== C. the drift guard: one haystack, two readers ==')

C = run_node(os.path.join(SP, '_v1134_c.js'),
             fn('prodSearchHaystack') + '\n' + fn('prodFindByTerm') + '\n'
             + fn('prodBuildFilterCtx') + '\n' + fn('prodRowMatchesFilters') + r"""
global.document = { getElementById: id => ({ value: VALS[id] || '' }) };
const VALS = {};
let topProductFilterId = null;
let records = [];
let allCategories = [];
function catVisPass() { return true; }
function catVisNorm(v) { return v; }

// One product carrying ALL NINE searchable fields, each with its own token.
const P = {
  master_id: 'MID-aaa', title: 'TTL-bbb', short_name: 'SHT-ccc', sp_sku: 'SPS-ddd',
  asin: 'ASN-eee', shopify_sku: 'SHP-fff', chewy_sku: 'CHW-ggg',
  walmart_item_id: 'WMT-hhh', barcode: 'UPC-iii',
};
const OTHER = { master_id: 'MID-zzz', title: 'something else', short_name: '', sp_sku: '',
  asin: '', shopify_sku: '', chewy_sku: '', walmart_item_id: '', barcode: '' };
let allProducts = [P, OTHER];

const TOKENS = ['MID-aaa','TTL-bbb','SHT-ccc','SPS-ddd','ASN-eee','SHP-fff','CHW-ggg','WMT-hhh','UPC-iii'];
const drift = [];
for (const t of TOKENS) {
  VALS.prodSrch = t;
  const ctx = prodBuildFilterCtx();
  const table = allProducts.filter(p => prodRowMatchesFilters(p, ctx)).map(p => p.master_id);
  const chip  = prodFindByTerm(t).map(p => p.master_id);
  if (JSON.stringify(table) !== JSON.stringify(chip) || table.length !== 1) {
    drift.push({ t, table, chip });
  }
}
VALS.prodSrch = '';
const out = { drift, fields: TOKENS.length };

// Case-insensitive, both sides.
VALS.prodSrch = 'asn-EEE';
out.c2_table = allProducts.filter(p => prodRowMatchesFilters(p, prodBuildFilterCtx())).length;
out.c2_chip  = prodFindByTerm('asn-EEE').length;

// An id nothing carries resolves to nothing on BOTH sides, rather than to
// everything (which an empty haystack would do).
VALS.prodSrch = 'B0NOPE';
out.c3_table = allProducts.filter(p => prodRowMatchesFilters(p, prodBuildFilterCtx())).length;
out.c3_chip  = prodFindByTerm('B0NOPE').length;

// A blank term is NOT "match everything" on the chip side - it is a refusal.
out.c4_blank = prodFindByTerm('   ').length;
out.c5_null  = prodFindByTerm(null).length;

// A product missing every field must not throw.
out.c6_sparse = prodSearchHaystack({});

console.log(JSON.stringify(out));
""")

eq('C1a all nine searchable fields were exercised', C['fields'], 9)
eq('C1b THE DRIFT GUARD: the table and the chip agree on every one '
   '(a field one searches and the other does not would land here)', C['drift'], [])
eq('C2a the table is case-insensitive', C['c2_table'], 1)
eq('C2b and so is the chip', C['c2_chip'], 1)
eq('C3a an id nothing carries matches no row', C['c3_table'], 0)
eq('C3b and no product - so the chip can promise an empty table', C['c3_chip'], 0)
eq('C4 a blank term is a refusal on the chip side, never match-everything', C['c4_blank'], 0)
eq('C5 null likewise', C['c5_null'], 0)
eq('C6 a product with no fields at all does not throw', C['c6_sparse'], '')


# ══════════════════════════════════════════ D. the v8.76 regression guard
print('== D. the v8.76 regression guard ==')

for dead in ("reset('prod-brand'", "reset('prod-search'", "reset('prod-filter'"):
    ok(dead not in js, 'D1 the dead id %s is gone from the file' % dead.split("'")[1])

for live in ('prodBrand', 'prodSrch', 'prodFilter'):
    eq('D2 id="%s" exists exactly once in the markup' % live, s.count('id="%s"' % live), 1)
for dead in ('prod-brand', 'prod-search', 'prod-filter'):
    eq('D3 THE GUARD: id="%s" has never existed' % dead, s.count('id="%s"' % dead), 0)

D = run_node(os.path.join(SP, '_v1134_d.js'), DOM + '\n'
             + fn('clearPageFiltersForTopProductChip') + r"""
['prodBrand', 'prodSrch', 'prodFilter', 'pnl-brand'].forEach(mount);
EL.prodBrand.value = 'Doggijuana';
EL.prodSrch.value  = 'zoomies';
EL.prodFilter.value = 'needs_review';
EL['pnl-brand'].value = 'Meowijuana';

// The PRE-v11.34 reads, reproduced against the same DOM.
const before = {
  brand:  document.getElementById('prod-brand'),
  search: document.getElementById('prod-search'),
  filter: document.getElementById('prod-filter'),
};
clearPageFiltersForTopProductChip();
console.log(JSON.stringify({
  oldIdsResolved: Object.values(before).filter(Boolean).length,
  brand:  EL.prodBrand.value,
  search: EL.prodSrch.value,
  filter: EL.prodFilter.value,
  pnl:    EL['pnl-brand'].value,
}));
""")

eq('D4 THE GUARD: all three pre-v11.34 ids resolved to NOTHING, so the three '
   'reset() calls were dead from v8.76 to v11.33', D['oldIdsResolved'], 0)
eq('D5a the Products brand filter is cleared now', D['brand'], '')
eq('D5b the Products search is cleared now', D['search'], '')
eq('D5c the Products Show filter is cleared now', D['filter'], '')
eq('D6 and every other page still clears as before', D['pnl'], '')


# ═══════════════════════════════════════════════════════════════ E. static
print('== E. static ==')

for name in ('prodSearchHaystack', 'prodFindByTerm', 'openProductsForTerm',
             'uploadUnmatchedGo', 'uploadUnmatchedChips'):
    eq('E1 exactly one definition of %s' % name, js.count('function %s(' % name), 1)

CARDS = {
    'st-sales-traffic':  'ASIN',
    'st-fba-fee-preview': 'ASIN',
    'st-chewy-ads':      'Chewy SKU',
    'st-chewy-catalog':  'Chewy SKU',
}
for st, noun in CARDS.items():
    calls = re.findall(r"uploadUnmatchedChips\('%s'" % re.escape(st), js)
    eq('E2a %s calls the shared renderer twice (clear + render)' % st, len(calls), 2)
    ok("uploadUnmatchedChips('%s', [], '%s')" % (st, noun) in js,
       'E2b %s CLEARS on parse, so a clean upload cannot inherit the last '
       "file's orphans" % st)

eq('E2c no fifth caller crept in', js.count('uploadUnmatchedChips('), 1 + 8)

ok('.dz-warn { color: var(--orange); }' in s,
   'E3a .dz-warn finally has a rule - six handlers have set it since v7.x')
ok(s.count('dz-warn') >= 7, 'E3b and it is still being set', s.count('dz-warn'))
ok('.dz-unmatched' in s, 'E3c the chip row is styled by class, not inline')

# The status lines stay on textContent. innerHTML there would put file content
# into markup, which is the whole reason the chips are a separate element.
for pat in ("el.textContent = msg; el.className = 'dz-st '",
            "el.textContent = m; el.className = 'dz-st '",
            "st.textContent = msg; st.className = 'dz-st'"):
    ok(pat in js, 'E4 the status setter is still textContent: %s' % pat[:28])
ok('st-sales-traffic\').innerHTML' not in js and 'st-chewy-ads\').innerHTML' not in js,
   'E4b no status element gained an innerHTML write')

ok('unknownAsinList,' in js, 'E5a the Sales & Traffic parser returns the ASINs')
ok("unknownAsinList = [...unknownAsins].map(a => ({ id: a, label: (rows.get(a) || {}).title || '' }))" in js,
   'E5b built from the SAME set the count comes from, so the two cannot disagree')
ok('unmatchedList, stores, brands, tiers, futureCount, dimsWritten' in js,
   'E6a the FBA parser returns its list')
ok('${r.unmatchedList.length} ASIN(s) not in catalog' in js,
   'E6b and the note counts DISTINCT ASINs, which is what it always claimed')
ok('${r.unmatched} ASIN(s) not in catalog' not in js,
   'E6c THE GUARD: the raw-line count no longer renders as an ASIN count')
ok('unmatched_asins: r.unmatchedList.length' in js,
   'E6d while the audit log keeps BOTH, so the line count is not lost')

ok('clearProdFilters()' not in fn('openProductsForTerm'),
   'E7 openProductsForTerm does NOT call clearProdFilters - that clears the '
   'search it is about to set and persists the cleared multi-selects')
ok('catVis' not in fn('openProductsForTerm'),
   'E8 nor does it touch category visibility, a saved cross-device preference; '
   'renderProductsTbl already reports what that removed (v10.46)')

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
