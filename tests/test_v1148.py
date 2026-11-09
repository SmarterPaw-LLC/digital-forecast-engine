#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.48 - a brand with no rows is not a missing upload.

Jason, on the Amazon Ads card: "this still doesn't make sense - it's one
report for all regions and brands. i think you aren't seeing any campaigns
for certain brands, but that doesn't mean there is data missing."

And on FBA Inventory EU/UK, whose own subtitle reads "One upload covers GB +
DE/FR/IT/ES/NL/SE/PL/BE/IE": "only meow products are available in the UK."

The fixtures below are the REAL rollups the live database returned for the
SQL the shipped builder produces, so they cannot drift from the query.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1148_")
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
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


def nocomment(t):
    return re.sub(r"(?m)^\s*//.*$", "", t)


def fn(name):
    for pre in ("async function ", "function "):
        i = js.find(pre + name + "(")
        if i >= 0:
            break
    if i < 0:
        raise SystemExit("missing %s" % name)
    d, started, k = 0, False, js.index("{", i)
    while k < len(js):
        if js[k] == "{":
            d += 1; started = True
        elif js[k] == "}":
            d -= 1
            if started and d == 0:
                return js[i:k + 1]
        k += 1
    raise SystemExit("unbalanced %s" % name)


REG = js[js.index("const UH_SOURCES = {"):]
REG = REG[:REG.index("\n};") + 3]
HARNESS = """
globalThis.UH_SOURCES = """ + REG[len("const UH_SOURCES = "):] + """
globalThis.esc2 = (v) => String(v == null ? '' : v)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
globalThis._uploadRegionsHidden = null;
"""
DEFS = "\n".join(fn(n) for n in (
    # v11.75 - sliced, not stubbed, so D1 proves the SHIPPED staleness
    # rule still bites rather than a local copy of it.
    "uploadGrain", "uploadWeekEndOffset", "uploadPeriodEnd", "uploadDataThru",
    "uploadCoverageAxes", "uploadSqlIdent", "uploadCoverageSql", "uploadFreshDays",
    "uploadRegionHidden", "uploadCoverageHtml", "uploadCoverageFetch"))


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


# The REAL fba_inventory_snapshots rollup, 2026-11-03. Note EU/UK: ONE brand.
FBA = [
    {"region": "CA", "brand": "Doggijuana", "latest": "2026-11-02",
     "fresh": "2026-11-02T23:25:29+00:00", "n": 406},
    {"region": "CA", "brand": "Kitty Ka-Zoom", "latest": "2026-11-03",
     "fresh": "2026-11-03T17:29:35+00:00", "n": 378},
    {"region": "CA", "brand": "Meowijuana", "latest": "2026-11-03",
     "fresh": "2026-11-03T17:28:49+00:00", "n": 454},
    {"region": "EU/UK", "brand": "Meowijuana", "latest": "2026-11-02",
     "fresh": "2026-11-02T23:25:35+00:00", "n": 47},
    {"region": "US", "brand": "Doggijuana", "latest": "2026-10-20",
     "fresh": "2026-10-20T16:44:32+00:00", "n": 635},
    {"region": "US", "brand": "Kitty Ka-Zoom", "latest": "2026-11-02",
     "fresh": "2026-11-02T15:00:13+00:00", "n": 380},
    {"region": "US", "brand": "Meowijuana", "latest": "2026-11-02",
     "fresh": "2026-11-02T14:55:51+00:00", "n": 1577},
]
# A region whose ONLY load is long stale - the case that must still go orange.
STALE = [
    {"region": "US", "brand": "Meowijuana", "latest": "2026-01-05",
     "fresh": "2026-01-05T10:00:00+00:00", "n": 10},
    {"region": "US", "brand": "Doggijuana", "latest": "2026-01-05",
     "fresh": "2026-01-05T10:00:00+00:00", "n": 10},
]

print("\n" + "=" * 62)
print("  v11.48  a brand with no rows is not a missing upload")
print("=" * 62)

