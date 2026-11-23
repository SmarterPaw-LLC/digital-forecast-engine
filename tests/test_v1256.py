#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.56 - picking "Missing detail" widens the window, because the work is old.

- **Jason:** *"the summary shows '7 need detail' and when i go to the 'missing
  detail' toggle under fba shipments, nothing appears."*

Driven through the tab's own predicate against the live shapes:

| Missing detail + | rows |
|---|---|
| Last 365 days (the default) | **0** |
| All time | **7** |

Nothing else is broken. But a filter whose whole job is to find OUTSTANDING
work, behind a default window that hides anything over a year old, cannot do
that job - every one of the seven was created in 2023.

This suite also pins the second half of his message: *"why is the brand not
available? it's ALWAYS pulled through on the fba shipments page"* - the TAB
renders `+ Set` for those same seven, so the card is consistent with it.
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
print("  v12.56  a worklist filter may not be hidden by a default window")
print("=" * 70)

# ===========================================================================
print("\nA. the handler")
# ===========================================================================
H = fn_flat("fbaShipOnDetailChange")
ok("d.value === 'missing'" in H, "A1  it fires only on Missing detail")
ok("w.value !== '0'" in H,
   "A2  ...and only when the window is not already All time - a no-op repaint "
   "that moves a control is worse than none")
ok("fbaShipSetWindow('0')" in H,
   "A3  /!\\ it widens VISIBLY, through the control's own setter, so what "
   "changed is on screen (v12.46: a filter you cannot see is the defect)")
ok("renderFbaShipmentsTbl()" in H,
   "A4  every other pick just repaints")
ok('onchange="fbaShipOnDetailChange()"' in s,
   "A5  the select calls it")
ok('id="fba-ship-detail" onchange="renderFbaShipmentsTbl()"' not in s,
   "A6  ...and the old direct repaint is gone, not left beside it")
ok("also sets the window to All time" in s,
   "A7  the control says what it does")

# ===========================================================================
print("\nB. his two claims, driven through the REAL tab path")
# ===========================================================================
R = fn_flat("renderFbaShipmentsTbl")
i = R.index("  let arr = [...groups.values()].filter(g => {")
PRED = R[i:R.index("\n  });\n", i) + len("\n  });\n")]

B = run_node(os.path.join(SP, "_v1256_b.js"),
             fn_flat("shipGroupBrand") + "\n" + fn_flat("shipBrandCell") + r"""
function esc2(x){return String(x==null?'':x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function setShipmentBrand(){}
const allProducts = [{ master_id:'SP-0034', brand:'Meowijuana' }];

// The seven summary-only groups the merge builds, exactly as the live table
// holds them: no items, no summary.brand, every one created in 2023.
const SEVEN = [
 ['FBA179Z6SM14','2023-07-31'],['FBA1786R71JD','2023-06-21'],
 ['FBA174L6CT45','2023-04-26'],['FBA173CRYC0V','2023-04-05'],
 ['FBA173082ZD8','2023-03-29'],['FBA1713ZZTC3','2023-02-20'],
 ['FBA170ZZSJKJ','2023-02-14'],
].map(([id,d]) => ({ shipment_id:id, created_date:d, region:'CA', items:[],
                     has_detail:false, summary:{ status:'Closed', brand:null } }));
const WITHDETAIL = { shipment_id:'FBA2026X', created_date:'2026-11-16', region:'US',
  items:[{ master_id:'SP-0034' }], has_detail:true, summary:{ status:'Closed', brand:null } };

function run(winDays, detailFilter) {
  const groups = new Map();
  [...SEVEN, WITHDETAIL].forEach((g,n) => groups.set(String(n), g));
  const region = '', brandFilter = '', q = '';
  const cutoff = winDays ? (() => { const d = new Date('2026-11-23T12:00:00');
    d.setDate(d.getDate() - winDays); return d.toISOString().slice(0,10); })() : null;
""" + PRED.replace("  let arr =", "  const arr =") + r"""
  return arr;
}
const all = run(0, 'missing');
console.log(JSON.stringify({
  rows365: run(365, 'missing').length,
  rowsAll: all.length,
  idsAll: all.map(g => g.shipment_id),
  tabBrand: all.map(g => shipBrandCell(g).includes('+ Set') ? '+ Set'
                       : shipBrandCell(g).replace(/<[^>]+>/g,'').trim()),
  withDetailBrand: shipBrandCell(WITHDETAIL).replace(/<[^>]+>/g,'').trim(),
}));
""")

eq("B1  /!\\ HIS SCREEN: Missing detail at the 365-day default returns ZERO",
   B["rows365"], 0)
eq("B2  ...and All time returns the seven the card names", B["rowsAll"], 7)
eq("B3  the same seven, by id", B["idsAll"][0], "FBA179Z6SM14")

# ===========================================================================
print("\nC. \"it's ALWAYS pulled through on the fba shipments page\"")
# ===========================================================================
eq("C1  /!\\ THE TAB RENDERS `+ Set` FOR THOSE SAME SEVEN - the card is "
   "consistent with it, not different from it",
   sorted(set(B["tabBrand"])), ["+ Set"])
eq("C2  ...and a shipment WITH detail does resolve its brand from the items, "
   "which is why it is 'always pulled through' everywhere else",
   B["withDetailBrand"], "Meowij")
G = fn_flat("shipGroupBrand")
ok("if (!g.items || !g.items.length) return '';" in G,
   "C3  no items is the whole reason: brand comes from the per-shipment items, "
   "and a summary-only row has none")

# ===========================================================================
print("\nD. the release names itself")
# ===========================================================================
C_ = io.open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
chip = re.search(r"(v\d+\.\d+)\s*·\s*(\d{4}-\d{2}-\d{2})", s)
decl = re.search(r"current version \*\*(v\d+\.\d+)\*\*", C_)
ok(chip is not None and decl is not None and chip.group(1) == decl.group(1),
   "D1  the version chip and CLAUDE.md name the SAME release",
   "%s vs %s" % (chip.group(1) if chip else None, decl.group(1) if decl else None))
ok("v12.56" in C_, "D2  CLAUDE.md carries the entry")

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
