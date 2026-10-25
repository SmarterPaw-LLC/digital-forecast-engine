# -*- coding: utf-8 -*-
"""
v10.14 — Cost to Chewy: click the Case cell to set units-per-case in place.

The gaps panel already named every SKU missing a case pack; sending the
operator to the product card one at a time to fix them was the wrong half of
that loop. On a CS row case_qty is the single value that blocks every column
to its right.
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


SLICES = [fn('chewyCaseSave'), fn('chewyCaseKey')]

HARNESS = r'''
// ── stubs ──
let allProducts = [];
let records = [];
let writes = [];
let alerts = [];
let renders = 0;
let auditEvents = [];
const alert = m => alerts.push(m);
const document = { getElementById: () => null };
function renderChewyPnlCost() { renders++; }
function renderInventoryTbl() {}
function logAudit(a, d) { auditEvents.push({ a, d }); }
let _sbError = null;
async function getSB() {
  return { from: (t) => ({ update: (payload) => ({ eq: async (col, val) => { writes.push({ t, payload, col, val }); return { error: _sbError }; } }) }) };
}

__SLICES__

let pass = 0, fail = 0; const failures = [];
function ok(c, label, extra) { if (c) pass++; else { fail++; failures.push(label + (extra ? ' :: ' + extra : '')); } }

function reset(caseQty) {
  allProducts = [{ master_id: 'SP-1', case_qty: caseQty === undefined ? null : caseQty }];
  records = [{ master_id: 'SP-1', region: 'US', case_qty: 0 },
             { master_id: 'SP-1', region: 'CA', case_qty: 0 },
             { master_id: 'SP-9', region: 'US', case_qty: 7 }];
  writes = []; alerts = []; renders = 0; auditEvents = []; _sbError = null;
}
const mkInput = v => ({ value: v, dataset: {}, blur() {} });

// ═════════ A. the happy path ═════════
reset(null);
await chewyCaseSave('SP-1', mkInput('12'));
ok(writes.length === 1, 'A1 one write', 'got ' + writes.length);
ok(writes[0].t === 'products', 'A1 writes to products (NOT product_cogs)', writes[0].t);
ok(writes[0].payload.case_qty === 12, 'A1 payload is the integer', JSON.stringify(writes[0].payload));
ok(Object.keys(writes[0].payload).length === 1, 'A1 touches ONLY case_qty', JSON.stringify(writes[0].payload));
ok(writes[0].col === 'master_id' && writes[0].val === 'SP-1', 'A1 scoped to the one product');

// A2 — the v7.34 lesson: every in-memory cache that reads case_qty must be
// mirrored, or Inventory Planning serves the old value until a page reload.
ok(allProducts[0].case_qty === 12, 'A2 allProducts mirrored');
ok(records[0].case_qty === 12 && records[1].case_qty === 12, 'A2 BOTH region records mirrored',
   JSON.stringify(records.map(r => r.case_qty)));
ok(records[2].case_qty === 7, 'A2 another product is untouched');
ok(renders > 0, 'A3 re-renders so the row recomputes');
ok(auditEvents.length === 1 && auditEvents[0].a === 'product.case_qty', 'A4 audited', JSON.stringify(auditEvents));
ok(auditEvents[0].d.from === null && auditEvents[0].d.to === 12, 'A4 audit records before and after');

// ═════════ B. validation — a bad value must never reach the database ═════════
for (const bad of ['0', '-3', '-1', 'abc']) {
  reset(12);
  await chewyCaseSave('SP-1', mkInput(bad));
  ok(writes.length === 0, 'B1 ' + JSON.stringify(bad) + ' is rejected', 'writes=' + writes.length);
  ok(allProducts[0].case_qty === 12, 'B1 ' + JSON.stringify(bad) + ' leaves the stored value alone');
  ok(alerts.length === 1, 'B1 ' + JSON.stringify(bad) + ' tells the user why');
}
// B2 — a decimal truncates to a whole case rather than being rejected: 12.9
// cases is not a thing, and parseInt is the honest read of a typo.
reset(null);
await chewyCaseSave('SP-1', mkInput('12.9'));
ok(writes.length === 1 && writes[0].payload.case_qty === 12, 'B2 a decimal truncates to a whole number',
   JSON.stringify(writes.map(w => w.payload)));
// B3 — whitespace is tolerated.
reset(null);
await chewyCaseSave('SP-1', mkInput('  24  '));
ok(writes[0].payload.case_qty === 24, 'B3 whitespace trimmed');

// ═════════ C. clearing ═════════
reset(12);
await chewyCaseSave('SP-1', mkInput(''));
ok(writes.length === 1 && writes[0].payload.case_qty === null, 'C1 blank clears to null',
   JSON.stringify(writes.map(w => w.payload)));
ok(allProducts[0].case_qty === null, 'C1 cache cleared');
ok(records[0].case_qty === 0, 'C1 records fall back to 0, the shape they store');

// ═════════ D. no-ops ═════════
reset(12);
await chewyCaseSave('SP-1', mkInput('12'));
ok(writes.length === 0, 'D1 an unchanged value writes nothing');
ok(renders > 0, 'D1 but still re-renders to drop the editor');
reset(null);
await chewyCaseSave('SP-1', mkInput(''));
ok(writes.length === 0, 'D2 blank on an already-null value writes nothing');

// ═════════ E. idempotency — Enter saves, then blur fires ═════════
// chewyCaseKey saves DIRECTLY on Enter rather than leaning on blur(), because
// .blur() is a no-op when the field is not focused and the edit would then
// evaporate with no error. The blur that follows must not run it all again.
reset(null);
const inp = mkInput('12');
await chewyCaseSave('SP-1', inp);
await chewyCaseSave('SP-1', inp);          // the trailing blur
ok(writes.length === 1, 'E1 a second call on the same input is a no-op', 'writes=' + writes.length);
ok(inp.dataset.cancelled === '1', 'E1 the input is marked as handled');

// E2 — ESC marks it before anything runs.
reset(null);
const escInp = mkInput('99');
escInp.dataset.cancelled = '1';
await chewyCaseSave('SP-1', escInp);
ok(writes.length === 0, 'E2 ESC saves nothing');
ok(allProducts[0].case_qty === null, 'E2 ESC leaves the value alone');

// E3 — Enter routes through the save, not through blur().
reset(null);
let blurred = false;
const keyInp = { value: '12', dataset: {}, blur() { blurred = true; } };
chewyCaseKey({ key: 'Enter', preventDefault() {}, stopPropagation() {} }, 'SP-1', keyInp);
await new Promise(r => setTimeout(r, 10));
ok(writes.length === 1, 'E3 Enter saves without depending on a blur event', 'writes=' + writes.length);
ok(blurred, 'E3 and still blurs so the caret leaves the cell');

// E4 — ESC via the key handler cancels and re-renders.
reset(12);
const escKeyInp = { value: '99', dataset: {}, blur() {} };
chewyCaseKey({ key: 'Escape', preventDefault() {}, stopPropagation() {} }, 'SP-1', escKeyInp);
ok(escKeyInp.dataset.cancelled === '1', 'E4 ESC marks the input cancelled');
ok(writes.length === 0, 'E4 ESC writes nothing');

// ═════════ F. a failed write must not leave the cache lying ═════════
reset(null);
_sbError = { message: 'permission denied' };
await chewyCaseSave('SP-1', mkInput('12'));
ok(allProducts[0].case_qty === null, 'F1 a rejected write leaves allProducts untouched',
   String(allProducts[0].case_qty));
ok(records[0].case_qty === 0, 'F1 and records untouched');
ok(alerts.length === 1 && /permission denied/.test(alerts[0]), 'F1 and surfaces the real error', alerts[0]);
ok(auditEvents.length === 0, 'F1 and logs no audit event for a write that did not happen');

console.log('\n  v10.14: ' + pass + ' passed, ' + fail + ' failed');
if (fail) { failures.forEach(f => console.log('    FAIL ' + f)); process.exit(1); }
'''

harness = '(async () => {\n' + HARNESS.replace('__SLICES__', '\n\n'.join(SLICES)) + '\n})();'
tmpdir = tempfile.mkdtemp(prefix='v1014_')
jsp = os.path.join(tmpdir, 'test_v1014.js')
io.open(jsp, 'w', encoding='utf-8', newline='').write(harness)

print('=== v10.14 behaviour tests ===')
r = subprocess.run([os.environ.get('NODE', 'node'), jsp], capture_output=True, text=True)
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
if r.returncode != 0:
    sys.exit(r.returncode)

print('\n=== v10.14 static assertions ===')
sfail = []


def sok(cond, label):
    print(('  ok: ' if cond else '  FAIL: ') + label)
    if not cond:
        sfail.append(label)


cost = fn('renderChewyPnlCost')
sok('const caseCell = (r) =>' in cost, 'the Case column has its own cell renderer')
# v10.82 - the Cost body is keyed now, so the Case cell is `case: caseCell(r)`
# in the CELLS map rather than an inlined ${caseCell(r)} in a run of <td>s.
# The guarantee is unchanged: exactly one site renders the Case cell.
sok(cost.count('caseCell(r)') == 1, 'the Case cell uses it (once, via the keyed CELLS map)')
sok('case: caseCell(r),' in cost, 'the Case cell is keyed to its column')
# The handler is built ONCE into `open` and interpolated into each branch, so
# count the interpolation — counting the call would read 1 and miss the point.
sok(cost.count('${open}') == 4, 'all four Case cell states are clickable')
sok(cost.count("chewyCaseEdit('") == 1, 'one source for the click handler, reused')
sok("cursor:pointer" in cost, 'the cell advertises itself as clickable')

edit = fn('chewyCaseEdit')
sok('ev.stopPropagation()' in edit, 'the cell click does not bubble to openProductModal')
sok("onclick=\\\"event.stopPropagation()\\\"" in edit or 'onclick="event.stopPropagation()"' in edit,
    'clicks inside the input do not bubble either')
sok('input.focus()' in edit and 'input.select()' in edit, 'the editor focuses and selects')
sok("type=\\\"number\\\"" in edit or 'type="number"' in edit, 'numeric input')

save = fn('chewyCaseSave')
sok("from('products')" in save, 'writes to products (case_qty is a product field)')
sok('allProducts' in save and 'records' in save, 'mirrors both in-memory caches')
sok("input.dataset.cancelled = '1';" in save, 'claims the edit so a trailing blur no-ops')
sok('renderChewyPnlCost()' in save, 're-renders so the row recomputes in place')
sok('renderInventoryTbl' in save, 'refreshes Inventory Planning when it is on screen')

key = fn('chewyCaseKey')
sok('chewyCaseSave(masterId, input)' in key, 'Enter saves DIRECTLY, not via blur()')

# The guidance must point at the new path, not the old one.
sok('Click the Case cell in the table below to set it' in src,
    'the gaps panel names the inline edit')
sok('Set Case qty on the product card.' not in src,
    'the stale product-card-only instruction is gone from the gap message')
sok('CLICK ANY CELL to set it in place.' in src, 'the column tooltip advertises it')

# Provenance, not the chip.
sok(src.count('v10.14 —') >= 1, "v10.14's own provenance markers survive")
for marker in ('v10.13 —', 'v10.11 —', 'v7.27 —'):
    sok(marker in src, 'earlier provenance marker preserved: %s' % marker.split(' ')[0])

print('\n  static: %d failed' % len(sfail))
if sfail:
    sys.exit(1)
print('\n  v10.14 ALL GREEN')
