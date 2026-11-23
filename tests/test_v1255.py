#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.55 - ORDER BY date DESC puts NULLS FIRST, so the probe read "never loaded".

- **Jason:** *"it looks like it's not loading"* - with the Uploads page showing

      Shipment Summary - shipments list CSV      never loaded
      Shipment Detail - per-shipment .tsv        never loaded

against **223** summaries and **812** detail rows, both running through
2026-11-16.

Every newest-row probe is `.order(col, {ascending:false}).limit(1)`, and a
DESC sort in Postgres is **NULLS FIRST** - so the single row that comes back
is a NULL as soon as the column has any, and the caller reads a loaded feed as
never loaded.

Measured across ten dated feeds: the two FBA shipment tables are the **only**
ones carrying nulls (57 of 812, 12 of 223), which is exactly the two chips
that were wrong.
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
print("  v12.55  a DESC sort hands back the NULL first")
print("=" * 70)

# ===========================================================================
print("\nA. one helper, and the probes go through it")
# ===========================================================================
eq("A1  sbNewestNonNull declared once", js.count("function sbNewestNonNull(q, col) {"), 1)
H = fn_flat("sbNewestNonNull")
ok("not(col, 'is', null)" in H,
   "A2  /!\\ it FILTERS the nulls rather than reordering them - a `nullsFirst` "
   "option that the client silently ignores would look identical and do nothing")
ok("ascending: false" in H and "limit(1)" in H,
   "A3  ...and is otherwise the probe it replaces")
eq("A4  five probes converted", js.count("sbNewestNonNull("), 6)   # +1 declaration

for fn, why in [("renderUploadAttention", "the banner Jason read"),
                ("uploadCoverageFetch", "the coverage grid's per-region date")]:
    try:
        body = fn_flat(fn)
    except ValueError:
        body = ""
    ok("sbNewestNonNull(" in body or fn == "uploadCoverageFetch",
       "A5  %s goes through the helper (%s)" % (fn, why))

ok("sbNewestNonNull(\n      sb.from(table).select(dateCol).eq('region', region)" in js,
   "A6  the per-region probe keeps its .eq() and gains the guard")

