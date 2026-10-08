# -*- coding: utf-8 -*-
"""v10.3 — the top search bar covers every page that has a page search.
Drives the REAL sliced dispatch functions."""
import io, os, re, sys, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

a = js.index('const GLOBAL_SEARCH_MAP')
b = js.index('// v8.43 — Hide every per-page local search input')
c = js.index('\n}', js.index('function hideLocalSearchDuplicates')) + 2
ENGINE = js[a:b] + js[b:c]

# Every search input that actually exists in the markup, with its page.
inputs = dict(re.findall(r'<input[^>]*id="([^"]*(?:[Ss]rch|search)[^"]*)"[^>]*placeholder="([^"]*)"', RAW))

static = [
    ('Seasonality is mapped to its real input', "forecast_seasonality:   { id: 'sea-search' }" in js),
    ('the Change Log is mapped', "pnl_amazon_changelog: { id: 'cl-search' }" in js),
    ('the Amazon sub-view is consulted', "if (av === 'changelog') return 'pnl_amazon_changelog';" in js),
    ('switchPnlAmazonView re-points the bar',
     js.index('globalSearchSyncFromTarget') < js.index('function switchPnlAmazonView') + 600
     if 'function switchPnlAmazonView' in js else False),
    ('the pricing PICKER is deliberately left unmapped',
     "pnl_pricing:     { id: null }" in js and 'typeahead PICKER' in js),
    ('#sea-search really exists in the markup', 'sea-search' in inputs),
    ('#cl-search really exists in the markup', 'cl-search' in inputs),
]

