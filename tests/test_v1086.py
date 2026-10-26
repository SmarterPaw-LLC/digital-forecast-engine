# -*- coding: utf-8 -*-
r"""v10.86 - every uploader must be registered in all THREE registries.

Jason, on the Sales & Traffic card: "no recent uploads showing here".

He was looking at one symptom of a three-way drift. Eight dropzones had
shipped since each registry was last touched, so for those uploaders:

  1. DZ_RECENT_SOURCES   - no recent-uploads rail (the visible symptom)
  2. UH_SOURCES          - no Upload History row either, so there was no way
                           to inspect a past upload or retroactively fix a
                           bad region/brand on it
  3. refreshUploadDataRanges - two '-grp' freshness slots existed in the
                           markup but were never written, so the card read
                           "LATEST DATA -" forever

That is the Architecture Rule #8 shape ("a new table means auditing every
site that enumerates tables") applied to the Uploads page rather than to
the FK migration paths. A rule nobody can run is a rule that drifts - the
v10.53 lesson - so this suite makes it runnable.

The sweeps guard THEMSELVES: each one is first run against a deliberately
broken copy and must fail there, otherwise a masking bug (the v10.20 class)
would let it pass against an empty haystack.
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


def script_body(html):
    """Largest inline <script> - where every registry lives."""
    bodies = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)
    return max(bodies, key=len)


def strip_comments(js):
    """Blank // and /* */ so a name mentioned in prose is not read as code."""
    js = re.sub(r'/\*.*?\*/', lambda m: ' ' * len(m.group(0)), js, flags=re.S)
    js = re.sub(r'(?m)//[^\n]*', lambda m: ' ' * len(m.group(0)), js)
    return js


JS = script_body(RAW)
JS_NC = strip_comments(JS)


def obj_block(js, name):
    """Slice `const NAME = { ... };` by brace balance, not by regex."""
    m = re.search(r'const\s+' + name + r'\s*=\s*\{', js)
    if not m:
        return ''
    i = js.index('{', m.start())
    depth = 0
    for j in range(i, len(js)):
        c = js[j]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return js[i:j + 1]
    return ''


# ── A. Every dropzone is registered, or explicitly excluded ────────────────
print('\nA. DZ_RECENT_SOURCES covers every dropzone')

dz_ids = sorted(set(re.findall(r'id="(dz-[a-z0-9-]+)"', RAW)))
ok(len(dz_ids) >= 15, 'found the dropzones in markup', len(dz_ids))

dz_block = obj_block(JS, 'DZ_RECENT_SOURCES')
ok(bool(dz_block), 'DZ_RECENT_SOURCES located')
mapped = set(re.findall(r"'(dz-[a-z0-9-]+)'\s*:", dz_block))

norail_m = re.search(r"const\s+DZ_RECENT_NO_RAIL\s*=\s*new\s+Set\(\[(.*?)\]\)", JS, re.S)
ok(bool(norail_m), 'DZ_RECENT_NO_RAIL declared (explicit exclusions)')
norail = set(re.findall(r"'(dz-[a-z0-9-]+)'", norail_m.group(1) if norail_m else ''))

def unregistered(ids, mapped_set, norail_set):
    return [i for i in ids if i not in mapped_set and i not in norail_set]

missing = unregistered(dz_ids, mapped, norail)
ok(not missing, 'every dropzone has a rail or a stated reason not to', missing)

# teeth: the sweep must fail on a planted unregistered dropzone
ok(unregistered(dz_ids + ['dz-planted-fake'], mapped, norail) == ['dz-planted-fake'],
   'GUARD sweep detects an unregistered dropzone')

# and must not silently pass when the map is empty
ok(len(unregistered(dz_ids, set(), norail)) == len(dz_ids) - len(norail),
   'GUARD sweep is not vacuous against an empty map')

for d in ['dz-sales-traffic', 'dz-chewy-actuals', 'dz-fba-ship', 'dz-amazon-ads-bulk',
          'dz-amz-sqp-asin', 'dz-amz-sp-search-term', 'dz-amz-sp-campaign']:
    ok(d in mapped, 'v10.86 wired ' + d)

ok('dz-shopify' in norail, 'legacy warehouse tile is an explicit exclusion (no uploaded_at)')


