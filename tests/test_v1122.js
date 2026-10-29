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
  }

  const derive = (c) => {
    c.type   = [...c.types].sort().join(' · ');
    c.status = [...c.statuses].sort().join(' · ');
    if (GROUP !== 'campaign') {
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
  };

  const campaigns = [...agg.values()].map(derive);
  // Totals are summed from the ROWS, then the ratios derived once — never
  // averaged across campaigns, which would weight a $2 campaign the same as a
  // $20,000 one (the v11.08 lesson, in a different table).
  const t = { campaign: 'TOTAL', types: new Set(), statuses: new Set(), skuSet: new Set(),
              matches: new Set(), campaigns: new Set(), adgroups: new Set(),
              impressions: 0, clicks: 0, spend: 0, orders: 0, units: 0, sales: 0,
              ntb: 0, signups: 0, hasUnits: false, hasNtb: false, firstDate: '', lastDate: '' };
  for (const c of campaigns) {
    t.impressions += c.impressions; t.clicks += c.clicks; t.spend += c.spend;
    t.orders += c.orders; t.sales += c.sales; t.signups += c.signups;
    if (c.units != null) { t.units += c.units; t.hasUnits = true; }
    if (c.ntb   != null) { t.ntb   += c.ntb;   t.hasNtb   = true; }
    c.skuSet.forEach(s => t.skuSet.add(s));
    c.types.forEach(s => t.types.add(s));
    if (!t.firstDate || (c.firstDate && c.firstDate < t.firstDate)) t.firstDate = c.firstDate;
    if (c.lastDate > t.lastDate) t.lastDate = c.lastDate;
  }
  derive(t);

  // Coverage: how much of this window predates campaign tracking. Reported as
  // SPEND, not as a row count — a row count would make a long tail of tiny
  // legacy rows look like a bigger hole than it is, and vice versa.
  const noCamp = campaigns.find(c => c.noCampaign);
  return {
    campaigns, totals: t,
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
  return _adsState[k] || (_adsState[k] = { sortK: 'spend', sortDir: -1 });
}
let _adsExport = {};

function adsSortBy(channel, k, view) {
  const st = adsState(channel, view); if (!st) return;
  if (st.sortK === k) st.sortDir = -st.sortDir;
  else { st.sortK = k; st.sortDir = (k === 'campaign' || k === 'type' || k === 'status') ? 1 : -1; }
  renderAdsCampaigns(channel, view);
}
function adsSearchChanged(channel, view) { renderAdsCampaigns(channel, view); }

// ⚠ The shell is built ONCE per host and then only repainted. Re-emitting the
// controls on every render would blow away the search box's focus and caret
// mid-keystroke — the v10.99 "do not rewrite the field while you type" rule,
// applied to the whole control row.
function adsEnsureShell(channel, view) {
  const ch = adsViewCfg(channel, view); if (!ch) return null;
  const host = document.getElementById(ch.host + '-host');
  if (!host) return null;
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
    +   `<input type="text" id="${ch.host}-search" placeholder="Search campaign, type or status…" oninput="adsSearchChanged('${channel}','${view || ''}')" autocomplete="off" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:5px 10px;width:260px">`
    +   brandPicker
    +   filterPickers
    +   `<label style="font-family:var(--mono);font-size:11px;color:var(--text2);cursor:pointer" title="Campaigns with no spend in this window. Hidden by default because a long tail of paused campaigns buries the ones actually running.">`
    +     `<input type="checkbox" id="${ch.host}-zero" onchange="renderAdsCampaigns('${channel}','${view || ''}')"> show zero-spend</label>`
    +   `<button onclick="downloadAdsCampaignsCSV('${channel}','${view || ''}')" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text2);border:1px solid var(--border2);border-radius:6px;padding:5px 12px;cursor:pointer">↓ CSV</button>`
    + `</div>`
    + `<div id="${ch.host}-cards" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:14px"></div>`
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
  const res = adsCampaignRollup({ channel, view, from: win.from, to: win.to, brand, filters: picked });
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
  let prev = null;
  if (win.from && win.to && !win.allTime) {
    const d0 = new Date(win.from + 'T00:00:00'), d1 = new Date(win.to + 'T00:00:00');
    const len = Math.round((d1 - d0) / 86400000) + 1;
    if (len > 0) {
      const pTo = new Date(d0.getTime() - 86400000);
      const pFrom = new Date(pTo.getTime() - (len - 1) * 86400000);
      const ymd = (d) => d.toISOString().slice(0, 10);
      prev = adsCampaignRollup({ channel, from: ymd(pFrom), to: ymd(pTo), brand });
    }
  }
  _adsExport[_adsKey(channel, view)] = { res, win, brand, channel, view };

  const t = res.totals;
  const $0 = (n) => '$' + Math.round(Number(n) || 0).toLocaleString();
  const n0 = (n) => Math.round(Number(n) || 0).toLocaleString();
  const pt = prev ? prev.totals : null;
  const prevLabel = prev ? (prev.coverage.from + ' → ' + prev.coverage.to) : 'none';
  const chip = (cur, pv, good, pts) => (pt && typeof pnlDeltaChip === 'function')
    ? pnlDeltaChip(cur, pv, good, pts, prevLabel) : '';

  const cards = document.getElementById(ch.host + '-cards');
  if (cards && typeof pnlCardStrip === 'function') {
    cards.innerHTML = pnlCardStrip([
      // ⚠ Ad Spend is NEUTRAL (goodWhenUp null). Spend rising is neither good
      // nor bad on its own, and a red chip there reads as "cut it" — the one
      // default Jason has ruled out for brand and awareness spend. v11.03.
      // The view's own noun; 'campaign' stays the default so the Campaigns
      // view reads exactly as before.
      { label: 'Ad Spend', val: $0(t.spend),
        sub: res.coverage.campaignCount + ' ' + (ch.noun || 'campaign')
             + (res.coverage.campaignCount === 1 ? '' : 's'),
        color: 'var(--sp-red)', delta: chip(t.spend, pt && pt.spend, null), src: ch.src },
      { label: channel === 'chewy' ? 'Direct Sales (retail)' : 'Ad Sales', val: $0(t.sales),
        sub: 'attributed to a click', delta: chip(t.sales, pt && pt.sales, true), src: ch.src },
      { label: channel === 'chewy' ? 'Direct ROAS' : 'ROAS',
        val: t.roas == null ? '—' : t.roas.toFixed(2) + 'x',
        sub: t.acos == null ? 'no attributed sales' : t.acos.toFixed(1) + '% ACOS',
        color: t.roas == null ? 'var(--text3)' : (t.roas >= 1 ? 'var(--sp-green)' : 'var(--sp-red)'),
        delta: chip(t.roas, pt && pt.roas, true), src: ch.src },
      { label: 'Clicks', val: n0(t.clicks),
        sub: (t.ctr == null ? '—' : t.ctr.toFixed(2) + '% CTR') + ' · ' + (t.cpc == null ? '—' : '$' + t.cpc.toFixed(2) + ' CPC'),
        delta: chip(t.clicks, pt && pt.clicks, true), src: ch.src },
      { label: channel === 'chewy' ? 'Total orders' : 'Orders', val: n0(t.orders),
        sub: t.cpa == null ? 'no attributed orders' : '$' + t.cpa.toFixed(2) + ' per order',
        delta: chip(t.orders, pt && pt.orders, true), src: ch.src },
    ].concat(channel === 'chewy' ? [{
      label: 'NTB', val: n0(t.ntb), sub: 'new-to-brand customers',
      delta: chip(t.ntb, pt && pt.ntb, true), src: ch.src,
    }] : []));
  }

  // --- header, sortable -----------------------------------------------
  const st = adsState(channel, view);
  const th = document.getElementById(ch.host + '-thead');
  if (th) th.innerHTML = COLS.map(c => {
    const arrow = st.sortK === c.k ? (st.sortDir < 0 ? ' ▼' : ' ▲') : '';
    return `<th onclick="adsSortBy('${channel}','${c.k}','${view || ''}')" title="${esc2(c.tip || c.label)}"`
      + ` style="text-align:${c.align};padding:6px 8px;min-width:${c.w}px;cursor:pointer;`
      + `font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.5px;`
      + `color:var(--text3);border-bottom:1px solid var(--border2);white-space:nowrap">${c.label}${arrow}</th>`;
  }).join('');

  // --- rows -------------------------------------------------------------
  const q = (document.getElementById(ch.host + '-search')?.value || '').trim().toLowerCase();
  const showZero = !!document.getElementById(ch.host + '-zero')?.checked;
  let list = res.campaigns.filter(c => {
    if (!showZero && !(c.spend > 0)) return false;
    if (!q) return true;
    return (c.campaign + ' ' + c.type + ' ' + c.status).toLowerCase().indexOf(q) > -1;
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

  const RED = 'var(--sp-red,#d63f2a)';
  // ⚠ The NAME column is the view's own grouping key - 'campaign' on the
  // Campaigns view, 'term' on Keywords. Assuming 'campaign' put the dimmed
  // no-bucket treatment and the footer's row-count label on whichever column
  // happened to carry that name, which on Keywords is the campaign LIST.
  const NAMECOL = ch.groupBy || 'campaign';
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

  const tb = document.getElementById(ch.host + '-tbody');
  if (tb) {
    tb.innerHTML = list.length
      ? list.map(c => `<tr style="border-bottom:1px solid var(--border)">`
          + COLS.map(col => cellOf(c, col)).join('') + '</tr>').join('')
      : `<tr><td colspan="${COLS.length}" style="text-align:center;padding:24px;color:var(--text3);font-family:var(--mono);font-size:11px">`
        + (res.coverage.scanned
            ? 'No ' + (ch.noun || 'campaign') + 's with spend in this window.'
            : 'No ' + ch.label + ' data loaded yet — upload it from Data → Uploads.')
        + '</td></tr>';
  }
  // ⚠ The TOTAL row is KEYED off the same registry the header reads. A
  // hand-ordered footer slides every value under the wrong heading the moment
  // a column is added, silently — the v10.54 / v11.03 defect, twice already.
  const tf = document.getElementById(ch.host + '-tfoot');
  if (tf) {
    const shown = { ...t };
    // The footer totals WHAT IS ON SCREEN, so a search or a zero-spend filter
    // cannot leave a TOTAL describing rows the operator cannot see.
    if (q || !showZero) {
      const re = { impressions: 0, clicks: 0, spend: 0, orders: 0, sales: 0, units: 0, ntb: 0 };
      let hu = false, hn = false;
      for (const c of list) {
        re.impressions += c.impressions; re.clicks += c.clicks; re.spend += c.spend;
        re.orders += c.orders; re.sales += c.sales;
        if (c.units != null) { re.units += c.units; hu = true; }
        if (c.ntb   != null) { re.ntb   += c.ntb;   hn = true; }
      }
      Object.assign(shown, re);
      shown.skus = new Set(list.flatMap(c => [...c.skuSet])).size;
      shown.units = hu ? re.units : null;
      shown.ntb   = hn ? re.ntb   : null;
      shown.ctr  = adsDiv(shown.clicks, shown.impressions); if (shown.ctr != null) shown.ctr *= 100;
      shown.cpc  = adsDiv(shown.spend, shown.clicks);
      shown.cpa  = adsDiv(shown.spend, shown.orders);
      shown.roas = adsDiv(shown.sales, shown.spend);
      shown.acos = adsDiv(shown.spend, shown.sales); if (shown.acos != null) shown.acos *= 100;
    }
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
    tf.innerHTML = COLS.map(col => {
      if (col.k === NAMECOL) return `<td style="padding:6px 8px;text-align:left;font-family:var(--mono);font-size:11px;border-top:1px solid var(--border2)">${esc2(shown[NAMECOL])}</td>`;
      const c = cellOf(shown, col);
      return c.replace('<td', '<td').replace('style="padding:5px 8px', 'style="padding:6px 8px;border-top:1px solid var(--border2)');
    }).join('');
  }

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
  const val = (c, k) => {
    if (k === 'campaign' || k === 'type' || k === 'status') return c[k] || '';
    if (k === 'spend' || k === 'sales' || k === 'cpc' || k === 'cpa'
        || k === 'ctr' || k === 'acos' || k === 'roas') return f2(c[k]);
    return i0(c[k]);
  };
  const lines = [];
  // A file with no stated scope is unreadable three weeks later (v10.79).
  lines.push('# ' + ch.label + ' · campaign level');
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
    tb.innerHTML = `<tr><td colspan="${(ch.columns || ADS_COLUMNS[channel]).length}" style="text-align:center;padding:24px;color:var(--text3);font-family:var(--mono);font-size:11px">⏳ Loading ${ch.label}…</td></tr>`;
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
    if (tb) tb.innerHTML = `<tr><td colspan="${(ch.columns || ADS_COLUMNS[channel]).length}" style="text-align:center;padding:24px;color:var(--sp-red,#d63f2a);font-family:var(--mono);font-size:11px">✗ ${esc2(e.message || e)}</td></tr>`;
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
