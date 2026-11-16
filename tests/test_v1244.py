#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.44 - a ticked row narrows the scorecards, not just the chart.

- **Jason:** *"on seo page, checking a box doesn't change the scorecards"*

/!\ AND THE HALF HE COULD NOT SEE WAS WORSE. `seoTrPrevRows` has narrowed the
PRIOR year to the ticked rows since v11.61 while the cards read the two
DROPDOWNS alone - so ticking Organic Search left Sessions on the whole site
and compared it against last year's Organic Search. His screenshot: 53,466
sessions, +227.1% vs prev; $26,754 revenue, +540.6%.

A missing filter is visible. A delta between two different populations prints
a number that looks like an answer.
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


def line_of(name):
    m = re.search(r"(?m)^function " + name + r"\(.*$", js)
    return m.group(0)


def strip_comments(t):
    t = re.sub(r"/\*[\s\S]*?\*/", "", t)
    return re.sub(r"^\s*//.*$", "", t, flags=re.M)


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.44  one answer to which population is selected")
print("=" * 70)

# A stand-in for the two dropdowns and the tick state, plus the four feeds.
HARNESS = r"""
let PICK = { chan: '', dev: '' };
const document = { getElementById: (id) =>
  id === 'seo-tr-chan' ? { value: PICK.chan }
  : id === 'seo-tr-dev' ? { value: PICK.dev } : null };
let seoTrSel = { dim: '', keys: new Set(), pages: new Set() };
// Shaped like the live feeds: one row per day per key, every card metric on
// it. Figures are invented; the SHAPE is the migration's.
const D = (day, extra) => Object.assign(
  { day, sessions: 0, new_users: 0, engaged_sessions: 0, revenue: 0, transactions: 0 }, extra);
let seoTr = {
  days: [D('2026-11-01', { sessions: 1000, new_users: 800, engaged_sessions: 400,
                           revenue: 500, transactions: 20, total_users: 900, purchasers: 15 })],
  chan: [
    D('2026-11-01', { channel: 'Organic Search', sessions: 200, new_users: 150,
                      engaged_sessions: 110, revenue: 40, transactions: 3 }),
    D('2026-11-01', { channel: 'Direct',         sessions: 440, new_users: 300,
                      engaged_sessions: 180, revenue: 150, transactions: 6 }),
    D('2026-11-01', { channel: null,             sessions: 360, new_users: 350,
                      engaged_sessions: 110, revenue: 310, transactions: 11 }),
  ],
  dev: [
    D('2026-11-01', { device: 'mobile',  sessions: 480, revenue: 300, transactions: 12 }),
    D('2026-11-01', { device: 'desktop', sessions: 520, revenue: 200, transactions: 8 }),
  ],
  pages: [
    D('2026-11-01', { landing_page: '/a', channel: 'Organic Search', sessions: 70, revenue: 10 }),
    D('2026-11-01', { landing_page: '/a', channel: 'Direct',         sessions: 30, revenue: 5 }),
    D('2026-11-01', { landing_page: '/b', channel: 'Organic Search', sessions: 50, revenue: 7 }),
    D('2026-11-01', { landing_page: '',   channel: 'Direct',         sessions: 11, revenue: 1 }),
  ],
  prev:     [D('2025-11-02', { sessions: 900, revenue: 400 })],
  prevChan: [
    D('2025-11-02', { channel: 'Organic Search', sessions: 160, revenue: 60 }),
    D('2025-11-02', { channel: 'Direct',         sessions: 740, revenue: 340 }),
  ],
  prevDev:  [D('2025-11-02', { device: 'mobile', sessions: 500, revenue: 250 })],
};
""" + fn_flat("seoTrPageKey") + "\n" + fn_flat("seoTrSelNoun") + "\n" \
  + fn_flat("seoTrSum") + "\n" + fn_flat("seoTrScopeSel") + "\n" \
  + fn_flat("seoTrScopeRows") + "\n" + fn_flat("seoTrScopeLabel") + "\n" \
  + fn_flat("seoTrPrevRows") + r"""
// /!\ THE PRE-v12.44 CARD POPULATION, VERBATIM: the two dropdowns and
// nothing else. This is what printed 53,466 under a ticked Organic Search.
function oldScopeRows() {
  const chanPick = PICK.chan, devPick = PICK.dev;
  if (chanPick && devPick) return [];
  if (chanPick) return seoTr.chan.filter(r => r.channel === chanPick);
  if (devPick)  return seoTr.dev.filter(r => r.device === devPick);
  return seoTr.days;
}
const tick = (dim, ...keys) => { seoTrSel = { dim, keys: new Set(keys), pages: new Set() }; };
const pages = (...ks) => { seoTrSel = { dim: '', keys: new Set(), pages: new Set(ks) }; };
const clear = () => { seoTrSel = { dim: '', keys: new Set(), pages: new Set() };
                      PICK = { chan: '', dev: '' }; };
const snap = () => ({
  kind: seoTrScopeSel().kind,
  label: seoTrScopeLabel(),
  cur: seoTrSum(seoTrScopeRows()).sessions,
  curRev: seoTrSum(seoTrScopeRows()).revenue,
  old: seoTrSum(oldScopeRows()).sessions,
  oldRev: seoTrSum(oldScopeRows()).revenue,
  prev: seoTrSum(seoTrPrevRows()).sessions,
  prevRev: seoTrSum(seoTrPrevRows()).revenue,
});
"""

