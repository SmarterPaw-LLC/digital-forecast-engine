#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.73 - the Traffic tab says how current it is, and a partial bucket says so.

Jason: "this data doesn't appear to refresh daily."

Measured 2026-11-06: it did not refresh AT ALL. Exactly one pull had ever been
loaded - 2026-11-02 - so the newest day was 4 days behind and the window's last
four days were simply absent. The page said "176 days on record" over a 180-day
window and nothing else, so the only visible symptom was a chart whose last
bucket fell off a cliff.

And the half that survives any amount of refreshing: ga4_pull.py ends its
window on TODAY, so the last day it writes is however much of today had
happened when it ran. 2026-11-02 was loaded as 190 sessions and reads 667 now -
the same day, 3.5x, after GA4 settled it.

  * A  the real pnlProvisionalBuckets. A bucket whose SPAN runs past the last
       settled day cannot be drawn as final. Opt-out is an EMPTY set, which is
       every chart in this app but one.
  * B  the real seoTrCoverage, on a pinned clock: newest, how far behind, and
       the 48h settle cut DERIVED from the pull's own timestamp.
  * C  /!\ THE DEFECT REPRODUCED - the pre-v11.73 label builder run beside the
       shipped one on Jason's own shape.
  * D  /!\ the BUCKET KEY is untouched, so v11.28's click-a-point-to-scope
       still parses it.
  * E  static: the failure branch clears the pull row, no settle cutoff is
       typed, and one definition of each new answer.
"""
import io, os, re, sys, json, subprocess

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


def _bal(i):
    k, n = i, len(js)
    depth, started, prev = 0, False, ""
    while k < n:
        c = js[k]
        if c == "/" and k + 1 < n and js[k + 1] == "/":
            while k < n and js[k] != "\n":
                k += 1
            continue
        if c == "/" and k + 1 < n and js[k + 1] == "*":
            k = js.index("*/", k) + 2
            continue
        if c == "/" and prev in "(,=:[!&|?{};+-*%~^<>":
            k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == "[":
                    while k < n and js[k] != "]":
                        k += 2 if js[k] == "\\" else 1
                if js[k] == "/":
                    break
                k += 1
            k += 1
            while k < n and js[k].isalpha():
                k += 1
            prev = "x"
            continue
        if c in "\"'`":
            q = c; k += 1
            while k < n:
                if js[k] == "\\":
                    k += 2; continue
                if js[k] == q:
                    break
                k += 1
            k += 1
            prev = "x"
            continue
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:k + 1]
        if not c.isspace():
            prev = c
        k += 1
    raise SystemExit("unbalanced at %d" % i)


def fn(name, kw="function"):
    pat = kw + " " + name + "("
    i = js.index(pat)
    head = js.index("{", i)
    j = i
    while j > 0 and js[j - 1] != "\n":
        j -= 1
    return js[j:head] + _bal(head)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])



print("\n" + "=" * 68)
print("v11.73 - how current is this, and which buckets are not final")
print("=" * 68)

NC = nocomment(js)

# ---------------------------------------------------------------------------
print("\nA. the real pnlProvisionalBuckets")
# ---------------------------------------------------------------------------
A = run_node(os.path.join(SP, "_v1173_a.js"), (
    fn("pnlBucketRange") + "\n" + fn("pnlBucketGrain") + "\n"
    + fn("pnlProvisionalBuckets") + r"""
