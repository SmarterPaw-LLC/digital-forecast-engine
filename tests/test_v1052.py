# -*- coding: utf-8 -*-
r"""v10.52 — Realised ROAS was double-counting the first Autoship order.

Chewy's own metric tooltips, pulled by Jason:
  "Autoship actualized orders: Total number of Autoship orders attributed to an
   ad click, INCLUDING THE FIRST ORDER and all recurring shipments."
  "Direct sales: Sales attributed to campaigns EXCLUDING RECURRING Autoship
   orders."

Read together, the first autoship order is in BOTH. `Realised = Direct +
Autoship` counted it twice on every SKU, and on Jason's 91-day window that is
nearly the whole autoship figure: 977 sign-ups against 1,065 actualized orders,
so 92% of autoship orders are first orders.

chewyBreakevenEcon is deliberately NOT touched (29 behaviour tests ride on it).
Its `realisedSales = directSales + autoshipSales` becomes correct the moment the
value handed to it is the incremental one, so this suite drives the SPLIT.
"""
import io, os, re, subprocess, sys, tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)

def fn(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m: raise SystemExit('FAIL: cannot slice %s' % name)
    a = m.start() + 1
    i = js.index('{', a); depth = 0
    while True:
        c = js[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return js[a:i + 1]
        i += 1


# ══════════════ A. static — the econ contract is untouched ══════════════
print('A. static — the split happens at the call site, not inside the econ')

econ = fn('chewyBreakevenEcon')
ok('directSales + autoshipSales' in econ.replace('\n', ' ') or 'autoshipSales' in econ,
   'chewyBreakevenEcon still sums whatever autoship figure it is handed')
ok('autoship_actualized_orders' not in econ and 'autoship_signups' not in econ,
   '  and knows nothing about sign-ups or order counts (29 tests ride on it)')

ok('autoshipSales: autoshipRecurring' in js,
   'the break-even page hands it the RECURRING figure')
ok('a.autoship_orders += Number(r.autoship_actualized_orders) || 0;' in js,
   'actualized orders are accumulated per SKU')
ok('Math.max(0, asOrders - a.autoship_signups)' in js,
   'recurring orders = actualized orders minus sign-ups')
ok('Math.min(a.autoship_sales, a.autoship_sales * (asRecurOrders / asOrders))' in js,
   '  valued at the window average order value, clamped to the gross')
ok('autoship_unsplit: asOrders === 0 && a.autoship_sales > 0' in js,
   'a SKU with autoship sales but no order count is FLAGGED, not guessed')


# ══════════════ B. static — every surface says what it now means ══════════
print('\nB. static — no surface still shows the gross figure as if it were incremental')

ok("key: 'autoship_recurring'" in js, 'the column reads the recurring field')
ok("label: 'Autoship $'" not in js, '  the old gross-figure label is gone')
ok('(direct + recurring autoship)' in js, 'the Realised ROAS sub-line names the split')
ok("'Realised ROAS = (Direct sales + Autoship actualised) / spend.'," not in js,
   '  and the old explainer line is gone')
ok('Chewy counts the first autoship order in BOTH' in js,
   'the explainer states WHY only part is added')
ok('first orders excluded' in js, 'the scorecard names the excluded dollars')
ok("'autoship_recurring_sales','autoship_first_order_sales','autoship_actualized_orders'" in js,
   'the CSV carries both halves plus the order count, so the split is auditable')


# ══════════════ C. behaviour — the split, against Jason's real totals ══════
print("\nC. behaviour — the split logic on Jason's own numbers")

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + '  got ' + g + ' want ' + w); }
};
const r2 = (n) => Math.round(n * 100) / 100;

// The split, lifted verbatim from the shipped call site.
function split(a) {
  const asOrders = a.autoship_orders;
  const asRecurOrders = Math.max(0, asOrders - a.autoship_signups);
  const autoshipRecurring = asOrders > 0
    ? Math.min(a.autoship_sales, a.autoship_sales * (asRecurOrders / asOrders))
    : 0;
  const autoshipFirst = Math.max(0, a.autoship_sales - autoshipRecurring);
  return { recurring: autoshipRecurring, first: autoshipFirst,
           unsplit: asOrders === 0 && a.autoship_sales > 0 };
}

// ── Jason's 91-day portfolio: 977 sign-ups, 1,065 orders, $11,985.26 ──────
const port = split({ autoship_sales: 11985.26, autoship_signups: 977, autoship_orders: 1065 });
t('92% of autoship orders are first orders, so most of the dollars are too',
  r2(port.first), 10994.93);
t('  leaving this much genuinely incremental', r2(port.recurring), 990.33);
t('  and the two halves still sum to the gross', r2(port.first + port.recurring), 11985.26);

// Realised ROAS moves a long way. Spend over the same window: $18,865.
const spend = 18865, direct = 80640.65;
t('Realised ROAS was overstated at ~491%',
  Math.round(((direct + 11985.26) / spend) * 100), 491);
t('  and is ~433% once the first order stops being counted twice',
  Math.round(((direct + port.recurring) / spend) * 100), 433);
t('  i.e. barely above Direct ROAS, which is the real finding',
  Math.round((direct / spend) * 100), 427);

// ── the shapes that must not break ────────────────────────────────────────
t('every order being a first order leaves zero incremental',
  split({ autoship_sales: 500, autoship_signups: 10, autoship_orders: 10 }).recurring, 0);
t('no sign-ups at all means the whole figure is recurring',
  split({ autoship_sales: 500, autoship_signups: 0, autoship_orders: 10 }).recurring, 500);
t('more sign-ups than orders (a sign-up that has not shipped) clamps at zero',
  split({ autoship_sales: 500, autoship_signups: 14, autoship_orders: 10 }).recurring, 0);
t('  and never produces a negative first-order figure',
  split({ autoship_sales: 500, autoship_signups: 14, autoship_orders: 10 }).first, 500);
t('no autoship at all is simply zero',
  split({ autoship_sales: 0, autoship_signups: 0, autoship_orders: 0 }).recurring, 0);
t('  and is NOT flagged unsplittable',
  split({ autoship_sales: 0, autoship_signups: 0, autoship_orders: 0 }).unsplit, false);
t('sales with no order count IS flagged unsplittable',
  split({ autoship_sales: 500, autoship_signups: 0, autoship_orders: 0 }).unsplit, true);
t('  and contributes nothing rather than being guessed',
  split({ autoship_sales: 500, autoship_signups: 0, autoship_orders: 0 }).recurring, 0);

// A half-and-half SKU, so the proportioning itself is checked rather than only
// the degenerate ends.
const half = split({ autoship_sales: 1000, autoship_signups: 5, autoship_orders: 10 });
t('five of ten orders recurring splits the dollars in half', half.recurring, 500);
t('  with the other half attributed to first orders', half.first, 500);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

tmp = os.path.join(tempfile.gettempdir(), 'test_v1052_split.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('split behaviour')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d static, %d sections): %s' % (F, len(fails), ', '.join(fails[:6])))
    sys.exit(1)
print('v10.52 — all green (%d static assertions + 1 behaviour section)' % P)
