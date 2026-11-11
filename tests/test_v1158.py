#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" v11.58 - a tooltip explains the VALUE, not the design decision behind it.

Jason, on the Walmart Ads In-Store $ tip:
  "explaining how the value is derived = good"
  "but the meta commentary is not"

The clause he objected to - "so it keeps its own column rather than being
folded into Ad Sales" - existed in ONE of the two places that column is
declared, which is why this suite is as much about the divergence as about
the wording.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1158_")
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
    """Strip // and /* */ comments.

    /!\\ v11.18, and this file has now logged it six times: a static guard over
    this source must strip comments FIRST, or it reads the comment EXPLAINING a
    retired mechanism as the mechanism. The patch for this release tripped on
    exactly that again.
    """
    t = re.sub(r"(?m)^\s*//.*$", "", t)
    return re.sub(r"/\*[\s\S]*?\*/", "", t)


JS = nocomment(js)

# v11.59 added roasVsBe to both tables, so this is 15.
SHARED = ['impressions', 'clicks', 'ctr', 'cpc', 'spend', 'orders', 'units',
          'cpa', 'cvr', 'sales', 'roas', 'inStoreSales', 'omniRoas', 'acos',
          'roasVsBe']

# ===========================================================================
print("\nA. ONE TEXT PER COLUMN - the shared table exists and is the only source")
# ===========================================================================
eq("A1  WM_ADS_TIP declared exactly once", JS.count("const WM_ADS_TIP = {"), 1)

decl = JS[JS.index("const WM_ADS_TIP = {"):]
decl = decl[:decl.index("\n};") + 3]
keys = re.findall(r"^\s{2}([A-Za-z0-9_]+):\s", decl, re.M)
eq("A2  it carries exactly the %d shared columns" % len(SHARED), sorted(keys), sorted(SHARED))

# /!\ `campaign` means two different things on the two tables - the campaign a
# KEYWORD spent under, vs the campaign the ROW is. Folding it in would be the
# rule 3a defect (one label, two measures), so its absence is the assertion.
ok("campaign:" not in decl, "A3  `campaign` is NOT shared (two meanings, two texts)")

ok("WM_ADS_TIP" in JS[:JS.index("const ADS_VIEWS = {")],
   "A4  declared BEFORE ADS_VIEWS, so both registries can read it")
ok(JS.index("const WM_ADS_TIP") < JS.index("const ADS_COLUMNS = {"),
   "A5  declared before ADS_COLUMNS too")

# ===========================================================================
print("\nB. BOTH registries read it - 14 columns x 2 tables")
# ===========================================================================
_views = JS.index("const ADS_VIEWS = {")
_wmv = JS.index("  walmart: {", _views)
kw = JS[JS.index("      columns: [", _wmv):JS.index("\n      ],", _wmv)]
cp_o = JS.index("  walmart: [", JS.index("const ADS_COLUMNS = {"))
cp = JS[cp_o:JS.index("\n  ],", cp_o)]
# v12.07 - TWO registries again. The Advertiser daily view and the monthly
# campaigns view are both retired, and ADS_COLUMNS.walmart IS the campaign x
# day list now - lifted verbatim out of the deleted view, so no header or
# tooltip was re-typed.
DAILY_OMITS = []

for blk, name in ((kw, "keyword"), (cp, "campaign")):
    missing = [k for k in SHARED if ("tip: WM_ADS_TIP." + k) not in blk]
    eq("B1  %-8s table reads the shared tip for all 14" % name, missing, [])

# v12.07 - B1b / B1c / B1d tested the two retired views. B1 above already
# covers both surviving registries, which is the guarantee that mattered:
# no Walmart ads table carries a literal tip beside a shared one.

# v12.03 - RE-POINTED. Two registries x 15 keys, plus the daily one which
# offers 11 of the 15. Derived rather than typed, so the next registry
# fails this line for the right reason.
# v12.05 - THREE registries carry all 15 (keywords, campaigns, campdaily)
# and the Advertiser daily one carries 11. Derived, so the next registry
# fails this line for the right reason rather than by a typed number.
WANT_REFS = len(SHARED) * 2
eq("B2  %d references in all" % WANT_REFS, JS.count("tip: WM_ADS_TIP."), WANT_REFS)

# No entry in the shared table is dead weight.
for k in SHARED:
    want = 2
    eq("B3  %-12s referenced %d time(s)" % (k, want),
       # /!\ `WM_ADS_TIP.roas` is a PREFIX of `WM_ADS_TIP.roasVsBe`, so a
       # substring count reads 4 for roas. Match the whole identifier.
       len(re.findall(r"tip: WM_ADS_TIP\." + k + r"\b(?!VsBe)", JS)), want)

# /!\ The whole failure mode: a literal tip surviving beside a shared one, so
# the two tables can drift apart again one edit later.
for blk, name in ((kw, "keyword"), (cp, "campaign")):
    lits = [m.group(1) for m in re.finditer(r"\{ k: '([A-Za-z0-9_]+)',[^\n]*?tip:\s*'", blk)
            if m.group(1) in SHARED]
    eq("B4  %-8s table has no literal tip for a shared column" % name, lits, [])

