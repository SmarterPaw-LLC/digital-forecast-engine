#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.60 - a seasonality save that matched NOTHING looked exactly like one
that saved.

- **Jason:** *"i changed pawty mix seasonality to mix, which changed the
  status to plan to ship, but on reload, the seasonality had reverted. not
  sure why. i did it again and it appears to have saved this time."*

PostgREST answers a no-match UPDATE with **204 No Content**, so supabase-js
hands back `{ data: null, error: null }` - the same shape a row that really
changed produces. All seven seasonality writers read that as success: no
alert, an audit entry written, the grid repainted off a re-fetch that could
only agree with whatever was already stored.

Measured on the live database, 2026-11-23: `audit_log` carries TWO
`seasonality.set_method` rows for `SP-0055` (13:40:03 and 15:14:33 CT), and
RLS on `products` is wide open (`qual: true` on UPDATE) - so an audit entry
proves the request returned 2xx and proves **nothing at all** about whether a
row changed. That gap is what this release closes.
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0


def ok(cond, label, extra=None):
    global passed, failed
    if cond:
        passed += 1; print("  ok    %s" % label)
    else:
        failed += 1
        print("  FAIL  %s%s" % (label, ("  got: %s" % extra) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.60  a save that matched nothing is not a save")
print("=" * 70)

# ===========================================================================
print("\nA. one helper, and every seasonality writer goes through it")
# ===========================================================================
eq("A1  the helper is declared exactly once",
   js.count("async function seaUpdateChecked("), 1)
eq("A2  /!\\ and ALL SEVEN writers call it - a consolidation that leaves a "
   "copy behind is not a consolidation (hard rule #1 / #5)",
   js.count("await seaUpdateChecked(sb,"), 7)

# The seasonality writers all live in one span, from the helper down to the
# curve resolver; the bare shape must be gone from every one of them.
SEA_SPAN = js[js.index("async function seaUpdateChecked("):
              js.index("// Resolve which curve to use for a given product")]
ok("sb.from('products').update(" not in SEA_SPAN,
   "A3  /!\\ no seasonality writer still issues the bare update - the shape "
   "whose 204 cannot be told from a save")
ok(".select('master_id,' + verifyCol)" in fn_flat("seaUpdateChecked"),
   "A4  it asks for the row BACK, which is the whole fix")

HELP = fn_flat("seaUpdateChecked")
ok("rows.length !== 1" in HELP,
   "A5  /!\\ exactly one row, so a no-match AND a wider-than-intended update "
   "are both refused")

# ===========================================================================
print("\nB. the verify column is a scalar, never a curve")
# ===========================================================================
CALLS = re.findall(r"await seaUpdateChecked\(sb,[\s\S]*?,\s*'([a-z_]+)'\);", js)
eq("B1  seven calls, seven verify columns", len(CALLS), 7)
ok(set(CALLS) <= {"sea_method", "seasonal_type"},
   "B2  /!\\ every verify column is a SCALAR - a JSON curve could never "
   "compare equal to the one sent, so it is never verified this way", set(CALLS))
eq("B3  the two seasonal_type writers verify seasonal_type",
   CALLS.count("seasonal_type"), 2)
eq("B4  the five curve/method writers verify sea_method",
   CALLS.count("sea_method"), 5)

# ===========================================================================
print("\nC. the defect reproduced, and the fix driven beside it")
# ===========================================================================
HARNESS = fn_flat("seaUpdateChecked") + r"""
// A stub shaped exactly the way supabase-js answers. MATCHED decides whether
// the row existed; RETURN_NULL reproduces the pre-v12.60 call, which asked for
// no representation and therefore got 204 / data:null either way.
let MATCHED = 1, STORED = 'mix', RETURN_NULL = false, ERR = null;
const sb = {
  from() { return this; },
  update(p) { this._p = p; return this; },
  eq() { return this; },
  select(cols) {
    this._cols = cols;
    if (ERR) return Promise.resolve({ data: null, error: ERR });
    if (RETURN_NULL) return Promise.resolve({ data: null, error: null });
    const rows = [];
    for (let i = 0; i < MATCHED; i++) rows.push({ master_id: 'SP-0055', sea_method: STORED, seasonal_type: STORED });
    return Promise.resolve({ data: rows, error: null });
  },
  // The PRE-v12.60 shape: no .select(), so the promise resolves on .eq().
  then(res) { return Promise.resolve({ data: null, error: ERR }).then(res); },
};

// The pre-v12.60 writer, verbatim in shape: update -> eq -> read `error`.
async function oldWriter(payload) {
  const { error } = await sb.from('products').update(payload).eq('master_id', 'SP-0055');
  if (error) throw error;
  return 'saved';
}

(async () => {
  const out = {};

  // 1. THE DEFECT: nothing matched, and the old writer reports a save.
  MATCHED = 0; RETURN_NULL = true;
  out.oldOnNoMatch = await oldWriter({ sea_method: 'mix' }).catch(e => 'THREW: ' + e.message);

  // 2. The shipped helper, same state.
  RETURN_NULL = false;
  out.newOnNoMatch = await seaUpdateChecked(sb, { sea_method: 'mix' }, 'SP-0055', 'sea_method')
    .then(() => 'returned').catch(e => 'THREW: ' + e.message);

  // 3. A real save.
  MATCHED = 1; STORED = 'mix';
  out.newOnSave = await seaUpdateChecked(sb, { sea_method: 'mix' }, 'SP-0055', 'sea_method')
    .then(r => r.sea_method).catch(e => 'THREW: ' + e.message);
  out.colsAsked = sb._cols;

  // 4. The row came back carrying something else.
  STORED = 'calculated';
  out.newOnWrongValue = await seaUpdateChecked(sb, { sea_method: 'mix' }, 'SP-0055', 'sea_method')
    .then(() => 'returned').catch(e => 'THREW: ' + e.message);

  // 5. More than one row matched.
  MATCHED = 2; STORED = 'mix';
  out.newOnTwoRows = await seaUpdateChecked(sb, { sea_method: 'mix' }, 'SP-0055', 'sea_method')
    .then(() => 'returned').catch(e => 'THREW: ' + e.message);

  // 6. A payload that does not carry the verify column is NOT compared - the
  //    caller is saving something else about the row.
  MATCHED = 1; STORED = 'mix';
  out.newNoVerifyKey = await seaUpdateChecked(sb, { sea_min_weeks: 26 }, 'SP-0055', 'sea_method')
    .then(() => 'returned').catch(e => 'THREW: ' + e.message);

  // 7. A real Postgres error still surfaces as itself.
  ERR = { message: 'permission denied for table products' };
  out.newOnError = await seaUpdateChecked(sb, { sea_method: 'mix' }, 'SP-0055', 'sea_method')
    .then(() => 'returned').catch(e => 'THREW: ' + e.message);
  ERR = null;

  console.log(JSON.stringify(out));
})();
"""
C = run_node(os.path.join(SP, "_v1260_c.js"), HARNESS)

eq("C1  /!\\ THE DEFECT: nothing matched and the pre-v12.60 writer reported a "
   "SAVE - which is why an audit entry was written for a row that never moved",
   C["oldOnNoMatch"], "saved")
ok(C["newOnNoMatch"].startswith("THREW:"),
   "C2  /!\\ THE FIX: the same state now refuses", C["newOnNoMatch"])
ok("matched 0 rows" in C["newOnNoMatch"] and "nothing was stored" in C["newOnNoMatch"],
   "C3  ...and says so in the operator's terms, not Postgres'", C["newOnNoMatch"])
eq("C4  a real save returns the stored row", C["newOnSave"], "mix")
eq("C5  /!\\ and it asks for the KEY and the verify column only, never the "
   "whole row - these rows carry a 52-week curve",
   C["colsAsked"], "master_id,sea_method")
ok(C["newOnWrongValue"].startswith("THREW:") and "came back as" in C["newOnWrongValue"],
   "C6  /!\\ a row that came back carrying something ELSE is refused too - a "
   "write intercepted by a trigger or a stale payload is not a save",
   C["newOnWrongValue"])
ok(C["newOnTwoRows"].startswith("THREW:") and "matched 2 rows" in C["newOnTwoRows"],
   "C7  /!\\ and so is a wider-than-intended update", C["newOnTwoRows"])
eq("C8  a payload with no verify column is not compared - the caller is "
   "saving something else about the row", C["newNoVerifyKey"], "returned")
ok("permission denied" in C["newOnError"],
   "C9  a genuine Postgres error still surfaces as itself, unwrapped",
   C["newOnError"])

# ===========================================================================
print("\nD. the failure reaches the operator, and the dropdown goes back")
# ===========================================================================
SETM = fn_flat("seaSetMethod")
ok("Could not set method" in SETM and "renderSeasonalityList()" in SETM,
   "D1  /!\\ seaSetMethod's catch both ALERTS and repaints, so a refused save "
   "snaps the visible dropdown back to what is stored (v10.19: a control that "
   "looks like it worked is worse than one that refuses)")
ok(SETM.index("await seaUpdateChecked(sb,") < SETM.index("logAudit('seasonality.set_method'"),
   "D2  /!\\ the audit entry is written AFTER the row is confirmed - an audit "
   "log that records saves which did not happen is worse than none")

for fn, label in [("seaBulkApplyMids", "D3  bulk apply"),
                  ("seaBulkSetSeasonalType", "D4  bulk set type"),
                  ("seaBulkRevert", "D5  bulk revert")]:
    body = fn_flat(fn)
    ok("catch (e) { errors++" in body or "catch (e) { errors++;" in body
       or re.search(r"catch \(e\) \{\s*errors\+\+", body) is not None,
       "%s counts a refused row as an ERROR rather than as applied" % label)

# ===========================================================================
print("\nE. the rest of the file is written down, not quietly swept")
# ===========================================================================
BARE = len(re.findall(r"\.from\('products'\)\s*\.?\s*\n?\s*\.update\(", js))
ok(BARE >= 10,
   "E1  /!\\ THE OTHER products WRITERS ARE UNCONVERTED AND COUNTED. Only the "
   "seasonality ones are converted here; every other `.update()` on products "
   "has the same blind spot and is on the Still-open list (the v12.55 rule: "
   "a census with a known hole is written down, never quietly widened)", BARE)

# ===========================================================================
print("\nF. the release names itself")
# ===========================================================================
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "F1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok("v12.60" in C_, "F2  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