const set = (b, s) => [...pnlProvisionalBuckets(b, s)];
// Jason's own chart: 26 Monday-keyed weekly buckets. The last one starts
// 2026-11-02 and runs to 2026-11-08, which has not happened.
const WEEKS = ['2026-10-12','2026-10-19','2026-10-26','2026-11-02'];
const DAYS  = ['2026-11-03','2026-11-04','2026-11-05','2026-11-06'];
console.log(JSON.stringify({
  // settled through the Saturday before the last week closes
  weekTail:      set(WEEKS, '2026-11-04'),
  // settled right up to the last bucket's final day - nothing is provisional
  weekComplete:  set(WEEKS, '2026-11-08'),
  // the feed stopped two weeks back: BOTH open weeks are provisional
  weekBehind:    set(WEEKS, '2026-10-20'),
  dayTail:       set(DAYS,  '2026-11-04'),
  dayNone:       set(DAYS,  '2026-11-06'),
  monthTail:     set(['2026-09','2026-10','2026-11'], '2026-11-06'),
  // THE OPT-OUT. Every other chart in this app passes nothing.
  noSettled:     set(WEEKS, null),
  undefSettled:  set(WEEKS, undefined),
  emptySettled:  set(WEEKS, ''),
  noBuckets:     set([], '2026-11-04'),
  nullBuckets:   set(null, '2026-11-04'),
  // the span is the BUCKET's, not the key's: a week key BEFORE settled is
  // still provisional when its seventh day is after it.
  spanNotKey:    set(WEEKS, '2026-11-03'),
  // /!\ one bucket cannot declare its own grain - pnlBucketGrain says so in
  // its own comment - so it is read as a DAY. Asserted as what it is.
  loneBucket:    set(['2026-11-02'], '2026-11-03'),
}));
"""))

eq("A1  the open trailing week is provisional", A["weekTail"], ["2026-11-02"])
eq("A2  a week fully settled is NOT", A["weekComplete"], [])
eq("A3  a feed two weeks behind leaves EVERY still-open week provisional",
   A["weekBehind"], ["2026-10-19", "2026-10-26", "2026-11-02"])
eq("A4  daily grain marks only the unsettled days",
   A["dayTail"], ["2026-11-05", "2026-11-06"])
eq("A5  daily grain fully settled marks nothing", A["dayNone"], [])
eq("A6  a MONTH bucket is provisional until its last day",
   A["monthTail"], ["2026-11"])
ok(A["noSettled"] == [] and A["undefSettled"] == [] and A["emptySettled"] == [],
   "A7  /!\\ NO settled day -> EMPTY SET. Every other chart is byte-identical",
   (A["noSettled"], A["undefSettled"], A["emptySettled"]))
ok(A["noBuckets"] == [] and A["nullBuckets"] == [],
   "A8  no buckets, or none at all, does not throw",
   (A["noBuckets"], A["nullBuckets"]))
eq("A9  /!\\ the SPAN decides, not the key: 11-02 is before 11-03 and still marked",
   A["spanNotKey"], ["2026-11-02"])
eq("A10 a LONE bucket is read as a DAY - pnlBucketGrain's own documented rule",
   A["loneBucket"], [])

# ---------------------------------------------------------------------------
print("\nB. the real seoTrCoverage, clock pinned to 2026-11-06")
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "_v1173_b.js"), (r"""
let FROM = '2026-05-11', TO = '2026-11-06', PERIOD = 'custom';
global.document = { getElementById: (id) =>
    id === 'seo-tr-period' ? { value: PERIOD }
  : id === 'seo-tr-from'   ? { value: FROM }
  : id === 'seo-tr-to'     ? { value: TO } : null };
""" + fn("seoTrWindow") + r"""
const RealDate = Date;
const FIXED = new RealDate(2026, 10, 6);     // 2026-11-06
globalThis.Date = class extends RealDate {
  constructor(...a) { if (!a.length) return new RealDate(FIXED); return new RealDate(...a); }
  static now() { return FIXED.getTime(); }
  static parse(x) { return RealDate.parse(x); }
};
let seoTr = { days: [] }, seoTrSnap = null;
""" + re.search(r"(?m)^const GA4_SETTLE_DAYS\s*=.*$", js).group(0) + chr(10) + fn("ga4SettledThrough") + chr(10) + fn("seoTrCoverage") + r"""
const days = (hi) => { const out = []; const d = new RealDate(RealDate.parse('2026-05-11T00:00:00Z'));
  const end = RealDate.parse(hi + 'T00:00:00Z');
  while (d.getTime() <= end) { out.push({ day: d.toISOString().slice(0,10) }); d.setUTCDate(d.getUTCDate()+1); }
  return out; };
