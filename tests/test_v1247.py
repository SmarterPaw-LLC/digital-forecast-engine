#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.47 - one short line, the rest on the tooltip.

- **Jason:** *"text bloat. this should be a tooltip. you have this rule
  saved. please create a list of rules that you always reference, bc you keep
  skipping this."*

The Units Sold subtitle ran ~450 characters over four wrapped rows, and
v12.46 added to it. This suite is the budget, so the next release cannot.
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0
BUDGET = 110


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
print("  v12.47  the line is a number, a unit and a window")
print("=" * 70)

A = run_node(os.path.join(SP, "_v1247_a.js"),
             fn_flat("salesRevNoteBrief") + "\n" + fn_flat("salesRevNote") + "\n"
             + fn_flat("salesCovChipHtml") + "\n" + fn_flat("salesSetSub") + r"""
// A stand-in for the one element this writes to.
const EL = { textContent: '', title: null, style: {}, html: '',
  insertAdjacentHTML(_, h) { this.html += h; },
  removeAttribute(k) { this[k] = null; } };
const document = { getElementById: (id) => id === 'salesDrillSub' ? EL : null };
let _salesRev = null;
const reset = () => { EL.textContent = ''; EL.title = null; EL.style = {}; EL.html = ''; };

const GAP = { chewyMids: new Set(['a','b']), chewyUnits: 12958,
              wmMids: new Set(), wmUnits: 0, amzMiss: 0,
              otherChannels: new Set(['amazon_gb']), otherUnits: 0 };
const out = {};

// /!\ THE LINE JASON PHOTOGRAPHED, rebuilt from its own pieces.
_salesRev = { ok: true, gap: GAP };
const HEAD = `6 weeks · $188,981 our revenue · Last 30 days${salesRevNoteBrief()}`;
const DETAIL = [
  'Channels: Amazon US, Amazon CA, Shopify DTC, Chewy, Walmart',
  ' · ⚠ $374 our revenue in amazon_gb (no checkbox)',
  salesRevNote(),
  ' · data: Amazon US thru 11/9/26 (8d) · Amazon CA thru 11/9/26 (8d) · Shopify DTC thru 11/16/26 (1d) · Chewy thru 10/26/26 (22d) · Walmart thru 11/2/26 (15d)',
  '',
];
const COV = { firstGapWeek: '2026-11-02', weeks: ['2026-11-02','2026-11-09','2026-11-16'],
              channels: [{ ch: 'chewy', label: 'Chewy', firstGap: '2026-11-02' }] };
reset(); salesSetSub(HEAD, DETAIL, COV, true);
out.head = EL.textContent;
out.headLen = EL.textContent.length;
out.title = EL.title;
out.titleLines = (EL.title || '').split('\n').length;
out.cursor = EL.style.cursor;
out.html = EL.html;
// The old single-string form, for scale.
out.oldLen = (HEAD + DETAIL.filter(Boolean).join('')).length;

// Nothing to say -> no tooltip at all, and no cursor:help promising one.
reset(); salesSetSub('6 weeks · 253,347 units · Year to date', [], null, false);
out.cleanTitle = EL.title;
out.cleanCursor = EL.style.cursor;
out.cleanHtml = EL.html;

// The brief form over the shapes the gap can take.
const brief = (st) => { _salesRev = st; return salesRevNoteBrief(); };
out.b_units = brief({ ok: true, gap: GAP });
out.b_none  = brief({ ok: true, gap: { chewyMids: new Set(), chewyUnits: 0, wmUnits: 0, otherUnits: 0 } });
out.b_feed  = brief({ ok: true, gap: { chewyUnits: 0, wmUnits: 0, otherUnits: 0, cyErr: 'permission denied' } });
out.b_week  = brief({ ok: true, gap: { chewyUnits: 0, wmUnits: 0, otherUnits: 0, amzMiss: 12 } });
out.b_err   = brief({ err: 'statement timeout' });
out.b_pend  = brief({ pending: true });
out.b_null  = brief(null);
// /!\ The LONG form over the same gap, so the two can be compared.
_salesRev = { ok: true, gap: GAP };
out.longForm = salesRevNote();
console.log(JSON.stringify(out));
""")

# ===========================================================================
print("\nA. /!\\ THE BUDGET")
# ===========================================================================
ok(A["headLen"] <= BUDGET,
   "A1  /!\\ the visible line is %d characters, under the %d budget - it was "
   "%d, over four wrapped rows" % (A["headLen"], BUDGET, A["oldLen"]),
   A["head"])
ok(A["oldLen"] > 400,
   "A2  ...and the single-string form it replaces really was that long",
   A["oldLen"])
ok("12,958 units" in A["head"],
   "A3  /!\\ ONE warning survives on the line, in four words - a gap that "
   "only exists in a tooltip is a gap nobody sees (v12.08)")
