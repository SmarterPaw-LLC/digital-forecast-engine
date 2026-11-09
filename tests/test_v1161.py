#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" v11.61 - the prior-year line matches what you drilled into.

Jason: "when i drill in, it's showing the previous period total, not the
previous period for the same drill in."

Declared "Still open" since v11.56 and true since v11.41: seoTr.prev was
fetched SITEWIDE only, so isolating Organic Search compared one channel
against the whole site.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1161_")
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
    t = re.sub(r"(?m)^\s*//.*$", "", t)
    return re.sub(r"/\*[\s\S]*?\*/", "", t)


def fn(name):
    i = js.index("function " + name + "(")
    if js[i - 6:i] == "async ":
        i -= 6
    d, started, k = 0, False, js.index("{", js.index("function " + name + "("))
    while k < len(js):
        c = js[k]
        if c == "{":
            d += 1; started = True
        elif c == "}":
            d -= 1
            if started and d == 0:
                return js[i:k + 1]
        k += 1
    raise RuntimeError("unbalanced " + name)


def run(body):
    p = os.path.join(SP, "h.js")
    io.open(p, "w", encoding="utf-8", newline="").write(body)
    r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr[-2500:])
    return json.loads(r.stdout)


CODE = nocomment(js)

# ===========================================================================
print("\nA. Last year's BREAKDOWNS are fetched, on the same 364-day shift")
# ===========================================================================
ld = js[js.index("async function loadSeoTraffic"):]
ld = ld[:ld.index("\n}")]
eq("A1  three prior-year fetches (total + channel + device)",
   ld.count("shift(w.from,364)"), 3)
eq("A2  by_date_channel is fetched twice (this year + last)",
   ld.count("'ga4_by_date_channel'"), 2)
eq("A3  by_date_device likewise", ld.count("'ga4_by_date_device'"), 2)
# /!\ v11.41's rule: 364 days, not 365. 52 whole weeks keeps a Monday on a
# Monday; a one-day slip puts a weekend against a weekday.
ok("365" not in nocomment(ld), "A4  no 365 anywhere in the loader")
ok("prevChan, prevDev" in ld, "A5  both land on seoTr")

# v11.82 - the shape was a LITERAL at two sites and the GA4 button would have
# made it three. Three literals of one shape is how a field gets added to two
# of them, which is the risk this assertion was written for - so it now pins
# the shape to ONE declaration and checks every reset goes through it, rather
# than counting copies.
SHAPE = "{ days: [], chan: [], dev: [], pages: [], prev: [], prevChan: [], prevDev: [] }"
eq("A6  /!\\ the EMPTY shape is declared exactly ONCE",
   js.count("const SEO_TR_EMPTY = () => (" + SHAPE + ");"), 1)
eq("A6b /!\\ ...and no site writes the literal out beside it",
   js.count("seoTr = " + SHAPE + ";"), 0)
ok(js.count("SEO_TR_EMPTY()") >= 3,
   "A6c every reset goes through it - the initial, the failure path and the pull",
   js.count("SEO_TR_EMPTY()"))

# ===========================================================================
print("\nB. The REAL seoTrPrevRows, driven")
# ===========================================================================
HARNESS = r"""
const mk = (n, extra) => Object.assign({ day: '2026-10-01', sessions: n }, extra || {});
const seoTr = {
  prev:     [mk(100), mk(101)],
  prevChan: [mk(10, { channel: 'Organic Search' }), mk(20, { channel: 'Direct' }),
             mk(30, { channel: 'Paid Social' }),    mk(40, { channel: null })],
  prevDev:  [mk(50, { device: 'mobile' }), mk(60, { device: 'desktop' })],
};
let seoTrSel = { dim: '', keys: new Set(), pages: new Set() };
const EL = { 'seo-tr-chan': { value: '' }, 'seo-tr-dev': { value: '' } };
globalThis.document = { getElementById: (id) => EL[id] || null };
""" + fn("seoTrPrevRows") + r"""
const sum = rows => rows.reduce((a, r) => a + r.sessions, 0);
const out = {};
const snap = k => { out[k] = { n: seoTrPrevRows().length, total: sum(seoTrPrevRows()) }; };

snap('sitewide');

seoTrSel = { dim: 'channel', keys: new Set(['Organic Search']), pages: new Set() };
snap('oneChannel');
seoTrSel = { dim: 'channel', keys: new Set(['Organic Search', 'Direct']), pages: new Set() };
snap('twoChannels');
seoTrSel = { dim: 'device', keys: new Set(['mobile']), pages: new Set() };
snap('oneDevice');

// A GA4 null renders as '(not set)' in the CURRENT rollup, so the prior-year
// lookup has to resolve it the same way or the match silently misses.
seoTrSel = { dim: 'channel', keys: new Set(['(not set)']) };
snap('notSet');

// A DROPDOWN PICK WINS over a row selection, exactly as the chart does.
seoTrSel = { dim: 'channel', keys: new Set(['Organic Search']), pages: new Set() };
EL['seo-tr-chan'].value = 'Paid Social';
snap('dropdownBeatsSelection');
EL['seo-tr-chan'].value = '';
EL['seo-tr-dev'].value = 'desktop';
snap('devicePick');
// Both picked is REFUSED, not guessed at (v11.41).
EL['seo-tr-chan'].value = 'Direct';
snap('bothPicked');
EL['seo-tr-chan'].value = ''; EL['seo-tr-dev'].value = '';
seoTrSel = { dim: '', keys: new Set(), pages: new Set() };

// A load that predates v11.61 has no breakdowns: no line beats a wrong one.
seoTr.prevChan = [];
seoTrSel = { dim: 'channel', keys: new Set(['Direct']), pages: new Set() };
snap('noPriorBreakdown');
// ...and a MISSING key (undefined, not []) must not throw either.
delete seoTr.prevDev;
seoTrSel = { dim: 'device', keys: new Set(['mobile']), pages: new Set() };
snap('prevDevUndefined');
console.log(JSON.stringify(out));
"""
B = run(HARNESS)

