# -*- coding: utf-8 -*-
"""v11.18 - the Chewy period control repainted the WRONG TAB.

Jason: "same issue with chewy" - the readout said 2026-10-01 -> 2026-10-28
(Quarter-to-date) while the Ads panel beneath it still said 2026-09-01 ->
2026-09-30.

`CHEWY_PERIOD_RENDERERS` is a hand-kept map of sub-view -> renderer. v11.16
added a sixth tab and did not add a row to it, so `chewyRerenderActiveTab`
fell through `|| CHEWY_PERIOD_RENDERERS.sales` and repainted the SALES tab - a
hidden panel - while the visible Ads panel kept a window nobody selected.

The assertions that earn their keep:

  * A1 THE THREE REGISTRIES NAME THE SAME SET OF TABS. A per-tab spot check
    would only ever catch the tab someone thought to check. This compares the
    TABS registry inside switchChewyPnlView against CHEWY_PERIOD_RENDERERS and
    CHEWY_PERIOD_SOURCES as sets, so the NEXT Chewy tab cannot ship with a
    missing row either - which is the actual bug, not the one line that fixes
    this instance of it.

  * B1 AN UNREGISTERED TAB IS LOUD. The silent `|| ...sales` default is what
    let this survive a release: work happened, nothing threw, and the stale
    panel looked like a working one. Asserted gone, and asserted that the
    remaining fallback is scoped to an UNSET view rather than an unknown one.
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


print('\n== A. the three registries describe the SAME set of Chewy tabs ==')

# The authoritative list: the TABS registry switchChewyPnlView drives.
swb = fnbody('switchChewyPnlView')
tabs = set(re.findall(r"\{\s*key:\s*'([a-z]+)'", swb))
ok(len(tabs) >= 6, 'A0a the TABS registry was really found', sorted(tabs))

def mapkeys(const):
    """Top-level keys only.

    CHEWY_PERIOD_SOURCES' values are OBJECTS (`sales: { field, rows }`), so a
    bare `word:` sweep also harvests `field` and `rows` and then reports them
    as tabs that no longer exist. Match a key at the start of its own line
    instead, which both registries write that way.
    """
    i = js.index('const %s = {' % const)
    j = js.index('\n};', i)
    body = js[i + len('const %s = {' % const):j]
    body = re.sub(r'//[^\n]*', '', body)        # a comment can contain `word:`
    flat = re.sub(r'\{[^{}]*\}', '', body)      # drop the nested value objects
    return set(re.findall(r"(?:^|[,{\s])([a-z]+)\s*:", flat))

rend = mapkeys('CHEWY_PERIOD_RENDERERS')
srcs = mapkeys('CHEWY_PERIOD_SOURCES')
ok(len(rend) >= 6 and len(srcs) >= 6,
   'A0b and both period registries were really found - a bad slice would make '
   'every check below pass vacuously', (sorted(rend), sorted(srcs)))

eq('A1a every Chewy sub-tab has a period RENDERER, or the control repaints '
   'someone else', sorted(tabs - rend), [])
eq('A1b every Chewy sub-tab has a period SOURCE, or all-time floors on the '
   'wrong feed', sorted(tabs - srcs), [])
eq('A1c and neither registry names a tab that no longer exists',
   sorted((rend | srcs) - tabs), [])
ok('ads' in tabs and 'ads' in rend and 'ads' in srcs,
   'A1d the Ads tab specifically is in all three', (sorted(tabs), sorted(rend), sorted(srcs)))

# The renderer names must be real functions, not plausible strings.
for view, name in re.findall(r"([a-z]+):\s*'(render[A-Za-z]+)'",
                             js[js.index('const CHEWY_PERIOD_RENDERERS = {'):
                                js.index('\n};', js.index('const CHEWY_PERIOD_RENDERERS = {'))]):
    ok(('function %s(' % name) in js,
       'A2  %s -> %s is a real function' % (view, name))

print('\n== B. an unregistered tab is LOUD, not silently redirected ==')
body = fnbody('chewyRerenderActiveTab')
# ⚠ Assert on LIVE CODE. The fix's own comment quotes the removed line to say
# what it used to read, so a raw substring sweep matches its own explanation -
# the v10.90 / v10.93 prose-in-source class, in a guard again.
live = re.sub(r'//[^\n]*', '', body)
ok('|| CHEWY_PERIOD_RENDERERS.sales' not in live,
   'B1a the silent fall-back-to-Sales default is GONE from the CODE - it '
   'turned a missing registration into a hidden panel being repainted while '
   'the visible one went stale')
ok('|| CHEWY_PERIOD_RENDERERS.sales' in body,
   'B1a2 while the comment explaining why still survives, so nobody '
   '"optimises" the default back in')
ok('console.warn' in body and 'CHEWY_PERIOD_RENDERERS' in body,
   'B1b an unknown sub-tab warns by name')
ok("chewyPnlView || 'sales'" in body,
   'B2  the remaining fallback is scoped to an UNSET view, which is the only '
   'case it was ever for')
ok(body.index('if (!name)') < body.index('window[name]'),
   'B3  and it bails BEFORE trying to call it')

print('\n== C. the shared renderer is reached by a zero-arg name ==')
ok(js.count('function renderChewyAds(') == 1,
   'C1  one thin adapter, so the registry stays one uniform shape')
ok("renderAdsCampaigns('chewy')" in fnbody('renderChewyAds'),
   'C2  that calls the SHARED two-channel renderer, not a Chewy-only copy')
ok(js.count('function renderAdsCampaigns(') == 1,
   'C3  which is still the only one in the app')

print('\n== D. the Amazon side keeps its own fix ==')
rp = fnbody('renderPnl')
ok("renderAdsCampaigns('amazon')" in rp
   and rp.index("renderAdsCampaigns('amazon')") < rp.index('No SKU Economics data loaded for'),
   'D1  v11.17 is intact: the Amazon hook still runs above the early return')

print('\n' + '-' * 58)
print('v11.18: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