const run = (hi, snap, from, to) => {
  seoTr = { days: hi ? days(hi) : [] };
  seoTrSnap = snap;
  FROM = from || '2026-05-11'; TO = to || '2026-11-06';
  return seoTrCoverage();
};
console.log(JSON.stringify({
  // WHAT JASON WAS LOOKING AT: the only pull ever loaded was 2026-11-02.
  stale:     run('2026-11-02', { snapshot_date: '2026-11-02', pulled_at: '2026-11-02T18:20:18+00:00' }),
  // after the 2026-11-06 pull
  current:   run('2026-11-06', { snapshot_date: '2026-11-06', pulled_at: '2026-11-06T19:23:16+00:00' }),
  // no pull row at all - settled must NOT be guessed
  noSnap:    run('2026-11-06', null),
  snapNoTs:  run('2026-11-06', { snapshot_date: '2026-11-06', pulled_at: null }),
  // a window that CLOSES IN THE PAST is not behind because the calendar moved
  histWin:   run('2026-08-31', { snapshot_date: '2026-11-06', pulled_at: '2026-11-06T19:23:16+00:00' },
                 '2026-06-01', '2026-08-31'),
  empty:     run(null, { snapshot_date: '2026-11-06', pulled_at: '2026-11-06T19:23:16+00:00' }),
  // the newest row wins whatever order they arrive in
  newestWins: (() => { seoTr = { days: [{day:'2026-11-01'},{day:'2026-11-05'},{day:'2026-11-03'}] };
    seoTrSnap = { snapshot_date:'2026-11-06', pulled_at:'2026-11-06T19:23:16+00:00' };
    FROM='2026-05-11'; TO='2026-11-06'; return seoTrCoverage(); })(),
  holes: (() => { seoTr = { days: [{day:'2026-11-01'},{day:null},{}] };
    seoTrSnap = null; return seoTrCoverage(); })(),
}));
"""))

eq("B1  /!\\ the stale feed: newest 2026-11-02", B["stale"]["newest"], "2026-11-02")
eq("B2  /!\\ and 4 days behind - Jason's missing days, counted",
   B["stale"]["behind"], 4)
eq("B3  the pull that wrote it is named", B["stale"]["pulled"], "2026-11-02")
eq("B4  /!\\ a pull of 11-02 settles only through 10-31 (48h, inclusive)",
   B["stale"]["settled"], "2026-10-31")
eq("B5  after today's pull nothing is behind", B["current"]["behind"], 0)
eq("B6  and the newest day is 2026-11-06", B["current"]["newest"], "2026-11-06")
eq("B7  /!\\ which is PROVISIONAL - settled stops at 11-04",
   B["current"]["settled"], "2026-11-04")
eq("B8  /!\\ NO pull row: settled is the newest day, never a guess",
   B["noSnap"]["settled"], "2026-11-06")
eq("B8b and a pull row with no timestamp is the same",
   B["snapNoTs"]["settled"], "2026-11-06")
eq("B8c with no pull row there is no pull date either",
   B["noSnap"]["pulled"], None)
eq("B9  /!\\ a window closing in the PAST is not behind", B["histWin"]["behind"], 0)
eq("B10 an empty feed answers null rather than throwing",
   [B["empty"]["newest"], B["empty"]["behind"], B["empty"]["settled"]], [None, None, None])
eq("B11 the newest day wins whatever order the rows arrive in",
   B["newestWins"]["newest"], "2026-11-05")
eq("B12 a null or missing day is skipped, not read as newest",
   B["holes"]["newest"], "2026-11-01")

# ---------------------------------------------------------------------------
print("\nC. /!\\ THE DEFECT REPRODUCED - the pre-v11.73 labels, run beside the shipped ones")
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, "_v1173_c.js"), (
    fn("pnlBucketRange") + "\n" + fn("pnlBucketGrain") + "\n"
    + fn("pnlProvisionalBuckets") + r"""
const MON3 = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fmtBucket = b => {
  const [y, mo, d] = String(b || '').split('-');
  if (!y) return b;
  if (d === undefined) return (MON3[(+mo) - 1] || mo) + "'" + y.slice(2);
  return `${+mo}/${+d}/${y.slice(2)}`;
};
const BUCKETS = ['2026-10-12','2026-10-19','2026-10-26','2026-11-02'];
// v11.72 and earlier: labels are fmtBucket, full stop.
const OLD = BUCKETS.map(fmtBucket);
// v11.73: the same labels, with the one that cannot be filled marked.
const provisional = pnlProvisionalBuckets(BUCKETS, '2026-11-04');
const labelOf = b => fmtBucket(b) + (provisional.has(b) ? '*' : '');
const NEW = BUCKETS.map(labelOf);
// and with no settled day the two are the same array.
const prov0 = pnlProvisionalBuckets(BUCKETS, null);
const OPTOUT = BUCKETS.map(b => fmtBucket(b) + (prov0.has(b) ? '*' : ''));
console.log(JSON.stringify({ OLD, NEW, OPTOUT }));
"""))

eq("C1  pre-v11.73 drew the partial week as an ordinary one",
   C["OLD"], ["10/12/26", "10/19/26", "10/26/26", "11/2/26"])
eq("C2  /!\\ v11.73 marks it", C["NEW"],
   ["10/12/26", "10/19/26", "10/26/26", "11/2/26*"])
eq("C3  exactly ONE label moved", sum(1 for a, b in zip(C["OLD"], C["NEW"]) if a != b), 1)
eq("C4  /!\\ and with no settled day the labels are BYTE-IDENTICAL to v11.72",
   C["OPTOUT"], C["OLD"])

# ---------------------------------------------------------------------------
print("\nD. the BUCKET KEY is untouched, so click-a-point-to-scope still parses")
# ---------------------------------------------------------------------------
D = run_node(os.path.join(SP, "_v1173_d.js"), (
    fn("pnlBucketRange") + "\n" + fn("pnlBucketGrain") + "\n"
    + fn("pnlProvisionalBuckets") + r"""
