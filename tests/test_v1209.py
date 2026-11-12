#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.09 - the product modal: vendor cost, the prose, and the grab-bag section.

Jason, on the product card:
  1. "why is all of this text here? this should be on the tool tip, not taking
      up space on the card modal."
  2. "there is no costing to vendors here (walmart, chewy)."
  3. "in general, the information on this card could be organized better."

/!\ A MODAL IS THE ONE SURFACE WHERE VERTICAL SPACE IS FINITE, which is what
makes (1) expensive rather than untidy: four lines of explanation pushed the
fields below the fold.
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


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("\n};", i) + 3]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.09  the product card")
print("=" * 70)

MODAL = s[s.index('id="pf-title"') - 4000:s.index('id="pf-notes"') + 400] \
    if 'id="pf-notes"' in s else s

# ===========================================================================
print("\nA. the prose is a tooltip now")
# ===========================================================================
DIMS = fn_flat("pfRenderDims")
# /!\ The paragraph is gone from the BODY and its content survives in a title.
ok("These are <strong>Amazon" not in js,
   "A1  /!\\ the four-line paragraph is out of the card body")
ok('data-prose="1"' in DIMS, "A2  it is a data-prose line")
ok("refreshed by the FBA Fee Preview upload" in DIMS,
   "A3  with a one-line caption")
ok("an edit would be overwritten on the next upload" in DIMS,
   "A4  /!\\ and the WHOLE explanation survives in the tooltip, not just a trim")
ok('cursor:help' in DIMS, "A5  ...and it reads as hoverable")
# /!\ v10.87's rule: collapsing prose must not take an affordance with it.
# There was nothing interactive in that paragraph, which is why the whole
# thing could move - asserted so a future edit that adds a link has to think.
ok("<a " not in DIMS and "button" not in DIMS,
   "A6  /!\\ nothing interactive was swallowed into a title=")

# ===========================================================================
print("\nB. what each vendor pays us")
# ===========================================================================
VEN = fn_flat("pfRenderVendorCost")
ok('id="pf-vendor-cost-section"' in s, "B1  the section exists")
ok('id="pf-vendor-cost-body"' in s, "B2  with a body to render into")
ok("pfRenderVendorCost(p, isNew);" in js, "B3  the modal renders it")
ok("pfLoadVendorCost(p.master_id).then(" in js, "B4  ...and fetches behind it")

# /!\ THE LABELS ARE THE APP'S OWN WORDS for this number. `Cost to Walmart`
# and `Cost to Chewy` are the names of the two tabs built on it; coining a
# third here is the rule 3a defect.
ok("'Cost to Walmart'" in VEN, "B5  /!\\ it reuses the Cost to Walmart name")
ok("'Cost to Chewy'" in VEN, "B6  /!\\ ...and Cost to Chewy")

# /!\ CHEWY'S IS DERIVED THROUGH THE EXISTING HELPER, not re-spelled.
ok("chewyCatalogPricePerEach" in VEN,
   "B7  /!\\ Chewy's per-each comes from the shared helper, so the modal and "
   "the Cost to Chewy tab cannot disagree")
ok("cost / case_qty" not in VEN and "/ p.case_qty" not in VEN,
   "B8  ...and the division is not re-written here")

# /!\ A REASON, NOT A DASH. Every one of these is something Jason can fix, and
# `no-case-qty` is fixable in this very modal.
WHY = const_obj("PF_CHEWY_WHY")
for k in ("no-catalog", "no-cost", "no-case-qty", "unknown-uom"):
    ok("'%s'" % k in WHY, "B9  %s has a sentence" % k)
ok("set it below" in WHY,
   "B10 /!\\ and the fixable one points at the field that fixes it")

# /!\ A BLANK COGS MUST NOT READ AS 100% MARGIN.
ok("cogs != null && v > 0" in VEN,
   "B11 /!\\ the GM line is only drawn where a COGS exists to draw it against")

# The tooltips have to say these are NOT retail - that is the whole trap.
ok("NOT the retail price" in VEN, "B12 the Walmart tip says it is not retail")
ok("vanity" in VEN, "B13 ...and Chewy's reuses the app's own word for it")

LOAD = fn_flat("pfLoadVendorCost")
ok("walmart_cost_per_each" in LOAD, "B14 Walmart's comes from its own table")
ok("loadChewyCatalog" in LOAD, "B15 and Chewy's catalog is loaded first")
# /!\ A missing table must not break the modal - the cell says so instead.
eq("B16 /!\\ both fetches are guarded, so a missing table cannot block the card",
   LOAD.count("catch (e)"), 2)