ok("Chewy 38 SKU" not in A["head"] and "data:" not in A["head"]
   and "Channels:" not in A["head"],
   "A4  and the sentences, the per-feed list and the scope are NOT on it",
   A["head"])

# ===========================================================================
print("\nB. the tooltip carries the rest, one line each")
# ===========================================================================
ok(A["titleLines"] == 4,
   "B1  four detail sentences, four tooltip lines - not one run-on string",
   A["titleLines"])
ok("Channels: Amazon US" in A["title"], "B2  the scope is there")
ok("amazon_gb" in A["title"], "B3  the unmapped-channel note is there")
ok("data: Amazon US thru" in A["title"], "B4  the per-feed list is there")
ok(not A["title"].startswith(" · ") and "\n · " not in A["title"],
   "B5  /!\\ the subtitle separator is stripped, so no call site has to carry "
   "two spellings of its own note", ascii(A["title"][:40]))
eq("B6  and the element says it has a tooltip", A["cursor"], "help")

# ===========================================================================
print("\nC. /!\\ THE AFFORDANCE STAYS MARKUP")
# ===========================================================================
ok("compare without" in A["html"],
   "C1  /!\\ the one-click fix is still a LINK beside the text, not a label "
   "buried in a title attribute - test_v1087 fails the build on that, and "
   "rule 1a is why it exists")
ok("<a href" in A["html"], "C2  ...a real anchor")
ok("compare without" not in (A["title"] or ""),
   "C3  and it is not ALSO in the tooltip, which would be two of it")
ok("incomplete" in A["html"],
   "C4  the incomplete-weeks chip is still rendered as markup too")

# ===========================================================================
print("\nD. nothing to say means no tooltip")
# ===========================================================================
eq("D1  /!\\ a clean view removes the title rather than leaving a stale one",
   A["cleanTitle"], None)
eq("D2  ...and takes cursor:help with it, so nothing promises a tooltip that "
   "is not there", A["cleanCursor"], "")
eq("D3  and no chip is appended when there is no gap", A["cleanHtml"], "")

# ===========================================================================
print("\nE. /!\\ ONE DERIVATION, TWO LENGTHS")
# ===========================================================================
eq("E1  units behind the gap are counted", A["b_units"],
   " · ⚠ excludes 12,958 units")
eq("E2  no gap, no warning", A["b_none"], "")
eq("E3  /!\\ an unreadable feed has no unit count and is still a gap (v11.16)",
   A["b_feed"], " · ⚠ revenue has gaps")
eq("E4  ...and so is a missing Amazon week", A["b_week"],
   " · ⚠ revenue has gaps")
eq("E5  a failure says so without pasting the message onto the line",
   A["b_err"], " · ⚠ revenue unreadable")
eq("E6  loading is not a gap", A["b_pend"], " · reading revenue…")
eq("E7  never fetched is its own state", A["b_null"],
   " · ⚠ revenue not loaded")
ok("12,958" in A["longForm"] and "Chewy 2 SKUs" in A["longForm"],
   "E8  /!\\ and the LONG form names the same 12,958 - both read "
   "_salesRev.gap, so the line and the tooltip cannot report two counts",
   A["longForm"])

# ===========================================================================
print("\nF. both call sites pass detail rather than concatenating")
# ===========================================================================
eq("F1  one writer of the subtitle", js.count("function salesSetSub("), 1)
eq("F2  two callers", js.count("  salesSetSub(\n"), 2)
eq("F3  /!\\ and BOTH hand it a detail ARRAY - one converted and one left "
   "concatenating is how this grows back",
   len(re.findall(r"salesSetSub\(\s*\n\s*`[^`]*`,\s*\n\s*\[", js)), 2)
ok("${_measNote}" not in js,
   "F4  the long note is no longer interpolated into a line")
ok("${_freshLine}" not in js and "${_freshLineCh}" not in js,
   "F5  ...and neither is the per-feed list")
ok("sub.style.cursor = 'help'" in fn_flat("salesSetSub"),
   "F6  the help cursor is set where the title is")

# ===========================================================================
print("\nG. the list he asked for exists and is pointed at")
# ===========================================================================
rules = os.path.join(ROOT, "RULES.md")
ok(os.path.exists(rules), "G1  RULES.md exists at the repo root")
R = io.open(rules, encoding="utf-8").read() if os.path.exists(rules) else ""
ok("NEVER print prose in a UI" in R,
   "G2  /!\\ and the rule that keeps getting skipped is rule 1 on it")
ok(str(BUDGET) in R,
   "G3  with the budget as a NUMBER, so it is checkable rather than a feeling")
C = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
ok("READ `RULES.md` FIRST" in C[:900],
   "G4  /!\\ and CLAUDE.md points at it in its first lines - a rule I have to "
   "remember to look up is a rule I skip")
ok(len(R.split("\n")) < 90,
   "G5  ...and the list is SHORT, because a long rules file is itself the "
   "thing rule 1 forbids", len(R.split("\n")))

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