A = run_node(os.path.join(SP, "_v1244_a.js"), HARNESS + r"""
const out = {};
clear();                              out.site    = snap();
clear(); tick('channel', 'Organic Search');  out.tickOrg = snap();
clear(); tick('channel', 'Organic Search', 'Direct'); out.tick2 = snap();
clear(); tick('channel', '(not set)');       out.tickNull = snap();
clear(); tick('device', 'mobile');           out.tickDev = snap();
clear(); PICK.chan = 'Organic Search';       out.pick    = snap();
clear(); PICK.chan = 'Organic Search'; tick('channel', 'Direct'); out.pickBeatsTick = snap();
clear(); PICK.chan = 'Direct'; PICK.dev = 'mobile'; out.both = snap();
clear(); pages('/a', '/b');                  out.pages   = snap();
clear(); pages('/a'); PICK.chan = 'Organic Search'; out.pagesInChan = snap();
clear(); pages('');                          out.pageBlank = snap();
console.log(JSON.stringify(out));
""")

# ===========================================================================
print("\nA. /!\\ THE DEFECT: the card and its delta described different sites")
# ===========================================================================
eq("A1  /!\\ the OLD card population ignored the tick entirely - the whole "
   "site's sessions under a ticked Organic Search", A["tickOrg"]["old"], 1000)
eq("A2  /!\\ ...while the PRIOR year had already narrowed to that channel",
   A["tickOrg"]["prev"], 160)
_old_pct = round((1000 - 160) / 160 * 100, 1)
ok(_old_pct > 200,
   "A3  /!\\ so the chip computed +%.1f%% - Jason's screenshot reads +227.1%% "
   "on the same shape" % _old_pct)
eq("A4  /!\\ and the shipped one narrows, so the two sides are one population",
   A["tickOrg"]["cur"], 200)
_new_pct = round((200 - 160) / 160 * 100, 1)
ok(_new_pct < 30,
   "A5  ...which makes the chip +%.1f%%, a number that means something" % _new_pct)
eq("A6  revenue, the card that read +540.6%%: old 500 against last year's 60",
   [A["tickOrg"]["oldRev"], A["tickOrg"]["prevRev"]], [500, 60])
eq("A7  ...and shipped, 40 against 60", A["tickOrg"]["curRev"], 40)

# ===========================================================================
print("\nB. /!\\ NOTHING TICKED, NOTHING MOVED")
# ===========================================================================
eq("B1  /!\\ with no selection at all the shipped population IS the old one",
   A["site"]["cur"], A["site"]["old"])
eq("B2  ...sitewide, which is 1000", A["site"]["cur"], 1000)
eq("B3  and under a DROPDOWN pick the two still agree - the dropdown was "
   "never the broken half", A["pick"]["cur"], A["pick"]["old"])