# ===========================================================================
print("\nC. Classification was a grab-bag; it is split")
# ===========================================================================
titles = [t.strip() for t in
          re.findall(r'<div class="edit-section-title"[^>]*>([^<]{0,60})', s) if t.strip()]
ok("Classification" not in titles,
   "C1  /!\\ the bare `Classification` heading is gone - it described none of "
   "what it held", titles[:6])
ok(any("Classification &amp; flags" in t for t in titles),
   "C2  it names what it still holds")
ok(any("Pricing &amp; COGS" in t for t in titles), "C3  money has its own section")
ok(any("What each vendor pays us" in t for t in titles), "C4  and vendor cost its own")

# /!\ ORDER MATTERS: our prices, then what the vendors pay us, then Amazon's
# measurements. Each is a narrower question than the one before it.
ix = {t: i for i, t in enumerate(titles)}
pri = next(i for t, i in ix.items() if "Pricing" in t)
ven = next(i for t, i in ix.items() if "vendor pays us" in t)
dim = next(i for t, i in ix.items() if "Dimensions" in t)
ok(pri < ven < dim, "C5  Pricing -> vendor cost -> dimensions", (pri, ven, dim))

# ===========================================================================
print("\nD. /!\\ NOT ONE FIELD WAS LOST IN THE MOVE")
# ===========================================================================
# The fields were cut and re-emitted rather than re-typed, because every one
# of these ids is read by name on save - a dropped id saves a null silently.
FIELDS = ["pf-title", "pf-shortname", "pf-brand", "pf-spsku", "pf-shopifysku",
          "pf-asin", "pf-barcode", "pf-chewy", "pf-walmart",
          "pf-msrp", "pf-map-price", "pf-wholesale",
          "pf-cogs", "pf-cogs-dtc", "pf-cogs-chewy", "pf-cogs-eu",
          "pf-cb-landed", "pf-cb-fulfill-amz", "pf-cb-fulfill-chewy",
          "pf-cb-fulfill-dtc", "pf-cb-overhead-dtc", "pf-cb-shipping", "pf-cb-labor",
          "pf-supplier", "pf-case-qty", "pf-bundle", "pf-active", "pf-seasonal",
          "pf-in-house", "pf-image", "pf-cat-display", "pf-subcat-wrap"]
missing = [f for f in FIELDS if s.count('id="%s"' % f) != 1]
eq("D1  every field exists exactly once", missing, [])

# The handlers that ride on them survived the cut too.
for h in ("pfCogsRecalc()", "pfCogsMarkManual(this)", "pfCheckMap()", "toggleBomSection()"):
    ok(h in s, "D2  %s survived" % h)
eq("D3  /!\\ all seven COGS building blocks still recalc",
   s.count('oninput="pfCogsRecalc()"'), 7)
eq("D4  ...and all four channel totals still mark manual",
   s.count('oninput="pfCogsMarkManual(this)"'), 4)
ok('onclick="pfCogsClearManual(' in s, "D5  the auto-reset buttons survived")

# ===========================================================================
print("\nE. /!\\ JS ESCAPES IN HTML RENDER AS LITERAL TEXT")
# ===========================================================================
# The non-ASCII trap in reverse, and caught by looking rather than by a test:
# the section titles are MARKUP, so `🏷` would have shown as that
# text on the card. index.html holds real characters in HTML and escapes only
# inside JS string literals.
bad = re.findall(r'<div class="edit-section-title"[^>]*>\\\\u[0-9a-f]{4}', s)
eq("E1  /!\\ no section title carries a raw \\uXXXX escape", bad, [])
for g, what in [(chr(0x1F3F7), "Classification"), (chr(0x1F4B0), "Pricing"),
                (chr(0x1F4B5), "vendor cost")]:
    ok(g in s, "E2  %s's glyph is a real character" % what)
# /!\ rule #2: the banknote already means "what the 1P retailer pays us" on
# walmart_catalog, and the money bag already means COGS on product_cogs. Same
# concepts, so these are reuse rather than collision - pinned so a later edit
# cannot quietly give either a second meaning.
ok("walmart_catalog:          { icon: '\\ud83d\\udcb5'" in js,
   "E3  /!\\ the banknote still means what the 1P retailer pays us")
ok("product_cogs:             { icon: '\\ud83d\\udcb0'" in js,
   "E4  /!\\ and the money bag still means COGS")

print("\nF. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "F1  both declare a version")
eq("F2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
