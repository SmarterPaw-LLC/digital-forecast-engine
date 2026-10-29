const ADS_NO_CAMPAIGN = '(no campaign)';

// Amazon stores the ad product as a slug (v11.14's `_amzAdProduct`). This
// de-slugs it for display rather than carrying a hand-kept label map, so a new
// Amazon format that v11.14 passes through as its own slug shows up as itself
// instead of falling off a lookup.
function adsTypeLabel(slug) {
  const t = String(slug == null ? '' : slug).trim();
  if (!t) return '';
  return t.replace(/_/g, ' ').replace(/\b[a-z]/g, c => c.toUpperCase())
          .replace(/\bDsp\b/, 'DSP').replace(/\bTv\b/, 'TV');
}

// ⚠ Every derived ratio returns NULL on a zero denominator, never Infinity or
// NaN. A campaign with spend and no clicks is the ordinary case (impressions
// only), and `$Infinity/click` on a cost column reads as a crash.
function adsDiv(a, b) {
  // ⚠ A MISSING numerator is not a zero numerator. Number(null) is 0, so
  // without this a metric we have no value for would render 0.00x - identical
  // to a campaign that genuinely returned nothing, which is the one row on
  // this page nobody can afford to confuse with a gap in the data.
  if (a == null || b == null) return null;
  const x = Number(a), y = Number(b);
  if (!isFinite(x) || !isFinite(y) || y === 0) return null;
  const r = x / y;
  return isFinite(r) ? r : null;
}

// Per-channel adapter. `map` normalises one stored row into the shared shape;
// a metric the channel does not report stays null so the registry can leave
// the column out rather than render a fabricated zero.
const ADS_CHANNELS = {
  amazon: {
    label: 'Amazon Ads', icon: '📢', host: 'amzads',
    table: 'amazon_ad_spend',
    freshness: [{ label: 'Amazon Ads', table: 'amazon_ad_spend', icon: '📢' }],
    src: ['amazon_ad_spend'],
    dateField: 'date',
    rows: () => (typeof amazonAdSpendData !== 'undefined' && amazonAdSpendData) || [],
    // The Amazon P&L's own Region / Period / Brand bar scopes this tab, the
    // same controls the Summary tab reads. A second period control one tab
    // away would be a second answer to "what window am I looking at".
    range: () => (typeof getPnlDateRange === 'function') ? getPnlDateRange() : { from: null, to: null },
    brand: () => document.getElementById('pnl-brand')?.value || '',
    // EU is six country codes behind one button, exactly as the Fee Breakdown
    // scan resolves it — reused rather than re-listed.
    regionOk: (r) => {
      const reg = String(r.region || 'US').toUpperCase();
      const sel = (typeof pnlRegion !== 'undefined') ? pnlRegion : 'US';
      if (sel === 'EU') return new Set(['EU/UK','GB','DE','FR','IT','ES','NL']).has(reg);
      return !sel || reg === sel;
    },
    // Which dimensions this channel can filter on, and what each one is
    // CALLED here. Amazon has no campaign status in the unified report, so it
    // offers one filter and Chewy offers two - the strip is built from this
    // rather than from a list that has to remember which channel it is on.
    filters: [{ k: 'type', label: 'Ad type' }],
    map: (r) => ({
      campaign: r.campaign || null,
      type:     adsTypeLabel(r.ad_product),
      status:   null,
      sku:      r.master_id || r.asin || null,
      brand:    r.advertiser_brand || null,
      impressions: +r.impressions || 0,
      clicks:      +r.clicks || 0,
      spend:       +r.spend || 0,
      orders:      +r.purchases || 0,
      units:       null,
      sales:       +r.attributed_sales || 0,
      ntb:         null,
      signups:     null,
    }),
  },
  chewy: {
    label: 'Chewy Ads', icon: '📣', host: 'chads',
    table: 'chewy_ad_spend',
    freshness: [{ label: 'Chewy Ads', table: 'chewy_ad_spend', icon: '📣' }],
    src: ['chewy_ad_spend'],
    dateField: 'date',
    rows: () => (typeof chewyAdSpendData !== 'undefined' && chewyAdSpendData) || [],
    // The v11.02 shared Chewy period control, through its one resolver.
    range: () => (typeof getChewyPnlDateRange === 'function') ? getChewyPnlDateRange('ads') : { from: null, to: null },
    brand: () => document.getElementById('chads-brand')?.value || '',
    regionOk: () => true,
    filters: [{ k: 'type', label: 'Campaign type' }, { k: 'status', label: 'Status' }],
    map: (r) => ({
      campaign: r.campaign || null,
      type:     r.campaign_type || '',
      status:   r.campaign_status || '',
      sku:      r.chewy_sku || null,
      brand:    r.advertiser || null,
      impressions: +r.impressions || 0,
      clicks:      +r.clicks || 0,
      spend:       +r.spend || 0,
      orders:      +r.total_orders || 0,
      units:       +r.direct_units || 0,
      sales:       +r.direct_sales || 0,
      ntb:         +r.ntb_customers || 0,
      signups:     +r.autoship_signups || 0,
    }),
  },
};

// ⚠ Column registries, per channel, because the two channels report different
// things AND name them differently in their own consoles — which is what Jason
// reconciles against. The Chewy set reuses CHEWY_MEASURE_VOCAB's declared
// words verbatim (Spend / Direct $ / Direct ROAS / Impressions / Clicks / NTB
// / Total orders / Ad Units), so rule 3a's sweep covers this tab too.
//
// ⚠ `Direct ACOS %` is NOT `Actual ACOS %`. The declared `Actual ACOS %` is
// spend over REALISED sales (direct plus recurring autoship) on the Break-Even
// tab. This one is spend over DIRECT sales. Same arithmetic, narrower
// population, so it gets its own scoped name rather than quietly meaning two
// things one tab apart.
// ── v11.22 ADS VIEWS ──────────────────────────────────────────────────────
//
// Jason: "give me another sub-page tab for keywords. do you have this data? I
// need a way to see level of detail in the ads viewer for amazon, chewy,
// walmart."
//
// The honest answer, checked rather than assumed:
//   Amazon  amazon_sp_search_term - customer search term, targeting, match
//           type, impressions, clicks, CPC, spend, 7-day sales/orders/units,
//           ACOS, ROAS, CVR. MONTHLY grain, SPONSORED PRODUCTS ONLY.
//   Chewy   nothing. chewy_ad_spend goes campaign -> promoted SKU -> day and
//           the vendor export carries no keyword dimension at all. Chewy's
//           level of detail below campaign is the SKU.
//   Walmart no ads feed yet.
//
// ⚠ SO THE TAB EXISTS ONLY WHERE THE DATA DOES. A Keywords tab on Chewy that
// always said "no data" would be a live-looking control that can never do
// anything - the v10.19 rule. ADS_VIEWS is keyed by channel, and a channel
// with no entry simply has no extra tab.
const ADS_VIEWS = {
  amazon: {
    keywords: {
      host: 'amzkw',
      label: 'Search terms',
      freshness: [{ label: 'SP Search Term', table: 'amazon_sp_search_term', icon: '🔑' }],
      src: ['amazon_sp_search_term'],
      rows: () => (typeof amazonSpSearchTermCache !== 'undefined' && amazonSpSearchTermCache) || [],
      load: () => (typeof loadAmazonSpSearchTerm === 'function') ? loadAmazonSpSearchTerm() : null,
      groupBy: 'term',
      // ⚠ Its own NOUN. These rows are search terms, not campaigns - and this
      // tab shows a campaign LIST column at the same time, so borrowing the word
      // would put two meanings of 'campaign' side by side (rule 3a).
      noun: 'search term',
      noneLabel: '(no search term)',
      filters: [{ k: 'match', label: 'Match type' }, { k: 'campaign', label: 'Campaign' }],

      // ⚠ THE GRAIN IS MONTHLY AND THE PERIOD CONTROL IS DAILY.
      //
      // The report has no per-day rows: `reporting_month` is 'YYYY-MM' and
      // `reporting_date` is the period END. Filtering that end-date against a
      // daily window would include or drop a WHOLE month depending on where
      // its last day happened to fall - a 30-day window could silently cover
      // two months or none, and nothing on screen would say which.
      //
      // So a month is IN when it OVERLAPS the window at all, and the coverage
      // line states the months it actually resolved to. The window is honest
      // about being approximate rather than pretending to a precision the
      // feed does not have. The Campaigns tab is genuinely daily; these two
      // tabs therefore resolve the same period differently, which is exactly
      // why each says what it resolved to (the v11.02 rule).
      inWindow: (raw, from, to) => {
        const m = String(raw.reporting_month || '').slice(0, 7);
        if (!m) return false;
        if (from && m < String(from).slice(0, 7)) return false;
        if (to && m > String(to).slice(0, 7)) return false;
        return true;
      },
      monthOf: (raw) => String(raw.reporting_month || '').slice(0, 7),

      map: (r) => ({
        term:     String(r.customer_search_term || '').trim() || null,
        match:    String(r.match_type || '').trim().toUpperCase(),
        campaign: String(r.campaign_name || '').trim(),
        adgroup:  String(r.ad_group_name || '').trim(),
        sku:      r.master_id || r.asin || null,
        brand:    null,
        impressions: +r.impressions || 0,
        clicks:      +r.clicks || 0,
        spend:       +r.spend || 0,
        orders:      +r.orders_7d || 0,
        units:       +r.units_7d || 0,
        sales:       +r.sales_7d || 0,
        ntb:         null,
        signups:     null,
      }),

      columns: [
        { k: 'term',        label: 'Search term',  align: 'left',  w: 280, tip: 'The customer query that triggered the ad. Sponsored Products only - Amazon does not report search terms for Brands, Display, TV or DSP.' },
        { k: 'match',       label: 'Match',        align: 'left',  w: 84,  tip: 'How the targeting matched: BROAD / PHRASE / EXACT, or AUTO for automatic targeting.' },
        { k: 'campaign',    label: 'Campaign',     align: 'left',  w: 200, tip: 'The campaign the term spent under. Several when one term is targeted from more than one.' },
        { k: 'skus',        label: 'ASINs',        align: 'right', w: 68,  tip: 'Distinct advertised products the term drove in the window.' },
        { k: 'impressions', label: 'Impressions',  align: 'right', w: 104, tip: 'Impressions over the window.' },
        { k: 'clicks',      label: 'Clicks',       align: 'right', w: 80,  tip: 'Clicks over the window.' },
        { k: 'ctr',         label: 'CTR %',        align: 'right', w: 72,  tip: 'Clicks / Impressions.' },
        { k: 'cpc',         label: 'CPC',          align: 'right', w: 72,  tip: 'Spend / Clicks.' },
        { k: 'spend',       label: 'Spend',        align: 'right', w: 96,  tip: 'Ad spend over the window.' },
        { k: 'orders',      label: 'Orders',       align: 'right', w: 76,  tip: '7-day attributed orders.' },
        { k: 'units',       label: 'Units',        align: 'right', w: 72,  tip: '7-day attributed units.' },
        { k: 'cvr',         label: 'CVR %',        align: 'right', w: 76,  tip: 'Orders / Clicks.\n\nDerived from the window totals, never averaged across the per-row CVR the report carries - an average would weight a 2-click term the same as a 2,000-click one.' },
        { k: 'cpa',         label: 'CPA',          align: 'right', w: 76,  tip: 'Spend / Orders - what an attributed order cost.' },
        { k: 'sales',       label: 'Ad Sales',     align: 'right', w: 104, tip: '7-day attributed sales (Amazon RETAIL dollars, not our revenue).' },
        { k: 'roas',        label: 'ROAS',         align: 'right', w: 76,  tip: 'Ad Sales / Spend.' },
        { k: 'acos',        label: 'ACOS %',       align: 'right', w: 80,  tip: 'Spend / Ad Sales.' },
      ],
    },
  },
};

