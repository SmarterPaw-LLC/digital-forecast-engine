#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.50 - the summary upload NAMES the shipments with no detail.

- **Jason:** *"when i upload a shipment summary, it would be helpful if the
  success text told me which ones don't have shipment detail available."*

v5.49 already counted them, and the count never fired, because it asked only
about the rows IN THE FILE. Measured 2026-11-23 on the live database: all 25
of his rows have detail, while **7 shipments have had none since 2023**
(1,717 units, all CA, all Closed). A count that can only describe the file
you just uploaded is not a worklist.

This suite drives the real renderer and pins the status line's text budget,
which was **140 characters over two wrapped rows BEFORE** this release added
to it.
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0
BUDGET = 110


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
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.50  which shipments have no detail, not how many")
print("=" * 70)

# ===========================================================================
print("\nA. the query")
# ===========================================================================
SQL = run_node(os.path.join(SP, "_v1250_a.js"),
               fn_flat("fbaDetailGapSql") + "\nconsole.log(JSON.stringify(fbaDetailGapSql()));\n")
ok("fba_shipment_summaries" in SQL and "fba_shipments" in SQL,
   "A1  it joins the list CSV against the per-shipment detail")
ok("not exists" in SQL.lower(),
   "A2  a shipment with NO detail row is the gap")
ok("not like 'cancel%'" in SQL,
   "A3  /!\\ a CANCELLED shipment is not work - there is no detail to pull")
ok("lower(coalesce(s.status" in SQL,
   "A4  ...and the test is a normalised prefix, because the data carries BOTH "
   "`Canceled` and `Cancelled`")
ok(not re.search(r"\bas\s+t\b", SQL),
   "A5  /!\\ no column aliased `t` - exec_sql wraps as json_agg(t) and the row "
   "would collapse to that value (v12.08)")
ok(not SQL.rstrip().endswith(";"),
   "A6  /!\\ and no trailing semicolon - a syntax error inside the wrap")
ok("order by s.created_date desc" in SQL,
   "A7  newest first: the operator judges whether Amazon still serves an old one")
ok("limit" not in SQL.lower(),
   "A8  /!\\ NOT WINDOWED. v12.43 windows its re-pull list to 180 days; here "
   "the ENTIRE gap is older than that, so a window would draw a clean tick "
   "over the only thing there is to report")

# ===========================================================================
print("\nB. the real renderer, driven")
# ===========================================================================
HARNESS = (fn_flat("fbaDetailGapHtml") + "\n" + fn_flat("fbaDetailGapTip") + "\n"
           + fn_flat("fbaDetailGapBlock") + "\n" + fn_flat("fbaDetailGapToggle") + r"""
function esc2(x) { return String(x == null ? '' : x)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
const FBA_DETAIL_GAP_SOURCES = { fba_shipment_summaries: true };
const _fbaDetailGap = {};
const _fbaDetailGapOpen = {};
const document = { getElementById: () => null };

// The 7 read off the live database on 2026-11-23.
const LIVE = [
  { shipment_id:'FBA179Z6SM14', shipment_name:'FBA STA (07/31/2023 20:01)-YHM1', region:'CA',
    brand:null, status:'Closed', units_expected:149, units_located:149, sku_count:4, created_on:'2023-07-31' },
  { shipment_id:'FBA1786R71JD', shipment_name:'FBA STA (06/21/2023 18:46)-YYZ4', region:'CA',
    brand:null, status:'Closed', units_expected:168, units_located:168, sku_count:2, created_on:'2023-06-21' },
  { shipment_id:'FBA174L6CT45', shipment_name:'FBA STA (04/26/2023 21:00)-YYZ4', region:'CA',
    brand:null, status:'Closed', units_expected:100, units_located:99, sku_count:2, created_on:'2023-04-26' },
  { shipment_id:'FBA173CRYC0V', shipment_name:'FBA STA (04/05/2023 20:13)-YYZ4', region:'CA',
    brand:null, status:'Closed', units_expected:260, units_located:260, sku_count:4, created_on:'2023-04-05' },
  { shipment_id:'FBA173082ZD8', shipment_name:'FBA STA (03/29/2023 16:00)-YYC1', region:'CA',
    brand:null, status:'Closed', units_expected:244, units_located:244, sku_count:6, created_on:'2023-03-29' },
  { shipment_id:'FBA1713ZZTC3', shipment_name:'FBA STA (02/20/2023 21:52)-YVR4', region:'CA',
    brand:null, status:'Closed', units_expected:396, units_located:396, sku_count:2, created_on:'2023-02-20' },
  { shipment_id:'FBA170ZZSJKJ', shipment_name:'FBA STA (02/14/2023 16:31)-YOW3', region:'CA',
    brand:null, status:'Closed', units_expected:400, units_located:402, sku_count:15, created_on:'2023-02-14' },
];

const out = {
  none:    fbaDetailGapHtml(null, 'dz'),
  clean:   fbaDetailGapHtml({ rows: [], err: null }, 'dz'),
  err:     fbaDetailGapHtml({ rows: [], err: 'permission denied for table' }, 'dz'),
  closed:  fbaDetailGapHtml({ rows: LIVE, err: null }, 'dz'),
  one:     fbaDetailGapHtml({ rows: [LIVE[0]], err: null }, 'dz'),
  tip:     fbaDetailGapTip(),
  blockOn: fbaDetailGapBlock('fba_shipment_summaries', 'dz'),
  blockOff: fbaDetailGapBlock('sku_economics', 'dz'),
};
_fbaDetailGapOpen['dz'] = true;
out.open = fbaDetailGapHtml({ rows: LIVE, err: null }, 'dz');
out.openNullBrand = /SP-|Meowijuana/.test(out.open);
console.log(JSON.stringify(out));
""")
B = run_node(os.path.join(SP, "_v1250_b.js"), HARNESS)

