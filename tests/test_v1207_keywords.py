#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.07 - the Walmart KEYWORD parser, which survived the retirement.

/!\ THIS SUITE IS WHAT IS LEFT OF test_v1125. That suite tested
`parseWalmartAdCampaign` and `parseWalmartAdKeyword` together, and the
campaign one is retired with its feed - the Custom report's Campaign x Day
file replaced it, with a real date on every row.

The keyword export is NOT retired and is now the only monthly Walmart ads
feed: the Custom builder has no measure for a bid or a suggested bid, because
those are settings rather than performance. So its parser keeps its coverage,
and the fixture below is LIFTED VERBATIM from test_v1125 - five real rows,
including the two never-served keywords whose BLANK cells are the whole point
of the null-not-zero rule.
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


def const_obj(name):
    i = js.index("const " + name + " = {")
    return js[i:js.index("\n};", i) + 3]


print("\n" + "=" * 70)
print("  v12.07  the Walmart keyword feed, the last monthly one")
print("=" * 70)

KW_CSV = r'''"Keyword Id","Keyword","Status","Match Type","Suggested Bid","Bid","Campaign Name","Campaign Id","Campaign Status","Ad Group Name","Ad Group Id","Ad Group Status","Total Attributed Sales","RoAS","Omni ROAS","Ad Spend","Average CPC","Impressions","Clicks","CTR","Total Product Detail Page Views","Total Add To Cart","Conversion Rate","Orders","Units Sold","In-Store Attributed Sales","In-Store Units Sold","In-Store Orders"
168430246,"catnip","enabled","exact",1.25,0.75,"Kitty Ka Zoom - Manual",5177666,"Live","Mixed",6321932,"Enabled",1705.75,2.63,2.77,649.14,0.68,133063,950,0.0071,783,432,0.2684,255,269,91.55,15,5
168430244,"catnip","enabled","phrase",1.12,0.5,"Kitty Ka Zoom - Manual",5177666,"Live","Mixed",6321932,"Enabled",96.91,2.75,2.92,35.25,0.5,609,71,0.1166,45,21,0.1831,13,15,5.97,1,0
275837761,"dog treat","enabled","exact",3.16,0.9,"SP - KW - MIXED - DOGGIJUANA",5684267,"Live","18768809559",7159519,"Enabled",298.47,2.14,2.14,139.5,1.17,26909,119,0.0044,84,29,0.2185,26,27,0,0,0
275837803,"calm dog treat for anxiety","enabled","phrase",2.64,0.6,"SP - KW - MIXED - DOGGIJUANA",5684267,"Live","18768809559",7159519,"Enabled","","","","","","","","","","","","","","","",""
168430291,"kitty bubble","enabled","exact",2.02,0.5,"Kitty Ka Zoom - Manual",5177666,"Live","Mixed",6321932,"Enabled","","","","","","","","","","","","","","","",""
'''

PIECES = "\n".join([
    fn_flat("parseDelimited"),
    line_of("function parseCSV(line)"),
    line_of("function clean(s)"),
    line_of("const hdrNorm ="),
    fn_flat("_wmcNum"),
    line_of("function _wmcInt(v)"),
    fn_flat("_wmcCi"),
    fn_flat("_wmcLastDay"),
    const_obj("_WMC_SQL"),
    fn_flat("_wmcTableErr"),
    fn_flat("adsAdvertiserToBrand"),
    fn_flat("parseWalmartAdKeyword"),
])

DRIVER = r"""
'use strict';
__PIECES__
const written = [];
let deleted = null;
async function getSB() {
  return { from: () => ({
    delete: () => ({ eq: function () { return this; },
                     then: (f) => { deleted = true; return Promise.resolve(f({ error: null })); } }),
    insert: (rows) => { written.push(...rows); return Promise.resolve({ error: null }); },
  }) };
}
(async () => {
  try {
    const r = await parseWalmartAdKeyword(__KW__, 'Kitty Ka-Zoom (SmarterPaw LLC) (1p - SS)',
                                          'US', '2026-09');
    console.log(JSON.stringify({ r, rows: written }));
  } catch (e) { console.log(JSON.stringify({ threw: e.message })); }
})();
"""

