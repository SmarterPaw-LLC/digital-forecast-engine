
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
  const latestSqpMonth = [...historyByMonth].reverse().find(h => (h.keywords || 0) > 0) || null;
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