// The config a (channel, view) pair runs on. An absent view falls back to the
// CHANNEL adapter, so every existing campaigns call is unchanged.
function adsViewCfg(channel, view) {
  const ch = ADS_CHANNELS[channel];
  if (!ch) return null;
  const v = (ADS_VIEWS[channel] || {})[view];
  if (!v) return ch;
  // Channel-level bits (the period control, the brand filter) always come
  // from the channel; the view only overrides what it actually changes.
  return Object.assign(Object.create(ch), v);
}

const ADS_COLUMNS = {
  amazon: [
    { k: 'campaign',    label: 'Campaign',    align: 'left',  w: 260, tip: 'Amazon Ads campaign name, from the unified report\'s Campaign name dimension.\n\n"(no campaign)" is spend uploaded before v11.15 added the column — Amazon cannot retrofit the dimension onto a past pull, so re-upload the window to fill it in.' },
    { k: 'type',        label: 'Type',        align: 'left',  w: 150, tip: 'Ad product: Sponsored Products / Brands / Display / TV / DSP. Several when one campaign name carries more than one.' },
    { k: 'skus',        label: 'SKUs',        align: 'right', w: 62,  tip: 'Distinct advertised products in the campaign over the window.' },
    { k: 'impressions', label: 'Impressions', align: 'right', w: 104, tip: 'Impressions over the window.' },
    { k: 'clicks',      label: 'Clicks',      align: 'right', w: 80,  tip: 'Clicks over the window.' },
    { k: 'ctr',         label: 'CTR %',       align: 'right', w: 72,  tip: 'Clicks / Impressions.' },
    { k: 'cpc',         label: 'CPC',         align: 'right', w: 72,  tip: 'Spend / Clicks.' },
    { k: 'spend',       label: 'Spend',       align: 'right', w: 96,  tip: 'Ad spend over the window.' },
    { k: 'orders',      label: 'Orders',      align: 'right', w: 76,  tip: 'Ad-attributed purchases.' },
    { k: 'cpa',         label: 'CPA',         align: 'right', w: 76,  tip: 'Spend / Orders — what an attributed order cost.' },
    { k: 'sales',       label: 'Ad Sales',    align: 'right', w: 104, tip: 'Ad-attributed sales (Amazon RETAIL dollars, not our revenue).' },
    { k: 'roas',        label: 'ROAS',        align: 'right', w: 76,  tip: 'Ad Sales / Spend.' },
    { k: 'acos',        label: 'ACOS %',      align: 'right', w: 80,  tip: 'Spend / Ad Sales.' },
  ],
  chewy: [
    { k: 'campaign',    label: 'Campaign',    align: 'left',  w: 260, tip: 'Chewy Ads campaign name.' },
    { k: 'type',        label: 'Campaign Type', align: 'left', w: 140, tip: 'Chewy Max / Sponsored Brand / Sponsored Product.' },
    { k: 'status',      label: 'Status',      align: 'left',  w: 92,  tip: 'Campaign status as Chewy last reported it.' },
    { k: 'skus',        label: 'SKUs',        align: 'right', w: 62,  tip: 'Distinct promoted products in the campaign over the window.' },
    { k: 'impressions', label: 'Impressions', align: 'right', w: 104, tip: 'Chewy Ads impressions over the window.' },
    { k: 'clicks',      label: 'Clicks',      align: 'right', w: 80,  tip: 'Chewy Ads clicks over the window.' },
    { k: 'ctr',         label: 'CTR %',       align: 'right', w: 72,  tip: 'Clicks / Impressions.' },
    { k: 'cpc',         label: 'CPC',         align: 'right', w: 72,  tip: 'Spend / Clicks.' },
    { k: 'spend',       label: 'Spend',       align: 'right', w: 96,  tip: 'Chewy Ads spend over the window.' },
    { k: 'units',       label: 'Ad Units',    align: 'right', w: 82,  tip: 'Units attributed to an ad click (Chewy direct units).' },
    { k: 'orders',      label: 'Total orders', align: 'right', w: 92, tip: 'All ad-attributed orders over the window.' },
    { k: 'cpa',         label: 'CPA',         align: 'right', w: 76,  tip: 'Spend / Total orders — what an attributed order cost.' },
    { k: 'sales',       label: 'Direct $',    align: 'right', w: 104, tip: 'Chewy RETAIL sales attributed to the click.' },
    { k: 'roas',        label: 'Direct ROAS', align: 'right', w: 92,  tip: 'Direct $ / Spend.\n\nRETAIL basis. The Break-Even tab measures realised ROAS, which adds recurring autoship — this is the direct read only.' },
    { k: 'acos',        label: 'Direct ACOS %', align: 'right', w: 104, tip: 'Spend / Direct $.\n\nNOT the Break-Even tab\'s Actual ACOS %, which divides by REALISED sales (direct plus recurring autoship). Narrower population, so a different name.' },
    { k: 'ntb',         label: 'NTB',         align: 'right', w: 72,  tip: 'New-to-brand customers Chewy attributed to the ads.' },
  ],
};

// ⚠ ONE derivation of the ratio columns. The rollup's TOTAL, the footer's
// on-screen re-sum and v11.23's selection scorecards all sum rows and then
// derive - three hand-written copies would be three chances to average a
// ratio by accident, which weights a $2 campaign the same as a $20,000 one.
function adsDeriveRow(c, group) {
  c.type   = [...c.types].sort().join(' · ');
  c.status = [...c.statuses].sort().join(' · ');
  if (group && group !== 'campaign') {
    c.match    = [...c.matches].sort().join(' · ');
    c.campaign = [...c.campaigns].sort().join(' · ');
    c.adgroup  = [...c.adgroups].sort().join(' · ');
  }
  c.skus   = c.skuSet.size;
  // Conversion rate, derived from the window TOTALS. The report carries a
  // per-row cvr_pct; averaging those would weight a 2-click term the same
  // as a 2,000-click one.
  c.cvr    = adsDiv(c.orders, c.clicks);
  if (c.cvr != null) c.cvr *= 100;
  c.ctr    = adsDiv(c.clicks, c.impressions);
  c.cpc    = adsDiv(c.spend, c.clicks);
  c.cpa    = adsDiv(c.spend, c.orders);
  c.roas   = adsDiv(c.sales, c.spend);
  c.acos   = adsDiv(c.spend, c.sales);
  if (c.ctr  != null) c.ctr  *= 100;
  if (c.acos != null) c.acos *= 100;
  if (!c.hasUnits) c.units = null;
  if (!c.hasNtb)   c.ntb   = null;
  return c;
}

// Sum ALREADY-ROLLED-UP rows and derive the ratios once from the sums.
// ⚠ It unions `types` and `skuSet` only, exactly as the v11.16 total loop
// did. Unioning statuses or the campaign list as well would put a joined
// string into the TOTAL row's Status cell in the CSV, which is a change of
// output dressed up as a refactor.
function adsSumRows(rows, group, label) {
  const t = { campaign: label || 'TOTAL', types: new Set(), statuses: new Set(), skuSet: new Set(),
              matches: new Set(), campaigns: new Set(), adgroups: new Set(),
              impressions: 0, clicks: 0, spend: 0, orders: 0, units: 0, sales: 0,
              ntb: 0, signups: 0, hasUnits: false, hasNtb: false, firstDate: '', lastDate: '' };
  for (const c of (rows || [])) {
    t.impressions += c.impressions; t.clicks += c.clicks; t.spend += c.spend;
    t.orders += c.orders; t.sales += c.sales; t.signups += (c.signups || 0);
    if (c.units != null) { t.units += c.units; t.hasUnits = true; }
    if (c.ntb   != null) { t.ntb   += c.ntb;   t.hasNtb   = true; }
    c.skuSet.forEach(x => t.skuSet.add(x));
    c.types.forEach(x => t.types.add(x));
    if (!t.firstDate || (c.firstDate && c.firstDate < t.firstDate)) t.firstDate = c.firstDate;
    if (c.lastDate > t.lastDate) t.lastDate = c.lastDate;
  }
  return adsDeriveRow(t, group);
}

