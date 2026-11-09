#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.44 - the upload conformity guard.

Jason: "there should be validation check on all uploads to match conformity -
if upload looks different than expected, prompted user with an 'are you sure'
message"

  * A  THE REAL FAILURE, REPLAYED. On 2026-11-02 the US FBA inventory file was
       uploaded again with the region set to CA; the table upserts on
       (asin, region, snapshot_date) so it overwrote the real CA numbers, and
       all 112 ASINs with both rows ended up byte-identical. A1 feeds the
       guard that exact shape and requires it to fire.
    A2 and requires it NOT to fire when the two scopes genuinely differ,
       because two regions really can both hold stock.
  * B  the replacing and size checks.
  * D  FAILURE-SAFE. A guard that cannot run must not stop the upload - and
       must not claim it ran either.
  * E  an INFO-only result proceeds without a prompt (the v11.31 lesson: a
       prompt on the ordinary path is a prompt nobody reads).
  * F  static: the confirm runs BEFORE the write, or it is an audit.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0


def ok(cond, name, got=None):
    global passed, failed
    if cond:
        passed += 1; print('  ok    ' + name)
    else:
        failed += 1
        print('  FAIL  ' + name + ('' if got is None else '   got=' + ascii(got)))


def eq(name, got, want):
    ok(got == want, name, None if got == want else '%s want %s' % (ascii(got), ascii(want)))