eq("B1  nothing fetched yet draws nothing", B["none"], "")
ok("every shipment has detail" in B["clean"],
   "B2  a clean table says so, with the tip on the title")
ok("detail coverage not checked" in B["err"] and "permission denied" in B["err"],
   "B3  /!\\ a FAILED READ is not a clean tick (v10.19) - it names the error")
ok("every shipment has detail" not in B["err"],
   "B4  ...and never both")
ok("7 shipments need detail" in B["closed"],
   "B5  /!\\ THE ASK: the count on one line, orange, click to expand")
ok("&#9662;" in B["closed"] and "&#9652;" in B["open"],
   "B6  the caret follows the open state")
ok("<table" not in B["closed"],
   "B7  closed is ONE LINE - the list is not printed into the card unasked")
ok("1 shipment need" in B["one"] or "1 shipment needs" in B["one"] or "1 shipment " in B["one"],
   "B8  one row does not read `1 shipments`", B["one"][:140])

# the expanded table
for sid in ["FBA179Z6SM14", "FBA170ZZSJKJ"]:
    ok(sid in B["open"], "B9  the expanded list NAMES %s" % sid)
ok(B["open"].index("FBA179Z6SM14") < B["open"].index("FBA170ZZSJKJ"),
   "B10 ...newest first, the order the query returns")
ok("2023-07-31" in B["open"],
   "B11 with the created date, so an unservable old shipment is visible")
ok(">CA<" in B["open"] and ">Closed<" in B["open"],
   "B12 ...the marketplace and the status")
eq("B13 1,717 units named as the cost of the gap",
   "1,717 units with no item detail" in B["open"], True)
ok("downloadFbaDetailGapCSV" in B["open"],
   "B14 and it is CSV-exportable before it ships (RULES.md #12)")
ok(not B["openNullBrand"],
   "B15 /!\\ a null brand is a DASH, never an invented one")

# the block gate
ok(B["blockOn"].startswith('<div id="fdg-dz"'),
   "B16 the block is hosted for the card that has the feed")
eq("B17 /!\\ and a card without it gets NO block, not an empty one",
   B["blockOff"], "")

# the tooltip
ok("Download the per-shipment .tsv" in B["tip"],
   "C1  the tip says HOW to close the gap")
ok("Cancelled shipments are not listed" in B["tip"],
   "C2  ...and states the one thing it leaves out")
ok("All time" in B["tip"],
   "C3  /!\\ the FBA Shipments filter defaults to the last 365 days, and every "
   "one of these is from 2023 - the tip says to widen it")

