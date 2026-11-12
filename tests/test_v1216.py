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
print("\nC. the refusal names the cause it KNOWS")
# ===========================================================================
TAC = fn_flat("adsTacosFor")
ok("r.bases || []" in TAC, "C1  it reads the loaded rows' basis")
ok("/shipped/.test(String(b))" in TAC, "C2  ...and tests for shipped")
# The sentence is built by concatenation, so it is matched on a contiguous
# fragment rather than on the whole rendered string.
ok("INTO Walmart, not what customers bought out of it" in TAC,
   "C3  /!\\ and says what the feed actually measures")
ok("SHIPPED-based (shipped_based_net_sales_amount)" in TAC,
   "C3b ...naming the column, so it can be checked against the export")
ok("point-of-sale / " in TAC or "point-of-sale" in TAC,
   "C4  ...and what would fix it")
# /!\ v12.13's advice is GONE. It sent him to check item numbers, and nothing
# was unmapped - 0 rows without a master_id, 0 without a cost_per_each.
ok("Check that every product sold here has a Walmart item" not in TAC,
   "C5  /!\\ and the wrong advice about item numbers is gone")
# Where the basis is unknown the message must not claim shipped.
ok("measuring something narrower than total sales" in TAC,
   "C6  /!\\ an unknown basis says only what is certain")

LOAD = fn_flat("adsLoadOurRev")
ok("max(w.source) basis" in LOAD, "C7  the query returns the basis")
ok("const bases = [...new Set(" in LOAD,
   "C8  /!\\ bases are COLLECTED, not reduced to the first - a table holding "
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
