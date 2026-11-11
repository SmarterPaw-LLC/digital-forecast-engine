#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v11.67 - the Walmart ad tables show the LEVERS, and a campaign opens its keywords.

Jason: "did we finish the work on the walmart ads? i need to be able to make
adjustments weekly."

No. Checked against the live tables first: bid, suggested_bid, status and
ad_group are populated on 189/189 keyword rows in every one of the eight
loaded months, and daily_budget / bidding_strategy on every campaign row - and
not one of them was rendered. The tables reported what an ad DID and showed
nothing you could change about it.

  * A  the wiring, asserted against the registries: every field added is
       MAPPED and RENDERED. A column with no map entry renders blank forever.
  * B  /!\ A BID IS A STATE, NOT A FLOW. The real adsCampaignRollup driven
       over three months: the newest bid wins, spend still SUMS beside it, the
       order rows arrive in does not matter, and a view that declares no
       stateFields is byte-identical.
  * C  the real adsDrillNames / adsDrillOpen / cellOf: who gets a link, who
       does not and why, index addressing, and the pending-filter lifecycle.
  * D  static: one definition each, the format, node --check.
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
    # /!\ LINE comments only - block-stripping this file eats 824,674 chars.
    return re.sub(r"(?m)^\s*//.*$", "", t)


def _balance(i):
    """String-, comment- and regex-aware, because cellOf is mostly template
    literals and a naive brace count walks straight off the end of it."""
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


def fn(name):
    i = js.index("function " + name + "(")
    while i > 0 and js[i - 1] != "\n":
        i -= 1
    return js[i:js.index("function " + name + "(")] + "function " + name \
         + js[js.index("(", js.index("function " + name + "(")):js.index("{", js.index("function " + name + "("))] \
         + _balance(js.index("{", js.index("function " + name + "(")))


def const_obj(name):
    i = js.index("const %s = {" % name)
    return "const %s = %s;" % (name, _balance(js.index("{", i)))


def arrow(decl):
    """Slice an inner `const x = (...) => { ... };` out of a function body.

    `decl` ends ON the opening brace and _balance starts there, so the head is
    taken up to that brace and never including it - otherwise the slice opens
    two scopes and closes one, and node reports the truncation 60 lines later.
    """
    i = js.index(decl)
    b = js.index("{", i + len(decl) - 2)
    return js[i:b] + _balance(b) + ";"


def run_node(path, body):
    io.open(path, "w", encoding="utf-8", newline="\n").write(body)
    r = subprocess.run(["node", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-2500:]); print(r.stderr[-2500:])
        raise SystemExit("node failed: %s" % path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 68)
print("  v11.67  the levers, and the campaign drill-in")
print("=" * 68)

NC = nocomment(js)

# The two Walmart registry blocks, sliced so a claim about one cannot be
# satisfied by the other.
_kwi = js.index("walmart: {\n    keywords: {")
KW = js[_kwi:js.index("\n  },\n};", _kwi)]
_cai = js.index("\n  walmart: {\n    label: 'Walmart Ads'")
CAMP = js[_cai:js.index("\n  },\n};", _cai)]
_coli = js.index("\n  walmart: [", js.index("const ADS_COLUMNS = {"))
CAMPCOLS = js[_coli:js.index("\n  ],", _coli)]


# ===========================================================================
print("\nA. every lever is MAPPED and RENDERED - neither half is enough")
# ===========================================================================
# A column with no map entry renders blank on every row, forever; a mapped
# field with no column is work nobody can see. Both halves, per field.
for f, raw, col in [("bid", "r.bid", "k: 'bid'"),
                    ("suggestedBid", "r.suggested_bid", "k: 'suggestedBid'"),
                    ("status", "r.status", "k: 'status'"),
                    ("adgroup", "r.ad_group", "k: 'adgroup'")]:
    ok(raw in KW, "A1  keyword map reads %s" % raw)
    ok(col in KW, "A1b and the keyword table renders %s" % f)
