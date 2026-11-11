#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.81 - the Uploads page grouped by channel, with a what-needs-feeding strip.

Jason: "i need this entire page organized better."

  * A  the move: every group is still on the page, in exactly one section, and
       nothing interactive was lost on the way (the v10.87 failure mode).
  * B  the vocabulary: section glyphs are the P&L nav's channel glyphs, not a
       second set for the same four channels (rule #3).
  * C  the real upAttentionVerdict / upAttentionWorstPerRow / uploadAgeDays,
       sliced and driven.
  * D  the regression guard: a per-TABLE list really does draw two chips for
       one row, and the strip really would have reached rows that are not on
       this page.
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


def nocomment(t):
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
    return _bal(js.index(kw + " " + name + "("))


NC   = nocomment(js)
VIEW = s[s.index('<div id="data-view-uploads"'):s.index('<div id="data-view-history"')]

AMZ, WMT, CHEWY, DTC = chr(0x1f4ca), chr(0x1f6d2), chr(0x1f43e), chr(0x1f6cd)

# ---------------------------------------------------------------------------
print("A. the move - nothing fell out of it")
# ---------------------------------------------------------------------------
gids = re.findall(r'<div class="up-grp" id="(grp-[a-z0-9-]+)">', VIEW)
eq("A1  18 groups on the page", len(gids), 18)
eq("A2  ...and none of them twice", len(set(gids)), 18)

# Everything interactive the groups carried before the move is still here.
# These counts are the ones the extractor took on BOTH sides of the cut.
# v12.03 - /!\ EACH OF THESE IS +1 FOR ONE NEW DROPZONE (Walmart Ads -
# Daily), and +2 on A7 because a dropzone carries both a dz-st and a
# dz-last. The guarantee is that nothing was LOST in the v11.81 move, so a
# deliberate addition is bumped rather than the assertion loosened - a
# >= would stop catching the thing this suite exists for.
# v12.05 - +1 again, for the Campaign x Day dropzone. Bumped rather than
# loosened to a >=, which would stop catching a LOST one.
eq("A3  /!\\ every dropzone survived the move",
   len(re.findall(r'id="dz-[a-z0-9-]+"', VIEW)), 22)
eq("A4  /!\\ every file input survived", len(re.findall(r'type="file"', VIEW)), 26)
eq("A5  /!\\ every onchange handler survived", len(re.findall(r'onchange="', VIEW)), 25)
# v11.82 swapped the GA4 row's two copy buttons (two tooltips) for one Run
# button (one), so the page carries one fewer. The count stays pinned: its job
# is catching a tooltip that falls out of a MOVE, not freezing the page.
eq("A6  /!\\ every tooltip survived", len(re.findall(r'title="', VIEW)), 52)
eq("A7  /!\\ every status / last element survived",
   len(re.findall(r'id="(?:st|last)-[a-z0-9-]+"', VIEW)), 63)
ok('id="f-newsku"' in VIEW,
   "A8  /!\\ the legacy hidden hook outside every group is still here")

secs = re.findall(r'<div class="up-section-hdr">([\s\S]*?)</div>', VIEW)
eq("A9  seven sections", len(secs), 7)
# Each group sits in exactly one section, and every section has at least one.
spans = [m.start() for m in re.finditer(r'<div class="up-section-hdr">', VIEW)] + [len(VIEW)]
counts = []
for i in range(len(spans) - 1):
    counts.append(len(re.findall(r'<div class="up-grp" id="', VIEW[spans[i]:spans[i + 1]])))
eq("A10 group counts per section", counts, [3, 2, 4, 2, 3, 3, 1])
eq("A11 ...summing to every group", sum(counts), 18)

# ---------------------------------------------------------------------------
print("\nB. the vocabulary - the channel glyphs are the P&L nav's")
# ---------------------------------------------------------------------------
nav = s[s.index('id="pv-amazon"'):s.index('id="pv-pricing"')]
for glyph, who in [(AMZ, "Amazon"), (WMT, "Walmart"), (CHEWY, "Chewy"), (DTC, "DTC")]:
    ok(glyph in nav, "B1  the P&L nav really uses %s for %s" % (glyph, who))
    ok(any(h.strip().startswith(glyph) for h in secs),
       "B2  ...and a section borrows it rather than coining one (%s)" % who)
eq("B3  /!\\ all three Amazon sections carry ONE Amazon glyph",
   len([h for h in secs if h.strip().startswith(AMZ)]), 3)

# The two icons this change made wrong.
def grp_block(gid):
    a = VIEW.index('<div class="up-grp" id="%s">' % gid)
    nxt = VIEW.find('<div class="up-grp" id="', a + 10)
    end = VIEW.find('</div>\n      </div>', a)
    return VIEW[a:min(x for x in (nxt, end) if x > a)]

chewy_act = grp_block("grp-chewy-actuals")
traffic   = grp_block("grp-sales-traffic")
ok(AMZ not in chewy_act,
   "B4  /!\\ no Amazon glyph inside the Chewy section - it would read as Amazon")
# Sales & Traffic sits IN the Amazon section, so a bar chart on its drop tile
# is consistent rather than wrong; what was wrong was the ROW icon repeating
# the section's own glyph one line above it.
tr_ico = re.search(r'<span class="up-grp-ico">(.*?)</span>', traffic).group(1)
ok(AMZ != tr_ico,
   "B5  /!\\ ...and the Sales & Traffic ROW no longer duplicates its OWN section glyph",
   tr_ico)
ok(chr(0x1f9fe) in chewy_act, "B6  Chewy actuals took a receipt")
ok(chr(0x1f441) in traffic,   "B7  Sales & Traffic took an eye - it counts views")

# ---------------------------------------------------------------------------
print("\nC. the strip - no second opinion, one chip per row, this page only")
# ---------------------------------------------------------------------------
eq("C1  uploadAgeDays declared exactly once", NC.count("function uploadAgeDays("), 1)
ok("const ageOf" not in NC,
   "C2  /!\\ the local copy inside uploadCoverageHtml is GONE, not shadowing it")
ok("uploadAgeDays(end, today)" in NC,
   "C3  /!\\ the coverage grid was converted in the same commit (rule #5)")
ok("uploadFreshDays(table)" in nocomment(fn("upAttentionFeeds")),
   "C4  /!\\ the tolerance is the v11.75 definition, not a second one")
ok("uploadDataThru(" in nocomment(fn("upAttentionVerdict")),
   "C5  /!\\ ...and so is the period end")
ok("DZ_RECENT_SOURCES" in nocomment(fn("upAttentionFeeds")),
   "C6  the feed list reuses the registry test_v1086 already polices")
ok("page.contains(grp)" in nocomment(fn("upAttentionFeeds")),
   "C7  /!\\ scoped to #data-view-uploads - four uploaders live on the P&L")
eq("C8  upAttentionWorstPerRow declared once", NC.count("function upAttentionWorstPerRow("), 1)
ok("upAttentionWorstPerRow(" in nocomment(fn("renderUploadAttention", "async function")),
   "C9  ...and the renderer uses it")
ok("upAttentionFeedBy" not in NC,
   "C10 /!\\ the tooltip no longer re-runs discovery - it could land on the "
   "OTHER feed in the same row")
ok("if (error) return null;" in nocomment(fn("renderUploadAttention", "async function")),
   "C11 /!\\ a table that cannot be READ is not reported as never loaded")
ok("box.style.display = 'none'" in nocomment(fn("renderUploadAttention", "async function")),
   "C12 an empty strip hides - an empty box is not a status")
ok("UP_ATTENTION_SCRIPTS" in NC and "'grp-ga4'" in NC,
   "C13 GA4 is declared, because a script-fed feed has no dropzone to find")
ok("GA4_SETTLE_DAYS" in nocomment(js[js.index("const UP_ATTENTION_SCRIPTS"):][:400]),
   "C14 ...and reads its tolerance from the shared settle rule, not a typed 2")
ok("renderUploadAttention()" in nocomment(fn("refreshUploadDataRanges", "async function")),
   "C15 the refresh runs it")
eq("C16 the strip's host element exists once", s.count('id="up-attention"'), 1)

m = re.search(r">v(\d+\.\d+) · [\d-]+<", s)
cl = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
cm = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cl)
eq("C17 /!\\ the version chip AGREES with CLAUDE.md",
   m.group(1) if m else None, cm.group(1) if cm else None)

