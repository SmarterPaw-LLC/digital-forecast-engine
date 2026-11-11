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

# v12.07 - the campaign x day feed IS ADS_CHANNELS.walmart now; the
# `campdaily` view it lived in is deleted, and its column list was lifted
# verbatim into ADS_COLUMNS.walmart.
CD = js[js.index("  walmart: {", js.index("const ADS_CHANNELS = {")):]
CD = CD[:CD.index("\n  },\n};")]
CD_COLS = js[js.index("  walmart: [", js.index("const ADS_COLUMNS = {")):]
CD_COLS = CD_COLS[:CD_COLS.index("\n  ],")]
ok("dpv:          r.dpv == null ? null : +r.dpv || 0," in CD,
   "A6  the view maps page views")
ok("atc:          r.atc == null ? null : +r.atc || 0," in CD,
   "A7  ...and add to cart")
# /!\ A null stays null. The rollup's hasFunnel flag is what keeps a feed
# WITHOUT these from reading as "nobody viewed the page" (v11.25's rule).
ok("r.dpv == null ? null" in CD and "r.atc == null ? null" in CD,
   "A8  /!\\ null stays null, so a feed without them reads a GAP not a zero")

COLS = re.findall(r"\{ k: '(\w+)',", CD_COLS)
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
print("\nC. two tabs, and the retired feeds are gone")
# ===========================================================================
# /!\ v12.07 REPLACED THIS SECTION. It asserted a four-tab hierarchy -
# START HERE on Campaigns, SECONDARY on the account feed - which was the right
# answer while four feeds existed. Jason's answer was that two of them should
# not exist at all, so the hierarchy has nothing left to express and what is
# worth pinning instead is that the retirement is COMPLETE.
STRIP = s[s.index('<div id="wmpnl-view-ads"'):]
STRIP = STRIP[:STRIP.index("</div>", STRIP.index("subtab-strip"))]
eq("C1  two tabs", len(re.findall(r'class="subtab(?: on)?"', STRIP)), 2)
ok('id="wmpnl-ads-tab-campaigns"' in STRIP, "C2  Campaigns")
ok('id="wmpnl-ads-tab-keywords"' in STRIP, "C3  Keywords")
ok('class="subtab on" id="wmpnl-ads-tab-campaigns"' in STRIP,
   "C4  /!\\ Campaigns opens by default - it is the channel itself now")

# /!\ THE RETIREMENT IS COMPLETE, checked by ABSENCE across every surface a
# feed touches. A half-removed uploader leaves a dropzone that accepts a drop
# and does nothing, which is worse than leaving it in place (v10.19).
for pat, what in [
    ('id="dz-walmart-ad-daily"',      "the account dropzone"),
    ('id="dz-walmart-ad-campaign"',   "the monthly campaigns dropzone"),
    ("parseWalmartAdDaily",           "the account parser"),
    ("async function parseWalmartAdCampaign(", "the monthly parser"),
    ("handleWalmartAdDailyUpload",    "the account handler"),
    ("handleWalmartAdCampaignUpload", "the monthly handler"),
    ("walmartAdDailyCache",           "the account cache"),
    ("walmartAdCampaignCache",        "the monthly cache"),
    ("loadWalmartAdDaily",            "the account loader"),
    ("wmday-host",                    "the account host"),
    ("wmcd-host",                     "the campdaily host"),
    ("campdaily:",                    "the campdaily view"),
    ("'wmpnl-ads-view-daily'",        "the account area"),
]:
    ok(pat not in s, "C5  %s is gone" % what, None if pat not in s else pat)

# ...and the keyword feed, which is NOT retired, keeps all of its.
for pat, what in [('id="dz-walmart-ad-keyword"', "dropzone"),
                  ("parseWalmartAdKeyword", "parser"),
                  ("walmartAdKeywordCache", "cache"),
                  ("loadWalmartAdKeyword", "loader")]:
    ok(pat in s, "C6  /!\\ the keyword feed keeps its %s" % what)

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
