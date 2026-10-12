# -*- coding: utf-8 -*-
"""
v10.25 — the Break-Even query referenced a column that was out of scope.

    column "amzn_net_proceeds" does not exist

The v10.22 Contribution columns read amzn_net_proceeds in the FINAL select, but
the `base` CTE only ever projected the per-unit form (amzn_np_pu). The raw total
stayed behind in `econ`, so the outer select could not see it and EVERY run of
the tab failed.

Why nothing caught it:
  - node --check passes; this is SQL inside a string, not JavaScript.
  - The v10.19 drift guard compares the two copies' OUTPUT column lists. Both
    copies were broken IDENTICALLY, so they matched.
  - v10.22 shipped without an end-to-end run; CLAUDE.md said so at the time.

So the guard this suite adds is scope resolution: every bare identifier the
outer select reads must actually be projected by the CTE chain beneath it.
That is the check that would have failed on v10.22.
"""
import io
import os
import re
import sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
QFILE = os.path.join(ROOT, 'query_amazon_breakeven_acos.sql')

src = io.open(INDEX, encoding='utf-8', newline='').read()
sqlfile = io.open(QFILE, encoding='utf-8', newline='').read()

fails = []
def ok(cond, label):
    if cond:
        print('  ok  ' + label)
    else:
        print('  FAIL ' + label)
        fails.append(label)


def strip_comments(t):
    return re.sub(r'--[^\n]*', '', t)


def strip_literals(t):
    """Blank out '...' string literals.

    Without this, the words inside a CASE label ('low volume - unreliable
    per unit cost') read as column references and the scope check cries
    wolf. A check that cries wolf is a check that gets ignored."""
    return re.sub(r"'(?:[^']|'')*'", " '' ", t)


def embedded_sql():
    """The copy that actually runs, lifted out of the BREAKEVEN_SQL_BODY literal."""
    m = re.search(r'const BREAKEVEN_SQL_BODY\s*=\s*`(.*?)`;', src, re.S)
    if not m:
        raise SystemExit('FAIL: cannot find BREAKEVEN_SQL_BODY')
    return m.group(1)


def cte_body(text, name):
    """Body of `name as ( ... )`, sliced by paren balance so nested parens survive."""
    m = re.search(r'\b%s\s+as\s*\(' % re.escape(name), text, re.I)
    if not m:
        raise SystemExit('FAIL: cannot find CTE %s' % name)
    i = m.end() - 1
    depth, j = 0, i
    while j < len(text):
        if text[j] == '(':
            depth += 1
        elif text[j] == ')':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return text[i + 1:j]


def outer_select(text):
    """Everything after the last CTE: the final `select ... from final ...`."""
    m = re.search(r'\nselect\b(.*?)\nfrom\s+final\b', text, re.S | re.I)
    if not m:
        raise SystemExit('FAIL: cannot find the outer select')
    return m.group(1)


def projected_aliases(body):
    """Column names a CTE exposes: every `as <ident>` and every `as "Quoted"`."""
    body = strip_comments(body)
    out = set(re.findall(r'\bas\s+([a-z_][a-z0-9_]*)\s*(?:,|$)', body, re.I | re.M))
    out |= set(re.findall(r'\bas\s+"([^"]+)"', body))
    return out


def passthrough_cols(body):
    """Bare `x.col` / `col,` projections that are NOT behind an `as`."""
    body = strip_comments(body)
    cols = set()
    # table-qualified passthroughs: `p.sp_sku,` `e.net_units,`
    # Trailing comma OR end of the select list (the last item before FROM
    # has none -- that is how pr.min_units_for_confidence was being missed).
    for m in re.finditer(
            r'(?<![\w.])[a-z]{1,4}\.([a-z_][a-z0-9_]*)\s*(?=,|\n\s*from\b)',
            body, re.I):
        cols.add(m.group(1))
    return cols


# ═════════ A. the fix is present in BOTH copies ═════════
print('\nA. the fix — base now carries the raw total forward')

