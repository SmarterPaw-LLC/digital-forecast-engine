#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.43 - when to re-pull: a week whose FEES HAVE NOT POSTED.

- **Jason:** *"i ALWAYS have pulled the reports Sunday through Saturday ...
  I don't know how these date gaps even happened"* ... *"yes, i need to know
  when to repull"*

/!\ There are no date gaps. Amazon's SKU Economics settles AFTER the fact,
this app pulls a week once and never re-reads it, and five US weeks were
frozen before the fulfilment fees posted.

/!\ AND THE CHIP BROKE IN v12.42. `\uXXXX` went into MARKUP, where it renders
as six literal characters. Section E is the regression.
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


def const_src(name):
    i = js.index("const " + name)
    return js[i:js.index("\n", js.index(";", i))]


def strip_comments(t):
    t = re.sub(r"/\*[\s\S]*?\*/", "", t)
    return re.sub(r"^\s*//.*$", "", t, flags=re.M)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.43  a week whose fees have not posted")
print("=" * 70)

# ===========================================================================
print("\nA. /!\\ SUN-SAT, because that is what the operator types")
# ===========================================================================
A = run_node(os.path.join(SP, "_v1243_a.js"),
             fn_flat("parseLocalDate") + "\n" + fn_flat("feeSettleWeekRange") + r"""
console.log(JSON.stringify({
  // The five US weeks measured on the live database.
  jun22: feeSettleWeekRange('2026-06-22'),
  jun29: feeSettleWeekRange('2026-06-29'),
  jul06: feeSettleWeekRange('2026-07-06'),
  jul20: feeSettleWeekRange('2026-07-20'),
  aug03: feeSettleWeekRange('2026-08-03'),
  // A month boundary, and a year one.
  mar02: feeSettleWeekRange('2026-03-02'),
  jan04: feeSettleWeekRange('2027-01-04'),
  junk:  feeSettleWeekRange('not-a-date'),
  blank: feeSettleWeekRange(''),
  nul:   feeSettleWeekRange(null),
}));
""")
eq("A1  /!\\ the stored MONDAY prints as Amazon's SUN-SAT week - this is the "
   "range typed into the report's date picker, and Jason's screenshot shows "
   "exactly it", A["jun22"], {"from": "2026-06-21", "to": "2026-06-27"})
eq("A2  ...and it is seven days, not six or eight",
   A["jun29"], {"from": "2026-06-28", "to": "2026-07-04"})
eq("A3  a week that crosses a month end", A["jul06"], {"from": "2026-07-05", "to": "2026-07-11"})
eq("A4  the other two measured weeks",
   [A["jul20"], A["aug03"]],
   [{"from": "2026-07-19", "to": "2026-07-25"},
    {"from": "2026-08-02", "to": "2026-08-08"}])
eq("A5  /!\\ a week that crosses a YEAR end carries the year back with it",
   A["jan04"], {"from": "2027-01-03", "to": "2027-01-09"})
eq("A6  the start of March, which is where a UTC parse would have slipped a "
   "day", A["mar02"], {"from": "2026-03-01", "to": "2026-03-07"})
for k in ("junk", "blank", "nul"):
    ok(A[k]["from"] == A[k]["to"],
       "A7  an unreadable key collapses to itself rather than inventing a "
       "range (%s)" % k, A[k])
ok("parseLocalDate(" in fn_flat("feeSettleWeekRange"),
   "A8  /!\\ through the shared LOCAL parser - the v9.71 rule, and a UTC "
   "parse here would move every date in the list by a day")

# ===========================================================================
print("\nB. the SQL says what the comment says")
# ===========================================================================
SQL = fn_flat("feeSettleSql")
B = run_node(os.path.join(SP, "_v1243_b.js"),
             fn_flat("uploadSqlIdent") + "\n"
             + const_src("FEE_SETTLE_FLOOR") + "\n"
             + const_src("FEE_SETTLE_MIN_UNITS") + "\n"
             + const_src("FEE_SETTLE_MIN_WEEKS") + "\n"
             + const_src("FEE_SETTLE_WINDOW_DAYS") + "\n"
             + "const FEE_SETTLE_SOURCES = " + js[js.index("const FEE_SETTLE_SOURCES = {")
               + len("const FEE_SETTLE_SOURCES = "):js.index("};", js.index("const FEE_SETTLE_SOURCES = {")) + 2]
             + "\n" + SQL + r"""
console.log(JSON.stringify({
  us: feeSettleSql('sku_economics'),
  eu: feeSettleSql('sku_economics_eu'),
  nope: feeSettleSql('sales_weekly'),
  inject: feeSettleSql("sku_economics; drop table products --"),
  floor: FEE_SETTLE_FLOOR, minU: FEE_SETTLE_MIN_UNITS, minW: FEE_SETTLE_MIN_WEEKS,
  winD: FEE_SETTLE_WINDOW_DAYS,
}));
""")
eq("B1  the floor is 80% of the brand's own median", B["floor"], 0.80)
eq("B2  a thin week is not judged", B["minU"], 25)
eq("B3  ...nor is a brand with too few weeks to have a median", B["minW"], 8)
eq("B3a the LIST is windowed to six months", B["winD"], 180)
ok("current_date - interval '180 days'" in B["us"],
   "B3b /!\\ and the window is on the FINAL select, not on the CTE - a median "
   "wants every loaded week and only the WORKLIST is recent. Unwindowed it "
   "named 40+ weeks inside closed quarters, and that was found by RUNNING "
   "the query rather than reading it")
