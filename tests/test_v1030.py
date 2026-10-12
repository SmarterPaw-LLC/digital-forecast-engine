# -*- coding: utf-8 -*-
"""
v10.30 — "if i click 'yes' nothing happens."

The write was SUCCEEDING. The panel never repainted, so there was no feedback
and it looked dead.

    pageSettingsRefresh() {
      try { if (typeof renderPageSettingsMenu === 'function') renderPageSettingsMenu(); } catch {}
      try { if (typeof syncPageSettingsGear === 'function') syncPageSettingsGear(); } catch {}
    }

NEITHER FUNCTION EXISTS. Both names were guessed rather than read out of the
file (the real ones are openPageSettingsMenu / pageSettingsSyncIndicator), and
the `typeof … === 'function'` guard plus the try/catch meant the mistake failed
silently instead of throwing. The defensive code is what hid the bug.

⚠ v10.8 already built a called-but-undefined sweep for exactly this class, and
it did not catch this one because it matches by NAMESPACE PREFIX (catVis* /
pageSettings* / freeze*). `renderPageSettingsMenu` starts with "render" and
`syncPageSettingsGear` starts with "sync", so both sailed straight past it.

So the guard here is call-site-scoped rather than prefix-scoped: every function
invoked from the view-defaults code must actually be defined somewhere. That
catches a guessed name regardless of what it is called.
"""
import io
import os
import re
import sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, 'index.html')
src = io.open(INDEX, encoding='utf-8', newline='').read()
js = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', src, re.S), key=len)

fails = []
def ok(cond, label):
    if cond:
        print('  ok  ' + label)
    else:
        print('  FAIL ' + label)
        fails.append(label)