# ── B. Every rail table is a known Upload History source ───────────────────
print('\nB. DZ_RECENT_SOURCES tables resolve in UH_SOURCES')

uh_block = obj_block(JS, 'UH_SOURCES')
ok(bool(uh_block), 'UH_SOURCES located')
uh_tables = set(re.findall(r'(?m)^\s*([a-z_0-9]+)\s*:\s*\{', uh_block))
uh_tables |= set(re.findall(r'(?m)^\s*([a-z_0-9]+)\s*:\s*$', uh_block))  # wrapped entries
ok(len(uh_tables) >= 18, 'UH_SOURCES entries parsed', len(uh_tables))

# v10.89 - a source is now a bare table name OR { table, filter }. Strip the
# dz keys AND any filter block first, or the filter's VALUES ('asin',
# 'brand') get read as table names and the sweep fails on a phantom.
_body = re.sub(r"'dz-[a-z0-9-]+'\s*:", '', dz_block)
_body = re.sub(r"filter:\s*\{[^}]*\}", '', _body)
rail_tables = set(re.findall(r"table:\s*'([a-z_0-9]+)'", _body))
rail_tables |= set(re.findall(r"(?<![\w:])'([a-z_0-9]+)'", _body))
unresolved = sorted(t for t in rail_tables if t not in uh_tables)
ok(not unresolved, 'every rail table has a UH_SOURCES config', unresolved)

ok(sorted(t for t in rail_tables | {'planted_missing_table'} if t not in uh_tables)
   == ['planted_missing_table'],
   'GUARD detects a rail table with no UH_SOURCES entry')

# dzLoadRecentUploads returns [] without a config, so a missing entry is a
# SILENT empty rail - exactly the failure Jason reported.
ok('const cfg = (typeof UH_SOURCES !== \'undefined\') ? UH_SOURCES[table] : null;' in JS
   and 'if (!cfg) return [];' in JS,
   'a missing config fails closed (empty rail, not a throw)')


# ── C. Every UH_SOURCES entry is usable ────────────────────────────────────
print('\nC. UH_SOURCES entries are complete')

for t in ['amazon_sales_traffic', 'amazon_sales_traffic_snapshot', 'chewy_sales_weekly',
          'fba_shipments', 'amazon_ads_bulk_upload', 'amazon_query_performance_asin',
          'amazon_sp_search_term', 'amazon_sp_campaign_snapshot']:
    ok(t in uh_tables, 'v10.86 registered ' + t + ' in UH_SOURCES')

# Each entry needs a dateField or the rail cannot build a range at all.
entries = re.findall(r'(?m)^\s*([a-z_0-9]+):\s*\{(.*?)\},\s*$', uh_block, re.S)
no_date = [n for n, body in entries if 'dateField' not in body]
ok(not no_date, 'every UH_SOURCES entry declares a dateField', no_date)
no_label = [n for n, body in entries if 'label' not in body]
ok(not no_label, 'every UH_SOURCES entry declares a label', no_label)


# ── D. Freshness slots in markup are actually written ──────────────────────
print('\nD. every -grp freshness slot gets populated')

grp_ids = sorted(set(re.findall(r'id="(last-[a-z0-9-]+-grp)"', RAW)))
ok(len(grp_ids) >= 16, 'found the freshness slots in markup', len(grp_ids))

m = re.search(r'async function refreshUploadDataRanges\b', JS)
ok(bool(m), 'refreshUploadDataRanges located')
probe = JS[m.start():m.start() + 60000] if m else ''
written = set(re.findall(r"setLast\('(last-[a-z0-9-]+-grp)'", probe))
# v10.89 - the SQP probe loops over a literal [view, cardId, grpId] table and
# calls setLast(grpId, ...) with a VARIABLE, so match any slot id named
# anywhere in the probe body, not only ones passed as a literal argument.
written |= set(re.findall(r"'(last-[a-z0-9-]+-grp)'", probe))

never = [g for g in grp_ids if g not in written]
ok(not never, 'no freshness slot is left permanently blank', never)

ok([g for g in grp_ids + ['last-planted-fake-grp'] if g not in written]
   == ['last-planted-fake-grp'],
   'GUARD detects an unpopulated freshness slot')