# `campaign` keeps its own, DIFFERENT text on each table.
kw_c = re.search(r"\{ k: 'campaign',[^\n]*?tip: '((?:[^'\\]|\\.)*)'", kw)
cp_c = re.search(r"\{ k: 'campaign',[^\n]*?tip: '((?:[^'\\]|\\.)*)'", cp)
ok(kw_c and cp_c, "B5  both tables still declare their own `campaign` tip")
ok(kw_c and cp_c and kw_c.group(1) != cp_c.group(1),
   "B6  and the two texts genuinely differ (two meanings)")

# ===========================================================================
print("\nC. THE META COMMENTARY IS GONE - and the derivation is not")
# ===========================================================================
RETIRED = [
    ("in-store, the clause Jason screenshotted",
     "so it keeps its own column rather than being folded into Ad Sales"),
    ("omni, where the word came from (a)", "own word for it, reused rather than coined"),
    ("omni, where the word came from (b)", "own word for it, kept verbatim"),
    ("acos, which column to read it beside", "so it reads against the ROAS column beside it"),
    ("uploads subtab citing a version at the user", "the v10.39 rule sends scheduled reports"),
    ("ga4 engagement, an implementation detail", "derived here rather than stored"),
    ("zero-spend toggle, justifying a default", "Hidden by default because a long tail"),
    ("chewy organic units, justifying no clamp", "because a clamp would hide a feed disagreement"),
    ("velocity window, restating itself", "so this ties out against Vel/day"),
    ("cover days, asserting the app agrees with itself", "so the two always agree"),
]
for label, phrase in RETIRED:
    ok(phrase not in nocomment(s), "C1  gone: %s" % label)

# ...but the reasoning survives where it belongs: in a comment.
ok("reused rather than coined (rule #3)" in s,
   "C2  the Omni naming rationale survives as a SOURCE COMMENT")
ok("NOT THE DESIGN DECISION" in s,
   "C3  the rule itself is written down beside the shared table")

KEPT = [
    ("in-store, what Walmart attributes",
     "physical-store purchases Walmart attributed back to an online ad click"),
    ("omni, that it is a second basis", "A SECOND BASIS, not a better ROAS"),
    ("omni, how it is derived", "never averaged across rows"),
    ("roas, that it reconciles to Walmart's own column", "the same basis as Walmart"),
    ("ad sales, the BASIS", "Walmart RETAIL dollars, not our revenue"),
    ("cvr, why totals not an average", "an average would weight a 3-click row"),
    ("walmart GM, what is NOT deducted", "Walmart allowances are NOT deducted"),
    ("walmart COGS, what is EXCLUDED", "An unpriced product is EXCLUDED rather than counted at zero"),
    ("chewy units, that it can read negative", "Can read negative when Chewy attributes more units"),
    ("landing pages, that it is a ranking", "a ranking, not a total"),
]
for label, phrase in KEPT:
    ok(phrase in s, "C4  kept: %s" % label)

# ===========================================================================
print("\nD. NO TOOLTIP CITES AN INTERNAL VERSION")
# ===========================================================================
# The one automatable half of the rule, and it is unambiguous: a release number
# is never a fact about a number on screen.
tips = []
for m in re.finditer(r"\btip:\s*'((?:[^'\\]|\\.)*)'", JS):
    tips.append(("tip", m.group(1)))
for m in re.finditer(r'\btitle="([^"]{25,})"', s):
    tips.append(("title", m.group(1)))
vers = [t for kind, t in tips if re.search(r"\bv\d+\.\d+\b", t)]
eq("D1  zero tooltips cite a vN.NN release", vers, [])
ok(len(tips) > 1000, "D2  the sweep actually walked the file", len(tips))

# The 26 this guard found on its first run, now gone. A sample pinned by text,
# so the sweep cannot be undone one tooltip at a time without failing here.
for phrase in ["v9.23 — CTR decay", "v8.71 — Cross-panel", "Pre-v7.52 bundles",
               "Per-region (v5.1)", "v7.38 — hover any cell", "(pre-v9.23)",
               "Past versions (v4.91, v4.92)", "defaulted ON since v7.27"]:
    ok(phrase not in s, "D3  gone from the UI: %r" % phrase)

# ...and the design history still lives where it belongs.
ok(len(re.findall(r"(?m)^\s*// .*\bv\d+\.\d+\b", s)) > 200,
   "D4  source comments keep their version history")

# ===========================================================================
print("\nE. The file still parses, and nothing else moved")
# ===========================================================================
p = os.path.join(SP, "app.js")
io.open(p, "w", encoding="utf-8", newline="").write(js)
r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
eq("E1  node --check clean", r.returncode, 0)

# The In-Store $ text is now ONE string, used twice.
INSTORE = "In-Store Attributed Sales: physical-store purchases Walmart attributed back to an online ad click."
eq("E2  the In-Store $ text exists exactly once in the file", JS.count(INSTORE), 1)
# v12.03 - RE-POINTED from 2 to 3, the same way B2 was: the guarantee is that
# the TEXT exists once (E2) and every column that shows In-Store $ reads it,
# not that there are two such columns. The Advertiser daily view is the third.
eq("E3  ...and every column that shows it reads that one string",
   JS.count("tip: WM_ADS_TIP.inStoreSales"), 2)

print("\n%s  %d passed, %d failed" % ("PASS" if not failed else "FAIL", passed, failed))
sys.exit(1 if failed else 0)