# ---------------------------------------------------------------------------
print("\nD. the real functions, sliced and driven")
# ---------------------------------------------------------------------------
D = r"""
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}
const UH_SOURCES = {
  sku_economics:    { dateField: 'week_start', weekEndOffset: 5 },
  sku_economics_eu: { dateField: 'week_start', weekEndOffset: 5 },
  ga4_by_date:      { dateField: 'day' },
  walmart_ad_campaign: { dateField: 'reporting_month' },
};
__GRAIN__
__OFFSET__
__PEND__
__THRU__
__FRESH__
__AGE__
__VERDICT__
__WORST__

// Pinned, or this suite is a countdown (the v11.75 lesson).
const NOW = new Date('2026-11-09T12:00:00').getTime();

t('D1  a period that ended today is 0 days old', uploadAgeDays('2026-11-09', NOW), 0);
t('D2  ...and one a week back is 7', uploadAgeDays('2026-11-02', NOW), 7);
t('D3  junk is null, not a huge number', uploadAgeDays('202645', NOW), null);
t('D4  /!\\ and null, not 0 - a feed with no readable date is not fresh',
  uploadAgeDays('', NOW), null);

const skuUs = { grpId: 'grp-amz-sales', table: 'sku_economics', freshDays: 7, label: 'SKU Economics' };
const skuEu = { grpId: 'grp-amz-sales', table: 'sku_economics_eu', freshDays: 7, label: 'SKU Economics' };
const ga4   = { grpId: 'grp-ga4', table: 'ga4_by_date', freshDays: 2, label: 'GA4' };

t('D5  a current feed returns NOTHING - the strip names only what is late',
  upAttentionVerdict({ ...ga4 }, '2026-11-08', NOW), null);
t('D6  a late feed is named with its age',
  upAttentionVerdict({ ...ga4 }, '2026-11-06', NOW),
  { grpId: 'grp-ga4', label: 'GA4', state: 'late', age: 3, thru: '2026-11-06', freshDays: 2 });
t('D7  /!\\ a weekly feed is measured from its week END, not its start',
  upAttentionVerdict({ ...skuUs }, '2026-10-26', NOW).thru, '2026-10-31');
t('D8  nothing loaded at all says so',
  upAttentionVerdict({ ...skuUs }, null, NOW).state, 'never');
t('D9  ...and carries no age it cannot know',
  upAttentionVerdict({ ...skuUs }, null, NOW).age, null);
t('D10 an empty string counts as never, not as a date',
  upAttentionVerdict({ ...skuUs }, '', NOW).state, 'never');
t('D11 the verdict carries its OWN tolerance, so the tooltip cannot re-look it up',
  upAttentionVerdict({ ...ga4 }, '2026-11-06', NOW).freshDays, 2);

// One row, two tables - SKU Economics US/CA + EU.
const two = [
  upAttentionVerdict({ ...skuUs }, '2026-10-26', NOW),
  upAttentionVerdict({ ...skuEu }, '2026-10-19', NOW),
].filter(Boolean);
t('D12 both feeds really are late on their own', two.length, 2);
const one = upAttentionWorstPerRow(two);
t('D13 /!\\ ONE ROW, ONE CHIP', one.length, 1);
t('D14 /!\\ ...and the WORST of the two wins - a row is as behind as its worst feed',
  one[0].age, Math.max(two[0].age, two[1].age));

const mixed = upAttentionWorstPerRow([
  { grpId: 'g', state: 'late', age: 99 },
  { grpId: 'g', state: 'never', age: null },
]);
t('D15 /!\\ never beats late, however old the late one is',
  [mixed.length, mixed[0].state], [1, 'never']);
const mixed2 = upAttentionWorstPerRow([
  { grpId: 'g', state: 'never', age: null },
  { grpId: 'g', state: 'late', age: 99 },
]);
t('D16 ...in either order', mixed2[0].state, 'never');
t('D17 two different rows stay two chips',
  upAttentionWorstPerRow([{ grpId: 'a', state: 'late', age: 1 },
                          { grpId: 'b', state: 'late', age: 2 }]).length, 2);
t('D18 an empty list stays empty', upAttentionWorstPerRow([]), []);

console.log(JSON.stringify(out));
"""
D = (D.replace("__GRAIN__", fn("uploadGrain"))
      .replace("__OFFSET__", fn("uploadWeekEndOffset"))
      .replace("__PEND__", fn("uploadPeriodEnd"))
      .replace("__THRU__", fn("uploadDataThru"))
      .replace("__FRESH__", fn("uploadFreshDays"))
      .replace("__AGE__", fn("uploadAgeDays"))
      .replace("__VERDICT__", fn("upAttentionVerdict"))
      .replace("__WORST__", fn("upAttentionWorstPerRow")))
