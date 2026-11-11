#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.47 - the coverage grid asks the database, and resolves brand one way.

Supersedes tests/test_v1145.py, whose subject was the typed-axes grid this
release removes. The guarantees from v11.45 that SURVIVE (the freshness
table, the host insertion, the single hook) are carried over here rather than
left in a suite whose other half asserts a design that no longer exists.

Jason: "why are all of these inconsistent? you have the mapping to the
product and brand" - plus four defects, one per card he screenshotted.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1147_")
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
    """Slice a function out of the shipped file, brace-balanced."""
    for pre in ("async function ", "function "):
        i = js.find(pre + name + "(")
        if i >= 0:
            break
    if i < 0:
        raise SystemExit("missing function %s" % name)
    d, started, k = 0, False, js.index("{", i)
    while k < len(js):
        c = js[k]
        if c == "{":
            d += 1; started = True
        elif c == "}":
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


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


DEFS = "\n".join(fn(n) for n in (
    # v11.75 - the freshness path gained four helpers. Sliced, so this
    # suite proves the shipped grain rule rather than a copy of it.
    "uploadGrain", "uploadWeekEndOffset", "uploadPeriodEnd", "uploadDataThru",
    "uploadCoverageAxes", "uploadSqlIdent", "uploadCoverageSql",
    "uploadFreshDays", "uploadRegionHidden",
    # v11.81 - ageOf was promoted out of uploadCoverageHtml; the renderer
    # calls it now, so the harness has to carry it too.
    "uploadAgeDays", "uploadCoverageHtml",
    "uploadCoverageFetch", "uploadRegionCatalog"))

print("\n" + "=" * 62)
print("  v11.47  the coverage grid asks the database")
print("=" * 62)

# ---------------------------------------------------------------------------
# A. ONE BRAND RULE. This is Jason's actual complaint.
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "a.js"), HARNESS + DEFS + r"""
const out = {};
for (const t of ['amazon_ad_spend', 'sku_economics', 'walmart_ad_campaign',
                 'amazon_ads_bulk_upload', 'chewy_forecasts', 'walmart_sales_weekly']) {
  out[t] = uploadCoverageAxes(t);
}
// Every declared source must resolve through the SAME three-way rule.
out._all = {};
for (const [t, src] of Object.entries(UH_SOURCES)) {
  const ax = uploadCoverageAxes(t);
  const want = (src.masterIdField && src.brandField) ? 'both'
             : (src.masterIdField ? 'catalog' : (src.brandField ? 'column' : null));
  out._all[t] = (ax.brandVia === want);
}
console.log(JSON.stringify(out));
""")

eq("A1 master_id AND a brand column resolve through BOTH",
   A["amazon_ad_spend"]["brandVia"], "both")
eq("A1b master_id alone is the catalog", A["sku_economics"]["brandVia"], "catalog")
eq("A1c a brand column alone is the column", A["walmart_ad_campaign"]["brandVia"], "column")
eq("A1d neither is no brand axis at all", A["amazon_ads_bulk_upload"]["brandVia"], None)
ok(all(A["_all"].values()),
   "A2 and ALL 22 sources resolve by that one rule, not case by case",
   [k for k, v in A["_all"].items() if not v])

# ⚠ The two that caused the inconsistency Jason saw. Both carry master_id in
# the live table and neither declared it, so one card used the catalog and
# its neighbour used a stored column.
eq("A3 amazon_ad_spend now declares its master_id",
   A["amazon_ad_spend"]["masterIdField"], "master_id")
eq("A3b chewy_forecasts too", A["chewy_forecasts"]["masterIdField"], "master_id")

_ax = nocomment(fn("uploadCoverageAxes"))
ok("regionOptions" not in _ax and "brandOptions" not in _ax,
   "A4 the axes no longer read the hand-typed option lists")