R = run_node(os.path.join(SP, "r.js"), HARNESS + DEFS + """
// v11.75 - PIN THE CLOCK, for the same reason test_v1147 does: A1's fixture
// carries real dates, so "covered" was true only until 10 days after them.
Date.now = () => new Date('2026-11-04T12:00:00').getTime();
const FBA = """ + json.dumps(FBA) + """;
const STALE = """ + json.dumps(STALE) + r""";
globalThis.getSB = async () => ({
  rpc: async (_f, a) => {
    const t = /from public\.([a-z0-9_]+) t/.exec(a.query)[1];
    return { data: t === 'sku_economics' ? STALE : FBA, error: null };
  },
});
const texts = (h) => [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(m =>
  [...m[1].matchAll(/<(th|td)[^>]*>([\s\S]*?)<\/\1>/g)].map(c =>
    c[2].replace(/<[^>]*>/g, '').replace(/&#10003;/g, 'OK')
        .replace(/&#8212;/g, '--').trim()));
const tips = (h) => [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].slice(1).map(m =>
  [...m[1].matchAll(/<td[^>]*title="([^"]*)"/g)].map(x => x[1].replace(/&quot;/g, '"')));
(async () => {
  const out = {};
  const res = await uploadCoverageFetch('fba_inventory_snapshots', null);
  out.byRegion = res.byRegion;
  out.byRegionFresh = res.byRegionFresh;
  out.cells = res.cells;
  const h = uploadCoverageHtml('fba_inventory_snapshots', res);
  out.texts = texts(h);
  out.tips = tips(h);
  const sres = await uploadCoverageFetch('sku_economics', null);
  out.staleTexts = texts(uploadCoverageHtml('sku_economics', sres));
  console.log(JSON.stringify(out));
})();
""")

# ---------------------------------------------------------------------------
# A. THE DEFECT, on the exact card Jason screenshotted.
# ---------------------------------------------------------------------------
# v11.47 drew  EU/UK | -- | -- | OK |.  Only Meowijuana is listed in the UK,
# so the other two were a FACT ABOUT THE CATALOGUE rendered as a missing file.
eq("A1 EU/UK is covered for every brand, because ONE file covers them all",
   R["texts"][2], ["EU/UK", "OK", "OK", "OK"])
eq("A1b CA likewise", R["texts"][1], ["CA", "OK", "OK", "OK"])
# v11.77 RE-POINTED, and it was right to go red. This pinned US Doggijuana
# as OK although its rows stop on 2026-10-20, two weeks behind the region.
# Jason, on exactly that shape one release later: "this is STILL not showing
# correct. i haven't uploaded the new kitty report yet." Several of these
# feeds are uploaded ONE BRAND AT A TIME, so a region's newest load says
# nothing about a brand that was not in it. A cell with rows of its own marks
# on those now. test_v1177 owns the rule.
eq("A1c US Doggijuana marks on ITS OWN rows, which stop on 2026-10-20",
   R["texts"][3], ["US", "2026-10-20", "OK", "OK"])
# /!\ THE GUARANTEE v11.48 EXISTS FOR IS INTACT: a brand with no rows in a
# region still inherits the region's mark, so it can never read as a missing
# file. A1, A1b and A2 are unchanged.
ok("--" not in json.dumps(R["texts"]),
   "A2 NO dash anywhere - a brand can never be a coverage gap", R["texts"])

# ---------------------------------------------------------------------------
# B. The per-brand fact is REPORTED, not discarded.
# ---------------------------------------------------------------------------
_eu = R["tips"][1]
ok("no rows here" in _eu[0] and "NOT a missing file" in _eu[0],
   "B1 the EU/UK Doggijuana tooltip says it is activity, not coverage", _eu[0])
ok("Kitty Ka-Zoom: no rows here" in _eu[1], "B1b and Kitty Ka-Zoom the same")
# v11.77 RE-POINTED. The per-brand date used to be a trailing clause beside
# the region's, because the region's was the headline. The cell's own date IS
# the headline now, so repeating it would be the same fact twice.
ok("for EU/UK " + chr(0x00b7) + " Meowijuana: 2026-11-02" in _eu[2],
   "B1c while the brand that IS sold there is dated on its own rows", _eu[2])

_us = R["tips"][2]
ok("for US " + chr(0x00b7) + " Doggijuana: 2026-10-20" in _us[0],
   "B2 a brand whose rows stopped early is dated by them", _us[0])
