#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.77 - a coverage cell marks on its OWN data when it has data.

Jason: "this is STILL not showing correct. i haven't uploaded the new kitty
report yet."

Measured on sku_economics the moment he said it: Doggijuana and Meowijuana
run through 2026-11-02 in both US and CA, Kitty Ka-Zoom only through
2026-10-26 - and all six cells drew a green check, because v11.48 made the
mark the REGION's. That is the SAME defect v11.76 fixed in the upload guard
one release earlier: several of these feeds are uploaded ONE BRAND AT A TIME,
so a region's newest load says nothing about a brand that was not in it.

  * A  /!\ THE DEFECT REPRODUCED - v11.48's cell rule run beside the shipped
       one on the REAL sku_economics rollup.
  * B  the real uploadCoverageHtml on that rollup: the grid he screenshotted,
       cell by cell, with the tooltips.
  * C  /!\ v11.48's GUARANTEE IS INTACT - a brand with no rows in a region
       still inherits the region's mark and can never draw a dash.
  * D  a feed where every brand shares the region's newest load is
       BYTE-IDENTICAL to v11.76.
  * E  static.
"""
import io, os, re, sys, json, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0
DOT = chr(0x00b7)


def ok(cond, label, extra=None):
    global passed, failed
    if cond:
        passed += 1; print("  ok    %s" % label)
    else:
        failed += 1
        print("  FAIL  %s%s" % (label, ("  got: %s" % ascii(extra)) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def nocomment(t):
    # LINE comments only - v11.63: block-stripping index.html eats 824,674
    # characters, because a `/*` inside a string pairs with a distant `*/`.
    return re.sub(r"(?m)^\s*//.*$", "", t)


def _bal(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ""
    while k < n:
        c = js[k]
        if c == "/" and k + 1 < n and js[k + 1] == "/":
            while k < n and js[k] != "\n":
                k += 1
            continue
        if c == "/" and k + 1 < n and js[k + 1] == "*":
            k = js.index("*/", k) + 2
            continue
        if c == "/" and prev in "(,=:[!&|?{};+-*%~^<>":
            k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == "[":
                    while k < n and js[k] != "]":
                        k += 2 if js[k] == "\\" else 1
                if js[k] == "/":
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = "x"
            continue
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = "x"
            continue
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise SystemExit("unbalanced at %d" % i)


def fn(name, kw="function"):
    pat = kw + " " + name + "("
    i = js.index(pat)
    head = js.index("{", i)
    j = i
    while j > 0 and js[j - 1] != "\n":
        j -= 1
    return js[j:head] + _bal(head)


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("{", i)] + _bal(js.index("{", i)) + ";"


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("v11.77 - a cell marks on its own data when it has data")
print("=" * 68)

NC = nocomment(js)

# THE REAL ROLLUP, read off sku_economics on 2026-11-09 - exactly the rows
# uploadCoverageFetch returns for the card in Jason's screenshot. The null
# brand is the "some rows are not mapped to a product" bucket.
ROLL = [
    {"region": "CA", "brand": "Doggijuana",    "latest": "2026-11-02", "fresh": "2026-11-09T14:58:19.026+00:00", "n": 3746},
    {"region": "CA", "brand": "Kitty Ka-Zoom", "latest": "2026-10-26", "fresh": "2026-11-02T14:58:51.17+00:00",  "n": 1666},
    {"region": "CA", "brand": "Meowijuana",    "latest": "2026-11-02", "fresh": "2026-11-09T14:58:19.026+00:00", "n": 6577},
    {"region": "CA", "brand": None,            "latest": "2026-05-25", "fresh": "2026-06-01T14:42:18.209+00:00", "n": 2699},
    {"region": "US", "brand": "Doggijuana",    "latest": "2026-11-02", "fresh": "2026-11-09T14:58:19.026+00:00", "n": 6381},
    {"region": "US", "brand": "Kitty Ka-Zoom", "latest": "2026-10-26", "fresh": "2026-11-02T14:58:51.17+00:00",  "n": 2000},
    {"region": "US", "brand": "Meowijuana",    "latest": "2026-11-02", "fresh": "2026-11-09T14:58:19.026+00:00", "n": 14459},
    {"region": "US", "brand": None,            "latest": "2026-05-25", "fresh": "2026-06-01T14:42:18.209+00:00", "n": 3657},
]

HARNESS = ("globalThis._uploadRegionsHidden = null;\n"
           + const_obj("UH_SOURCES") + "\n"
           + fn("uploadGrain") + "\n"
           + fn("uploadWeekEndOffset") + "\n"
           + fn("uploadPeriodEnd") + "\n"
           + fn("uploadDataThru") + "\n"
           + fn("uploadFreshDays") + "\n"
           + fn("uploadCoverageAxes") + "\n"
           + fn("uploadSqlIdent") + "\n"
           + fn("uploadCoverageSql") + "\n"
           + fn("uploadRegionHidden") + "\n"
           + fn("esc2") + "\n"
           + fn("uploadCoverageFetch", kw="async function") + "\n")

CLOCK = """
// Pinned to the day Jason reported it. LOCAL midnight, because ageOf parses
// its dates as local too.
const _now = new Date('2026-11-09T00:00:00').getTime();
Date.now = () => _now;
"""

FEED = """
const ROLL = """ + json.dumps(ROLL) + r""";
globalThis.getSB = async () => ({
  rpc: async (_f, a) => {
    const m = /from public\.([a-z0-9_]+) t/.exec(a.query);
    return { data: m && m[1] === 'sku_economics' ? ROLL : [], error: null };
  },
});
const texts = (h) => [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(m =>
  [...m[1].matchAll(/<(th|td)[^>]*>([\s\S]*?)<\/\1>/g)].map(c =>
    c[2].replace(/<[^>]*>/g, '').replace(/&#10003;/g, 'OK')
        .replace(/&#8212;/g, '--').trim()));
const tips = (h) => [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].slice(1).map(m =>
  [...m[1].matchAll(/<td[^>]*title="([^"]*)"/g)].map(x => x[1].replace(/&quot;/g, '"')));
const colors = (h) => [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].slice(1).map(m =>
  [...m[1].matchAll(/<td style="[^"]*color:(var\(--[a-z0-9-]+\))/g)].map(x => x[1]));
"""

# ---------------------------------------------------------------------------
print("\nA. /!\\ THE DEFECT REPRODUCED - v11.48's rule beside the shipped one")
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "_v1177_a.js"), HARNESS + CLOCK + FEED + "\n"
             + fn("uploadCoverageHtml") + r"""
(async () => {
  const res = await uploadCoverageFetch('sku_economics', null);
  const h = uploadCoverageHtml('sku_economics', res);

  // ---- the PRE-v11.77 cell rule, exactly as it stood -------------------
  // v11.48: the mark is the REGION's, never the cell's.
  const fresh = uploadFreshDays('sku_economics');
  const ageOf = (d) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(d || ''))) return null;
    return Math.floor((Date.now() - new Date(String(d).slice(0, 10) + 'T00:00:00').getTime()) / 86400000);
  };
  const oldMark = (rk, c) => {
    const d = res.byRegion[rk];
    const up = res.byRegionFresh[rk];
    const end = uploadDataThru('sku_economics', d);
    const age = end ? ageOf(end) : ageOf(up);
    return (!!d && age != null && age <= fresh) ? 'OK' : (d || '--');
  };
  const newMark = (rk, c) => {
    const bd = res.cells[rk + '|' + c];
    const d = (c && bd) ? bd : res.byRegion[rk];
    const up = (c && bd && res.fresh[rk + '|' + c]) ? res.fresh[rk + '|' + c] : res.byRegionFresh[rk];
    const end = uploadDataThru('sku_economics', d);
    const age = end ? ageOf(end) : ageOf(up);
    return (!!d && age != null && age <= fresh) ? 'OK' : (d || '--');
  };
  const grid = (f) => res.regions.map(r => [r].concat(res.brands.map(b => f(r, b))));

  console.log(JSON.stringify({
    regions: res.regions, brands: res.brands,
    cells: res.cells, byRegion: res.byRegion,
    old: grid(oldMark), nu: grid(newMark),
    texts: texts(h), tips: tips(h), colors: colors(h),
    unmapped: /not mapped to a product/.test(h),
  }));
})();
""")

eq("A1  the real rollup carries both regions", A["regions"], ["CA", "US"])
eq("A2  and three brands, the unmapped bucket not among them",
   A["brands"], ["Doggijuana", "Kitty Ka-Zoom", "Meowijuana"])
eq("A3  Kitty Ka-Zoom's own newest week is 2026-10-26",
   A["cells"]["CA|Kitty Ka-Zoom"], "2026-10-26")
eq("A4  while the region's newest is 2026-11-02", A["byRegion"]["CA"], "2026-11-02")

# /!\ Six green checks over a brand that is a week behind. This is the grid
#     in Jason's screenshot.
eq("A5  v11.48 drew a check for EVERY cell, Kitty included",
   A["old"], [["CA", "OK", "OK", "OK"], ["US", "OK", "OK", "OK"]])
eq("A6  the shipped rule dates Kitty by its own rows, in both regions",
   A["nu"], [["CA", "OK", "2026-10-26", "OK"], ["US", "OK", "2026-10-26", "OK"]])
eq("A7  ... and the rendered grid agrees with it", A["texts"][1:], A["nu"])
eq("A8  the header still sits over its own data",
   A["texts"][0], ["", "Doggijuana", "Kitty Ka-Zoom", "Meowijuana"])

# ---------------------------------------------------------------------------
print("\nB. the grid Jason screenshotted, cell by cell")
# ---------------------------------------------------------------------------
eq("B1  Kitty renders in the not-fresh colour, the others green",
   A["colors"][0], ["var(--sp-green)", "var(--orange)", "var(--sp-green)"])
eq("B2  ... and the same in US", A["colors"][1],
   ["var(--sp-green)", "var(--orange)", "var(--sp-green)"])

_kitty = A["tips"][0][1]
ok(("for CA " + DOT + " Kitty Ka-Zoom: 2026-10-26") in _kitty,
   "B3  the tooltip names the BRAND the date belongs to", _kitty)
ok("covers through 2026-10-31 (9 days ago)" in _kitty,
   "B4  ... measured from the week's last day (v11.75)", _kitty)
ok("late after 7 days" in _kitty, "B5  ... against one weekly cycle", _kitty)
ok("no rows here" not in _kitty,
   "B6  ... and it is not described as having no rows, because it has them",
   _kitty)

_doggi = A["tips"][0][0]
ok(("for CA " + DOT + " Doggijuana: 2026-11-02") in _doggi,
   "B7  a current brand is dated by its own rows too", _doggi)
ok("covers through 2026-11-07 (2 days ago)" in _doggi,
   "B8  ... the Saturday the card line above it prints", _doggi)
ok("rows through" not in json.dumps(A["tips"]),
   "B9  the retired trailing clause is gone, not repeating the headline",
   A["tips"])
ok(A["unmapped"],
   "B10 the unmapped-rows note still renders, and is still not a brand column")

# ---------------------------------------------------------------------------
print("\nC. /!\\ v11.48's GUARANTEE IS INTACT")
# ---------------------------------------------------------------------------
# Jason, v11.48: "it's one report for all regions and brands ... that doesn't
# mean there is data missing." He pointed at the UK, where only Meowijuana is
# listed. A brand with NO rows in a region is a fact about the catalogue.
C = run_node(os.path.join(SP, "_v1177_c.js"), HARNESS + CLOCK + """
const ROLL = """ + json.dumps([
    {"region": "EU/UK", "brand": "Meowijuana", "latest": "2026-11-02",
     "fresh": "2026-11-02T20:00:00+00:00", "n": 7},
    {"region": "US", "brand": "Meowijuana", "latest": "2026-11-02",
     "fresh": "2026-11-02T20:00:00+00:00", "n": 90},
    {"region": "US", "brand": "Doggijuana", "latest": "2026-10-20",
     "fresh": "2026-10-20T20:00:00+00:00", "n": 41},
    {"region": "US", "brand": "Kitty Ka-Zoom", "latest": "2026-11-02",
     "fresh": "2026-11-02T20:00:00+00:00", "n": 22},
]) + r""";
globalThis.getSB = async () => ({ rpc: async () => ({ data: ROLL, error: null }) });
const texts = (h) => [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(m =>
  [...m[1].matchAll(/<(th|td)[^>]*>([\s\S]*?)<\/\1>/g)].map(c =>
    c[2].replace(/<[^>]*>/g, '').replace(/&#10003;/g, 'OK')
        .replace(/&#8212;/g, '--').trim()));
const tips = (h) => [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].slice(1).map(m =>
  [...m[1].matchAll(/<td[^>]*title="([^"]*)"/g)].map(x => x[1].replace(/&quot;/g, '"')));
""" + fn("uploadCoverageHtml") + r"""
(async () => {
  const res = await uploadCoverageFetch('fba_inventory_snapshots', null);
  const h = uploadCoverageHtml('fba_inventory_snapshots', res);
  console.log(JSON.stringify({ texts: texts(h), tips: tips(h) }));
})();
""")

eq("C1  EU/UK: the two brands NOT sold there still read as covered",
   C["texts"][1], ["EU/UK", "OK", "OK", "OK"])
ok("--" not in json.dumps(C["texts"]),
   "C2  NO dash anywhere - a brand can never be a coverage gap", C["texts"])
_uk = C["tips"][0]
ok("Doggijuana: no rows here" in _uk[0] and "NOT a missing file" in _uk[0],
   "C3  ... and the tooltip still says why", _uk[0])
ok(("for EU/UK: 2026-11-02") in _uk[0],
   "C4  a cell with no rows is dated by its REGION, and says so", _uk[0])
# And the other half of the same grid, which is the thing that moved.
eq("C5  US: the brand two weeks behind is dated by its own rows",
   C["texts"][2], ["US", "2026-10-20", "OK", "OK"])

# ---------------------------------------------------------------------------
print("\nD. a region-wide feed does not move at all")
# ---------------------------------------------------------------------------
# The only form in which "nothing changed for a feed that really is one file
# per region" is checkable rather than read off a diff.
D = run_node(os.path.join(SP, "_v1177_d.js"), HARNESS + CLOCK + """
const ROLL = """ + json.dumps([
    {"region": "US", "brand": b, "latest": "2026-11-02",
     "fresh": "2026-11-02T20:00:00+00:00", "n": 10}
    for b in ("Doggijuana", "Kitty Ka-Zoom", "Meowijuana")
] + [
    {"region": "CA", "brand": b, "latest": "2026-10-05",
     "fresh": "2026-10-05T20:00:00+00:00", "n": 10}
    for b in ("Doggijuana", "Kitty Ka-Zoom", "Meowijuana")
]) + r""";
globalThis.getSB = async () => ({ rpc: async () => ({ data: ROLL, error: null }) });
const texts = (h) => [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(m =>
  [...m[1].matchAll(/<(th|td)[^>]*>([\s\S]*?)<\/\1>/g)].map(c =>
    c[2].replace(/<[^>]*>/g, '').replace(/&#10003;/g, 'OK')
        .replace(/&#8212;/g, '--').trim()));
""" + fn("uploadCoverageHtml") + r"""
(async () => {
  const res = await uploadCoverageFetch('fba_inventory_snapshots', null);
  // The retired rule, over the same rollup.
  const fresh = uploadFreshDays('fba_inventory_snapshots');
  const ageOf = (d) => /^\d{4}-\d{2}-\d{2}$/.test(String(d || ''))
    ? Math.floor((Date.now() - new Date(String(d) + 'T00:00:00').getTime()) / 86400000) : null;
  const oldGrid = res.regions.map(r => [r].concat(res.brands.map(() => {
    const d = res.byRegion[r];
    const end = uploadDataThru('fba_inventory_snapshots', d);
    const age = end ? ageOf(end) : ageOf(res.byRegionFresh[r]);
    return (!!d && age != null && age <= fresh) ? 'OK' : (d || '--');
  })));
  console.log(JSON.stringify({
    old: oldGrid, nu: texts(uploadCoverageHtml('fba_inventory_snapshots', res)).slice(1) }));
})();
""")

eq("D1  every brand shares the region's load, so the grids are identical",
   D["nu"], D["old"])
eq("D2  ... a current region all green", D["nu"][1], ["US", "OK", "OK", "OK"])
eq("D3  ... and a stale one all dated, for every brand alike",
   D["nu"][0], ["CA", "2026-10-05", "2026-10-05", "2026-10-05"])

# ---------------------------------------------------------------------------
print("\nE. static")
# ---------------------------------------------------------------------------
_h = nocomment(fn("uploadCoverageHtml"))
ok("const d = (c && bd) ? bd : res.byRegion[rk];" in _h,
   "E1  the mark is the cell's own, falling back to the region rollup")
ok("const d = res.byRegion[rk];" not in _h,
   "E2  the retired rule is GONE from live code, not left beside it")
ok("THE MARK IS THE REGION'S, NOT THE CELL'S" in js,
   "E3  ... and v11.48's heading survives in a comment, so grepping it lands "
   "on why it changed")
ok("res.fresh[k]" in _h,
   "E4  the per-cell upload timestamp is read, not just the region's")
eq("E5  res.cells is still resolved exactly once", _h.count("res.cells["), 1)
ok("uploadDataThru(table, d)" in _h,
   "E6  and the period end is still resolved from whichever date won")
ok("no rows here" in _h and "NOT a missing file" in _h,
   "E7  v11.48's sentence is still what a cell with no rows says")
ok(_h.count("rows through") == 0,
   "E8  the clause that repeated the date is gone", _h)

# v11.63: the chip and CLAUDE.md's current-version line must AGREE.
doc = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", newline="").read()
chip = re.findall(r">v(11\.\d+) " + DOT + r" ([\d-]+)<", s)
eq("E9  exactly one version chip", len(chip), 1)
docv = re.search(r"current version \*\*v(11\.\d+)\*\*", doc)
eq("E10 the chip agrees with CLAUDE.md", chip[0][0], docv.group(1) if docv else None)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
