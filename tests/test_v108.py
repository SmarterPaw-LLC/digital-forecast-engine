# -*- coding: utf-8 -*-
"""v10.8 — no function in the page-settings namespaces is called without a definition.

THE BUG THIS EXISTS FOR: v10.7 replaced a whole span of the file with a new
block. The old span also contained catVisRerenderCurrent(); the new block kept
calling it but never defined it. That is valid JavaScript, so `node --check`
passed, every behaviour suite passed (none drove the global-edit path), and it
shipped. Editing the global category default threw ReferenceError and silently
did nothing.

Any wholesale span replacement can drop a definition the replacement still
depends on. This is the cheap catch for that class.

⚠ Scope is deliberate. A whole-file version of this sweep drowns in false
positives — function PARAMETERS (`function f(getVal)`), destructured bindings
(`const { regionMatches: pnlRegionMatches } = …`) and prose inside template
literals all look like calls to a regex, and a check that cries wolf is a check
that gets ignored. Restricted to the three namespaces this feature owns, where
no such cases exist, it is exact.
"""
import io, os, re, sys

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

OWNED = re.compile(r'^(catVis|pageSettings|freeze[A-Z])')

# ── definitions ──────────────────────────────────────────────────────────────
defined = set(re.findall(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(', js))
defined |= set(re.findall(
    r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)', js))
defined |= set(re.findall(r'\bwindow\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function', js))

# ── call sites, with comments and string/template literals removed ───────────
code = re.sub(r'/\*.*?\*/', ' ', js, flags=re.S)
code = re.sub(r'(?m)^\s*//.*$', ' ', code)
code = re.sub(r'`(?:\\.|[^`\\])*`', '``', code, flags=re.S)   # template literals
code = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", code)
code = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', code)

missing = {}
for name in set(re.findall(r'(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(', code)):
    if not OWNED.match(name) or name in defined:
        continue
    missing[name] = len(re.findall(r'(?<![.\w$])%s\s*\(' % re.escape(name), code))

# A `typeof f === 'function'` guard makes a missing hook deliberate, not a break.
guarded = set(re.findall(r"typeof\s+([A-Za-z_$][\w$]*)\s*===?\s*'function'", js))
hard = {n: c for n, c in missing.items() if n not in guarded}
soft = {n: c for n, c in missing.items() if n in guarded}

owned_defs = sorted(n for n in defined if OWNED.match(n))

print('=== v10.8 \u00b7 called-but-undefined sweep (catVis / pageSettings / freeze) ===')
print('  definitions in these namespaces: %d' % len(owned_defs))
if hard:
    print('\n  \u2717 UNGUARDED calls with no definition:')
    for n, c in sorted(hard.items()):
        print('      %-34s %d call site(s)' % (n, c))
else:
    print('  \u2713 every call in these namespaces resolves to a definition')
if soft:
    print('  \u2139 guarded optional hooks (fine):')
    for n, c in sorted(soft.items()):
        print('      %-34s %d call site(s)' % (n, c))

# Each function the two containers depend on, named so a future span replacement
# that drops one fails here instead of in Jason's browser.
REQUIRED = [
    'catVisPass', 'catVisResolved', 'catVisInvalidate', 'catVisIdMap',
    'catVisAllCats', 'catVisAllSubcats', 'catVisSetPage', 'catVisClearPageOverride',
    'catVisPromoteToGlobal', 'catVisMigrateProductsLocal', 'catVisPersist',
    'catVisLoadFromDb', 'catVisHiddenCount', 'catVisSummaryText',
    'catVisRenderControls', 'catVisRerenderCurrent', 'catVisOpenPopover',
    'catVisOpenGlobalPopover', 'catVisRenderSettings', 'catVisSyncAllChips',
    'catVisPageDef', 'pageSettingsCurrentNavKey', 'pageSettingsPanelsFor',
    'pageSettingsSyncIndicator', 'openPageSettingsMenu', 'closePageSettingsMenu',
    'togglePageSettingsMenu', 'freezeCurrentKey', 'freezeCurrentLabel',
    'freezeRenderControls',
]

checks = [('NO unguarded call to an undefined function in these namespaces', not hard)]
for fname in REQUIRED:
    checks.append(('%-26s is defined' % fname, fname in defined))
checks += [
    ('catVisRerenderCurrent is still CALLED where a global change needs it (the v10.7 regression)',
     js.count('catVisRerenderCurrent()') >= 2),
    ('  it resolves the page the same way the gear does',
     'pageSettingsCurrentNavKey' in js[js.index('function catVisRerenderCurrent('):
                                       js.index('function catVisRerenderCurrent(') + 900]),
    ('  and cannot break a save if a page definition is bad',
     'catVisRerenderCurrent:' in js),
]

print()
fail = 0
for name, cond in checks:
    print(('  \u2713 ' if cond else '  \u2717 ') + name)
    if not cond: fail += 1

print('\n' + ('\u2717 %d FAILED, %d passed' % (fail, len(checks) - fail) if fail
              else '\u2713 %d passed' % len(checks)))
sys.exit(1 if fail else 0)
