#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.82 - the GA4 pull as a button, and the drift guard that makes the port safe.

Jason: "this should be a button press."

The Edge Function is a PORT. The metric list, the dimension map, the reports
and their conflict keys are now declared in three places:

    smarterpaw-blog/ga4_pull.py          what to ask GA4 for
    digital-forecast-engine/load_ga4.py  where each report lands
    supabase/functions/ga4-pull/index.ts both, in one call

Three copies of one spec drift, and the drift would be silent: the function
would quietly write a different shape than the loader, into the same tables.
Section A is the only thing making that duplication safe.

  * A  the three specs agree, parsed from source.
  * B  the function's own invariants: the truncation refusal, the service
       account, the by_source_medium exclusion, the time budget.
  * C  the button: one affordance, disabled while it runs, no window picker.
"""
import io, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS   = os.path.join(ROOT, "supabase", "functions", "ga4-pull", "index.ts")
LOAD = os.path.join(ROOT, "load_ga4.py")
PULL = os.path.join(os.path.dirname(ROOT), "smarterpaw-blog", "ga4_pull.py")

s  = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)
ts = io.open(TS, encoding="utf-8", newline="").read()
ld = io.open(LOAD, encoding="utf-8", newline="").read()

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


def nocomment_ts(t):
    return re.sub(r"(?m)^\s*//.*$", "", t)


NC = nocomment_ts(ts)

# ---------------------------------------------------------------------------
print("A. the three copies of the spec agree")
# ---------------------------------------------------------------------------


def ts_pairs(name):
    m = re.search(r"const " + name + r"[^=]*=\s*\[([\s\S]*?)\];", ts)
    if not m:
        raise SystemExit("no " + name + " in index.ts")
    return [(a, b) for a, b in re.findall(r'\["([^"]+)",\s*"([^"]+)"\]', m.group(1))]


def py_pairs(src, name):
    m = re.search(r"^" + name + r"\s*=\s*\[([\s\S]*?)^\]", src, re.M)
    if not m:
        raise SystemExit("no " + name + " in the python")
    return [(a, b) for a, b in re.findall(r'\("([^"]+)",\s*"([^"]+)"\)', m.group(1))]


def ts_dims():
    m = re.search(r"const DIMS: Record<string, string> = \{([\s\S]*?)\};", ts)
    return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", m.group(1)))


# load_ga4.py's REPORTS: (file, table, conflict, dims)
ld_reports = re.findall(
    r'\("([a-z_]+)\.csv",\s*"([a-z0-9_]+)",\s*"([a-z0-9_,]+)",\s*\(([^)]*)\)\)', ld)
ld_spec = {}
for fname, table, conflict, dims in ld_reports:
    ld_spec[fname] = (table, conflict, tuple(re.findall(r'"([a-z_]+)"', dims)))
eq("A1  load_ga4.py declares six loaded reports", len(ld_spec), 6)

# index.ts REPORTS
ts_spec = {}
reports_blk = re.search(r"const REPORTS: Report\[\] = \[([\s\S]*?)" + chr(10) + r"\];", NC).group(1)
for blk in re.findall(r"\{\s*key:\s*\"([a-z_]+)\",([\s\S]*?)\},?\s*(?=\{\s*key:|$)", reports_blk):
    key, body = blk
    table = re.search(r'table:\s*"([a-z0-9_]+)"', body)
    conflict = re.search(r'conflict:\s*"([a-z0-9_,]+)"', body)
    dims = re.search(r"dims:\s*\[([^\]]*)\]", body)
    if not (table and conflict and dims):
        continue
    ts_spec[key] = (table.group(1), conflict.group(1),
                    tuple(re.findall(r'"([A-Za-z]+)"', dims.group(1))))
eq("A2  index.ts declares the same six", len(ts_spec), 6)

DIMS = ts_dims()
for key, (table, conflict, api_dims) in sorted(ts_spec.items()):
    want = ld_spec.get(key)
    ok(want is not None, "A3  %s is in load_ga4.py too" % key)
    if not want:
        continue
    eq("A4  %-20s table" % key, table, want[0])
    eq("A5  %-20s conflict key" % key, conflict, want[1])
    # The loader names the COLUMN; the function names the GA4 API dimension.
    # DIMS is the map between them and it has to round-trip.
    eq("A6  %-20s dimensions" % key, tuple(DIMS[d] for d in api_dims), want[2])

ts_metrics = ts_pairs("METRICS")
ts_page = ts_pairs("PAGE_METRICS")
eq("A7  eight metrics, under GA4's limit of ten", len(ts_metrics), 8)
eq("A8  five landing-page metrics", len(ts_page), 5)
ok(all(c in [b for _, b in ts_metrics] for _, c in ts_page),
   "A9  /!\\ the page metrics are a SUBSET of the full set, not a second list")

# The third copy, in the other repo.
if os.path.exists(PULL):
    pl = io.open(PULL, encoding="utf-8", newline="").read()
    eq("A10 /!\\ ga4_pull.py's METRICS match the function's", py_pairs(pl, "METRICS"), ts_metrics)
    eq("A11 /!\\ ...and its PAGE_METRICS", py_pairs(pl, "PAGE_METRICS"), ts_page)
    pd = re.search(r"^DIMS\s*=\s*\{([\s\S]*?)^\}", pl, re.M)
    py_dims = dict(re.findall(r'"([A-Za-z]+)":\s*"([a-z_]+)"', pd.group(1)))
    eq("A12 /!\\ ...and its dimension map", py_dims, DIMS)
else:
    failed += 1
    print("  FAIL  A10 ga4_pull.py not found at %s - the third copy of this spec "
          "cannot be checked, and an unchecked copy is the reason this suite "
          "exists" % PULL)

# ---------------------------------------------------------------------------
print("\nB. the function's own invariants")
# ---------------------------------------------------------------------------
ok("by_source_medium" not in NC.replace("by_source_medium is", ""),
   "B1  /!\\ by_source_medium is NOT loaded - a period aggregate with no date "
   "column would carry whatever window the last pull used (v11.22)")
ok("TRUNCATED report" in NC and "Refusing to write a short report" in NC,
   "B2  /!\\ a short read is REFUSED, not written - it is invisible downstream")
ok("out.length !== rowCount" in NC,
   "B3  ...and the check is against GA4's own rowCount, not a guess")
ok('"date" && /^\\d{8}$/' in NC or "date\" && /^\\d{8}$/" in NC,
   "B4  GA4's 20261030 is normalised at the source")
ok("yearMonth" in NC and "slice(0, 4)" in NC,
   "B5  ...and so is its 202610")
ok("resolution=merge-duplicates" in NC,
   "B6  /!\\ writes UPSERT, so re-running is free rather than duplicating rows")
ok("on_conflict=" in NC, "B7  ...on the declared key")
ok("ga4_snapshots" in NC and "pulled_at" in NC,
   "B8  a pull row is written, so the page can say when this last ran")
ok("BUDGET_MS" in NC and "stoppedEarly" in NC,
   "B9  /!\\ it stops cleanly inside the time budget rather than being killed "
   "mid-report with nothing said")
# v11.84 - it wrote with the service role until the first real call proved
# that NO table in this database grants service_role anything; all 52 grant
# `authenticated` only. It carries the caller's own token through to the
# writes now, so it cannot write what the person pressing the button could not.
ok("SUPABASE_SERVICE_ROLE_KEY" not in NC,
   "B10 /!\ the service role is NOT used - no table here grants it anything")
ok("apikey: anonKey" in NC and "Authorization: bearer" in NC,
   "B10b ...the writes carry the CALLER's token")
ok("GA4_SA_JSON" in NC and "client_email" in NC,
   "B11 a service account, not a copied user token")
ok("Missing secret(s)" in NC,
   "B12 a missing secret is NAMED rather than failing opaquely")
ok("Data API is enabled" in NC and "Viewer on the GA4 property" in NC,
   "B13 /!\\ a refused service account names the two things it is ever caused by")
ok("Math.max(2, Math.min(400" in NC,
   "B14 the day count is clamped - a caller cannot ask for a decade")
ok("tests/test_v1182.py" in ts,
   "B15 /!\\ the function's own header names the suite that stops it drifting")

# ---------------------------------------------------------------------------
print("\nC. the button")
# ---------------------------------------------------------------------------
JS = re.sub(r"(?m)^\s*//.*$", "", js)
eq("C1  one Run button", s.count('id="ga4-run"'), 1)
eq("C2  one status line", s.count('id="ga4-run-st"'), 1)
ok("ga4RunPull(this)" in s, "C3  wired to its handler")
eq("C4  ga4RunPull declared once", JS.count("async function ga4RunPull("), 1)
ok("btn.disabled = true" in JS,
   "C5  /!\\ disabled while it runs - a second click would start a second pull "
   "against the same tables")
ok("btn.disabled = false" in JS, "C6  ...and re-enabled afterwards, on both paths")
ok("res.ok !== true" in JS,
   "C7  /!\\ the FUNCTION's ok flag decides, not the transport - invoke() can "
   "resolve with no error on a 500")
ok("await refreshUploadDataRanges()" in JS,
   "C8  the row, the grid and the strip are refreshed after a pull")
ok("seoTrLoaded = false" in JS,
   "C9  ...and the Traffic tab's cache is dropped, or it shows pre-pull figures")
ok("Math.max(30, Math.min(400" in JS,
   "C10 /!\\ the window is COMPUTED from how behind the feed is, not picked")
ok("<select" not in s[s.index('id="grp-ga4"'):s.index('id="grp-ga4"') + 2500],
   "C11 /!\\ ...so there is no picker on the row to get wrong")
# Scoped to the ROW. load_ga4.py may still be named elsewhere as provenance;
# what must not survive is a second AFFORDANCE for doing the pull beside the
# button, which is the divergence rule #1 exists to stop.
GA4ROW = s[s.index('id="grp-ga4"'):]
_nxt = GA4ROW.find('<div class="up-grp" id="', 10)
GA4ROW = GA4ROW[:_nxt] if _nxt > 0 else GA4ROW[:3000]
ok("copyTextToClipboard" not in GA4ROW and "<code>" not in GA4ROW,
   "C12 /!\\ no copy-a-command affordance survives on the row beside the button")
ok("ga4_pull.py" in s,
   "C13 ...but the scripts survive as PROVENANCE, naming what the function ports")
ok("ONE CLICK" in s, "C14 the badge says what the row is, in the collapsed list")

m = re.search(r">v(\d+\.\d+) · [\d-]+<", s)
cl = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
cm = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cl)
eq("C15 /!\\ the version chip AGREES with CLAUDE.md",
   m.group(1) if m else None, cm.group(1) if cm else None)

print("\n" + "-" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