for f, raw, col in [("dailyBudget", "r.daily_budget", "k: 'dailyBudget'"),
                    ("biddingStrategy", "r.bidding_strategy", "k: 'biddingStrategy'")]:
    ok(raw in CAMP, "A2  campaign map reads %s" % raw)
    ok(col in CAMPCOLS, "A2b and the campaign table renders %s" % f)

# /!\ The gap column is DERIVED, never mapped - a feed that carried its own
# would be a second answer to one question (the v11.59 rule).
ok("k: 'bidVsSugg'" in KW, "A3  the gap column is on the keyword table")
ok("bidVsSugg" not in CAMP and "bidVsSugg" not in CAMPCOLS,
   "A3b and NOT on the campaign table, which has no bid")
eq("A3c it is derived exactly once", NC.count("c.bidVsSugg ="), 1)

# The two state declarations, and nowhere else: a view that sums a setting is
# the defect this release exists to avoid.
# v12.03 - RE-POINTED from 2 to 3. The Advertiser daily view declares an
# EMPTY stateFields, and that is load-bearing rather than tidy: adsViewCfg
# gives it the walmart CHANNEL as its prototype, so omitting the key would
# have inherited dailyBudget + biddingStrategy over a feed that carries
# neither - the rollup would then have read undefined onto every day.
# v12.05 - four. Campaign x Day declares an EMPTY one for the same reason
# the Advertiser daily view does: adsViewCfg gives it the walmart CHANNEL
# as prototype, so omitting the key would inherit dailyBudget +
# biddingStrategy over a feed whose export has neither column.
eq("A4  stateFields declared on every Walmart view",
   NC.count("stateFields: ["), 4)
ok("stateFields: []," in NC, "A4a  /!\\ daily declares an EMPTY one, shadowing the channel")
ok("stateFields: ['bid', 'suggestedBid']" in KW, "A4b keywords: the bid pair")
ok("stateFields: ['dailyBudget', 'biddingStrategy']" in CAMP,
   "A4c campaigns: the budget pair")
# Amazon and Chewy declare none, so their rollups are untouched.
for chan in ["amazon", "chewy"]:
    i = js.index("\n  %s: {" % chan, js.index("const ADS_CHANNELS = {"))
    ok("stateFields" not in js[i:js.index("\n  },\n", i)],
       "A4d %s declares none, so its rollup is unchanged" % chan)


