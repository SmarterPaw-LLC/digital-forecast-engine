#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.11 - one parallel pager.

Jason: "it takes SO LONG whenever i refresh".

Measured against the live REST API, the same endpoint and 1,000-row page size
the app uses, sequential against a six-wide burst:

    table                  rows      seq      par      x
    amazon_ad_spend     295,189   60.55s   13.78s   4.4x
    sku_economics        41,236   10.16s    3.13s   3.3x
    chewy_forecasts      25,641    4.83s    1.17s   4.1x
    sales_weekly         11,814    1.92s    0.59s   3.2x
    chewy_sales_weekly    9,304    2.02s    0.72s   2.8x
    TOTAL                         80.89s   20.71s   3.9x

/!\ amazon_ad_spend ALONE IS 75% OF THE WAIT - 296 sequential round trips,
each waiting for the one before it. This is v11.72's finding, which measured
5.8-7.3x and sat unbuilt through nine releases while the table grew.

/!\ THE WHOLE RISK OF THIS CHANGE IS ROWS, NOT SPEED. A pager that is fast
and drops a page is far worse than a slow one, so section B drives the real
helper against a stand-in client and compares it ROW FOR ROW with the
sequential loop it replaces, at every boundary that could go wrong.
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


def fn_flat(name):
    i = js.index("function " + name + "(")
    if js[max(0, i - 6):i] == "async ":
        i -= 6
    return js[i:js.index("\n}", i) + 2]


def line_of(pat):
    for ln in js.split("\n"):
        if pat in ln:
            return ln
    raise SystemExit("not found: " + pat)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.11  one parallel pager")
print("=" * 70)

DRIVER = r"""
'use strict';
__SIZE__
__BURST__
__PAGER__

// A stand-in PostgREST: N rows, served in pages, recording every range asked
// for and how many were in flight at once.
function makeClient(n, opts) {
  opts = opts || {};
  const rows = Array.from({ length: n }, (_, i) => ({ id: i, v: 'r' + i }));
  const asked = [];
  let inFlight = 0, maxInFlight = 0;
  const api = {
    from: () => {
      const q = {
        select: () => q,
        eq: () => q,
        order: () => q,
        range: (a, b) => {
          asked.push([a, b]);
          inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
          return new Promise((res) => setTimeout(() => {
            inFlight--;
            if (opts.failAt != null && a === opts.failAt) { res({ error: { message: 'boom' } }); return; }
            res({ data: rows.slice(a, Math.min(b + 1, rows.length)), error: null });
          }, 1));
        },
      };
      return q;
    },
  };
  return { api, rows, asked, stats: () => ({ maxInFlight, calls: asked.length }) };
}

// The loop this replaces, run against the SAME client.
async function sequential(sb, size) {
  let all = []; let from = 0;
  for (;;) {
    const { data, error } = await sb.from('t').select('*').range(from, from + size - 1);
    if (error) throw new Error(error.message);
    if (!data || !data.length) break;
    all = all.concat(data);
    if (data.length < size) break;
    from += size;
  }
  return all;
}

const SIZE = 10;
(async () => {
  const out = {};
  // /!\ EVERY BOUNDARY: empty, short, exactly one page, exactly a burst, one
  // past a burst, and a size that lands mid-burst.
  const Ns = [0, 1, 9, 10, 11, 59, 60, 61, 125, 180, 181];
  out.same = [];
  for (const n of Ns) {
    const a = makeClient(n), b = makeClient(n);
    const par = await sbPageAll('t', { sb: a.api, pageSize: SIZE, burst: 6 });
    const seq = await sequential(b.api, SIZE);
    out.same.push({
      n,
      rowsMatch: par.length === seq.length
                 && par.every((r, i) => r.id === seq[i].id),
      parRows: par.length, seqRows: seq.length,
      parCalls: a.stats().calls, seqCalls: b.stats().calls,
      maxInFlight: a.stats().maxInFlight,
    });
  }

  // concurrency really happens
  const c = makeClient(125);
  await sbPageAll('t', { sb: c.api, pageSize: SIZE, burst: 6 });
  out.burstWidth = c.stats().maxInFlight;

  // an error anywhere in a burst surfaces
  const e = makeClient(125, { failAt: 30 });
  try { await sbPageAll('t', { sb: e.api, pageSize: SIZE, burst: 6 }); out.threw = false; }
  catch (err) { out.threw = true; out.msg = err.message; }

  // onError can swallow it and substitute a value (the missing-table path)
  const e2 = makeClient(125, { failAt: 30 });
  out.onErr = await sbPageAll('t', { sb: e2.api, pageSize: SIZE, burst: 6,
                                     onError: () => ['handled'] });
  console.log(JSON.stringify(out));
})();
"""