ok("2026-11-02" not in _us[0],
   "B2b and the region's newer date is NOT what that cell reports", _us[0])
ok("rows through" not in json.dumps(R["tips"]),
   "B2c the retired trailing clause is gone, not left repeating the headline",
   R["tips"])

# ---------------------------------------------------------------------------
# C. The mark comes from the region rollup.
# ---------------------------------------------------------------------------
eq("C1 the region rollup takes the NEWEST load in that region",
   R["byRegion"]["CA"], "2026-11-03")
eq("C1b EU/UK has only one", R["byRegion"]["EU/UK"], "2026-11-02")
eq("C1c and US is 11-02, not Doggijuana's 10-20",
   R["byRegion"]["US"], "2026-11-02")
eq("C2 the per-(region, brand) map is still built, for the tooltip",
   R["cells"]["US|Doggijuana"], "2026-10-20")

_h = nocomment(fn("uploadCoverageHtml"))
# v11.77 RE-POINTED: the region rollup is the FALLBACK now, not the rule.
ok("const d = (c && bd) ? bd : res.byRegion[rk];" in _h,
   "C3 the mark is the cell's own, falling back to the region rollup")
eq("C3b and res.cells is read exactly once in the renderer",
   _h.count("res.cells["), 1)
ok("const bd = res.cells[k];" in _h,
   "C3c under a name that only reaches the tooltip")

# ---------------------------------------------------------------------------
# D. Staleness still bites. Removing the brand dash must not remove the one
#    mark the grid exists to show.
# ---------------------------------------------------------------------------
eq("D1 a region whose only load is ancient still shows its DATE, not a tick",
   R["staleTexts"][1], ["US", "2026-01-05", "2026-01-05"])
ok("OK" not in json.dumps(R["staleTexts"]),
   "D1b nothing in a stale grid reads as fresh", R["staleTexts"])

# ---------------------------------------------------------------------------
# E. The merge rule - every change here re-audits it (the standing rule).
# ---------------------------------------------------------------------------
_m = nocomment(fn("renderUploadCoverage"))
for k in ("merged.byRegion[k]", "merged.byRegionFresh[k]"):
    ok(k in _m, "E1 the multi-table merge carries %s" % k)
ok("byRegion: {}" in _m and "byRegionFresh: {}" in _m,
   "E1b and declares them, so a merge cannot read undefined")
_f = nocomment(fn("uploadCoverageFetch"))
for k in ("out.byRegion[r]", "out.byRegionFresh[r]"):
    ok(k in _f, "E2 the fetch accumulates %s in the same pass" % k)

# ---------------------------------------------------------------------------
# F. The claim this release rests on, asserted against the MARKUP.
# ---------------------------------------------------------------------------
# "Nothing in this app is uploaded per brand." If an uploader ever grows a
# brand scope, that is the day this design needs revisiting - so it fails here
# rather than silently flattening a real gap.
masked = re.sub(r"<!--[\s\S]*?-->", lambda m: " " * len(m.group(0)), s)
dz = js[js.index("const DZ_RECENT_SOURCES"):]
dz = dz[:dz.index("\n};")]
cards = re.findall(r"^\s*'([a-z0-9-]+)':", dz, re.M)


def card_body(did):
    m = re.search(r'id="%s"' % re.escape(did), s)
    if not m:
        return ""
    st = s.rindex("<div", 0, m.start())
    d, j = 0, st
    while True:
        o, c = masked.find("<div", j), masked.find("</div>", j)
        if c == -1:
            break
        if o != -1 and o < c:
            d += 1; j = o + 4
        else:
            d -= 1; j = c + 6
            if d == 0:
                break
    return s[st:j]


brand_scoped = [d for d in cards
                if re.findall(r'<select[^>]*id="[a-z0-9-]*brand[a-z0-9-]*"',
                              card_body(d), re.I)]
ok(not brand_scoped,
   "F1 no upload card makes the operator pick a BRAND", brand_scoped)
ok(len(cards) >= 20, "F1b over a real set of cards", len(cards))

eq("F2 version chip", len(re.findall(r">v11\.\d+ · [\d-]+<", s)), 1)

print("\n" + "=" * 62)
print("  v11.48  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