# ===========================================================================
print("\nB. /!\\ a bid is a STATE: the real rollup, three months of it")
# ===========================================================================
B = run_node(os.path.join(SP, "_v1167_b.js"),
    "const ADS_NO_CAMPAIGN = '(no campaign)';\n"
    + fn("adsDiv") + "\n" + fn("adsDeriveRow") + "\n" + fn("adsSumRows") + "\n"
    + fn("adsCampaignRollup") + r"""
// The walmart keywords view's own shape, declared here so the rollup is
// driven generically; A asserts the real registry carries the same fields.
const kw = (m, bid, sugg, spend) => ({
  reporting_month: m, keyword: 'catnip spray', match_type: 'EXACT',
  campaign: 'KKZ Manual', ad_group: 'AG1', status: 'enabled',
  bid, suggested_bid: sugg, spend, clicks: 5, sales: spend * 2,
  orders: 1, impressions: 100, units: 1,
});
const CFG = {
  groupBy: 'term', noneLabel: '(no keyword)',
  stateFields: ['bid', 'suggestedBid'],
  monthOf: (r) => String(r.reporting_month || '').slice(0, 7),
  inWindow: () => true,
  map: (r) => ({
    term: String(r.keyword || '').trim() || null,
    match: r.match_type, campaign: r.campaign, adgroup: r.ad_group,
    status: String(r.status || '').trim(),
    bid: r.bid == null ? null : +r.bid || 0,
    suggestedBid: r.suggested_bid == null ? null : +r.suggested_bid || 0,
    sku: null, brand: null,
    impressions: +r.impressions || 0, clicks: +r.clicks || 0,
    spend: +r.spend || 0, orders: +r.orders || 0, units: +r.units || 0,
    sales: +r.sales || 0, ntb: null, signups: null,
    inStoreSales: null, dpv: null, atc: null,
  }),
};
let CONF = CFG;
function adsViewCfg() { return CONF; }
const out = {};
const run = (rows, cfg) => {
  CONF = cfg || CFG;
  const res = adsCampaignRollup({ channel: 'walmart', view: 'keywords', rows });
  const r = res.campaigns[0];
  return { bid: r.bid === undefined ? '(undefined)' : r.bid,
           sugg: r.suggestedBid === undefined ? '(undefined)' : r.suggestedBid,
           gap: r.bidVsSugg, spend: r.spend, clicks: r.clicks,
           totalBid: res.totals.bid === undefined ? '(undefined)' : res.totals.bid };
};
const THREE = [kw('2026-08', 0.50, 0.70, 10), kw('2026-09', 0.65, 0.72, 20),
               kw('2026-10', 0.80, 0.75, 30)];
out.chrono = run(THREE);
// Out of order, because nothing guarantees the feed arrives sorted.
out.shuffled = run([THREE[2], THREE[0], THREE[1]]);
// One month only.
out.single = run([THREE[0]]);
// A suggested bid the export did not carry.
out.noSugg = run([kw('2026-10', 0.80, null, 30)]);
// /!\ A view that declares NO stateFields must be byte-identical to v11.66.
const NOSTATE = Object.assign({}, CFG); delete NOSTATE.stateFields;
out.noState = run(THREE, NOSTATE);
console.log(JSON.stringify(out));
""")

# /!\ THE MEASUREMENT. 0.50 + 0.65 + 0.80 = 1.95, which is a number nobody
# ever bid; the average 0.65 is one nobody can act on. The newest is 0.80.
eq("B1  /!\\ three months of bids report the NEWEST, not the sum",
   B["chrono"]["bid"], 0.80)
eq("B1b and not the average either", B["chrono"]["sugg"], 0.75)
eq("B2  the gap is derived from that pair", round(B["chrono"]["gap"], 2), 0.05)
# The state rule must not have touched the flows beside it.
eq("B3  /!\\ spend still SUMS over the same rows", B["chrono"]["spend"], 60)
eq("B3b and so do clicks", B["chrono"]["clicks"], 15)
eq("B4  /!\\ the arrival order does not matter",
   [B["shuffled"]["bid"], B["shuffled"]["sugg"], B["shuffled"]["spend"]],
   [0.80, 0.75, 60])
eq("B5  one month reports that month", [B["single"]["bid"], B["single"]["spend"]], [0.50, 10])
# A gap needs both sides. Rendering 0.00 would read as "exactly on Walmart's
# number", which is the one wrong answer here that looks like a real one.
eq("B6  /!\\ no suggested bid means NO gap, never a zero one", B["noSugg"]["gap"], None)
eq("B6b while the bid itself still reports", B["noSugg"]["bid"], 0.80)
# A view with no stateFields never gains the keys, so every pre-v11.67 caller
# is unchanged rather than newly carrying undefined numbers.
eq("B7  /!\\ a view declaring no stateFields is byte-identical",
   [B["noState"]["bid"], B["noState"]["sugg"]], ["(undefined)", "(undefined)"])
eq("B7b and its gap is null, not a number", B["noState"]["gap"], None)
eq("B7c while its flows are unchanged", B["noState"]["spend"], 60)
# The TOTAL row sums flows. A bid there would be a number for a row that is
# not a keyword.
eq("B8  /!\\ the TOTAL row carries no bid at all", B["chrono"]["totalBid"], "(undefined)")