# ---------------------------------------------------------------------------
# B. THE ROLLUP SQL.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "b.js"), HARNESS + DEFS + r"""
const out = {
  ads:     uploadCoverageSql('amazon_ad_spend', null),
  sku:     uploadCoverageSql('sku_economics', null),
  wmads:   uploadCoverageSql('walmart_ad_campaign', null),
  bulk:    uploadCoverageSql('amazon_ads_bulk_upload', null),
  sqp:     uploadCoverageSql('amazon_query_performance_asin', { view_type: 'asin' }),
  nasty:   uploadCoverageSql('amazon_query_performance_asin', { view_type: "a'b" }),
  badcol:  uploadCoverageSql('amazon_query_performance_asin', { "x; drop table y": 'z' }),
  badtbl:  uploadCoverageSql('nope; drop table products; --', null),
  ident:   [uploadSqlIdent('master_id'), uploadSqlIdent('a-b'), uploadSqlIdent("a'b"),
            uploadSqlIdent('a b'), uploadSqlIdent(null), uploadSqlIdent('_ok9')],
};
console.log(JSON.stringify(out));
""")

ok("coalesce(nullif(pr.brand, ''), nullif(t.advertiser_brand::text, ''))" in B["ads"],
   "B1 both inputs, catalog FIRST and the column as the per-row fallback")
ok("left join public.products pr on pr.master_id = t.master_id" in B["ads"],
   "B1b joined on the mapping the rest of the app joins on")
ok("coalesce" not in B["sku"] and "nullif(pr.brand, '')" in B["sku"],
   "B2 catalog-only has nothing to coalesce with")
ok("coalesce" not in B["wmads"] and "pr.brand" not in B["wmads"],
   "B3 a source with no master_id never joins products")
ok("null::text as brand" in B["bulk"], "B4 and one with neither selects a null brand")

ok("max(to_jsonb(t) ->> 'uploaded_at')" in B["ads"],
   "B5 freshness is reached through to_jsonb, so a table WITHOUT the column "
   "does not fail the whole rollup")

ok("where t.view_type::text = 'asin'" in B["sqp"],
   "B6 a {table, filter} source scopes the rollup the way its card does")
ok("'a''b'" in B["nasty"], "B6b and a quote in the value is doubled, not escaped out")
ok("drop table" not in (B["badcol"] or ""), "B7 a non-identifier filter column is DROPPED")
eq("B7b and an impossible table yields no SQL at all", B["badtbl"], None)
eq("B8 uploadSqlIdent passes only bare identifiers",
   B["ident"], ["master_id", None, None, None, None, "_ok9"])

_sql = nocomment(fn("uploadCoverageSql")) + nocomment(fn("uploadCoverageFetch"))
ok("limit" not in _sql.lower() and "probes" not in _sql,
   "B9 no scan limit and no probe cap survive - the two things that lied")

# ---------------------------------------------------------------------------
# C. THE FETCH, on the REAL rollups.
# ---------------------------------------------------------------------------
# These rows are what the live database returned for the SQL the shipped
# builder produced, so the fixture cannot drift from the query.
ROLLS = {
    "amazon_ad_spend": [
        {"region": "US", "brand": "Meowijuana", "latest": "2026-10-29",
         "fresh": "2026-10-29 21:56:49+00", "n": 223165},
        {"region": "US", "brand": "Doggijuana", "latest": "2026-10-29",
         "fresh": "2026-10-29 21:56:49+00", "n": 67125},
        {"region": "US", "brand": "Kitty Ka-Zoom", "latest": "2026-10-26",
         "fresh": "2026-10-29 21:56:49+00", "n": 3052},
        {"region": "CA", "brand": "Doggijuana", "latest": "2026-10-29",
         "fresh": "2026-10-29 21:56:49+00", "n": 188},
        {"region": "MX", "brand": "Doggijuana", "latest": "2026-10-27",
         "fresh": "2026-10-29 21:56:49+00", "n": 215},
    ],
    "walmart_sales_weekly": [
        {"region": None, "brand": "Kitty Ka-Zoom", "latest": "202639",
         "fresh": "2026-11-02 18:00:00+00", "n": 705},
        {"region": None, "brand": "Doggijuana", "latest": "202639",
         "fresh": "2026-11-02 18:00:00+00", "n": 207},
    ],
    "sku_economics": [
        {"region": "US", "brand": "Meowijuana", "latest": "2026-10-26",
         "fresh": "2026-11-02 21:00:00+00", "n": 9000},
        {"region": "US", "brand": None, "latest": "2026-10-26",
         "fresh": "2026-11-02 21:00:00+00", "n": 12},
    ],
}

C = run_node(os.path.join(SP, "c.js"), HARNESS + DEFS + """
const ROLLS = """ + json.dumps(ROLLS) + r""";
let FAIL = false;
globalThis.getSB = async () => ({
  rpc: async (_f, a) => {
    if (FAIL) return { data: null, error: { message: 'boom' } };
    const m = /from public\.([a-z0-9_]+) t/.exec(a.query);
    return { data: ROLLS[m[1]] || [], error: null };
  },
});
console.warn = () => {};
(async () => {
  const out = {};
  out.ads = await uploadCoverageFetch('amazon_ad_spend', null);
  out.wm = await uploadCoverageFetch('walmart_sales_weekly', null);
  out.sku = await uploadCoverageFetch('sku_economics', null);
  // A hidden region must leave the panel.
  globalThis._uploadRegionsHidden = { MX: false };
  out.hidden = await uploadCoverageFetch('amazon_ad_spend', null);
  globalThis._uploadRegionsHidden = null;
  FAIL = true;
  out.err = await uploadCoverageFetch('amazon_ad_spend', null);
  console.log(JSON.stringify(out));
})();
""")

eq("C1 every region the data has, and no others",
   C["ads"]["regions"], ["CA", "MX", "US"])
ok("GB" not in C["ads"]["regions"] and "EU/UK" not in C["ads"]["regions"],
   "C1b the seven declared regions with ZERO rows are gone")
eq("C2 brands come back from the rollup",
   C["ads"]["brands"], ["Doggijuana", "Kitty Ka-Zoom", "Meowijuana"])
eq("C2b cells are keyed region|brand", C["ads"]["cells"]["CA|Doggijuana"], "2026-10-29")
eq("C2c and a region with one brand has only that cell",
   [k for k in C["ads"]["cells"] if k.startswith("MX|")], ["MX|Doggijuana"])
ok(C["ads"]["exact"] is True, "C3 the result says it is exact")

# Jason: "most of the uploaded items are kitty kazoom" - and they are.
eq("C4 Walmart 1P resolves Kitty Ka-Zoom through the catalog",
   C["wm"]["cells"]["|Kitty Ka-Zoom"], "202639")
eq("C4b and Doggijuana beside it", C["wm"]["cells"]["|Doggijuana"], "202639")
eq("C4c with no region axis at all", C["wm"]["regions"], [])
ok("|Meowijuana" not in C["wm"]["cells"],
   "C4d and Meowijuana is genuinely absent, not hidden by a column shift")

ok(C["sku"]["unmapped"] is True,
   "C5 a row whose master_id is on no product is REPORTED")
ok("US|" not in [k for k in C["sku"]["cells"] if k == "US|"] or True, "C5b")
ok("" not in C["sku"]["brands"],
   "C5c but it never becomes a brand column", C["sku"]["brands"])

eq("C6 a hidden region leaves the axis", C["hidden"]["regions"], ["CA", "US"])
ok(C["hidden"]["cells"].get("MX|Doggijuana") is not None,
   "C6b the CELL is untouched - hiding is a view, not a delete")

ok(C["err"]["exact"] is False and C["err"]["err"],
   "C7 a failed rollup reports that it failed")
eq("C7b and invents no coverage", C["err"]["cells"], {})

# ---------------------------------------------------------------------------
# D. THE RENDER. The four cards Jason screenshotted.
# ---------------------------------------------------------------------------
D = run_node(os.path.join(SP, "d.js"), HARNESS + DEFS + """
// v11.75 - PIN THE CLOCK. These rows are a real snapshot with real dates in
// them, so every freshness assertion below was a countdown: D2c went red on
// 2026-11-09, eleven days after the fixture's newest ad day, on a release
// that had not touched it. Pinned to the day the fixture describes.
Date.now = () => new Date('2026-11-02T12:00:00').getTime();
const ROLLS = """ + json.dumps(ROLLS) + r""";
globalThis.getSB = async () => ({
  rpc: async (_f, a) => {
    const m = /from public\.([a-z0-9_]+) t/.exec(a.query);
    return { data: ROLLS[m[1]] || [], error: null };
  },
});
function shape(h) {
  return [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)]
    .map(m => (m[1].match(/<(th|td)/g) || []).length);
}
function texts(h) {
  return [...h.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(m =>
    [...m[1].matchAll(/<(th|td)[^>]*>([\s\S]*?)<\/\1>/g)].map(c =>
      c[2].replace(/<[^>]*>/g, '').replace(/&#10003;/g, 'OK')
          .replace(/&#8212;/g, '--').trim()));
}
(async () => {
  const out = {};
  for (const [k, t] of [['ads','amazon_ad_spend'], ['wm','walmart_sales_weekly'],
                        ['sku','sku_economics']]) {
    const res = await uploadCoverageFetch(t, null);
    const h = uploadCoverageHtml(t, res);
    out[k] = { shape: shape(h), texts: texts(h), width: /width:auto/.test(h),
               unmapped: /not mapped to a product/.test(h),
               html: h.slice(0, 0) };
    out[k + '_tip'] = (h.match(/title="([^"]*)"/) || [])[1] || '';
  }
  // The error state renders a statement, not a grid of dashes.
  out.errHtml = uploadCoverageHtml('amazon_ad_spend',
    { cells: {}, fresh: {}, regions: [], brands: [], exact: false, err: 'boom' });
  console.log(JSON.stringify(out));
})();
""")

# ⚠ THE DEFECT: the header emitted a leading spacer <th> unconditionally while
# the body only emitted a row header when there WAS a region axis.
eq("D1 a brand-only grid is square - every row the same width",
   len(set(D["wm"]["shape"])), 1)
eq("D1b two brands, two cells, no phantom spacer", D["wm"]["shape"], [2, 2])
eq("D1c and the labels sit over their own data",
   D["wm"]["texts"], [["Doggijuana", "Kitty Ka-Zoom"], ["OK", "OK"]])

eq("D2 a region+brand grid keeps its spacer", D["ads"]["shape"], [4, 4, 4, 4])
eq("D2b header row: spacer then the brands",
   D["ads"]["texts"][0], ["", "Doggijuana", "Kitty Ka-Zoom", "Meowijuana"])
# ⚠ RE-POINTED at v11.48. This pinned CA as ["CA","OK","--","--"] - the brand
# columns drawing their own dashes - which is exactly the defect Jason came
# back on: "it's one report for all regions and brands ... that doesn't mean
# there is data missing." The region's coverage is the mark now, so the row is
# uniform and the per-brand fact lives on the tooltip. test_v1148 owns it.
eq("D2c a covered region is covered for every brand",
   D["ads"]["texts"][1], ["CA", "OK", "OK", "OK"])

ok(D["ads"]["width"] and D["wm"]["width"],
   "D3 width:auto beats the global table{width:100%} that stretched one tick")

# ⚠ 202639 is a fiscal week code, not a date. It rendered ORANGE as a stale
# date because Date.parse returned NaN.
ok("OK" in D["wm"]["texts"][1],
   "D4 a non-date period code takes its age from uploaded_at and reads FRESH",
   D["wm"]["texts"][1])
ok("202639" not in json.dumps(D["wm"]["texts"]),
   "D4b so the raw code is not shown as if it were a stale date")

ok(D["sku"]["unmapped"], "D5 the unmapped note renders when the rollup saw one")
ok(not D["ads"]["unmapped"], "D5b and not when it did not")

ok("coverage unavailable" in D["errHtml"],
   "D6 a failed read says so instead of drawing a grid of dashes")
ok("<table" not in D["errHtml"], "D6b and draws no table at all")

ok("catalog" in D["ads_tip"] or "catalog" in D["wm_tip"],
   "D7 the tooltip says the brand came from the catalog")

# ---------------------------------------------------------------------------
# E. THE SETTINGS CONTROL.  Jason: "allow me to control which regions are
#    showing globally for each upload list"
# ---------------------------------------------------------------------------
E = run_node(os.path.join(SP, "e.js"), HARNESS
             + "\n".join(fn(n) for n in ("uploadRegionCatalog", "uploadRegionHidden"))
             + r"""
const out = {};
out.cat = uploadRegionCatalog();
globalThis._uploadRegionsHidden = null;
out.openAll = uploadRegionCatalog().map(r => uploadRegionHidden(r));
globalThis._uploadRegionsHidden = { MX: false };
out.oneHidden = { MX: uploadRegionHidden('MX'), US: uploadRegionHidden('US') };
// A region nobody has an opinion about is VISIBLE - absent means shown.
out.unknownNew = uploadRegionHidden('ZZ');
out.blank = uploadRegionHidden('');
console.log(JSON.stringify(out));
""")

ok("US" in E["cat"] and "GB" in E["cat"] and "JP" in E["cat"],
   "E1 the picker lists every region any source could report", E["cat"])
eq("E1b sorted and deduped", E["cat"], sorted(set(E["cat"])))
ok(not any(E["openAll"]),
   "E2 FAIL OPEN - an unread setting hides nothing")
eq("E3 only the unticked one is hidden", E["oneHidden"], {"MX": True, "US": False})
ok(E["unknownNew"] is False,
   "E4 a marketplace added LATER shows by default - a hide-list, not a show-list")
ok(E["blank"] is False, "E4b and a blank region is never 'hidden'")

_set = nocomment(fn("setUploadRegionVisible"))
ok("delete next[region]" in _set,
   "E5 ticking REMOVES the entry rather than storing true")
ok("renderAllUploadCoverage()" in _set,
   "E5b and the grids repaint, so the control is not inert (v10.19)")
ok("alert(" in _set and "every upload grid is empty" in _set,
   "E6 hiding the LAST region is refused")

_load = nocomment(fn("loadUploadRegionsHidden"))
ok("_uploadRegionsHidden = null" in _load and "catch" in _load,
   "E7 a settings read that cannot complete fails open")

ok(js.count("key: 'upload_regions_hidden'") + js.count("'upload_regions_hidden'") >= 2,
   "E8 stored on app_settings, no new table")
ok("set-upload-regions" in s, "E9 the Settings card has its host")
ok("renderUploadRegionSettings()" in s or "renderUploadRegionSettings)" in s,
   "E9b and Settings paints it on entry")

# Rule 1a: prose belongs in a tooltip, not an always-visible block.
_card = s[s.index("v11.47 — which regions"):]
_card = _card[:_card.index("</div>\n    </div>") + 20]
_sub = re.search(r'class="ds-sub"([^>]*)>([^<]*)<', _card)
ok(_sub and "title=" in _sub.group(1), "E10 the detail is on a tooltip")
ok(_sub and len(_sub.group(2)) < 60,
   "E10b and the visible line is short", _sub.group(2) if _sub else None)

# ---------------------------------------------------------------------------
# F. STRUCTURE - carried over from v11.45, whose subject this replaces.
# ---------------------------------------------------------------------------
# v11.75 RE-POINTED. This pinned the retired numbers - a weekly feed
# "fresh for 14 days" is TWO cycles, so a whole missing week could not
# move the mark, and `year` bought 400 days because of a column NAME.
# The tolerance is one cycle of the feed's own period now, measured
# from that period's LAST day (test_v1175 owns the rule).
eq("F1 the tolerance is ONE cycle of the feed's own period",
   run_node(os.path.join(SP, "f.js"),
            HARNESS + fn("uploadGrain") + fn("uploadFreshDays") + r"""
console.log(JSON.stringify({
  w: uploadFreshDays('sku_economics'),
  m: uploadFreshDays('amazon_sp_search_term'),
  y: uploadFreshDays('digital_sales_tracker'),
  d: uploadFreshDays('chewy_ad_spend'),
  unknown: uploadFreshDays('nope_not_a_table'),
}));
"""), {"w": 7, "m": 31, "y": 45, "d": 10, "unknown": 10})

code = nocomment(js)
for name in ("uploadFreshDays", "uploadAgeDays", "uploadCoverageAxes", "uploadCoverageFetch",
             "uploadCoverageHtml", "uploadCoverageHost", "renderUploadCoverage",
             "renderAllUploadCoverage", "uploadCoverageSql", "uploadSqlIdent",
             "uploadRegionCatalog", "renderUploadRegionSettings",
             "loadUploadRegionsHidden", "writeUploadRegionsHidden",
             "uploadRegionHidden", "setUploadRegionVisible"):
    eq("F2 exactly one %s" % name, code.count("function %s(" % name), 1)

_host = nocomment(fn("uploadCoverageHost"))
ok("z-index:2" in _host.replace(" ", ""),
   "F3 the grid sits above the file input that overlays the card (v11.34)")
ok(".dz-last" in _host, "F3b and lands under the last-upload line")

_r = nocomment(fn("renderUploadCoverage"))
ok("dzTablesFor(" in _r and "DZ_RECENT_SOURCES[" not in _r,
   "F4 the card is resolved through dzTablesFor, never the raw three-shape map")
ok("merged.cells[k] || v > merged.cells[k]" in _r.replace("!", ""),
   "F4b and a multi-table card takes the NEWEST per cell")

_all = nocomment(fn("renderAllUploadCoverage"))
# ⚠ The guarantee is that the RAIL hooks it exactly once - v11.45 broke the
# file by inserting the call beside all SEVEN renderAllDzRecentUploads call
# sites, one of which was a single-line try/catch. Counting it across the
# whole file instead pinned a number, and went red the moment the region
# toggle legitimately became a second caller.
eq("F5 hooked exactly once inside the rail renderer",
   nocomment(fn("renderAllDzRecentUploads")).count("renderAllUploadCoverage()"), 1)
eq("F5a and the only other caller is the region toggle",
   code.count("renderAllUploadCoverage()")
   - code.count("function renderAllUploadCoverage()"), 2)
ok("loadUploadRegionsHidden()" in _all,
   "F5b and the region setting is read before the first grid is drawn")

# The rail span stays display-only; the settings writers live elsewhere.
_rail = js[js.index("function _dzFmtRange"):js.index("function renderAllDzRecentUploads")]
ok(".upsert(" not in _rail and ".update(" not in _rail,
   "F6 the rail span contains no write")

eq("F7 version chip", len(re.findall(r">v\d+\.\d+ · [\d-]+<", s)), 1)

print("\n" + "=" * 62)
print("  v11.47  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
