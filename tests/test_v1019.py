# -*- coding: utf-8 -*-
"""
v10.19 — Break-Even sub-tab on Amazon P&L (Blake's financial-controls table).

Jason: "i want to build a page that matches the columns we built from his
request."

Those 55 columns are query_amazon_breakeven_acos.sql, which he had been running
by hand in Data → Query Database and Copy-CSVing every month. The page RUNS
that same SQL through exec_sql rather than reimplementing ~250 lines of
cost-stack math in JS — a JS port would be a second source of truth, and the
first time the two disagreed nobody would know which one was lying.

The load-bearing test is therefore the drift guard: the SQL embedded in
index.html must emit the SAME column list, in the same order, as the .sql file
in the repo. Everything else is downstream of that.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
QFILE = os.path.join(ROOT, 'query_amazon_breakeven_acos.sql')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)
sqlfile = io.open(QFILE, encoding='utf-8', newline='').read()

fails = []
def ok(cond, label):
    if cond:
        print('  ok  ' + label)
    else:
        print('  FAIL ' + label)
        fails.append(label)


def fn(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m:
        raise SystemExit('FAIL: cannot find %s' % name)
    i = js.index('{', m.end() - 1)
    depth, j = 0, i
    while j < len(js):
        if js[j] == '{':
            depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1]


# ═════════ A. the drift guard ═════════
print('\nA. the embedded SQL cannot drift from the .sql file')

m = re.search(r'const BREAKEVEN_SQL_BODY = `(.*?)`;\n', js, re.S)
ok(m is not None, 'BREAKEVEN_SQL_BODY is embedded')
body = m.group(1) if m else ''

# Strip -- comments first. A comment that happens to contain `as "Foo"` reads
# as a column to a naive extractor, which is exactly what tripped this guard
# when v10.21 added one.
def outcols(text):
    nocomments = re.sub(r'--[^\n]*', '', text)
    return re.findall(r'as "([^"]*)"', nocomments)

fileCols = outcols(sqlfile)
embedCols = outcols(body)
ok(len(fileCols) == 58, 'the .sql file still emits 58 columns (got %d)' % len(fileCols))
ok(len(set(fileCols)) == len(fileCols),
   'no duplicate column names (dupes: %s)'
   % sorted({c for c in fileCols if fileCols.count(c) > 1}))
ok(embedCols == fileCols,
   'embedded SQL emits the SAME columns in the SAME order as the .sql file')

# Blake's named deliverables, spelled exactly as his sheet expects them.
for c in ['SKU', 'ASIN', 'Price', 'Should be FBA Fee', 'FBA Fee Variance',
          'Referral Fees', 'COGS+Shipping+Storage', 'Finance cost Adjustment',
          'Total Cost', 'Non-Ad Profit', 'Break Even ACOS pct',
          'Break Even ROAS', 'Confidence Flag', 'Actual ACOS pct',
          'Stock Cover Months', 'Excess Stock']:
    ok(c in embedCols, 'column present: %s' % c)

# The params CTE must NOT be embedded — it is the page's inputs now.
ok('with params as' not in body, 'the params CTE is not baked into the body')
ok(body.lstrip().startswith('econ as ('), 'the body starts where the params CTE ended')
# A template literal cannot survive these.
for hz, name in [('`', 'backtick'), ('${', 'dollar-brace')]:
    ok(hz not in body, 'embedded SQL contains no %s' % name)


# ═════════ B. the generated query ═════════
print('\nB. behaviour — breakevenSql builds a valid params CTE')

h = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};
const BREAKEVEN_SQL_BODY = 'econ as ( /* body */ )';
BUILDER

const q = breakevenSql(90, 0, 2, 25);
t('starts with a WITH, so exec_sql accepts it', /^with params as \(/.test(q), true);
t('body is appended', q.includes('econ as ( /* body */ )'), true);
t('defaults land verbatim', /90 as win_days/.test(q), true);
t('finance rate rendered as numeric', /0\.0000::numeric as fin_rate/.test(q), true);
t('soh target rendered as numeric', /2\.00::numeric as soh_target_mo/.test(q), true);
t('min units rendered as int', /25::int as min_units_for_confidence/.test(q), true);

// Real values from the page.
const q2 = breakevenSql(180, 0.12, 3.5, 40);
t('window honoured', /180 as win_days/.test(q2), true);
t('12% cost of capital honoured', /0\.1200::numeric/.test(q2), true);
t('3.5 months honoured', /3\.50::numeric/.test(q2), true);
t('40 min units honoured', /40::int/.test(q2), true);

// ── the guard that matters: a junk input must not reach the database as
// syntax. The params are rebuilt from numbers, never string-patched in.
for (const junk of ['; drop table products', '90); select 1 --', 'abc', '', null, undefined, NaN, Infinity]) {
  const bad = breakevenSql(junk, junk, junk, junk);
  t('junk input ' + JSON.stringify(String(junk)) + ' cannot inject',
    /drop|insert|delete|update|truncate|--/i.test(bad.split('econ as (')[0]), false);
  t('junk input ' + JSON.stringify(String(junk)) + ' still yields a numeric CTE',
    /select \d+ as win_days,\s*\n\s*[\d.]+::numeric as fin_rate/.test(bad), true);
}

// Degenerate numbers are clamped rather than emitted as nonsense.
t('window clamps to at least 1 day', /select 1 as win_days/.test(breakevenSql(0, 0, 2, 25)), true);
t('window clamps a negative too', /select 1 as win_days/.test(breakevenSql(-5, 0, 2, 25)), true);
t('min units floors at 0', /0::int/.test(breakevenSql(90, 0, 2, -3)), true);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
h = h.replace('BUILDER', fn('breakevenSql'))
tmp = os.path.join(tempfile.gettempdir(), 'test_v1019_sql.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(h)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('breakevenSql behaviour')


# ═════════ C. the page ═════════
print('\nC. static — the tab is wired and the CSV is complete')

ok('id="pnl-amzn-tab-breakeven"' in src, 'the tab button exists')
ok("['pnl-amzn-tab-breakeven',  'breakeven']" in js
   or "['pnl-amzn-tab-breakeven', 'breakeven']" in js,
   'the tab is in the subtabApply table (v10.17 round trip)')
ok("'breakeven'" in js and "'adactivity','breakeven'" in js.replace(' ', ''),
   'breakeven is accepted by switchPnlAmazonView')
ok('id="pnl-amzn-breakeven-wrap"' in src, 'the panel exists')
ok("beWrap.style.display   = view === 'breakeven'" in js, 'the panel toggles with the tab')

# The four assumptions are inputs, not SQL you hand-edit.
for i, why in [('be-win-days', 'window'), ('be-fin-rate', 'finance rate'),
               ('be-soh-mo', 'SOH target'), ('be-min-units', 'min units')]:
    ok(('id="%s"' % i) in src, 'the %s is an input on the page' % why)

# The CSV is Blake's contract: every column, his header names, hidden or not.
csv = fn('downloadBreakevenCSV')
ok('breakevenCols' in csv and 'breakevenVisibleCols' not in csv,
   'CSV exports EVERY column, not just the visible ones')
ok('ufeff' in csv or '﻿' in csv, 'CSV carries a UTF-8 BOM so Excel reads it')

# exec_sql is a one-time install; a missing one must say so by name.
runner = fn('runBreakeven')
ok('exec_sql' in runner and 'supabase_create_exec_sql.sql' in runner,
   'a missing exec_sql names the migration file instead of a raw error')
ok("sb.rpc('exec_sql'" in runner,
   'routed through the Supabase client so the JWT is attached (the v4.85 lesson)')

# The shared Amazon P&L filter strip (Region / Period / Brand / Category) does
# nothing on this view — it is US-only with its own window. A live-looking
# control that is ignored is worse than no control, so it is hidden.
ok('id="pnl-amzn-controls"' in src, 'the shared controls bar is addressable')
ok("ctrls.style.display = view === 'breakeven' ? 'none' : 'flex'" in js,
   'the shared controls bar is hidden on Break-Even and restored elsewhere')

# Audit columns hidden on screen, never dropped from the export.
ok("BREAKEVEN_AUDIT_PREFIX = 'aud '" in js, 'audit columns are identified by prefix')
audFile = [c for c in fileCols if c.startswith('aud ')]
ok(len(audFile) == 8, 'the .sql file has 8 audit columns (got %d)' % len(audFile))


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.19 — all green')
