# -*- coding: utf-8 -*-
"""v11.19 - two leftovers on the Amazon P&L control bar.

Jason: "1. AD HR target - what is this for? if it is for the growth model, it
should live on that tab only. 2. the search is leftover from when we migrated
search up to the top of the page, i think."

(2) exactly right: hideLocalSearchDuplicates hid the INPUT and left its label
and decorative magnifier on the bar, which read "SEARCH (magnifier) QUICK".
(1) right instinct, different tab: Ad HR target drives the Ad Headroom column
on Summary (opt-in) and on Page Performance - and it was ALREADY duplicated in
the View popup, so the bar copy went rather than a third home appearing.

The assertions that earn their keep:

  * C2 THE SET IS READ, NOT CALLED. The first version of the widened
    condition shipped as `typeof pnlVisibleCols === 'function' &&
    pnlVisibleCols()`. pnlVisibleCols is a Set, so that clause was dead and
    the control never appeared on Summary - the exact case it was widened
    for. The suite was green throughout, because nothing named that branch.
    It is named here.

  * A2 THE GROUP IS HIDDEN, NOT THE INPUT. Asserted on the mechanism that
    generalises (walk the decorative wrapper, hide the matching label) rather
    than on one page's markup, so the next page to grow a labelled search
    group is covered without anyone remembering to look.
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


print('\n== A. the orphaned search label + magnifier ==')
h = fnbody('hideLocalSearchDuplicates')
ok(len(h) > 400, 'A0  the function body was really found', len(h))
ok('previousElementSibling' in h,
   'A1  it looks at what sits in FRONT of the input, which is where the dead '
   'label was')
ok('/^search$/i' in h,
   'A2a and only hides a label that really is this input\'s - matching the WORD, '
   'so it cannot eat the preceding control\'s label')
ok('querySelectorAll' in h and 'input, select, textarea, button, a' in h,
   'A2b the wrapper is only hidden when the input is the ONLY control in it - '
   'otherwise a real control row would go with it')
ok('for (var i = 0; i < 2; i++)' in h,
   'A2c the walk up is capped, so it cannot climb into the page layout')
# the fix is in the SHARED function, not one page's markup
ok(js.count('function hideLocalSearchDuplicates(') == 1,
   'A3  one implementation, so every mapped page is covered')
ok('class="fl">Search</span>' in s,
   'A4  the markup is untouched - the label is HIDDEN at runtime, not deleted, '
   'so a page that stops being driven by the top bar still has its own label')

print('\n== B. Ad HR target left the global bar ==')
bar = s[s.index('<div id="pnl-amzn-controls"'):]
bar = bar[:bar.index('<!-- v7.95') if '<!-- v7.95' in bar[:9000] else 9000]
full_bar = s[s.index('<div id="pnl-amzn-controls"'):]
full_bar = full_bar[:full_bar.index('id="pnl-quick"') + 200]
ok('pnl-ad-headroom-target' not in full_bar,
   'B1  the input is gone from the filter strip')
ok('>Ad HR target</span>' not in s,
   'B2  and so is its label - not hidden, removed')
ok('v11.19' in full_bar and 'Ad HR target LEFT this bar' in full_bar,
   'B3  with a note saying where it went, so nobody re-adds it')
ok(s.count('pnlSetAdHeadroomTarget(this.value)') == 1,
   'B4  exactly ONE control writes the setting now (was two - the bar and the '
   'View popup, which is the divergence hard rule #1 exists to stop)',
   s.count('pnlSetAdHeadroomTarget(this.value)'))

print('\n== C. the surviving control appears wherever the setting can bite ==')
pop = fnbody('pnlRenderColsPopup')
ok('_adHrLive' in pop, 'C1  the popup gates its Ad Headroom section on a flag')
# ⚠ THE REGRESSION GUARD. This exact line shipped broken.
ok("typeof pnlVisibleCols === 'function'" not in pop,
   'C2a pnlVisibleCols is NOT treated as a function - it is a Set, so that '
   'clause was dead and the control never appeared on Summary')
ok("pnlVisibleCols()" not in pop,
   'C2b and it is never CALLED')
ok("pnlVisibleCols.has('ad_headroom')" in pop,
   'C2c it is read as a Set of column keys')
ok(re.search(r"const pnlVisibleCols|let pnlVisibleCols", js) is not None
   and 'new Set' in js[js.index('pnlVisibleCols = ('):js.index('pnlVisibleCols = (') + 400],
   'C2d guard the guard: pnlVisibleCols really is a Set, so C2a-c are not '
   'asserting against a shape that changed')
ok("activeSubview === 'performance'" in pop,
   'C3  Page Performance always qualifies - its table always carries the column')
ok("activeSubview === 'performance' && (pnlPerfSelectedMid" in pop,
   'C4  while the PP-only focus/hidden buttons stay PP-only even when the '
   'section shows on Summary')

print('\n== D. v11.17 / v11.18 are intact ==')
rp = fnbody('renderPnl')
ok(rp.index("renderAdsCampaigns('amazon')") < rp.index('No SKU Economics data loaded for'),
   'D1  the Amazon Ads sync still runs above the early return')
ok("ads: 'renderChewyAds'" in js, 'D2  the Chewy Ads tab is still registered')
ok('|| CHEWY_PERIOD_RENDERERS.sales' not in re.sub(r'//[^\n]*', '', fnbody('chewyRerenderActiveTab')),
   'D3  and an unregistered Chewy tab still warns rather than repainting Sales')

print('\n' + '-' * 58)
print('v11.19: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
