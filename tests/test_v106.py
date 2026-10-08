# -*- coding: utf-8 -*-
"""v10.6 — per-user, per-page category visibility. Drives the REAL sliced engine."""
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


def slab(start, end):
    a = js.index(start); b = js.index(end, a)
    return js[a:b]


# Constants + registry + the pure logic. The DOM/Supabase halves are stubbed.
REAL = slab("const CATVIS_GLOBAL = '_global';", 'let catVisConfig = {};') + '\n' + '\n'.join([
    fn('catVisPageDef'),
    fn('catVisInvalidate'),
    fn('catVisResolved'),
    fn('catVisIdMap'),
    fn('catVisPass'),
    fn('catVisAllCats'),
    fn('catVisAllSubcats'),
    fn('catVisSetPage'),
    fn('catVisClearPageOverride'),
    fn('catVisPromoteToGlobal'),
    fn('catVisMigrateProductsLocal'),
])

# ── static assertions against the shipped source ─────────────────────────────
PAGES = ['forecast', 'inventory', 'seasonality', 'products', 'sales',
         'pnl_amazon', 'pnl_shopify', 'pnl_walmart', 'pnl_chewy', 'cogs']
# Where each page MUST have the predicate, and how many times (one per filter
# site: table render + selection/visible records + CSV export + export dialog).
EXPECTED_SITES = {
    'forecast': 1, 'inventory': 4, 'seasonality': 2, 'products': 1, 'sales': 1,
    'pnl_amazon': 3, 'pnl_shopify': 1, 'pnl_walmart': 1, 'pnl_chewy': 1, 'cogs': 1,
}
static = [
    ('all 10 pages are in the registry',
     all(("key: '%s'" % k) in js for k in PAGES)),
    ('the Pricing Scenarios benchmark is deliberately NOT wired',
     "catVisPass('pricing'" not in js and 'pnew-category' in js),
    ('the Chewy REBATE category (different taxonomy) is not wired',
     "catVisPass('pnl_rebates'" not in js),
    ('Products no longer runs the v5.76 localStorage predicate',
     '!prodCatFilter.has(catName)' not in js and '!prodSubcatFilter.has(subName)' not in js),
    ('  it delegates to the shared engine instead',
     "if (!catVisPass('products', p)) return false;" in js),
    # Markup assertions check RAW, not the extracted <script>. Checking `js`
    # here made the button-removal test a false pass: HTML is not in the script.
    ('the two v5.76 Products buttons are gone from the markup',
     'id="prodCatBtn"' not in RAW and 'id="prodSubcatBtn"' not in RAW),
    ('the v5.76 localStorage choice is migrated, not dropped',
     "read('prodCatFilterUser')" in js and 'catVisMigrateProductsLocal' in js),
    ('init loads the config from Supabase',
     'if (typeof catVisLoadFromDb === \'function\') catVisLoadFromDb();' in js),
    # v10.7 re-point: the ten per-page chips were replaced by one page-settings
    # gear beside the global search bar. The thing being asserted is unchanged —
    # that the visibility affordance is resolved once auth lands.
    ('the visibility affordance is resolved after auth resolves',
     "if (typeof pageSettingsSyncIndicator === 'function') pageSettingsSyncIndicator();" in js),
    ('a catalog reload rebuilds the caches',
     'catVisInvalidate();\n    catVisMigrateProductsLocal();' in js),
    ('persistence targets user_profiles.category_visibility on user_id',
     "update({ category_visibility: catVisConfig }).eq('user_id', user.id)" in js),
    ('  and names the migration file when the column is missing',
     'supabase_v10_6_category_visibility.sql' in js),
    ('the Settings host exists',
     'id="catvis-settings"' in RAW),
    ('  and avoids .ds-hdr (which v8.42 injects a chart Labels button into)',
     'id="catvis-settings"' in RAW
     and 'ds-hdr' not in RAW[RAW.index('id="catvis-settings"') - 1100: RAW.index('id="catvis-settings"')]),
    ('the chip anchors (every page category select) are all in the markup',
     all(('id="%s"' % sid) in RAW for sid in
         ['fCategory','ip-category','sea-category','prodCat','salesCat',
          'pnl-cat','spnl-cat','wmpnl-cat','chpnl-sales-cat','cogs-cat'])),
    ('the COGS predicate sits OUTSIDE the dropdown block',
     js.index("catVisPass('cogs', p)") < js.index('if (catFilter || subFilter) {')),
]
for k, n in EXPECTED_SITES.items():
    static.append(('%-12s has %d predicate site%s' % (k, n, '' if n == 1 else 's'),
                   js.count("catVisPass('%s'," % k) == n))

