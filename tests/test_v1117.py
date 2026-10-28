# -*- coding: utf-8 -*-
"""v11.17 - the period bar drives the Ads tab, and Ad Activity moves under it.

Jason, two things:
  1. "using the period filters on the ads tab does not filter anything. why is
     the reporting window locked to the range?"
  2. "ads activity tab on amazon p&L should be a sub area of the ads tab"

(1) was a real bug of mine. v11.16 painted the Ads panel ONLY on tab entry, so
the control repainted and the numbers under it did not - the page reported a
window nobody had selected.

The assertions that earn their keep:

  * A1 THE REGRESSION GUARD. Every Amazon filter funnels through renderPnl, so
    the guard asserts the hook lives THERE and not on one control - six hooks
    would be six chances to miss one. It also proves the pre-v11.17 shape
    really did leave the Ads branch out of the sync block that already existed
    for Opportunities.

  * B4 THE URL VOCABULARY DID NOT CHANGE. #pnl/amazon/adactivity has been a
    real link since v7.94 and data-currency chips still route to it. Moving a
    tab must not break a bookmark someone already has, so the name survives in
    BOTH directions: switchPnlAmazonView accepts it, pnlAmazonRouteView writes
    it back out.
"""
import io, os, re, sys

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name, got=None):
    global passed, failed
    if cond: passed += 1; print('  ok    ' + name)
    else:    failed += 1; print('  FAIL  %s%s' % (name, '' if got is None else '  got: %r' % (got,)))

def eq(name, got, want):
    ok(got == want, name, None if got == want else got)

def fnbody(name, kw='function'):
    i = js.index('%s %s(' % (kw, name))
    j = js.index('{', js.index(')', i))
    d, k = 0, j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k + 1]
        k += 1


print('\n== A. the filter bar actually drives the Ads tab ==')
rp = fnbody('renderPnl')
ok(len(rp) > 2000, 'A0  renderPnl body was really found', len(rp))
ok("pnlAmazonView === 'ads'" in rp and "renderAdsCampaigns('amazon')" in rp,
   'A1a renderPnl repaints the Ads tab on a filter change')
# ⚠ THE ASSERTION THAT EARNS ITS KEEP. renderPnl EARLY-RETURNS when
# sku_economics has no rows for the region. My first fix put the Ads repaint at
# the tail beside the v8.84 Opportunities block, where it never ran in that
# case. Opportunities belongs there - it is BUILT FROM the aggregates renderPnl
# computes, so it is meaningless without them. The Ads tab is not: it reads
# amazon_ad_spend and resolves its own window, and ad spend with no SKU
# Economics in the same window is an ordinary state (a backfilled ad pull, a
# region whose economics upload is a week behind). In every one of those the
# period control would have gone dead on the Ads tab with nothing to explain it.
_early = rp.index('No SKU Economics data loaded for')
ok(rp.index("renderAdsCampaigns('amazon')") < _early,
   'A1b the Ads sync runs ABOVE the empty-data early return, so the period '
   'control still drives the tab when sku_economics is empty for the region')
ok(rp.index("renderPnlOpportunities();") > _early,
   'A1c while Opportunities correctly stays below it - it is built from '
   'aggregates that do not exist in that branch')
# EVERY Amazon filter routes through renderPnl, so one hook covers all of them.
for ctl in ['id="pnl-from" onchange="renderPnl()"',
            'id="pnl-to" onchange="renderPnl()"',
            'id="pnl-brand" onchange="renderPnl()"',
            'id="pnl-cat" onchange="renderPnl()"']:
    ok(ctl in s, 'A2  %s funnels through renderPnl' % ctl.split('"')[1])
ok('onPnlPeriodChange' in s and 'renderPnl()' in fnbody('onPnlPeriodChange'),
   'A2  the period control funnels through renderPnl')
ok('renderPnl()' in fnbody('setPnlRegion'), 'A2  and so does the region control')
# The hook is NOT duplicated onto individual controls.
ok(s.count("renderAdsCampaigns('amazon')") <= 3,
   'A3  the repaint is hooked at the chokepoint, not copied onto each control',
   s.count("renderAdsCampaigns('amazon')"))