ok(B["us"].index("percentile_cont") < B["us"].index("current_date"),
   "B3c the median is computed before the window narrows anything")
ok("fba_fulfillment_fee_total" in B["us"],
   "B4  the US table's fee column")
ok("fba_fulfilment_fees_total" in B["eu"],
   "B5  /!\\ and the EU table spells fulfilment with ONE L - which is why "
   "this is a registry and not a column written into the query")
ok(B["nope"] is None,
   "B6  /!\\ a feed NOT in the registry gets no query at all, so no card can "
   "render a check it never ran (v10.19)")
ok(B["inject"] is None,
   "B7  /!\\ and a table name that is not a bare identifier is refused, not "
   "interpolated")
ok("percentile_cont(0.5)" in B["us"],
   "B8  the median is a median, not a mean - one short week would drag an "
   "average down and hide the next one")
ok("net_proceeds_total" in B["us"],
   "B9  /!\\ net proceeds rides along, because it is the number that says "
   "the fee is MISSING FROM AMAZON'S FILE rather than genuinely low")
ok(not B["us"].rstrip().endswith(";"),
   "B10 /!\\ no trailing semicolon - exec_sql wraps the query and a ';' is a "
   "syntax error (the v12.08 lesson)")
ok(" as t\n" not in B["us"] and " as t," not in B["us"],
   "B11 ...and no column aliased `t`, which would collide with the json_agg "
   "alias and collapse every row to one value")
ok("coalesce(t.net_units_sold, 0)" in B["us"],
   "B12 a null unit count is zero, not a null that silently drops the week")

# ===========================================================================
print("\nC. the line, driven over real shapes")
# ===========================================================================
ROWS = [
  {"region": "US", "brand": "Meowijuana", "wk": "2026-06-22", "units": 2815,
   "fee_per_unit": 1.20, "normal_per_unit": 3.48, "proceeds_pct": 59.6, "shortfall": 6413},
  {"region": "CA", "brand": "Kitty Ka-Zoom", "wk": "2026-03-09", "units": 434,
   "fee_per_unit": 0.0, "normal_per_unit": 5.76, "proceeds_pct": None, "shortfall": 1470},
]
C = run_node(os.path.join(SP, "_v1243_c.js"),
             fn_flat("parseLocalDate") + "\n" + fn_flat("feeSettleWeekRange") + "\n"
             + fn_flat("esc2") + "\n"
             + const_src("FEE_SETTLE_FLOOR") + "\n"
             + "const FEE_SETTLE_SOURCES = { sku_economics: { fee: 'x' } };\n"
             + "const _feeSettle = {}; const _feeSettleOpen = {};\n"
             + fn_flat("feeSettleTip") + "\n" + fn_flat("feeSettleHtml") + "\n"
             + fn_flat("feeSettleBlock") + r"""
const ROWS = """ + json.dumps(ROWS) + r""";
const out = {};
out.clean  = feeSettleHtml('sku_economics', { rows: [], err: null }, 'dz-x');
out.err    = feeSettleHtml('sku_economics', { rows: [], err: 'statement timeout' }, 'dz-x');
out.none   = feeSettleHtml('sku_economics', null, 'dz-x');
out.closed = feeSettleHtml('sku_economics', { rows: ROWS, err: null }, 'dz-x');
_feeSettleOpen['dz-x'] = true;
out.open   = feeSettleHtml('sku_economics', { rows: ROWS, err: null }, 'dz-x');
out.one    = feeSettleHtml('sku_economics', { rows: [ROWS[0]], err: null }, 'dz-x');
_feeSettleOpen['dz-x'] = false;
out.noReg  = feeSettleBlock('sales_weekly', 'dz-y');
console.log(JSON.stringify(out));
""")
ok("fees posted on every week" in C["clean"] and "re-pull" not in C["clean"],
   "C1  a clean feed says so quietly rather than rendering an empty table")
ok("fee settlement not checked" in C["err"] and "statement timeout" in C["err"],
   "C2  /!\\ a read that FAILED says it could not check - it never renders a "
   "tick it did not earn")
eq("C3  a feed that has not been read yet renders nothing at all",
   C["none"], "")
ok("2 weeks to re-pull" in C["closed"],
   "C4  the headline counts the weeks", C["closed"][:120])
ok("<table" not in C["closed"],
   "C5  ...and the list stays closed until it is asked for")
ok("<table" in C["open"], "C6  opening it draws the list")
ok("2026-06-21" in C["open"] and "2026-06-27" in C["open"],
   "C7  /!\\ in SUN-SAT form, which is the range the report asks for")
