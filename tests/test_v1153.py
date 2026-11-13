#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.53 - the SEO Traffic period control converges on every other page's.

Jason: "on seo i don't have the same date pickers as the other pages."
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1153_")
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

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


# v12.37 - PNL_PERIODS and PNL_PERIOD_ALIAS are top-level literals, not
# functions, so they need their own slicer. Sliced, never stubbed.
def const_block(name):
    i = s.index("const " + name + " = ")
    close = "];" if s.startswith("const " + name + " = [", i) else "};"
    return s[i:s.index(close, i) + 2]

def fn(name):
    i = js.index("function " + name + "(")
    d, started, k = 0, False, js.index("{", i)
    while k < len(js):
        if js[k] == "{":
            d += 1; started = True
        elif js[k] == "}":
            d -= 1
            if started and d == 0:
                return js[i:k + 1]
        k += 1
    raise SystemExit("unbalanced %s" % name)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 62)
print("  v11.53  the SEO period control matches every other page")
print("=" * 62)

# ---------------------------------------------------------------------------
# A. THE DIVERGENCE, closed.  Same values, same order, same vocabulary.
# ---------------------------------------------------------------------------
# v12.37 - /!\ THE DIVERGENCE IS NOW CLOSED BY A REGISTRY, not by two lists
# happening to match. PNL_PERIODS is the one declaration; the SEO picker is
# the only one built in JS, so it is the only one that can take the
# generator, and the static four are pinned against the same registry in
# test_v1237. Scraping literal <option> strings out of a generated control
# finds none - the guarantee moved, it did not weaken.
reg = s[s.index("const PNL_PERIODS = ["):s.index("];", s.index("const PNL_PERIODS = ["))]
ref_vals = re.findall(r"v: '([^']*)'", reg)
ref_labels = [x for x in re.findall(r"label: '([^']*)'", reg)]

seo_block = s[s.index("seo-tr-period"):s.index("seo-tr-custom-wrap")]
eq("A1 the SEO picker is built FROM the registry, not from a second list",
   "pnlPeriodOptionsHtml('90')" in seo_block, True)
ok("<option value=" not in seo_block,
   "A1b /!\\ ...and no hand-written option survives beside it")
ok("custom" in ref_vals, "A2 including a custom range, which it had none of")
ok(len(ref_vals) == 16 and len(ref_labels) == 16,
   "A3 sixteen windows, not five", len(ref_vals))
ok(ref_vals == list(dict.fromkeys(ref_vals)), "A3b no key declared twice")
ok(ref_labels == list(dict.fromkeys(ref_labels)),
   "A3c and no two windows share a label - one label, one measure")

# All four controls the shared v11.02 bar shape requires.
for ident in ("seo-tr-period", "seo-tr-custom-wrap", "seo-tr-from", "seo-tr-to"):
    eq("A4 exactly one %s" % ident, s.count('id="%s"' % ident), 1)

# ---------------------------------------------------------------------------
# B. seoTrWindow resolves every one of them.
# ---------------------------------------------------------------------------
B = run_node(os.path.join(SP, "b.js"), """
// v12.37 - the sixteen declared windows PLUS the two retired spellings,
// which saved views still hold and which must keep resolving.
const VALS = """ + json.dumps(ref_vals + ["this-month", "0"]) + r""";
let PERIOD = '90', FROM = '', TO = '';
globalThis.document = { getElementById: (id) =>
  id === 'seo-tr-period' ? { value: PERIOD }
  : id === 'seo-tr-from' ? { value: FROM }
  : id === 'seo-tr-to' ? { value: TO } : null };
""" + fn("seoTrWindow") + "\n"
   + fn("computePnlDateRange") + "\n" + fn("pnlPeriodLabelOf") + "\n"
   + fn("pnlPeriodKey") + "\n" + const_block("PNL_PERIODS") + "\n"
   + const_block("PNL_PERIOD_ALIAS") + r"""
// Pin "today" so the suite is not date-dependent.
const RealDate = Date;
const FIXED = new RealDate(2026, 10, 3);     // 2026-11-03
globalThis.Date = class extends RealDate {
  constructor(...a) { if (!a.length) return new RealDate(FIXED); return new RealDate(...a); }
  static now() { return FIXED.getTime(); }
};
const out = {};
for (const v of VALS) {
  if (v === 'custom') continue;
  PERIOD = v;
  out[v] = seoTrWindow();
}
PERIOD = 'custom';
out.custom_empty = seoTrWindow();
FROM = '2026-03-01'; TO = '2026-03-31';
out.custom_full = seoTrWindow();
FROM = '2026-05-01'; TO = '2026-04-01';          // inverted
out.custom_inverted = seoTrWindow();
PERIOD = 'mtd';
out.mtd = seoTrWindow();
PERIOD = 'nonsense-value';
out.unknown = seoTrWindow();
console.log(JSON.stringify(out));
""")

# Inclusive day counts, as the other bars resolve them.
eq("B1 30 days spans 30 days inclusive", B["30"]["from"], "2026-10-05")
eq("B1b 365", B["365"]["from"], "2025-11-04")
eq("B2 Year to date starts Jan 1 of the CURRENT year", B["ytd"]["from"], "2026-01-01")
eq("B2b labelled", B["ytd"]["label"], "Year to date")
# v12.37 - `this-month` is `mtd` now, aliased so an old saved view still
# resolves. Both spellings must land on the 1st.
eq("B3 This month starts on the 1st", B["this-month"]["from"], "2026-11-01")
eq("B3b /!\\ ...and so does the name every other page uses for it",
   B["mtd"]["from"], "2026-11-01")