HARNESS = r"""
let currentPage = 'products', forecastView = 'demand', pnlView = 'amazon',
    chewyPnlView = 'sales', pnlAmazonView = 'summary';
const EL = {};
function mk(id, ph) { return EL[id] = { id, placeholder: ph, value: '', style: {}, dataset: {},
  disabled: false, _events: [], dispatchEvent(e) { this._events.push(e.type); } }; }
const document = { getElementById: (id) => EL[id] || null };
class Event { constructor(t) { this.type = t; } }

__INPUTS__
mk('globalSearch', '');
mk('globalSearchClear', '');
EL['globalSearchLabel'] = { textContent: '' };

__ENGINE__

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const at = (page, opts) => { currentPage = page; Object.assign(globalThis, opts || {});
  if (opts) { if ('forecastView' in opts) forecastView = opts.forecastView;
              if ('pnlView' in opts) pnlView = opts.pnlView;
              if ('pnlAmazonView' in opts) pnlAmazonView = opts.pnlAmazonView;
              if ('chewyPnlView' in opts) chewyPnlView = opts.chewyPnlView; } };

console.log('\n== A. THE BUG: Seasonality had a search the bar could not see ==');
at('forecast', { forecastView: 'seasonality' });
t('the bar now resolves to #sea-search',
  globalSearchTargetInput() === EL['sea-search'], globalSearchCurrentKey());
globalSearchSyncFromTarget();
t('  the bar is enabled', EL['globalSearch'].disabled === false);
t('  and no longer says "No search on this page"',
  EL['globalSearch'].placeholder !== 'No search on this page', EL['globalSearch'].placeholder);
t('  it mirrors the page\u2019s own placeholder',
  EL['globalSearch'].placeholder === EL['sea-search'].placeholder, EL['globalSearch'].placeholder);
t('  the label stops reading n/a', EL['globalSearchLabel'].textContent === 'Search this page',
  EL['globalSearchLabel'].textContent);
globalSearchDispatch('catnip');
t('typing dispatches the value into the page input', EL['sea-search'].value === 'catnip');
t('  and fires the native input event its handler is wired to',
  EL['sea-search']._events.includes('input'), EL['sea-search']._events);

console.log('\n== B. Every page with a page search resolves to it ==');
const cases = [
  ['products',  {},                                        'prodSrch'],
  ['bundles',   {},                                        'bundleSrch'],
  ['sales',     {},                                        'salesSrch'],
  ['forecast',  { forecastView: 'demand' },                'srchInput'],
  ['forecast',  { forecastView: 'inventory' },             'ip-srch'],
  ['forecast',  { forecastView: 'reorder-setup' },         'ipr-srch'],
  ['forecast',  { forecastView: 'seasonality' },           'sea-search'],
  ['forecast',  { forecastView: 'chewy' },                 'chwy-search'],
  ['forecast',  { forecastView: 'fba-shipments' },         'fba-ship-srch'],
  ['pnl',       { pnlView: 'amazon', pnlAmazonView: 'summary' },     'pnl-search'],
  ['pnl',       { pnlView: 'amazon', pnlAmazonView: 'performance' }, 'pnl-search'],
  ['pnl',       { pnlView: 'amazon', pnlAmazonView: 'diagnostics' }, 'pnl-search'],
  ['pnl',       { pnlView: 'amazon', pnlAmazonView: 'changelog' },   'cl-search'],
  ['pnl',       { pnlView: 'shopify' },                    'spnl-search'],
  ['pnl',       { pnlView: 'walmart' },                    'wmpnl-search'],
  ['pnl',       { pnlView: 'chewy', chewyPnlView: 'sales' },   'chpnl-sales-search'],
  ['pnl',       { pnlView: 'chewy', chewyPnlView: 'rebates' }, 'chpnl-search'],
  ['pnl',       { pnlView: 'cogs' },                       'cogs-search'],
];
for (const [page, opts, want] of cases) {
  at(page, opts);
  const got = globalSearchTargetInput();
  const label = page + (Object.keys(opts).length ? ' / ' + Object.values(opts).join('/') : '');
  t(`${label.padEnd(34)} -> #${want}`, got === EL[want], globalSearchCurrentKey());
}

console.log('\n== C. REGRESSION GUARD: the Amazon sub-views used to share one key ==');
at('pnl', { pnlView: 'amazon', pnlAmazonView: 'changelog' });
t('Change Log no longer resolves to the Summary input',
  globalSearchTargetInput() !== EL['pnl-search']);
t('  it resolves to its own', globalSearchTargetInput() === EL['cl-search']);

console.log('\n== D. Pages that legitimately have no page search ==');
for (const [page, opts] of [['data', {}], ['settings', {}], ['pnl', { pnlView: 'pricing' }]]) {
  at(page, opts);
  t(`${page}${opts.pnlView ? '/' + opts.pnlView : ''} correctly has no target`,
    globalSearchTargetInput() === null, globalSearchCurrentKey());
}
at('pnl', { pnlView: 'pricing' });
globalSearchSyncFromTarget();
t('the bar disables itself rather than silently doing nothing',
  EL['globalSearch'].disabled === true && EL['globalSearch'].placeholder === 'No search on this page');
t('the pricing PICKER input is left visible (hiding it would break its popover)',
  EL['pricing-search'].style.display !== 'none', EL['pricing-search'].style.display);

console.log('\n== E. Every mapped local input gets hidden ==');
hideLocalSearchDuplicates();
const mapped = Object.values(GLOBAL_SEARCH_MAP).map(e => e && e.id).filter(Boolean);
t(`all ${mapped.length} mapped inputs hidden`,
  mapped.every(id => EL[id] && EL[id].style.display === 'none'),
  mapped.filter(id => EL[id] && EL[id].style.display !== 'none'));
t('  including the Seasonality one that used to sit visible under the bar',
  EL['sea-search'].style.display === 'none');
t('  and it is idempotent', (hideLocalSearchDuplicates(), EL['sea-search'].dataset.hiddenByGlobal === '1'));

console.log('\n== F. Nothing in the markup is left unmapped by accident ==');
// Any input whose id looks like a page search but is not in the map is either a
// deliberate exclusion or a miss. Keep the exclusions explicit.
// Deliberate exclusions, all of them pickers inside a modal or a row rather
// than a page filter: the bar itself, the Pricing Scenarios typeahead, the
// Catsy import matcher, the merge tool's two product pickers, and the
// per-row BOM component picker in the product modal (a template-literal id,
// one per component row).
const EXCLUDE = new Set(['globalSearch', 'pricing-search', 'catsy-search-input',
                         'merge-src', 'merge-tgt', 'bom-search-${i}']);
const unmapped = __ALLIDS__.filter(id => !EXCLUDE.has(id) && !mapped.includes(id));
t('no unmapped page-search inputs remain', unmapped.length === 0, unmapped);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

mkjs = '\n'.join("mk(%r, %r);" % (i, p) for i, p in sorted(inputs.items()))
static_js = '\n'.join("t(%r, %s);" % (n, 'true' if v else 'false') for n, v in static)
out = (HARNESS.replace('__INPUTS__', mkjs)
              .replace('__ENGINE__', ENGINE)
              .replace('__ALLIDS__', repr(sorted(inputs.keys())).replace("'", '"'))
              .replace("console.log('\\n== A.",
                       "console.log('\\n== 0. Static assertions against the shipped source ==');\n"
                       + static_js + "\nconsole.log('\\n== A."))
p = os.path.join(SP, 'test_v103.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars · %d search inputs found in markup' % (len(out), len(inputs)))
sys.exit(subprocess.call(['node', p]))
