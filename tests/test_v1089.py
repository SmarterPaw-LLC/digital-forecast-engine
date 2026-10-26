# -*- coding: utf-8 -*-
r"""v10.89 - two uploaders share one table, so freshness must be PER VIEW.

Jason: "shouldn't asin and brand be separated? i have to pull them
separately, and it's hard to tell which reports are current"

Search Query Performance has two views - ASIN (one CSV per listing) and
Brand (one CSV per brand) - pulled separately from Seller Central but
landing in ONE table, amazon_query_performance_asin, behind a view_type
discriminator.

The card showed ONE freshness line, taken from the newest reporting_month
across BOTH views. That is not cosmetic:

    the Growth Model reads view_type === 'asin' in eight places,

so a fresh Brand pull MASKED a stale ASIN pull and the model silently ran
on old inputs while the card read current. Same for the v10.85 rail, which
merged both views' sessions into one undifferentiated list.

Split into two cards. The durable rule this encodes: when two uploaders
share a table, every surface that reports freshness or history must scope
to the discriminator, or one upload masks the other's staleness.
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


# ── A. Two cards, one per view ─────────────────────────────────────────────
print('\nA. the SQP uploader is split by view')

for gid in ['grp-amz-sqp-asin', 'grp-amz-sqp-brand']:
    ok(MARKUP.count('id="' + gid + '"') == 1, gid + ' exists exactly once')
for dzid in ['dz-amz-sqp-asin', 'dz-amz-sqp-brand']:
    ok(MARKUP.count('id="' + dzid + '"') == 1, dzid + ' exists exactly once')

# Each card must pass its OWN view to the shared handler, or the status +
# freshness lines write to the wrong card.
for fid, view in [('f-amz-sqp-asin', 'asin'), ('f-amz-sqp-brand', 'brand')]:
    m = re.search(r'id="' + fid + r'"[^>]*onchange="([^"]+)"', MARKUP)
    ok(bool(m), fid + ' has an onchange handler')
    ok(bool(m) and ("'" + view + "'") in m.group(1),
       fid + " passes view '" + view + "'", m.group(1) if m else None)

# The old combined title must be gone - it is what made the card ambiguous.
ok('(ASIN + Brand view)' not in MARKUP,
   'the ambiguous combined card title is gone')


# ── B. Freshness is probed per view ────────────────────────────────────────
print('\nB. a fresh Brand pull cannot mask a stale ASIN pull')

m = re.search(r'async function refreshUploadDataRanges\b', JS)
probe = JS[m.start():m.start() + 60000] if m else ''
ok(bool(probe), 'refreshUploadDataRanges located')

sqp = re.search(r"for \(const \[vt, cardId, grpId, human\] of \[(.*?)\]\)", probe, re.S)
ok(bool(sqp), 'SQP probe loops over the two views')
views = re.findall(r"\['(\w+)',", sqp.group(1) if sqp else '')
ok(set(views) == {'asin', 'brand'}, 'it probes both views', views)

ok(".eq('view_type', vt)" in probe,
   'each probe filters on view_type (the whole point)')

# Both cards AND both group slots must be named.
for slot in ['last-amz-sqp-asin', 'last-amz-sqp-brand',
             'last-amz-sqp-asin-grp', 'last-amz-sqp-brand-grp']:
    ok("'" + slot + "'" in probe, slot + ' is written by the probe')

# Regression guard: the single unfiltered probe must not come back.
old = re.findall(r"from\('amazon_query_performance_asin'\)\s*\n?\s*\.select\('reporting_month, uploaded_at'\)\s*\n?\s*\.order", probe)
ok(not old, 'no unfiltered newest-month probe survives', old)


# ── C. The rail scopes to its own view ─────────────────────────────────────
print('\nC. each rail shows only its own view history')

dz = re.search(r'const\s+DZ_RECENT_SOURCES\s*=\s*\{(.*?)\n\};', JS, re.S)
ok(bool(dz), 'DZ_RECENT_SOURCES located')
blk = dz.group(1) if dz else ''

for dzid, vt in [('dz-amz-sqp-asin', 'asin'), ('dz-amz-sqp-brand', 'brand')]:
    m2 = re.search(r"'" + dzid + r"'\s*:\s*\{([^}]*\}[^}]*)\}", blk)
    ok(bool(m2), dzid + ' maps to a filtered source')
    body = m2.group(1) if m2 else ''
    ok("table: 'amazon_query_performance_asin'" in body, dzid + ' points at the shared table')
    ok("view_type: '" + vt + "'" in body, dzid + " filters view_type='" + vt + "'")

ok('function dzSourceKey(' in JS, 'sources hash to a cache key')
ok("'|'" in JS and 'dzSourceKey' in JS, 'the key includes the filter')
# Two views of one table MUST NOT share a cache entry.
ok('_dzRecentCache[ckey]' in JS, 'the cache is keyed by source, not by table')
ok('_dzRecentCache[table]' not in JS, 'no table-keyed cache write survives')
ok("k.startsWith(table + '|')" in JS,
   'invalidating a table clears every filtered variant of it')
ok('q = q.eq(col, val)' in JS, 'the filter is applied to the query itself')


# ── D. A file dropped on the wrong card is flagged, never lost ─────────────
print('\nD. a misdrop is surfaced, not silently mis-filed')

h = re.search(r'async function handleAmazonSqpAsinUpload.*?\n\}', JS, re.S)
body = h.group(0) if h else ''
ok(bool(body), 'handler located')
ok('expectView' in body, 'the handler knows which card it was dropped on')
ok('result.viewType !== expectView' in body, 'it compares detected vs expected view')
ok('misdropped.push' in body, 'a mismatch is recorded')
ok("'dz-warn'" in body, 'and surfaced as a warning, not an error')
# The parser auto-detects, so the row still lands under the RIGHT view.
ok('throw' not in body.split('misdropped.push')[1].split('\n')[0],
   'a misdrop does not abort the upload (data still stores correctly)')

# After an upload both cards must refresh, or the other view looks stale.
ok("dzRecentInvalidate('amazon_query_performance_asin')" in body,
   'upload invalidates both views\' rails')
ok('refreshUploadDataRanges' in body, 'upload refreshes both freshness lines')


# ── E. Both cards reachable from a data-currency chip ──────────────────────
print('\nE. chips still land on a real host')

m3 = re.search(r'const\s+PNL_HOSTED_UPLOAD_GROUPS\s*=\s*\{(.*?)\};', JS, re.S)
hosted = dict(re.findall(r"'([\w-]+)'\s*:\s*'(\w+)'", m3.group(1) if m3 else ''))
for gid in ['grp-amz-sqp-asin', 'grp-amz-sqp-brand']:
    ok(hosted.get(gid) == 'growth', gid + ' routes to the Growth Model', hosted.get(gid))

# Both must physically live in that wrapper.
w = re.search(r'<div id="pnl-amzn-growth-wrap"[^>]*>', MARKUP)
ok(bool(w), 'growth wrapper located')
start = w.end() if w else 0
depth, end = 0, len(MARKUP)
for mm in re.finditer(r'<div\b|</div>', MARKUP[w.start():]):
    depth += 1 if mm.group(0) != '</div>' else -1
    if depth == 0:
        end = w.start() + mm.end(); break
host = MARKUP[w.start():end]
for gid in ['grp-amz-sqp-asin', 'grp-amz-sqp-brand', 'grp-amz-sp-campaign']:
    ok('id="' + gid + '"' in host, gid + ' really sits inside the Growth Model')


print('\n' + '=' * 62)
print(f'  v10.89  PASS {P}   FAIL {F}')
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