A = run_node(os.path.join(SP, "_v1211_a.js"),
             DRIVER.replace("__SIZE__", line_of("const SB_PAGE_SIZE"))
                   .replace("__BURST__", line_of("const SB_PAGE_BURST"))
                   .replace("__PAGER__", fn_flat("sbPageAll")))

# ===========================================================================
print("\nA. /!\\ IDENTICAL ROWS TO THE LOOP IT REPLACES")
# ===========================================================================
for r in A["same"]:
    ok(r["rowsMatch"],
       "A1  %4d rows: same rows, same order as sequential" % r["n"],
       "par %d seq %d" % (r["parRows"], r["seqRows"]))
bad = [r for r in A["same"] if r["parRows"] != r["n"]]
eq("A2  /!\\ and the right NUMBER of rows at every boundary", bad, [])

print("\nB. it is actually parallel")
eq("B1  /!\\ six requests in flight at once", A["burstWidth"], 6)
# A burst overshoots the end; that is the trade for not paying a count query.
over = next(r for r in A["same"] if r["n"] == 61)
ok(over["parCalls"] >= over["seqCalls"],
   "B2  /!\\ it issues MORE requests than the loop - overshoot is the price "
   "of not running a count", (over["parCalls"], over["seqCalls"]))
one = next(r for r in A["same"] if r["n"] == 9)
eq("B3  /!\\ ...but a short first page costs exactly ONE request",
   one["parCalls"], 1)
zero = next(r for r in A["same"] if r["n"] == 0)
eq("B4  ...and an empty table also costs one", zero["parCalls"], 1)

print("\nC. errors")
ok(A["threw"], "C1  /!\\ a failure inside a burst is raised, not silently short")
ok("boom" in (A.get("msg") or ""), "C2  ...carrying the real message", A.get("msg"))
eq("C3  onError can substitute a value - the missing-table path", A["onErr"], ["handled"])

# ===========================================================================
print("\nD. the callers")
# ===========================================================================
ok("return sbPageAll(table, { filters });" in js, "D1  sbGet goes through it")
ok("const all = await sbPageAll('amazon_ad_spend', {" in js,
   "D2  /!\\ and so does the 295,189-row one that is 75% of the wait")
ok("order: { column: 'date', ascending: false }," in js,
   "D3  /!\\ with its ordering UNCHANGED - downstream readers rely on it")
ok("await sbPageAll(table, {\n      order: { column: orderBy" in js,
   "D4  the Walmart ads loader too")
# /!\ The sequential loops those replaced must be GONE, not left beside them.
ok("from += 1000;\n    }\n    amazonAdSpendData" not in js,
   "D5  /!\\ the loop it replaced is gone, not left standing beside it")
ok("while (true) {\n    let q = sb.from(table).select('*');" not in js,
   "D6  ...and so is sbGet's")

print("\nE. the burst width is a decision")
ok("const SB_PAGE_BURST = 6;" in js, "E1  six")
# The reasoning lives in the header comment ABOVE the function, which fn_flat
# does not include - asserted against the file.
ok("connections per host at six" in js,
   "E2  /!\\ and the reason is written down - browsers cap at six per host, "
   "so a wider burst queues and buys nothing")
ok("NO COUNT QUERY" in js,
   "E3  /!\\ and why there is no count first: a round trip AND a full scan")

print("\nF. the chip agrees with CLAUDE.md")
md = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r">v(\d+\.\d+) · (\d{4}-\d{2}-\d{2})</span>", s)
cur = re.search(r"current version \*\*v(\d+\.\d+)\*\*", md)
ok(chip and cur, "F1  both declare a version")
eq("F2  and they agree", chip.group(1), cur.group(1))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
