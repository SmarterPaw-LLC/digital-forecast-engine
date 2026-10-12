# -*- coding: utf-8 -*-
"""
v10.16 — the Chewy rebate-PDF uploader moves onto the Rebates tab.

Jason: "move the chewy rebates upload from the uploads page to this page."

Same call as v10.11 made for the catalog on the Cost tab: every number on the
Rebates tab is parsed out of these PDFs, so the drop target belongs beside
them. The static assertions below exist so a later tidy-up cannot quietly move
it back to Data → Uploads.
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
INDEX = os.path.join(os.path.dirname(HERE), 'index.html')
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
    for pat in (r'\nfunction %s\s*\(' % re.escape(name),
                r'\nasync function %s\s*\(' % re.escape(name)):
        m = re.search(pat, js)
        if m:
            break
    else:
        raise SystemExit('FAIL: cannot find %s' % name)
    k = m.end() - 1
    pdepth = 0
    while k < len(js):
        if js[k] == '(':
            pdepth += 1
        elif js[k] == ')':
            pdepth -= 1
            if pdepth == 0:
                break
        k += 1
    i = js.index('{', k)
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


# ═════════ A. it moved, and it moved exactly once ═════════
print('\nA. static — where the uploader lives now')

ok(src.count('<input type="file" id="f-chewy-rebates"') == 1,
   'exactly one f-chewy-rebates input in the file')

upStart = src.index('<div id="data-view-uploads"')
upEnd   = src.index('<div id="data-view-history"')
uploads = src[upStart:upEnd]
ok('f-chewy-rebates' not in uploads,
   'f-chewy-rebates is ABSENT from the Uploads page markup')
ok('grp-chewy-rebates' not in src,
   'the grp-chewy-rebates upload group is gone entirely')

rbStart = src.index('<div id="chpnl-view-rebates"')
# The Rebates tab is the last sub-panel of the Chewy P&L view.
rebates = src[rbStart:rbStart + 12000]
ok('id="f-chewy-rebates"' in rebates,
   'f-chewy-rebates is PRESENT on the Rebates tab')
ok('id="st-chewy-rebates"' in rebates,
   'the status line moved with it')
ok('id="last-chewy-rebates"' in rebates,
   'the last-loaded line moved with it')

# Other uploaders must not have been disturbed by the slice.
for grp in ['grp-chewy-sales', 'grp-chewy-actuals', 'grp-shopify-sales', 'grp-amz-sales']:
    ok(grp in uploads, 'neighbouring uploader %s survived the slice' % grp)


# ═════════ B. nothing still points at the old home ═════════
print('\nB. static — no dangling references to the removed group')

ok('last-chewy-rebates-grp' not in src,
   'the dead -grp element has no remaining references')
ok(not re.search(r"chewy_rebates:\s*'grp-chewy-rebates'", src),
   'TABLE_TO_UPLOAD_GROUP no longer routes the freshness chip to a dead group')
# Any surviving map entry must name a group that actually exists, or clicking
# a data-currency chip lands on Data → Uploads and expands nothing.
for tbl, grp in re.findall(r"^\s*(\w+):\s*'(grp-[\w-]+)',", src, re.M):
    ok(('id="%s"' % grp) in src,
       'TABLE_TO_UPLOAD_GROUP %s -> %s still exists' % (tbl, grp))

# Copy that told the operator to go to the Uploads page for rebates.
ok('Chewy Rebate Invoices (PDF)</strong>' not in src,
   'no copy still sends the operator to Data → Uploads for rebates')
ok('drop on the bar above' in src or 'on the bar above' in src,
   'the banner / empty state point at the inline bar instead')


# ═════════ C. the drop handler ═════════
print('\nC. behaviour — chewyRebateDrop (the real function)')

ok(len(re.findall(r'\nfunction chewyRebateDrop\s*\(', js)) == 1,
   'chewyRebateDrop defined exactly once')
ok('chewyRebateDrop(event, this)' in src,
   'chewyRebateDrop is wired to the bar')

handler = fn('chewyRebateDrop')
h = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + ' — got ' + g + ', want ' + w); }
};

let handed = null, prevented = 0;
const ST = { textContent: '', style: {} };
const document = { getElementById: id => id === 'st-chewy-rebates' ? ST : null };
function handleChewyRebatesUpload(input) { handed = input; }
const ev = (names) => ({
  preventDefault() { prevented++; },
  dataTransfer: { files: names.map(n => ({ name: n })) },
});
const BAR = { style: { borderColor: 'var(--sp-green)' } };

HANDLER

// A normal multi-PDF drop reaches the same handler the file picker uses.
handed = null; prevented = 0;
chewyRebateDrop(ev(['REB00175503.pdf', 'REB00174410.pdf']), BAR);
t('preventDefault called', prevented, 1);
t('two PDFs handed to the upload handler', handed.files.map(f => f.name),
  ['REB00175503.pdf', 'REB00174410.pdf']);
t('hover highlight is cleared on drop', BAR.style.borderColor, 'var(--border2)');

// Extension matching is case-insensitive — Chewy's portal has shipped .PDF.
handed = null;
chewyRebateDrop(ev(['REB1.PDF']), BAR);
t('uppercase .PDF accepted', handed.files.length, 1);

// Non-PDFs are dropped, not passed through to the PDF parser.
handed = null;
chewyRebateDrop(ev(['Catalog Details.csv', 'REB2.pdf', 'notes.txt']), BAR);
t('only the PDF survives a mixed drop', handed.files.map(f => f.name), ['REB2.pdf']);

// A drop with no PDFs at all says so rather than silently doing nothing.
handed = null; ST.textContent = '';
chewyRebateDrop(ev(['Catalog Details.csv']), BAR);
t('no handler call when nothing is a PDF', handed, null);
t('an all-non-PDF drop explains itself', /Drop PDF files/.test(ST.textContent), true);

// Degenerate shapes must not throw — a drag from the desktop with no files,
// or a browser that hands over a null dataTransfer.
let threw = false;
try {
  chewyRebateDrop({ preventDefault() {}, dataTransfer: { files: [] } }, BAR);
  chewyRebateDrop({ preventDefault() {} }, BAR);
  chewyRebateDrop({ preventDefault() {}, dataTransfer: { files: [] } }, null);
} catch (e) { threw = true; }
t('degenerate drops do not throw', threw, false);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""
h = h.replace('HANDLER', handler)
tmp = os.path.join(tempfile.gettempdir(), 'test_v1016_drop.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(h)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip())
    fails.append('chewyRebateDrop behaviour')


print('\n' + ('=' * 60))
if fails:
    print('FAILED (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('v10.16 — all green')