ok("2026-06-22" not in C["open"],
   "C8  /!\\ and NOT the stored Monday, which would send him to pull the "
   "wrong week")
ok("$1.20" in C["open"] and "$3.48" in C["open"],
   "C9  the week's figure beside what that brand normally runs, so the "
   "judgement is visible rather than asserted")
ok("59.6%" in C["open"],
   "C10 net proceeds, the corroborating number")
ok("&#8212;" in C["open"],
   "C11 /!\\ a week with no proceeds figure draws a DASH, never 0.0% - a "
   "measured-looking zero for something nobody measured (v11.16)")
ok("$7,883" in C["open"],
   "C12 the shortfall totals across the list", C["open"][-260:])
ok("downloadFeeSettleCSV" in C["open"],
   "C13 and it exports, which is the standing rule for any data view")
ok("1 week to re-pull" in C["one"],
   "C14 one week is not '1 weeks'")
eq("C15 /!\\ a feed not in the registry renders NO block, so a card cannot "
   "show a check that has no query behind it", C["noReg"], "")
ok("event.stopPropagation()" in C["closed"],
   "C16 /!\\ the click does not reach the dropzone underneath - this line "
   "sits inside a card whose file INPUT overlays the whole thing")

# ===========================================================================
print("\nD. one surface, one repaint")
# ===========================================================================
NO_C = strip_comments(js)
RUC = fn_flat("renderUploadCoverage")
ok("feeSettleBlock(sources[0].table, dzId)" in RUC,
   "D1  the block is appended by the coverage repaint, not by a second "
   "renderer with its own schedule")
ok("await feeSettleFetch(sources[0].table, true)" in RUC,
   "D2  /!\\ fetched BEFORE the paint and forced, so the week an upload just "
   "wrote is judged by that upload rather than by a cached answer")
ok("catch (e) { console.warn('feeSettle'" in RUC,
   "D3  /!\\ and it cannot take the coverage grid down with it")
ok(RUC.index("feeSettleFetch") < RUC.index("host.innerHTML"),
   "D4  the fetch precedes the paint by POSITION, not by hope")
eq("D5  one place builds the block", NO_C.count("function feeSettleBlock"), 1)
eq("D6  one place renders it", NO_C.count("function feeSettleHtml"), 1)
eq("D7  one query", NO_C.count("function feeSettleSql"), 1)
ok("csvEsc" in fn_flat("downloadFeeSettleCSV")
   and "promptCsvName" in fn_flat("downloadFeeSettleCSV"),
   "D8  the export uses the app's OWN csv helpers and filename prompt, not a "
   "tenth spelling of either (hard rule #1)")
ok("Stored_Week_Start_Mon" in fn_flat("downloadFeeSettleCSV"),
   "D9  /!\\ the CSV carries the stored Monday BESIDE the Sun-Sat range, so "
   "the file can be matched back to the table it describes")

# ===========================================================================
print("\nE. /!\\ THE REGRESSION: a JS escape in MARKUP renders as text")
# ===========================================================================
# v12.42 wrote `·` into the version chip, which lives in HTML. It
# rendered as the six characters. index.html holds REAL characters in markup
# and \uXXXX escapes only inside JS string literals - the v12.09 rule.
chips = re.findall(r'>v\d+\.\d+ (.) [\d-]+</span>', s)
eq("E1  exactly one version chip", len(chips), 1)
eq("E2  /!\\ its separator is a REAL middle dot, not an escape", chips[0], "·")
# /!\ THE NEEDLE IS BUILT, NOT TYPED. Writing the six characters as a
# literal is how this very assertion was wrong first time: the editor that
# wrote this file turned them into a real middle dot, so it asserted that the
# correct chip was absent.
_ESC = chr(92) + "u00b7"
ok((">v12.43 " + _ESC) not in s,
   "E3  /!\\ and the escape form does not survive anywhere in the chip")
eq("E3b the needle really is six characters, not one", len(_ESC), 6)
# The markup of this file - everything outside <script> - may not carry a
# \uXXXX escape at all, because nothing there interprets one.
markup = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", s)
stray = re.findall(r"\\u[0-9a-fA-F]{4}", markup)
eq("E4  /!\\ NO \\uXXXX ESCAPE ANYWHERE IN THE MARKUP - this is the check "
   "that would have caught v12.42 before Jason saw it", stray, [])

# ===========================================================================
print("\nF. the reason is recorded where the next reader will be")
# ===========================================================================
# A comment wraps, so the phrase is searched in the FLATTENED text rather
# than as one contiguous line - which is what this check got wrong first.
_FLAT = re.sub(r"\s*\n\s*//\s*", " ", js)
ok("IS NET PROCEEDS" in _FLAT,
   "F1  /!\\ the test that separates 'Amazon did not charge it' from 'we "
   "dropped the column' is named in the code")
ok("Sunday through Saturday" in js,
   "F2  and so is the report that found it")
ok("12-57%" in js,
   "F3  /!\\ the 80% floor carries the MEASUREMENT that chose it, so the "
   "next reader can tell a threshold from a guess")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