eq("B4  ...which is the channel's own 200", A["pick"]["cur"], 200)
eq("B5  a dropdown pair still renders nothing to compare",
   [A["both"]["cur"], A["both"]["old"]], [0, 0])
eq("B6  /!\\ and a dropdown pick still BEATS a tick, which is seoTrPrevRows' "
   "own order and would silently move the prior-year line if it changed",
   A["pickBeatsTick"]["cur"], 200)

# ===========================================================================
print("\nC. the decision table")
# ===========================================================================
eq("C1  nothing selected", A["site"]["kind"], "site")
eq("C2  ticked channels", A["tickOrg"]["kind"], "channel")
eq("C3  ticked devices", A["tickDev"]["kind"], "device")
eq("C4  ticked pages", A["pages"]["kind"], "page")
eq("C5  both dropdowns", A["both"]["kind"], "both")
eq("C6  two ticks sum both", A["tick2"]["cur"], 640)
eq("C7  /!\\ a NULL channel resolves through the same '(not set)' fallback "
   "the rollup uses - GA4 writes nulls, and matching a ticked '(not set)' "
   "against one is how a selection silently returns nothing",
   A["tickNull"]["cur"], 360)
eq("C8  a ticked device narrows to it", A["tickDev"]["cur"], 480)
eq("C9  ticked pages sum across their channels", A["pages"]["cur"], 70 + 30 + 50)
eq("C10 /!\\ ...and a channel pick NARROWS them, which is the one crossing "
   "GA4 reports (v11.65)", A["pagesInChan"]["cur"], 70)
eq("C11 a blank landing page is its own key, never merged with '(not set)'",
   A["pageBlank"]["cur"], 11)

# ===========================================================================
print("\nD. the label says which population")
# ===========================================================================
eq("D1  nothing selected", A["site"]["label"], "all channels and devices")
eq("D2  one tick names it", A["tickOrg"]["label"], "Organic Search")
eq("D3  two ticks count them", A["tick2"]["label"], "2 channel groups")
eq("D4  devices get the device noun", A["tickDev"]["label"], "mobile")
eq("D5  pages get the page noun", A["pages"]["label"], "2 landing pages")
eq("D6  /!\\ and a page selection inside a channel says BOTH, because it is "
   "a crossing", A["pagesInChan"]["label"], "/a in Organic Search")
eq("D7  a blank page reads as (blank), not as an empty string",
   A["pageBlank"]["label"], "(blank)")
eq("D8  a dropdown pair has nothing to label", A["both"]["label"], "")

# ===========================================================================
print("\nE. /!\\ THE PRIOR YEAR IS UNCHANGED - a refactor, not a behaviour move")
# ===========================================================================
E = run_node(os.path.join(SP, "_v1244_e.js"), HARNESS + r"""
// /!\ seoTrPrevRows AS IT STOOD BEFORE v12.44, VERBATIM, beside the shipped
// one. This release rewired it to share the decision; it may not have
// changed a single answer.
function oldPrevRows() {
  const sel = seoTrSel;
  const chanPick = PICK.chan, devPick = PICK.dev;
  if (sel.pages && sel.pages.size) return [];
  if (!chanPick && !devPick && sel.dim && sel.keys.size) {
    const fld = sel.dim === 'channel' ? 'channel' : 'device';
    const src = sel.dim === 'channel' ? seoTr.prevChan : seoTr.prevDev;
    return (src || []).filter(r => sel.keys.has(r[fld] || '(not set)'));
  }
  if (chanPick && devPick) return [];
  if (chanPick) return (seoTr.prevChan || []).filter(r => (r.channel || '(not set)') === chanPick);
  if (devPick)  return (seoTr.prevDev  || []).filter(r => (r.device  || '(not set)') === devPick);
  return seoTr.prev || [];
}
const states = [
  () => {},
  () => tick('channel', 'Organic Search'),
  () => tick('channel', 'Organic Search', 'Direct'),
  () => tick('device', 'mobile'),
  () => { PICK.chan = 'Organic Search'; },
  () => { PICK.dev = 'mobile'; },
  () => { PICK.chan = 'Direct'; PICK.dev = 'mobile'; },
  () => pages('/a'),
  () => { pages('/a'); PICK.chan = 'Organic Search'; },
  () => { tick('channel', 'Direct'); PICK.chan = 'Organic Search'; },
  () => { tick('device', 'mobile'); PICK.dev = 'desktop'; },
];
const out = [];
for (const set of states) {
  clear(); set();
  out.push([JSON.stringify(seoTrPrevRows()) === JSON.stringify(oldPrevRows()),
            seoTrSum(seoTrPrevRows()).sessions]);
}
console.log(JSON.stringify({ same: out.map(x => x[0]), vals: out.map(x => x[1]) }));
""")
eq("E1  /!\\ ELEVEN states, and the rewired resolver answers IDENTICALLY to "
   "the one it replaces in every one", E["same"], [True] * 11)