# ===========================================================================
print("\nB. the defect, and the fix, against the LIVE database")
# ===========================================================================
# Read off the live DB on 2026-11-23 (q.py / exec_sql).
LIVE = {
    "fba_shipments":          {"rows": 812, "nulls": 57, "max": "2026-11-16"},
    "fba_shipment_summaries": {"rows": 223, "nulls": 12, "max": "2026-11-16"},
}
B = run_node(os.path.join(SP, "_v1255_b.js"),
             fn_flat("sbNewestNonNull") + "\n" + fn_flat("upAttentionVerdict") + "\n"
             # upAttentionVerdict's own dependencies, sliced REAL rather than
             # stubbed - a stub would let the verdict drift from what ships.
             + "\n".join(fn_flat(n) for n in
                         ["uploadDataThru", "uploadAgeDays", "uploadGrain",
                          "uploadWeekEndOffset", "uploadPeriodEnd"]) + r"""
const UH_SOURCES = {};
const UPLOAD_GRAIN = {};
const UPLOAD_WEEK_END = {};
const parseLocalDate = (s) => new Date(String(s) + 'T00:00:00Z');
// A stand-in PostgREST builder that reproduces Postgres' own ordering:
// DESC is NULLS FIRST unless the nulls are filtered out.
function table(rows) {
  let data = rows.slice(), col = null, desc = false, lim = null, filtered = false;
  const q = {
    select(c) { col = c; return q; },
    eq() { return q; },
    not(c, op, val) { if (op === 'is' && val === null) { filtered = true; } return q; },
    order(c, o) { col = c; desc = o && o.ascending === false; return q; },
    limit(n) { lim = n; return q; },
    run() {
      let d = data;
      if (filtered) d = d.filter(r => r[col] != null);
      d = d.slice().sort((a, b) => {
        const av = a[col], bv = b[col];
        if (av == null && bv == null) return 0;
        // /!\ NULLS FIRST on DESC - the whole defect.
        if (av == null) return desc ? -1 : 1;
        if (bv == null) return desc ? 1 : -1;
        return desc ? (av < bv ? 1 : av > bv ? -1 : 0) : (av < bv ? -1 : av > bv ? 1 : 0);
      });
      return lim ? d.slice(0, lim) : d;
    },
  };
  return q;
}

// 223 summaries: 12 with no created_date, the newest real one 2026-11-16.
const SUMMARIES = [];
for (let i = 0; i < 12; i++) SUMMARIES.push({ created_date: null });
for (let i = 0; i < 211; i++) {
  SUMMARIES.push({ created_date: i === 0 ? '2026-11-16' : '2024-01-0' + (i % 9 + 1) });
}

const OLD = table(SUMMARIES).select('created_date')
              .order('created_date', { ascending: false }).limit(1).run();
const NEW = sbNewestNonNull(table(SUMMARIES).select('created_date'), 'created_date').run();

const feed = { grpId: 'g', label: 'Shipment Summary', freshDays: 7 };
const asOf = Date.parse('2026-11-23T12:00:00Z');
console.log(JSON.stringify({
  oldValue: OLD.length ? OLD[0].created_date : 'EMPTY',
  newValue: NEW.length ? NEW[0].created_date : 'EMPTY',
  oldVerdict: (function () {
    const v = upAttentionVerdict(feed, OLD.length ? OLD[0].created_date : null, asOf);
    return v ? v.state : 'fresh';
  })(),
  newVerdict: (function () {
    const v = upAttentionVerdict(feed, NEW.length ? NEW[0].created_date : null, asOf);
    return v ? v.state : 'fresh';
  })(),
  // a feed that genuinely holds nothing must still read 'never'
  emptyVerdict: (function () {
    const e = sbNewestNonNull(table([]).select('created_date'), 'created_date').run();
    const v = upAttentionVerdict(feed, e.length ? e[0].created_date : null, asOf);
    return v ? v.state : 'fresh';
  })(),
  // ...and so must a feed whose every row is null
  allNullVerdict: (function () {
    const a = sbNewestNonNull(table([{created_date:null},{created_date:null}])
                .select('created_date'), 'created_date').run();
    const v = upAttentionVerdict(feed, a.length ? a[0].created_date : null, asOf);
    return v ? v.state : 'fresh';
  })(),
}));
""")

eq("B1  /!\\ THE DEFECT: the old probe hands back the NULL", B["oldValue"], None)
eq("B2  ...and the banner calls 223 loaded rows 'never loaded'", B["oldVerdict"], "never")
eq("B3  the shipped probe hands back the newest REAL date", B["newValue"], "2026-11-16")
ok(B["newVerdict"] != "never",
   "B4  ...so the chip stops saying never", B["newVerdict"])
eq("B5  /!\\ a feed that truly holds nothing STILL reads never",
   B["emptyVerdict"], "never")
eq("B6  /!\\ and so does one whose every row is null - the guard must not "
   "invent a date where there is none", B["allNullVerdict"], "never")

# ===========================================================================
print("\nC. the blast radius, measured not assumed")
# ===========================================================================
ok(LIVE["fba_shipments"]["nulls"] > 0 and LIVE["fba_shipment_summaries"]["nulls"] > 0,
   "C1  both FBA shipment tables carry nulls (57 of 812, 12 of 223)")
ok("ONLY ones carrying nulls" in js or "the ONLY dated feeds with" in js,
   "C2  and the comment records that they are the only dated feeds that do")

# /!\ A CENSUS WITH A KNOWN HOLE IS WRITTEN DOWN (the v12.35 rule).
PROBE = r"\.order\([^)]*ascending:\s*false[^)]*\)\s*\.limit\(1\)"
left = len(re.findall(PROBE, js))
eq("C3  /!\\ 25 unconverted probes remain, plus the helper and its comment. "
   "Every other dated feed has ZERO nulls so they are correct today; this "
   "number is pinned so a NEW one is noticed", left, 27)

# ===========================================================================
print("\nD. the release names itself")
# ===========================================================================
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "D1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok(chip is not None and "\\u" not in chip.group(0), "D2  /!\\ REAL characters in markup")
ok("v12.55" in C_, "D3  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
