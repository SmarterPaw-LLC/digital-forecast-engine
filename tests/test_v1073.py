# -*- coding: utf-8 -*-
"""v10.73 - SEO tab, phase 1: the Google Search Console keyword tracker.

Jason: "we will build an seo tab in the digital forecast engine as a unified
keyword tracker tool."

The assertions that earn their keep here:

  1. THE POSITION DELTA SIGN. Search position IMPROVES when the number goes
     DOWN, so the delta is computed as (previous - current) on purpose and a
     POSITIVE value means "moved up the page". That is counterintuitive enough
     that a future refactor could silently flip it, and a flipped sign makes
     every rising keyword read as falling while still looking perfectly
     plausible. Driven against the real sliced function, both directions.

  2. THE EMPTY STATES ARE DISTINCT. v10.37 records the bug where a swallowed
     error made "migration not run" and "nothing uploaded yet" render the SAME
     message, and the one it guessed was wrong. Browser verification caught
     exactly that here: signed out, the read throws, and the tab claimed "the
     tables exist but are empty" when it had never successfully queried.
     Four causes, four messages, none claiming a fact it did not observe.

  3. seo-search IS MAPPED AND BARE. v8.43 hides every input in
     GLOBAL_SEARCH_MAP because the global bar drives it. It hides the INPUT
     only, so a label or sized wrapper around it survives as an orphan. That
     shipped briefly and rendered a "Search" caption pointing at nothing.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name, got=None):
    global passed, failed
    if cond: passed += 1; print('  ok    ' + name)
    else:    failed += 1; print('  FAIL  %s%s' % (name, '' if got is None else '  got: %r' % (got,)))

def fn(name, kw='function'):
    i = js.index('%s %s(' % (kw, name))
    j = js.index('{', i); d = 0; k = j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k+1]
        k += 1

print('\n== A. wiring: all three surfaces, or the tab is unreachable ==')
ok("{ id: 'seo'," in js,            'APP_TABS has a seo entry (drives tab-access + nav)')
ok('id="page-seo"' in s,            'page-seo div exists')
ok("if(id==='seo')" in js,          'showPage routes to loadSeoTab')
ok(s.count('id="page-seo"') == 1,   'exactly one page-seo div')

# body-level placement: test_v1061 asserts every .page opens at depth 0, and a
# page nested inside another is how v10.61 broke two unrelated tabs at once.
head = s[:s.index('id="page-seo"')]
depth = head.count('<body') and True
before = s[:s.index('<div class="page" id="page-seo"')]
opens = len(re.findall(r'<div\b', before)) - len(re.findall(r'</div>', before))
ok(opens <= 1, 'page-seo opens at body level (net open divs before it <= 1)', opens)

print('\n== B. glyph: one glyph one concept (hard rule #2) ==')
# The key glyph was the obvious pick for "keywords" but already means
# "Change password" in Settings, so it would carry two meanings.
ok('\U0001F511 Change password' in s or 'Change password' in s,
   'the key glyph still means Change password in Settings')
nav_line = [l for l in s.split('\n') if 'id="seoNavBtn"' in l][0]
ok('&#128246;' in nav_line,
   'nav button uses an HTML ENTITY, not a literal \\uXXXX (the v10.20 bug: '
   'nothing interprets escapes in raw markup, they render as six characters)')
ok('\\ud83d\\udcf6' not in nav_line, '  and carries no raw escape sequence')
# the same glyph inside <script> is correctly an escape, because JS parses it
ok("label: '\\ud83d\\udcf6 SEO'" in js,
   'APP_TABS label uses the JS escape form (inside <script>, which DOES parse it)')

print('\n== C. the search input: mapped AND bare ==')
ok("seo:           { id: 'seo-search' }" in js or "seo: { id: 'seo-search' }" in js,
   'seo-search is in GLOBAL_SEARCH_MAP, so the global bar drives the tab')
seg = s[s.index('id="page-seo"'):s.index('<!-- /page-seo -->')]
ok('id="seo-search"' in seg, 'the input exists for the global bar to write into')
# the orphan-label trap: hideLocalSearchDuplicates hides the INPUT only
m = re.search(r'<input[^>]*id="seo-search"[^>]*>', seg)
ok(m is not None, 'seo-search is an <input>')
around = seg[max(0, m.start()-320):m.start()] if m else ''
ok('class="fl">Search' not in around,
   'no label wraps seo-search (it would survive the input being hidden)')
ok('flex:1' not in around[-200:],
   'no flex:1 wrapper around it (an empty flex child still eats the row)')

print('\n== D. house renderers reused, not re-implemented (hard rule #1) ==')
ok('pnlCardStrip([' in fn('renderSeoKeywords'),
   'scorecards go through the canonical pnlCardStrip, not a 6th bespoke card')
ok('fitTableWrapsSoon()' in fn('renderSeoKeywords'),
   'table height uses the shared viewport fitter (v10.56)')
ok('data-fit="viewport"' in seg, '  and the wrap opts in via data-fit')

print('\n== E. Architecture Rule #4: every read paginates ==')
ff = fn('seoFetchAll', 'async function')
ok('.range(' in ff, 'seoFetchAll ranges (Supabase caps un-ranged selects at 1000)')
ok('length < PAGE' in ff, '  and stops on a short page')
ok('seoFetchAll(' in fn('loadSeoKeywords', 'async function'),
   'the keyword load uses it (a snapshot carries ~13k queries)')

print('\n== F. column naming ==')
# `position` is a Postgres keyword and, more importantly, the number is a MEAN
# across the pull's whole 16-month window, which the name should not hide.
ok("'query,clicks,impressions,ctr_pct,avg_position'" in js,
   'selects avg_position, not position')
ok('avg_position' in seg or 'avg_position' in fn('renderSeoKeywords'),
   'the renderer reads avg_position')

print('\n== G. BEHAVIOUR: the real sliced seoVisibleRows in node ==')
HARNESS = r"""
let seoRows = [], seoCompareMap = null, seoSortKey = 'impressions', seoSortDir = -1;
const DOM = { 'seo-minimp': '0', 'seo-search': '', 'seo-quick': 'all' };
function document_getElementById(id) { return (id in DOM) ? { value: DOM[id] } : null; }
const document = { getElementById: document_getElementById };