ok("if (typeof renderAdsCampaigns === 'function')" in rp
   or "typeof renderAdsCampaigns === 'function'" in rp,
   'A4  guarded, so a throw there cannot break renderPnl')

print('\n== B. Ad Activity is an area of the Ads tab ==')
ok('id="pnl-amzn-tab-adactivity"' not in s,
   'B1  the top-level Ad Activity button is GONE, not hidden - a hidden .subtab '
   'still counts in the census and still shows in the visibility panel')
ok('id="pnl-amzn-ads-tab-campaigns"' in s and 'id="pnl-amzn-ads-tab-activity"' in s,
   'B2  the Ads tab has a nested strip')
ok(js.count('function switchPnlAdsView(') == 1, 'B3  with ONE switcher')
sw = fnbody('switchPnlAdsView')
ok('subtabApply' in sw,
   'B3a routed through the SHARED sub-tab chokepoint, not a bespoke painter')
rt = fnbody('pnlAmazonRouteView')
ok("return 'adactivity'" in rt,
   'B4a the Ad Activity area still WRITES #pnl/amazon/adactivity')
amz = fnbody('switchPnlAmazonView')
ok("view === 'adactivity'" in amz and "view = 'ads'" in amz,
   'B4b and switchPnlAmazonView still ACCEPTS it, so existing links land')
ok("'adactivity'" in js[js.index("if (page === 'pnl' && sub === 'amazon')"):][:900],
   'B4c the router still lists it as a landable sub-view')
ok('pnlAmazonRouteView' in fnbody('pnlUpdateRoute'),
   'B4d and the URL writer reads the route NAME, not the raw view')
ok("'grp-amazon-ads-bulk': 'adactivity'" in js,
   'B5  the Bulk Sheet data-currency chip still resolves')

print('\n== C. the panel really is nested ==')
wrap = s[s.index('<div id="pnl-amzn-ads-wrap"'):]
wrap = wrap[:wrap.index('<!-- /pnl-amzn-ads-wrap -->')]
ok('id="pnl-amzn-ads-view-campaigns"' in wrap, 'C1  the campaigns area is inside the Ads wrap')
ok('id="amzads-host"' in wrap,                 'C2  with the shared host')
ok('id="pnl-amzn-adactivity-wrap"' in wrap,    'C3  and so is the Ad Activity panel')
ok('data-pnl-uploads="adactivity"' in wrap,
   'C4  including the Bulk Sheet uploader it hosts')
# Balance within the lifted block. The slice runs to the wrap's own end
# COMMENT, so it takes the closing tag with it and a balanced wrap reads 0.
# (My first expectation said 1, forgetting the slice includes that close - the
# code was right.) Anchoring on the end comment rather than counting tags from
# the opening one is the v11.12 rule: a naive count cannot tell code from the
# commentary this file is full of.
eq('C5  the Ads wrap opens and closes cleanly around BOTH areas',
   wrap.count('<div') - wrap.count('</div>'), 0)
ok("aaWrap" not in amz,
   'C6  the parent switch no longer shows/hides the activity panel - exactly '
   'one surface owns that now')

print('\n== D. the glyph rule ==')
strip = s[s.index('id="pnl-amzn-ads-tab-campaigns"'):]
strip = strip[:strip.index('</div>')]
camp = re.search(r'>([^<]*)</button>', strip).group(1).strip()
ok(camp.endswith('Campaigns'), 'D1  the first area is labelled Campaigns', camp)
glyph = camp.split(' ')[0]
# One concept, one glyph: this one must not already be a tab glyph elsewhere.
others = re.findall(r'class="subtab[^"]*"[^>]*>([^<]*)</button>', s)
clash = [o.strip() for o in others
         if o.strip().startswith(glyph) and not o.strip().endswith('Campaigns')]
eq('D2  its glyph is not already carrying another tab label (rule #2)', clash, [])
acts = [o.strip() for o in others if o.strip().endswith('Ad Activity')]
eq('D3  Ad Activity keeps its established glyph', acts, ['\U0001f6e0 Ad Activity'])

print('\n' + '-' * 58)
print('v11.17: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
