#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.06 - the funnel joins campaign x day, and four tabs stop reading as
four equal choices.

Jason: "what reports are being used now? can we clean up the uploader and ads
page?"

/!\ THE ANSWER WAS NOT "DELETE THE ACCOUNT FEED", although it is fully
superseded on content: campaign x day sums to it exactly. It is pulled from a
DIFFERENT report, and that independence is what caught v12.05's regex bug -
spend matched on all seven days while sales read 0.00. A cross-check that has
already earned its keep is worth a tab.

What was actually wrong is that four tabs read as four equal choices. So the
cleanup is in the LABELS: which one to start with, which is the check, and
what the two monthly feeds are still the only source of.
"""
import io, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


print("\n" + "=" * 70)
print("  v12.06  the funnel, and four tabs that say which to use")
print("=" * 70)

PARSER = fn_flat("parseWalmartAdCampaignDaily")

# ===========================================================================
print("\nA. the funnel columns")
# ===========================================================================
ok("const dpv      = _wmcAttrCol(H.norm, ['totalproductdetailpageviews'" in PARSER,
   "A1  page views are resolved by their own header")
ok("const atc      = _wmcAttrCol(H.norm, ['totaladdtocart'" in PARSER,
   "A2  and add to cart")
# /!\ THEY CARRY AN ATTRIBUTION WINDOW TOO, so they must be inside the
# one-window check - otherwise a 3-day Page Views column beside a 14-day
# Orders column would pass, which is the exact defect that check exists for.
ok("ntbOrd, ntbSales, dpv, atc]" in PARSER,
   "A3  /!\\ and BOTH are inside the one-window check")
ok("if (dpv.i      >= 0) row.dpv" in PARSER and "if (atc.i      >= 0) row.atc" in PARSER,
   "A4  written only when the file carries them")
ok("['page views', dpv.i], ['add to cart', atc.i]" in PARSER,
   "A5  ...and named in the status line when it does not")

CD = js[js.index("    campdaily: {"):]
CD = CD[:CD.index("\n    },")]
ok("dpv:          r.dpv == null ? null : +r.dpv || 0," in CD,
   "A6  the view maps page views")
ok("atc:          r.atc == null ? null : +r.atc || 0," in CD,
   "A7  ...and add to cart")
# /!\ A null stays null. The rollup's hasFunnel flag is what keeps a feed
# WITHOUT these from reading as "nobody viewed the page" (v11.25's rule).
ok("r.dpv == null ? null" in CD and "r.atc == null ? null" in CD,
   "A8  /!\\ null stays null, so a feed without them reads a GAP not a zero")

COLS = re.findall(r"\{ k: '(\w+)',", CD[CD.index("columns: ["):])
eq("A9  the funnel reads left to right on the row",
   [c for c in COLS if c in ('impressions', 'clicks', 'dpv', 'atc', 'orders')],
   ['impressions', 'clicks', 'dpv', 'atc', 'orders'])

# ===========================================================================
print("\nB. the migration")
# ===========================================================================
SQLP = os.path.join(ROOT, "supabase_v12_06_walmart_campaign_daily_funnel.sql")
ok(os.path.exists(SQLP), "B1  it is in the repo")
sql = io.open(SQLP, encoding="utf-8").read()
ok("add column if not exists dpv bigint;" in sql, "B2  dpv is added")
ok("add column if not exists atc bigint;" in sql, "B3  atc is added")
# /!\ ADDITIVE ONLY. The v12.05 table already holds rows; a create-table here
# would drop them, and a re-run must be safe.
ok("create table" not in sql.lower(),
   "B4  /!\\ additive only - it must not recreate a table that already holds rows")
ok("if not exists" in sql, "B5  and re-running it is safe")
# A schema error should name the file most likely missing, and there are TWO now.
ok("supabase_v12_06_walmart_campaign_daily_funnel.sql" in js,
   "B6  /!\\ a missing-column error names this file too, not just v12.05's")

# ===========================================================================
print("\nC. the four tabs say which to use")
# ===========================================================================
STRIP = s[s.index('<div id="wmpnl-view-ads"'):]
STRIP = STRIP[:STRIP.index("</div>", STRIP.index("subtab-strip"))]

ok("START HERE" in STRIP, "C1  one tab is named as the place to start")
eq("C2  /!\\ exactly one, or it is not a hierarchy", STRIP.count("START HERE"), 1)
ok('id="wmpnl-ads-tab-campdaily"' in STRIP
   and "START HERE" in STRIP[STRIP.index('id="wmpnl-ads-tab-campdaily"'):
                             STRIP.index("</button>", STRIP.index('id="wmpnl-ads-tab-campdaily"'))],
   "C3  ...and it is Campaigns, the one that carries the levers")

DAILY_BTN = STRIP[STRIP.index('id="wmpnl-ads-tab-daily"'):]
DAILY_BTN = DAILY_BTN[:DAILY_BTN.index("</button>")]
ok("SECONDARY" in DAILY_BTN, "C4  the account feed is marked secondary")
ok("CROSS-CHECK" in DAILY_BTN,
   "C5  /!\\ ...and says WHY it is kept - a different report agreeing is the proof")
eq("C6  /!\\ it is NOT deleted - it caught a real bug", s.count('id="dz-walmart-ad-daily"'), 1)
ok('id="wmpnl-ads-view-daily"' in s, "C7  its area survives")

# The two monthly feeds say what they are the only source of, so neither reads
# as a feed you still pull weekly.
ok("budget / status / bidding only" in s,
   "C8  the monthly campaign feed names what it alone carries")
ok("bids (the only source)" in s,
   "C9  ...and the keyword feed names its own")

# ===========================================================================
print("\nD. the chip agrees with CLAUDE.md")
# ===========================================================================
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "D1  both declare a version")
eq("D2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