# ===========================================================================
print("\nD. the status line, and its budget")
# ===========================================================================
H = fn_flat("handleFbaShipmentSummaryUpload")
ok(re.search(r"setSt\s*=\s*\(msg, cls, tip\)", H) is not None,
   "D1  setSt carries a tooltip (the v12.47 shape)")
ok("el.style.cursor = 'help'" in H,
   "D2  ...and the line reads as having one")
ok("removeAttribute('title')" in H,
   "D3  /!\\ and a call with no tip CLEARS the last one - a stale tooltip "
   "describing the previous upload is worse than none")
ok("` · 📥 ${result.missingDetailCount} need detail`" in H,
   "D4  the visible warning is four words")
ok('filter "Missing detail")' not in H,
   "D5  /!\\ the 66-character pointer is off the line")
ok("ID extracted from name on" not in H.split("detail.push")[0],
   "D6  ...and so is the ID-extraction provenance")
ok("detail.push" in H and "detail.join" in H,
   "D7  every clause that is not a number is a tooltip line")
ok("extractedLbl" not in js,
   "D7a /!\ and the label it replaced is GONE, not left declared and read "
   "nowhere - a dead const is the leftover hard rule #1 is about")
ok("result.missingDetailIds.slice(0, 40)" in H,
   "D8  the IDs are named on the tooltip, capped, with the remainder counted")
ok("could not be checked" in H,
   "D9  /!\\ a failed check does not read as a clean one on the line either")

# Rebuild the exact visible string the handler would produce, from the live
# figures in Jason's screenshot plus the measured gap.
LINE = ("✓ 25 shipments · 24,914 expected / 21,220 located"
        " · ⚠ 3,694 units short · \U0001f4e5 7 need detail"
        " · \U0001f3f7 Meowijuana")
PRE = ("✓ 25 shipments · 24,914 expected / 21,220 located"
       " · ⚠ 3,694 units short · ID extracted from name on 25 rows"
       " · \U0001f3f7 tagged Meowijuana on 25 rows")
ok(len(PRE) > BUDGET,
   "E1  /!\\ THE LINE WAS ALREADY OVER BUDGET BEFORE THIS RELEASE: %d chars "
   "against %d (the v12.47 lesson, on the very line being edited)" % (len(PRE), BUDGET))
ok(len(LINE) <= BUDGET,
   "E2  ...and it is inside the budget WITH the new warning on it: %d chars"
   % len(LINE), len(LINE))

# ===========================================================================
print("\nF. one derivation, two surfaces")
# ===========================================================================
P = fn_flat("parseFbaShipmentSummary")
ok("await fbaDetailGapFetch(true)" in P,
   "F1  the parser reads the one derivation")
ok(".select('shipment_id').in('shipment_id', batch)" not in js,
   "F2  /!\\ the per-FILE batch check is GONE, not left standing beside it "
   "(hard rule #1)")
ok("missingDetailIds" in P,
   "F3  and the ids ride the result so the status line needs no second query")
R = fn_flat("renderUploadCoverage")
ok("fbaDetailGapFetch(true)" in R and "fbaDetailGapBlock" in R,
   "F4  the block rides the SAME repaint as the coverage grid (the v12.43 "
   "precedent) so it survives a reload")
ok(R.index("feeSettleBlock") < R.index("fbaDetailGapBlock"),
   "F5  ...under the settlement line, in one host")
ok(js.count("FBA_DETAIL_GAP_SOURCES") >= 3,
   "F6  the feed is DECLARED in a registry, not hardcoded to a dzId")
ok("csvEsc" in fn_flat("downloadFbaDetailGapCSV") and "promptCsvName" in fn_flat("downloadFbaDetailGapCSV"),
   "F7  the export is the app's own writer, not a tenth one")

# ===========================================================================
print("\nG. the release names itself")
# ===========================================================================
# /!\ THE GUARANTEE, NOT THE NUMBER. test_v1249 pinned `v12.49` literally and
# went red the moment v12.50 shipped - a red that was not a defect. What has to
# hold on every release is that the chip and CLAUDE.md cannot disagree.
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "G1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok(chip is not None and "\\u" not in chip.group(0),
   "G2  /!\\ REAL characters in markup, not the escape form (v12.42 shipped "
   "`v12.42 \\u00b7` as literal text)", chip.group(0) if chip else None)
C = C_
ok("v12.50" in C, "G3  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
