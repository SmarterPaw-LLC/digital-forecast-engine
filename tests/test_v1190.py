#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.90 - the merge carries every table that carries master_id.

- Jason, with the confirm dialog open: "can you make sure this merge will
  work for amazon data?" ... "please make sure every change shipped looks at
  the merge function."

It would not have. Measured on his own pair before answering:

    SP-TEMP-B0HJDDN85X -> SP-0555 (Frosticles)
    amazon_sales_traffic   6 rows on the duplicate, 0 on the survivor
    and that FK is ON DELETE CASCADE

So the rows were not orphaned, they were DELETED with the duplicate - six
weeks of the product's launch ramp - and `deleted_rows` does not snapshot
that table, so undo could not have restored them either.

This class has bitten SIX times: sku_economics_eu (v4.145), chewy_sales_weekly
(v7.76), fba_fee_preview (v9.75), amazon_storage_fees (v11.79, caught in
time), and now four Amazon traffic tables plus two more found by auditing
all 26 rather than the four the v11.79 note named.

Remembering is not working, so the rule is structural: MERGE_MASTER_ID_TABLES
declares every table and what the merge does to it, and this suite fails the
build when that declaration and runMerge disagree IN EITHER DIRECTION.

  * A  the registry and runMerge agree, both ways.
  * B  every disposition is valid and every non-reassign carries its reason.
  * C  every table declaring a master_id column in the repo's SQL is declared.
  * D  undo reverses generically, so a new table needs no undo change.
  * E  the confirm dialog names what it touches.
  * F  the regression guard: the six tables this release adds.
