#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v11.65 - landing pages are selectable, and they COMPOSE with channel groups.

Jason: "on seo, i should have checkmarks next to the pages so i can select and
see the graph update. this should work in combination with the channel group
filters"

v11.57 established ONE SELECTION, ONE DIMENSION, because GA4 reports channel
and device as two independent breakdowns with no table crossing them. Landing
pages are the exception, and the exception is in the schema rather than in an
opinion: `ga4_by_date_landing_page` is keyed (property, day, landing_page,
channel) and its own migration calls it "Landing page x channel. THE SEO
TABLE". So a page measured within a set of channels is ONE table's own count.

That table has NO device column, so page-vs-device still does not cross.

This suite owns:
  * the composition rule, checked against the SCHEMA rather than against memory
  * what the chart draws for each combination, measured on the real renderer
  * that a page selection draws NO prior-year line (the v11.61 defect, which
    the site's own prior year would reproduce exactly)
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1165_")
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)
sql = io.open(os.path.join(ROOT, "supabase_v11_36_ga4.sql"), encoding="utf-8", newline="").read()

TINT = "rgba(127,211,42,0.10)"      # the selected-row tint, shared app-wide

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
    # /!\ LINE comments only - stripping block comments from this file eats
    # 824,674 characters (v11.63).
    return re.sub(r"(?m)^\s*//.*$", "", t)


def fn(name):
    i = js.index("function " + name + "(")
    while i > 0 and js[i - 1] not in "\n":
        i -= 1
    d, started, k = 0, False, js.index("{", js.index("function " + name + "("))
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
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


# v11.74 - the shared chart settings the controls and the series builder now
# read. Lifted from the shipped file rather than stubbed, so a default that
# moves fails this suite instead of being papered over.
V1174 = (re.search(r"const PNL_GRAIN_ORDER = \[[^\]]*\];", js).group(0) + chr(10)
         + re.search(r"const PNL_FILL_ALPHA = \{[^}]*\};", js).group(0) + chr(10)
         + re.search(r"const PNL_FILL_LINE = '[^']*';", js).group(0) + chr(10)
         + fn("pnlChartGrain") + chr(10) + fn("pnlGrainAuto") + chr(10)
         + fn("pnlGrainResolve") + chr(10) + fn("pnlGrainKey") + chr(10)
         + fn("pnlGrainAdv") + chr(10) + fn("pnlChartFill") + chr(10)
         + fn("pnlStackAlpha") + chr(10))

print("\n" + "=" * 68)
print("  v11.65  landing pages select, and compose with channel groups")
print("=" * 68)

NC = nocomment(js)


# ===========================================================================
print("\nA. /!\\ THE COMPOSITION RULE COMES FROM THE SCHEMA, not from memory")
# ===========================================================================
lp = sql[sql.index("create table if not exists ga4_by_date_landing_page"):]
lp = lp[:lp.index(");")]
ok("channel" in lp, "A1  the landing-page table carries a channel column")
ok("primary key (property, day, landing_page, channel)" in lp,
   "A2  /!\\ and channel is part of its PRIMARY KEY - a real crossing")
ok(not re.search(r"^\s*device\b", lp, re.M),
   "A3  /!\\ it has NO device column, so page-vs-device still does not cross")
# The access pattern this release serves is the one the index was built for.
ok("ga4_lp_channel_idx" in sql and "(property, channel, day)" in sql,
   "A4  and the (channel, day) index is already there for it")
# No (channel x device) table anywhere - the v11.41 refusal is unchanged.
ok("ga4_by_date_channel_device" not in sql,
   "A5  there is still no (channel x device) table")
# The loader has to actually SELECT the column the crossing depends on.
ok("'day,landing_page,channel,sessions" in js,
   "A6  and the loader selects landing_page AND channel")


# ===========================================================================
print("\nB. the REAL seoTrRenderPages, driven")
# ===========================================================================
PAGES = fn("seoTrPageKey") + "\n" + fn("seoTrRowsLocked") + "\n" + fn("seoTrSelNoun") \
      + "\n" + fn("esc2") + "\n" + fn("seoTrPageUrl") + "\n" + fn("seoTrRenderPages")
SITE = re.search(r"const SEO_TR_SITE = \{[^}]*\};", js).group(0)

