#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.16 - the Walmart sales feed is SHIPPED, and the refusal says so.

Jason: "i upload the walmart 1P sales already, what are you talking about"
...and then the file, whose header settles it:

    shipped_based_net_sales_amount_this_year
    shipped_based_quantity_this_year

/!\ IT MEASURES WHAT WE SHIPPED INTO WALMART, NOT WHAT SOLD OUT OF IT. Over
one window the two feeds disagree by 2.2x on UNITS - ads 4,758, shipments
2,142 - at the same ~$7 per unit, which is the shape of sell-through
exceeding replenishment.

/!\ AND v12.13's REFUSAL GAVE WRONG ADVICE. It blamed item coverage and sent
him to check Walmart item numbers; nothing was unmapped - 0 rows without a
master_id, 0 without a cost_per_each. I had inferred the cause from a TOOLTIP
rather than from the export, which is the same mistake v11.80 is about.
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

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


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def line_of(pat):
    for ln in js.split("\n"):
        if pat in ln:
            return ln
    raise SystemExit("not found: " + pat)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.16  shipped is not sold")
print("=" * 70)

PARSE = fn_flat("parseWalmartCSV")

# /!\ The REAL header, from the export Jason uploads every week. Not committed
# as data - these are column names, and they are the whole point.
REAL = ("walmart_calendar_week,vendor_number,item_description_2,item_name,vendor_name,"
        "product_name,product_description,walmart_item_number,"
        "shipped_based_net_sales_amount_this_year,shipped_based_quantity_this_year")

DRIVER = r"""
'use strict';
__PARSE_DEPS__
// The sniff, lifted from the parser so the suite drives the REAL expression.
const sniff = (headers) => {
  const _h = headers.join(' ');
  return __EXPR__;
};
console.log(JSON.stringify({
  real:    sniff(__REAL__.split(',')),
  posUnd:  sniff(['walmart_calendar_week', 'walmart_item_number', 'pos_net_sales', 'pos_quantity']),
  posBare: sniff(['week', 'item', 'pos', 'net_sales']),
  posDash: sniff(['week', 'item', 'pos-net-sales', 'pos-quantity']),
  sellthr: sniff(['week', 'item', 'sell_through_net_sales', 'sell_through_qty']),
  plain:   sniff(['week', 'item', 'net_sales', 'quantity']),
  // /!\ must NOT be read as pos: a word merely containing those letters.
  position: sniff(['week', 'item', 'position', 'net_sales']),
}));
"""

m = re.search(r"const wmBasis = (/shipped[\s\S]*?)\n                : null;", PARSE)
EXPR = (m.group(1) + "\n                : null") if m else None
ok(EXPR is not None, "A0  the basis expression was found in the parser")

A = run_node(os.path.join(SP, "_v1216_a.js"),
             DRIVER.replace("__PARSE_DEPS__", "")
                   .replace("__EXPR__", EXPR)
                   .replace("__REAL__", json.dumps(REAL)))

# ===========================================================================
print("\nA. the basis is read off the header")
# ===========================================================================
eq("A1  /!\\ Jason's real weekly export is SHIPPED", A["real"], "shipped")
eq("A2  a POS export reads as pos", A["posUnd"], "pos")
# /!\ THE REGRESSION. My first cut used \bpos\b - and `_` is a word character,
# so `pos_net_sales` did not match while sell_through did. Caught by driving
# it, not by reading it.
eq("A3  /!\\ pos_ is matched - `_` is a word character, so \\bpos\\b missed it",
   A["posUnd"], "pos")
eq("A4  ...and pos- too", A["posDash"], "pos")
eq("A5  ...and a bare pos column", A["posBare"], "pos")
eq("A6  sell_through counts as pos", A["sellthr"], "pos")
eq("A7  /!\\ an unmarked header claims NOTHING rather than guessing",
   A["plain"], None)
eq("A8  /!\\ and `position` is not read as pos", A["position"], None)

# ===========================================================================
print("\nB. /!\\ IT TRAVELS BY RETURN VALUE, NOT BY SCOPE")
# ===========================================================================
# My first cut computed the basis in parseWalmartCSV and referenced it inside
# walmartApplyImport - a DIFFERENT function. That is a ReferenceError on every
# upload, and `node --check` passes it, because scope is not syntax.
ok("basis: wmBasis }" in PARSE or "basis: wmBasis };" in PARSE,
   "B1  the parser RETURNS the basis")
IMP = fn_flat("walmartApplyImport")
ok("_wmImport.basis" in IMP,
   "B2  /!\\ and the importer reads it off the parse result")
ok("wmBasis" not in IMP,
   "B3  /!\\ it does NOT reference the parser's local - that threw on every upload")
eq("B4  wmBasis exists only inside the parser", js.count("wmBasis"), 2)
ok("source: _wmImport.basis ? ('walmart:' + _wmImport.basis) : 'walmart'," in IMP,
   "B5  ...and an unmarked file still writes the plain source it always did")

# ===========================================================================
print("\nC. /!\\ v12.17 - the basis is SURFACED, not used to refuse")
# ===========================================================================
# This section asserted the shipped-vs-sold explanation the refusal gave. That
# explanation was wrong - `shipped_based_` is an eComm measure, so it means
# shipped to the CUSTOMER, and AUTH came back within 0.1% of it. The refusal
# is gone with the reasoning.
#
# What survives, and is worth keeping, is the PROVENANCE: the app records
# which export the denominator came from, so nobody has to infer it from a
# column name again - which is how three wrong explanations got shipped.
TAC = fn_flat("adsTacosFor")
ok("r.bases || []" in TAC, "C1  the basis is read off the loaded rows")
ok("salesBasis" in TAC, "C2  ...and carried on the result")
# v12.19 - PROVENANCE IS NOT DERIVATION, so it came off the tooltip. It is
# still recorded at upload and still rides the result; what changed is that a
# hover no longer spends a paragraph on it.
ok("salesBasis," in fn_flat("adsTacosFor"),
   "C3  /!\\ the basis still rides the result, where a consumer can read it")
ok("basis: wmBasis" in PARSE,
   "C3b ...stamped at upload rather than inferred at read time")
# /!\ BOTH WRONG EXPLANATIONS ARE GONE.
ok("Check that every product sold here has a Walmart item" not in TAC,
   "C4  /!\\ v12.13's item-number advice is gone")
ok("INTO Walmart, not what customers bought out of it" not in TAC,
   "C5  /!\\ and v12.16's shipped-into-Walmart explanation too")
# /!\ AND IT NO LONGER REFUSES. TACoS divides by TOTAL sales, so a numerator
# that over-attributes cannot invalidate it.
ok("overAttr" in TAC, "C6  /!\\ the contradiction is a note")
ok("overAttr," in fn_flat("adsTacosFor"),
   "C7  ...carried as a note on the result, never as a refusal")

LOAD = fn_flat("adsLoadOurRev")
ok("max(w.source) basis" in LOAD, "C8  the query returns the basis")
ok("const bases = [...new Set(" in LOAD,
   "C9  /!\\ bases are COLLECTED, not reduced to the first - a table holding "
   "two of them is a worse problem than either")

print("\nD. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "D1  both declare a version")
eq("D2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
