# -*- coding: utf-8 -*-
r"""v10.90 - the rail must be readable without being explained.

Jason: "i don't understand what the upload history is telling me"

Two faults, and the first was mine against his ORIGINAL v10.85 spec:

  1. He asked for "the most recent DATE RANGE first". I sorted by
     uploaded_at. Several monthly CSVs dropped in one sitting share an
     upload time, so the prominent line - the data period - came out in an
     order driven by a value that was never shown:

         2026-02 / 2026-04 / 2026-01 -> 2026-03

     which reads as unsorted. Ordering by a hidden field is the bug.

  2. Nothing named either line. "2026-02" could be the upload date or the
     period covered. "1mo ago" could be either too.

The rule: never sort a list by a field the list does not display, and
never print two dates of different kinds without saying which is which.
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

JS = max(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', RAW, re.S), key=len)

rail_start = JS.index('function _dzFmtRange')
rail_end   = JS.index('function renderAllDzRecentUploads')
RAIL = JS[rail_start:rail_end]


# ── A. Sorted by what it shows ─────────────────────────────────────────────
print('\nA. ordered by the data period, not by a hidden field')

# Both the single-table and the merged path must use the same rule.
sorts = re.findall(r"\.sort\(\(a, b\) =>(.*?)\);", RAIL, re.S)
ok(len(sorts) >= 2, 'both the single-table and merged paths sort', len(sorts))
for i, body in enumerate(sorts):
    ok('b.max' in body and 'a.max' in body,
       f'sort #{i+1} ranks by the data period first')
    ok(body.index('max') < body.index('.ts') if '.ts' in body else True,
       f'sort #{i+1} uses upload time only as a tiebreak')

# The pre-v10.90 ordering must not survive anywhere in the rail.
bare_ts = re.findall(r"\.sort\(\(a, b\) => (?:String\()?b\.ts(?:\))?\.localeCompare", RAIL)
ok(not bare_ts, 'no upload-time-only sort remains', bare_ts)


# ── B. Both dates are named ────────────────────────────────────────────────
print('\nB. each line says what kind of date it is')

ok('uploaded ${when}' in RAIL,
   "the relative time is labelled 'uploaded'")
ok('rows \u00b7 uploaded' in RAIL, 'row count and upload time read as one line')

# A session spanning several periods should say so - "200 rows" does not
# tell you it was three monthly CSVs.
ok('g.periods' in RAIL, 'sessions carry their distinct period count')
ok('periods: new Set()' in RAIL, 'the set is initialised per session')
ok('g.periods.add(sv)' in RAIL, 'every period value is collected')
ok('nPer < 2' in RAIL, 'the count is suppressed for a single-period session')
for unit in ['months', 'weeks', 'days']:
    ok("'" + unit + "'" in RAIL, 'period unit "' + unit + '" is available')
ok('/month/.test(f)' in RAIL, 'the unit is derived from the table dateField')


# ── C. The header explains the list ────────────────────────────────────────
print('\nC. the header answers "what am I looking at"')

tips = re.findall(r'<div class="dz-recent-hdr" title="([^"]*)"', RAIL)
ok(len(tips) == 2, 'both the populated and empty header carry a tooltip', len(tips))
for t in tips:
    low = t.lower()
    ok('upload session' in low, 'tooltip defines a row as an upload session')
    ok('not when you uploaded' in low or 'data period' in low,
       'tooltip distinguishes data period from upload time')
    ok('most recent data period' in low, 'tooltip states the sort order')

ok("cursor:help" in RAIL, 'the header signals it is hoverable')


# ── D. The count names its unit ────────────────────────────────────────────
print('\nD. "3 of 8" says 3 of 8 WHAT')

ok('uploads`' in RAIL, 'the count is suffixed with its unit')
m = re.search(r"cnt\.textContent = hidden > 0 \? `([^`]*)` : `([^`]*)`", RAIL)
ok(bool(m), 'count assignment located')
if m:
    ok('uploads' in m.group(1) and 'uploads' in m.group(2),
       'both the truncated and full count name the unit', m.groups())
ok('cnt.title' in RAIL, 'the count carries its own explanation on hover')
ok('without making this card taller' in RAIL,
   'it explains WHY only some rows show (the v10.85 constraint)')


# ── E. Nothing regressed from the earlier rail fixes ───────────────────────
print('\nE. earlier guarantees still hold')

# v10.85 - the card may never grow for the log.
ok('.update(' not in RAIL and '.upsert(' not in RAIL, 'the rail still never writes')
ok('list.clientHeight' in RAIL, 'budget still comes from the clipped list box')
# v10.87 - no clickable affordance flattened into a tooltip.
ok(chr(0x2197) + ' Open' not in ''.join(tips), 'no link text stranded in the header tooltip')
# v10.89 - per-view scoping survives.
ok('dzSourceKey' in JS, 'filtered sources still hash to their own cache key')


print('\n' + '=' * 62)
print(f'  v10.90  PASS {P}   FAIL {F}')
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