for g in ['last-sales-traffic-grp', 'last-fba-fee-preview-grp']:
    ok(g in written, 'v10.86 populates ' + g)


# ── E. Multi-table dropzones ───────────────────────────────────────────────
print('\nE. a dropzone that writes two tables shows both')

ok('function dzTablesFor(' in JS, 'dzTablesFor helper exists')
ok('Array.isArray(v)' in JS, 'dzTablesFor accepts an array of tables')
ok('async function dzLoadRecentForDz(' in JS, 'dzLoadRecentForDz merges per dropzone')
ok('const sessions = await dzLoadRecentForDz(dzId);' in JS_NC,
   'the renderer uses the MERGED list, not a single table')

# Sales & Traffic routes to weekly OR snapshot depending on the uploaded
# range; reading only one would hide half the history.
st = re.search(r"'dz-sales-traffic'\s*:\s*\[(.*?)\]", dz_block, re.S)
ok(bool(st), 'dz-sales-traffic maps to an array')
if st:
    tabs = re.findall(r"'([a-z_0-9]+)'", st.group(1))
    ok(set(tabs) == {'amazon_sales_traffic', 'amazon_sales_traffic_snapshot'},
       'both Sales & Traffic tables are read', tabs)

ok('b.ts).localeCompare(String(a.ts))' in JS or "String(b.ts).localeCompare" in JS,
   'merged sessions are re-sorted newest-first across tables')

# A metadata table holds one row per upload with the count in a column -
# counting rows there would report "1 rows" for every session.
ok("cfg.rowCountField" in JS, 'rowCountField supported for metadata tables')
ok("rcField ? (Number(r[rcField]) || 0) : 1" in JS,
   'row count comes from the column when declared')
ok("rowCountField:'row_count'" in uh_block,
   'amazon_ads_bulk_upload declares its row-count column')


# ── F. Walmart renders a DATE, not its internal week code ──────────────────
print('\nF. Walmart week -> date, display only')

ok("dateField === 'walmart_calendar_week'" in JS_NC,
   '_dzFmtRange branches on the Walmart date field')
ok('walmartWeekToDate(n)' in JS_NC, 'uses the existing converter')
ok('fmtLocalYMD(d)' in JS_NC, 'formats via the shared local-date formatter')

# Both helpers must be TOP-LEVEL, else the call throws at render (v10.8 class).
for fn in ['walmartWeekToDate', 'fmtLocalYMD']:
    ok(len(re.findall(r'(?m)^function\s+' + fn + r'\s*\(', JS)) == 1,
       fn + ' is top-level (in scope for the rail)')

# Fallback must survive a missing converter rather than inventing a date.
ok("String(v).slice(0, 4)} wk ${String(v).slice(4)" in JS,
   'falls back to Walmart vocabulary if the converter is unavailable')

# DISPLAY ONLY - nothing may write a converted value back.
rail = JS[JS.index('function _dzFmtRange'):JS.index('function renderAllDzRecentUploads')]
ok('.update(' not in rail and '.upsert(' not in rail,
   'the rail never writes - conversion is display-only')

ok('function _dzRawRange(' in JS, 'raw stored value kept for the tooltip')
ok('_raw !== _shown' in JS, 'tooltip shows the raw code only when it differs')


# ── G. The esc() trap that nearly shipped ──────────────────────────────────
print('\nG. the rail calls no out-of-scope helper')

# `esc` is a LOCAL const inside 18 separate functions, never a global. A
# call to it from the rail is valid JavaScript and throws only at render -
# node --check and every static text assertion pass. This is the v10.8
# called-but-undefined class; pin it so it cannot come back.
ok(len(re.findall(r'(?m)^(?:function\s+esc\s*\(|const\s+esc\s*=)', JS)) == 0,
   'esc is NOT top-level (so the rail must not call it)')
ok('esc(_tip)' not in JS, 'the rail does not call esc()')
ok("replace(/&/g, '&amp;').replace(/\"/g, '&quot;')" in JS,
   'the rail escapes its tooltip inline instead')