eq("B3c /!\\ ...and the retired '0' still means all time",
   B["0"]["from"], B["all"]["from"])
eq("B4 Last month is the WHOLE previous month", B["last-month"]["from"], "2026-10-01")
eq("B4b and ends on its last day, not today", B["last-month"]["to"], "2026-10-31")
ok(B["all"]["from"] < "2015-01-01",
   "B5 All time reaches before any GA4 data can exist", B["all"]["from"])

# ⚠ v10.79: an incomplete custom range is not a window.
ok(B["custom_empty"]["incomplete"] is True,
   "B6 an empty custom range reports itself INCOMPLETE")
eq("B6b and resolves no dates at all", [B["custom_empty"]["from"], B["custom_empty"]["to"]],
   [None, None])
eq("B7 a complete custom range is used verbatim",
   [B["custom_full"]["from"], B["custom_full"]["to"]], ["2026-03-01", "2026-03-31"])
ok(B["custom_full"]["label"].startswith("2026-03-01"),
   "B7b and labels itself with its own dates", B["custom_full"]["label"])
ok(B["custom_inverted"].get("incomplete") is True,
   "B8 a from AFTER its to is refused, not silently swapped")

ok(B["unknown"]["from"] and not B["unknown"]["from"].startswith("NaN"),
   "B9 an unknown value still yields a real date", B["unknown"]["from"])

# ---------------------------------------------------------------------------
# C. The custom wrap, and the repaint it must NOT do.
# ---------------------------------------------------------------------------
C = run_node(os.path.join(SP, "c.js"), """
let PERIOD = '90', FROM = '', TO = '', DISPLAY = 'none', LOADS = 0;
globalThis.document = { getElementById: (id) =>
  id === 'seo-tr-period' ? { value: PERIOD }
  : id === 'seo-tr-custom-wrap' ? { style: { get display() { return DISPLAY; },
                                             set display(v) { DISPLAY = v; } } }
  : id === 'seo-tr-from' ? { value: FROM }
  : id === 'seo-tr-to' ? { value: TO } : null };
globalThis.loadSeoTraffic = () => { LOADS++; };
""" + fn("seoTrWindow") + "\n" + fn("seoTrPeriodChange") + "\n"
   + fn("computePnlDateRange") + "\n" + fn("pnlPeriodLabelOf") + "\n"
   + fn("pnlPeriodKey") + "\n" + const_block("PNL_PERIODS") + "\n"
   + const_block("PNL_PERIOD_ALIAS") + r"""
const out = {};
PERIOD = '180'; seoTrPeriodChange();
out.plain = { display: DISPLAY, loads: LOADS };
PERIOD = 'custom'; seoTrPeriodChange();
out.openedEmpty = { display: DISPLAY, loads: LOADS };
FROM = '2026-03-01'; seoTrPeriodChange();
out.halfSet = { display: DISPLAY, loads: LOADS };
TO = '2026-03-31'; seoTrPeriodChange();
out.bothSet = { display: DISPLAY, loads: LOADS };
PERIOD = '90'; seoTrPeriodChange();
out.backToPreset = { display: DISPLAY, loads: LOADS };
console.log(JSON.stringify(out));
""")

eq("C1 a preset keeps the wrap hidden and repaints", C["plain"], {"display": "none", "loads": 1})
eq("C2 choosing Custom OPENS the wrap", C["openedEmpty"]["display"], "inline-flex")
eq("C2b and does NOT repaint - the window is incomplete (v10.79)",
   C["openedEmpty"]["loads"], 1)
eq("C3 one date set is still incomplete, still no repaint", C["halfSet"]["loads"], 1)
eq("C4 both dates set repaints exactly once more", C["bothSet"]["loads"], 2)
eq("C5 going back to a preset closes the wrap", C["backToPreset"]["display"], "none")
eq("C5b and repaints", C["backToPreset"]["loads"], 3)

# ---------------------------------------------------------------------------
# D. It joins the SHARED registry, so v11.28's click-to-scope works here too.
# ---------------------------------------------------------------------------
code = nocomment(js)
ok("'seo-tr': 'SEO Traffic'" in code,
   "D1 SEO is registered as a period host alongside the four P&L pages")
ok("periodHost: 'seo-tr'" in code,
   "D1b and the SEO chart declares it, so a click on a point scopes the window")
# The registry is what v11.28's own guard walks; this keeps the two in step.
hosts = re.findall(r"^\s*'?([a-z-]+)'?:\s*'[^']+',", code[code.index("const PNL_PERIOD_HOSTS"):
                                                          code.index("const PNL_PERIOD_HOSTS") + 400], re.M)
eq("D2 five hosts now", len(hosts), 5)
for h in hosts:
    for suffix in ("-period", "-custom-wrap", "-from", "-to"):
        ok(('id="%s%s"' % (h, suffix)) in s,
           "D3 %s has its %s control" % (h, suffix))

eq("D4 version chip", len(re.findall(r">v\d+\.\d+ · [\d-]+<", s)), 1)

for phrase in ("an incomplete custom range is not a window",
               "the SEO Traffic bar now carries the same four controls"):
    ok(phrase in js, "D5 the reasoning survives: %s" % phrase[:38])

print("\n" + "=" * 62)
print("  v11.53  PASS %d   FAIL %d" % (passed, failed))
print("=" * 62)
sys.exit(1 if failed else 0)