// Local-calendar YYYY-MM-DD. ⚠ NOT toISOString().slice(0,10): these dates are
// parsed as LOCAL midnight, and toISOString shifts them by the UTC offset,
// which rolls the date back a day for anyone east of Greenwich.
function adsYmd(d) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
       + '-' + String(d.getDate()).padStart(2, '0');
}

// Which bucket a raw row falls in, for the trend chart.
function adsBucketFn(ch, grain) {
  // ⚠ A MONTHLY FEED HAS EXACTLY ONE HONEST GRAIN. The search-term report
  // stores YYYY-MM plus a period-END date; bucketing it by day would draw one
  // spike per month on whichever day the report happened to close.
  if (typeof ch.monthOf === 'function') return (raw) => ch.monthOf(raw) || null;
  return (raw, d) => {
    const str = String(d || '').slice(0, 10);
    if (str.length < 10) return null;
    if (grain === 'month') return str.slice(0, 7);
    if (grain === 'week') {
      // Sun—Sat, which is what computePnlDateRange already uses because it is
      // Amazon's own week definition. A second week rule here would put this
      // chart a day out of step with every other weekly figure in the app.
      const dt = new Date(str + 'T00:00:00');
      if (isNaN(dt.getTime())) return null;
      dt.setDate(dt.getDate() - dt.getDay());
      return adsYmd(dt);
    }
    return str;
  };
}

// ⚠ The grain is chosen from the WINDOW, and the chart says which it got.
// Ad spend is daily, so a 365-day window drawn per day is 365 points of noise
// and a 14-day window drawn per month is one. Auto-picking is only honest
// because the subtitle states what it resolved to (the v10.99 rule).
function adsGrain(win, ch) {
  if (ch && typeof ch.monthOf === 'function') return 'month';
  if (!win || !win.from || !win.to) return 'week';
  const days = Math.round((new Date(win.to + 'T00:00:00') - new Date(win.from + 'T00:00:00')) / 86400000) + 1;
  if (!isFinite(days) || days <= 0) return 'week';
  if (days <= 70) return 'day';
  if (days <= 400) return 'week';
  return 'month';
}

// ⚠ THE CHART'S METRIC LIST IS BUILT FROM THE TABLE'S COLUMN REGISTRY, so
// the two can never name the same number differently (rule 3a) and a column
// added later is plottable with no second list to keep in step. Every entry
// derives from a SUMMED slot, never from an average of the per-row figures.
const ADS_METRIC_SPEC = {
  spend:       { unit: '$', sum: s => s.spend },
  sales:       { unit: '$', sum: s => s.sales },
  impressions: { unit: '#', sum: s => s.impressions },
  clicks:      { unit: '#', sum: s => s.clicks },
  orders:      { unit: '#', sum: s => s.orders },
  units:       { unit: '#', sum: s => s.units },
  ntb:         { unit: '#', sum: s => s.ntb },
  ctr:  { unit: '%', isPct: true, noStack: true, sum: s => { const v = adsDiv(s.clicks, s.impressions); return v == null ? null : v * 100; } },
  cvr:  { unit: '%', isPct: true, noStack: true, sum: s => { const v = adsDiv(s.orders, s.clicks);     return v == null ? null : v * 100; } },
  acos: { unit: '%', isPct: true, noStack: true, sum: s => { const v = adsDiv(s.spend, s.sales);       return v == null ? null : v * 100; } },
  cpc:  { unit: '$', noStack: true, sum: s => adsDiv(s.spend, s.clicks) },
  cpa:  { unit: '$', noStack: true, sum: s => adsDiv(s.spend, s.orders) },
  roas: { unit: 'x', noStack: true, sum: s => adsDiv(s.sales, s.spend) },
};
function adsChartMetrics(COLS) {
  return (COLS || []).filter(c => ADS_METRIC_SPEC[c.k])
    .map(c => Object.assign({ k: c.k, label: c.label }, ADS_METRIC_SPEC[c.k]));
}

// ⚠ The rollup is a PURE function of (rows, window, filters) so it can be
// driven in a test without a DOM. Everything that reads the page goes through
// the adapter's range() / brand() / regionOk(), which the renderer resolves
// and passes in.
function adsCampaignRollup(opts) {
  const o = opts || {};
  // v11.22 — the config for this (channel, view). No view = the channel
  // adapter, so every campaigns call is byte-identical to v11.21.
  const ch = adsViewCfg(o.channel, o.view);
  if (!ch) return null;
  const GROUP = ch.groupBy || 'campaign';
  const NONE = ch.noneLabel || ADS_NO_CAMPAIGN;
  const from = o.from || null, to = o.to || null;
  const brand = o.brand || '';
  const rows = o.rows || ch.rows();
  // v11.20 — the active filters, as {dimension: Set(values)}. An absent or
  // empty Set means 'all', so an unfiltered call behaves exactly as before.
  const picked = o.filters || {};
  // Every value SEEN in the window, so the control can offer exactly what is
  // there. Collected before the filter is applied for the dimension it
  // belongs to - otherwise picking a value would erase every other option
  // and the control could never be widened again.
  const seen = {};
  const monthsSeen = new Set();
  // v11.23 - the per-bucket series for the trend chart, accumulated in THIS
  // scan so it cannot disagree with the rows the table shows. Absent
  // `bucket` nothing is built and the returned object gains no key.
  const bucketOf = o.bucket ? adsBucketFn(ch, o.bucket) : null;
  const series = bucketOf ? {} : null;
  const bucketsSeen = bucketOf ? new Set() : null;
  const agg = new Map();
  let scanned = 0, inWindow = 0, filteredOut = 0;
  for (const raw of rows) {
    scanned++;
    // ⚠ A view whose feed is not daily supplies its own window rule. The
    // search-term report is MONTHLY, so comparing its period-end date against
    // a daily window would include or drop a whole month on where its last
    // day fell. See the comment on ADS_VIEWS.amazon.keywords.inWindow.
    const d = typeof ch.monthOf === 'function' ? ch.monthOf(raw)
                                              : String(raw[ch.dateField] || '');
    if (typeof ch.inWindow === 'function') {
      if (!ch.inWindow(raw, from, to)) continue;
    } else {
      if (from && d < from) continue;
      if (to && d > to) continue;
    }
    if (o.regionOk !== false && typeof ch.regionOk === 'function' && !ch.regionOk(raw)) continue;
    const r = ch.map(raw);
    if (brand && String(r.brand || '') !== brand) continue;
    inWindow++;
    // Record what this row offers on every filterable dimension, then narrow.
    // ⚠ ROW LEVEL, not campaign level. A campaign can carry more than one
    // ad product under one name, so filtering to Sponsored Products must drop
    // that campaign's Brands spend and re-derive its totals - not drop the
    // whole campaign, and not keep blended figures under a filtered label.
    let drop = false;
    for (const f of (ch.filters || [])) {
      const v = String(r[f.k] == null ? '' : r[f.k]).trim();
      if (v) (seen[f.k] || (seen[f.k] = new Set())).add(v);
      const want = picked[f.k];
      if (want && want.size && !want.has(v)) drop = true;
    }
    if (drop) { filteredOut++; continue; }
    if (typeof ch.monthOf === 'function' && d) monthsSeen.add(d);
    const name = r[GROUP] || NONE;
    let c = agg.get(name);
    if (!c) {
      c = { campaign: name, [GROUP]: name, noCampaign: !r[GROUP], types: new Set(), statuses: new Set(),
            matches: new Set(), campaigns: new Set(), adgroups: new Set(),
            skuSet: new Set(), impressions: 0, clicks: 0, spend: 0, orders: 0,
            units: 0, sales: 0, ntb: 0, signups: 0,
            hasUnits: false, hasNtb: false, firstDate: d, lastDate: d };
      agg.set(name, c);
    }
    if (r.type)   c.types.add(r.type);
    if (r.status) c.statuses.add(r.status);
    // A search term can be targeted from several campaigns / ad groups / match
    // types in one window. Collected as sets and joined, the same way the
    // Campaigns view collects ad products - never silently keeping the first.
    if (r.match && GROUP !== 'campaign')    c.matches.add(r.match);
    if (r.campaign && GROUP !== 'campaign') c.campaigns.add(r.campaign);
    if (r.adgroup) c.adgroups.add(r.adgroup);
    if (r.sku)    c.skuSet.add(r.sku);
    c.impressions += r.impressions;
    c.clicks      += r.clicks;
    c.spend       += r.spend;
    c.orders      += r.orders;
    c.sales       += r.sales;
    if (r.units   != null) { c.units   += r.units;   c.hasUnits = true; }
    if (r.ntb     != null) { c.ntb     += r.ntb;     c.hasNtb   = true; }
    if (r.signups != null) { c.signups += r.signups; }
    if (d && d < c.firstDate) c.firstDate = d;
    if (d && d > c.lastDate)  c.lastDate  = d;
    if (bucketOf) {
      const bk = bucketOf(raw, d);
      if (bk) {
        bucketsSeen.add(bk);
        const byB = series[name] || (series[name] = {});
        const sl = byB[bk] || (byB[bk] = { impressions: 0, clicks: 0, spend: 0,
                                           orders: 0, units: 0, sales: 0, ntb: 0, signups: 0 });
        sl.impressions += r.impressions; sl.clicks += r.clicks; sl.spend += r.spend;
        sl.orders += r.orders; sl.sales += r.sales;
        sl.units += (r.units || 0); sl.ntb += (r.ntb || 0); sl.signups += (r.signups || 0);
      }
    }
  }

  const derive = (c) => adsDeriveRow(c, GROUP);
  const campaigns = [...agg.values()].map(derive);
  // Totals are summed from the ROWS, then the ratios derived once — never
  // averaged across campaigns, which would weight a $2 campaign the same as a
  // $20,000 one (the v11.08 lesson, in a different table).
  const t = adsSumRows(campaigns, GROUP);

  // Coverage: how much of this window predates campaign tracking. Reported as
  // SPEND, not as a row count — a row count would make a long tail of tiny
  // legacy rows look like a bigger hole than it is, and vice versa.
  const noCamp = campaigns.find(c => c.noCampaign);
  return {
    campaigns, totals: t,
    // Only present when a bucket grain was asked for, so an unbucketed call
    // returns exactly the object every pre-v11.23 caller already reads.
    ...(bucketOf ? { series, buckets: [...bucketsSeen].sort() } : {}),
    // Sorted so the control's order does not jump around between renders.
    options: Object.fromEntries(Object.entries(seen)
      .map(([k, v]) => [k, [...v].sort()])),
    coverage: {
      scanned, inWindow, filteredOut, from, to, brand,
      months: [...monthsSeen].sort(),
      filters: Object.fromEntries(Object.entries(picked)
        .filter(([, v]) => v && v.size).map(([k, v]) => [k, [...v].sort()])),
      campaignCount: campaigns.filter(c => !c.noCampaign).length,
      noCampaignSpend: noCamp ? noCamp.spend : 0,
      noCampaignPct: t.spend > 0 && noCamp ? (100 * noCamp.spend / t.spend) : 0,
    },
  };
}

