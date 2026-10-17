# -*- coding: utf-8 -*-
"""v10.68 - Query Database: paste a whole .sql file and have it just work.

Jason pasted query_keywords_by_product.sql whole and got
    syntax error at or near ";"

exec_sql wraps the input as `select ... from (USER_QUERY) t`. v4.43 already
stripped a TRAILING `;`, but the .sql files in this repo are written as ONE live
section with the alternates parked in /* ... */ blocks underneath — so a
whole-file paste ENDS IN A COMMENT and the real `;` sits mid-string, landing
inside the wrapper.

The fix is in the RUNNER, not the files, so every multi-section .sql works.
What is most worth guarding:
  1. the real strip pipeline, driven against the REAL .sql files on disk —
     a test against a hand-written fixture would not have caught this, because
     the bug is specifically about the shape those files happen to have;
  2. that stripping did not become so greedy it eats a legitimate query;
  3. the multi-statement message, which replaces Postgres's opaque one.
"""
import io, os, re, sys, glob, json, subprocess

REPO = r'C:\Users\Jason\digital-forecast-engine'
SRC  = os.path.join(REPO, 'index.html')
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(SRC, encoding='utf-8').read()
js   = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond: passed += 1; print('  ok  ' + name)
    else:    failed += 1; print('  FAIL  ' + name)

# ---------------------------------------------------------------- A. static
print('\n== A. the fix is where it belongs ==')

run = js[js.index('async function runDbQuery()'):]
run = run[:run.index('\nasync function ') if '\nasync function ' in run[10:] else len(run)]

ok('v10.68 - strip TRAILING comments too' in run,
   'trailing-comment strip lives inside runDbQuery')
ok(run.count('while (true) {') == 2,
   'exactly TWO strip loops - leading (v4.43) and trailing (v10.68)')
ok(run.index('v10.68 - strip TRAILING') < run.index('Strip LEADING'),
   'trailing strip runs BEFORE the leading one (it re-exposes the `;`)')
ok("sql = sql.replace(/;\\s*$/, '');" in run,
   'the loop re-strips the `;` the comment was hiding')
ok('_noStr' in run and "replace(/'(?:[^']|'')*'/g" in run,
   'string literals are blanked before the multi-statement check')
ok('more than one SQL statement' in run,
   'the opaque Postgres error is replaced by a named cause')
ok(run.index('startsWith(\'WITH\')') < run.index('_noStr'),
   'the multi-statement check runs AFTER the SELECT/WITH guard')

# the whole point is that the FILES were not touched
sqls = sorted(glob.glob(os.path.join(REPO, 'query_*.sql')))
ok(len(sqls) >= 3, 'the repo still has its multi-section .sql files (%d)' % len(sqls))

# --------------------------------------------------------------- B. behaviour
print('\n== B. BEHAVIOUR (real sliced pipeline driven in node) ==')

def grab(start_marker, end_marker):
    i = run.index(start_marker)
    j = run.index(end_marker, i) + len(end_marker)
    return run[i:j]

trail_semi = grab("sql = sql.replace(/;\\s*$/g, '').trim();",
                  "sql = sql.replace(/;\\s*$/g, '').trim();")
trail_loop = grab('// v10.68 - strip TRAILING comments too', "sql = sql.trim();")
lead_loop  = grab('// Strip LEADING -- line comments', 'if (sql === before) break;\n  }')
stripped_l = grab("const stripped = sql.replace(/--.*$/gm,'')",
                  ".trim().toUpperCase();")
nostr_l    = grab("const _noStr = stripped.replace(", '"QQ");')

HARNESS = r"""
function runStrip(input) {
  let sql = String(input).trim();
__TRAIL_SEMI__
__TRAIL_LOOP__
__LEAD_LOOP__
  __STRIPPED__
  __NOSTR__
  return {
    sql,
    startsOk: stripped.startsWith('SELECT') || stripped.startsWith('WITH'),
    multiStatement: _noStr.includes(';'),
  };
}
const results = {};
const _cases = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
for (const [name, text] of Object.entries(_cases)) {
  try { results[name] = runStrip(text); }
  catch (e) { results[name] = { error: String(e && e.message) }; }
}
console.log(JSON.stringify(results));
"""
HARNESS = (HARNESS
  .replace('__TRAIL_SEMI__', trail_semi)
  .replace('__TRAIL_LOOP__', trail_loop)
  .replace('__LEAD_LOOP__',  lead_loop)
  .replace('__STRIPPED__',   stripped_l)
  .replace('__NOSTR__',      nostr_l))