emb = embedded_sql()
for label, text in (('index.html (the copy that runs)', emb), ('query_….sql (the file)', sqlfile)):
    base = cte_body(text, 'base')
    ok(re.search(r'as\s+amzn_net_proceeds\s*,', base) is not None,
       '%s — base projects amzn_net_proceeds' % label)
    ok('as amzn_np_pu' in base,
       '%s — and still projects the per-unit amzn_np_pu' % label)

# ⚠ The regression guard: reproduce the pre-v10.25 base (fix line removed) and
# assert the outer select really DID reference a name it could not see.
base_now = cte_body(emb, 'base')
base_before = re.sub(r'\n\s*round\(e\.amzn_net_proceeds, 2\)[^\n]*\n', '\n', base_now)
ok(base_before != base_now, 'regression guard — pre-v10.25 base reconstructed')
ok('as amzn_net_proceeds' not in strip_comments(base_before),
   'regression guard — the old base genuinely did NOT project it')
ok('amzn_net_proceeds' in strip_comments(outer_select(emb)),
   'regression guard — while the outer select genuinely DOES read it')


# ═════════ B. scope resolution — the check that would have caught v10.22 ═════════
print('\nB. every identifier the outer select reads resolves in the CTE chain')

# base → costed (b.*) → final (c.*) → outer select. Each layer adds its own.
in_scope = set()
in_scope |= projected_aliases(base_now)
in_scope |= passthrough_cols(base_now)
in_scope |= projected_aliases(cte_body(emb, 'costed'))
in_scope |= projected_aliases(cte_body(emb, 'final'))

sel = strip_literals(strip_comments(outer_select(emb)))
# Drop the output names (they are being DEFINED here, not read).
sel_reads = re.sub(r'\bas\s+"[^"]+"', ' ', sel)

SQL_WORDS = {
    'select', 'from', 'where', 'as', 'round', 'coalesce', 'nullif', 'case', 'when',
    'then', 'else', 'end', 'and', 'or', 'not', 'null', 'is', 'in', 'order', 'by',
    'desc', 'asc', 'cast', 'numeric', 'int', 'text', 'date', 'greatest', 'least',
    'abs', 'sum', 'min', 'max', 'avg', 'count', 'left', 'join', 'on', 'distinct',
}

referenced = set()
for m in re.finditer(r'(?<![\w."])([a-z_][a-z0-9_]*)', sel_reads, re.I):
    w = m.group(1).lower()
    if w in SQL_WORDS or w.isdigit():
        continue
    referenced.add(w)

# The sweep must not pass by accident on an emptied haystack (the v10.20
# lesson). A real identifier has to survive the stripping, and a word that
# only ever appears inside a string literal has to be gone.
ok('amzn_net_proceeds' in referenced,
   'guard the guard — a real identifier survives literal-stripping')
ok('unreliable' not in referenced,
   'guard the guard — a word only inside a string literal is stripped')

unresolved = sorted(w for w in referenced if w not in in_scope)
ok(not unresolved,
   'no unresolved identifiers in the outer select'
   + ('' if not unresolved else ' — found: ' + ', '.join(unresolved)))

# Name the specific one this release is about, so a future refactor that drops
# the projection again fails on a line that says why.
ok('amzn_net_proceeds' in in_scope,
   'amzn_net_proceeds specifically resolves (the v10.25 bug)')
for col in ['nonsp_ad_spend', 'unit_cogs_only', 'net_units', 'net_sales']:
    ok(col in in_scope, 'the other v10.22 Contribution input %r resolves' % col)


# ═════════ C. the two copies still agree (the v10.19 drift guard) ═════════
print('\nC. drift — the embedded copy and the file still emit the same columns')

def outcols(text):
    return re.findall(r'as "([^"]*)"', strip_comments(text))

emb_cols, file_cols = outcols(emb), outcols(sqlfile)
ok(emb_cols == file_cols,
   'identical output column lists (%d vs %d)' % (len(emb_cols), len(file_cols)))
ok(len(emb_cols) == len(set(emb_cols)), 'no duplicate output column names')

# The fix must NOT have changed the output contract — it is an internal
# passthrough, deliberately unquoted so it cannot leak into the CSV.
ok('amzn_net_proceeds' not in emb_cols,
   'the carried-forward total is internal only — not a new output column')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.25 — all green')