# Sweep every bare call the rail makes against what is actually defined.
# A sweep that cries wolf is a sweep that gets ignored (the v10.8 lesson):
# `if (`, `for (`, `catch (` all look like calls to a naive regex, and the
# JS built-ins are never declared in this file.
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'new',
            'await', 'function', 'else', 'do', 'in', 'of', 'delete', 'void'}
BUILTINS = {'isNaN', 'isFinite', 'parseInt', 'parseFloat', 'encodeURIComponent',
            'decodeURIComponent', 'Boolean', 'Error', 'RegExp', 'Symbol', 'BigInt'}
LOCALS = {'f', 'g', 'r', 'v', 'd', 'n', 'c', 'e', 'it', 'cfg', 'sb', 'main', 'list',
          'rail', 'dz', 'items', 'out', 'byTs', 'rows', 'link', 'table', 'tables',
          'sessions', 'lists', 'budget', 'used', 'shown', 'hidden', 'cnt', 'when',
          'ts', 'rcField', 'label', 'String', 'Number', 'Array', 'Promise', 'Map',
          'Set', 'Math', 'Date', 'Object', 'JSON', 'console', 'document', 'setTimeout',
          'requestAnimationFrame', 'ResizeObserver', 'getComputedStyle'} | KEYWORDS | BUILTINS
# v10.90 - the rail builds its UI out of prose inside template literals, so
# "...that session covered (not when you uploaded it)" and "upload
# session(s) on record" both look like calls to a naive regex. Blank the
# PROSE of every template literal while preserving the ${...} expressions,
# which is where the real calls live. A check that cries wolf is a check
# that gets ignored (the v10.8 rule).
def strip_tpl_prose(js):
    out, i, n = [], 0, len(js)
    while i < n:
        if js[i] != '`':
            out.append(js[i]); i += 1; continue
        out.append('`'); j = i + 1
        while j < n and js[j] != '`':
            if js[j] == '\\':
                out.append('  '); j += 2; continue
            if js[j] == '$' and j + 1 < n and js[j + 1] == '{':
                depth, k = 0, j + 1
                while k < n:
                    if js[k] == '{': depth += 1
                    elif js[k] == '}':
                        depth -= 1
                        if depth == 0: k += 1; break
                    k += 1
                out.append(js[j:k]); j = k; continue   # keep the expression
            out.append(' '); j += 1                     # blank the prose
        out.append('`'); i = j + 1
    return ''.join(out)

_scan = strip_tpl_prose(strip_comments(rail))
_scan = re.sub(r'title="[^"]*"', 'title=""', _scan)
called = set(re.findall(r'(?<![\w.$])([a-zA-Z_$][\w$]*)\s*\(', _scan))
defined = set(re.findall(r'(?m)^(?:async\s+)?function\s+([\w$]+)\s*\(', JS))
defined |= set(re.findall(r'(?m)^(?:const|let|var)\s+([\w$]+)\s*=', JS))
# names declared locally inside the rail itself
defined |= set(re.findall(r'(?:const|let|var|function)\s+([\w$]+)', rail))
undefined = sorted(c for c in called - defined - LOCALS if not c.startswith('_'))
ok(not undefined, 'every function the rail calls is defined somewhere', undefined)

ok(sorted((called | {'totallyMadeUpFn'}) - defined - LOCALS - {c for c in called if c.startswith('_')})
   == ['totallyMadeUpFn'],
   'GUARD called-but-undefined sweep has teeth')

# The prose-stripper must not blank the ${...} expressions too - that would
# empty the haystack and let the sweep pass vacuously (the v10.20 class).
ok('_dzFmtRange' in called, 'GUARD stripper preserves calls inside ${...}')
ok('_dzRawRange' in called, 'GUARD stripper preserves a second ${...} call')
# Method calls are excluded BY DESIGN - the lookbehind drops anything after
# a dot, because `x.foo()` resolves on the object, not on a global name.
ok('toLocaleString' not in called, 'method calls are deliberately out of scope')
ok(len(called) >= 10, 'GUARD the sweep still has a real haystack', len(called))
ok('session' not in called and 'covered' not in called,
   'GUARD prose words are no longer read as calls')


print('\n' + '=' * 62)
print(f'  v10.86  PASS {P}   FAIL {F}')
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