HARNESS = SITE + r"""
const mk = (p, c, n) => ({ landing_page: p, channel: c, sessions: n,
                           new_users: n, engaged_sessions: n, revenue: n, transactions: 1 });
const seoTr = { pages: [
  mk('/', 'Organic Search', 500), mk('/', 'Direct', 300),
  mk('/collections/toys', 'Organic Search', 200),
  mk('/pages/meowijuana', 'Paid Social', 120),
  // /!\ A landing page is a GA4 string. This one is the injection probe.
  mk('/x"><b>bad</b>', 'Direct', 90),
  mk('(not set)', 'Direct', 80),
  mk('', 'Direct', 70),
] };
let CHAN = '', DEV = '';
const EL = {};
globalThis.document = { getElementById: (id) => {
  if (id === 'seo-tr-chan') return { get value() { return CHAN; } };
  if (id === 'seo-tr-dev')  return { get value() { return DEV; } };
  return (EL[id] || (EL[id] = { id, innerHTML: '' }));
} };
function seoTrScopePicked() { return !!(CHAN || DEV); }
let seoTrSel = { dim: '', keys: new Set(), pages: new Set() };
const _seoTrRendered = { channel: [], device: [], page: [] };
""" + PAGES

B = run_node(os.path.join(SP, "b.js"), HARNESS + r"""
const html = () => EL['seo-tr-pages'].innerHTML;
const out = {};
seoTrRenderPages('', '');
out.plain = {
  rendered: _seoTrRendered.page.slice(),
  headerBox: /seoTrToggleAll\('page'\)/.test(html()),
  rowCalls: (html().match(/seoTrToggleRow\('page',\d+\)/g) || []).length,
  rowTrClicks: (html().match(/<tr[^>]*onclick=/g) || []).length,
  rawBold: (html().match(/<b>/g) || []).length,
  escaped: html().includes('&lt;b&gt;'),
  ths: (html().match(/<th[ >]/g) || []).length,
  stopProp: (html().match(/onclick="event\.stopPropagation\(\)"/g) || []).length,
  blankLabel: html().includes('(blank)'),
};

seoTrSel.pages = new Set(['/collections/toys']);
seoTrRenderPages('', '');
out.ticked = {
  tint: (html().match(/background:rgba\(127,211,42,0\.10\)/g) || []).length,
  selFlags: (html().match(/data-sel="1"/g) || []).length,
  checked: (html().match(/ checked/g) || []).length,
};

// A CHANNEL pick is the COMBINATION, so the boxes stay live under it.
CHAN = 'Organic Search';
seoTrRenderPages('Organic Search', '');
out.underChannel = {
  locked: /disabled/.test(html()),
  rows: _seoTrRendered.page.slice(),
  rowClicks: (html().match(/seoTrToggleRow\('page',\d+\)/g) || []).length,
};
CHAN = '';

// A DEVICE pick has no crossing, so they lock.
DEV = 'mobile';
seoTrRenderPages('', '');
out.underDevice = {
  disabled: (html().match(/ disabled/g) || []).length,
  notAllowed: (html().match(/cursor:not-allowed/g) || []).length,
  rowTrClicks: (html().match(/<tr[^>]*onclick=/g) || []).length,
  boxHandlers: (html().match(/seoTrToggleRow\('page',\d+\)/g) || []).length,
  pointer: (html().match(/cursor:pointer/g) || []).length,
  tipSaysWhy: /no device column/.test(html()),
};
DEV = '';

// The empty state.
seoTrRenderPages('', 'zzzz-no-such-page');
out.empty = (html().match(/colspan="(\d+)"/) || [])[1];
console.log(JSON.stringify(out));
""")

eq("B1  every page row is addressable, blank and (not set) included",
   B["plain"]["rendered"],
   ['/', '/collections/toys', '/pages/meowijuana', '/x"><b>bad</b>', '(not set)', ''])
ok(B["plain"]["headerBox"], "B2  a header select-all, as the other tables have")
# Six rows, each wiring the row itself and its own checkbox.
eq("B2b one toggle per row and one per checkbox", B["plain"]["rowCalls"], 12)
eq("B2c and the row itself is clickable", B["plain"]["rowTrClicks"], 6)
# /!\ The v11.23 rule: the untrusted string never reaches an attribute.
eq("B3  /!\\ zero raw <b> survives the injection probe", B["plain"]["rawBold"], 0)
ok(B["plain"]["escaped"], "B3b and it renders escaped as text")
eq("B4  seven header cells, the checkbox included", B["plain"]["ths"], 7)
ok(B["plain"]["blankLabel"], "B5  a blank landing page still renders as (blank)")
# Four anchors, not six: v11.62 excludes '(not set)' and the blank before a
# URL is even built, so those two rows render a <span> with nothing to stop.
eq("B6  every link stops the row from toggling on the way past",
   B["plain"]["stopProp"], 4)
