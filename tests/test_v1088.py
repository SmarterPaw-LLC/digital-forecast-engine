# -*- coding: utf-8 -*-
r"""v10.88 - an uploader that moves must take its wiring with it.

Jason: "these are the two amazon ads reports i upload weekly. the other
uploads should be moved to the respective P&L pages."

That is the v10.39 rule running in the other direction - CADENCE decides
where an uploader lives, not which page consumes it. Weekly scheduled
reports stay on Data -> Uploads; occasional ones move next to what reads
them. So three Amazon Ads cards moved onto the Amazon P&L sub-view that
consumes each, and two stayed put.

Relocating an upload card is NOT just moving markup. Four things are wired
to the Uploads page by assumption, and each fails SILENTLY if left behind:

  - drag-and-drop  : initUploadDropTargets only walked '#data-view-uploads .dz'
                     (the v10.16 lesson, learned when the Chewy rebate card
                     moved and lost its drop handling)
  - data-currency  : openUploadGroupForTable navigates to Uploads and expands
    chips            a group id - pointing at a relocated group would navigate
                     and expand nothing (the v10.16 dangling-chip bug)
  - recent-uploads : the v10.85 rail renders from switchDataView('uploads')
    rail
  - freshness      : refreshUploadDataRanges fires on the Uploads view

This suite pins the placement AND all four wirings.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond:
        P += 1; print('  ok  ' + label)
    else:
        F += 1; fails.append(label)
        print('  FAIL ' + label + (('  -> ' + str(got)) if got is not None else ''))


def markup_only(html):
    return re.sub(r'(<(script|style)\b[^>]*>)(.*?)(</\2>)',
                  lambda m: m.group(1) + ' ' * len(m.group(3)) + m.group(4),
                  html, flags=re.S | re.I)


def script_body(html):
    return max(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S), key=len)


MARKUP = markup_only(RAW)
JS = script_body(RAW)


def slice_div(html, anchor):
    """Tag-balanced slice of the <div> carrying `anchor`."""
    i = html.index(anchor)
    start = html.rindex('<div', 0, i + len(anchor))
    depth = 0
    for m in re.finditer(r'<div\b|</div>', html[start:]):
        depth += 1 if m.group(0) != '</div>' else -1
        if depth == 0:
            return start, start + m.end()
    raise AssertionError('unbalanced: ' + anchor)


# v11.21 - all four ad uploaders now live in ONE place, the Ads tab's Uploads
# area. They used to be split between the Growth Model panel and the Ad
# Activity panel, each hosting the report it happened to consume; collecting
# them means there is one surface to wire and one place to drop a file.
MOVED = {
    'grp-amazon-ads-bulk': 'pnl-amzn-ads-view-uploads',
    'grp-amz-sqp-asin':    'pnl-amzn-ads-view-uploads',
    # v10.89 - SQP is one card per view (ASIN / Brand); both moved together.
    'grp-amz-sqp-brand':   'pnl-amzn-ads-view-uploads',
    'grp-amz-sp-campaign': 'pnl-amzn-ads-view-uploads',
}
STAYED = ['grp-amazon-ads', 'grp-amz-sp-search-term']


# ── A. Placement ───────────────────────────────────────────────────────────
print('\nA. each uploader sits where its cadence says it should')

up_s, up_e = slice_div(MARKUP, 'id="data-view-uploads"')
UPLOADS = MARKUP[up_s:up_e]

# v11.21 - MOVED hard-coded which panel hosts each card. Both ad uploaders
# then moved into the Ads tab's Uploads area and this went red on a rule that
# still held. The hosting panel is now resolved through
# PNL_HOSTED_UPLOAD_GROUPS -> AREA_WRAP, so the registry and the markup cannot
# drift apart silently, which is a stronger claim than the literal was.
AREA_WRAP = {
    'growth':     'pnl-amzn-growth-wrap',
    'adactivity': 'pnl-amzn-adactivity-wrap',
    'adsuploads': 'pnl-amzn-ads-view-uploads',
}
import re as _re
_m = _re.search(r'const\s+PNL_HOSTED_UPLOAD_GROUPS\s*=\s*\{(.*?)\};', JS, _re.S)
_hosted = dict(_re.findall(r"'([\w-]+)'\s*:\s*'(\w+)'", _m.group(1) if _m else ''))
ok(len(_hosted) >= 4, 'the hosted-group registry was really found', _hosted)
for gid in MOVED:
    area = _hosted.get(gid)
    ok(area in AREA_WRAP, gid + ' routes to a known Ads area', area)
    wrap = AREA_WRAP.get(area)
    if not wrap:
        continue
    w_s, w_e = slice_div(MARKUP, 'id="' + wrap + '"')
    host = MARKUP[w_s:w_e]
    ok('id="' + gid + '"' in host, gid + ' lives inside ' + wrap)
    ok('id="' + gid + '"' not in UPLOADS, gid + ' no longer on the Uploads page')

for gid in STAYED:
    ok('id="' + gid + '"' in UPLOADS, gid + ' (weekly) stayed on the Uploads page')

# exactly one definition each - a move must not leave a copy behind
for gid in list(MOVED) + STAYED:
    ok(MARKUP.count('id="' + gid + '"') == 1,
       gid + ' is defined exactly once', MARKUP.count('id="' + gid + '"'))


# ── B. The card survived the move intact ───────────────────────────────────
print('\nB. moved cards kept their file input and handler')

DZ_FOR = {'grp-amazon-ads-bulk': 'dz-amazon-ads-bulk',
          'grp-amz-sqp-asin':    'dz-amz-sqp-asin',
          'grp-amz-sp-campaign': 'dz-amz-sp-campaign'}

for gid, dzid in DZ_FOR.items():
    g_s, g_e = slice_div(MARKUP, 'id="' + gid + '"')
    blk = MARKUP[g_s:g_e]
    ok('id="' + dzid + '"' in blk, dzid + ' moved with its group')
    m = re.search(r'<input[^>]*type="file"[^>]*>', blk)
    ok(bool(m), dzid + ' kept its file input')
    ok(bool(m) and 'onchange=' in m.group(0), dzid + ' kept its onchange handler')
    ok('class="dz-st"' in blk, dzid + ' kept its status line')
    ok(blk.count('<div') == blk.count('</div>'), gid + ' block is tag-balanced')


# ── C. Drag-and-drop is no longer Uploads-only ─────────────────────────────
print('\nC. drag-and-drop follows the card (the v10.16 lesson)')

ok("querySelectorAll('#data-view-uploads .dz')" not in JS,
   'initUploadDropTargets is NOT scoped to the Uploads page')
ok("document.querySelectorAll('.dz')" in JS,
   'it sweeps every .dz wherever it lives')
ok("dz.dataset.ddWired === '1'" in JS,
   'wiring stays idempotent, so repeated calls are safe')


# ── D. Data-currency chips route to the new host ───────────────────────────
print('\nD. chips land on the page that now hosts the uploader')

m = re.search(r'const\s+PNL_HOSTED_UPLOAD_GROUPS\s*=\s*\{(.*?)\};', JS, re.S)
ok(bool(m), 'PNL_HOSTED_UPLOAD_GROUPS declared')
hosted = dict(re.findall(r"'([\w-]+)'\s*:\s*'(\w+)'", m.group(1) if m else ''))
ok(set(hosted) == set(MOVED), 'it lists exactly the moved groups', sorted(hosted))

# Every target must be a real sub-view, or the chip navigates nowhere.
sv = re.search(r"if \(!\[([^\]]*)\]\.includes\(view\)\) return;", JS)
views = set(re.findall(r"'(\w+)'", sv.group(1))) if sv else set()
ok(bool(views), 'switchPnlAmazonView whitelist parsed', sorted(views))
bad = sorted(v for v in hosted.values() if v not in views)
ok(not bad, 'every host target is a real Amazon P&L sub-view', bad)

# And the group must actually exist inside that sub-view's wrapper.
# v11.21 - MOVED used to map a group to a wrapper id whose NAME contained the
# chip's target ('growth' inside 'pnl-amzn-growth-wrap'). That substring trick
# broke when the target became 'adsuploads' for a wrapper called
# pnl-amzn-ads-view-uploads. Resolve through AREA_WRAP instead, which is an
# explicit mapping rather than a coincidence of naming.
mismatch = [g for g, v in hosted.items()
            if AREA_WRAP.get(v) and MOVED.get(g) != AREA_WRAP[v]]
ok(not mismatch, 'each chip target matches where the group really is', mismatch)

ok('PNL_HOSTED_UPLOAD_GROUPS[groupId]' in JS,
   'openUploadGroupForTable consults the host map')
ok("switchPnlAmazonView(pnlView_)" in JS, 'it switches to the hosting sub-view')

# Tables that stayed must still route to Data -> Uploads.
tmap = re.search(r'const\s+TABLE_TO_UPLOAD_GROUP\s*=\s*\{(.*?)\};', JS, re.S)
tbl = dict(re.findall(r"(\w+)\s*:\s*'([\w-]+)'", tmap.group(1) if tmap else ''))
ok(tbl.get('amazon_ad_spend') == 'grp-amazon-ads',
   'Unified Report still routes to Uploads')
ok(tbl.get('amazon_sp_search_term') == 'grp-amz-sp-search-term',
   'SP Search Term still routes to Uploads')
for t in ['amazon_ads_bulk_upload', 'amazon_ads_bulk_snapshot',
          'amazon_query_performance_asin', 'amazon_sp_campaign_snapshot']:
    ok(tbl.get(t) in hosted, t + ' routes to a P&L-hosted group', tbl.get(t))


# ── E. The host sub-views wire what the Uploads page used to ───────────────
print('\nE. host sub-views set up their uploaders on entry')

# v11.17 - this PINNED THE MECHANISM while its own heading claimed a
# GUARANTEE. It required one particular `if (view === 'growth' || view ===
# 'adactivity')` to exist. When Ad Activity became an AREA of the Ads tab,
# its wiring moved into switchPnlAdsView: same guarantee, different branch.
#
# Re-pointed to assert EACH hosting surface wires all three on entry,
# independently of whether they happen to share a branch. Stronger: two
# hosts sharing one `if` was never the thing that mattered, and a third host
# added later with a branch of its own now has to satisfy this too.
WIRES = ['initUploadDropTargets', 'renderAllDzRecentUploads', 'refreshUploadDataRanges']


def _fnbody(name):
    i = JS.index('function %s(' % name)
    j = JS.index('{', i)
    d = 0
    k = j
    while True:
        if JS[k] == '{':
            d += 1
        elif JS[k] == '}':
            d -= 1
            if d == 0:
                return JS[i:k + 1]
        k += 1


# v11.21 - BOTH ad uploaders now live in ONE place, the Ads tab's Uploads
# area, so there is one hosting surface to wire rather than two. This used to
# check the Growth Model branch of switchPnlAmazonView and the Ad Activity
# branch of switchPnlAdsView; neither hosts an uploader any more.
#
# The guarantee is unchanged and is asserted where hosting now happens.
_sw = _fnbody('switchPnlAmazonView')
_ads = _fnbody('switchPnlAdsView')
ok(len(_ads) > 400, 'the Ads switcher body was really found', len(_ads))
_up = re.search(r"view === 'uploads'\) \{(.*?)\n  \} else", _ads, re.S)
ok(bool(_up), 'the Uploads area has an entry hook')
for fn in WIRES:
    ok(fn in (_up.group(1) if _up else ''),
       'Uploads entry hook calls ' + fn)
ok("renderPnlAdActivity" in _ads,
   'and the Ad Activity area still renders its timeline on entry')
ok("pnlGrowthInit" in _ads,
   'and the Growth Model area still initialises on entry')
# Nothing is left wiring uploaders from the parent switch, which would be a
# second place doing the same job.
for fn in WIRES:
    ok(_sw.count(fn) == 0,
       'the parent sub-view switch no longer wires ' + fn, _sw.count(fn))
# Guard the guard: a typo in either slice would make every check above pass
# vacuously against an empty haystack.
ok(len(_ads) > 200 and len(_sw) > 500,
   'both function bodies were really found', (len(_ads), len(_sw)))


# ── F. The reveal cannot depend on rAF alone ───────────────────────────────
print('\nF. chip reveal survives a throttled tab')

# rAF is throttled to nothing in a background / non-compositing tab, which
# would navigate and then silently never expand the group. Found while
# driving this: rAF did not fire in the harness at all.
rv = re.search(r'function openUploadGroupForTable.*?\n\}', JS, re.S)
body = rv.group(0) if rv else ''
ok(bool(body), 'openUploadGroupForTable located')
ok('requestAnimationFrame' in body, 'still prefers rAF when frames are running')
ok('setTimeout(_reveal' in body, 'has a timeout fallback when they are not')
ok('if (_opened) return;' in body, 'fallback is idempotent (cannot double-run)')


# ── G. Nothing was orphaned on the way out ─────────────────────────────────
print('\nG. the Uploads page is still well-formed')

ok(UPLOADS.count('<div') == UPLOADS.count('</div>'),
   'uploads view is tag-balanced after the cuts')

# No section left with a header and no cards under it.
# NB: slice from the match OFFSET, not by searching for its text - every
# .up-section opening tag is byte-identical, so a text search re-slices the
# first one on every iteration (the v10.53 wrong-haystack class, in a test).
def slice_div_at(html, start):
    depth = 0
    for m in re.finditer(r'<div\b|</div>', html[start:]):
        depth += 1 if m.group(0) != '</div>' else -1
        if depth == 0:
            return start, start + m.end()
    raise AssertionError('unbalanced at offset ' + str(start))

seen = 0
for sm in re.finditer(r'<div class="up-section"[^>]*>', UPLOADS):
    a, b = slice_div_at(UPLOADS, sm.start())
    sec = UPLOADS[a:b]
    seen += 1
    if 'up-section-hdr' in sec:
        hdr = re.sub(r'<[^>]+>', ' ', sec[:400])
        hdr = re.sub(r'\s+', ' ', hdr).strip()[:40]
        ok('class="up-grp"' in sec, 'section has cards: ' + hdr)

ok(seen >= 3, 'walked every upload section', seen)

ok(len(re.findall(r'class="up-grp"', UPLOADS)) >= 14,
   'the Uploads page still carries its remaining groups',
   len(re.findall(r'class="up-grp"', UPLOADS)))


print('\n' + '=' * 62)
print(f'  v10.88  PASS {P}   FAIL {F}')
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