p = os.path.join(SP, "_v1181_d.js")
io.open(p, "w", encoding="utf-8", newline="").write(D)
r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
if r.returncode:
    print(r.stdout[-3000:]); print(r.stderr[-3000:]); raise SystemExit("node failed: " + p)
for c in json.loads(r.stdout.strip().splitlines()[-1]):
    ok(c["pass"], c["name"], None if c["pass"] else "%s want %s" % (c["got"], c["want"]))

# ---------------------------------------------------------------------------
print("\nE. the regression guard - what the browser run actually found")
# ---------------------------------------------------------------------------
# Four uploaders live on the Amazon P&L sub-views, NOT on the Uploads page.
# A strip that found groups by id alone reached all four, and its chips
# scrolled to a collapsed row on a tab nobody was looking at.
elsewhere = [g for g in re.findall(r'<div class="up-grp" id="(grp-[a-z0-9-]+)">', s)
             if g not in gids]
eq("E1  /!\\ four upload groups really do live off this page", len(elsewhere), 4)
ok("grp-amazon-ads-bulk" in elsewhere and "grp-amz-sp-campaign" in elsewhere,
   "E2  ...and they are the ones the browser run surfaced", elsewhere)

# Those four are registered dropzones, so a page-blind strip WOULD reach them.
dz_block = js[js.index("const DZ_RECENT_SOURCES = {"):]
dz_block = dz_block[:dz_block.index("};") + 2]
reg = set(re.findall(r"'(dz-[a-z0-9-]+)'\s*:", dz_block))
ok("dz-amazon-ads-bulk" in reg,
   "E3  /!\\ the off-page group IS in the registry - the scope check is load-bearing")

# And two groups really do feed from two tables each.
pairs = {}
for dzId in reg:
    m = re.search(r"'%s'\s*:\s*'([a-z0-9_]+)'" % dzId, dz_block)
    if not m:
        continue
    hit = re.search(r'id="%s"' % dzId, VIEW)
    if not hit:
        continue
    pre = VIEW[:hit.start()]
    g = re.findall(r'<div class="up-grp" id="(grp-[a-z0-9-]+)">', pre)
    if g:
        pairs.setdefault(g[-1], set()).add(m.group(1))
multi = {g: sorted(t) for g, t in pairs.items() if len(t) > 1}
ok(len(multi) >= 2,
   "E4  /!\\ at least two rows really do feed from two tables - the dedupe is "
   "load-bearing too", multi)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