p = os.path.join(SP, "_v1207kw.js")
io.open(p, "w", encoding="utf-8", newline="\n").write(
    DRIVER.replace("__PIECES__", PIECES).replace("__KW__", json.dumps(KW_CSV)))
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode != 0:
    print(r.stdout[-2500:]); print(r.stderr[-2500:]); raise SystemExit("node failed")
A = json.loads(r.stdout.strip().splitlines()[-1])
if "threw" in A:
    print("  FAIL  the parser threw: " + A["threw"]); raise SystemExit(1)
ROWS = A["rows"]
by = {}
for x in ROWS:
    by.setdefault(x["keyword"], []).append(x)

print("\nA. the parser, on five real rows")
eq("A1  every row is kept", len(ROWS), 5)
eq("A2  four distinct keywords", len(by), 4)
eq("A3  the month is stamped from the prompt, because the file has none",
   sorted({x["reporting_month"] for x in ROWS}), ["2026-09"])
eq("A4  ...and reporting_date is DERIVED as that month's last day",
   sorted({x["reporting_date"] for x in ROWS}), ["2026-09-30"])

# /!\ THE RULE THIS FIXTURE EXISTS FOR. Two of the five rows are enabled
# keywords carrying a real bid that have NOT SERVED yet - every metric cell is
# blank. Stored as 0 they would be indistinguishable from a keyword that
# delivered and returned nothing, which is the one row on an ads page nobody
# can afford to confuse with a gap.
never = by["kitty bubble"][0]
print("\nB. a blank metric cell is NULL, never 0")
eq("B1  /!\\ a never-served keyword has NULL spend", never["spend"], None)
eq("B2  /!\\ ...and null impressions", never["impressions"], None)
eq("B3  ...and null sales", never["sales"], None)
# /!\ But its BID is real, which is why the row is kept at all.
eq("B4  /!\\ its bid is a real number - that is why the row is kept", never["bid"], 0.5)
eq("B5  ...and so is Walmart's suggestion", never["suggested_bid"], 2.02)

served = by["catnip"]
eq("B6  a served keyword has real metrics",
   sorted(round(x["spend"], 2) for x in served), [35.25, 649.14])

print("\nC. one keyword, two match types, two rows")
# /!\ The parser keeps them SEPARATE; the rollup is what merges them by term.
eq("C1  /!\\ both match types are stored, not deduped",
   sorted(x["match_type"] for x in served), ["exact", "phrase"])

print("\nD. the brand comes from the CAMPAIGN NAME, not the account")
# /!\ The account is Kitty Ka-Zoom and it carries Doggijuana campaigns inside
# it, so reading the brand off the account files every Doggijuana dollar under
# Kitty Ka-Zoom.
eq("D1  a Kitty campaign's keyword", by["catnip"][0]["advertiser_brand"], "Kitty Ka-Zoom")
eq("D2  /!\\ a DOGGIJUANA campaign's keyword, inside the SAME account",
   by["dog treat"][0]["advertiser_brand"], "Doggijuana")

print("\nE. it is the only monthly Walmart ads feed left")
ok("parseWalmartAdKeyword" in js, "E1  its parser is live")
ok("async function parseWalmartAdCampaign(" not in js,
   "E2  /!\\ while the monthly CAMPAIGN parser is retired")
ok("parseWalmartAdDaily" not in js, "E3  ...and so is the Advertiser daily one")
ok("reporting_month" in fn_flat("parseWalmartAdKeyword"),
   "E4  it still stamps an operator-supplied month, because its file has no date")
ok("walmart_ad_keyword:  'supabase_v11_25_walmart_ads.sql'" in js,
   "E5  and a missing table still names the migration that creates it")

print("\nF. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) \u00b7 (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "F1  both declare a version")
eq("F2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