# ===========================================================================
print("\nC. the drill: who gets a link, who does not, and why")
# ===========================================================================
C = run_node(os.path.join(SP, "_v1167_c.js"),
    fn("esc2") + "\n" + const_obj("ADS_DRILL") + "\n"
    + "const _adsDrillNames = {};\n"
    + fn("adsDrillNames") + "\n"
    + "let _adsPendingFilter = null;\nconst _adsDrillLoading = {};\n"
    + "const _adsKey = (channel, view) => channel + '|' + (view || 'campaigns');\n"
    + "const _adsRendered = {};\n"
    + fn("adsSelName") + "\n" + fn("adsDrillOpen") + r"""
// The keyword feed, as the destination view would hold it. 'SP - AUTO - CATCH
// ALL' is the real shape of the case that matters: a campaign with spend at
// campaign level and NO keyword rows at all.
const ROWS = [
  { reporting_month: '2026-10', campaign: 'KKZ Manual',    keyword: 'catnip', advertiser_brand: 'Kitty Ka-Zoom' },
  { reporting_month: '2026-10', campaign: 'KKZ Manual',    keyword: 'nip',    advertiser_brand: 'Kitty Ka-Zoom' },
  { reporting_month: '2026-09', campaign: 'Old Campaign',  keyword: 'gone',   advertiser_brand: 'Kitty Ka-Zoom' },
  { reporting_month: '2026-10', campaign: 'DJ Manual',     keyword: 'dog',    advertiser_brand: 'Doggijuana' },
];
let FEED = ROWS;
const CFG = {
  rows: () => FEED,
  load: () => { LOADED++; return Promise.resolve(); },
  inWindow: (r, from, to) => {
    const m = String(r.reporting_month || '').slice(0, 7);
    if (from && m < String(from).slice(0, 7)) return false;
    if (to && m > String(to).slice(0, 7)) return false;
    return true;
  },
  map: (r) => ({ campaign: r.campaign, brand: r.advertiser_brand || null }),
  groupBy: 'term',
};
let LOADED = 0;
function adsViewCfg(channel, view) {
  if (channel === 'chewy') return null;
  return view === 'keywords' ? CFG : { groupBy: 'campaign' };
}
let WENT = [];
globalThis.window = {
  switchWalmartAdsView: (v) => WENT.push(v),
  switchPnlAdsView: (v) => WENT.push(v),
};
const out = {};
const names = (from, to, brand) => {
  _adsDrillNames.walmart = null;          // defeat the memo between cases
  const set = adsDrillNames('walmart', from, to, brand);
  return set ? [...set].sort() : null;
};
out.wide    = names('2026-01', '2026-12', '');
out.october = names('2026-10', '2026-10', '');
out.branded = names('2026-10', '2026-10', 'Kitty Ka-Zoom');
FEED = [];
out.empty   = names('2026-01', '2026-12', '');
FEED = ROWS;
out.chewy   = (function () { _adsDrillNames.chewy = null;
  const r = adsDrillNames('chewy', '2026-01', '2026-12', ''); return r === null; })();

// --- adsDrillOpen, by INDEX ---------------------------------------------
_adsRendered['walmart|campaigns'] = [
  { campaign: "KKZ Manual" }, { campaign: "O'Brien \"x\" & co" },
];
WENT = []; _adsPendingFilter = null;
adsDrillOpen('walmart', 1);
out.opened = { pend: _adsPendingFilter, went: WENT.slice() };
// An index nobody rendered is a no-op, never a throw.
WENT = []; _adsPendingFilter = null;
adsDrillOpen('walmart', 99);
out.outOfRange = { pend: _adsPendingFilter, went: WENT.slice() };
// A channel with no entry does nothing at all.
WENT = []; _adsPendingFilter = null;
adsDrillOpen('chewy', 0);
out.noEntry = { pend: _adsPendingFilter, went: WENT.slice() };
// /!\ A switcher that is not there must not leave the pick ARMED: it would
// re-apply itself on the next unrelated render of that view.
WENT = []; _adsPendingFilter = null;
const keep = globalThis.window.switchWalmartAdsView;
delete globalThis.window.switchWalmartAdsView;
adsDrillOpen('walmart', 0);
out.noSwitcher = _adsPendingFilter;
globalThis.window.switchWalmartAdsView = keep;
console.log(JSON.stringify(out));
""")

