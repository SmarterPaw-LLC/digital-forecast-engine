# -*- coding: utf-8 -*-
r"""v10.98 - the share ramp started at 0% while the keyword table showed share.

Jason: "on the growth model for pawty mix - there is not a scorecard for
existing impression share, the ramp shows 0% starting. this can't be right
as there are keywords with share in the table"

The panel said:

    SHARE RAMP      0.0% -> 25.0%
    YOUR $ TODAY    $10,395/mo   0.0% impression share - 3.8% of market $

"0.0% impression share" and "3.8% of market $" cannot both be true, and the
keyword table directly underneath showed 2.8% / 2.3% / 2.2% CUR SHARE on its
biggest queries. Two numbers on one screen contradicting each other again.

Cause: historyByMonth is built from SQP months, each carrying a real
total_impressions_share. The v8.53b sku_economics enrichment then APPENDS any
month that has sku_economics but no SQP rows, with total_impressions_share: 0,
and re-sorts by month. sku_economics uploads weekly; SQP lands monthly in
arrears - so that zero-share month is routinely the NEWEST one, and
currentShareOverall read historyByMonth[last] blindly.

baselineLatest reading the last month is CORRECT - sku_economics is the better
VOLUME source, which is the whole point of v8.53b. Only SHARE has to come from
the latest month that actually has SQP keywords: the same month the keyword
table is built from, so the two now agree by construction.
"""
import io, os, re, sys, json, subprocess

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
RAW = io.open(SRC, encoding='utf-8', newline='').read()
JS  = max(re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond:
        P += 1; print('  ok  ' + label)
    else:
        F += 1; fails.append(label)
        print('  FAIL ' + label + (('  -> ' + str(got)) if got is not None else ''))


# -- A. The selection reads the latest month WITH keywords ----------------
print('\nA. share no longer reads a keyword-less month')

ok('latestSqpMonth' in JS, 'the latest-SQP-month lookup exists')
sel = re.search(r'const latestSqpMonth = .*?;', JS, re.S)
ok(bool(sel), 'the selection line is parseable')
SEL = sel.group(0) if sel else ''
ok('(h.keywords || 0) > 0' in SEL,
   'it skips months with no SQP keywords')
ok('.reverse()' in SEL and '.find(' in SEL,
   'it walks backwards to the most recent qualifying month')
ok('[...historyByMonth]' in SEL,
   'it copies before reversing - reversing in place would corrupt the history')

# Volume must still read the last month. Fixing share by also changing volume
# would undo v8.53b, which exists precisely because sku_economics is the better
# volume source.
ok(re.search(r'const baselineLatest = historyByMonth\[historyByMonth\.length - 1\]\?\.total_purchases', JS) is not None,
   'VOLUME still reads the last month - v8.53b is untouched')
ok(re.search(r'const currentShareOverall = historyByMonth\[historyByMonth\.length - 1\]', JS) is None,
   'SHARE no longer reads the last month blindly')

# The synthetic sku-econ-only month is still marked, which is what makes the
# fix possible. If that marker ever goes away this silently breaks again.
ok('from_sku_economics_only: true' in JS,
   'sku-econ-only months are still flagged')
ok('total_impressions_share: 0, keywords: 0' in JS,
   '...and still carry keywords: 0, which is what the fix keys off')


# -- B. The number says where it came from --------------------------------
print('\nB. the share states its source month')

ok('currentShareMonth' in JS, 'the source month is computed')
ok('shareStartMonth' in JS, 'and exposed on the result for the UI')
ok('base ' in JS and 'shareStartMonth ?' in JS,
   'the Share Ramp sub-line names the month')
ok('the same month the keyword table below is built from' in JS,
   'the tooltip explains why the two agree')
# The no-SQP-at-all case has to say so rather than quietly showing 0%.
ok('No SQP ASIN-view month has keyword data' in JS,
   'a genuine zero is explained, not left to look like a bug')


# -- C. Driven: Jason's exact shape ---------------------------------------
print('\nC. behaviour, on the reported data shape')

harness = r'''
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// Pawty Mix: SQP ASIN-view ends 2026-08, sku_economics runs to 2026-09, so the
// v8.53b enrichment appends a keyword-less 2026-09 and re-sorts it to the end.
function build() {
  return [
    { month: '2026-06', total_purchases: 900,  total_impressions_share: 1.8, keywords: 100 },
    { month: '2026-07', total_purchases: 1050, total_impressions_share: 2.1, keywords: 100 },
    { month: '2026-08', total_purchases: 1262, total_impressions_share: 2.4, keywords: 100 },
    { month: '2026-09', total_purchases: 973,  total_impressions_share: 0,   keywords: 0,
      from_sku_economics_only: true },
  ];
}

// -- the OLD selection, reproduced verbatim ------------------------------
function OLD(historyByMonth) {
  return historyByMonth[historyByMonth.length - 1]?.total_impressions_share || 0;
}
// -- the NEW selection, lifted from source -------------------------------
function NEW(historyByMonth) {
  __SEL__
  return { share: latestSqpMonth?.total_impressions_share || 0,
           month: latestSqpMonth?.month || null };
}

let h = build();
t('C1  OLD: the ramp really did start from 0%', OLD(h), 0);
t('C2  NEW: it starts from the real share', NEW(h).share, 2.4);
t('C3  NEW: and names the month it came from', NEW(h).month, '2026-08');
t('C4  the history array was not mutated by the reverse',
  h.map(x => x.month), ['2026-06','2026-07','2026-08','2026-09']);

// VOLUME must still come from the last month - sku_economics is the better
// source and v8.53b exists for that reason.
t('C5  volume still reads the sku_economics month',
  h[h.length - 1].total_purchases, 973);

// -- several trailing keyword-less months -------------------------------
h = build();
h.push({ month: '2026-10', total_purchases: 800, total_impressions_share: 0, keywords: 0, from_sku_economics_only: true });
t('C6  it skips BACK over several keyword-less months', NEW(h).month, '2026-08');

// -- no gap at all: the newest month has SQP ----------------------------
h = build().slice(0, 3);
t('C7  with no sku-econ-only month it is just the last month', NEW(h).month, '2026-08');

// -- a genuinely zero share is preserved, not treated as missing --------
h = [{ month: '2026-08', total_purchases: 10, total_impressions_share: 0, keywords: 100 }];
t('C8  a real 0% on a month WITH keywords is kept as 0',
  [NEW(h).share, NEW(h).month], [0, '2026-08']);

// -- no SQP anywhere ----------------------------------------------------
h = [{ month: '2026-09', total_purchases: 973, total_impressions_share: 0, keywords: 0, from_sku_economics_only: true }];
t('C9  no SQP month at all -> 0 and no month, so the UI can say why',
  [NEW(h).share, NEW(h).month], [0, null]);

// -- empty history -------------------------------------------------------
t('C10 an empty history does not throw', [NEW([]).share, NEW([]).month], [0, null]);

// -- the ramp gain the model actually buys -------------------------------
// shareEnd - shareStart is the gain spread across the horizon, so a wrong
// 0% start made the model buy ~2.4pp MORE impressions than it should.
const TARGET = 25;
t('C11 the old 0% start inflated the ramp gain',
  [TARGET - OLD(build()), TARGET - NEW(build()).share], [25, 22.6]);

console.log(JSON.stringify(out));
'''
harness = harness.replace('__SEL__', SEL)
hp = os.path.join(SP, 'test_v1098_share.js')
io.open(hp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', hp], capture_output=True, text=True)
if r.returncode != 0:
    print('  FAIL  share harness did not run:\n' + (r.stderr or '')[:2000]); F += 1; fails.append('harness')
else:
    try: rows = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        print('  FAIL  share harness unparseable: %s\n%s' % (e, r.stdout[:600])); F += 1; fails.append('harness parse'); rows = []
    for row in rows:
        ok(row['pass'], row['name'], None if row['pass'] else ('got ' + row['got'] + ' want ' + row['want']))


# -- D. Known, deliberately NOT changed here ------------------------------
# total_impressions_share is the PLAIN MEAN of each keyword's share. The true
# aggregate impression share is impressions-WEIGHTED - a mean over 100 keywords
# is pulled around by long-tail queries with tiny volume. That is a modelling
# change that would move the number for every product, so it does not ride
# along on a bug fix. Printed on every run so it cannot pass as settled.
print('\nD. known outstanding - how the aggregate share is averaged')
agg = re.search(r'total_impressions_share: rows\.reduce\(.*?\n', JS)
ok(bool(agg) and 'rows.length' in agg.group(0),
   'the aggregate is still the plain per-keyword mean (unchanged here)')
print('     total_impressions_share averages each keyword\'s share equally.')
print('     The true aggregate is impressions-WEIGHTED: sum(your impressions)')
print('     / sum(total impressions). With 100 keywords the plain mean is')
print('     pulled around by long-tail queries carrying almost no volume.')
print('     Left alone deliberately - it moves the number for every product')
print('     and is a modelling decision, not part of this fix.')


print('\n' + '=' * 62)
print('  v10.98  PASS %d   FAIL %d' % (P, F))
if fails:
    print('  failed:')
    for f_ in fails: print('    - ' + f_)
print('=' * 62)
sys.exit(1 if F else 0)
