#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.52 - an empty table says WHY it is empty.

Jason's screenshot of FBA Shipments, filter `Missing detail`:

    0 shipments
    No shipments match. Upload a packing-list .tsv on Data -> Uploads to
    get started.

He has **223 shipments**. The filters hid every one, and the empty state told
him to go and upload data - which is what sent him looking for a data problem
instead of at the window control. v12.46's defect, on a table instead of a
chart.

`node --check` passes a cross-function reference that throws at runtime
(RULES.md #24), so this drives the branch and pins every local it reads.
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
print("  v12.52  nothing loaded is not nothing matching")
print("=" * 70)

R = fn_flat("renderFbaShipmentsTbl")

# ===========================================================================
print("\nA. the misdirecting message is gone")
# ===========================================================================
ok("No shipments match. Upload a packing-list" not in js,
   "A1  /!\\ 'No shipments match. Upload a packing-list .tsv' is GONE - it told "
   "an operator with 223 shipments to go and upload data")
eq("A2  the upload prompt survives for the state it IS true in",
   js.count("No shipments loaded. Upload a packing-list"), 1)
ok("const total = groups.size;" in R,
   "A3  the two states are told apart by whether anything loaded at all")

# ===========================================================================
print("\nB. the branch, driven")
# ===========================================================================
# Lift the empty-state branch verbatim out of the renderer - it is inside a
# function, so it is sliced rather than re-typed (the v12.39 rule).
i = R.index("  if (!arr.length) {")
BRANCH = R[i:R.index("\n  }\n", i) + len("\n  }\n")]
ok("groups.size" in BRANCH and "winSel" in BRANCH,
   "B0  the branch lifted holds the count and the window read")

B = run_node(os.path.join(SP, "_v1252_b.js"), r"""
function esc2(x) { return String(x == null ? '' : x)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function drive(opts) {
  const { total, winDays, detailFilter, region, brandFilter, q, winLabel } = opts;
  const arr = [];
  const groups = new Map();
  for (let n = 0; n < total; n++) groups.set(String(n), {});
  const tb = { innerHTML: '' };
  const document = { getElementById: (id) =>
    id === 'fba-ship-window'
      ? { selectedOptions: [{ textContent: winLabel }] }
      : null };
  // /!\ THE LIFTED BRANCH CARRIES ITS OWN `return`, so it runs inside an IIFE
  // - called directly it would return out of drive() before the read.
  (function () {
""" + BRANCH + r"""
  })();
  return tb.innerHTML;
}

const text = (h) => h.replace(/<[^>]+>/g, '').trim();
console.log(JSON.stringify({
  // His exact screen: 223 shipments, Missing detail, Last 365 days.
  his: text(drive({ total: 223, winDays: 365, detailFilter: 'missing',
                    region: '', brandFilter: '', q: '', winLabel: 'Last 365 days' })),
  // Genuinely nothing loaded.
  empty: text(drive({ total: 0, winDays: 365, detailFilter: '',
                      region: '', brandFilter: '', q: '', winLabel: 'Last 365 days' })),
  // All time, no filters at all - nothing to name.
  bare: text(drive({ total: 223, winDays: 0, detailFilter: '',
                     region: '', brandFilter: '', q: '', winLabel: 'All time' })),
  // Every filter on at once.
  all: text(drive({ total: 223, winDays: 90, detailFilter: 'with', region: 'CA',
                    brandFilter: '__untagged__', q: 'fba17', winLabel: 'Last 90 days' })),
}));
""")

ok("None of 223 shipments match" in B["his"],
   "B1  /!\\ HIS SCREEN: it counts what exists instead of claiming nothing does",
   B["his"])
ok("window: Last 365 days" in B["his"],
   "B2  ...and names the window FIRST - the only filter with a non-empty "
   "default, so the one hiding rows nobody chose to hide")
ok("missing detail" in B["his"],
   "B3  ...and the filter he had set")
ok("Upload a packing-list" not in B["his"],
   "B4  /!\\ and does NOT send him to the uploader")
ok("No shipments loaded" in B["empty"] and "Upload a packing-list" in B["empty"],
   "B5  nothing loaded still points at the uploader, which is true there",
   B["empty"])
eq("B6  all-time with no filters names none of them",
   B["bare"], "None of 223 shipments match")
for frag in ["window: Last 90 days", "with detail", "region: CA",
             "brand: untagged", "search: fba17"]:
    ok(frag in B["all"], "B7  every active filter is named: %s" % frag)

# ===========================================================================
print("\nC. the locals it reads are the renderer's own")
# ===========================================================================
# Scope is not syntax (RULES.md #24): every identifier the branch reads has to
# be declared in renderFbaShipmentsTbl ABOVE it, or it throws at runtime on the
# one path no other test executes (the v12.25 lesson).
head = R[:i]
for name in ["winDays", "detailFilter", "region", "brandFilter", "q", "groups", "tb"]:
    ok(re.search(r"\b(const|let|var)\s+%s\b" % name, head) is not None,
       "C1  `%s` is declared before the branch reads it" % name, )
ok("function esc2(" in js,
   "C2  esc2 is module-scope, so the branch may call it")

# ===========================================================================
print("\nD. the release names itself")
# ===========================================================================
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "D1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok(chip is not None and "\\u" not in chip.group(0),
   "D2  /!\\ REAL characters in markup", chip.group(0) if chip else None)
ok("v12.52" in C_, "D3  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