eq("C1  every campaign with keyword rows in the window",
   C["wide"], ["DJ Manual", "KKZ Manual", "Old Campaign"])
# /!\ The window is honoured, so a link is never offered for a campaign the
# destination would then filter away - the control and the table cannot
# disagree about what you just clicked.
eq("C2  /!\\ a narrower window drops the campaign that is not in it",
   C["october"], ["DJ Manual", "KKZ Manual"])
eq("C3  /!\\ and the brand pick scopes it too", C["branded"], ["KKZ Manual"])
eq("C4  an unloaded feed yields null, so nothing is offered yet", C["empty"], None)
eq("C5  a channel with no drill declared yields null", C["chewy"], True)

eq("C6  /!\\ the name is resolved by INDEX, never interpolated",
   C["opened"]["pend"],
   {"channel": "walmart", "view": "keywords", "k": "campaign", "v": "O'Brien \"x\" & co"})
eq("C6b and the switcher is called with the destination view",
   C["opened"]["went"], ["keywords"])
eq("C7  an index nobody rendered is a no-op",
   [C["outOfRange"]["pend"], C["outOfRange"]["went"]], [None, []])
eq("C8  a channel with no entry does nothing",
   [C["noEntry"]["pend"], C["noEntry"]["went"]], [None, []])
eq("C9  /!\\ a missing switcher DISARMS the pick rather than leaving it to "
   "re-apply on the next render", C["noSwitcher"], None)


# ===========================================================================
print("\nC2. the real cell markup, driven")
# ===========================================================================
CELL = arrow("const cellOf = (c, col, i) => {")
D = run_node(os.path.join(SP, "_v1167_d.js"), fn("esc2") + "\n"
    + fn("adsColFmt") + "\n" + fn("adsFmtNum") + "\n" + fn("adsDiv") + "\n" + r"""
const NAMECOL = 'campaign', channel = 'walmart';
const RED = 'red';
const adsRoasFloor = () => 1;
const adsBrandFilterValue = () => '';
const ch = {};
let drill = { view: 'keywords' };
let drillNames = new Set(['KKZ Manual', "O'Brien <b>x</b>"]);
""" + CELL + r"""
const COL = { k: 'campaign', align: 'left', w: 240 };
const out = {};
out.linked   = cellOf({ campaign: 'KKZ Manual' }, COL, 0);
out.nasty    = cellOf({ campaign: "O'Brien <b>x</b>" }, COL, 3);
out.noRows   = cellOf({ campaign: 'SP - AUTO - CATCH ALL' }, COL, 1);
out.footer   = cellOf({ campaign: 'KKZ Manual' }, COL, -1);
drillNames = null;
out.notLoaded = cellOf({ campaign: 'KKZ Manual' }, COL, 0);
drill = null;
out.noDrill  = cellOf({ campaign: 'KKZ Manual' }, COL, 0);
console.log(JSON.stringify(out));
""")

ok("adsDrillOpen('walmart',0)" in D["linked"],
   "C10 a drillable name carries the drill, addressed by index", D["linked"])
ok("event.stopPropagation()" in D["linked"],
   "C10b /!\\ and stops the row toggling - 'that is what the checkbox is for'")
# v11.23: an untrusted string never reaches an attribute.
ok("<b>" not in D["nasty"] and "&lt;b&gt;" in D["nasty"],
   "C11 /!\\ a campaign name carrying markup renders as TEXT", D["nasty"])