// Sort + search state, per channel so switching P&L pages does not reset the
// other one. Default: biggest spender first, which is the order anyone opening
// an ads page is looking for.
// Keyed by (channel, view) so the Campaigns and Keywords tables keep their
// own sort and their own export snapshot instead of overwriting each other.
const _adsKey = (channel, view) => channel + '|' + (view || 'campaigns');
const _adsState = {};
function adsState(channel, view) {
  const k = _adsKey(channel, view);
  // v11.23 - `sel` holds the CHECKED row names for this (channel, view).
  // Keyed the same way as the sort, so the Campaigns and Keywords tables
  // keep their own selection instead of sharing one.
  return _adsState[k] || (_adsState[k] = { sortK: 'spend', sortDir: -1, sel: new Set() });
}
let _adsExport = {};

function adsSortBy(channel, k, view) {
  const st = adsState(channel, view); if (!st) return;
  if (st.sortK === k) st.sortDir = -st.sortDir;
  else { st.sortK = k; st.sortDir = (k === 'campaign' || k === 'type' || k === 'status') ? 1 : -1; }
  renderAdsCampaigns(channel, view);
}
function adsSearchChanged(channel, view) { renderAdsCampaigns(channel, view); }

// ⚠ The rows AS RENDERED, so a checkbox can address its row by INDEX.
// A campaign name can contain quotes, commas and backslashes; interpolating
// one into an onclick attribute is an injection waiting to happen and breaks
// on the first apostrophe. The index is resolved back to the name here.
const _adsRendered = {};
function adsSelName(channel, view, i) {
  const row = (_adsRendered[_adsKey(channel, view)] || [])[i];
  if (!row) return null;
  const ch = adsViewCfg(channel, view);
  return ch ? row[ch.groupBy || 'campaign'] : null;
}
function adsToggleRow(channel, i, view) {
  const name = adsSelName(channel, view, i);
  if (name == null) return;
  const sel = adsState(channel, view).sel;
  if (sel.has(name)) sel.delete(name); else sel.add(name);
  renderAdsCampaigns(channel, view);
}
// Header checkbox: select every VISIBLE row, or clear them if all are on.
// Rows the search has hidden keep their state - the selection persists
// across filters, exactly as the Summary table's does.
function adsToggleAllVisible(channel, view) {
  const ch = adsViewCfg(channel, view); if (!ch) return;
  const key = ch.groupBy || 'campaign';
  const names = (_adsRendered[_adsKey(channel, view)] || []).map(c => c[key]);
  const sel = adsState(channel, view).sel;
  const allOn = names.length > 0 && names.every(n => sel.has(n));
  if (allOn) names.forEach(n => sel.delete(n));
  else       names.forEach(n => sel.add(n));
  renderAdsCampaigns(channel, view);
}
function adsClearSelection(channel, view) {
  adsState(channel, view).sel.clear();
  renderAdsCampaigns(channel, view);
}

// ⚠ A bucket at the edge of the window is usually PART of a bucket, and a
// half week drawn beside full ones is a cliff that reads as spend collapsing.
// Named rather than dropped or rounded away - the v11.02 part-month rule.
//
// Skipped for a monthly VIEW, where the rollup takes a month that merely
// OVERLAPS the window: those edge buckets carry MORE than the window, not
// less, so calling them partial would be the opposite of true.
function adsBucketEdges(buckets, grain, win) {
  if (grain === 'day' || !buckets || !buckets.length || !win || !win.from || !win.to) return [];
  const DAY = 86400000;
  const span = (b) => {
    if (grain === 'month') {
      const [y, m] = String(b).split('-').map(Number);
      return [new Date(y, m - 1, 1), new Date(y, m, 0)];
    }
    const a = new Date(b + 'T00:00:00');
    const z = new Date(a); z.setDate(a.getDate() + 6);
    return [a, z];
  };
  const from = new Date(win.from + 'T00:00:00'), to = new Date(win.to + 'T00:00:00');
  const out = [];
  const edges = buckets.length === 1 ? [['only', buckets[0]]]
    : [['first', buckets[0]], ['last', buckets[buckets.length - 1]]];
  for (const [which, b] of edges) {
    const [a, z] = span(b);
    if (isNaN(a.getTime())) continue;
    const full = Math.round((z - a) / DAY) + 1;
    const lo = a > from ? a : from, hi = z < to ? z : to;
    const have = Math.round((hi - lo) / DAY) + 1;
    if (have > 0 && have < full) out.push(which + ' ' + grain + ' partial · ' + have + ' of ' + full + ' days');
  }
  return out;
}

// One trend chart for every ads view, through the SAME engine the four P&L
// charts use (hard rule #1): pnlTrendSeries builds the datasets,
// pnlTrendRender draws them, pnlTrendSubtitle describes the state and
// pnlInjectChartModeToggle paints Line / Stacked.
const _adsChartInstance = {};
const ADS_CHART_COLORS = ['#4a9e38','#f97316','#3b82f6','#a855f7','#ef4444','#eab308','#06b6d4','#ec4899','#84cc16','#f59e0b'];
function adsUpdateChart(ctx) {
  const { ch, channel, view, COLS, res, win, list, sel, grain, totals } = ctx;
  const panel = document.getElementById(ch.host + '-chart-panel');
  if (!panel) return;
  const key = _adsKey(channel, view);
  const hide = () => {
    panel.style.display = 'none';
    if (_adsChartInstance[key]) { try { _adsChartInstance[key].destroy(); } catch (e) {} _adsChartInstance[key] = null; }
  };
  const metrics = adsChartMetrics(COLS);
  const picked = (document.getElementById(ch.host + '-chart-metric') || {}).value || 'spend';
  const m = metrics.find(x => x.k === picked) || metrics.find(x => x.k === 'spend') || metrics[0];
  if (!m) return hide();
  const NAMECOL = ch.groupBy || 'campaign';
  const selectionActive = !!(sel && sel.size);
  // No selection -> ONE total line across the rows on screen, which is the
  // question you have before you have clicked anything (the v10.12 default).
  const names = selectionActive
    ? res.campaigns.filter(c => sel.has(c[NAMECOL])).map(c => c[NAMECOL])
    : list.map(c => c[NAMECOL]);
  const buckets = res.buckets || [];
  if (!names.length || !buckets.length) return hide();
  const built = pnlTrendSeries({
    perProd: res.series || {}, buckets, mids: names, metricOf: m.sum,
    colors: ADS_CHART_COLORS, mode: pnlChartMode(),
    isPct: !!m.isPct, noStack: !!m.noStack, selectionActive,
    noun: ch.noun || 'campaign', otherNoun: (ch.noun || 'campaign') + 's',
    labelOf: n => n,
  });
  pnlInjectChartModeToggle(ch.host + '-chart-mode-host', '_adsRe_' + ch.host, !!m.noStack);
  // What the window RESOLVED to, stated rather than assumed (v10.99): the
  // grain was picked from the window length, and the edge buckets are named
  // when they are partial.
  const notes = [built.note].concat(
    typeof ch.monthOf === 'function' ? [] : adsBucketEdges(buckets, grain, win));
  if (typeof ch.monthOf !== 'function' && totals && totals.lastDate && win.to && totals.lastDate < win.to) {
    notes.push('data through ' + totals.lastDate);
  }
  const titleEl = document.getElementById(ch.host + '-chart-title');
  const subEl   = document.getElementById(ch.host + '-chart-sub');
  if (titleEl) titleEl.textContent = m.label + ' · ' + grain + 'ly trend';
  if (subEl) subEl.textContent = pnlTrendSubtitle({
    selectionActive, midCount: names.length, bandCount: built.bandCount,
    // A MONTHLY view states the MONTHS it resolved to, not the daily window
    // the period control happens to hold: "3 months, 2026-08-01 to 2026-10-29"
    // reads as a contradiction next to a chart whose last point is all of
    // October. The coverage line above already names the months; the subtitle
    // must not disagree with it one line down.
    buckets: buckets.length,
    from: (typeof ch.monthOf === 'function' ? buckets[0] : (win.from || 'start')),
    to:   (typeof ch.monthOf === 'function' ? buckets[buckets.length - 1] : (win.to || 'today')),
    mode: built.mode, note: notes.filter(Boolean).join(' · '),
    bucketNoun: grain, noun: ch.noun || 'campaign',
  });
  panel.style.display = 'block';
  // Fire and forget: pnlTrendRender awaits the Chart.js loader, and the
  // renderer that called us is synchronous (v11.03).
  pnlTrendRender({
    canvasId: ch.host + '-chart-canvas', instance: _adsChartInstance[key],
    buckets, datasets: built.datasets, mode: built.mode,
    isPct: !!m.isPct, unit: m.unit,
  }).then(inst => { _adsChartInstance[key] = inst; })
    .catch(e => console.warn('ads trend chart:', (e && e.message) || e));
}