eq("B1  nothing picked -> the SITEWIDE prior year, unchanged", B["sitewide"],
   {"n": 2, "total": 201})
eq("B2  one channel ticked -> that channel last year", B["oneChannel"],
   {"n": 1, "total": 10})
eq("B3  two ticked -> both, summed", B["twoChannels"], {"n": 2, "total": 30})
eq("B4  a device ticked -> that device last year", B["oneDevice"],
   {"n": 1, "total": 50})
eq("B5  '(not set)' matches a NULL row, as the current rollup does",
   B["notSet"], {"n": 1, "total": 40})
eq("B6  a dropdown pick WINS over a row selection", B["dropdownBeatsSelection"],
   {"n": 1, "total": 30})
eq("B7  a device pick resolves on the device feed", B["devicePick"],
   {"n": 1, "total": 60})
eq("B8  channel AND device picked is refused, not intersected",
   B["bothPicked"], {"n": 0, "total": 0})
eq("B9  no prior breakdown on record -> NO line rather than the site's",
   B["noPriorBreakdown"], {"n": 0, "total": 0})
eq("B10 an absent feed does not throw", B["prevDevUndefined"], {"n": 0, "total": 0})

# ===========================================================================
print("\nC. ONE resolver, two readers - the cards and the chart")
# ===========================================================================
eq("C1  declared exactly once", CODE.count("function seoTrPrevRows()"), 1)
eq("C2  and called from exactly two places", CODE.count("seoTrPrevRows()") - 1, 2)
# /!\ The retired sitewide reads are GONE, not bypassed - otherwise the two
# could drift back apart one edit later.
ok("seoTrSum(seoTr.prev)" not in CODE, "C3  the cards no longer sum the site's prior year")
ok("rollBy(seoTr.prev, null)" not in CODE, "C4  nor does the chart roll it")

# The v11.41 chip suppression was replaced by a condition that is now SUFFICIENT.
ok("const yoy = (k, good) => (prv[k] > 0)" in CODE,
   "C5  a chip renders whenever this scope HAS a prior year")
ok("!chanPick && !devPick && prv[k] > 0" not in CODE,
   "C6  ...and the blanket suppression is gone")

# ===========================================================================
print("\nD. The line SAYS which population it is")
# ===========================================================================
ok("(prior year)" in CODE, "D1  the label is still spelled one way")
for frag in ["selKeys.length === 1 ? selKeys[0]",
             "scoped ? `${scoped} (prior year)`",
             "'Sessions (prior year)'"]:
    ok(frag in js, "D2  names the %s case" % frag[:28])
# Rule 3a: the label and the subtitle use the SAME noun for the same thing.
# v11.65 - the dimension is resolved into `selDim` first, because a page
# selection draws pages and `seoTrSel.dim` names the channel/device pick beside
# it. The guarantee is unchanged: ONE noun function, never a second word.
ok("seoTrSelNoun(selDim, selKeys.length)" in js,
   "D3  a multi-key label reuses the subtitle's noun rather than coining one")
ok("const selDim = hasPages ? 'page' : seoTrSel.dim;" in js,
   "D3b and it names what is DRAWN, not the pick beside it")

# ===========================================================================
print("\nE. The file still parses")
# ===========================================================================
p = os.path.join(SP, "app.js")
io.open(p, "w", encoding="utf-8", newline="").write(js)
r = subprocess.run(["node", "--check", p], capture_output=True, text=True, encoding="utf-8")
eq("E1  node --check clean", r.returncode, 0)

print("\n%s  %d passed, %d failed" % ("PASS" if not failed else "FAIL", passed, failed))
sys.exit(1 if failed else 0)