def fn(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m:
        raise SystemExit('FAIL: cannot find %s' % name)
    i = js.index('{', m.end() - 1)
    depth, j = 0, i
    while j < len(js):
        if js[j] == '{':
            depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[m.start() + 1:j + 1]


def strip_noise(t):
    """Drop comments and string/template literals.

    Without this, a function NAMED inside the comment that explains the bug
    reads as a live call — which would make this very suite report the thing it
    was written to prove is gone.
    """
    t = re.sub(r'/\*.*?\*/', ' ', t, flags=re.S)
    t = re.sub(r'//[^\n]*', ' ', t)
    t = re.sub(r'`(?:[^`\\]|\\.)*`', ' `` ', t, flags=re.S)
    t = re.sub(r"'(?:[^'\\\n]|\\.)*'", " '' ", t)
    t = re.sub(r'"(?:[^"\\\n]|\\.)*"', ' "" ', t)
    return t


# Every function the view-defaults feature owns.
OWNED = [
    'loadGlobalViewDefaults', 'writeGlobalViewDefaults', 'setViewDefaultField',
    'setViewDefaultSort', 'afterViewDefaultChange', 'onViewDefaultSortChange',
    'clearViewDefault', 'viewDefaultError', 'pageSettingsRefresh',
    'applyGlobalViewDefaults', 'viewDefaultSummary', 'viewDefaultRenderControls',
]

# Names that are built-ins, locals, or object methods rather than free functions.
IGNORE = {
    'if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'function',
    'parseInt', 'parseFloat', 'String', 'Number', 'Boolean', 'Object', 'Array',
    'JSON', 'Math', 'alert', 'confirm', 'console', 'Set', 'Map', 'Promise',
    'await', 'new', 'delete', 'document', 'window', 'localStorage',
}


def local_names(name, body):
    """Names bound INSIDE this function: parameters, declarations, destructured
    bindings, catch bindings.

    ⚠ Without this the sweep cries wolf. v10.8 hit exactly this — run naively
    it reported 18 "missing" functions, every one a parameter or a destructured
    binding. A check that cries wolf is a check that gets ignored, so it gets
    narrowed rather than shipped noisy.
    """
    out = set()
    sig = re.search(r'\n(?:async )?function %s\s*\(([^)]*)\)' % re.escape(name), js)
    if sig:
        for part in sig.group(1).split(','):
            for w in re.findall(r'[A-Za-z_$][\w$]*', part):
                out.add(w)
    for m in re.finditer(r'\b(?:const|let|var)\s+(\{[^}]*\}|\[[^\]]*\]|[A-Za-z_$][\w$]*)', body):
        for w in re.findall(r'[A-Za-z_$][\w$]*', m.group(1)):
            out.add(w)
    for m in re.finditer(r'\bcatch\s*\(\s*([A-Za-z_$][\w$]*)', body):
        out.add(m.group(1))
    # Arrow / function-expression parameters: `(a, b) =>` and `function (a) {`
    for m in re.finditer(r'\(([^()]*)\)\s*=>', body):
        for w in re.findall(r'[A-Za-z_$][\w$]*', m.group(1)):
            out.add(w)
    for m in re.finditer(r'(?<![\w.$])([A-Za-z_$][\w$]*)\s*=>', body):
        out.add(m.group(1))
    return out


def defined_somewhere(name):
    pats = [
        r'\bfunction\s+%s\s*\(' % re.escape(name),
        r'\b(?:const|let|var)\s+%s\s*=' % re.escape(name),
        r'\bwindow\.%s\s*=' % re.escape(name),
    ]
    return any(re.search(p, js) for p in pats)


# ═════════ A. the sweep — no guessed function names ═════════
print('\nA. called-but-undefined sweep over the view-defaults code')

missing = []
for name in OWNED:
    body = strip_noise(fn(name))
    locals_here = local_names(name, body)
    for m in re.finditer(r'(?<![\w.$])([A-Za-z_$][\w$]*)\s*\(', body):
        callee = m.group(1)
        if callee in IGNORE or callee in OWNED or callee in locals_here:
            continue
        if not defined_somewhere(callee):
            missing.append('%s() called from %s()' % (callee, name))

ok(not missing,
   'every function the view-defaults code calls is defined'
   + ('' if not missing else ' — MISSING: ' + '; '.join(sorted(set(missing)))))

# ⚠ Guard the guard. If strip_noise ever over-matches and blanks the bodies,
# the sweep passes against an empty haystack — exactly how the v10.20 escape
# sweep looked fine while being wrong. A real call must still be visible.
ok('onAfterChange' in local_names('pageSettingsRefresh', strip_noise(fn('pageSettingsRefresh'))),
   'guard the guard — a destructured local is recognised as local')
ok('applyGlobalViewDefaults' not in local_names('afterViewDefaultChange', strip_noise(fn('afterViewDefaultChange'))),
   'guard the guard — a real free call is NOT written off as local')

probe = strip_noise(fn('afterViewDefaultChange'))
ok('applyGlobalViewDefaults' in probe,
   'guard the guard — a real call survives comment/literal stripping')
probe2 = strip_noise(fn('pageSettingsRefresh'))
ok('renderPageSettingsMenu' not in probe2,
   'guard the guard — a name that only appears in a comment is stripped')


# ═════════ B. the specific bug ═════════
print('\nB. the bug itself')

refresh = fn('pageSettingsRefresh')
clean = strip_noise(refresh)
ok('renderPageSettingsMenu' not in clean, 'no longer calls the invented renderPageSettingsMenu')
ok('syncPageSettingsGear' not in clean, 'no longer calls the invented syncPageSettingsGear')
ok('pageSettingsSyncIndicator' in clean, 'calls the gear helper that actually exists')
ok(defined_somewhere('pageSettingsSyncIndicator'), '  and it is defined')

# ⚠ The swallowing try/catch is what turned a typo into a silent no-op.
ok('catch' not in clean,
   'the refresh no longer swallows its own errors')

# Repaint in place, not a full menu rebuild under the cursor.
ok('viewDefaultRenderControls(host, pageKey, onAfterChange)' in refresh,
   'repaints the panel in place')
ok('_vdHosts' in refresh, '  using the host the render recorded')

render = fn('viewDefaultRenderControls')
ok('_vdHosts[pageKey] = { host, onAfterChange }' in render,
   'the render records its host so a click can find it again')

after = fn('afterViewDefaultChange')
ok('pageSettingsRefresh(pageKey)' in after,
   'the setter passes the page through so the right panel repaints')
ok('applyGlobalViewDefaults()' in strip_noise(after),
   '  and applies to the live page so the change is visible')

clearfn = fn('clearViewDefault')
ok('afterViewDefaultChange(pageKey)' in clearfn,
   'clear routes through the same repaint path as set')


# ═════════ C. nothing of Jason's was removed ═════════
print("\nC. the pre-existing global settings are intact")

# ⚠ Jason asked directly whether the org-wide settings he had already
# configured were gone. They are not, and that is worth an assertion rather
# than a reassurance — v10.28 removed only MY OWN v10.26 Settings panel.
for marker, what in [
    ('function renderGlobalTabDefaults',  'global default TAB ACCESS panel (v9.85)'),
    ('users-global-tabs',                 '  its mount point in Settings'),
    ('Global default tab access',         '  its heading'),
    ('async function setGlobalDefaultTabs', '  its writer'),
    ('function catVisPromoteToGlobal',    'category visibility GLOBAL DEFAULT (v10.6)'),
    ('Make this my global default',       '  its button'),
]:
    ok(marker in js or marker in src, what + ' still present')

print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.30 — all green')