const BUCKETS = ['2026-10-26','2026-11-02'];
const provisional = pnlProvisionalBuckets(BUCKETS, '2026-11-04');
// v11.28 resolves a click through buckets[i], NOT through the label.
console.log(JSON.stringify({
  keysUnchanged: BUCKETS,
  rangeOfMarked: pnlBucketRange(BUCKETS[1], 'week'),
  // what it WOULD do if the marker had gone into the key
  rangeOfLabel:  pnlBucketRange(BUCKETS[1] + '*', 'week'),
}));
"""))

eq("D1  the keys the click reads are unchanged",
   D["keysUnchanged"], ["2026-10-26", "2026-11-02"])
eq("D2  a marked bucket still resolves to its week",
   D["rangeOfMarked"], {"from": "2026-11-02", "to": "2026-11-08"})
eq("D3  /!\\ and a marker INSIDE the key would have killed the journey",
   D["rangeOfLabel"], None)
eq("D4  the renderer labels through labelOf, not fmtBucket",
   NC.count("buckets.map(labelOf)"), 1)
eq("D4b fmtBucket is not also mapped directly", NC.count("buckets.map(fmtBucket)"), 0)
ok("pnlPickBucket(cfg.periodHost, buckets[i]" in NC,
   "D5  the click still reads the raw bucket array")

# ---------------------------------------------------------------------------
print("\nE. static")
# ---------------------------------------------------------------------------
eq("E1  pnlProvisionalBuckets declared exactly once",
   NC.count("function pnlProvisionalBuckets("), 1)
eq("E2  seoTrCoverage declared exactly once",
   NC.count("function seoTrCoverage("), 1)
eq("E3  ONE caller passes settledThrough - the opt-in is not a sweep",
   NC.count("settledThrough:"), 1)
ok("seoTrSnap = null;" in NC.split("seoTrErr = /ga4_/i")[-1][:1200]
   or NC.count("seoTrSnap = null;") >= 2,
   "E4  /!\\ the FAILURE branch clears the pull row too",
   NC.count("seoTrSnap = null;"))
ok("seoFetchAll('ga4_snapshots'" in NC,
   "E5  the pull row comes through the same seam as everything else here")
ok("let seoTrSnap" in NC, "E6  seoTrSnap is declared at module scope")
# The settle window is DERIVED from the pull's own timestamp. A typed date, or
# a typed hour count, would be stale the day the pull moves.
#
# v11.78 - the arithmetic moved into ga4SettledThrough so the Uploads page
# could read the SAME rule instead of keeping a second copy of "is the last
# day real yet". seoTrCoverage still sources pulled_at; the cut is derived one
# function over. E7 follows it rather than pinning the old address, and E7b
# holds the guarantee E7 was actually written for.
cov    = fn("seoTrCoverage")
settle = fn("ga4SettledThrough")
ok("pulled_at" in cov and "ga4SettledThrough(" in cov,
   "E7  /!\\ seoTrCoverage sources the cut from pulled_at, through the shared rule")
ok("setUTCDate" in settle and "GA4_SETTLE_DAYS" in settle,
   "E7b /!\\ the cut is derived, not typed")
ok(not re.search(r"\b202[0-9]-[0-9]{2}-[0-9]{2}\b", nocomment(cov + settle)),
   "E8  /!\\ no cutoff DATE is typed into the derivation")
ok("GA4 settles a day within" in js or "settles a day" in js,
   "E9  the 48h rule is written down where the next reader will find it")
eq("E10 the subtitle declares the marker beside what it means",
   NC.count("partial (*), settled through"), 1)
ok("days on record" in NC and "seoTrCoverageNote()" in NC,
   "E11 the coverage line reads the shared answer")
eq("E12 seoTrCoverageNote declared exactly once",
   NC.count("function seoTrCoverageNote("), 1)

m = re.search(r">v(\d+\.\d+) \u00b7 [\d-]+<", s)
cl = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
mc = re.search(r"current version \*\*v(\d+\.\d+)\*\*", cl)
eq("E13 the chip and CLAUDE.md agree (v11.63's rule)",
   m and m.group(1), mc and mc.group(1))

print("\n" + "-" * 68)
print("  passed %d   failed %d" % (passed, failed))
print("-" * 68)
sys.exit(1 if failed else 0)
