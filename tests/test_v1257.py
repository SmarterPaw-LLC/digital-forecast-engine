#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.57 - the Vel vs dropdown repaints the grid it is standing on.

- **Jason:** *"if i change the velocity vs drop down, it does not change the
  vel trend"*

`setVelCmpMode` saved the mode and cleared the memo correctly every time, then
asked `page-inventory.classList.contains('active')` which page to repaint.
**`#page-inventory` is never given a class** - `switchForecastView` shows it
with `style.display` - so that test is permanently false and the function fell
through to `renderAll()`, which repaints the Demand Forecast and never touches
the Inventory Planning grid under the dropdown.
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
print("  v12.57  the page is shown with style.display, never a class")
print("=" * 70)

# ===========================================================================
print("\nA. the markup says which test is the right one")
# ===========================================================================
ok('<div id="page-inventory" style="display:none">' in s,
   "A1  /!\\ #page-inventory is a style.display page - that is the fact the "
   "broken test ignored")
ok("document.getElementById('page-inventory').style.display" in js,
   "A2  ...and switchForecastView shows it that way")
ok("page-inventory')?.classList.contains('active')" not in js,
   "A3  /!\\ no class test against it survives anywhere")
eq("A4  one helper answers it", js.count("function ipPageVisible() {"), 1)
eq("A5  ...read by all three call sites", js.count("ipPageVisible()"), 4)
ok("el.style.display !== 'none'" in fn_flat("ipPageVisible"),
   "A6  and it tests what the page actually uses")

# ===========================================================================
print("\nB. setVelCmpMode, driven - the defect and the fix")
# ===========================================================================
HARNESS = fn_flat("ipPageVisible") + "\n" + fn_flat("setVelCmpMode") + r"""
const CALLS = [];
const STORE = {};
const localStorage = { getItem: (k) => STORE[k] ?? null,
                       setItem: (k, v) => { STORE[k] = String(v); } };
function clearVelMemo() { CALLS.push('clearVelMemo'); }
function renderInventoryTbl() { CALLS.push('renderInventoryTbl'); }
function renderAll() { CALLS.push('renderAll'); }

// The page as it really is: shown with style.display, and carrying NO class.
function mkDom(display) {
  return { getElementById: (id) => {
    if (id === 'page-inventory') return { style: { display }, classList: { contains: () => false } };
    if (id === 'ip-vel-cmp' || id === 'fc-vel-cmp') return { value: 'prior' };
    return null;
  } };
}

function run(display, mode) {
  CALLS.length = 0;
  globalThis.document = mkDom(display);
  setVelCmpMode(mode);
  return { calls: CALLS.slice(), saved: STORE['velCmpMode'] };
}

const onInventory = run('', '90');          // the page is showing
const onForecast  = run('none', '365');     // it is not

// ...and the pre-v12.57 decision, reproduced verbatim beside it.
function oldDecide(display) {
  const d = mkDom(display);
  return d.getElementById('page-inventory')?.classList.contains('active')
    ? 'renderInventoryTbl' : 'renderAll';
}
console.log(JSON.stringify({
  onInventory, onForecast,
  oldOnInventory: oldDecide(''),
  newOnInventory: ipPageVisible.call(null) === undefined ? null : null,
}));
"""
B = run_node(os.path.join(SP, "_v1257_b.js"), HARNESS)

ok("renderInventoryTbl" in B["onInventory"]["calls"],
   "B1  /!\\ THE FIX: on the Inventory page it repaints THAT grid",
   B["onInventory"]["calls"])
ok("renderAll" not in B["onInventory"]["calls"],
   "B2  ...and not the Demand Forecast")
eq("B3  the mode is saved, as it always was", B["onInventory"]["saved"], "90")
ok("clearVelMemo" in B["onInventory"]["calls"],
   "B4  the velocity memo is dropped first, or the column recomputes nothing")
ok("renderAll" in B["onForecast"]["calls"]
   and "renderInventoryTbl" not in B["onForecast"]["calls"],
   "B5  off that page it still repaints the Forecast, exactly as before",
   B["onForecast"]["calls"])
eq("B6  /!\\ THE DEFECT: the pre-v12.57 test chose renderAll even standing on "
   "the Inventory page, because the class is never set",
   B["oldOnInventory"], "renderAll")

# ===========================================================================
print("\nC. the mode actually reaches the column")
# ===========================================================================
ok(js.count("ipVelCompareMode()") >= 3,
   "C1  the Vel Trend derivation reads the mode in three places")
ok("velCmpMode" in js, "C2  ...off the one localStorage key both pages share")

# ===========================================================================
print("\nD. the release names itself")
# ===========================================================================
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "D1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok("v12.57" in C_, "D2  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