ok("adsDrillOpen('walmart',3)" in D["nasty"] and "O'Brien" not in D["nasty"].split("title=")[1].split(">")[0].replace("&#39;", ""),
   "C11b and the handler carries only the index")
# /!\ THE v10.19 HALF. The live data: SP - AUTO - CATCH ALL is Walmart's
# biggest spender and has no keyword rows at all.
ok("adsDrillOpen" not in D["noRows"],
   "C12 /!\\ a campaign with no keyword rows gets NO link", D["noRows"])
ok("nothing below it to open" in D["noRows"],
   "C12b and its tooltip says why rather than leaving it a mystery")
eq("C13 the footer has no index and never drills",
   "adsDrillOpen" in D["footer"], False)
ok("adsDrillOpen" not in D["notLoaded"],
   "C14 nothing is offered while the destination feed is still loading")
ok("adsDrillOpen" not in D["noDrill"] and "nothing below it" not in D["noDrill"],
   "C15 a channel with no drill renders exactly as it did in v11.66")


# ===========================================================================
print("\nD. one definition each, the format, and the reasoning survives")
# ===========================================================================
for f in ("adsDrillNames", "adsDrillOpen"):
    eq("D1  %s defined once" % f, NC.count("function %s(" % f), 1)
eq("D2  one drill registry", NC.count("const ADS_DRILL = {"), 1)
# Chewy has no keyword feed at all, so it must not appear in it.
ok("chewy:" not in js[js.index("const ADS_DRILL = {"):js.index("};", js.index("const ADS_DRILL = {"))],
   "D2b /!\\ and Chewy is absent from it - it has no keyword feed")
# Three CLEARS - the two refusals inside adsDrillOpen and the one in the
# render that consumes it - plus the declaration, which is not a clear.
eq("D3  the pending pick has exactly three clears",
   NC.count("_adsPendingFilter = null") - NC.count("let _adsPendingFilter = null"), 3)
ok("Consumed, whether or not it landed" in js,
   "D3b and why it must be, where it is cleared")
eq("D4  the signed-dollar format is defined once", NC.count("fmt === '$2s'"), 1)
eq("D4b and used only where a dollar GAP is reported", NC.count("fmt: '$2s'"), 1)
ok("A BID IS A STATE, NOT A FLOW" in js,
   "D5  the rule is written where the state is accumulated")
# /!\ Asserted on a fragment that fits ON ONE LINE. The quote wraps in the
# source, and a guard that spans a line break fails on a comment that is
# perfectly correct - the v11.63 trap.
ok("currently it just selects the row" in js,
   "D6  and the ask is recorded beside the thing that answers it")

E = run_node(os.path.join(SP, "_v1167_e.js"), fn("adsFmtNum") + r"""
console.log(JSON.stringify({
  pos: adsFmtNum(0.05, '$2s'), neg: adsFmtNum(-0.12, '$2s'),
  zero: adsFmtNum(0, '$2s'), bid: adsFmtNum(0.65, '$2'),
  xs: adsFmtNum(-0.71, 'xs'), money: adsFmtNum(1234.5, '$'),
}));
""")
eq("D7  a positive gap is signed", E["pos"], "+$0.05")
eq("D7b a negative gap uses the minus sign, not a hyphen", E["neg"], "−$0.12")
eq("D7c zero reads as on the number", E["zero"], "+$0.00")
# Every pre-v11.67 format is untouched.
eq("D8  '$2' is unchanged", E["bid"], "$0.65")
eq("D8b 'xs' is unchanged", E["xs"], "−0.71x")
eq("D8c '$' is unchanged", E["money"], "$1,235")

r = subprocess.run(["node", "--check", os.path.join(SP, "_v1167_b.js")],
                   capture_output=True, text=True)
ok(r.returncode == 0, "D9  the sliced source parses", r.stderr[-300:])

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
