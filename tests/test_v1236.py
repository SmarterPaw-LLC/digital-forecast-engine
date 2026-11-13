#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.36 - the Chewy cost can be TYPED, and the case-qty note becomes a
tooltip.

Jason: "wtf? i can't set the cost per case for chewy on the 'cost to chewy'
tab. when i click on the row it opens the card. the card has no place to set
this" ... "also goddamnit why is this note here"

Both right. v12.35 reported 35 Chewy SKUs missing from the Catalog Details
export as something only an upload could fix - and the deeper fact is that
the app had NO way to enter a Chewy cost by hand at all, so those 35 priced
at nothing everywhere: the Cost to Chewy tab, the Chewy P&L, and Our Revenue.
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
        print("  FAIL  %s%s" % (label, ("  got: %s" % extra) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.36  a Chewy cost you can type")
print("=" * 70)

# ===========================================================================
print("\nA. /!\\ THE FALLBACK SITS AT THE ONE LOOKUP, so nine consumers get it")
# ===========================================================================
CF = fn_flat("chewyCatalogFor")
PX = fn_flat("chewyCatalogPricePerEach")

A = run_node(os.path.join(SP, "_v1236_a.js"), CF + "\n" + PX + r"""
const chewyCatalogByMaster = {
  EXPORTED: { cost: 24, purchase_uom: 'CS', item_name: 'From Chewy', msrp: 9.99 },
};
const allProducts = [
  { master_id: 'EXPORTED', chewy_sku: '111', case_qty: 12, chewy_cost: 99, chewy_cost_uom: 'CS' },
  { master_id: 'TYPED_CS', chewy_sku: '222', case_qty: 6,  chewy_cost: 30, chewy_cost_uom: 'CS' },
  { master_id: 'TYPED_EA', chewy_sku: '333', case_qty: null, chewy_cost: 4.25, chewy_cost_uom: 'EA' },
  { master_id: 'TYPED_LC', chewy_sku: '444', case_qty: 4,  chewy_cost: 20, chewy_cost_uom: 'cs' },
  { master_id: 'TYPED_NQ', chewy_sku: '555', case_qty: null, chewy_cost: 18, chewy_cost_uom: 'CS' },
  { master_id: 'NO_UOM',   chewy_sku: '666', case_qty: 3,  chewy_cost: 12 },
  { master_id: 'ZERO',     chewy_sku: '777', case_qty: 3,  chewy_cost: 0 },
  { master_id: 'NEG',      chewy_sku: '888', case_qty: 3,  chewy_cost: -5 },
  { master_id: 'NONE',     chewy_sku: '999', case_qty: 3 },
];
const by = (mid) => {
  const p = allProducts.find(x => x.master_id === mid);
  const cat = chewyCatalogFor(mid);
  const pe = chewyCatalogPricePerEach(cat, p && p.case_qty);
  return { manualRow: !!(cat && cat._manual), price: pe.price, reason: pe.reason,
           uom: pe.uom, manual: pe.manual };
};
console.log(JSON.stringify({
  exported: by('EXPORTED'), cs: by('TYPED_CS'), ea: by('TYPED_EA'),
  lower: by('TYPED_LC'), noQty: by('TYPED_NQ'), noUom: by('NO_UOM'),
  zero: by('ZERO'), neg: by('NEG'), none: by('NONE'),
  missing: chewyCatalogFor('NOT_A_PRODUCT'), blank: chewyCatalogFor(''),
}));
""")

eq("A1  /!\\ THE EXPORT WINS - a $99 hand entry does not override Chewy's own $24",
   A["exported"]["price"], 2)
ok(not A["exported"]["manual"], "A2  ...and it is not flagged as typed")
eq("A3  /!\\ a typed CASE cost divides by the case qty - 30/6", A["cs"]["price"], 5)
ok(A["cs"]["manual"], "A4  ...and IS flagged as typed")
eq("A5  a typed EACH cost is used as-is", A["ea"]["price"], 4.25)
eq("A6  the UOM is read case-insensitively", A["lower"]["price"], 5)
eq("A7  /!\\ a typed CASE cost with no case qty is the EXISTING reason, not a "
   "new one - and the card says which field fixes it",
   [A["noQty"]["price"], A["noQty"]["reason"]], [None, "no-case-qty"])
eq("A8  a cost with no UOM defaults to per-case, which is what 106 of the "
   "127 catalog rows are", A["noUom"]["price"], 4)
eq("A9  /!\\ zero is NOT a price", [A["zero"]["price"], A["zero"]["reason"]],
   [None, "no-catalog"])
eq("A10 ...nor is a negative one", A["neg"]["price"], None)
eq("A11 and a product with nothing typed falls through unchanged",
   [A["none"]["price"], A["none"]["reason"]], [None, "no-catalog"])
eq("A12 an unknown master_id is still null", A["missing"], None)
eq("A13 ...and so is a blank one", A["blank"], None)

ok(js.count("function chewyCatalogFor") == 1, "A14 one lookup")
ok("_manual: true" in CF, "A15 the synthesized row is marked at birth")
ok("chewyCatalogByMaster[mid]" in CF
   and CF.index("chewyCatalogByMaster[mid]") < CF.index("chewy_cost"),
   "A16 /!\\ the export is consulted FIRST, in the code as well as in effect")

# ===========================================================================
print("\nB. every consumer goes through it")
# ===========================================================================
# /!\ The point of synthesizing inside chewyCatalogFor is that nine call
# sites get the fallback without a tenth spelling of the division. That only
# holds while nobody reads the raw cache to price something.
_raw = [m.start() for m in re.finditer(r"chewyCatalogPricePerEach\(", js)]
_bad = []
for i in _raw:
    ctx = js[max(0, i - 260):i]
    if "chewyCatalogByMaster" in ctx.split("\n")[-6:][0:1] or "cyCat[" in ctx:
        _bad.append(js[i - 60:i + 40])
ok(not _bad, "B1  /!\\ nothing prices off the raw chewyCatalogByMaster cache", _bad[:2])
ok("chewyCatalogPricePerEach(chewyCatalogFor(mid), caseQty.get(mid))" in js,
   "B2  /!\\ v12.35's revenue pass was converted in this commit (rule #5)")
ok("const cyCat = (typeof chewyCatalogByMaster" not in js,
   "B3  ...and its raw-cache read is GONE, not left standing beside it")
ok(js.count("manual: pe.manual") >= 1,
   "B4  the Cost to Chewy row carries the provenance")

# ===========================================================================
print("\nC. /!\\ THE COVERAGE AUDIT DOES NOT SILENTLY HEAL")
# ===========================================================================
# Typing a cost does not put the SKU in Chewy's export, and that panel exists
# to report which SKUs the export is missing. The gap has to stand.
COST = fn_flat("renderChewyPnlCost")
ok("let gap = pe.reason || (pe.manual ? 'no-catalog' : null)" in COST,
   "C1  /!\\ a hand-priced SKU is STILL reported as missing from the export")
ok("'no-catalog-dormant'" in COST,
   "C2  ...and the dormant split it already had is untouched")
ok("✎" in COST,
   "C3  the Cost cell marks a typed figure so it cannot pass for an exported one")

# ===========================================================================
print("\nD. the card")
# ===========================================================================
ED = fn_flat("pfChewyCostEditor")
PV = fn_flat("pfChewyCostPreview")
ok('id="pf-chewy-cost"' in ED and 'id="pf-chewy-cost-uom"' in ED,
   "D1  the two fields exist")
ok(s.count('id="pf-chewy-cost"') == 1 and s.count('id="pf-chewy-cost-uom"') == 1,
   "D2  /!\\ exactly once each - the save reads them BY NAME, and a second "
   "copy writes a null silently (v10.87)")
ok("const dis = fromExport || !sku;" in ED,
   "D3  /!\\ disabled while Chewy's export answers the question, and when "
   "there is no Chewy SKU to price")
ok("Set a Chewy SKU in Classification below first" in ED,
   "D4  ...and it names the field that fixes the second case")
ok("disabled" in ED and "oninput=" in ED and "'disabled' : 'oninput=" in ED,
   "D5  /!\\ the handler is STRIPPED when disabled, not left to be ignored")
ok("chewyCatalogPricePerEach({ cost, purchase_uom: uom, _manual: true }, cq)" in PV,
   "D6  /!\\ the live preview drives the REAL helper, not a second division")
ok("pf-case-qty" in PV,
   "D7  ...against the case-qty box on the same card, which is the other "
   "half of a CS figure")
ok('oninput="pfChewyCostPreview()"' in s and s.count("pf-case-qty") >= 3,
   "D8  and editing the case qty re-runs it")

# the save
SAVE_OK = "const el = document.getElementById('pf-chewy-cost');" in js \
    and "if (!el || el.disabled) return {};" in js
ok(SAVE_OK, "D9  /!\\ ABSENT OR DISABLED MEANS UNTOUCHED - writing null while "
            "the export is answering would wipe a figure typed earlier")
ok("chewy_cost_uom: ok" in js, "D10 the UOM saves with it")
ok("chewy_cost: ok ? v : null" in js,
   "D11 ...and clearing the box clears both, rather than orphaning a UOM")

# the load path reads it back
ok("(p && p.chewy_cost != null) ? String(p.chewy_cost) : ''" in ED,
   "D12 the field repopulates from the product")
ok("String((p && p.chewy_cost_uom) || 'CS').toUpperCase()" in ED,
   "D13 ...and so does the UOM, defaulting to per-case")

# ===========================================================================
print("\nE. /!\\ THE NOTE IS A TOOLTIP NOW")
# ===========================================================================
# Jason: "also goddamnit why is this note here". Three sentences, a version
# number and two bold words under an input - my own standing rule (STOP UI
# TEXT BLOAT - tooltip it), broken on the one card where vertical space is
# finite.
ok("v7.27 — units per case for production pack-out" not in s,
   "E1  the prose block is gone from under the input")
ok("Units per case for production pack-out. Drives the Cases Needed column" in s,
   "E2  /!\\ ...and ALL of it moved to the tooltip, not a trimmed version")
ok('<label title="Units per case for production pack-out' in s,
   "E3  on the label, where the card's other collapsed prose lives")
ok("divides the Chewy case cost into a per-unit figure" in s,
   "E4  and it names the second thing the field now drives")
# v10.87: collapsing prose must not swallow an affordance.
ok("<a " not in "Units per case for production pack-out. Drives the Cases Needed column",
   "E5  /!\\ the paragraph held no link and no button, which is why all of "
   "it could move (the v10.87 check)")

# ===========================================================================
print("\nF. the migration")
# ===========================================================================
SQL = io.open(os.path.join(ROOT, "supabase_v12_36_chewy_manual_cost.sql"),
              encoding="utf-8").read()
ok("add column if not exists chewy_cost " in SQL
   and "add column if not exists chewy_cost_uom text" in SQL,
   "F1  both columns, idempotent")
ok("alter table public.products" in SQL,
   "F2  /!\\ on `products`, not in chewy_catalog - our number is ours, and "
   "writing it into the upload table would both be erased without trace and "
   "destroy the coverage audit")
ok("comment on column public.products.chewy_cost " in SQL,
   "F3  the column says what it is, in the database")
ok("No RLS change" in SQL,
   "F4  ...and no policy is needed: `products` already carries one")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