hpath = os.path.join(SP, 'test_v1068.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)

# --- the cases. The real files on disk are the ones that mattered.
cases = {}
for p in sqls:
    cases['FILE:' + os.path.basename(p)] = io.open(p, encoding='utf-8').read()

cases['plain'] = 'select 1'
cases['trailing_semi'] = 'select 1;'
cases['leading_comment'] = '-- explainer\nselect 1;'
cases['leading_block'] = '/* explainer\n   spans lines */\nselect 1;'
# the exact shape that broke: live section, `;`, then parked alternates
cases['live_then_parked'] = (
    '-- header comment\n\nselect a, b\nfrom t\norder by a;\n\n\n'
    '-- ====\n-- SECTION 1\n-- ====\n\n/*\nselect x from y;\n*/\n\n'
    '/*\nselect z from w;\n*/\n')
# a genuine two-statement paste must still be REFUSED, not silently truncated
cases['two_statements'] = 'select 1;\nselect 2'
# a semicolon inside a string literal is not a separator
cases['semi_in_string'] = "select 'a;b' as x from t"
cases['semi_in_string_trailing'] = "select 'a;b' as x from t;"
# stripping must not eat the query itself
cases['block_comment_midquery'] = 'select a /* inline */, b from t;'
cases['with_cte'] = 'with c as (select 1) select * from c;'
cases['comment_only'] = '-- nothing here\n'

cpath = os.path.join(SP, 'test_v1068_cases.json')
io.open(cpath, 'w', encoding='utf-8').write(json.dumps(cases))
res = json.loads(subprocess.run(
    ['node', hpath, cpath],
    capture_output=True, text=True, check=True).stdout)

for name in cases:
    ok('error' not in res[name], 'no throw: %s' % name)

print('\n-- the real files (this is the bug) --')
for p in sqls:
    k = 'FILE:' + os.path.basename(p)
    r = res[k]
    ok(not r['multiStatement'],
       '%s -> no surviving `;` (would have been a syntax error)' % os.path.basename(p))
    ok(r['startsOk'],
       '%s -> reduces to a real SELECT/WITH' % os.path.basename(p))
    ok(not r['sql'].rstrip().endswith('*/'),
       '%s -> does not end inside a parked comment' % os.path.basename(p))

print('\n-- the shape, isolated --')
r = res['live_then_parked']
ok(r['sql'] == 'select a, b\nfrom t\norder by a',
   'live section survives verbatim, parked alternates + `;` stripped')
ok(not r['multiStatement'], '  and it is not flagged multi-statement')
ok(r['startsOk'], '  and it still starts with SELECT')

print('\n-- stripping is not over-greedy --')
ok(res['plain']['sql'] == 'select 1', 'a bare query is untouched')
ok(res['trailing_semi']['sql'] == 'select 1', 'trailing `;` stripped')
ok(res['leading_comment']['sql'] == 'select 1', 'leading line comment stripped')
ok(res['leading_block']['sql'] == 'select 1', 'leading block comment stripped')
ok(res['block_comment_midquery']['sql'] == 'select a /* inline */, b from t',
   'an INLINE comment inside the query is preserved')
ok(res['with_cte']['sql'] == 'with c as (select 1) select * from c',
   'a WITH ... SELECT survives intact')
ok(res['with_cte']['startsOk'], '  and still passes the WITH guard')

print('\n-- the refusals still refuse --')
ok(res['two_statements']['multiStatement'],
   'a genuine two-statement paste IS flagged (not silently truncated)')
ok(not res['semi_in_string']['multiStatement'],
   "a `;` inside a string literal is NOT mistaken for a separator")
ok(not res['semi_in_string_trailing']['multiStatement'],
   '  same with a trailing `;` also present')
ok(res['semi_in_string_trailing']['sql'] == "select 'a;b' as x from t",
   '  and the literal is left intact')
ok(not res['comment_only']['startsOk'],
   'a comment-only paste does not pass the SELECT guard')

# --------------------------------------------------- C. regression guard
print('\n== C. regression guard (the OLD runner really was broken) ==')

OLD = r"""
function oldStrip(input) {
  let sql = String(input).trim();
  sql = sql.replace(/;\s*$/g, '').trim();
  while (true) {
    const before = sql;
    sql = sql.replace(/^\s*--[^\n]*\n?/, '');
    sql = sql.replace(/^\s*\/\*[\s\S]*?\*\/\s*/, '');
    sql = sql.replace(/^\s+/, '');
    if (sql === before) break;
  }
  const stripped = sql.replace(/--.*$/gm,'').replace(/\/\*[\s\S]*?\*\//g,'').trim().toUpperCase();
  return { sql, hadSemi: stripped.includes(';') };
}
const out = {};
const _gc = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
for (const [k, v] of Object.entries(_gc)) out[k] = oldStrip(v);
console.log(JSON.stringify(out));
"""
opath = os.path.join(SP, 'test_v1068_old.js')
io.open(opath, 'w', encoding='utf-8').write(OLD)

guard_cases = {'live_then_parked': cases['live_then_parked']}
for p in sqls:
    guard_cases['FILE:' + os.path.basename(p)] = io.open(p, encoding='utf-8').read()

gpath = os.path.join(SP, 'test_v1068_guard.json')
io.open(gpath, 'w', encoding='utf-8').write(json.dumps(guard_cases))
old = json.loads(subprocess.run(
    ['node', opath, gpath],
    capture_output=True, text=True, check=True).stdout)

ok(old['live_then_parked']['hadSemi'],
   'pre-v10.68 left a `;` in the wrapper on the isolated shape')
broke = [k for k in old if k.startswith('FILE:') and old[k]['hadSemi']]
ok(len(broke) >= 1,
   'pre-v10.68 broke on %d of the real .sql file(s): %s'
   % (len(broke), ', '.join(sorted(x[5:] for x in broke))))
for k in broke:
    ok(not res[k]['multiStatement'],
       '  %s is fixed now' % k[5:])

# ------------------------------------------------------------------- report
print('\n%s' % ('-' * 58))
print('v10.68: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