HARNESS = r"""
// ── stubs ────────────────────────────────────────────────────────────────────
let allCategories = [
  { id: 1, category: 'Sprays',      subcategory: '3 oz'     },
  { id: 2, category: 'Sprays',      subcategory: '6 oz'     },
  { id: 3, category: 'Treats',      subcategory: 'Crunchy'  },
  { id: 4, category: 'Toys',        subcategory: 'Kickers'  },
  { id: 5, category: 'Apparel',     subcategory: 'Tees'     },
];
function getCategories() { return [...new Set(allCategories.map(c => c.category))].sort(); }
let STORE = {};
const localStorage = {
  getItem: (k) => (k in STORE ? STORE[k] : null),
  setItem: (k, v) => { STORE[k] = String(v); },
  removeItem: (k) => { delete STORE[k]; },
};
let PERSISTS = 0;
function catVisPersist() { PERSISTS++; try { localStorage.setItem(CATVIS_LS_KEY, JSON.stringify(catVisConfig)); } catch {} }
function catVisSyncAllChips() {}
function catVisRenderSettings() {}
let catVisConfig = {};

__REAL__

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const reset = (cfg) => { catVisConfig = cfg || {}; catVisInvalidate(); STORE = {}; PERSISTS = 0; };
// Products rows carry category_id; records rows also carry resolved names.
const P = (id) => ({ master_id: 'SP-' + id, category_id: id });
const REC = (id, cat, sub) => ({ master_id: 'R-' + id, category_id: id, category: cat, subcategory: sub });

console.log('\n== A. No config: nothing is ever hidden ==');
reset({});
t('every page resolves to no filter',
  CATVIS_PAGES.every(p => catVisResolved(p.key).source === 'none'));
t('every product passes on every page',
  CATVIS_PAGES.every(p => [1,2,3,4,5].every(i => catVisPass(p.key, P(i)))));

console.log('\n== B. THE ASK: hide a category on one page only ==');
reset({ pnl_amazon: { cats: ['Sprays','Treats','Toys'], subcats: null } });   // Apparel hidden
t('Apparel is hidden on Amazon P&L', catVisPass('pnl_amazon', P(5)) === false);
t('Sprays still shows there',        catVisPass('pnl_amazon', P(1)) === true);
t('and NO other page is affected',
  CATVIS_PAGES.filter(p => p.key !== 'pnl_amazon').every(p => catVisPass(p.key, P(5))));
t('source reads as a page override', catVisResolved('pnl_amazon').source === 'page');

console.log('\n== C. Global default applies everywhere, per-page overrides win ==');
reset({ _global: { cats: ['Sprays','Treats','Toys'], subcats: null } });
t('Apparel is hidden on all ten pages',
  CATVIS_PAGES.every(p => catVisPass(p.key, P(5)) === false));
t('  and each reports source:global',
  CATVIS_PAGES.every(p => catVisResolved(p.key).source === 'global'));

reset({ _global: { cats: ['Sprays'], subcats: null },
        cogs:    { cats: ['Sprays','Treats','Toys','Apparel'], subcats: null } });
t('COGS override beats the global', catVisPass('cogs', P(3)) === true);
t('  while other pages follow the global', catVisPass('sales', P(3)) === false);

console.log('\n== D. \u26a0 "present but all-null" is an explicit show-all, not inherit ==');
reset({ _global: { cats: ['Sprays'], subcats: null }, sales: { cats: null, subcats: null } });
t('the global hides Treats on inventory', catVisPass('inventory', P(3)) === false);
t('but Units Sold explicitly shows everything', catVisPass('sales', P(3)) === true);
t('  and reports source:page, not global', catVisResolved('sales').source === 'page');
// Regression guard: an implementation using a truthiness check instead of
// hasOwnProperty would read {cats:null,subcats:null} as "no override" and fall
// through to the global, hiding Treats on a page that asked to show everything.
t('  REGRESSION GUARD: a truthiness check would have inherited here',
  !(catVisConfig.sales.cats || catVisConfig.sales.subcats));

console.log('\n== E. Sub-categories filter independently of categories ==');
reset({ inventory: { cats: null, subcats: ['3 oz','Crunchy','Kickers','Tees'] } });  // 6 oz hidden
t('Sprays / 6 oz is hidden', catVisPass('inventory', P(2)) === false);
t('Sprays / 3 oz still shows', catVisPass('inventory', P(1)) === true);
reset({ inventory: { cats: ['Sprays'], subcats: ['6 oz'] } });
t('both axes apply together (Sprays + 6 oz only)',
  [catVisPass('inventory', P(1)), catVisPass('inventory', P(2)), catVisPass('inventory', P(3))]
    .join() === 'false,true,false',
  [catVisPass('inventory', P(1)), catVisPass('inventory', P(2)), catVisPass('inventory', P(3))]);

console.log('\n== F. \u26a0 Unclassifiable rows are VISIBLE, never silently dropped ==');
reset({ _global: { cats: ['Sprays'], subcats: null } });
t('a product with no category_id passes', catVisPass('sales', { master_id: 'SP-X' }) === true);
t('a category_id with no matching row passes', catVisPass('sales', { category_id: 999 }) === true);
t('null (the Walmart / Chewy P&L unmatched case) passes', catVisPass('pnl_walmart', null) === true);
t('undefined passes', catVisPass('pnl_walmart', undefined) === true);

console.log('\n== G. records rows (name fields already resolved) ==');
reset({ inventory: { cats: ['Sprays'], subcats: null } });
t('resolves from r.category when present',
  catVisPass('inventory', REC(1, 'Sprays', '3 oz')) === true);
t('  and hides a non-matching one', catVisPass('inventory', REC(3, 'Treats', 'Crunchy')) === false);
t('a pooled record with only category_id still resolves',
  catVisPass('inventory', { master_id: 'R-9', category_id: 3 }) === false);

console.log('\n== H. Mutation: set / clear / promote ==');
reset({});
catVisSetPage('products', ['Sprays','Treats','Toys'], null);
t('setPage writes an override', catVisResolved('products').source === 'page');
t('  and hides Apparel', catVisPass('products', P(5)) === false);
t('  and persisted', PERSISTS > 0);

reset({});
catVisSetPage('products', getCategories(), catVisAllSubcats());
t('a FULL selection normalizes to null (reads "All", not "5 of 5")',
  catVisConfig.products.cats === null && catVisConfig.products.subcats === null,
  catVisConfig.products);

reset({ _global: { cats: ['Sprays'], subcats: null }, products: { cats: ['Treats'], subcats: null } });
catVisClearPageOverride('products');
t('clearing the override falls back to the global', catVisResolved('products').source === 'global');
t('  so the global rule now applies', catVisPass('products', P(3)) === false);

reset({ cogs: { cats: ['Sprays','Treats'], subcats: null } });
catVisPromoteToGlobal('cogs');
t('promote copies the page scope to _global',
  JSON.stringify(catVisConfig._global.cats) === JSON.stringify(['Sprays','Treats']),
  catVisConfig._global);
t('  and drops the page override so it visibly inherits',
  !Object.prototype.hasOwnProperty.call(catVisConfig, 'cogs'));
t('  every page now follows it', catVisPass('sales', P(4)) === false);

reset({ _global: { cats: ['Sprays'], subcats: null } });
catVisPromoteToGlobal(CATVIS_GLOBAL);
t('REGRESSION GUARD: promoting global to global does NOT delete it',
  Object.prototype.hasOwnProperty.call(catVisConfig, CATVIS_GLOBAL));

console.log('\n== I. v5.76 Products localStorage migration ==');
reset({});
STORE['prodCatFilterUser'] = JSON.stringify(['Sprays','Treats','Toys']);
t('migrates the old Products-only choice', catVisMigrateProductsLocal() === true);
t('  onto the products page', catVisPass('products', P(5)) === false);
t('  \u26a0 and NOT into _global (nine other pages must not change silently)',
  !Object.prototype.hasOwnProperty.call(catVisConfig, CATVIS_GLOBAL));
t('  other pages still show everything', catVisPass('sales', P(5)) === true);

reset({});
STORE['prodCatFilterDefault'] = JSON.stringify(['Sprays']);
t('falls back to the saved DEFAULT key when no user key exists',
  catVisMigrateProductsLocal() === true && catVisPass('products', P(3)) === false);

reset({ products: { cats: null, subcats: null } });
STORE['prodCatFilterUser'] = JSON.stringify(['Sprays']);
t('never overwrites an existing products config', catVisMigrateProductsLocal() === false);
t('  (the config stays an explicit show-all)', catVisPass('products', P(3)) === true);

reset({});
t('no localStorage keys \u2192 nothing to migrate', catVisMigrateProductsLocal() === false);
t('  and no products key is invented',
  !Object.prototype.hasOwnProperty.call(catVisConfig, 'products'));

console.log('\n== J. Cache correctness (catVisPass runs once per row per render) ==');
reset({ sales: { cats: ['Sprays'], subcats: null } });
t('first call hides Treats', catVisPass('sales', P(3)) === false);
catVisConfig.sales = { cats: ['Sprays','Treats'], subcats: null };
t('a config change WITHOUT invalidate serves the cached answer (by design)',
  catVisPass('sales', P(3)) === false);
catVisInvalidate();
t('  invalidate picks up the change', catVisPass('sales', P(3)) === true);
t('every mutator invalidates for you',
  (() => { reset({ sales: { cats: ['Sprays'], subcats: null } });
           catVisPass('sales', P(3));
           catVisSetPage('sales', ['Sprays','Treats'], null);
           return catVisPass('sales', P(3)) === true; })());

console.log('\n== K. Nothing throws on hostile input ==');
for (const cfg of [{ sales: null }, { sales: { cats: 'nope' } }, { sales: {} }, { _global: 7 }]) {
  let threw = false, out;
  try { reset(cfg); out = catVisPass('sales', P(1)); } catch { threw = true; }
  t('config ' + JSON.stringify(cfg) + ' \u2192 no throw, boolean out',
    !threw && typeof out === 'boolean', out);
}
reset({ sales: { cats: ['Sprays'], subcats: null } });
t('an unknown page key behaves as unconfigured', catVisPass('nope', P(5)) === true);
t('catVisPageDef on an unknown key returns null', catVisPageDef('nope') === null);
let threwNoCats = false;
try { allCategories = []; catVisInvalidate(); catVisAllCats(); catVisPass('sales', P(1)); } catch { threwNoCats = true; }
t('an empty category catalog does not throw', !threwNoCats);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

static_js = '\n'.join("t(%r, %s);" % (n, 'true' if v else 'false') for n, v in static)
out = (HARNESS.replace('__REAL__', REAL)
              .replace("console.log('\\n== A.",
                       "console.log('\\n== 0. Static assertions against the shipped source ==');\n"
                       + static_js + "\nconsole.log('\\n== A."))
p = os.path.join(SP, 'test_v106.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars' % len(out))
sys.exit(subprocess.call(['node', p]))