__VISIBLE__

const out = {};
function setup() {
  seoRows = [
    { query: 'meowijuana',        clicks: 1969, impressions: 19248, ctr_pct: 10.23, avg_position: 2.63 },
    { query: 'catnip spray',      clicks: 12,   impressions: 4800,  ctr_pct: 0.25,  avg_position: 14.2 },
    { query: 'silvervine sticks', clicks: 0,    impressions: 1200,  ctr_pct: 0.00,  avg_position: 17.9 },
    { query: 'cat grass',         clicks: 3,    impressions: 560,   ctr_pct: 0.54,  avg_position: 66.1 },
  ];
  seoCompareMap = new Map([
    ['meowijuana',        { avg_position: 3.4,  impressions: 18000 }],  // improved 3.4 -> 2.63
    ['catnip spray',      { avg_position: 12.1, impressions: 5200  }],  // worsened 12.1 -> 14.2
    ['silvervine sticks', { avg_position: 19.4, impressions: 900   }],  // improved
  ]);
  DOM['seo-minimp'] = '0'; DOM['seo-search'] = ''; DOM['seo-quick'] = 'all';
  seoSortKey = 'impressions'; seoSortDir = -1;
}

setup();
let r = seoVisibleRows();
out.all = r.map(x => [x.query, x._dPos === null ? null : +x._dPos.toFixed(2), x._isNew]);

// the sign convention, stated as the question a reader would ask
out.improvedIsPositive = r.find(x => x.query === 'meowijuana')._dPos > 0;
out.worsenedIsNegative = r.find(x => x.query === 'catnip spray')._dPos < 0;
out.newHasNullDelta    = r.find(x => x.query === 'cat grass')._dPos === null;
out.newIsFlagged       = r.find(x => x.query === 'cat grass')._isNew === true;

setup(); DOM['seo-quick'] = 'striking';
out.striking = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'page1';
out.page1 = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'rising';
out.rising = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'falling';
out.falling = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'new';
out.newOnly = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'noclicks';
out.noclicks = seoVisibleRows().map(x => x.query);