"""
import io, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="",
            errors="replace").read()
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0


def ok(cond, label, extra=None):
    global passed, failed
    if cond:
        passed += 1; print("  ok    %s" % label)
    else:
        failed += 1
        print("  FAIL  %s%s" % (label, ("  got: %s" % ascii(extra)) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


# --------------------------------------------------------------- the registry
m = re.search(r"const MERGE_MASTER_ID_TABLES = \{([\s\S]*?)\n\};", js)
if not m:
    print("  FAIL  MERGE_MASTER_ID_TABLES not found"); sys.exit(1)
block = m.group(1)
# Strip comments so a table named inside one is not read as an entry.
body = re.sub(r"(?m)^\s*//.*$", "", block)
REG = {}
for em in re.finditer(r"(?m)^\s*([a-z0-9_]+):\s*\{\s*d:\s*'([a-z]+)'(.*)$", body):
    REG[em.group(1)] = {"d": em.group(2), "rest": em.group(3)}

# runMerge's ACTUAL calls.
CALLS = re.findall(r"reassignMasterId\('([a-z0-9_]+)'\)", js)
# The declaration inside the helper itself is `reassignMasterId(table)`, so it
# does not match the quoted pattern and cannot inflate this.
CALLSET = set(CALLS)

# ---------------------------------------------------------------------------
print("A. the registry and runMerge agree, both ways")
# ---------------------------------------------------------------------------
ok(len(REG) >= 26, "A1  the registry declares every master_id table", len(REG))
declared_reassign = {k for k, v in REG.items() if v["d"] == "reassign"}

missing = sorted(declared_reassign - CALLSET)
eq("A2  /!\\ every declared 'reassign' is actually called in runMerge", missing, [])

undeclared = sorted(CALLSET - declared_reassign)
eq("A3  /!\\ every runMerge call is declared - no silent additions", undeclared, [])

# A table called twice would be a merge doing double work and an undo list
# with duplicate ids in it.
dupes = sorted({t for t in CALLS if CALLS.count(t) > 1})
eq("A4  no table is reassigned twice", dupes, [])

# ---------------------------------------------------------------------------
print("\nB. the dispositions are real")
# ---------------------------------------------------------------------------
bad = sorted({k for k, v in REG.items() if v["d"] not in ("reassign", "special", "skip")})
eq("B1  every disposition is reassign / special / skip", bad, [])

# /!\ A table that is NOT reassigned has to say WHY, because that is the
# decision this whole suite exists to stop being made silently.
nowhy = sorted({k for k, v in REG.items()
                if v["d"] in ("special", "skip") and "why:" not in v["rest"]})
eq("B2  /!\\ every non-reassigned table carries its reason", nowhy, [])

for t in ("products", "inventory", "product_cogs"):
    eq("B3  %s is handled by its own block" % t, REG.get(t, {}).get("d"), "special")
for t in ("velocity_calculated", "walmart_cost_per_each"):
    eq("B4  %s is a declared skip" % t, REG.get(t, {}).get("d"), "skip")

# Those two are skipped because reassignMasterId selects `id` and they have
# none - so the reason has to name that, not merely exist.
for t in ("velocity_calculated", "walmart_cost_per_each"):
    ok("primary key" in REG.get(t, {}).get("rest", ""),
       "B5  ...and %s says it has no primary key to address" % t)

# ---------------------------------------------------------------------------
print("\nC. the repo's own SQL cannot introduce an undeclared table")
# ---------------------------------------------------------------------------
sql_tables = set()
for f in sorted(os.listdir(ROOT)):
    if not f.endswith(".sql"):
        continue
    t = io.open(os.path.join(ROOT, f), encoding="utf-8", errors="replace").read()
    for cm in re.finditer(r"create table (?:if not exists )?(?:public\.)?([a-z0-9_]+)\s*\(", t, re.I):
        rest = t[cm.end():]
        end = rest.find(");")
        blk = rest[:end] if end > 0 else rest[:4000]
        # /!\ A COLUMN DECLARATION, not a substring. `src_master_id` on
        # merge_history contains "master_id" and is not one - matching loosely
        # put two tables in this list that do not belong to it.
        if re.search(r"(?m)^\s*master_id\b", blk):
            sql_tables.add(cm.group(1))
    for am in re.finditer(r"(?i)alter table (?:public\.)?([a-z0-9_]+)\s+add column (?:if not exists )?master_id\b", t):
        sql_tables.add(am.group(1))

ok(len(sql_tables) >= 18, "C1  the SQL scan found the migrations", len(sql_tables))
eq("C2  /!\\ every table whose migration adds master_id is declared",
   sorted(sql_tables - set(REG)), [])
ok("merge_history" not in sql_tables,
   "C3  ...and src_master_id on merge_history is not read as one")

# ---------------------------------------------------------------------------
print("\nD. undo reverses generically")
# ---------------------------------------------------------------------------
um = re.search(r"async function runUndoMerge\(([\s\S]*?)\n\}", js)
undo = um.group(1) if um else ""
ok("Object.entries(reassigned)" in undo,
   "D1  /!\\ undo iterates the captured tables rather than a second list")
ok("update({ master_id: h.src_master_id })" in undo,
   "D2  ...and re-points each captured row by id")
# A hardcoded table list inside undo would be the second spelling that makes
# a new table need two edits instead of one.
for t in ("amazon_sales_traffic", "amazon_storage_fees", "sku_economics"):
    ok("'%s'" % t not in undo, "D3  undo names no table literally (%s)" % t)

# The capture is what makes that work, so it has to happen for every table.
rm = re.search(r"async function reassignMasterId\(table\) \{([\s\S]*?)\n    \}", js)
cap = rm.group(1) if rm else ""
ok("capturedIds[table] = ids" in cap,
   "D4  /!\\ reassignMasterId captures ids for EVERY table it touches")
ok("capturedIds[table] = capturedIds[table] || []" in cap,
   "D5  ...and a failure still leaves an entry rather than undefined")

# ---------------------------------------------------------------------------
print("\nE. the dialog names what it touches")
# ---------------------------------------------------------------------------
# /!\ SCOPED TO runMerge, AND ANCHORED ON THE CLOSING LINE. Two ways to read
# the wrong text, both of which this section hit:
#   - a non-greedy match to `))` stops inside `(${src.master_id})` on the
#     dialog's own first line, so it read three characters;
#   - searching the whole file starts at the FIRST `if (!confirm(` - a scenario
#     delete 48,000 lines earlier - and swallows everything between.
_mi = js.index("async function runMerge() {")
dlg = re.search(r"if \(!confirm\(([\s\S]*?)\n  \)\) return;", js[_mi:])
d = dlg.group(1) if dlg else ""
ok(bool(d), "E1  the confirm dialog is found")
for t in ("amazon_sales_traffic", "amazon_sp_search_term", "amazon_query_performance_asin"):
    ok(t in d, "E2  the dialog names %s" % t)
ok("fba_fee_preview" in d, "E3  ...and fba_fee_preview, missing since v9.75")
for t in ("pnl_action_items", "walmart_catalog"):
    ok(t in d, "E4  ...and %s" % t)
# /!\ IT SAID "This cannot be undone" AND THAT WAS FALSE - Merge History
# carries a working Undo button for every merge whose history row was written.
ok("cannot be undone" not in d,
   "E5  /!\\ the dialog no longer claims the merge is irreversible")
ok("Merge History" in d, "E6  ...it names where to undo it instead")

# ---------------------------------------------------------------------------
print("\nF. the regression guard - what this release added")
# ---------------------------------------------------------------------------
# /!\ THESE SIX WERE NOT IN runMerge AND EVERY ONE COULD LOSE ROWS.
# amazon_* and pnl_action_items are ON DELETE CASCADE (deleted with the
# duplicate); walmart_catalog is ON DELETE SET NULL (orphaned, the
# fba_fee_preview class). Read off pg_constraint on 2026-11-10.
ADDED = ['amazon_sales_traffic', 'amazon_sales_traffic_snapshot',
         'amazon_sp_search_term', 'amazon_query_performance_asin',
         'pnl_action_items', 'walmart_catalog']
for t in ADDED:
    ok(t in CALLSET, "F1  %s is reassigned" % t)
eq("F2  /!\\ and the list grew from 15 to 21", len(CALLSET), 21)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