// ⚠ The shell is built ONCE per host and then only repainted. Re-emitting the
// controls on every render would blow away the search box's focus and caret
// mid-keystroke — the v10.99 "do not rewrite the field while you type" rule,
// applied to the whole control row.
function adsEnsureShell(channel, view) {
  const ch = adsViewCfg(channel, view); if (!ch) return null;
  const COLS = ch.columns || ADS_COLUMNS[channel] || [];
  const host = document.getElementById(ch.host + '-host');
  if (!host) return null;
  // The shared Line / Stacked toggle and the Bands stepper re-render through
  // window[name](), which has to be callable with no arguments. One named
  // global per host, registered where the host is built.
  window['_adsRe_' + ch.host] = () => renderAdsCampaigns(channel, view);
  if (host.dataset.built) return host;
  // One <select multiple>-free control per filterable dimension. A plain
  // single-select keeps it readable at a glance; the rollup still takes a SET
  // per dimension, so a multi-select can be dropped in later without the
  // aggregation changing at all.
  const filterPickers = (ch.filters || []).map(f =>
      `<label style="display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:11px;color:var(--text3)">${f.label}`
    + `<select id="${ch.host}-f-${f.k}" onchange="renderAdsCampaigns('${channel}','${view || ''}')" `
    + `style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);`
    + `border:1px solid var(--border2);border-radius:5px;padding:4px 8px">`
    + `<option value="">All</option></select></label>`).join('');
  const brandPicker = channel === 'chewy'
    ? `<select id="chads-brand" onchange="renderAdsCampaigns('chewy')" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:4px 8px"><option value="">All Brands</option></select>`
    : '';
  host.innerHTML =
      `<div id="${ch.host}-freshness" style="margin-bottom:10px"></div>`
    + `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px">`
    +   `<input type="text" id="${ch.host}-search" placeholder="Search…" title="Matches any text column on this table." oninput="adsSearchChanged('${channel}','${view || ''}')" autocomplete="off" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:5px 10px;width:260px">`
    +   brandPicker
    +   filterPickers
    +   `<label style="font-family:var(--mono);font-size:11px;color:var(--text2);cursor:pointer" title="Campaigns with no spend in this window. Hidden by default because a long tail of paused campaigns buries the ones actually running.">`
    +     `<input type="checkbox" id="${ch.host}-zero" onchange="renderAdsCampaigns('${channel}','${view || ''}')"> show zero-spend</label>`
    +   `<button onclick="downloadAdsCampaignsCSV('${channel}','${view || ''}')" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text2);border:1px solid var(--border2);border-radius:6px;padding:5px 12px;cursor:pointer">↓ CSV</button>`
    + `</div>`
    + `<div id="${ch.host}-cards" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:14px"></div>`
    // The Summary page's trend panel, same `.ds` card and the same control
    // row, because that is the page Jason named as the reference (rule #4).
    // The metric list is built from this view's own column registry.
    + `<div id="${ch.host}-chart-panel" style="display:none;margin-bottom:14px">`
    +   `<div class="ds" style="resize:vertical;overflow:auto;height:340px;min-height:240px;max-height:720px">`
    +     `<div class="ds-hdr">`
    +       `<div style="flex:1;min-width:0"><div class="ds-title" id="${ch.host}-chart-title">Trend</div>`
    +         `<div class="ds-sub" id="${ch.host}-chart-sub"></div></div>`
    +       `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">`
    +         `<span id="${ch.host}-chart-mode-host" style="display:inline-flex;gap:6px;align-items:center"></span>`
    +         `<span style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">Metric</span>`
    +         `<select id="${ch.host}-chart-metric" onchange="renderAdsCampaigns('${channel}','${view || ''}')" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:4px 8px;outline:none">`
    +           adsChartMetrics(COLS).map(m => `<option value="${m.k}"${m.k === 'spend' ? ' selected' : ''}>${esc2(m.label)}</option>`).join('')
    +         `</select>`
    +       `</div>`
    +     `</div>`
    +     `<div class="ds-body" style="padding:0;height:calc(100% - 56px);position:relative">`
    +       `<canvas id="${ch.host}-chart-canvas" style="width:100%;height:100%;display:block"></canvas>`
    +     `</div>`
    +   `</div></div>`
    + `<div id="${ch.host}-cov" style="font-family:var(--mono);font-size:10px;color:var(--text3);margin-bottom:8px"></div>`
    + `<div class="tbl-wrap" style="max-height:560px;overflow:auto">`
    +   `<table style="width:100%;border-collapse:collapse;font-size:12px">`
    +     `<thead><tr id="${ch.host}-thead" style="position:sticky;top:0;background:var(--surface);z-index:2"></tr></thead>`
    +     `<tbody id="${ch.host}-tbody"></tbody>`
    +     `<tfoot><tr id="${ch.host}-tfoot" style="position:sticky;bottom:0;background:var(--surface);font-weight:700"></tr></tfoot>`
    +   `</table></div>`;
  host.dataset.built = '1';
  return host;
}

