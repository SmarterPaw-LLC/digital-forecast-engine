#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.99 - master_id stamped against the LIVE products table.

Jason, mid-upload:

    FBA inventory upload error: insert or update on table
    "fba_inventory_snapshots" violates foreign key constraint
    "fba_inventory_snapshots_master_id_fkey"

/!\ CAUSE, MEASURED. `allProducts` is a snapshot taken at page load. Two
merges on 2026-11-10 DELETED the exact rows his file resolves to:

    16:46  SP-TEMP-B0HJDBGVVW -> SP-0560  Rudolph's Rollies
    16:37  SP-TEMP-B0HJDDN85X -> SP-0555  Frosticles

His tab had been open since before them, so the uploader stamped two
master_ids that no longer exist and Postgres rejected THE WHOLE BATCH with a
message naming no ASIN, no product and no remedy.

Why nothing caught it:
  - the FK is nullable, so an UNMATCHED asin (master_id null) is legal; only
    a DEAD id fails, and nothing ever checked that an id was still alive.
  - the products auto-create swallowed its error, so the one place that
    reloads the catalogue could fail silently.
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
        print("  FAIL  %s%s" % (label, ("  got: %s" % ascii(extra)) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def nocomment(t):
    return re.sub(r"(?m)^\s*//.*$", "", t)


def fn_flat(name):
    i = js.index("function " + name + "(")
    # /!\ KEEP THE `async` PREFIX. Slicing from the `function` keyword drops
    # it, and the sliced copy then fails to parse on its own `await` - which
    # looks like a bug in the code under test rather than in the harness.
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def fn_span(name):
    """Slice a function by the NEXT top-level declaration rather than by a
    closing brace: the big uploaders nest template literals that the brace
    matcher cannot walk (the v11.91 lesson)."""
    i = js.index("function " + name + "(")
    m = re.search(r"\n(?:async )?function [A-Za-z0-9_$]+\(", js[i + 10:])
    return js[i: i + 10 + m.start()] if m else js[i:]


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.99  the uploader checks that the product still exists")
print("=" * 68)

STAMP = fn_flat("stampMasterIds")
NOTE  = fn_flat("stampNote")
INV   = fn_span("parseFbaInventorySnapshot")

# ===========================================================================
print("\nA. one helper, one registry")
# ===========================================================================
eq("A1  stampMasterIds is declared exactly once",
   len(re.findall(r"async function stampMasterIds\(", js)), 1)
eq("A2  stampNote is declared exactly once",
   len(re.findall(r"function stampNote\(", js)), 1)
ok("const MASTER_ID_UPLOADERS = {" in js, "A3  the uploader set is declared")

REG = re.search(r"const MASTER_ID_UPLOADERS = \{([\s\S]*?)\n\};", js).group(1)
REG_FNS = re.findall(r"^\s*([A-Za-z0-9_$]+):", REG, re.M)
eq("A4  six uploaders declared", len(REG_FNS), 6)
ok(set(REG_FNS) == {"parseSalesWeekly", "parseAmazonSqpAsinView",
                    "parseFbaInventorySnapshot", "parseFbaShipment",
                    "parseSkuEconomics", "parseEuSkuEconomics"},
   "A5  ...and they are the six that stamp an FK-carrying table", sorted(REG_FNS))

# /!\ A FAILED CHECK MUST NOT PASS SILENTLY - carrying on writes the batch
# this exists to stop.
ok("throw new Error('Could not verify product IDs before upload: '" in STAMP,
   "A6  /!\\ a failed verification throws rather than writing anyway")
ok("await loadProducts();" in STAMP, "A7  a miss refreshes the catalogue")
# ...and only on a miss. The clean path must not pay for it.
ok(STAMP.index("if (!stale.size) return") < STAMP.index("await loadProducts();"),
   "A8  /!\\ ...only AFTER the no-stale early return, so a clean upload does not")

# ===========================================================================
print("\nB. the real stampMasterIds, driven")
# ===========================================================================
DRIVER = r"""
'use strict';
let allProducts = [];
let loadCalls = 0;
let queries = [];

// The catalogue as it stands in the DATABASE after the 2026-11-10 merges.
const LIVE = [
  { master_id: 'SP-0560', asin: 'B0HJDBGVVW', title: "Rudolph's Rollies" },
  { master_id: 'SP-0555', asin: 'B0HJDDN85X', title: 'Frosticles' },
  { master_id: 'SP-0001', asin: 'B00AAA0001', title: 'Pawty Mix' },
  { master_id: 'SP-TEMP-B00ZZZ9999', asin: null, title: 'Unknown' },
];
const LIVE_IDS = new Set(LIVE.map(p => p.master_id));

async function loadProducts() { loadCalls++; allProducts = LIVE.slice(); }

function mkSb(opts) {
  opts = opts || {};
  return { from: () => ({ select: () => ({ in: (col, ids) => {
    queries.push(ids.slice());
    if (opts.err) return Promise.resolve({ data: null, error: { message: opts.err } });
    return Promise.resolve({
      data: ids.filter(i => LIVE_IDS.has(i)).map(m => ({ master_id: m })), error: null });
  } }) }) };
}

__STAMP__
__NOTE__

function reset(stale) {
  loadCalls = 0; queries = [];
  // The TAB's copy: taken before the merges, so it still holds the dead ids.
  allProducts = stale ? [
    { master_id: 'SP-TEMP-B0HJDBGVVW', asin: 'B0HJDBGVVW' },
    { master_id: 'SP-TEMP-B0HJDDN85X', asin: 'B0HJDDN85X' },
    { master_id: 'SP-0001',            asin: 'B00AAA0001' },
  ] : LIVE.slice();
}

(async () => {
  const out = {};

  // --- B1 nothing stale -------------------------------------------------
  reset(false);
  let rows = [
    { asin: 'B00AAA0001', master_id: 'SP-0001', n: 1 },
    { asin: 'B0HJDBGVVW', master_id: 'SP-0560', n: 2 },
  ];
  out.clean = await stampMasterIds(mkSb(), rows);
  out.cleanLoads = loadCalls;
  out.cleanIds = rows.map(r => r.master_id);
  out.cleanQueries = queries.length;

  // --- B2 the real incident --------------------------------------------
  reset(true);
  rows = [
    { asin: 'B0HJDBGVVW', master_id: 'SP-TEMP-B0HJDBGVVW' },
    { asin: 'B0HJDDN85X', master_id: 'SP-TEMP-B0HJDDN85X' },
    { asin: 'B00AAA0001', master_id: 'SP-0001' },
  ];
  out.incident = await stampMasterIds(mkSb(), rows);
  out.incidentIds = rows.map(r => r.master_id);
  out.incidentLoads = loadCalls;

  // --- B3 a stale id whose ASIN resolves to nothing ---------------------
  reset(true);
  rows = [{ asin: 'B0NOTREAL1', master_id: 'SP-TEMP-GONE' }];
  out.gone = await stampMasterIds(mkSb(), rows);
  out.goneId = rows[0].master_id;

  // --- B4 the SP-TEMP fallback -----------------------------------------
  reset(true);
  rows = [{ asin: 'B00ZZZ9999', master_id: 'SP-TEMP-DEAD' }];
  out.temp = await stampMasterIds(mkSb(), rows);
  out.tempId = rows[0].master_id;

  // --- B5 the verification itself fails ---------------------------------
  reset(true);
  rows = [{ asin: 'B00AAA0001', master_id: 'SP-0001' }];
  try { await stampMasterIds(mkSb({ err: 'statement timeout' }), rows); out.threw = false; }
  catch (e) { out.threw = true; out.throwMsg = e.message; }

  // --- B6 nothing to check ----------------------------------------------
  reset(false);
  out.emptyRows = await stampMasterIds(mkSb(), []);
  out.emptyQueries = queries.length;
  reset(false);
  out.allNull = await stampMasterIds(mkSb(), [{ asin: 'X', master_id: null }]);
  out.allNullQueries = queries.length;

  // --- B7 distinct ids only, and chunked at 200 -------------------------
  reset(false);
  rows = [];
  for (let i = 0; i < 500; i++) rows.push({ asin: 'B00AAA0001', master_id: 'SP-0001' });
  await stampMasterIds(mkSb(), rows);
  out.dedupQuerySizes = queries.map(q => q.length);

  reset(false);
  rows = [];
  for (let i = 0; i < 250; i++) rows.push({ asin: 'A' + i, master_id: 'SP-0001' + i });
  await stampMasterIds(mkSb(), rows);
  out.chunkSizes = queries.map(q => q.length);

  // --- B8 a different asin key ------------------------------------------
  reset(true);
  rows = [{ child_asin: 'B0HJDDN85X', master_id: 'SP-TEMP-B0HJDDN85X' }];
  await stampMasterIds(mkSb(), rows, 'child_asin');
  out.altKeyId = rows[0].master_id;

  // --- B9 stampNote -----------------------------------------------------
  out.noteClean = stampNote({ checked: 3, repointed: 0, dropped: [] });
  out.noteNull  = stampNote(null);
  out.noteBoth  = stampNote({ checked: 3, repointed: 2, dropped: ['B0X'] });

  console.log(JSON.stringify(out));
})();
"""

R = run_node(os.path.join(SP, "_v1199_a.js"),
             DRIVER.replace("__STAMP__", STAMP).replace("__NOTE__", NOTE))

# B1 - the clean path costs one query and changes nothing.
eq("B1  clean: nothing re-pointed", R["clean"]["repointed"], 0)
eq("B2  clean: nothing dropped", R["clean"]["dropped"], [])
eq("B3  clean: ids untouched", R["cleanIds"], ["SP-0001", "SP-0560"])
eq("B4  /!\\ clean: loadProducts NOT re-run", R["cleanLoads"], 0)
eq("B5  clean: exactly one verification query", R["cleanQueries"], 1)

# B2 - THE INCIDENT. Both dead ids land on their merge survivors.
eq("B6  /!\\ incident: both dead ids re-pointed", R["incident"]["repointed"], 2)
eq("B7  /!\\ ...to SP-0560 and SP-0555, not to null",
   R["incidentIds"], ["SP-0560", "SP-0555", "SP-0001"])
eq("B8  incident: nothing dropped", R["incident"]["dropped"], [])
eq("B9  incident: the catalogue was refreshed once", R["incidentLoads"], 1)

# B3 - an ASIN that resolves to nothing is nulled AND NAMED.
eq("B10 unresolvable: master_id nulled (the FK accepts null)", R["goneId"], None)
eq("B11 /!\\ ...and the ASIN is named, not counted", R["gone"]["dropped"], ["B0NOTREAL1"])
eq("B12 unresolvable: not counted as a re-point", R["gone"]["repointed"], 0)

# B4 - the SP-TEMP fallback the uploaders already use.
eq("B13 SP-TEMP fallback re-points", R["tempId"], "SP-TEMP-B00ZZZ9999")

# B5 - a failed check throws.
ok(R["threw"], "B14 /!\\ a failed verification throws")
ok("statement timeout" in R.get("throwMsg", ""),
   "B15 ...carrying the real reason, not the FK error that would follow")

# B6 - nothing to check means no round trip at all.
eq("B16 no rows: no query", R["emptyQueries"], 0)
eq("B17 all-null master_ids: no query", R["allNullQueries"], 0)
eq("B18 no rows: reported as checked 0", R["emptyRows"]["checked"], 0)

# B7 - distinct ids, chunked.
eq("B19 /!\\ 500 rows of one id is ONE id checked", R["dedupQuerySizes"], [1])
eq("B20 250 distinct ids chunk at 200", R["chunkSizes"], [200, 50])

# B8/B9
eq("B21 a non-default asin key is honoured", R["altKeyId"], "SP-0555")
eq("B22 stampNote is empty when nothing moved", R["noteClean"], "")
eq("B23 stampNote tolerates null", R["noteNull"], "")
ok("2 row(s) re-pointed" in R["noteBoth"] and "1 ASIN(s) left unlinked" in R["noteBoth"],
   "B24 stampNote names both halves", R["noteBoth"])

# ===========================================================================
print("\nC. THE DEFECT REPRODUCED")
# ===========================================================================
# The pre-v11.99 path is simply "resolve through allProducts and write". Run
# it beside the shipped one on the same stale tab state, so the FK violation
# is a MEASUREMENT rather than a story about what used to happen.
REPRO = r"""
'use strict';
let allProducts = [];
let loadCalls = 0;
let queries = [];
const LIVE = [
  { master_id: 'SP-0560', asin: 'B0HJDBGVVW' },
  { master_id: 'SP-0555', asin: 'B0HJDDN85X' },
];
const LIVE_IDS = new Set(LIVE.map(p => p.master_id));
async function loadProducts() { loadCalls++; allProducts = LIVE.slice(); }
function mkSb() {
  return { from: () => ({ select: () => ({ in: (c, ids) => {
    queries.push(ids.slice());
    return Promise.resolve({ data: ids.filter(i => LIVE_IDS.has(i)).map(m => ({ master_id: m })), error: null });
  } }) }) };
}
__STAMP__

// The tab's product list, taken before the merges.
const STALE_TAB = [
  { master_id: 'SP-TEMP-B0HJDBGVVW', asin: 'B0HJDBGVVW' },
  { master_id: 'SP-TEMP-B0HJDDN85X', asin: 'B0HJDDN85X' },
];
const FILE = [{ asin: 'B0HJDBGVVW' }, { asin: 'B0HJDDN85X' }];

// How the uploader builds a payload (the line is identical in all six).
const build = (cat) => FILE.map(r => {
  const prod = cat.find(p => p.asin === r.asin) || cat.find(p => p.master_id === 'SP-TEMP-' + r.asin);
  return { asin: r.asin, master_id: prod ? prod.master_id : null };
});

(async () => {
  const out = {};
  allProducts = STALE_TAB.slice();
  const before = build(allProducts);
  out.before = before.map(r => r.master_id);
  out.beforeDead = before.filter(r => r.master_id && !LIVE_IDS.has(r.master_id)).length;

  allProducts = STALE_TAB.slice();
  const after = build(allProducts);
  await stampMasterIds(mkSb(), after);
  out.after = after.map(r => r.master_id);
  out.afterDead = after.filter(r => r.master_id && !LIVE_IDS.has(r.master_id)).length;
  console.log(JSON.stringify(out));
})();
"""
D = run_node(os.path.join(SP, "_v1199_b.js"), REPRO.replace("__STAMP__", STAMP))

eq("C1  /!\\ pre-v11.99 stamps the two DELETED ids",
   D["before"], ["SP-TEMP-B0HJDBGVVW", "SP-TEMP-B0HJDDN85X"])
eq("C2  /!\\ ...both of which violate the FK", D["beforeDead"], 2)
eq("C3  shipped: the survivors", D["after"], ["SP-0560", "SP-0555"])
eq("C4  /!\\ ...and NO dead id survives the stamp", D["afterDead"], 0)

# ===========================================================================
print("\nD. the registry and the code agree, in BOTH directions")
# ===========================================================================
for name in sorted(REG_FNS):
    body = fn_span(name)
    ok("stampMasterIds(" in body, "D   %s calls stampMasterIds" % name)

# /!\ AND NO SEVENTH. Any parse* that resolves an ASIN to a master_id and
# writes it into a table carrying the FK must be declared, or this release
# fixes five uploaders and leaves one able to throw the same error.
FK_TABLES = set(re.findall(r"^\s*([a-z_]+):\s*\{ d: 'reassign' \}",
                           re.search(r"const MERGE_MASTER_ID_TABLES = \{([\s\S]*?)\n\};", js).group(1), re.M))
ok(len(FK_TABLES) >= 20, "D90 the v11.90 FK table registry was read", len(FK_TABLES))

missing = []
for m in re.finditer(r"(?:async )?function (parse[A-Za-z0-9_$]+)\(", js):
    name = m.group(1)
    body = fn_span(name)
    if "allProducts.find(p => p.asin" not in body:
        continue
    writes = {t for t in FK_TABLES
              if re.search(r"\.from\('%s'\)\s*\n?\s*\.?(upsert|insert)" % t, body)}
    if writes and name not in REG_FNS:
        missing.append((name, sorted(writes)))
eq("D91 /!\\ no undeclared uploader stamps an FK table", missing, [])

# ===========================================================================
print("\nE. where the stamp sits in the inventory uploader")
# ===========================================================================
INVC = nocomment(INV)
ok("stampMasterIds(sb, payload)" in INVC, "E1  the inventory payload is stamped")
# /!\ BEFORE the guard: the guard shows the operator a payload, and a payload
# carrying a dead id cannot be written whatever they answer.
ok(INVC.index("stampMasterIds(sb, payload)") < INVC.index("uploadGuardConfirm('fba_inventory'"),
   "E2  /!\\ ...BEFORE uploadGuardConfirm, so the figures confirmed are the ones that land")
ok(INVC.index("stampMasterIds(sb, payload)") < INVC.index(".from('fba_inventory_snapshots')"),
   "E3  ...and before the first write")
ok("aggregated: aggregated.length, stamp }" in INVC, "E4  the result carries it")
ok("${stampNote(result.stamp)}" in js, "E5  ...and the status line reports it")

# The legacy `inventory` upsert reads master_id off the SAME payload rows, so
# one stamp covers both tables rather than needing a second call.
ok("master_id: r.master_id," in INVC,
   "E6  the legacy inventory rows reuse the stamped payload")

# /!\ AND THE AUTO-CREATE STOPPED SWALLOWING ITS ERROR.
ok("product auto-create failed" in INVC,
   "E7  /!\\ a failed product auto-create is no longer silent")

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
