# -*- coding: utf-8 -*-
"""v10.9 — Customize columns moves into the page chrome, between search and gear."""
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


REAL = slab('const PAGE_COLUMN_BUTTONS = [', 'function pageColsSyncButton') \
     + '\n' + fn('pageColsSyncButton')

BTN_IDS = ['fc-cols-btn', 'ip-view-btn', 'prod-view-btn',
           'pnl-cols-btn', 'spnl-cols-btn', 'sales-view-btn']

bar_a = RAW.index('id="globalSearchBar"')
bar_b = RAW.index('<!-- SHEETS BAR', bar_a)
bar   = RAW[bar_a:bar_b]

static = [
    ('all six column buttons now live in the global bar',
     all(('id="%s"' % b) in bar for b in BTN_IDS)),
    ('  and each appears exactly once in the whole file',
     all(RAW.count('id="%s"' % b) == 1 for b in BTN_IDS)),
    ('they sit AFTER the search input',
     all(bar.index('id="%s"' % b) > bar.index('id="globalSearch"') for b in BTN_IDS)),
    ('  and BEFORE the settings gear',
     all(bar.index('id="%s"' % b) < bar.index('id="pageSettingsBtn"') for b in BTN_IDS)),
    ('they start hidden, so nothing flashes before the nav key resolves',
     all(re.search(r'id="%s"[^>]*style="display:none;' % re.escape(b), bar) for b in BTN_IDS)),
    ('  with one uniform look rather than the three they arrived with',
     bar.count('font-family:var(--mono);font-size:11px;padding:6px 10px') == len(BTN_IDS)),

    # ⚠ the thing that would have broken a dispatcher rewrite
    ('\u26a0 every id is PRESERVED \u2014 ~35 call sites re-open popups by id',
     all(("document.getElementById('%s')" % b) in js for b in BTN_IDS)),
    ('  the openers were not touched',
     all(o in RAW for o in ['openFcColumnsPopup(this)', 'openIpColumnsPopup(this)',
                            'prodToggleColsPopup()', 'pnlToggleColsPopup(event)',
                            'shopifyPnlToggleColsPopup(event)', 'openSalesViewPopup(this)'])),
    ('  and the v10.7 sort re-anchor still points at a real element',
     "document.getElementById('fc-sort-btn') || document.getElementById('fc-cols-btn')" in js),

    ('visibility is driven by the same resolver as the gear',
     'pageSettingsCurrentNavKey' in fn('pageColsSyncButton')),
    ('synced on every nav (inside globalSearchSyncFromTarget)',
     "if (typeof pageColsSyncButton === 'function') pageColsSyncButton();   // v10.9\n}" in js),
    ('  and once auth resolves', js.count('pageColsSyncButton();   // v10.9') == 2),
    ('Units Sold keeps its honest label',
     '\U0001F4CB Saved reports</button>' in RAW),
    ('the other five say Customize columns',
     bar.count('\U0001F4CB Customize columns</button>') == 5),
]

HARNESS = r"""
const SHOWN = {};
const document = {
  getElementById: (id) => (id in SHOWN ? { style: SHOWN[id] } : null),
};
let NAV = '';
function pageSettingsCurrentNavKey() { return NAV; }

__REAL__

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const IDS = __IDS__;
const reset = () => { IDS.forEach(id => SHOWN[id] = { display: 'none' }); };
const visible = () => IDS.filter(id => SHOWN[id].display !== 'none');

console.log('\n== A. Exactly one button per page ==');
const CASES = {
  forecast_demand:      'fc-cols-btn',
  forecast_inventory:   'ip-view-btn',
  products:             'prod-view-btn',
  sales:                'sales-view-btn',
  pnl_amazon:           'pnl-cols-btn',
  pnl_amazon_changelog: 'pnl-cols-btn',
  pnl_shopify:          'spnl-cols-btn',
};
for (const [navKey, want] of Object.entries(CASES)) {
  reset(); NAV = navKey; pageColsSyncButton();
  const v = visible();
  t(`${navKey.padEnd(22)} -> ${want}`, v.length === 1 && v[0] === want, v);
}

console.log('\n== B. Pages with no column picker show none ==');
for (const navKey of ['forecast_seasonality', 'pnl_walmart', 'pnl_chewy_sales', 'pnl_cogs',
                      'bundles', 'data', 'settings', 'forecast_chewy', 'pnl_pricing',
                      'forecast_fba-shipments', 'pnl_chewy_rebates']) {
  reset(); NAV = navKey; pageColsSyncButton();
  t(`${navKey.padEnd(24)} shows no button`, visible().length === 0, visible());
}

console.log('\n== C. Switching pages hides the previous one ==');
reset();
NAV = 'products';          pageColsSyncButton();
t('on Products, the Products button shows', visible().join() === 'prod-view-btn');
NAV = 'pnl_shopify';       pageColsSyncButton();
t('moving to Shopify P&L swaps it', visible().join() === 'spnl-cols-btn', visible());
NAV = 'pnl_cogs';          pageColsSyncButton();
t('moving to COGS leaves none', visible().length === 0, visible());
NAV = 'forecast_demand';   pageColsSyncButton();
t('coming back reveals the right one', visible().join() === 'fc-cols-btn', visible());

console.log('\n== D. Registry shape ==');
t('every entry has an id and at least one nav key',
  PAGE_COLUMN_BUTTONS.every(b => typeof b.id === 'string' && Array.isArray(b.navKeys) && b.navKeys.length));
t('no id is registered twice',
  new Set(PAGE_COLUMN_BUTTONS.map(b => b.id)).size === PAGE_COLUMN_BUTTONS.length);
t('no nav key maps to two buttons', (() => {
  const seen = new Set();
  for (const b of PAGE_COLUMN_BUTTONS) for (const k of b.navKeys) {
    if (seen.has(k)) return false; seen.add(k);
  }
  return true;
})());

console.log('\n== E. Missing elements never throw ==');
let threw = false;
try { for (const id of IDS) delete SHOWN[id]; NAV = 'products'; pageColsSyncButton(); } catch { threw = true; }
t('a button absent from the DOM is skipped, not fatal', !threw);
reset();
for (const k of ['', null, undefined, 'nonsense']) {
  let th = false;
  try { NAV = k; pageColsSyncButton(); } catch { th = true; }
  t('nav key ' + JSON.stringify(k) + ' is safe', !th && visible().length === 0, visible());
}

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
"""

import json
static_js = '\n'.join("t(%r, %s);" % (n, 'true' if v else 'false') for n, v in static)
out = (HARNESS.replace('__REAL__', REAL)
              .replace('__IDS__', json.dumps(BTN_IDS))
              .replace("console.log('\\n== A.",
                       "console.log('\\n== 0. Static assertions against the shipped source ==');\n"
                       + static_js + "\nconsole.log('\\n== A."))
p = os.path.join(SP, 'test_v109.js')
io.open(p, 'w', encoding='utf-8', newline='\n').write(out)
print('harness %d chars' % len(out))
sys.exit(subprocess.call(['node', p]))