function renderAdsCampaigns(channel, view) {
  const ch = adsViewCfg(channel, view); if (!ch) return;
  if (!adsEnsureShell(channel, view)) return;
  const COLS = ch.columns || ADS_COLUMNS[channel];
  if (typeof renderPageFreshness === 'function') {
    renderPageFreshness(ch.host + '-freshness', ch.freshness).catch(console.warn);
  }

  const win = ch.range() || {};
  const brand = ch.brand();
  // Read the filter strip into the {dimension: Set} shape the rollup takes.
  const picked = {};
  for (const f of (ch.filters || [])) {
    const v = (document.getElementById(ch.host + '-f-' + f.k) || {}).value || '';
    if (v) picked[f.k] = new Set([v]);
  }
  // The chart's bucket grain, chosen from the window and STATED in the
  // chart's own subtitle. Asking the rollup for the series here means the
  // chart is built from the same scan, the same window and the same filters
  // as the table - it cannot describe a different slice (the v11.20 rule).
  const grain = adsGrain(win, ch);
  const res = adsCampaignRollup({ channel, view, from: win.from, to: win.to, brand, filters: picked, bucket: grain });
  // ⚠ The OPTIONS come from an UNFILTERED pass over the same window. Reading
  // them off the filtered result would leave the control showing only the value
  // already picked, with no way back to the others - a filter you can enter and
  // not leave.
  const optsRes = Object.keys(picked).length
    ? adsCampaignRollup({ channel, view, from: win.from, to: win.to, brand })
    : res;
  for (const f of (ch.filters || [])) {
    const sel = document.getElementById(ch.host + '-f-' + f.k);
    if (!sel) continue;
    const opts = (optsRes.options && optsRes.options[f.k]) || [];
    const keep = sel.value;
    const next = '<option value="">All</option>'
      + opts.map(v => `<option value="${esc2(v)}">${esc2(v)}</option>`).join('');
    if (sel.innerHTML !== next) sel.innerHTML = next;
    // A stored pick the window no longer contains falls back to All rather
    // than leaving the control on a value the table cannot show (v11.02).
    sel.value = opts.includes(keep) ? keep : '';
  }
  // The comparison basis: the block of the same length immediately before the
  // window. Ad spend has no calendar-twin thesis the way the Program tab does,
  // so prev-period is the only basis offered rather than a toggle that looks
  // live and only has one setting (the v10.19 rule).
  //
  // ⚠ IT TAKES `view` AND `filters`. Without the view, an Amazon KEYWORDS
  // tab compared search-term spend against the unified report's - two
  // different tables under one chip. Without the filters, picking an ad type
  // narrowed the current total and not the prior one, so every chip read as a
  // collapse the moment a filter was set. Both shipped in v11.22.
  let prev = null;
  if (typeof ch.monthOf === 'function') {
    // ⚠ A MONTHLY VIEW NEEDS A MONTHLY PRIOR BLOCK. Shifting a 15-day window
    // back 15 days lands inside the SAME month, and this view takes any month
    // that OVERLAPS - so the "previous period" would contain the period it is
    // being compared against. Instead: the same NUMBER of whole months
    // immediately before the earliest month on screen.
    const mm = res.coverage.months || [];
    if (mm.length) {
      const [py, pm] = String(mm[0]).split('-').map(Number);
      const pFrom = new Date(py, pm - 1 - mm.length, 1);
      const pTo   = new Date(py, pm - 1, 0);      // day 0 = last day of the month before
      prev = adsCampaignRollup({ channel, view, from: adsYmd(pFrom), to: adsYmd(pTo), brand, filters: picked });
    }
  } else if (win.from && win.to && !win.allTime) {
    const d0 = new Date(win.from + 'T00:00:00'), d1 = new Date(win.to + 'T00:00:00');
    const len = Math.round((d1 - d0) / 86400000) + 1;
    if (len > 0) {
      const pTo = new Date(d0.getTime() - 86400000);
      const pFrom = new Date(pTo.getTime() - (len - 1) * 86400000);
      prev = adsCampaignRollup({ channel, view, from: adsYmd(pFrom), to: adsYmd(pTo), brand, filters: picked });
    }
  }
  // The export reads this SNAPSHOT, never a recompute (the v8.00 rule), so
  // the selection has to ride along with it.
  _adsExport[_adsKey(channel, view)] = { res, win, brand, channel, view,
    sel: [...adsState(channel, view).sel] };

  const t = res.totals;
  const $0 = (n) => '$' + Math.round(Number(n) || 0).toLocaleString();
  const n0 = (n) => Math.round(Number(n) || 0).toLocaleString();

  // ── what is on screen ─────────────────────────────────────────────────
  // v11.23 — the row list is resolved BEFORE the scorecards, because the
  // cards now have to know which of the selected rows the search has hidden.
  // One resolution of "what is visible", read by the banner, the table, the
  // footer and the chart.
  const st = adsState(channel, view);
  // ⚠ The NAME column is the view's own grouping key — 'campaign' on the
  // Campaigns view, 'term' on Keywords.
  const NAMECOL = ch.groupBy || 'campaign';
  const q = (document.getElementById(ch.host + '-search')?.value || '').trim().toLowerCase();
  const showZero = !!document.getElementById(ch.host + '-zero')?.checked;
  // ⚠ THE HAYSTACK IS EVERY TEXT COLUMN THE VIEW RENDERS, detected by VALUE.
  // It was hardcoded to campaign + type + status, which on the Keywords view
  // is the campaign LIST and two empty strings — so typing a search term
  // filtered on everything except the thing the table is a list of.
  const hay = (c) => COLS.map(col => c[col.k])
    .filter(v => typeof v === 'string').join(' ').toLowerCase();
  let list = res.campaigns.filter(c => {
    if (!showZero && !(c.spend > 0)) return false;
    if (!q) return true;
    return hay(c).indexOf(q) > -1;
  });
  const dir = st.sortDir, k = st.sortK;
  list = list.slice().sort((a, b) => {
    const av = a[k], bv = b[k];
    // Nulls sort last in BOTH directions. A campaign with no ROAS is not the
    // best or the worst performer; floating it to the top of a descending sort
    // would put the rows with no answer above the rows with one.
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'string' || typeof bv === 'string') {
      return String(av).localeCompare(String(bv)) * dir;
    }
    return (av - bv) * dir;
  });
  // The rows AS RENDERED, so a checkbox can address its row by index.
  _adsRendered[_adsKey(channel, view)] = list;

  // ── the selection ─────────────────────────────────────────────────────
  // ⚠ SELECTION NARROWS THE SCORECARDS AND THE CHART, NEVER THE WINDOW the
  // coverage line describes. Two numbers on one screen that cannot both be
  // true is the shape Jason has caught three times, so the banner sits
  // directly above the cards and says which of the two they are.
  //
  // It reads res.campaigns rather than the visible list, so a row the search
  // has hidden stays in the totals — the Summary table's rule, and the reason
  // you can build a selection across several searches.
  const sel = st.sel;
  const selRows = sel.size ? res.campaigns.filter(c => sel.has(c[NAMECOL])) : null;
  const hiddenSel = selRows ? selRows.length - list.filter(c => sel.has(c[NAMECOL])).length : 0;
  // ⚠ Ratios are derived ONCE from the summed selection, never averaged over
  // the selected rows — an average weights a $2 campaign the same as a
  // $20,000 one. adsSumRows is the same helper the window total runs through.
  const cardT = selRows ? adsSumRows(selRows, NAMECOL) : t;
  // ⚠ And the PRIOR period is narrowed to the SAME rows. Comparing three
  // selected campaigns now against a hundred and forty then would read as a
  // collapse that never happened.
  const pt = prev
    ? (selRows ? adsSumRows(prev.campaigns.filter(c => sel.has(c[NAMECOL])), NAMECOL)
               : prev.totals)
    : null;
  const prevLabel = prev ? (prev.coverage.from + ' → ' + prev.coverage.to) : 'none';
  const chip = (cur, pv, good, pts) => (pt && typeof pnlDeltaChip === 'function')
    ? pnlDeltaChip(cur, pv, good, pts, prevLabel) : '';

  const NOUN = ch.noun || 'campaign';
  const hiddenChip = hiddenSel > 0
    ? `<span title="Still counted in the cards and the chart. They are just not in the table below, because the search or the zero-spend filter narrowed it." style="display:inline-block;background:var(--surface);border:1px solid var(--sp-orange,#f5a142);color:var(--sp-orange,#f5a142);font-family:var(--mono);font-size:10px;font-weight:700;border-radius:4px;padding:3px 8px">⚠ ${hiddenSel} hidden</span>`
    : '';
  // Same banner shape as the Summary table's drill banner, in the same grid
  // slot (grid-column:1/-1) — rule #4, the page Jason named as the reference.
  const selBanner = selRows
    ? `<div style="grid-column:1/-1;background:var(--surface2);border:1px solid var(--sp-green);border-radius:10px;padding:8px 14px;display:flex;justify-content:space-between;align-items:center;gap:12px">
        <div style="min-width:0;font-family:var(--mono);font-size:11px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc2(selRows.map(c => c[NAMECOL]).join(', '))}">
          <span style="color:var(--sp-green);font-weight:700">${selRows.length} ${NOUN}${selRows.length === 1 ? '' : 's'} selected</span> · cards and chart below only · ${$0(cardT.spend)}
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">${hiddenChip}<button onclick="adsClearSelection('${channel}','${view || ''}')" style="background:var(--surface);border:1px solid var(--border2);border-radius:5px;padding:5px 12px;font-size:11px;color:var(--text2);cursor:pointer;font-family:var(--display);font-weight:700;white-space:nowrap">✕ Clear</button></div>
      </div>`
    : '';

  const cards = document.getElementById(ch.host + '-cards');
  if (cards && typeof pnlCardStrip === 'function') {
    cards.innerHTML = selBanner + pnlCardStrip([
      // ⚠ Ad Spend is NEUTRAL (goodWhenUp null). Spend rising is neither good
      // nor bad on its own, and a red chip there reads as "cut it" — the one
      // default Jason has ruled out for brand and awareness spend. v11.03.
      // The view's own noun; 'campaign' stays the default so the Campaigns
      // view reads exactly as before.
      { label: 'Ad Spend', val: $0(cardT.spend),
        sub: selRows
          ? (selRows.length + ' of ' + res.campaigns.length + ' selected')
          : (res.coverage.campaignCount + ' ' + NOUN
             + (res.coverage.campaignCount === 1 ? '' : 's')),
        color: 'var(--sp-red)', delta: chip(cardT.spend, pt && pt.spend, null), src: ch.src },
      { label: channel === 'chewy' ? 'Direct Sales (retail)' : 'Ad Sales', val: $0(cardT.sales),
        sub: 'attributed to a click', delta: chip(cardT.sales, pt && pt.sales, true), src: ch.src },
      { label: channel === 'chewy' ? 'Direct ROAS' : 'ROAS',
        val: cardT.roas == null ? '—' : cardT.roas.toFixed(2) + 'x',
        sub: cardT.acos == null ? 'no attributed sales' : cardT.acos.toFixed(1) + '% ACOS',
        color: cardT.roas == null ? 'var(--text3)' : (cardT.roas >= 1 ? 'var(--sp-green)' : 'var(--sp-red)'),
        delta: chip(cardT.roas, pt && pt.roas, true), src: ch.src },
      { label: 'Clicks', val: n0(cardT.clicks),
        sub: (cardT.ctr == null ? '—' : cardT.ctr.toFixed(2) + '% CTR') + ' · ' + (cardT.cpc == null ? '—' : '$' + cardT.cpc.toFixed(2) + ' CPC'),
        delta: chip(cardT.clicks, pt && pt.clicks, true), src: ch.src },
      { label: channel === 'chewy' ? 'Total orders' : 'Orders', val: n0(cardT.orders),
        sub: cardT.cpa == null ? 'no attributed orders' : '$' + cardT.cpa.toFixed(2) + ' per order',
        delta: chip(cardT.orders, pt && pt.orders, true), src: ch.src },
    ].concat(channel === 'chewy' ? [{
      label: 'NTB', val: n0(cardT.ntb), sub: 'new-to-brand customers',
      delta: chip(cardT.ntb, pt && pt.ntb, true), src: ch.src,
    }] : []));
  }

  // --- header, sortable -----------------------------------------------
  // The select-all checkbox leads the row, like the Summary table's.
  const selAllTh = `<th style="text-align:center;padding:6px 6px;width:30px;border-bottom:1px solid var(--border2)" title="Select every row currently visible, or clear them."><input type="checkbox" id="${ch.host}-selall" onclick="adsToggleAllVisible('${channel}','${view || ''}')" style="cursor:pointer;margin:0;vertical-align:middle"></th>`;
  const th = document.getElementById(ch.host + '-thead');
  if (th) th.innerHTML = selAllTh + COLS.map(c => {
    const arrow = st.sortK === c.k ? (st.sortDir < 0 ? ' ▼' : ' ▲') : '';
    return `<th onclick="adsSortBy('${channel}','${c.k}','${view || ''}')" title="${esc2(c.tip || c.label)}"`
      + ` style="text-align:${c.align};padding:6px 8px;min-width:${c.w}px;cursor:pointer;`
      + `font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.5px;`
      + `color:var(--text3);border-bottom:1px solid var(--border2);white-space:nowrap">${c.label}${arrow}</th>`;
  }).join('');

  // --- rows -------------------------------------------------------------
  const RED = 'var(--sp-red,#d63f2a)';
  const cellOf = (c, col) => {
    const v = c[col.k];
    const pad = `padding:5px 8px;text-align:${col.align};white-space:nowrap`;
    if (col.k === NAMECOL) {
      // The no-campaign bucket is DIMMED AND NAMED, not hidden, and says why.
      const dim = c.noCampaign ? ';color:var(--text3);font-style:italic' : '';
      const tip = c.noCampaign
        ? ' title="Spend uploaded before the Campaign name column existed. Re-upload this window from Amazon Ads → Reports with Campaign name as a dimension to fill it in."'
        : ` title="${esc2(c[NAMECOL])}"`;
      return `<td${tip} style="${pad};max-width:${col.w}px;overflow:hidden;text-overflow:ellipsis${dim}">${esc2(c[NAMECOL])}</td>`;
    }
    // ⚠ TEXT IS DETECTED BY VALUE, NOT BY A LIST OF COLUMN NAMES. The old
    // check named campaign / type / status and sent everything else to the
    // numeric formatter, so a view with its own text columns rendered
    // Math.round('catnip spray') - NaN, in the first column of the table.
    if (typeof v === 'string' || col.k === 'type' || col.k === 'status') {
      return `<td style="${pad};font-family:var(--mono);font-size:10px;color:var(--text3)">${esc2(v || '—')}</td>`;
    }
    if (v == null) return `<td style="${pad};color:var(--text3)">—</td>`;
    let out;
    if (col.k === 'spend' || col.k === 'sales') out = '$' + Math.round(v).toLocaleString();
    else if (col.k === 'cpc' || col.k === 'cpa') out = '$' + v.toFixed(2);
    else if (col.k === 'ctr' || col.k === 'acos') out = v.toFixed(1) + '%';
    else if (col.k === 'roas') out = v.toFixed(2) + 'x';
    else out = Math.round(v).toLocaleString();
    const warn = (col.k === 'roas' && v < 1) || (col.k === 'acos' && v > 100);
    return `<td style="${pad}${warn ? ';color:' + RED : ''}">${out}</td>`;
  };

  const SEL_BG = 'rgba(127,211,42,0.10)';   // tinted sp-green, same as Summary
  const tb = document.getElementById(ch.host + '-tbody');
  if (tb) {
    tb.innerHTML = list.length
      ? list.map((c, i) => {
          const on = sel.has(c[NAMECOL]);
          return `<tr style="border-bottom:1px solid var(--border);cursor:pointer;background:${on ? SEL_BG : ''}" data-sel="${on ? '1' : '0'}"`
            + ` onclick="adsToggleRow('${channel}',${i},'${view || ''}')"`
            + ` onmouseover="if(this.dataset.sel!=='1')this.style.background='var(--surface2)'"`
            + ` onmouseout="this.style.background=this.dataset.sel==='1'?'${SEL_BG}':''">`
            + `<td style="text-align:center;padding:5px 6px;width:30px"><input type="checkbox" ${on ? 'checked' : ''} onclick="event.stopPropagation();adsToggleRow('${channel}',${i},'${view || ''}')" style="cursor:pointer;margin:0;vertical-align:middle"></td>`
            + COLS.map(col => cellOf(c, col)).join('') + '</tr>';
        }).join('')
      : `<tr><td colspan="${COLS.length + 1}" style="text-align:center;padding:24px;color:var(--text3);font-family:var(--mono);font-size:11px">`
        + (res.coverage.scanned
            ? 'No ' + NOUN + 's with spend in this window.'
            : 'No ' + ch.label + ' data loaded yet — upload it from Data → Uploads.')
        + '</td></tr>';
  }
  // The select-all box mirrors the visible rows: checked when all are on,
  // indeterminate when some are.
  const selAllEl = document.getElementById(ch.host + '-selall');
  if (selAllEl) {
    const onCount = list.filter(c => sel.has(c[NAMECOL])).length;
    selAllEl.checked = list.length > 0 && onCount === list.length;
    selAllEl.indeterminate = onCount > 0 && onCount < list.length;
  }
  // ⚠ The TOTAL row is KEYED off the same registry the header reads. A
  // hand-ordered footer slides every value under the wrong heading the moment
  // a column is added, silently — the v10.54 / v11.03 defect, twice already.
  const tf = document.getElementById(ch.host + '-tfoot');
  if (tf) {
    // The footer totals WHAT IS ON SCREEN, so a search or the zero-spend
    // filter cannot leave a TOTAL describing rows the operator cannot see.
    // ⚠ Through the SAME summer as the window total and the selection cards,
    // so the three cannot derive a ratio differently. The hand-written version
    // re-derived ctr / cpc / cpa / roas / acos and forgot cvr, which left one
    // Keywords footer cell describing the window while the rest described the
    // search.
    const shown = adsSumRows(list, NAMECOL);
    // ⚠ ROWS, not 'campaigns'. The scorecard above counts NAMED campaigns
    // and this counts what is on screen, which also includes the (no campaign)
    // bucket - so the two legitimately differ. Saying 'campaigns' in both
    // places made the page look like it was contradicting itself one scroll
    // apart, with nothing to say which number to trust.
    shown[NAMECOL] = list.length + ' row' + (list.length === 1 ? '' : 's');
    // Blank every OTHER text column: a joined list of campaigns or match
    // types has no meaningful total, and formatting it as a number is how the
    // NaN got there in the first place.
    for (const col of COLS) {
      if (col.k !== NAMECOL && typeof shown[col.k] === 'string') shown[col.k] = '';
    }
    tf.innerHTML = `<td style="width:30px;border-top:1px solid var(--border2)"></td>` + COLS.map(col => {
      if (col.k === NAMECOL) return `<td style="padding:6px 8px;text-align:left;font-family:var(--mono);font-size:11px;border-top:1px solid var(--border2)">${esc2(shown[NAMECOL])}</td>`;
      const c = cellOf(shown, col);
      return c.replace('<td', '<td').replace('style="padding:5px 8px', 'style="padding:6px 8px;border-top:1px solid var(--border2)');
    }).join('');
  }

  // The trend, through the same engine the four P&L charts use.
  try {
    adsUpdateChart({ ch, channel, view, COLS, res, win, list, sel, grain, totals: t });
  } catch (e) { console.warn('ads trend chart:', (e && e.message) || e); }

  const cov = document.getElementById(ch.host + '-cov');
  if (cov) {
    const parts = [];
    // ⚠ A view whose feed is monthly says so, and names the months it
    // actually resolved to. The Campaigns tab is genuinely daily, so the two
    // tabs under one period control CAN resolve different windows - which is
    // exactly why each states its own (the v11.02 rule).
    if (typeof ch.monthOf === 'function') {
      const mm = res.coverage.months || [];
      parts.push(mm.length
        ? ('monthly grain · ' + mm.length + ' month' + (mm.length === 1 ? '' : 's')
           + ' · ' + mm[0] + (mm.length > 1 ? ' → ' + mm[mm.length - 1] : ''))
        : 'monthly grain · no month overlaps this window');
    } else {
      parts.push((win.from || 'start') + ' → ' + (win.to || 'today'));
    }
    if (brand) parts.push(brand);
    parts.push(res.coverage.campaignCount + ' ' + (ch.noun || 'campaign')
      + (res.coverage.campaignCount === 1 ? '' : 's'));
    parts.push($0(t.spend) + ' spend');
    // A filter one row above the table still reads as ignored unless something
    // states what it resolved to - the v10.99 lesson.
    for (const [k, vals] of Object.entries(res.coverage.filters || {})) {
      const f = (ch.filters || []).find(x => x.k === k);
      parts.push((f ? f.label : k) + ': ' + vals.join(', '));
    }
    if (res.coverage.noCampaignSpend > 0) {
      parts.push('⚠ ' + $0(res.coverage.noCampaignSpend) + ' ('
        + res.coverage.noCampaignPct.toFixed(0) + '%) has no campaign on record');
    }
    cov.textContent = parts.join(' · ');
    cov.title = res.coverage.noCampaignSpend > 0
      ? 'Spend uploaded before the Campaign name column existed. It is included in every total here so nothing is understated; re-upload the window with Campaign name as a dimension to break it out.'
      : '';
  }
  if (typeof fitTableWrapsSoon === 'function') fitTableWrapsSoon();
}

