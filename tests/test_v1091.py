# -*- coding: utf-8 -*-
r"""v10.91 - MAP (Minimum Advertised Price) as a product dimension.

Jason: "i need a new dim on the product table for MAP"

Adding a value-bearing column to `products` is an Architecture Rule #8
trigger. The column itself is the easy part; what fails SILENTLY is every
site that enumerates product fields:

  - runMerge's SIMPLE_BACKFILL_FIELDS - omit it and a duplicate's MAP is
    dropped when the survivor has none (the v5.45 class, which cost
    image_url and eight other fields)
  - the product modal's load AND save - either half missing means the
    field looks editable and silently never persists
  - bulk edit - a field in the dropdown with no coercion branch writes
    the raw string, or nothing

Plus one semantic that must not drift: blank MAP is NULL, never 0. A MAP
of $0.00 is a real (and nonsensical) advertised-price floor.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

ROOT = r'C:\Users\Jason\digital-forecast-engine'
RAW  = io.open(ROOT + r'\index.html', encoding='utf-8', newline='').read()
JS   = max(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond:
        P += 1; print('  ok  ' + label)
    else:
        F += 1; fails.append(label)
        print('  FAIL ' + label + (('  -> ' + str(got)) if got is not None else ''))

def fn(name):
    m = re.search(r'(?:async\s+)?function\s+' + name + r'\s*\(', JS)
    if not m: return ''
    i = JS.index('{', m.end() - 1)
    depth = 0
    for j in range(i, len(JS)):
        if JS[j] == '{': depth += 1
        elif JS[j] == '}':
            depth -= 1
            if depth == 0: return JS[m.start():j + 1]
    return ''


# ── A. Migration ───────────────────────────────────────────────────────────
print('\nA. the migration exists and is idempotent')

SQL = io.open(ROOT + r'\supabase_v10_91_product_map_price.sql', encoding='utf-8').read()
ok('add column if not exists map_price' in SQL, 'adds map_price idempotently')
ok('numeric' in SQL, 'stored as numeric, not text')
# Check the DDL STATEMENT, not the file - the header comment legitimately
# contains the word "default" while explaining why there isn't one.
_ddl = re.search(r'alter table products\s+add column if not exists map_price[^;]*;', SQL, re.I)
ok(bool(_ddl), 'the add-column statement is parseable')
ok('default' not in (_ddl.group(0).lower() if _ddl else 'default'),
   'the column has no DEFAULT - blank must stay NULL, not become 0',
   _ddl.group(0) if _ddl else None)
ok('comment on column products.map_price' in SQL, 'the column documents itself')
ok('create index if not exists' in SQL, 'partial index for the populated rows')

# The name must match the one chewy_catalog already uses, or a future join
# reads as two different concepts.
CHEWY = io.open(ROOT + r'\supabase_v10_11_chewy_catalog.sql', encoding='utf-8').read()
ok('map_price' in CHEWY, 'chewy_catalog already uses the same column name')


# ── B. Products table column ───────────────────────────────────────────────
print('\nB. the column is registered, sortable and exportable')

m = re.search(r"\{\s*key:'map_price'.*?csv:[^}]*\}", JS, re.S)
ok(bool(m), 'map_price entry in PROD_COLUMNS')
col = m.group(0) if m else ''
ok("label:'MAP'" in col, 'labelled MAP')
ok("group:'commerce'" in col, 'grouped with the other pricing fields')
ok('default:false' in col, 'opt-in, so no saved column set shifts')
ok('sortVal:' in col, 'sortable')
ok('csv:' in col, 'exportable')
ok('tip:' in col, 'carries a header tooltip explaining what MAP is')

# Blank must render as a dash, never $0.00.
ok("map_price == null" in col, 'blank is detected explicitly')
ok(chr(0x2014) in col or '\\u2014' in col, 'blank renders as an em dash')

# A MAP at or above MSRP cannot be enforced as written - flag, do not hide.
ok('>= msrp' in col, 'MAP >= MSRP is detected')
ok('sp-orange' in col, 'and surfaced in orange rather than silently rendered')

# It must sit between MSRP and Wholesale - the pricing ladder reads
# list > MAP > wholesale.
order = [k for k in re.findall(r"key:'(msrp|map_price|wholesale)'", JS)]
ok(order[:3] == ['msrp', 'map_price', 'wholesale'],
   'column order is MSRP -> MAP -> Wholesale', order[:3])


# ── C. Product modal: load AND save ────────────────────────────────────────
print('\nC. the modal both loads and saves it')

opm = fn('openProductModal')
ok(bool(opm), 'openProductModal located')
ok('pf-map-price' in opm, 'modal LOADS map_price')
# v10.91 - the insert nearly orphaned this function's `async` (the v10.85
# trap: the anchor matched inside `async function ...`). Pin it.
ok(re.search(r'async\s+function\s+openProductModal\s*\(', JS) is not None,
   'openProductModal is still async (its awaits depend on it)')
ok('async //' not in JS, 'no orphaned async left anywhere')

sp = fn('saveProduct')
ok(bool(sp), 'saveProduct located')
ok('map_price:' in sp, 'modal SAVES map_price')
# The whole point of the explicit branch: `parseFloat('') || null` would
# also give null, but `parseFloat('0') || null` wrongly gives null too.
# Blank -> null, 0 -> 0.
mm = re.search(r"map_price:\s*\(\(\)\s*=>\s*\{(.*?)\}\)\(\)", sp, re.S)
ok(bool(mm), 'map_price uses an explicit coercion, not `|| null`')
body = mm.group(1) if mm else ''
ok("raw === ''" in body, 'blank is checked before parsing')
ok('return null' in body, 'blank becomes NULL')
ok('isFinite' in body, 'non-numeric input becomes NULL rather than NaN')

ok('<input' in RAW and 'id="pf-map-price"' in RAW, 'the input exists in markup')
tag = re.search(r'<input[^>]*id="pf-map-price"[^>]*>', RAW)
ok(bool(tag), 'map input tag located')
t = tag.group(0) if tag else ''
ok(t.count('oninput=') == 1, 'exactly one oninput handler (no duplicate attr)', t.count('oninput='))
ok('type="number"' in t, 'numeric input')
ok('title=' in t, 'explains that blank is not $0.00')


# ── D. The inline sanity check ─────────────────────────────────────────────
print('\nD. MAP above list price is flagged while editing')

pc = fn('pfCheckMap')
ok(bool(pc), 'pfCheckMap exists')
ok('pf-map-note' in pc, 'it drives a visible note')
ok('map >= msrp' in pc, 'it compares MAP against MSRP')
ok("display = 'none'" in pc or "style.display = 'none'" in pc,
   'and clears the note when the values are sane')
ok('pfCheckMap()' in t, 'the input calls it as you type')


# ── E. Bulk edit ───────────────────────────────────────────────────────────
print('\nE. bulk edit can set it')

be = fn('prodOpenBulkEdit')
ok('value="map_price"' in be, 'MAP is offered in the bulk-edit field list')
ok('Pricing' in be, 'under the Pricing group')

ba = fn('prodBulkApply')
ok("field === 'map_price'" in ba, 'bulk edit has a coercion branch for MAP')
# It must share the currency branch with msrp/wholesale, not fall through to
# the string branch, or a bulk set would write "5.99" as text.
cur = re.search(r"field === 'msrp' \|\| field === 'wholesale' \|\| field === 'map_price'", ba)
ok(bool(cur), 'MAP is coerced as currency alongside msrp + wholesale')


# ── F. Architecture Rule #8 ────────────────────────────────────────────────
print('\nF. a merge cannot silently drop it')

rm = fn('runMerge')
ok(bool(rm), 'runMerge located')
sbf = re.search(r'SIMPLE_BACKFILL_FIELDS = \[(.*?)\]', rm, re.S)
ok(bool(sbf), 'SIMPLE_BACKFILL_FIELDS located')
fields = re.findall(r"'([a-z_]+)'", sbf.group(1) if sbf else '')
ok('map_price' in fields, 'map_price is backfilled onto the survivor', fields)
# Sanity: the fields it sits beside are still there (guards a bad edit).
for f_ in ['msrp', 'wholesale', 'image_url']:
    ok(f_ in fields, f_ + ' still backfilled')


print('\n' + '=' * 62)
print(f'  v10.91  PASS {P}   FAIL {F}')
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