eq("B7  a ticked row carries the shared tint", B["ticked"]["tint"], 1)
eq("B7b and one data-sel flag", B["ticked"]["selFlags"], 1)
# /!\ THE COMBINATION. A channel pick must NOT lock the page checkboxes.
eq("B8  /!\\ a CHANNEL pick leaves the page boxes LIVE", B["underChannel"]["locked"], False)
eq("B8b and narrows the rows to that channel",
   B["underChannel"]["rows"], ['/', '/collections/toys'])
eq("B8c with every row still clickable", B["underChannel"]["rowClicks"], 4)
# /!\ A device pick has no crossing to draw.
# Six rows plus the header select-all.
eq("B9  a DEVICE pick disables every box", B["underDevice"]["disabled"], 7)
eq("B9b with not-allowed cursors on all of them", B["underDevice"]["notAllowed"], 7)
# /!\ The guarantee is about the ROW: a locked table must not look clickable.
# The CHECKBOX keeps its handler and is `disabled` - the same shape the v11.57
# tables ship - and seoTrToggleRow refuses it anyway (C7), which is the second
# half a disabled control needs because it is bypassable from the console.
eq("B9c and no row is clickable", B["underDevice"]["rowTrClicks"], 0)
eq("B9c2 nor does any row still say it is", B["underDevice"]["pointer"], 0)
eq("B9c3 while the checkboxes keep their (refused) handlers",
   B["underDevice"]["boxHandlers"], 6)
ok(B["underDevice"]["tipSaysWhy"], "B9d and the tooltip says why")
eq("B10 the empty state spans the new column count", B["empty"], "7")


# ===========================================================================
print("\nC. the REAL state machine: which dimensions cross")
# ===========================================================================
C = run_node(os.path.join(SP, "c.js"), r"""
let CHAN = '', DEV = '';
globalThis.document = { getElementById: (id) =>
  id === 'seo-tr-chan' ? { get value() { return CHAN; } }
  : id === 'seo-tr-dev' ? { get value() { return DEV; } } : null };
function seoTrScopePicked() { return !!(CHAN || DEV); }
const _seoTrRendered = {
  channel: ['Organic Search', 'Direct'],
  device:  ['mobile', 'desktop'],
  page:    ['/', '/collections/toys', '/pages/meowijuana'],
};
let RENDERS = 0;
function renderSeoTraffic() { RENDERS++; }
""" + fn("seoTrSelNew") + "\n" + fn("seoTrRowsLocked") + "\n" + fn("seoTrSelApply") + "\n"
   + fn("seoTrToggleRow") + "\n" + fn("seoTrToggleAll") + "\n" + fn("seoTrClearSel") + r"""
let seoTrSel = seoTrSelNew();
const snap = () => ({ dim: seoTrSel.dim, keys: [...seoTrSel.keys],
                      pages: [...seoTrSel.pages], renders: RENDERS });
const out = {};
out.fresh = snap();

// /!\ THE ASK: channels and pages COMPOSE.
seoTrToggleRow('channel', 0);
seoTrToggleRow('page', 1);
out.composed = snap();

// Device crosses with neither, and the NEWEST click wins.
seoTrToggleRow('device', 0);
out.deviceClearsPages = snap();
seoTrToggleRow('page', 0);
out.pageClearsDevice = snap();

seoTrClearSel();
out.cleared = snap();

// Select-all means the rows ON SCREEN.
seoTrToggleAll('page');   out.allPages = snap();
seoTrToggleAll('page');   out.allPagesOff = snap();

// A channel select-all beside a page selection leaves the pages alone.
seoTrToggleRow('page', 2);
seoTrToggleAll('channel');
out.bothFull = snap();

// Locks refuse from the console too, not just in the markup.
seoTrClearSel();
DEV = 'mobile';
seoTrToggleRow('page', 0);  seoTrToggleAll('page');
out.lockedByDevice = snap();
DEV = ''; CHAN = 'Organic Search';
seoTrToggleRow('page', 0);
out.liveUnderChannel = snap();
seoTrToggleRow('channel', 0);
out.channelRowsStillLocked = snap();
CHAN = '';

// An out-of-range index is a no-op, not a throw.
const before = snap();
seoTrToggleRow('page', 99);
out.outOfRange = { before: before.pages, after: snap().pages };
console.log(JSON.stringify(out));
""")