// Every data-bearing view is CSV-exportable from the top-bar button.
// ⚠ Reads the render SNAPSHOT, never a recompute — a recompute could silently
// disagree with the table it claims to export (the v8.00 rule).
function downloadAdsCampaignsCSV(channel, view) {
  const snap = _adsExport[_adsKey(channel, view)];
  const ch = adsViewCfg(channel, view);
  if (!snap || !ch || !snap.res) {
    alert('No ' + (ch ? ch.label : 'ads') + ' data to export — open the Ads tab and let it render first.');
    return;
  }
  const { res, win, brand } = snap;
  const COLS = ch.columns || ADS_COLUMNS[channel];
  const f2 = (v) => v == null ? '' : Number(v).toFixed(2);
  const i0 = (v) => v == null ? '' : String(Math.round(Number(v)));
  const esc = (v) => {
    const sv = v == null ? '' : String(v);
    return /[",\n]/.test(sv) ? '"' + sv.replace(/"/g, '""') + '"' : sv;
  };
  // ⚠ TEXT IS DETECTED BY VALUE, NOT BY A LIST OF COLUMN NAMES - the same
  // rule the table renderer follows. Naming campaign / type / status here
  // sent the Keywords view's own text columns through Math.round, so every
  // row of that export carried the literal string NaN in Search term and
  // Match. The table was fixed in v11.22b and this second renderer of the
  // same data was not.
  const val = (c, k) => {
    const v = c[k];
    if (typeof v === 'string') return v;
    if (v == null) return '';
    if (k === 'spend' || k === 'sales' || k === 'cpc' || k === 'cpa'
        || k === 'ctr' || k === 'acos' || k === 'roas') return f2(v);
    return i0(v);
  };
  const lines = [];
  // A file with no stated scope is unreadable three weeks later (v10.79).
  lines.push('# ' + ch.label + ' · ' + (ch.noun || 'campaign') + ' level');
  lines.push('# window: ' + (win.from || 'start') + ' to ' + (win.to || 'today'));
  lines.push('# brand: ' + (brand || 'all brands'));
  // ⚠ A monthly-grain view SAYS SO in the file, and names the months it
  // resolved to. Without it an archived export looks like it covers the daily
  // window in the line above, which it does not.
  if (res.coverage.months && res.coverage.months.length) {
    lines.push('# grain: MONTHLY - ' + res.coverage.months.join(' '));
  }
  const _af = Object.entries(res.coverage.filters || {});
  lines.push('# filters: ' + (_af.length
    ? _af.map(([k, v]) => k + '=' + v.join('|')).join(' · ') : 'none'));
  lines.push('# ' + res.coverage.campaignCount + ' named ' + (ch.noun || 'campaign')
    + (res.coverage.campaignCount === 1 ? '' : 's') + ' · '
    + res.campaigns.length + ' rows including the un-named bucket');
  // ⚠ THE ROWS ARE THE WHOLE WINDOW even when rows are checked. A file that
  // silently dropped rows because a checkbox was ticked would be unreadable
  // later; the header says which part of the screen the selection governed.
  if (snap.sel && snap.sel.length) {
    lines.push('# selection: ' + snap.sel.length + ' ' + (ch.noun || 'campaign')
      + (snap.sel.length === 1 ? '' : 's') + ' were checked - that narrowed the scorecards and the chart only, not the rows below');
  }
  if (res.coverage.noCampaignSpend > 0) {
    lines.push('# ' + res.coverage.noCampaignSpend.toFixed(2) + ' of spend ('
      + res.coverage.noCampaignPct.toFixed(1) + '%) has no campaign on record - uploaded '
      + 'before the Campaign name column existed. Included in the TOTAL, not dropped.');
  }
  lines.push(COLS.map(c => c.label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')).join(','));
  for (const c of res.campaigns) lines.push(COLS.map(col => esc(val(c, col.k))).join(','));
  lines.push(COLS.map((col, i) => i === 0 ? 'TOTAL' : esc(val(res.totals, col.k))).join(','));

  const name = promptCsvName('smarterpaw-ads-' + channel + '-' + (view || 'campaigns') + '-'
    + new Date().toISOString().slice(0, 10) + '.csv');
  if (!name) return;
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  if (typeof logAudit === 'function') logAudit('ads.campaign_export', {
    channel, campaigns: res.campaigns.length, spend: res.totals.spend,
    from: win.from || null, to: win.to || null,
  });
}

// Loader per channel — reuses each channel's EXISTING cache + loader rather
// than issuing a third query against the same table (hard rule #1).
async function loadAdsCampaigns(channel, view) {
  const ch = adsViewCfg(channel, view); if (!ch) return;
  adsEnsureShell(channel, view);
  const tb = document.getElementById(ch.host + '-tbody');
  if (tb && !tb.innerHTML) {
    tb.innerHTML = `<tr><td colspan="${(ch.columns || ADS_COLUMNS[channel]).length + 1}" style="text-align:center;padding:24px;color:var(--text3);font-family:var(--mono);font-size:11px">⏳ Loading ${ch.label}…</td></tr>`;
  }
  try {
    // A view may read a different table than its channel's default feed.
    if (typeof ch.load === 'function') { await ch.load(); }
    else if (channel === 'amazon' && typeof loadAmazonAdSpend === 'function') await loadAmazonAdSpend();
    if (channel === 'chewy') {
      if (typeof loadChewyAdSpend === 'function') await loadChewyAdSpend();
      adsFillChewyBrands();
    }
    renderAdsCampaigns(channel, view);
  } catch (e) {
    if (tb) tb.innerHTML = `<tr><td colspan="${(ch.columns || ADS_COLUMNS[channel]).length + 1}" style="text-align:center;padding:24px;color:var(--sp-red,#d63f2a);font-family:var(--mono);font-size:11px">✗ ${esc2(e.message || e)}</td></tr>`;
  }
}

// The Chewy brand picker is filled from the DATA, not a hardcoded list, so an
// advertiser account that appears later shows up with no code change.
function adsFillChewyBrands() {
  const sel = document.getElementById('chads-brand');
  if (!sel) return;
  const keep = sel.value;
  const names = [...new Set((ADS_CHANNELS.chewy.rows() || [])
    .map(r => String(r.advertiser || '').trim()).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">All Brands</option>'
    + names.map(n => `<option value="${esc2(n)}">${esc2(n)}</option>`).join('');
  if (keep && names.includes(keep)) sel.value = keep;
}



var allProducts = [];
var amazonSpSearchTermCache = [];
const AMZ = [
  { date:'2026-10-01', region:'US', campaign:'C1', ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:1000, clicks:50, spend:100, purchases:5, attributed_sales:400 },
  { date:'2026-10-02', region:'US', campaign:'C2', ad_product:'sponsored_brands',
    asin:'B2', master_id:'M2', impressions:2000, clicks:25, spend:300, purchases:2, attributed_sales:150 },
];
// ONE term under TWO campaigns and TWO match types, plus a month outside.
const ST = [
  { reporting_month:'2026-10', reporting_date:'2026-10-31', customer_search_term:'catnip spray',
    match_type:'EXACT', campaign_name:'KW Exact', ad_group_name:'AG1', asin:'B1', master_id:'M1',
    impressions:12000, clicks:400, spend:520, orders_7d:60, units_7d:72, sales_7d:1800 },
  { reporting_month:'2026-10', reporting_date:'2026-10-31', customer_search_term:'catnip spray',
    match_type:'BROAD', campaign_name:'KW Broad', ad_group_name:'AG2', asin:'B1', master_id:'M1',
    impressions:30000, clicks:200, spend:260, orders_7d:10, units_7d:11, sales_7d:300 },
  { reporting_month:'2026-09', reporting_date:'2026-09-30', customer_search_term:'cat nip toys',
    match_type:'AUTO', campaign_name:'AUTO', ad_group_name:'AG3', asin:'B2', master_id:'M2',
    impressions:9000, clicks:90, spend:120, orders_7d:4, units_7d:4, sales_7d:60 },
  { reporting_month:'2026-06', reporting_date:'2026-06-30', customer_search_term:'old term',
    match_type:'EXACT', campaign_name:'OLD', ad_group_name:'AG4', asin:'B3', master_id:'M3',
    impressions:100, clicks:1, spend:2, orders_7d:0, units_7d:0, sales_7d:0 },
];
ADS_VIEWS.amazon.keywords.rows = () => ST;
const W = { from:'2026-09-01', to:'2026-10-28' };


const out = {};
// A1 - the campaigns path with and without the new `view` plumbing
const noView = adsCampaignRollup({ channel:'amazon', rows:AMZ, from:W.from, to:W.to, regionOk:false });
const asCamp = adsCampaignRollup({ channel:'amazon', view:'campaigns', rows:AMZ, from:W.from, to:W.to, regionOk:false });
const strip = (r) => JSON.stringify(r, (k, v) => v instanceof Set ? [...v].sort() : v);
out.campaignsIdentical = strip(noView) === strip(asCamp);
out.campaignsSpend = noView.totals.spend;

// A2 - keywords group by term, collecting campaigns and match types
const kw = adsCampaignRollup({ channel:'amazon', view:'keywords', from:W.from, to:W.to, regionOk:false });
out.terms = kw.campaigns.map(c => c.term).sort();
const spray = kw.campaigns.find(c => c.term === 'catnip spray');
out.sprayMatch    = spray.match;
out.sprayCampaign = spray.campaign;
out.spraySpend    = spray.spend;
out.sprayClicks   = spray.clicks;
out.sprayCvr      = +spray.cvr.toFixed(4);
out.sprayRoas     = +spray.roas.toFixed(4);
out.sprayAsins    = spray.skus;
out.kwMonths      = kw.coverage.months;
out.kwSpend       = kw.totals.spend;
out.kwTotalCvr    = +kw.totals.cvr.toFixed(4);

// A3 - THE MONTHLY WINDOW GUARD. The naive read compares reporting_date to the
// daily window; 2026-10-31 is AFTER a window ending 2026-10-28, so the whole
// October month would vanish.
const naive = ST.filter(r => r.reporting_date >= W.from && r.reporting_date <= W.to);
out.naiveMonths = [...new Set(naive.map(r => r.reporting_month))].sort();
out.naiveSpend  = naive.reduce((a, r) => a + r.spend, 0);

// A4 - a window with no overlapping month is honest, not a throw
const none = adsCampaignRollup({ channel:'amazon', view:'keywords', from:'2026-01-01', to:'2026-02-28', regionOk:false });
out.noneRows = none.campaigns.length;
out.noneMonths = none.coverage.months;
out.noneBad = /NaN|Infinity/.test(JSON.stringify(none.totals));

// A5 - the match filter narrows at row level here too
const ex = adsCampaignRollup({ channel:'amazon', view:'keywords', from:W.from, to:W.to,
                               regionOk:false, filters:{ match: new Set(['EXACT']) } });
const exSpray = ex.campaigns.find(c => c.term === 'catnip spray');
out.exactSpend = exSpray ? exSpray.spend : null;
out.exactMatch = exSpray ? exSpray.match : null;
out.exactOptions = ex.options.match;
console.log(JSON.stringify(out));