eq("E2  ...and they are not all the same answer, so that is not vacuous",
   len(set(E["vals"])) > 2, True)
eq("E3  a page selection still draws NO prior year (v11.65)", E["vals"][7], 0)
eq("E4  ...and so does a dropdown pair", E["vals"][6], 0)

# ===========================================================================
print("\nF. one resolver, and the SHARE column is not it")
# ===========================================================================
NO_C = strip_comments(js)
RST = fn_flat("renderSeoTraffic")
eq("F1  one decision function", NO_C.count("function seoTrScopeSel"), 1)
ok("seoTrScopeSel()" in fn_flat("seoTrPrevRows"),
   "F2  /!\\ the prior year reads it rather than carrying a second copy - "
   "two resolvers for one control is how these came to disagree")
ok("const cur = seoTrSum(seoTrScopeRows());" in RST,
   "F3  and so do the cards")
ok("seoTrRenderBreakdowns(scopeCur)" in RST,
   "F4  /!\\ but the breakdown tables' SHARE is a share of the SCOPE, not of "
   "the selection - narrowing it would print 100% beside every row just "
   "ticked and a share of a denominator excluding the rest")
ok("const scopeCur = seoTrSum(scopeRows);" in RST,
   "F5  ...which is the dropdown scope, exactly as before")
ok("seoTrRenderChart(scopeRows," in RST,
   "F6  /!\\ and the CHART is handed what it was handed before. Its bands "
   "apply the ticks themselves; `rows` is its x-axis and its unscoped total, "
   "so narrowing it would drop a day with no rows out of the axis")
ok(RST.index("const scopeCur") < RST.index("const cur = seoTrSum"),
   "F7  the scope is resolved before the selection narrows it")
ok("scopeNote = seoTrScopeLabel() || scopeNote;" in RST,
   "F8  /!\\ and the sub-line follows the number. A narrowed figure under "
   "'all channels and devices' is the same defect written in words")

# ===========================================================================
print("\nG. every card metric EXISTS in every breakdown")
# ===========================================================================
# Measured against information_schema: ga4_by_date_channel, _device and
# _landing_page all carry sessions, new_users, engaged_sessions, revenue and
# transactions - so no card has to refuse under a selection. total_users and
# purchasers are missing from the landing-page feed and are on no card.
CARDS = re.search(r"cards\.innerHTML = bothPicked[\s\S]*?\]\);", js).group(0)
for k in ("sessions", "new_users", "engaged_sessions", "revenue", "transactions"):
    ok("cur." + k in CARDS, "G1  the cards read cur.%s" % k)
for k in ("total_users", "purchasers"):
    ok("cur." + k not in CARDS,
       "G2  /!\\ and NOT cur.%s, which the landing-page feed does not carry - "
       "a card reading it would quietly show 0 under a page selection" % k)
SEL = js[js.index("'day,landing_page,channel"):js.index("'", js.index("'day,landing_page,channel") + 1)]
for k in ("sessions", "new_users", "engaged_sessions", "revenue", "transactions"):
    ok(k in SEL, "G3  ...and the landing-page fetch selects %s" % k)

print("\n" + "-" * 70)
print("  %d passed, %d failed" % (passed, failed))
print("-" * 70)
sys.exit(1 if failed else 0)
