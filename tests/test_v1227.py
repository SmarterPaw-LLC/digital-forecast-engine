#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""v12.27 - campaign notes, and the events they put on the timeline.

Jason: "i need a 'notes' section that i can set per campaign level, with an
event that appears on the timeline ... i just changed the kitty ka zoom manual
campaign to dynamic bidding today, and i want to record that change"

/!\ NOT pnl_action_items. That table is PRODUCT-scoped (master_id -> products,
ASIN, region), its action_type enum is about ad spend and PDPs on Amazon, and
it carries a draft -> sent_to_agency -> in_effect workflow. A campaign-level
"switched to dynamic bidding" has no product, no workflow, and its whole point
is the DATE. Reusing it would give one table two meanings (rule 3a).
"""
import io, os, re, sys, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP   = os.path.dirname(os.path.abspath(__file__))
s    = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js   = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)
SQL  = io.open(os.path.join(ROOT, "supabase_v12_27_ads_campaign_notes.sql"),
               encoding="utf-8").read()

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
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("node failed: " + path)
    return json.loads(r.stdout.strip().splitlines()[-1])


print("\n" + "=" * 70)
print("  v12.27  campaign notes on the timeline")
print("=" * 70)

# ===========================================================================
print("\nA. the migration carries RLS, a POLICY and grants")
# ===========================================================================
# /!\ v12.03 shipped a table with the grants and without the policy, and
# Jason's first upload failed. Supabase enables RLS on a new table by itself
# and `authenticated` already holds the default grants, so the POLICY is the
# half that matters.
ok("enable row level security" in SQL, "A1  RLS is enabled")
ok("create policy ads_campaign_notes_all" in SQL, "A2  /!\\ and a POLICY exists")
ok("for all to authenticated using (true) with check (true)" in SQL,
   "A3  ...covering every verb")
ok("grant usage, select on sequence ads_campaign_notes_id_seq" in SQL,
   "A4  /!\\ and the sequence grant a bigserial needs to allocate an id")
ok("pnl_action_items" in SQL,
   "A5  the header records WHY this is not the action-items table")

# ===========================================================================
print("\nB. /!\\ ONE SCOPING RULE, in one place")
# ===========================================================================
SCOPE = fn_flat("adsNotesFor")
ok("!r.campaign || want.has(r.campaign)" in SCOPE,
   "B1  /!\\ an account-level note (no campaign) applies to every view")
D = run_node(os.path.join(SP, "_v1227_b.js"), r"""
'use strict';
const rows = [
  { id: 1, campaign: null,                     note: 'price change' },
  { id: 2, campaign: 'Kitty Ka Zoom - Manual', note: 'dynamic bidding' },
  { id: 3, campaign: 'SP - AUTO - CATCH ALL',  note: 'budget up' },
];
const adsNotesRows = () => rows;
__SCOPE__
console.log(JSON.stringify({
  all:  adsNotesFor('walmart', null).map(r => r.id),
  one:  adsNotesFor('walmart', ['Kitty Ka Zoom - Manual']).map(r => r.id),
  two:  adsNotesFor('walmart', ['Kitty Ka Zoom - Manual', 'SP - AUTO - CATCH ALL']).map(r => r.id),
  none: adsNotesFor('walmart', ['Nothing At All']).map(r => r.id),
}));
""".replace("__SCOPE__", SCOPE))
eq("B2  nothing selected: every note is in view", D["all"], [1, 2, 3])
eq("B3  /!\\ one campaign: its own note AND the account one", D["one"], [1, 2])
eq("B4  two campaigns: both, plus the account one", D["two"], [1, 2, 3])
eq("B5  /!\\ a campaign with no notes still sees the account one", D["none"], [1])

# ===========================================================================
print("\nC. /!\\ A NOTE IS PLACED BY SPAN, NEVER BY KEY")
# ===========================================================================
# The v12.15 Sunday/Monday trap: ads buckets are keyed on the Sunday. A note
# written on a Wednesday has to land in the week that CONTAINS it.
IDX = fn_flat("adsNoteBucketIdx")
ok("pnlBucketRange" in IDX, "C1  it asks the bucket for its own span")
ok("d >= span.from && d <= span.to" in IDX, "C2  ...and tests containment")
E = run_node(os.path.join(SP, "_v1227_c.js"), r"""
'use strict';
// stand-in for the real pnlBucketRange: weekly buckets keyed on the Sunday
function pnlBucketRange(b, grain) {
  if (grain === 'month' || /^\d{4}-\d{2}$/.test(b)) {
    const [y, m] = b.split('-').map(Number);
    const last = new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
    return { from: b + '-01', to: last };
  }
  const d = new Date(b + 'T00:00:00Z');
  const e = new Date(d.getTime() + 6 * 86400000);
  return { from: b, to: e.toISOString().slice(0, 10) };
}
__IDX__
const weeks = ['2026-11-01', '2026-11-08'];
console.log(JSON.stringify({
  // Jason's own case: a change made on a Thursday
  thu:    adsNoteBucketIdx('2026-11-12', weeks, 'week'),
  sunday: adsNoteBucketIdx('2026-11-08', weeks, 'week'),
  prev:   adsNoteBucketIdx('2026-11-07', weeks, 'week'),
  before: adsNoteBucketIdx('2026-10-30', weeks, 'week'),
  month:  adsNoteBucketIdx('2026-11-12', ['2026-10', '2026-11'], 'month'),
  empty:  adsNoteBucketIdx('2026-11-12', [], 'week'),
  nodate: adsNoteBucketIdx('', weeks, 'week'),
}));
""".replace("__IDX__", IDX))
eq("C3  /!\\ a Thursday lands in the week that contains it", E["thu"], 1)
eq("C4  the bucket's own key lands in it", E["sunday"], 1)
eq("C5  /!\\ the day before lands in the PREVIOUS week, not this one", E["prev"], 0)
eq("C6  a date outside every bucket is not placed", E["before"], -1)
eq("C7  a month grain works the same way", E["month"], 1)
eq("C8  no buckets, no placement", E["empty"], -1)
eq("C9  no date, no placement", E["nodate"], -1)

# ===========================================================================
print("\nD. the chart plugin is OPT-IN and draws nothing by itself")
# ===========================================================================
# /!\ A chart whose instance carries no $spEvents must be byte-identical to
# v12.26 - the only way "no existing chart moved" is checkable.
PLUG = js[js.index("const CHART_EVENT_MARKS = {"):]
PLUG = PLUG[:PLUG.index("\n};") + 3]
ok("if (!Array.isArray(evs) || !evs.length) return;" in PLUG,
   "D1  /!\\ no events, no drawing")
ok("chart.$spEvents" in PLUG, "D2  it reads the events off the instance")
ok("getPixelForTick" in PLUG, "D3  ...and places them on the bucket's own tick")
ok("perIdx" in PLUG,
   "D4  /!\\ two events in one bucket stack rather than hiding each other")
ok("chartjs-plugin-annotation" not in js,
   "D5  /!\\ no new CDN dependency - an inline plugin, not a second way to "
   "draw on these charts")
ok("CHART_HTML_LEGEND, CHART_EVENT_MARKS" in js,
   "D6  registered beside the legend, on the one shared renderer")

# ===========================================================================
print("\nE. the panel is built ONCE and only its list repaints")
# ===========================================================================
# /!\ The v10.99 rule: rewriting the form on every render would blow away the
# note field's focus and caret mid-sentence.
ENS = fn_flat("adsNotesEnsure")
ok("if (box) return box;" in ENS, "E1  /!\\ the form is built once")
LIST = fn_flat("adsNotesRenderList")
ok("adsnote-text" not in LIST, "E2  /!\\ and the repaint never touches the text field")
ok("sel.dataset.sig !== want" in LIST,
   "E3  the campaign dropdown is rebuilt only when the campaigns change")
ok("selectedNames.length === 1 && !sel.dataset.touched" in LIST,
   "E4  /!\\ a single selected campaign PREFILLS the form, until it is touched")
ok("cannot be undone" in fn_flat("adsNoteDelete"),
   "E5  /!\\ deleting a note confirms - it is the only record of why a line moved")

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
