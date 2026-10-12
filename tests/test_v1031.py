# -*- coding: utf-8 -*-
"""
v10.31 — deleting a block took a declaration with it, and the whole Users
section died.

Jason: "you DID NOT BRING BACK MY DEFAULT TABS GLOBAL SETTING"

v10.28 deleted the v9.82 UI-scoping banner block to turn it into a tooltip.
That block opened with:

    const wrap = document.getElementById('users-tbl-wrap');

and the v9.85 global-tab-access code BELOW it still used `wrap`. So the
declaration went out with the banner, every line after it threw
ReferenceError, and renderUsersList died before painting anything — the users
table AND the global tab-access panel both vanished.

⚠ Two guards failed to catch this, and the reason each failed is the point:

  * `node --check` passes — an undeclared identifier is a RUNTIME error.
  * v10.30's section C asserted the markers were PRESENT IN THE FILE. They
    were. Text presence is not rendering. Asserting a string exists in the
    source proves nothing about whether the code runs.

So this suite sweeps for undeclared identifiers, and v10.30's "nothing was
removed" assertions are upgraded from "the text exists" to "the function runs
without throwing". That second change is the one that actually matters.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

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
    return js[m.start() + 1:j + 1], m


def strip_noise(t):
    t = re.sub(r'/\*.*?\*/', ' ', t, flags=re.S)
    t = re.sub(r'//[^\n]*', ' ', t)
    t = re.sub(r'`(?:[^`\\]|\\.)*`', ' `` ', t, flags=re.S)
    t = re.sub(r"'(?:[^'\\\n]|\\.)*'", " '' ", t)
    t = re.sub(r'"(?:[^"\\\n]|\\.)*"', ' "" ', t)
    t = re.sub(r'/(?:[^/\\\n\[]|\\.|\[[^\]]*\])+/[gimsuy]*', ' // ', t)
    return t


# Everything declared at module scope anywhere in the file.
MODULE_SCOPE = set()
for pat in [r'\bfunction\s+([A-Za-z_$][\w$]*)',
            r'\n(?:const|let|var)\s+([A-Za-z_$][\w$]*)',
            r'\bwindow\.([A-Za-z_$][\w$]*)\s*=']:
    MODULE_SCOPE |= set(re.findall(pat, js))

BUILTINS = {
    'document', 'window', 'console', 'localStorage', 'sessionStorage', 'navigator',
    'location', 'history', 'fetch', 'alert', 'confirm', 'prompt', 'setTimeout',
    'setInterval', 'clearTimeout', 'clearInterval', 'requestAnimationFrame',
    'JSON', 'Math', 'Date', 'Object', 'Array', 'String', 'Number', 'Boolean',
    'Promise', 'Set', 'Map', 'RegExp', 'Error', 'Infinity', 'NaN', 'undefined',
    'null', 'true', 'false', 'this', 'parseInt', 'parseFloat', 'isFinite',
    'isNaN', 'encodeURIComponent', 'decodeURIComponent', 'URL', 'Blob', 'Intl',
    'XMLHttpRequest', 'FileReader', 'Image', 'Chart', 'XLSX', 'supabase',
    'structuredClone', 'globalThis', 'Symbol', 'WeakMap', 'Proxy', 'Reflect',
    'getComputedStyle', 'CustomEvent', 'Event', 'MutationObserver', 'TextDecoder',
    'TextEncoder', 'Uint8Array', 'ArrayBuffer', 'DataView', 'AbortController',
}

KEYWORDS = {
    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default', 'break',
    'continue', 'return', 'function', 'const', 'let', 'var', 'new', 'delete',
    'typeof', 'instanceof', 'in', 'of', 'try', 'catch', 'finally', 'throw',
    'class', 'extends', 'super', 'async', 'await', 'yield', 'void', 'static',
    'get', 'set',
}


def local_names(body, sig_params=''):
    """Parameters, declarations, destructured bindings, catch and loop vars."""
    out = set()
    for w in re.findall(r'[A-Za-z_$][\w$]*', sig_params):
        out.add(w)
    for m in re.finditer(r'\b(?:const|let|var)\s+(\{[^}]*\}|\[[^\]]*\]|[A-Za-z_$][\w$]*)', body):
        for w in re.findall(r'[A-Za-z_$][\w$]*', m.group(1)):
            out.add(w)
    for m in re.finditer(r'\bcatch\s*\(\s*([A-Za-z_$][\w$]*)', body):
        out.add(m.group(1))
    for m in re.finditer(r'\(([^()]*)\)\s*=>', body):
        for w in re.findall(r'[A-Za-z_$][\w$]*', m.group(1)):
            out.add(w)
    for m in re.finditer(r'(?<![\w.$])([A-Za-z_$][\w$]*)\s*=>', body):
        out.add(m.group(1))
    for m in re.finditer(r'\bfunction\s*\(([^)]*)\)', body):
        for w in re.findall(r'[A-Za-z_$][\w$]*', m.group(1)):
            out.add(w)
    return out


def undeclared_in(name):
    body, m = fn(name)
    sig = re.search(r'\(([^)]*)\)', js[m.start():m.start() + 400])
    clean = strip_noise(body)
    loc = local_names(clean, sig.group(1) if sig else '')
    bad = set()
    for mm in re.finditer(r'(?<![\w.$])([A-Za-z_$][\w$]*)', clean):
        w = mm.group(1)
        if w in KEYWORDS or w in BUILTINS or w in loc or w in MODULE_SCOPE:
            continue
        # Skip object-literal keys (`foo:`) and labels.
        tail = clean[mm.end():mm.end() + 2]
        if tail.lstrip().startswith(':'):
            continue
        bad.add(w)
    return bad


# ═════════ A. the sweep ═════════
print('\nA. undeclared-identifier sweep')

WATCH = ['renderUsersList', 'renderGlobalTabDefaults', 'viewDefaultRenderControls',
         'pageSettingsRefresh', 'applyGlobalViewDefaults', 'afterViewDefaultChange']
for name in WATCH:
    bad = undeclared_in(name)
    ok(not bad, '%s() uses no undeclared identifiers%s'
       % (name, '' if not bad else ' — found: ' + ', '.join(sorted(bad))))

# ⚠ Has teeth? Re-run the sweep against the BROKEN version of renderUsersList
# (declaration removed) and confirm it flags `wrap`.
body, m = fn('renderUsersList')
broken = re.sub(r"\n\s*const wrap = document\.getElementById\('users-tbl-wrap'\);", '', body)
clean = strip_noise(broken)
sig = re.search(r'\(([^)]*)\)', js[m.start():m.start() + 400])
loc = local_names(clean, sig.group(1) if sig else '')
flagged = {mm.group(1) for mm in re.finditer(r'(?<![\w.$])([A-Za-z_$][\w$]*)', clean)
           if mm.group(1) not in KEYWORDS and mm.group(1) not in BUILTINS
           and mm.group(1) not in loc and mm.group(1) not in MODULE_SCOPE}
ok('wrap' in flagged,
   'regression guard — the sweep DOES flag wrap once its declaration is removed')
ok('wrap' not in undeclared_in('renderUsersList'),
   '  and does NOT flag it now that the declaration is back')


# ═════════ B. the Users section actually RUNS ═════════
print('\nB. renderUsersList runs — not just "the text is in the file"')

# ⚠ v10.30's section C asserted these markers were PRESENT IN THE SOURCE. They
# were, the whole time the panel was broken. Text presence proves nothing about
# whether the code runs, so this drives the real function against a DOM stub.
harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

// Minimal DOM: enough for renderUsersList to walk its mount points.
const NODES = {};
function el(id) {
  return NODES[id] || (NODES[id] = {
    id, innerHTML: '', textContent: '', title: '', style: {}, children: [],
    parentNode: { insertBefore(n) { NODES[n.id] = n; } },
    querySelector: () => ({ innerHTML: '', textContent: '', style: {} }),
    querySelectorAll: () => [],
  });
}
['users-tbl', 'users-status', 'users-tbl-wrap'].forEach(el);
NODES['users-tbl'].querySelector = () => ({ innerHTML: '', textContent: '', style: {} });

const document = {
  getElementById: id => NODES[id] || null,
  createElement: () => ({ id: '', style: { cssText: '' }, innerHTML: '' }),
};
let renderedGlobalTabs = 0;
function renderGlobalTabDefaults() { renderedGlobalTabs++; }
function renderGlobalViewDefaults() {}
function isAppAdmin() { return true; }
let _usersCache = [];
async function getSB() { return { from: () => ({ select: () => ({ order: async () => ({ data: [], error: null }) }) }) }; }

BODY

(async () => {
  let threw = null;
  try { await renderUsersList(); } catch (e) { threw = e.message; }
  t('renderUsersList does not throw', threw, null);
  t('  and it reached renderGlobalTabDefaults()', renderedGlobalTabs > 0, true);
  t('  mounting the global tab-access panel', !!NODES['users-global-tabs'], true);
  t('  while keeping the UI-scoping warning on the status tooltip',
    /UI scoping/.test(NODES['users-status'].title), true);
  console.log('\n  ' + P + ' passed, ' + F + ' failed');
  if (F) process.exit(1);
})();
"""
ubody, _ = fn('renderUsersList')
# fn() already returns the text INCLUDING the `async function …()` header,
# so it drops in as-is. Prefixing it again produced `async function f() async
# function f() {`.
harness = harness.replace('BODY', ubody)
tmp = os.path.join(tempfile.gettempdir(), 'test_v1031_users.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('renderUsersList runs')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.31 — all green')