eq("C1  nothing selected to start",
   C["fresh"], {"dim": "", "keys": [], "pages": [], "renders": 0})
eq("C2  /!\\ a channel and a page selection COMPOSE",
   [C["composed"]["dim"], C["composed"]["keys"], C["composed"]["pages"]],
   ["channel", ["Organic Search"], ["/collections/toys"]])
eq("C3  ticking a DEVICE drops the pages (no crossing)",
   [C["deviceClearsPages"]["dim"], C["deviceClearsPages"]["keys"],
    C["deviceClearsPages"]["pages"]], ["device", ["mobile"], []])
eq("C3b and ticking a PAGE then drops the device - newest wins",
   [C["pageClearsDevice"]["dim"], C["pageClearsDevice"]["keys"],
    C["pageClearsDevice"]["pages"]], ["", [], ["/"]])
eq("C4  clear empties both", [C["cleared"]["keys"], C["cleared"]["pages"]], [[], []])
eq("C5  select-all takes the rows ON SCREEN",
   C["allPages"]["pages"], ['/', '/collections/toys', '/pages/meowijuana'])
eq("C5b and a second press clears them", C["allPagesOff"]["pages"], [])
eq("C6  a channel select-all leaves a page selection standing",
   [C["bothFull"]["keys"], C["bothFull"]["pages"]],
   [["Organic Search", "Direct"], ["/pages/meowijuana"]])
# /!\ BOTH HALVES REFUSE - a disabled box is bypassable from the console.
eq("C7  /!\\ a DEVICE pick refuses page toggles called directly",
   C["lockedByDevice"]["pages"], [])
eq("C8  /!\\ a CHANNEL pick does NOT - that is the combination",
   C["liveUnderChannel"]["pages"], ["/"])
eq("C8b while the channel/device rows stay locked under it",
   C["channelRowsStillLocked"]["keys"], [])
eq("C9  an out-of-range index changes nothing",
   C["outOfRange"]["after"], C["outOfRange"]["before"])