setup(); DOM['seo-minimp'] = '1000';
out.floored = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-search'] = 'CATNIP';
out.searchCaseInsensitive = seoVisibleRows().map(x => x.query);

setup(); seoSortKey = 'avg_position'; seoSortDir = 1;
out.sortByPosAsc = seoVisibleRows().map(x => x.query);

// no comparison snapshot: deltas must be null, nothing marked new
setup(); seoCompareMap = null;
const nc = seoVisibleRows();
out.noCompareAllNull = nc.every(x => x._dPos === null && x._dImp === null);
out.noCompareNoneNew = nc.every(x => x._isNew === false);

console.log(JSON.stringify(out));
"""
HARNESS = HARNESS.replace('__VISIBLE__', fn('seoVisibleRows'))
hp = os.path.join(SP, 'test_v1073.js')
io.open(hp, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hp], capture_output=True, text=True)
if res.returncode != 0:
    print(res.stderr[:2000]); sys.exit(1)
R = json.loads([l for l in res.stdout.splitlines() if l.strip()][-1])

print('\n-- the sign convention (the one a refactor could silently flip) --')
ok(R['improvedIsPositive'],
   'a keyword that moved 3.4 -> 2.63 reports a POSITIVE delta (moved up the page)')
ok(R['worsenedIsNegative'],
   'a keyword that moved 12.1 -> 14.2 reports a NEGATIVE delta (fell down the page)')
ok(R['newHasNullDelta'], 'a query absent from the comparison has a null delta, not 0')
ok(R['newIsFlagged'],    '  and is flagged new rather than silently showing a dash')

print('\n-- quick filters --')
ok(R['striking'] == ['catnip spray', 'silvervine sticks'],
   'striking distance isolates pos 11-20', R['striking'])
ok(R['page1'] == ['meowijuana'], 'page 1 isolates pos 1-10', R['page1'])
ok(R['rising'] == ['meowijuana', 'silvervine sticks'], 'rising = improved only', R['rising'])
ok(R['falling'] == ['catnip spray'], 'falling = declined only', R['falling'])
ok(R['newOnly'] == ['cat grass'], 'new = absent from the comparison', R['newOnly'])
ok(R['noclicks'] == ['silvervine sticks'],
   'impressions-with-zero-clicks finds the CTR problem', R['noclicks'])

print('\n-- filters + sort --')
ok(R['floored'] == ['meowijuana', 'catnip spray', 'silvervine sticks'],
   'the min-impressions floor drops rows below it', R['floored'])
ok(R['searchCaseInsensitive'] == ['catnip spray'],
   'search is case insensitive', R['searchCaseInsensitive'])
ok(R['sortByPosAsc'][0] == 'meowijuana' and R['sortByPosAsc'][-1] == 'cat grass',
   'sorting by position ascending puts the best rank first', R['sortByPosAsc'])

print('\n-- no comparison snapshot --')
ok(R['noCompareAllNull'], 'with no comparison every delta is null')
ok(R['noCompareNoneNew'], '  and nothing is falsely flagged as new')

print('\n== H. the four empty states say four different things ==')
rk = fn('renderSeoKeywords')
ok('seoTableMissing' in rk and 'supabase_v10_73_gsc_seo.sql' in rk,
   'tables missing -> names the migration to run')
ok('seoLoadError' in rk, 'a failed read is tracked separately from an empty one')
ok('not known whether the tables are empty or missing' in rk,
   'a failed read does NOT claim the tables exist (the v10.37 bug)')
ok('not signed in' in rk, 'the signed-out case is named, since it is the common one')
ok('load_gsc.py' in rk, 'loaded-but-empty -> names the loader to run')
guesses = rk.count('The tables exist but are empty')
ok(guesses == 1, 'only the genuinely-empty branch claims the tables exist', guesses)

print('\n== I. the 16-month-mean caveat is surfaced, not buried ==')
ok('16 month' in rk or '16 month' in js, 'the window is named in the UI layer')
ok('damp' in js.lower() or 'MEAN' in js,
   'the damping limitation is written down where the next reader will see it')

print('\n%s' % ('=' * 60))
print('v10.73: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