def _balance(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ''
    while k < n:
        c = js[k]
        if c == '/' and k + 1 < n and js[k + 1] == '/':
            while k < n and js[k] != '\n':
                k += 1
            continue
        if c == '/' and k + 1 < n and js[k + 1] == '*':
            k = js.index('*/', k) + 2
            continue
        if c == '/' and prev in '(,=:[!&|?{};+-*%~^<>':
            k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == '[':
                    while k < n and js[k] != ']':
                        k += 2 if js[k] == '\\' else 1
                if js[k] == '/':
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = 'x'
            continue
        if c in '"\'`':
            q = c; k += 1
            while k < n:
                if js[k] == '\\':
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = 'x'
            continue
        if c == '{':
            depth += 1; started = True
        elif c == '}':
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise RuntimeError('unbalanced slice at %d' % i)


def fn(name):
    i = js.index('function %s(' % name)
    head = 'async ' if js[max(0, i - 6):i] == 'async ' else ''
    k = js.index('(', i)
    depth = 0
    while k < len(js):
        if js[k] == '(': depth += 1
        elif js[k] == ')':
            depth -= 1
            if depth == 0: break
        k += 1
    brace = js.index('{', k)
    return head + js[i:brace] + _balance(brace)


def const_obj(name):
    i = js.index('const %s = {' % name)
    return 'const %s = %s;' % (name, _balance(js.index('{', i)))


def run_node(path, src):
    io.open(path, 'w', encoding='utf-8', newline='\n').write(src)
    r = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print(r.stdout); print(r.stderr); sys.exit(1)
    return json.loads(r.stdout)


# A Supabase double. Records every query and answers from a fixture, so the
# REAL check runs against the REAL shapes PostgREST returns.
SB = r"""
let FIX = { samePeriod: [], existingCount: 0, prevRows: [], throwOn: null };
const QUERIES = [];
function mkQ(table) {
  const q = { _t: table, _eq: {}, _lt: null, _head: false };
  q.select = (cols, opts) => { q._cols = cols; if (opts && opts.head) q._head = true; return q; };
  q.eq = (c, v) => { q._eq[c] = v; return q; };
  q.lt = (c, v) => { q._lt = [c, v]; return q; };
  q.order = () => q;
  q.limit = () => q;
  q.then = (res, rej) => {
    QUERIES.push({ table: q._t, cols: q._cols, eq: { ...q._eq }, lt: q._lt, head: q._head });
    if (FIX.throwOn && QUERIES.length === FIX.throwOn) { return Promise.reject(new Error('boom')).then(res, rej); }
    let out;
    if (q._head) out = { count: FIX.existingCount, data: null };
    else if (q._lt) out = { data: FIX.prevRows };
    // v11.76 - check 2 selects the KEY column alone now, because it counts
    // which of THIS file's keys already exist rather than every row loaded
    // that day. One column, its own fixture.
    else if (q._cols && String(q._cols).indexOf(',') === -1) out = { data: FIX.sameCell };
    else out = { data: FIX.samePeriod };
    return Promise.resolve(out).then(res, rej);
  };
  return q;
}
async function getSB() { return { from: (t) => mkQ(t) }; }
function esc2(v) { return String(v == null ? '' : v); }
console.warn = () => {};
"""

RULES = const_obj('UPLOAD_GUARD_RULES')
# v11.76 - the size check resolves its baseline through uploadGuardBaseline
# now. Sliced rather than stubbed, so this suite proves the SHIPPED
# predecessor rule rather than a copy of it.
CONSTS = '\n'.join(
    js[js.index('const %s' % k):js.index('\n', js.index('const %s' % k))]
    for k in ('UPLOAD_GUARD_TWIN_PCT', 'UPLOAD_GUARD_MIN_KEYS', 'UPLOAD_GUARD_COUNT_PCT',
              'UPLOAD_GUARD_OVERLAP_PCT'))

A = run_node(os.path.join(SP, '_v1144_a.js'),
    SB + RULES + '\n' + CONSTS + '\n' + fn('uploadGuardBaseline') + '\n'
    + fn('uploadGuardCheck') + '\n' + r"""
const out = {};
const mkPayload = (qty) => qty.map(([asin, q]) => ({
  asin, region: 'CA', snapshot_date: '2026-11-02', afn_fulfillable_quantity: q }));
const mkExisting = (qty, region) => qty.map(([asin, q]) => ({
  asin, region, afn_fulfillable_quantity: q }));

// A1 THE REAL SHAPE: 112 ASINs, every one identical to its US twin, being
// uploaded as CA. The 3 oz spray's own numbers lead.
const real = [['B07KPRTSMT', 5654], ['B07WGHX6M3', 3185], ['B08ZHDPPNH', 113],
              ['B08ZGL2CNL', 106], ['B081ZDBFXP', 261], ['B00U6DJCR8', 415],
              ['B0D9ZLLH9C', 128], ['B0HJDDN85X', 20], ['B0AAA00001', 7],
              ['B0AAA00002', 9], ['B0AAA00003', 11], ['B0AAA00004', 13]];
FIX = { samePeriod: mkExisting(real, 'US'), existingCount: 0, prevRows: [], throwOn: null };
(async () => {
  out.a1 = await uploadGuardCheck('fba_inventory', mkPayload(real));

  // A2 two regions that genuinely differ must NOT fire.
  const diff = real.map(([a, q], i) => [a, q + 100 + i]);
  FIX = { samePeriod: mkExisting(diff, 'US'), existingCount: 0, prevRows: [], throwOn: null };
  out.a2 = await uploadGuardCheck('fba_inventory', mkPayload(real));

  // A3 a handful of matching rows is coincidence, not a twin.
  const few = real.slice(0, 4);
  FIX = { samePeriod: mkExisting(few, 'US'), existingCount: 0, prevRows: [], throwOn: null };
  out.a3 = await uploadGuardCheck('fba_inventory', mkPayload(few));

  // A4 the SAME scope is never its own twin - that is the replacing check.
  FIX = { samePeriod: mkExisting(real, 'CA'), existingCount: 0, prevRows: [], throwOn: null };
  out.a4 = await uploadGuardCheck('fba_inventory', mkPayload(real));

  // B1 v11.76 - replacing is the INTERSECTION with this file's own keys,
  // because that is all the conflict key can touch. Here the day already
  // holds all 12 of them, plus 3 rows from another brand's upload.
  FIX = { samePeriod: [], prevRows: [], throwOn: null,
          sameCell: real.map(([a]) => ({ asin: a }))
                        .concat([{ asin: 'Z1' }, { asin: 'Z2' }, { asin: 'Z3' }]) };
  out.b1 = await uploadGuardCheck('fba_inventory', mkPayload(real));

  // B1d a day holding ONLY another brand's upload replaces nothing at all.
  FIX = { samePeriod: [], prevRows: [], throwOn: null,
          sameCell: [{ asin: 'Z1' }, { asin: 'Z2' }, { asin: 'Z3' }] };
  out.b1d = await uploadGuardCheck('fba_inventory', mkPayload(real));

  // B2 a row count far off the previous load of the SAME scope.
  FIX = { samePeriod: [], existingCount: 0, throwOn: null,
          prevRows: real.concat([['X1',1],['X2',1],['X3',1],['X4',1],['X5',1],
                                 ['X6',1],['X7',1],['X8',1],['X9',1],['X10',1],
                                 ['X11',1],['X12',1],['X13',1],['X14',1]])
                   .map(([a, q]) => ({ snapshot_date: '2026-10-20', asin: a, afn_fulfillable_quantity: q })) };
  out.b2 = await uploadGuardCheck('fba_inventory', mkPayload(real.slice(0, 8)));

  // D1 a failing query must return NOTHING and must not throw.
  FIX = { samePeriod: [], existingCount: 0, prevRows: [], throwOn: 1 };
  let threw = false;
  try { out.d1 = await uploadGuardCheck('fba_inventory', mkPayload(real)); }
  catch (e) { threw = true; }
  out.d1_threw = threw;

  // D2 an undeclared source is unguarded, and says nothing.
  FIX = { samePeriod: mkExisting(real, 'US'), existingCount: 0, prevRows: [], throwOn: null };
  out.d2 = await uploadGuardCheck('not_a_source', mkPayload(real));
  out.d3 = await uploadGuardCheck('fba_inventory', []);

  out.queries = QUERIES.slice(0, 3);
  console.log(JSON.stringify(out));
})();
""")

_twin = [c for c in A['a1'] if 'IDENTICAL' in c['text']]
eq('A1 THE REAL FAILURE: the twin check fires', len(_twin), 1)
eq('A1b at high severity, so it prompts', _twin[0]['level'], 'high')
ok('100%' in _twin[0]['text'], 'A1c naming how much of the file matched', _twin[0]['text'])
ok('"US"' in _twin[0]['text'], 'A1d and WHICH scope it matched')
ok('overwrite real CA numbers' in _twin[0]['text'],
   'A1e and what uploading anyway would do')
eq('A2 two genuinely different regions do NOT fire it',
   [c for c in A['a2'] if 'IDENTICAL' in c['text']], [])
eq('A3 four matching rows is coincidence, not a twin',
   [c for c in A['a3'] if 'IDENTICAL' in c['text']], [])
eq('A4 a scope is never its own twin', [c for c in A['a4'] if 'IDENTICAL' in c['text']], [])

_rep = [c for c in A['b1'] if 'already loaded' in c['text']]
eq('B1 replacing an existing load is reported', len(_rep), 1)
eq('B1b as INFO, because replacing is the ordinary path', _rep[0]['level'], 'info')
# v11.76 RE-POINTED. This pinned '133' - the count of EVERY row loaded for
# that (region, date). The conflict key is (asin, region, snapshot_date), so
# only a key THIS file carries can be replaced, and counting the whole day
# told an operator uploading a second brand that the first was about to be
# wiped. test_v1176 section D owns the rule.
ok("12 of this file's 12 ASINs" in _rep[0]['text'],
   'B1c naming exactly which rows go', _rep[0]['text'])
_repd = [c for c in A['b1d'] if 'already loaded' in c['text']]
eq('B1d another brand on the same day is still reported', len(_repd), 1)
ok('Nothing is replaced' in _repd[0]['text'],
   'B1e ... as replacing nothing', _repd[0]['text'])

_size = [c for c in A['b2'] if 'had' in c['text'] and 'ASINs' in c['text']]
eq('B2 a row count far off the last load is reported', len(_size), 1)
eq('B2b at high severity', _size[0]['level'], 'high')
ok('drop' in _size[0]['text'], 'B2c naming the direction', _size[0]['text'])

eq('D1 a failing query returns no concerns', A['d1'], [])
ok(A['d1_threw'] is False, 'D1b THE RULE: a guard that cannot run does not stop the upload')
eq('D2 an undeclared source is unguarded', A['d2'], [])
eq('D3 an empty payload is not an anomaly', A['d3'], [])
eq('D4 the first query is scoped to the period, not the whole table',
   A['queries'][0]['eq'].get('snapshot_date'), '2026-11-02')

# ---------------------------------------------------------------------------
# E. The confirm gate.
# ---------------------------------------------------------------------------
E = run_node(os.path.join(SP, '_v1144_e.js'),
    'const UPLOAD_GUARD_RULES = { s: { label: "Src" } };\n'
    'let CONCERNS = []; let SHOWN = 0; let ANSWER = true;\n'
    'async function uploadGuardCheck() { return CONCERNS; }\n'
    'function uploadGuardDialog() { SHOWN++; return Promise.resolve(ANSWER); }\n'
    + fn('uploadGuardConfirm') + '\n' + r"""
const out = {};
(async () => {
  CONCERNS = []; SHOWN = 0;
  out.e1 = await uploadGuardConfirm('s', [{}]); out.e1_shown = SHOWN;
  CONCERNS = [{ level: 'info', text: 'x' }]; SHOWN = 0;
  out.e2 = await uploadGuardConfirm('s', [{}]); out.e2_shown = SHOWN;
  CONCERNS = [{ level: 'info', text: 'x' }, { level: 'high', text: 'y' }]; SHOWN = 0;
  out.e3 = await uploadGuardConfirm('s', [{}]); out.e3_shown = SHOWN;
  ANSWER = false; SHOWN = 0;
  out.e4 = await uploadGuardConfirm('s', [{}]); out.e4_shown = SHOWN;
  console.log(JSON.stringify(out));
})();
""")

ok(E['e1'] is True and E['e1_shown'] == 0, 'E1 a clean file proceeds with no prompt')
ok(E['e2'] is True and E['e2_shown'] == 0,
   'E2 INFO alone proceeds silently - a prompt on the ordinary path is one nobody reads')
ok(E['e3'] is True and E['e3_shown'] == 1, 'E3 a HIGH concern prompts, and Yes proceeds')
ok(E['e4'] is False and E['e4_shown'] == 1, 'E4 and No stops it')

# ---------------------------------------------------------------------------
# F. Static wiring.
# ---------------------------------------------------------------------------
def nocomment(t):
    t = re.sub(r'/\*[\s\S]*?\*/', '', t)
    return re.sub(r'(?m)^\s*//.*$', '', t)
code = nocomment(js)

for f in ('uploadGuardCheck', 'uploadGuardDialog', 'uploadGuardConfirm'):
    eq('F1 exactly one %s' % f, code.count('function %s(' % f), 1)

# THE ORDERING THAT MAKES IT A GUARD RATHER THAN AN AUDIT.
_p = nocomment(fn('parseFbaInventorySnapshot'))
ok(_p.index("uploadGuardConfirm('fba_inventory'") < _p.index("onConflict: 'asin,region,snapshot_date'"),
   'F2 the confirm runs BEFORE the upsert')
ok('return { cancelled: true' in _p, 'F2b a decline returns rather than writing')
_h = nocomment(fn('handleFbaInventoryUpload'))
ok('result.cancelled' in _h, 'F3 and the handler reports it')

# The backdrop must CANCEL: the destructive choice cannot be what a stray
# click lands on.
_d = fn('uploadGuardDialog')
ok('if (e.target === dlg) done(false)' in _d,
   'F4 clicking the backdrop cancels rather than proceeding')
ok("done(false)" in _d and "done(true)" in _d, 'F4b both answers are reachable')
ok('esc2(c.text)' in _d and 'esc2(title)' in _d,
   'F5 nothing reaches the dialog markup unescaped')

eq('F6 version chip', len(re.findall(r'>v11\.\d+ \u00b7 [\d-]+<', s)), 1)
eq('F6b exactly one chip', len(re.findall(r'>v11\.\d+ \u00b7 [\d-]+<', s)), 1)

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