# ===========================================================================
print("\nD. the REAL seoTrRenderChart: what each combination draws")
# ===========================================================================
D = run_node(os.path.join(SP, "d.js"), r"""
const day = (d, p, c, n) => ({ day: d, landing_page: p, channel: c, sessions: n });
const chan = (d, c, n) => ({ day: d, channel: c, sessions: n });
const D1 = '2026-10-01', D2 = '2026-10-02';
const seoTr = {
  days: [{ day: D1, sessions: 1000 }, { day: D2, sessions: 1100 }],
  chan: [chan(D1, 'Organic Search', 600), chan(D1, 'Direct', 400),
         chan(D2, 'Organic Search', 700), chan(D2, 'Direct', 400)],
  dev:  [{ day: D1, device: 'mobile', sessions: 900 }],
  pages: [
    day(D1, '/', 'Organic Search', 300), day(D1, '/', 'Direct', 250),
    day(D2, '/', 'Organic Search', 320), day(D2, '/', 'Direct', 260),
    day(D1, '/collections/toys', 'Organic Search', 150),
    day(D2, '/collections/toys', 'Organic Search', 170),
    day(D1, '/collections/toys', 'Direct', 40),
    day(D1, '', 'Direct', 25), day(D2, '', 'Direct', 30),
  ],
  prev: [{ day: '2025-10-02', sessions: 900 }, { day: '2025-10-03', sessions: 950 }],
  prevChan: [chan('2025-10-02', 'Organic Search', 500)],
  prevDev: [],
};
let MODE = 'line', CHAN = '', DEV = '', TOGGLE = null;
const EL = {};
globalThis.document = { getElementById: (id) =>
  id === 'seo-tr-chan' ? { get value() { return CHAN; } }
  : id === 'seo-tr-dev' ? { get value() { return DEV; } }
  : (EL[id] || (EL[id] = { id, textContent: '', innerHTML: '' })) };
const pnlChartMode = () => MODE;
const pnlChartBands = () => 8;
const pnlInjectChartModeToggle = (_a, _b, dis) => { TOGGLE = { disabled: dis }; };
let CFG = null, seoTrChart = null;
const pnlTrendRender = async (cfg) => { CFG = cfg; return { destroy() {} }; };
const seoTrWindow = () => ({ from: '2026-10-01', to: '2026-10-02', label: 'x' });
""" + fn("seoTrSelNew") + "\n" + fn("seoTrPageKey") + "\n" + fn("seoTrSelNoun") + "\n"
   + fn("seoTrPrevRows") + "\n" + 'let seoTrSnap = null;' + chr(10) + fn('pnlBucketRange') + chr(10) + fn('pnlBucketGrain') + chr(10) + fn('pnlProvisionalBuckets') + chr(10) + re.search(r"(?m)^const GA4_SETTLE_DAYS\s*=.*$", js).group(0) + chr(10) + fn('ga4SettledThrough') + chr(10) + fn('seoTrCoverage') + chr(10) + V1174 + fn("seoTrRenderChart") + r"""
let seoTrSel = seoTrSelNew();
const shot = () => ({
  labels: CFG.datasets.map(d => d.label),
  data: CFG.datasets.map(d => d.data),
  stacks: CFG.datasets.map(d => d.stack || null),
  sub: EL['seo-tr-sub'].textContent,
  mode: CFG.mode,
});
const out = {};
const draw = async (rows, scoped) => { await seoTrRenderChart(rows, scoped); return shot(); };

out.none = await draw(seoTr.days, '');

// Pages alone: every channel.
seoTrSel = seoTrSelNew({ pages: new Set(['/', '/collections/toys']) });
out.pagesAll = await draw(seoTr.days, '');

// /!\ THE ASK: pages WITHIN ticked channel groups.
seoTrSel = seoTrSelNew({ dim: 'channel', keys: new Set(['Organic Search']),
                         pages: new Set(['/', '/collections/toys']) });
out.pagesWithinChannels = await draw(seoTr.days, '');

// Two channels ticked: the scope widens, the series stay the pages.
seoTrSel = seoTrSelNew({ dim: 'channel', keys: new Set(['Organic Search', 'Direct']),
                         pages: new Set(['/collections/toys']) });
out.pagesWithinTwo = await draw(seoTr.days, '');

// A channel DROPDOWN pick scopes them the same way, and stacking survives it.
seoTrSel = seoTrSelNew({ pages: new Set(['/', '/collections/toys']) });
CHAN = 'Organic Search'; MODE = 'stacked';
out.underChanPick = await draw(seoTr.chan.filter(r => r.channel === 'Organic Search'), 'Organic Search');
out.underChanPickToggle = TOGGLE;
CHAN = ''; MODE = 'line';

// A DEVICE pick has no crossing: the page selection is ignored entirely.
DEV = 'mobile';
out.underDevPick = await draw(seoTr.dev, 'mobile');
DEV = '';

// A blank landing page keys as '' and renders as (blank).
seoTrSel = seoTrSelNew({ pages: new Set(['']) });
out.blank = await draw(seoTr.days, '');

// Channels alone are byte-identical to v11.57.
seoTrSel = seoTrSelNew({ dim: 'channel', keys: new Set(['Organic Search']) });
out.channelsOnly = await draw(seoTr.days, '');
console.log(JSON.stringify(out));
""")

eq("D1  with nothing ticked the chart is unchanged",
   D["none"]["labels"], ["Sessions", "Sessions (prior year)"])
eq("D2  a page selection draws one series per page",
   D["pagesAll"]["labels"], ["/", "/collections/toys"])
eq("D2b over every channel", D["pagesAll"]["data"], [[550, 580], [190, 170]])
# /!\ THE MEASUREMENT THAT MATTERS: the same pages, scoped by the ticked
# channel groups. 300/320 is '/' in Organic Search alone, not 550/580.
eq("D3  /!\\ pages are measured WITHIN the ticked channel groups",
   D["pagesWithinChannels"]["labels"], ["/", "/collections/toys"])
eq("D3b and the numbers are that channel's, not every channel's",
   D["pagesWithinChannels"]["data"], [[300, 320], [150, 170]])
ok("within 1 channel group" in D["pagesWithinChannels"]["sub"],
   "D3c and the subtitle says what it was scoped by",
   D["pagesWithinChannels"]["sub"])
