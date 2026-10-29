# -*- coding: utf-8 -*-
"""v11.21 - Growth Model and both ad uploaders become areas of the Ads tab.

Jason: "3. the growth model should be a sub-tab of the ads page for amazon p&L
(and other p&L pages). 4. the uploads for the growth model should be moved to
an uploads sub-page tab within ads tab."

The assertions that earn their keep:

  * B1 EVERY AREA'S URL ROUND-TRIPS. Each area writes a name, and that name
    must restore that area. '/ads' shipped briefly meaning "whatever area you
    were last on", so a link saying /ads could land you on Uploads - the
    address bar describing a page nobody could navigate back to. v7.94's whole
    point is that a link restores the exact view.

  * C1 ONE AREA REGISTRY. The strip and the show/hide are driven from the same
    map, so a fifth area is one row rather than a pair of hand-written lines
    that can drift apart.

  * D1 THE UPLOADERS ARE WIRED WHERE THEY NOW LIVE, and nowhere else. Both
    cards moved into one area, so exactly one surface may wire them - two
    would be two places doing the same job, which is how v10.88's wiring got
    missed in the first place.
"""
import io, os, re, sys

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name, got=None):
    global passed, failed
    if cond: passed += 1; print('  ok    ' + name)
    else:    failed += 1; print('  FAIL  %s%s' % (name, '' if got is None else '  got: ' + ascii(got)))

def eq(name, got, want):
    ok(got == want, name, None if got == want else got)

def fnbody(name):
    i = js.index('function %s(' % name)
    j = js.index('{', js.index(')', i))
    d, k = 0, j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k + 1]
        k += 1


print('\n== A. the strips ==')
ok('id="pnl-amzn-tab-growth"' not in s,
   'A1  Growth Model is GONE from the Amazon strip - deleted, not hidden')
for a in ['campaigns', 'growth', 'activity', 'uploads']:
    ok('id="pnl-amzn-ads-tab-%s"' % a in s, 'A2  the Ads strip has %s' % a)
amz_tabs = re.findall(r'id="pnl-amzn-tab-([a-z]+)"', s)
eq('A3  the Amazon strip is down to seven', len(set(amz_tabs)), 7)

print('\n== B. the URL round-trips ==')
rt = fnbody('pnlAmazonRouteView')
sw = fnbody('switchPnlAmazonView')
WRITES = {'activity': 'adactivity', 'growth': 'growth', 'uploads': 'adsuploads'}
for area, name in WRITES.items():
    ok("pnlAdsView === '%s') return '%s'" % (area, name) in rt,
       'B1a the %s area writes /%s' % (area, name))
    ok("view === '%s'" % name in sw,
       'B1b and switchPnlAmazonView accepts /%s back' % name)
ok("else if (view === 'ads')   { _adsArea = 'campaigns'; }" in sw,
   'B1c /ads restores CAMPAIGNS - the one area that writes it. A sticky '
   '"last area" here made the URL non-reversible')
router = js[js.index("if (page === 'pnl' && sub === 'amazon')"):][:900]
for name in ['growth', 'adsuploads', 'adactivity', 'ads']:
    ok("'%s'" % name in router, 'B2  the router lands on /%s' % name)

print('\n== C. one area registry ==')
ads = fnbody('switchPnlAdsView')
ok('const AREAS = {' in ads, 'C1a the areas are a registry, not hand-written lines')
areas = dict(re.findall(r"(\w+):\s*'([\w-]+)'", ads[ads.index('const AREAS'):ads.index('};', ads.index('const AREAS'))]))
eq('C1b naming all four panels', sorted(areas), ['activity', 'campaigns', 'growth', 'uploads'])
for k, v in areas.items():
    ok('id="%s"' % v in s, 'C1c %s -> %s is a real element' % (k, v))
ok("Object.entries(AREAS)" in ads,
   'C2  and the show/hide walks it, so the strip and the panels cannot drift')
ok("includes(view)) view = 'campaigns'" in ads,
   'C3  an unknown area falls back to Campaigns rather than showing nothing')

print('\n== D. the uploaders ==')
wrap = s[s.index('<div id="pnl-amzn-ads-view-uploads"'):]
wrap = wrap[:wrap.index('<!-- /pnl-amzn-ads-view-uploads -->')]
for gid in ['grp-amz-sqp-asin', 'grp-amz-sqp-brand', 'grp-amz-sp-campaign', 'grp-amazon-ads-bulk']:
    ok('id="%s"' % gid in wrap, 'D1a %s lives in the Uploads area' % gid)
eq('D1b both upload sections moved, not just one',
   wrap.count('class="up-section"'), 2)
ok(wrap.count('<div') - wrap.count('</div>') == 0,
   'D1c and the area opens and closes cleanly',
   wrap.count('<div') - wrap.count('</div>'))
WIRES = ['initUploadDropTargets', 'renderAllDzRecentUploads', 'refreshUploadDataRanges']
up = re.search(r"view === 'uploads'\) \{(.*?)\n  \} else", ads, re.S)
ok(bool(up), 'D2a the Uploads area has an entry hook')
for fn in WIRES:
    ok(fn in (up.group(1) if up else ''), 'D2b it calls ' + fn)
for fn in WIRES:
    eq('D3  the parent switch no longer wires %s - exactly one surface does' % fn,
       sw.count(fn), 0)
# the growth panel kept its own init, which is not uploader wiring
ok('pnlGrowthInit' in ads, 'D4  the Growth Model area still initialises on entry')
ok('pnlGrowthInit' not in sw, 'D4b and only from there')

print('\n== E. the chips follow their cards ==')
m = re.search(r'const\s+PNL_HOSTED_UPLOAD_GROUPS\s*=\s*\{(.*?)\};', js, re.S)
hosted = dict(re.findall(r"'([\w-]+)'\s*:\s*'(\w+)'", m.group(1) if m else ''))
eq('E1  all four ad uploaders route to the Uploads area',
   sorted(k for k, v in hosted.items() if v == 'adsuploads'),
   ['grp-amazon-ads-bulk', 'grp-amz-sp-campaign', 'grp-amz-sqp-asin', 'grp-amz-sqp-brand'])
ok(all(v != 'growth' for v in hosted.values()),
   'E2  and none still points at the Growth Model, which no longer hosts a card',
   hosted)

print('\n' + '-' * 58)
print('v11.21: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