eq("D4  two ticked channels widen the scope, not the series",
   [D["pagesWithinTwo"]["labels"], D["pagesWithinTwo"]["data"]],
   [["/collections/toys"], [[190, 170]]])
ok("within 2 channel groups" in D["pagesWithinTwo"]["sub"], "D4b and it says so")
# Asserted as a MAPPING, because this draw is stacked and stacked draws
# smallest-first so the biggest band sits on top (the v11.57 / P&L rule).
eq("D5  a channel DROPDOWN pick scopes them the same way",
   dict(zip(D["underChanPick"]["labels"], D["underChanPick"]["data"])),
   {"/": [300, 320], "/collections/toys": [150, 170]})
eq("D5c and the smallest band is drawn first, as everywhere else",
   D["underChanPick"]["labels"], ["/collections/toys", "/"])
eq("D5b and stacking is available again, because there are series to stack",
   [D["underChanPick"]["mode"], D["underChanPickToggle"]["disabled"]], ["stacked", False])
eq("D6  a DEVICE pick ignores the page selection entirely",
   D["underDevPick"]["labels"], ["Sessions", "mobile (prior year)"][:1])
eq("D7  a blank landing page draws as (blank), keyed by ''",
   [D["blank"]["labels"], D["blank"]["data"]], [["(blank)"], [[25, 30]]])
eq("D8  channels alone are unchanged from v11.57",
   D["channelsOnly"]["labels"], ["Organic Search", "Organic Search (prior year)"])

# /!\ A PAGE SELECTION HAS NO PRIOR YEAR. Drawing the site's would reproduce
# the v11.61 defect exactly: a narrow population compared against everything.
for key, why in [("pagesAll", "pages alone"),
                 ("pagesWithinChannels", "pages within channels"),
                 ("underChanPick", "pages under a channel pick"),
                 ("blank", "a blank page")]:
    ok(all(st != "_prev" for st in D[key]["stacks"]),
       "D9  /!\\ no prior-year line with %s" % why, D[key]["labels"])
ok(any(st == "_prev" for st in D["none"]["stacks"]),
   "D9b and it is still drawn when nothing is ticked")
ok(any(st == "_prev" for st in D["channelsOnly"]["stacks"]),
   "D9c and for a channel selection, as v11.61 made it")


# ===========================================================================
print("\nE. one definition each, and the reasoning survives")
# ===========================================================================
for f in ("seoTrPageKey", "seoTrSelNew", "seoTrRowsLocked", "seoTrSelApply"):
    eq("E1  %s defined once" % f, NC.count("function %s(" % f), 1)
# /!\ The table, the chart and the CSV must key a landing page identically, or
# a ticked row addresses a series filed under another name.
eq("E2  seoTrPageKey has three readers", NC.count("seoTrPageKey"), 4)
eq("E2b and no second spelling of the key survives",
   NC.count("r.landing_page || ''"), 1)
ok("function seoTrPageKey(r) { return r.landing_page || ''; }" in NC,
   "E2c and that one spelling is the definition itself")
eq("E3  one selection state", NC.count("let seoTrSel ="), 1)
eq("E3b one rendered cache", NC.count("const _seoTrRendered ="), 1)
# The lock has one definition per rule, and the channel/device one is REUSED
# rather than respelled.
ok("if (dim !== 'page') return seoTrScopePicked();" in NC,
   "E4  the page lock reuses the existing scope rule rather than respelling it")

for phrase, why in [
    ("LANDING PAGES COMPOSE WITH CHANNEL GROUPS", "why this crosses when nothing else does"),
    ("THE LOCK IS PER DIMENSION", "why a channel pick does not lock the page boxes"),
    ("A PAGE SELECTION HAS NO PRIOR YEAR", "why no dashed line is drawn"),
    ("The LINK wins its own click", "why the anchor stops propagation"),
    ("are DIFFERENT states and are not merged", "why '' is not '(not set)'"),
]:
    ok(phrase in js, "E5  the source still explains %s" % why)

io.open(os.path.join(SP, "check.js"), "w", encoding="utf-8", newline="\n").write(js)
r = subprocess.run(["node", "--check", os.path.join(SP, "check.js")],
                   capture_output=True, text=True, encoding="utf-8")
ok(r.returncode == 0, "E6  node --check is clean", (r.stderr or "")[-300:])


print("\n" + "=" * 68)
print("  %d passed, %d failed" % (passed, failed))
print("=" * 68)
sys.exit(1 if failed else 0)
