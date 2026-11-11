const ADS_NO_CAMPAIGN = '(no campaign)';

// Amazon stores the ad product as a slug (v11.14's `_amzAdProduct`). This
// de-slugs it for display rather than carrying a hand-kept label map, so a new
// Amazon format that v11.14 passes through as its own slug shows up as itself
// instead of falling off a lookup.
// v11.25 - how a numeric column RENDERS, declared by the column and falling
// back to the pre-v11.25 key rule.
//
// /!\ v11.22 fixed the TEXT half of cellOf by looking at the value instead of
// a list of column names. The NUMERIC half cannot be fixed that way: 2.19 and
// 2 are both numbers, and the difference between a ratio and a count is a
// property of the MEASURE, not of the value. So the column declares it.
//
// Absent a declaration the old key rule applies verbatim, so every column that
// existed before v11.25 resolves exactly as it did - which is what makes
// "no existing table changed" a checkable claim rather than a read of a diff.
//   '$'  money, whole dollars with separators      '$2'  money, 2dp
//   '%'  percent, 1dp                              'x'   ratio, 2dp
//   'n'  count, rounded with separators
function adsColFmt(col) {
  if (col && col.fmt) return col.fmt;
  const k = col && col.k;
  if (k === 'spend' || k === 'sales') return '$';
  if (k === 'cpc' || k === 'cpa') return '$2';
  if (k === 'ctr' || k === 'acos') return '%';
  if (k === 'roas') return 'x';
  return 'n';
}

// ===========================================================================
// v11.52 - BREAK-EVEN ROAS, because 1.0 is the wrong line on a 1P channel
// ===========================================================================
// Jason: "i need to be able to analyze walmart.com ads and make decisions
// about what changes to make."
//
// ⚠ Walmart Connect reports ROAS on RETAIL sales. We are 1P: Walmart buys
// from us at wholesale and keeps the retail margin, so a dollar of reported
// ad sales is NOT a dollar of our revenue. Break-even is
//
//     1 / (our share of retail  x  our gross margin on wholesale)
//
// Measured on the live feeds for Kitty Ka-Zoom - 95% of Walmart ad spend -
// that is 1 / (0.526 x 0.592) = 3.21, not 1.00. Every Walmart ROAS between
// 1.00 and 3.21 was rendering as ordinary text while losing money.
//
// ⚠ DERIVED, NEVER TYPED. The share and the margin move as prices and COGS
// move, and a hardcoded 3.21 would be quietly wrong a quarter from now. It is
// read from walmart_sales_weekly x walmart_cost_per_each x product_cogs, the
// same three feeds the Walmart P&L uses.
//
// Amazon and Chewy keep a floor of 1.0: on those channels the reported sales
// ARE our revenue, so the old line is the right one. Absent an entry here a
// channel is byte-identical to v11.51.
let _adsBreakEven = {};

// The brand the ads panel is currently scoped to, or '' for all. The
// break-even differs materially by brand - Kitty Ka-Zoom keeps 52.6% of
// retail against 57.2% blended - so the floor follows the filter.
function adsBrandFilterValue(ch) {
  try { return (ch && typeof ch.brand === 'function') ? (ch.brand() || '') : ''; }
  catch (_) { return ''; }
}

function adsRoasFloor(channel, brand) {
  const be = _adsBreakEven[channel];
  if (!be || be.pending) return 1;
  const row = (brand && be.byBrand && be.byBrand[brand]) || be.overall;
  return (row && row.roas > 0) ? row.roas : 1;
}

// /!\ A FLOOR OF 1.0 IS THE FALLBACK, NOT AN ANSWER. adsLoadBreakEven fails
// to 1.0 on purpose, so that a derivation that could not run colours nothing.
// A `vs Break-Even` column therefore has to tell the two apart: without this
// it would report a confident gap measured against a line nobody computed,
// which is the one wrong answer here that looks like a real one.
function adsRoasFloorKnown(channel, brand) {
  const be = _adsBreakEven[channel];
  if (!be || be.pending) return false;
  const row = (brand && be.byBrand && be.byBrand[brand]) || be.overall;
  return !!(row && row.roas > 0);
}

// Stamp the gap onto already-derived rows. It cannot live in adsDeriveRow:
// that function has neither the channel nor the brand filter, and the floor
// depends on both.
//
// /!\ ONE NUMBER, EVERY CONSUMER. Stamped on `res` itself - which the export
// snapshot already holds by reference - so the table, the sort, the TOTAL row
// and the CSV cannot disagree about it (the v8.00 rule).
function adsStampBreakEven(rows, channel, brand) {
  const known = adsRoasFloorKnown(channel, brand);
  const floor = adsRoasFloor(channel, brand);
  for (const c of (rows || [])) {
    if (!c) continue;
    c.beRoas   = known ? floor : null;
    c.roasVsBe = (known && c.roas != null) ? c.roas - floor : null;
  }
}

function adsBreakEvenNote(channel, brand) {
  const be = _adsBreakEven[channel];
  if (!be || be.pending) return '';
  const row = (brand && be.byBrand && be.byBrand[brand]) || be.overall;
  if (!row || !(row.roas > 0)) return '';
  return `break-even ROAS ${row.roas.toFixed(2)}x`
    + ` (we keep ${row.sharePct.toFixed(0)}% of retail, ${row.gmPct.toFixed(0)}% GM on that)`;
}

// Only Walmart needs one today. The shape is per-channel so a second 1P
// channel does not need a second mechanism.
async function adsLoadBreakEven(channel) {
  if (channel !== 'walmart') { _adsBreakEven[channel] = { overall: null }; return; }
  if (_adsBreakEven[channel]) return;
  _adsBreakEven[channel] = { pending: true };
  try {
    const sb = await getSB();
    // ⚠ Share and margin are computed over the SAME joined rows. Taking the
    // share over all sell-through and the margin over the priced subset would
    // multiply two figures that describe different populations.
    const cogs = "coalesce(cg.landed_cost, cg.dtc_cogs, cg.amazon_cogs)";
    const sql = `select coalesce(p.brand, '') brand,
        sum(w.net_sales) retail,
        sum(w.units * c.cost_per_each) wholesale,
        sum(w.units * ${cogs}) cogs
      from public.walmart_sales_weekly w
      join public.walmart_cost_per_each c on c.master_id = w.master_id
      join public.product_cogs cg on cg.master_id = w.master_id
      left join public.products p on p.master_id = w.master_id
      where ${cogs} is not null and w.net_sales > 0
      group by 1`;
    const { data, error } = await sb.rpc('exec_sql', { query: sql });
    if (error) throw error;
    const mk = (retail, wholesale, cogs_) => {
      const sharePct = retail > 0 ? (wholesale / retail) * 100 : 0;
      const gmPct = wholesale > 0 ? ((wholesale - cogs_) / wholesale) * 100 : 0;
      const factor = (sharePct / 100) * (gmPct / 100);
      return factor > 0 ? { roas: 1 / factor, sharePct, gmPct } : null;
    };
    let R = 0, W = 0, C = 0;
    const byBrand = {};
    for (const r of (data || [])) {
      const retail = Number(r.retail) || 0, wholesale = Number(r.wholesale) || 0;
      const cg = Number(r.cogs) || 0;
      R += retail; W += wholesale; C += cg;
      const m = mk(retail, wholesale, cg);
      if (m && r.brand) byBrand[r.brand] = m;
    }
    _adsBreakEven[channel] = { overall: mk(R, W, C), byBrand };
  } catch (e) {
    // ⚠ Fail to 1.0 rather than to a guess. A break-even we could not compute
    // must not colour anything, and must not claim a line it does not know.
    console.warn('ads break-even unavailable for', channel, e?.message || e);
    _adsBreakEven[channel] = { overall: null };
  }
}

function adsFmtNum(v, fmt) {
  if (fmt === '$')  return '$' + Math.round(v).toLocaleString();
  if (fmt === '$2') return '$' + v.toFixed(2);
  if (fmt === '%')  return v.toFixed(1) + '%';
  if (fmt === 'x')  return v.toFixed(2) + 'x';
  // v11.59 - a SIGNED multiple. The sign is the whole message on a gap
  // column, and a bare "0.35x" beside a "2.50x" ROAS reads as another ratio.
  if (fmt === 'xs') return (v >= 0 ? '+' : '\u2212') + Math.abs(v).toFixed(2) + 'x';
  // v11.67 - a SIGNED two-decimal dollar, for a bid gap. Same reasoning as
  // 'xs' one line up: the sign is the message, and a bare "0.12" beside a
  // "$0.65" bid reads as another price rather than as a difference.
  if (fmt === '$2s') return (v >= 0 ? '+' : '\u2212') + '$' + Math.abs(v).toFixed(2);
  return Math.round(v).toLocaleString();
}

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
    // v11.28 - the control a clicked trend point writes back to. The SAME one
    // range() reads, named once rather than inferred twice.
    periodHost: 'pnl',
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
      inStoreSales: null,
      dpv: null,
      atc: null,
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
    periodHost: 'chpnl',
    // v11.25 - `this.host`, not a literal id. adsViewCfg returns an object
    // whose PROTOTYPE is the channel, so a view inherits this method and
    // `this.host` resolves to the VIEW's host. Chewy's host is already
    // `chads`, so the element id is unchanged.
    brandPicker: true,
    brand: function () { return document.getElementById(this.host + '-brand')?.value || ''; },
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
      inStoreSales: null,
      dpv: null,
      atc: null,
    }),
  },
  // ── v11.25 Walmart Connect ───────────────────────────────────────────
  // The third channel is an ADAPTER, not another renderer - which is what
  // the v11.16 design was for. It is the first one whose CAMPAIGN feed is
  // monthly, and the rollup already reads monthOf / inWindow off whatever
  // config a (channel, view) pair resolves to, so that costs nothing here.
  walmart: {
    label: 'Walmart Ads', icon: '\ud83d\udcef', host: 'wmads',
    // v12.07 - /!\ THE CHANNEL IS THE CAMPAIGN x DAY FEED NOW.
    // walmart_ad_campaign was monthly because its EXPORT carries no date at
    // all (v11.25) - the operator stamped a month at upload and nothing could
    // check it. The Custom report gives the same numbers with a real date per
    // row, so the monthly feed has no job left: its three settings columns
    // (daily budget, status, bidding strategy) are readable in Ad Center and
    // its history is re-pullable at day grain.
    //
    // Replaced rather than deleted, because this object is the PROTOTYPE every
    // Walmart view inherits - and being the channel is what makes Campaigns
    // the default tab with no view key, exactly like Amazon's.
    table: 'walmart_ad_campaign_daily',
    freshness: [{ label: 'Walmart Campaign \u00d7 Day', table: 'walmart_ad_campaign_daily', icon: '\ud83d\udce1' }],
    src: ['walmart_ad_campaign_daily'],
    dateField: 'date',
    rows: () => (typeof walmartAdCampaignDailyCache !== 'undefined' && walmartAdCampaignDailyCache) || [],
    load: () => (typeof loadWalmartAdCampaignDaily === 'function') ? loadWalmartAdCampaignDaily() : null,
    // The Walmart P&L's own period control, through its one resolver - the
    // same relationship the Amazon tab has with getPnlDateRange.
    range: () => (typeof getWalmartPnlDateRange === 'function') ? getWalmartPnlDateRange() : { from: null, to: null },
    periodHost: 'wmpnl',
    // v11.27 - NO brandPicker. The Walmart P&L's own page-level Brand control
    // scopes this tab, exactly as the Amazon adapter reads `pnl-brand` - the
    // page Jason named as the reference (rule #4). The shell used to emit a
    // second one in the control row, so picking a brand on Sales and
    // switching to Ads silently reset it.
    //
    // /!\ The options are the hardcoded three rather than adsFillBrands' read
    // of the data, which is DELIBERATE and matches Amazon. A brand we are not
    // advertising on Walmart now shows an empty table, which is a fact worth
    // seeing; the option quietly disappearing hid it.
    brand: () => document.getElementById('wmpnl-brand')?.value || '',
    // Walmart Connect is US-only here, so the Amazon region button must not
    // silently empty this table. Returning true is a DECISION, not a default.
    regionOk: () => true,
    // The Custom report has Campaign Type Name. It has no status column, so
    // Status would be a filter over empty strings (v10.19).
    filters: [{ k: 'type', label: 'Campaign type' }],

    // /!\ NO monthOf AND NO inWindow ANY MORE, and that is the whole point of
    // this release. `typeof ch.monthOf === 'function'` is what pinned every
    // Walmart ads chart to a monthly grain, refused the D and W buttons and
    // made the coverage line read "monthly grain". The rows carry a real date
    // now, so the default daily window compare on ch.dateField applies.

    // No budget and no bidding strategy in this export - they were the monthly
    // feed's. Declared empty rather than omitted: a view inheriting this
    // prototype must not pick up fields the rows do not have.
    stateFields: [],

    map: (r) => ({
      campaign: r.campaign || null,
      type:     r.campaign_type || '',
      status:   '',
      // Walmart puts the item dimension in a separate Item report, so there
      // is no SKU column here. Left null rather than faked.
      sku:      null,
      // /!\ FROM THE CAMPAIGN NAME at upload, not from Walmart's own Brand
      // dimension - which splits Sponsored Brand Video across the brand and an
      // `unknown` bucket, so it is not a key (v12.05).
      brand:    r.advertiser_brand || null,
      impressions: +r.impressions || 0,
      clicks:      +r.clicks || 0,
      spend:       +r.spend || 0,
      orders:      +r.orders || 0,
      units:       r.units == null ? null : +r.units || 0,
      sales:       +r.sales || 0,
      // /!\ NTB COUNTS ORDERS HERE AND CUSTOMERS ON CHEWY, so it is never
      // mapped onto `ntb` and its columns name their own operand (rule 3a).
      ntb:         null,
      signups:     null,
      ntbOrders:   r.ntb_orders == null ? null : +r.ntb_orders || 0,
      ntbSales:    r.ntb_sales  == null ? null : +r.ntb_sales  || 0,
      // /!\ null, not 0, when the column is absent - the has* flags in the
      // rollup are what keep an export without these from reading as
      // "nothing sold in store" / "nobody viewed the page".
      inStoreSales: r.in_store_sales == null ? null : +r.in_store_sales || 0,
      dpv:          r.dpv == null ? null : +r.dpv || 0,
      atc:          r.atc == null ? null : +r.atc || 0,
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
// v11.58 - ONE TEXT PER COLUMN. The Walmart ad columns are declared twice,
// once for the keyword table and once for the campaign table, and NINE of the
// fifteen shared columns had drifted to different wording - which is how In-Store $
// ended up with two tips and only one of them carrying the design commentary
// Jason objected to. Both registries read this now.
//
// /!\ A TOOLTIP EXPLAINS THE VALUE, NOT THE DESIGN DECISION. Jason: "explaining
// how the value is derived = good ... but the meta commentary is not". So these
// say what the number is, how it is derived and what is excluded from it, and
// never why the column exists or what it is not folded into. That reasoning
// belongs in a comment like this one.
//
// `campaign` is deliberately NOT here: on the keyword table it names the campaign
// a keyword spent under, on the campaign table it names the row itself.
const WM_ADS_TIP = {
  impressions:  'Impressions over the window.',
  clicks:       'Clicks over the window.',
  ctr:          'Clicks / Impressions.',
  cpc:          'Spend / Clicks.',
  spend:        'Ad Spend over the window.',
  orders:       'Ad-attributed ONLINE orders.',
  units:        'Ad-attributed ONLINE units.',
  cpa:          'Spend / Orders - what an attributed order cost.',
  cvr:          'Orders / Clicks.\n\nDerived from the window totals, never averaged across the per-row Conversion Rate the export carries - an average would weight a 3-click row the same as a 3,000-click one.',
  sales:        'Total Attributed Sales, ONLINE only (Walmart RETAIL dollars, not our revenue).',
  roas:         'Ad Sales / Spend. Online only - the same basis as Walmart\u2019s own RoAS column.',
  inStoreSales: 'In-Store Attributed Sales: physical-store purchases Walmart attributed back to an online ad click.',
  omniRoas:     '(Ad Sales + In-Store $) / Spend.\n\nA SECOND BASIS, not a better ROAS - a wider sales figure over the same spend. Derived from the window totals, never averaged across rows.',
  acos:         'Spend / Ad Sales. Online only.',
  roasVsBe:     'ROAS minus break-even ROAS, in ROAS points. Below zero the row spent more than the unit could pay back.\n\nBreak-even = 1 / (our share of Walmart retail \u00d7 our GM on that wholesale), derived per brand from walmart_sales_weekly, walmart_cost_per_each and product_cogs. Online basis, matching the ROAS column. Blank when the break-even could not be derived.',
};

// v12.03 - null stays null, a figure becomes a figure. `+null || 0` is 0,
// which on a sales column is the difference between "sold nothing" and "not
// reported" - the v11.16 distinction, in the one place a map is written.
function col0(v) { return v == null ? null : (+v || 0); }

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
        inStoreSales: null,
        dpv: null,
        atc: null,
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

  // ── v11.25 ──────────────────────────────────────────────────────────
  // Walmart DOES have keyword-level detail, which is why it gets this tab
  // and Chewy still does not: chewy_ad_spend goes campaign -> SKU -> day and
  // the vendor export has no keyword dimension to show.
  //
  // /!\ These are KEYWORDS (targets we bid on), not SEARCH TERMS (what the
  // customer typed). Amazon's view is the other one. The tab button says
  // Keywords on both because that is the level of detail it reaches, but the
  // noun and the column label say which of the two this actually is, so the
  // two tabs cannot be read as the same report.
  walmart: {
    keywords: {
      host: 'wmkw',
      label: 'Keywords',
      freshness: [{ label: 'Walmart Keywords', table: 'walmart_ad_keyword', icon: '\ud83d\udd11' }],
      src: ['walmart_ad_keyword'],
      rows: () => (typeof walmartAdKeywordCache !== 'undefined' && walmartAdKeywordCache) || [],
      load: () => (typeof loadWalmartAdKeyword === 'function') ? loadWalmartAdKeyword() : null,
      groupBy: 'term',
      noun: 'keyword',
      noneLabel: '(no keyword)',
      filters: [{ k: 'match', label: 'Match type' }, { k: 'campaign', label: 'Campaign' }],
      // v11.67 - the bid and Walmart's own suggestion are SETTINGS. See the
      // state block in adsCampaignRollup.
      stateFields: ['bid', 'suggestedBid'],

      // Monthly, for the same reason the campaigns feed is - one aggregate
      // per export, with the month supplied at upload.
      inWindow: (raw, from, to) => {
        const m = String(raw.reporting_month || '').slice(0, 7);
        if (!m) return false;
        if (from && m < String(from).slice(0, 7)) return false;
        if (to && m > String(to).slice(0, 7)) return false;
        return true;
      },
      monthOf: (raw) => String(raw.reporting_month || '').slice(0, 7),

      map: (r) => ({
        term:     String(r.keyword || '').trim() || null,
        match:    String(r.match_type || '').trim().toUpperCase(),
        campaign: String(r.campaign || '').trim(),
        adgroup:  String(r.ad_group || '').trim(),
        // v11.67 - the levers. All four are populated on every loaded row and
        // none of them was being rendered, so the table reported what the
        // keyword DID and showed nothing you could change about it.
        status:       String(r.status || '').trim(),
        bid:          r.bid == null ? null : +r.bid || 0,
        suggestedBid: r.suggested_bid == null ? null : +r.suggested_bid || 0,
        sku:      null,
        brand:    r.advertiser_brand || null,
        // /!\ A NEVER-SERVED KEYWORD HAS NULL METRICS, NOT ZERO - 132 of the
        // 189 rows in the September export are enabled targets that have not
        // delivered yet. They are kept because they are real targeting, and
        // they fall to 0 HERE because the table sums them; the uploader is
        // what preserves the null/0 distinction in the stored row.
        impressions: +r.impressions || 0,
        clicks:      +r.clicks || 0,
        spend:       +r.spend || 0,
        orders:      +r.orders || 0,
        units:       +r.units || 0,
        sales:       +r.sales || 0,
        ntb:         null,
        signups:     null,
        inStoreSales: r.in_store_sales == null ? null : +r.in_store_sales || 0,
        dpv:          r.dpv == null ? null : +r.dpv || 0,
        atc:          r.atc == null ? null : +r.atc || 0,
      }),

      columns: [
        { k: 'term',         label: 'Keyword',     align: 'left',  w: 260, tip: 'The keyword we bid on, from the Walmart Connect keyword export.\n\nThis is TARGETING, not the customer query - Walmart reports search terms separately. Amazon\u2019s equivalent tab shows the query side.' },
        { k: 'match',        label: 'Match',       align: 'left',  w: 84,  tip: 'EXACT / PHRASE / BROAD. Several when one keyword is targeted more than one way in the window.' },
        { k: 'campaign',     label: 'Campaign',    align: 'left',  w: 200, tip: 'The campaign the keyword spent under. Several when one keyword runs in more than one.' },
        { k: 'adgroup',      label: 'Ad Group',    align: 'left',  w: 160, tip: 'The ad group the keyword sits in. Several when one keyword runs in more than one.' },
        { k: 'status',       label: 'Status',      align: 'left',  w: 92,  tip: 'The keyword\u2019s own status, from the Walmart Connect keyword export.\n\n\u26a0 The status WHEN THE FILE WAS DOWNLOADED, not during the period it reports. Several when it differed across the periods in the window.' },
        { k: 'bid',          label: 'Bid',         align: 'right', w: 76,  fmt: '$2', tip: 'What we bid on this keyword.\n\n\u26a0 A SETTING, not a total: the newest period in the window, never the sum or the average of the periods in it.' },
        { k: 'suggestedBid', label: 'Suggested',   align: 'right', w: 92,  fmt: '$2', tip: 'Walmart Connect\u2019s own suggested bid for this keyword, from the same export.\n\nNewest period in the window, like Bid beside it.' },
        { k: 'bidVsSugg',    label: 'vs Suggested', align: 'right', w: 112, fmt: '$2s', tip: 'Bid minus Suggested, in dollars.\n\nNegative means we are bidding under Walmart\u2019s suggestion. Blank when either side is missing.' },
        { k: 'impressions',  label: 'Impressions', align: 'right', w: 104, tip: WM_ADS_TIP.impressions },
        { k: 'clicks',       label: 'Clicks',      align: 'right', w: 80,  tip: WM_ADS_TIP.clicks },
        { k: 'ctr',          label: 'CTR %',       align: 'right', w: 72,  tip: WM_ADS_TIP.ctr },
        { k: 'cpc',          label: 'CPC',         align: 'right', w: 72,  tip: WM_ADS_TIP.cpc },
        { k: 'spend',        label: 'Spend',       align: 'right', w: 96,  tip: WM_ADS_TIP.spend },
        { k: 'orders',       label: 'Orders',      align: 'right', w: 76,  tip: WM_ADS_TIP.orders },
        { k: 'units',        label: 'Units',       align: 'right', w: 72,  tip: WM_ADS_TIP.units },
        { k: 'cvr',          label: 'CVR %',       align: 'right', w: 76,  tip: WM_ADS_TIP.cvr },
        { k: 'cpa',          label: 'CPA',         align: 'right', w: 76,  tip: WM_ADS_TIP.cpa },
        { k: 'sales',        label: 'Ad Sales',    align: 'right', w: 104, tip: WM_ADS_TIP.sales },
        { k: 'roas',         label: 'ROAS',        align: 'right', w: 76,  tip: WM_ADS_TIP.roas },
        { k: 'inStoreSales', label: 'In-Store $',  align: 'right', w: 96,  fmt: '$',  tip: WM_ADS_TIP.inStoreSales },
        { k: 'omniRoas',     label: 'Omni ROAS',   align: 'right', w: 88,  fmt: 'x',  tip: WM_ADS_TIP.omniRoas },
        { k: 'acos',         label: 'ACOS %',      align: 'right', w: 80,  tip: WM_ADS_TIP.acos },
        { k: 'roasVsBe',     label: 'vs Break-Even', align: 'right', w: 116, fmt: 'xs',  tip: WM_ADS_TIP.roasVsBe },
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
    { k: 'campaign',    label: 'Campaign',    align: 'left',  w: 260, tip: 'Amazon Ads campaign name, from the unified report\'s Campaign name dimension.\n\n"(no campaign)" is spend uploaded without the Campaign name dimension. Amazon cannot retrofit it onto a past pull, so re-upload the window to fill it in.' },
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
  // ── v11.25 Walmart. Its own names, because Walmart's console is what Jason
  // reconciles this table against - and three of these measures (Page Views,
  // Add to Cart, In-Store $) do not exist on the other two channels at all.
  walmart: [
      { k: 'campaign',     label: 'Campaign',    align: 'left',  w: 240, tip: 'Walmart Connect campaign name, from the Custom report.\n\n\u26a0 The NAME is the key here, not the id - the export carries no Campaign Id. A renamed campaign starts a new row.' },
      { k: 'type',         label: 'Type',        align: 'left',  w: 170, tip: 'Sponsored Products (Auto) / Sponsored Products (Manual) / Sponsored Videos, as Walmart names them.' },
      { k: 'impressions',  label: 'Impressions', align: 'right', w: 104, tip: WM_ADS_TIP.impressions },
      { k: 'clicks',       label: 'Clicks',      align: 'right', w: 80,  tip: WM_ADS_TIP.clicks },
      { k: 'ctr',          label: 'CTR %',       align: 'right', w: 72,  tip: WM_ADS_TIP.ctr },
      { k: 'cpc',          label: 'CPC',         align: 'right', w: 72,  tip: WM_ADS_TIP.cpc },
      { k: 'spend',        label: 'Spend',       align: 'right', w: 96,  tip: WM_ADS_TIP.spend },
      // v12.06 - the funnel, per campaign per day. Impressions -> Clicks ->
      // Page Views -> Add to Cart -> Orders on one row.
      { k: 'dpv',          label: 'Page Views',  align: 'right', w: 92,  tip: 'Total Product Detail Page Views driven by the ad, at the file\u2019s attribution window.\n\n\u26a0 Settles upward for a day or two: the newest day in an export can report 0 against real clicks.' },
      { k: 'atc',          label: 'Add to Cart', align: 'right', w: 96,  tip: 'Total Add To Cart events driven by the ad.\n\nWith Page Views beside it this puts the whole funnel on one row: Impressions \u2192 Clicks \u2192 Page Views \u2192 Add to Cart \u2192 Orders.' },
      { k: 'orders',       label: 'Orders',      align: 'right', w: 76,  tip: WM_ADS_TIP.orders },
      { k: 'units',        label: 'Units',       align: 'right', w: 72,  tip: WM_ADS_TIP.units },
      { k: 'cvr',          label: 'CVR %',       align: 'right', w: 76,  tip: WM_ADS_TIP.cvr },
      { k: 'cpa',          label: 'CPA',         align: 'right', w: 76,  tip: WM_ADS_TIP.cpa },
      { k: 'sales',        label: 'Ad Sales',    align: 'right', w: 104, tip: WM_ADS_TIP.sales },
      { k: 'roas',         label: 'ROAS',        align: 'right', w: 76,  tip: WM_ADS_TIP.roas },
      { k: 'ntbOrders',    label: 'NTB Orders',  align: 'right', w: 96,  tip: 'New-to-brand orders at the file\u2019s attribution window.\n\n\u26a0 ORDERS, not customers. The Chewy tab\u2019s NTB column counts CUSTOMERS, so this one is named for its own operand rather than borrowing that word.' },
      { k: 'ntbSales',     label: 'NTB $',       align: 'right', w: 92,  fmt: '$', tip: 'Sales from new-to-brand orders, at the file\u2019s attribution window.' },
      { k: 'inStoreSales', label: 'In-Store $',  align: 'right', w: 96,  fmt: '$',  tip: WM_ADS_TIP.inStoreSales },
      { k: 'omniRoas',     label: 'Omni ROAS',   align: 'right', w: 88,  fmt: 'x',  tip: WM_ADS_TIP.omniRoas },
      { k: 'acos',         label: 'ACOS %',      align: 'right', w: 80,  tip: WM_ADS_TIP.acos },
      { k: 'roasVsBe',     label: 'vs Break-Even', align: 'right', w: 116, fmt: 'xs',  tip: WM_ADS_TIP.roasVsBe },
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
  // v11.25 - OMNI ROAS is a SECOND basis, not a better ROAS. Walmart
  // attributes in-store purchases back to an online click, so Omni divides
  // (online + in-store) sales by the same spend while `roas` stays online
  // only. Two scopes, two names, per rule 3a - and `Omni ROAS` is Walmart's
  // own word for it, reused rather than coined (rule #3).
  //
  // /!\ Derived from the SUMMED totals like every other ratio here, never
  // averaged across the per-row Omni ROAS the export carries.
  c.omniRoas = c.hasInStore ? adsDiv((c.sales || 0) + (c.inStoreSales || 0), c.spend) : null;
  // v11.67 - the bid gap. Null unless BOTH sides are known: a keyword with no
  // suggested bid has no gap, and rendering one as 0.00 would read as "we are
  // exactly on Walmart's number". Every channel that maps neither field gets
  // null from the same line, so this is a no-op off Walmart.
  c.bidVsSugg = (c.bid != null && c.suggestedBid != null) ? c.bid - c.suggestedBid : null;
  if (!c.hasUnits)   c.units        = null;
  if (!c.hasNtb)     c.ntb          = null;
  if (!c.hasInStore) c.inStoreSales = null;
  if (!c.hasNtbOrders) { c.ntbOrders = null; c.ntbSales = null; }
  if (!c.hasFunnel) { c.dpv = null; c.atc = null; }
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
              ntb: 0, signups: 0, inStoreSales: 0, dpv: 0, atc: 0,
              hasUnits: false, hasNtb: false, hasInStore: false, hasFunnel: false,
              firstDate: '', lastDate: '' };
  for (const c of (rows || [])) {
    t.impressions += c.impressions; t.clicks += c.clicks; t.spend += c.spend;
    t.orders += c.orders; t.sales += c.sales; t.signups += (c.signups || 0);
    if (c.units != null) { t.units += c.units; t.hasUnits = true; }
    if (c.ntb   != null) { t.ntb   += c.ntb;   t.hasNtb   = true; }
    if (c.inStoreSales != null) { t.inStoreSales += c.inStoreSales; t.hasInStore = true; }
    if (c.dpv != null || c.atc != null) {
      t.dpv += (c.dpv || 0); t.atc += (c.atc || 0); t.hasFunnel = true;
    }
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
// v11.74 - the WIDTH rule moved to pnlGrainAuto and the OVERRIDE arrives
// with it, so these charts gained the control for free. The Walmart feed is
// stamped per MONTH (v11.67), so it declares monthly and the resolver
// refuses anything finer rather than inventing a week it does not have.
// The ONE sentence for a refused ads grain, so both readings say it the same
// way. Walmart Connect exports carry NO reporting date - the uploader asks
// which month a file covers and stamps every row with it (v11.67) - so there
// is no day or week underneath to group by.
function _adsGrainWhy(ch) {
  return (ch && typeof ch.monthOf === 'function')
    ? 'Walmart Connect files carry no reporting date, so every row is stamped with the MONTH the file covers (v11.67). There is no finer grain underneath.'
    : 'These rows do not carry that grain.';
}
function adsGrainAllowed(ch) {
  return (ch && typeof ch.monthOf === 'function') ? ['month'] : PNL_GRAIN_ORDER;
}
function adsGrain(win, ch) {
  return pnlGrainResolve(win, adsGrainAllowed(ch));
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
  ntbOrders: { unit: '#', sum: s => s.ntbOrders },
  ntbSales:  { unit: '$', sum: s => s.ntbSales },
  // v12.02 - /!\ THE ONLY METRIC HERE WHOSE DENOMINATOR IS NOT IN THE ADS
  // FEED. `netSales` is attached per bucket from sku_economics, and it is
  // attached ONLY when this metric is actually plotted - see the chart's
  // metric branch. A bucket with no sales is a GAP, never 0% (the v11.16
  // rule): 0.0% TACoS would mean "sold plenty, spent nothing", which is a
  // different fact from having no sales figure for that week at all.
  tacos: { unit: '%', isPct: true, noStack: true, needsNetSales: true,
           sum: s => { const v = adsDiv(s.spend, s.netSales); return v == null ? null : v * 100; } },
};
function adsChartMetrics(COLS, channel) {
  const out = (COLS || []).filter(c => ADS_METRIC_SPEC[c.k])
    .map(c => Object.assign({ k: c.k, label: c.label }, ADS_METRIC_SPEC[c.k]));
  // v12.02 - /!\ TACoS IS NOT A COLUMN AND CANNOT BE ONE. Sales are not
  // attributable to a campaign, so there is no per-row TACoS to put in the
  // table - but there IS a per-WEEK one, because spend and net sales are both
  // weekly. It is appended for the one channel that has a total-sales feed
  // behind it rather than derived from COLS like the rest.
  if (channel === 'amazon') {
    out.push(Object.assign({ k: 'tacos', label: 'TACoS %' }, ADS_METRIC_SPEC.tacos));
  }
  return out;
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
            // v11.25 - Walmart only. Amazon and Chewy map these to null, so
            // the has* flags stay false and adsDeriveRow nulls them back out.
            inStoreSales: 0, dpv: 0, atc: 0,
            // v12.05 - Walmart's campaign x day feed. Their own slots rather
            // than `ntb`, which on Chewy counts CUSTOMERS (rule 3a).
            ntbOrders: 0, ntbSales: 0,
            hasUnits: false, hasNtb: false, hasInStore: false, hasFunnel: false,
            hasNtbOrders: false,
            firstDate: d, lastDate: d };
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
    if (r.inStoreSales != null) { c.inStoreSales += r.inStoreSales; c.hasInStore = true; }
    if (r.ntbOrders != null || r.ntbSales != null) {
      c.ntbOrders += (r.ntbOrders || 0); c.ntbSales += (r.ntbSales || 0);
      c.hasNtbOrders = true;
    }
    if (r.dpv != null || r.atc != null) {
      c.dpv += (r.dpv || 0); c.atc += (r.atc || 0); c.hasFunnel = true;
    }
    if (d && d < c.firstDate) c.firstDate = d;
    if (d && d > c.lastDate)  c.lastDate  = d;
    // v11.67 - /!\ A BID IS A STATE, NOT A FLOW. Every other number here is
    // something that HAPPENED over the window and sums; a bid, a suggested
    // bid and a daily budget are what the setting IS. Summing three months of
    // a $0.65 bid into $1.95 reports a number nobody ever bid, and averaging
    // it reports one nobody can act on. The NEWEST period in the window wins,
    // because that is the only one still standing.
    //
    // Declared per view, so a channel that declares none is byte-identical.
    if (ch.stateFields && d && (!c._stateAt || d >= c._stateAt)) {
      c._stateAt = d;
      for (const k of ch.stateFields) c[k] = r[k];
    }
    if (bucketOf) {
      const bk = bucketOf(raw, d);
      if (bk) {
        bucketsSeen.add(bk);
        const byB = series[name] || (series[name] = {});
        const sl = byB[bk] || (byB[bk] = { impressions: 0, clicks: 0, spend: 0,
                                           orders: 0, units: 0, sales: 0, ntb: 0, signups: 0,
                                           inStoreSales: 0, dpv: 0, atc: 0,
                                           ntbOrders: 0, ntbSales: 0 });
        sl.impressions += r.impressions; sl.clicks += r.clicks; sl.spend += r.spend;
        sl.orders += r.orders; sl.sales += r.sales;
        sl.units += (r.units || 0); sl.ntb += (r.ntb || 0); sl.signups += (r.signups || 0);
        sl.inStoreSales += (r.inStoreSales || 0); sl.dpv += (r.dpv || 0); sl.atc += (r.atc || 0);
        sl.ntbOrders += (r.ntbOrders || 0); sl.ntbSales += (r.ntbSales || 0);
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

// ===========================================================================
// v11.67 - WHERE A CAMPAIGN NAME GOES WHEN YOU CLICK IT
// ===========================================================================
// Jason: "when i click on a campaign name, can that open to the keywords and
// products view? currently it just selects the row - but that is what the
// checkbox is for."
//
// DECLARED per channel, never inferred, because the journey needs four things
// to be true at once and only a declaration can state them: a view that lists
// something below campaign level, a `campaign` filter on that view to receive
// the pick, the raw column that filter reads, and the channel's own sub-tab
// switcher to get there.
//
// /!\ CHEWY HAS NO ENTRY AND GETS NO LINK. Its feed goes campaign -> promoted
// SKU -> day with no keyword dimension at all (v11.22), so there is no view to
// open. A link that cannot honour itself is the v10.19 defect.
//
// /!\ AND NEITHER CHANNEL GETS A PRODUCTS LINK. Walmart has exactly two ad
// tables and neither carries an item dimension - Walmart reports items in a
// separate export we do not load - so a Products view would be a missing FEED
// dressed up as a missing screen.
const ADS_DRILL = {
  walmart: { view: 'keywords', filter: 'campaign', rawCol: 'campaign',      go: 'switchWalmartAdsView' },
  amazon:  { view: 'keywords', filter: 'campaign', rawCol: 'campaign_name', go: 'switchPnlAdsView' },
};

// The campaign names the destination can ACTUALLY show, in this window and
// under this brand - or null while its feed has not loaded yet.
//
// /!\ THIS IS THE HALF THAT MATTERS, and the live data says why: Walmart's
// biggest spender is `SP - AUTO - CATCH ALL - Kitty` at $1,903 in October, and
// an auto campaign has no keyword rows at all. Linking it would land you on an
// empty table having told you nothing. It renders as plain text, with the
// reason on its tooltip.
//
// Scoped to the SAME window and brand the Campaigns table is showing, so the
// link cannot be offered for a campaign the destination would then filter
// away - which would leave the control saying one thing and the table another.
const _adsDrillNames = {};
function adsDrillNames(channel, from, to, brand) {
  const d = ADS_DRILL[channel];
  if (!d) return null;
  const cfg = adsViewCfg(channel, d.view);
  if (!cfg || typeof cfg.rows !== 'function') return null;
  const rows = cfg.rows();
  if (!rows || !rows.length) return null;
  const sig = [channel, from || '', to || '', brand || '', rows.length].join('|');
  const memo = _adsDrillNames[channel];
  if (memo && memo.sig === sig) return memo.set;
  const out = new Set();
  for (const raw of rows) {
    if (typeof cfg.inWindow === 'function' && !cfg.inWindow(raw, from, to)) continue;
    if (brand && String(cfg.map(raw).brand || '') !== brand) continue;
    const v = String(raw[d.rawCol] == null ? '' : raw[d.rawCol]).trim();
    if (v) out.add(v);
  }
  _adsDrillNames[channel] = { sig, set: out };
  return out;
}

// /!\ The pick is carried in STATE rather than written onto the control,
// because the control has no options yet: they are built by the very render
// the drill is about to trigger, and the loop that builds them resets a value
// it does not recognise (v11.02). renderAdsCampaigns consumes this once.
let _adsPendingFilter = null;
const _adsDrillLoading = {};

// Addressed by INDEX into the rows AS RENDERED - the v11.23 rule. A campaign
// name is an arbitrary string; interpolating one into an onclick attribute
// breaks on the first apostrophe and is an injection waiting to happen.
function adsDrillOpen(channel, i) {
  const d = ADS_DRILL[channel];
  if (!d) return;
  const name = adsSelName(channel, undefined, i);
  if (!name) return;
  _adsPendingFilter = { channel, view: d.view, k: d.filter, v: name };
  const go = window[d.go];
  if (typeof go !== 'function') { _adsPendingFilter = null; return; }
  try { go(d.view); } catch (e) { _adsPendingFilter = null; console.warn('[ads] drill failed', e); }
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
  if (_adsState[k]) return _adsState[k];
  // v12.03 - a view may declare the column it OPENS on. The Walmart Daily
  // view is a list of days, and a list of days ranked by spend is a league
  // table of dates - not a question anyone has. Every existing view declares
  // none and keeps 'spend' descending, so nothing that exists today moves.
  let cfg = null;
  try { cfg = (typeof adsViewCfg === 'function') ? adsViewCfg(channel, view) : null; } catch (_) {}
  return (_adsState[k] = {
    sortK: (cfg && cfg.defaultSort) || 'spend',
    sortDir: (cfg && cfg.defaultSortDir) || -1,
    sel: new Set(),
  });
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
// v11.33 - the adverb for a bucket grain. `grain + 'ly'` gives weekly and
// monthly and **dayly**, which the Campaigns reading has rendered since
// v11.23. One helper, so the Metrics reading added beside it cannot ship a
// second copy of the same typo (hard rule #1).
// v11.74 - renamed from adsGrainAdv: the grain is a chart-wide concept now,
// not an Ads one, and a shared idea must not keep a tab's prefix (rule #3).
function pnlGrainAdv(grain) {
  return grain === 'day' ? 'daily' : grain === 'week' ? 'weekly'
       : grain === 'month' ? 'monthly' : (grain + 'ly');
}

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

// v11.33 - WHICH METRICS ARE PLOTTED, per (channel, view). The Amazon
// console's shape, which Jason named as the reference (rule #4): the
// scorecards are the series toggles.
//
// Capped at FOUR. One axis per metric is what makes the overlay readable at
// all - spend and sales share a unit and not a magnitude - and four axes is
// what a 340px plot can label without the ticks colliding. The fifth card's
// control renders DISABLED and says why, rather than accepting a click and
// silently dropping it (the v10.19 rule).
const ADS_CHART_MAX = 4;
const ADS_CHART_DEFAULT = ['spend', 'sales'];
const _adsChartSel = {};
const _adsChartBy = {};
function adsChartSel(channel, view) {
  const k = _adsKey(channel, view);
  return _adsChartSel[k] || (_adsChartSel[k] = new Set(ADS_CHART_DEFAULT));
}
function adsChartBy(channel, view) { return _adsChartBy[_adsKey(channel, view)] || 'metric'; }
// v12.03 - /!\ A FEED WITH ONE ADVERTISER HAS NOTHING TO BAND.
// The Campaigns reading splits ONE metric into a line per selected row. On a
// view whose rows are DAYS that would draw one single-point line per day,
// along an axis that is already the days - the same reading, scattered. The
// view declares why, the control renders disabled carrying that sentence, AND
// the resolver clamps, because a disabled button is bypassable from the
// console (the v11.74 rule, applied to the other chart control).
function adsBandWhy(ch) {
  const w = ch && ch.bandWhy;
  return (typeof w === 'function') ? (w() || '') : (w || '');
}
function adsChartByResolve(ch, channel, view) {
  const by = adsChartBy(channel, view);
  return (by === 'campaign' && adsBandWhy(ch)) ? 'metric' : by;
}
function adsSetChartBy(channel, view, by) {
  _adsChartBy[_adsKey(channel, view)] = (by === 'campaign') ? 'campaign' : 'metric';
  renderAdsCampaigns(channel, view);
}
function adsToggleChartMetric(channel, view, k) {
  const sel = adsChartSel(channel, view);
  if (sel.has(k)) sel.delete(k);
  else if (sel.size < ADS_CHART_MAX) sel.add(k);
  else return;                 // belt and braces: the control is already disabled
  renderAdsCampaigns(channel, view);
}
// The colour a metric is drawn in, FIXED PER METRIC KEY rather than taken by
// position in the selection. Toggling one series off must not recolour the
// others, and a card's lit edge has to match its own line on the chart - one
// concept, one colour (rule #2).
const ADS_METRIC_COLOR = {
  spend: '#6366f1', sales: '#06b6d4', roas: '#a855f7', acos: '#4a9e38',
  clicks: '#f97316', orders: '#eab308', impressions: '#3b82f6',
  ctr: '#ec4899', cvr: '#84cc16', cpc: '#f59e0b', cpa: '#ef4444',
  units: '#14b8a6', ntb: '#d946ef', omniRoas: '#8b5cf6', inStoreSales: '#0ea5e9',
  dpv: '#64748b', atc: '#22c55e',
  ntbOrders: '#be185d', ntbSales: '#0d9488',
  // v12.02 - TACoS is ACOS's sibling (same question, two denominators)
  // but deliberately NOT a shade of ACOS's green: two greens on one
  // chart are hard to tell apart, and both are good-when-down, so the
  // pairing has to come from the labels rather than from the hue.
  tacos: '#92400e',
};
function adsMetricColor(k, i) {
  return ADS_METRIC_COLOR[k] || ADS_CHART_COLORS[(i || 0) % ADS_CHART_COLORS.length];
}

// The chart's two readings, as one segmented control in the panel header -
// the same shape and the same slot as the Line / Stacked toggle it sits
// beside. Each of the other controls is shown only where it bites: the Metric
// picker and the Line / Stacked toggle both belong to the Campaigns reading.
function adsInjectChartBy(ch, channel, view, by) {
  const host = document.getElementById(ch.host + '-chart-by-host');
  if (host) {
    const bandWhy = adsBandWhy(ch);
    const btn = (v, label, tip, dis) => {
      const on = !dis && by === v;
      // /!\ Disabled, not hidden - a toggle that vanishes on one tab reads as
      // a bug, and the onclick is STRIPPED rather than left to be ignored.
      return `<button type="button"${dis ? ' disabled' : ` onclick="adsSetChartBy('${channel}','${view || ''}','${v}')"`} title="${esc2(tip)}"`
        + ` style="padding:3px 9px;font-size:10px;font-family:var(--display);font-weight:${on ? 700 : 600};`
        + `background:${on ? 'var(--sp-green)' : 'transparent'};color:${on ? '#fff' : 'var(--text2)'};`
        + `opacity:${dis ? '.45' : '1'};border:none;border-radius:4px;cursor:${dis ? 'not-allowed' : 'pointer'}">${label}</button>`;
    };
    host.innerHTML = '<span style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">Compare</span>'
      + '<span style="display:inline-flex;gap:2px;background:var(--surface2);border:1px solid var(--border2);border-radius:5px;padding:2px">'
      + btn('metric', 'Metrics', 'Several metrics over time, each on its own axis. Use the + on a scorecard above to add or remove one.')
      + btn('campaign', 'Campaigns',
            bandWhy || 'One metric over time, split into a line per selected row. Tick rows in the table below.',
            !!bandWhy)
      + '</span>';
  }
  // v10.19 - a control that cannot bite is hidden, not left looking live.
  const mw = document.getElementById(ch.host + '-chart-metric-wrap');
  if (mw) mw.style.display = (by === 'campaign') ? 'inline-flex' : 'none';
  const mh = document.getElementById(ch.host + '-chart-mode-host');
  if (mh && by !== 'campaign') mh.innerHTML = '';
}
function adsUpdateChart(ctx) {
  const { ch, channel, view, COLS, res, win, list, sel, grain, totals, prev } = ctx;
  const panel = document.getElementById(ch.host + '-chart-panel');
  if (!panel) return;
  const key = _adsKey(channel, view);
  const hide = () => {
    panel.style.display = 'none';
    if (_adsChartInstance[key]) { try { _adsChartInstance[key].destroy(); } catch (e) {} _adsChartInstance[key] = null; }
  };
  const metrics = adsChartMetrics(COLS, channel);
  // v11.33 - which reading the panel is showing. Injected on every paint, like
  // the Line / Stacked toggle, because the shell is built once and only
  // repainted afterwards.
  const by = adsChartByResolve(ch, channel, view);
  adsInjectChartBy(ch, channel, view, by);
  const picked = (document.getElementById(ch.host + '-chart-metric') || {}).value || 'spend';
  const m = metrics.find(x => x.k === picked) || metrics.find(x => x.k === 'spend') || metrics[0];
  if (!m && by === 'campaign') return hide();
  const NAMECOL = ch.groupBy || 'campaign';
  const selectionActive = !!(sel && sel.size);
  // No selection -> ONE total line across the rows on screen, which is the
  // question you have before you have clicked anything (the v10.12 default).
  const names = selectionActive
    ? res.campaigns.filter(c => sel.has(c[NAMECOL])).map(c => c[NAMECOL])
    : list.map(c => c[NAMECOL]);
  const buckets = res.buckets || [];
  if (!names.length || !buckets.length) return hide();
  // The window facts both readings state identically, resolved once so the two
  // cannot describe the same chart differently (v10.99).
  const edgeNotes = (typeof ch.monthOf === 'function' ? [] : adsBucketEdges(buckets, grain, win))
    .concat((typeof ch.monthOf !== 'function' && totals && totals.lastDate && win.to && totals.lastDate < win.to)
      ? ['data through ' + totals.lastDate] : []);
  const subFrom = (typeof ch.monthOf === 'function' ? buckets[0] : (win.from || 'start'));
  const subTo   = (typeof ch.monthOf === 'function' ? buckets[buckets.length - 1] : (win.to || 'today'));
  const titleEl0 = document.getElementById(ch.host + '-chart-title');
  const subEl0   = document.getElementById(ch.host + '-chart-sub');

  if (by === 'metric') {
    const want = adsChartSel(channel, view);
    // Ordered by the REGISTRY, not by the order they were clicked, so the
    // legend and the axes keep a stable order across toggles.
    const plot = metrics.filter(x => want.has(x.k)).slice(0, ADS_CHART_MAX);
    // The per-bucket TOTAL across the names on screen (or the selection),
    // summed from the SAME slots the table rolled up and the ratio derived
    // ONCE per bucket - never averaged across campaigns, which would weight a
    // $2 campaign the same as a $20,000 one (the v11.23 rule, per bucket).
    const perB = buckets.map(b => {
      const acc = { impressions: 0, clicks: 0, spend: 0, orders: 0, units: 0,
                    sales: 0, ntb: 0, signups: 0, inStoreSales: 0, dpv: 0, atc: 0,
                    ntbOrders: 0, ntbSales: 0 };
      for (const nm of names) {
        const sl = (res.series || {})[nm] && res.series[nm][b];
        if (!sl) continue;
        for (const kk in acc) acc[kk] += (sl[kk] || 0);
      }
      return acc;
    });
    // v12.02 - /!\ THE DENOMINATOR IS FETCHED PER BUCKET, BY SPAN, NOT BY KEY.
    // An ads bucket is keyed on the SUNDAY; sku_economics stores the same week
    // under its MONDAY. Joining the two strings would have put every week's
    // sales against the previous week's spend. pnlBucketRange turns the bucket
    // into its own date span and amzFeeAgg - the SAME aggregator the scorecard
    // uses, so the card and the line cannot disagree - sums the weeks inside it.
    //
    // Only when TACoS is actually on the chart: this is a full scan of
    // sku_economics per bucket, and no other metric needs it.
    if (plot.some(x => x.needsNetSales) && typeof amzFeeAgg === 'function') {
      buckets.forEach((b, i) => {
        const r = (typeof pnlBucketRange === 'function') ? pnlBucketRange(b, grain) : null;
        if (!r) return;
        try {
          const a = amzFeeAgg(r);
          if (a && a.tot) perB[i].netSales = a.tot.netSales || 0;
        } catch (e) { /* leave it absent - the metric draws a gap, not a zero */ }
      });
    }
    const datasets = plot.map((x, i) => {
      const col = adsMetricColor(x.k, i);
      return { label: x.label, yAxisID: 'y_' + x.k, borderColor: col, backgroundColor: col,
               // A bucket with no denominator is a GAP, never a zero - 0.00x
               // ROAS means spent and returned nothing, which is a different
               // fact from having spent nothing at all (the v11.16 argument).
               data: perB.map(a => x.sum(a)), spanGaps: false,
               borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: .25, fill: false };
    });
    const axes = plot.map((x, i) => ({ id: 'y_' + x.k, unit: x.unit, isPct: !!x.isPct,
                                       color: adsMetricColor(x.k, i) }));
    if (titleEl0) titleEl0.textContent = 'Metrics \u00b7 ' + pnlGrainAdv(grain) + ' trend';
    if (subEl0) subEl0.textContent = pnlTrendSubtitle({
      selectionActive, midCount: names.length, bandCount: 0,
      buckets: buckets.length, from: subFrom, to: subTo, mode: 'line',
      // An empty selection is STATED rather than left as a blank plot: the
      // toggles live on the cards above, so a chart that just vanished would
      // leave nothing on screen explaining how to get it back.
      extra: plot.length
        ? (plot.map(x => x.label).join(' + ') + ' \u00b7 own axis each')
        : 'no metric plotted \u00b7 use + on a scorecard above',
      note: edgeNotes.filter(Boolean).join(' \u00b7 '),
      bucketNoun: grain, noun: ch.noun || 'campaign',
    });
    panel.style.display = 'block';
    // v11.68 - /!\ this reading never re-injected the toggle at all, so it
    // sat showing whatever the CAMPAIGN reading had last written. Harmless
    // while the only control was View; with a Compare button beside it that
    // is a live control doing nothing, which is the v10.19 case.
    //
    // It is always a line (each metric gets its OWN axis, so there is nothing
    // to stack), and a single dashed line cannot say which of several metrics
    // it is the previous period OF - so both are reported as unavailable with
    // the reason rather than left to look live.
    pnlInjectChartModeToggle(ch.host + '-chart-mode-host', '_adsRe_' + ch.host, true,
      undefined, { ok: false,
        why: 'Each metric is on its own axis here, so one comparison line could not say which metric it belongs to. Switch to the per-' + (ch.noun || 'campaign') + ' reading to compare.' },
      { win, allowed: adsGrainAllowed(ch), why: _adsGrainWhy(ch) });
    pnlTrendRender({
      canvasId: ch.host + '-chart-canvas', instance: _adsChartInstance[key], periodHost: ch.periodHost,
      buckets, datasets, mode: 'line', axes,
    }).then(inst => { _adsChartInstance[key] = inst; })
      .catch(e => console.warn('ads trend chart:', (e && e.message) || e));
    return;
  }

  const built = pnlTrendSeries({
    perProd: res.series || {}, buckets, mids: names, metricOf: m.sum,
    colors: ADS_CHART_COLORS, mode: pnlChartMode(),
    isPct: !!m.isPct, noStack: !!m.noStack, selectionActive,
    noun: ch.noun || 'campaign', otherNoun: (ch.noun || 'campaign') + 's',
    labelOf: n => n,
  });
  // v11.68 - the previous period, over the SAME names and the SAME metric.
  // `prev` is the rollup the delta chips already read, so the dashed line and
  // the chips above it cannot describe different windows - and it is bucketed
  // by the same grain this chart resolved, so the two series are comparable
  // bucket for bucket.
  //
  // /!\ Offered only when there IS a prior rollup. A window with no block
  // before it (All time, or a monthly view with no earlier months loaded)
  // leaves the control disabled with the reason rather than live and inert.
  const _adsCmpOk = !!(prev && prev.buckets && prev.buckets.length);
  const _adsCmpOn = _adsCmpOk && pnlChartCompare();
  pnlInjectChartModeToggle(ch.host + '-chart-mode-host', '_adsRe_' + ch.host, !!m.noStack,
    undefined, { ok: _adsCmpOk,
      why: 'No earlier block of the same length is loaded to compare this window against.' },
    { win, allowed: adsGrainAllowed(ch), why: _adsGrainWhy(ch) });
  if (_adsCmpOn) {
    const _ov = pnlPrevOverlay(pnlPrevVals(prev.series || {}, prev.buckets, names, m.sum),
                               buckets, prev.buckets);
    if (_ov) built.datasets.push(_ov);
  }
  // v11.69 - the same legend rule, on the same mechanism. A band here is a
  // campaign or a keyword rather than a product; the mapping is the renderer's
  // either way.
  const _adsSync = _adsCmpOn
    ? pnlMakeOverlaySync({ bandMids: built.bandMids, prevPerProd: prev.series || {},
                           prevBuckets: prev.buckets, curBuckets: buckets,
                           metricOf: m.sum, baseMids: names })
    : null;
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
  if (titleEl) titleEl.textContent = m.label + ' · ' + pnlGrainAdv(grain) + ' trend';
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
    canvasId: ch.host + '-chart-canvas', instance: _adsChartInstance[key], periodHost: ch.periodHost,
    buckets, datasets: built.datasets, mode: built.mode,
    isPct: !!m.isPct, unit: m.unit,
  }).then(inst => { _adsChartInstance[key] = inst;
                    if (inst) inst.$overlaySync = _adsSync; })
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
  // v11.25 - declared by the channel and keyed on the HOST, like every other
  // control this shell emits. The old form wrote `chads-brand` and
  // `renderAdsCampaigns('chewy')` in literally, so a view of the same channel
  // would have emitted a duplicate id wired to re-render a different tab.
  const brandPicker = ch.brandPicker
    ? `<select id="${ch.host}-brand" onchange="renderAdsCampaigns('${channel}','${view || ''}')" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:4px 8px"><option value="">All Brands</option></select>`
    : '';
  host.innerHTML =
      `<div id="${ch.host}-freshness" style="margin-bottom:10px"></div>`
    + `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px">`
    +   `<input type="text" id="${ch.host}-search" placeholder="Search…" title="Matches any text column on this table." oninput="adsSearchChanged('${channel}','${view || ''}')" autocomplete="off" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:5px 10px;width:260px">`
    +   brandPicker
    +   filterPickers
    +   `<label style="font-family:var(--mono);font-size:11px;color:var(--text2);cursor:pointer" title="Campaigns with no spend in this window.">`
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
    +         `<span id="${ch.host}-chart-by-host" style="display:inline-flex;gap:6px;align-items:center"></span>`
    +         `<span id="${ch.host}-chart-mode-host" style="display:inline-flex;gap:6px;align-items:center"></span>`
    // v11.33 - the Metric picker belongs to the Campaigns reading only, so it
    // is wrapped in a span the renderer shows and hides as a unit. The LABEL
    // went inside it too: v11.19 shipped exactly this bug the other way round,
    // hiding a search input and leaving its label as dead furniture.
    +         `<span id="${ch.host}-chart-metric-wrap" style="display:none;gap:6px;align-items:center">`
    +           `<span style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">Metric</span>`
    +           `<select id="${ch.host}-chart-metric" onchange="renderAdsCampaigns('${channel}','${view || ''}')" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:4px 8px;outline:none">`
    +             adsChartMetrics(COLS, channel).map(m => `<option value="${m.k}"${m.k === 'spend' ? ' selected' : ''}>${esc2(m.label)}</option>`).join('')
    +           `</select>`
    +         `</span>`
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

// ===========================================================================
// v12.00 - TACoS on the Ads tab: ad spend over TOTAL sales.
//
// /!\ ONE DEFINITION, NOT A SECOND SPELLING. `TACoS` already exists on the
// P&L Page Performance tile as `ad spend / net sales` (renderPnlPerformance).
// This is that same measure on this tab's scope. Rule 3a: one label, one
// measure - so the arithmetic here is deliberately identical and the suite
// pins the two together.
//
// /!\ IT CANNOT BE DERIVED FROM SKU ECONOMICS ALONE, and that was the
// question. That feed carries `sponsored_products_total` and nothing else
// about ads. Measured on the live table, US, trailing 90 days:
//
//     sponsored_products  $44,250  |  sponsored_display  $1,753
//     sponsored_brands    $10,337  |  sponsored_tv       $1,739
//
// SP is 76% of spend, so an SP-only TACoS reads 12.4% against a real 16.5%
// over 12 full weeks - it would hide a quarter of the spend, silently, on
// the one card whose job is to say what advertising costs in total.
// The numerator is this tab's Ad Spend, which is every ad product.
//
// /!\ THE DENOMINATOR IS WEEKLY AND THE NUMERATOR IS DAILY. amzFeeAgg sums
// sku_economics rows whose week_start falls in the window, so a window that
// does not start on a Monday buys whole weeks only. The card says which days
// its sales actually cover rather than implying they match the ad window.
// Proration is NOT used: it would invent daily sales these feeds do not
// carry, which is the rule v11.74 set.
//
// Returns { pct, netSales, why } - `pct` null means NO ANSWER, and `why`
// says which of the four reasons it is. A wrong TACoS is worse than none.
// ===========================================================================
function adsTacosFor(channel, selRows, spend, range) {
  const no = (why) => ({ pct: null, netSales: null, why });

  // Only the Amazon tab has a total-sales feed behind it on this page.
  if (channel !== 'amazon') {
    return no('TACoS needs this channel\u2019s total sales, and only Amazon carries them on this page.');
  }
  // v11.xx standing gap: no UK/EU Amazon ad spend is loaded, so an EU TACoS
  // would divide a blank by a real number and read 0.0%.
  if (typeof pnlRegion !== 'undefined' && pnlRegion === 'EU') {
    return no('No EU Amazon ad spend is loaded, so an EU TACoS would read 0.0% against real sales.');
  }
  // /!\ A CAMPAIGN SELECTION CANNOT NARROW THE SALES SIDE. Organic sales do
  // not belong to a campaign. Dividing a few campaigns' spend by the whole
  // catalogue's sales reads far too low, and it would move every time a row
  // is ticked - a card that appears to answer a control it cannot honour is
  // the v10.19 defect.
  if (selRows && selRows.length) {
    return no('Organic sales do not belong to a campaign, so selecting campaigns cannot narrow the sales side. Clear the selection for TACoS.');
  }
  if (typeof amzFeeAgg !== 'function') return no('Sales totals are not loaded yet.');
  // /!\ NO RANGE, NO ANSWER. amzFeeAgg falls back to getPnlDateRange() when
  // it is handed nothing, which would measure sales over a DIFFERENT window
  // than the ad spend sitting beside it on the same strip - two windows in
  // one ratio, with nothing on screen saying so.
  if (!range || !range.from || !range.to) {
    return no('This window has no date range, so TACoS cannot match its sales to its spend.');
  }

  let agg = null;
  try { agg = amzFeeAgg(range); } catch (e) { return no('Sales totals could not be read: ' + e.message); }
  const ns = (agg && agg.tot) ? (agg.tot.netSales || 0) : 0;
  if (!(ns > 0)) {
    return no('No net sales in this window, so TACoS has no denominator. Widen the period.');
  }
  return { pct: (spend || 0) / ns * 100, netSales: ns, from: agg.from, to: agg.to, why: null };
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
  // v11.67 - the drill, on the CAMPAIGNS view only: `drill` is what this table
  // can offer, `drillNames` is what the destination can honour.
  const drill = (!view && ADS_DRILL[channel]) ? ADS_DRILL[channel] : null;
  const drillNames = drill ? adsDrillNames(channel, win.from, win.to, brand) : null;
  // The destination feed is what decides whether a name is a link, so it has
  // to be in hand. Fired ONCE per channel per session; until it lands every
  // name renders as plain text, which is the honest state rather than a link
  // we cannot yet promise to honour.
  if (drill && !drillNames && !_adsDrillLoading[channel]) {
    const dcfg = adsViewCfg(channel, drill.view);
    if (dcfg && typeof dcfg.load === 'function') {
      _adsDrillLoading[channel] = true;
      Promise.resolve(dcfg.load())
        .then(() => renderAdsCampaigns(channel, view))
        .catch(console.warn);
    }
  }
  // Read the filter strip into the {dimension: Set} shape the rollup takes.
  const picked = {};
  // v11.67 - a drill-in arrives BEFORE this view's filter control has options,
  // so its pick is applied to the ROLLUP here and written onto the control in
  // the options loop below. One render, no re-entry.
  const pend = (_adsPendingFilter && _adsPendingFilter.channel === channel
                && (_adsPendingFilter.view || '') === (view || '')) ? _adsPendingFilter : null;
  for (const f of (ch.filters || [])) {
    const v = (document.getElementById(ch.host + '-f-' + f.k) || {}).value || '';
    if (v) picked[f.k] = new Set([v]);
  }
  if (pend) picked[pend.k] = new Set([pend.v]);
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
    // A pending drill-in wins over whatever the control was left on.
    const keep = (pend && pend.k === f.k) ? pend.v : sel.value;
    const next = '<option value="">All</option>'
      + opts.map(v => `<option value="${esc2(v)}">${esc2(v)}</option>`).join('');
    if (sel.innerHTML !== next) sel.innerHTML = next;
    // A stored pick the window no longer contains falls back to All rather
    // than leaving the control on a value the table cannot show (v11.02).
    sel.value = opts.includes(keep) ? keep : '';
  }
  // Consumed, whether or not it landed - a pick that outlived its render would
  // re-apply itself on the next repaint and the filter could never be cleared.
  if (pend) _adsPendingFilter = null;
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
      prev = adsCampaignRollup({ channel, view, from: adsYmd(pFrom), to: adsYmd(pTo), brand, filters: picked, bucket: grain });
    }
  } else if (win.from && win.to && !win.allTime) {
    const d0 = new Date(win.from + 'T00:00:00'), d1 = new Date(win.to + 'T00:00:00');
    const len = Math.round((d1 - d0) / 86400000) + 1;
    if (len > 0) {
      const pTo = new Date(d0.getTime() - 86400000);
      const pFrom = new Date(pTo.getTime() - (len - 1) * 86400000);
      prev = adsCampaignRollup({ channel, view, from: adsYmd(pFrom), to: adsYmd(pTo), brand, filters: picked, bucket: grain });
    }
  }
  // The export reads this SNAPSHOT, never a recompute (the v8.00 rule), so
  // the selection has to ride along with it.
  _adsExport[_adsKey(channel, view)] = { res, win, brand, channel, view,
    sel: [...adsState(channel, view).sel] };

  // v11.59 - resolved against adsBrandFilterValue(ch), the SAME expression
  // the sub-floor red colour uses, so the column and the colour can never
  // disagree about which break-even applies.
  adsStampBreakEven(res.campaigns, channel, adsBrandFilterValue(ch));
  if (res.totals) adsStampBreakEven([res.totals], channel, adsBrandFilterValue(ch));

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
  // v11.71 - the shared comparator. The null rule lives in tableSortCmp now,
  // so the Fees table cannot disagree with this one about where a blank goes.
  list = list.slice().sort(tableSortCmp(st.sortK, st.sortDir));
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

  // v11.33 - every metric card is a chart toggle, built from the metric list
  // the CHART itself reads. A card and its series therefore cannot name the
  // same number differently (rule 3a), and a card whose metric the chart
  // cannot plot gets no control at all rather than a dead one.
  const chartBy = adsChartByResolve(ch, channel, view);
  const plotSel = adsChartSel(channel, view);
  const plotMetrics = adsChartMetrics(COLS, channel);
  const colLabel = (k, dflt) => (COLS.find(c => c.k === k) || {}).label || dflt;
  const colTip = (k) => (COLS.find(c => c.k === k) || {}).tip;
  const plotOf = (k) => {
    if (chartBy !== 'metric') return null;     // v10.19 - no control where it cannot bite
    const mi = plotMetrics.findIndex(x => x.k === k);
    if (mi < 0) return null;
    const on = plotSel.has(k);
    const full = !on && plotSel.size >= ADS_CHART_MAX;
    // v12.02 - /!\ TACoS HAS TWO STATES THE OTHER METRICS DO NOT.
    // Both render the button DISABLED with the reason on it rather than
    // hiding it, because a toggle that silently vanishes on some grains
    // reads as a bug; and pnlCard strips the onclick when disabled, so a
    // refused control cannot be clicked through.
    if (k === 'tacos') {
      if (grain === 'day') {
        return { on, disabled: true, color: adsMetricColor(k, mi), onclick: '',
                 tip: 'SKU Economics is stamped one row per WEEK, so there is no daily sales figure to divide spend by. Switch GROUP to W or M.' };
      }
      if (sel && sel.size) {
        return { on, disabled: true, color: adsMetricColor(k, mi), onclick: '',
                 tip: 'Organic sales do not belong to a campaign, so a selection cannot narrow the sales side. Clear the selection to plot TACoS.' };
      }
    }
    return {
      on, disabled: full, color: adsMetricColor(k, mi),
      onclick: `adsToggleChartMetric('${channel}','${view || ''}','${k}')`,
      tip: full ? ('Four metrics is the most the chart can label at once. Switch one off first.')
                : (on ? 'Remove this line from the chart below.'
                      : 'Add this line to the chart below, on its own axis.'),
    };
  };

  // v12.00 - TACoS, on the SCOPE total `t` rather than on the selection-aware
  // `cardT`: the denominator cannot be narrowed to selected campaigns, so the
  // numerator must not be either (adsTacosFor refuses outright when rows are
  // selected, and this keeps the two sides describing one population).
  // v12.01 - /!\ getPnlPrevDateRange(cur) REQUIRES the current range; it reads
  // `cur.from` on its third line. v12.00 called it with no argument, so every
  // render of this tab threw `Cannot read properties of undefined (reading
  // 'from')` before a single card was drawn - the TACoS card took down the six
  // that have nothing to do with it.
  //
  // /!\ SO THE WHOLE COMPUTATION IS GUARDED, not just the call that was wrong.
  // A scorecard must not be able to destroy the page it sits on: a throw in
  // here now costs this one card its number and nothing else, and the reason
  // lands on its tooltip rather than in the console.
  let tacos = { pct: null, why: 'TACoS could not be computed for this window.' };
  let tacosPrev = { pct: null };
  try {
    const tacosRange = (win && win.from && win.to) ? { from: win.from, to: win.to } : null;
    tacos = adsTacosFor(channel, selRows, t && t.spend, tacosRange);
    if (!selRows && prev && tacosRange && typeof getPnlPrevDateRange === 'function') {
      tacosPrev = adsTacosFor(channel, null, pt && pt.spend, getPnlPrevDateRange(tacosRange));
    }
  } catch (e) {
    console.warn('TACoS card:', e && e.message);
    tacos = { pct: null, why: 'TACoS could not be computed: ' + (e && e.message) };
    tacosPrev = { pct: null };
  }

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
        color: 'var(--sp-red)', delta: chip(cardT.spend, pt && pt.spend, null), src: ch.src,
        tip: colTip('spend'), plot: plotOf('spend') },
      { label: colLabel('sales', 'Ad Sales'), val: $0(cardT.sales),
        sub: 'attributed to a click', delta: chip(cardT.sales, pt && pt.sales, true), src: ch.src,
        tip: colTip('sales'), plot: plotOf('sales') },
      { label: colLabel('roas', 'ROAS'),
        val: cardT.roas == null ? '—' : cardT.roas.toFixed(2) + 'x',
        // ⚠ The ACOS that used to live on this line now has its own card
        // one slot over, because the console Jason named shows it as its own
        // tile AND because only a card can carry the chart toggle. Repeating
        // it here would be the same number twice, a card apart.
        sub: cardT.roas == null ? 'no attributed sales' : '',
        color: cardT.roas == null ? 'var(--text3)' : (cardT.roas >= 1 ? 'var(--sp-green)' : 'var(--sp-red)'),
        delta: chip(cardT.roas, pt && pt.roas, true), src: ch.src,
        tip: colTip('roas'), plot: plotOf('roas') },
      // ⚠ ACOS is the one card here that is GOOD WHEN DOWN, and the only
      // one whose chip passes goodWhenUp=false. It is also a percentage, so
      // the delta is in POINTS - a 40% to 30% move is 10 points, not -25%.
      { label: colLabel('acos', 'ACOS %'),
        val: cardT.acos == null ? '—' : cardT.acos.toFixed(1) + '%',
        sub: cardT.acos == null ? 'no attributed sales' : '',
        color: cardT.acos == null ? 'var(--text3)' : (cardT.acos > 100 ? 'var(--sp-red)' : 'var(--text)'),
        delta: chip(cardT.acos, pt && pt.acos, false, true), src: ch.src,
        tip: colTip('acos'), plot: plotOf('acos') },
      // v12.00 - /!\ TACoS sits beside ACOS because they are the same
      // question asked of two denominators: ACOS is spend over AD-ATTRIBUTED
      // sales, TACoS is spend over ALL sales. Good when DOWN, like ACOS, and
      // reported in POINTS for the same reason.
      { label: 'Clicks', val: n0(cardT.clicks),
        sub: (cardT.ctr == null ? '—' : cardT.ctr.toFixed(2) + '% CTR') + ' · ' + (cardT.cpc == null ? '—' : '$' + cardT.cpc.toFixed(2) + ' CPC'),
        delta: chip(cardT.clicks, pt && pt.clicks, true), src: ch.src,
        tip: colTip('clicks'), plot: plotOf('clicks') },
    // v12.03 - /!\ GATED ON THE COLUMN REGISTRY, which is already what
    // declares whether a feed reports orders at all. The Walmart Daily export
    // carries neither orders nor units, so `cardT.orders` accumulates to 0 and
    // this card would have read "0 - no attributed orders": a measured-looking
    // zero for something nobody measured, which is the v11.16 rule and the
    // v10.19 confident-wrong-answer in one card. All five existing views
    // declare an orders column, so not one of them moves.
    // v12.07 - /!\ ONLY ON THE CHANNEL THAT CAN COMPUTE IT.
    // adsTacosFor refuses every channel but Amazon, so on Walmart and
    // Chewy this card rendered a permanent dash - with `amazon_ad_spend`
    // and `sku_economics` chips under it, naming another channel's feeds
    // on this page. Gated on the same channel the helper accepts, so the
    // two cannot disagree about where it belongs.
    ].concat(channel === 'amazon' ? [{
      label: 'TACoS %',
      val: tacos.pct == null ? '—' : tacos.pct.toFixed(1) + '%',
      sub: tacos.pct == null
        ? 'not available'
        : 'of $' + Math.round(tacos.netSales).toLocaleString() + ' net sales',
      color: tacos.pct == null ? 'var(--text3)'
           : (tacos.pct > 30 ? 'var(--sp-red)' : tacos.pct > 20 ? 'var(--sp-orange)' : 'var(--text)'),
      delta: (tacos.pct == null || tacosPrev.pct == null) ? null
           : chip(tacos.pct, tacosPrev.pct, false, true),
      src: ['amazon_ad_spend', 'sku_economics'],
      plot: plotOf('tacos'),
      tip: tacos.pct == null
        ? tacos.why
        : ('Total Advertising Cost of Sales: ad spend \u00f7 net sales, every ad product '
           + '(Sponsored Products, Brands, Display and TV), not just the ad-attributed '
           + 'half that ACOS uses.\n\nSales come from SKU Economics, which is stamped one '
           + 'row per WEEK, so this window\u2019s sales cover ' + tacos.from + ' to ' + tacos.to
           + ' \u2014 whole weeks only. Nothing is prorated, because these feeds carry no '
           + 'daily sales to prorate with.'),
    }] : []).concat(COLS.some(c => c.k === 'orders') ? [{
      label: colLabel('orders', 'Orders'), val: n0(cardT.orders),
      sub: cardT.cpa == null ? 'no attributed orders' : '$' + cardT.cpa.toFixed(2) + ' per order',
      delta: chip(cardT.orders, pt && pt.orders, true), src: ch.src,
      tip: colTip('orders'), plot: plotOf('orders'),
    }] : []).concat(channel === 'chewy' ? [{
      label: 'NTB', val: n0(cardT.ntb), sub: 'new-to-brand customers',
      delta: chip(cardT.ntb, pt && pt.ntb, true), src: ch.src,
      tip: colTip('ntb'), plot: plotOf('ntb'),
    }] : []));
  }

  // --- header, sortable -----------------------------------------------
  // The select-all checkbox leads the row, like the Summary table's.
  const selAllTh = `<th style="text-align:center;padding:6px 6px;width:30px;border-bottom:1px solid var(--border2)" title="Select every row currently visible, or clear them."><input type="checkbox" id="${ch.host}-selall" onclick="adsToggleAllVisible('${channel}','${view || ''}')" style="cursor:pointer;margin:0;vertical-align:middle"></th>`;
  const th = document.getElementById(ch.host + '-thead');
  if (th) th.innerHTML = selAllTh + COLS.map(c => {
    const arrow = tableSortArrow(st.sortK === c.k, st.sortDir);
    return `<th onclick="adsSortBy('${channel}','${c.k}','${view || ''}')" title="${esc2(c.tip || c.label)}"`
      + ` style="text-align:${c.align};padding:6px 8px;min-width:${c.w}px;cursor:pointer;`
      + `font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.5px;`
      + `color:var(--text3);border-bottom:1px solid var(--border2);white-space:nowrap">${c.label}${arrow}</th>`;
  }).join('');

  // --- rows -------------------------------------------------------------
  const RED = 'var(--sp-red,#d63f2a)';
  const cellOf = (c, col, i) => {
    const v = c[col.k];
    const pad = `padding:5px 8px;text-align:${col.align};white-space:nowrap`;
    if (col.k === NAMECOL) {
      // The no-campaign bucket is DIMMED AND NAMED, not hidden, and says why.
      const dim = c.noCampaign ? ';color:var(--text3);font-style:italic' : '';
      // v11.67 - the drill, offered ONLY where the destination can honour it.
      // The footer calls cellOf with no index and therefore never drills.
      const canDrill = !!(drill && drillNames && i >= 0 && !c.noCampaign
                          && drillNames.has(c[NAMECOL]));
      const tip = c.noCampaign
        ? ' title="Spend uploaded before the Campaign name column existed. Re-upload this window from Amazon Ads → Reports with Campaign name as a dimension to fill it in."'
        : canDrill
          ? ` title="${esc2(c[NAMECOL])}\nOpen this campaign's keywords."`
          : (drill && drillNames)
            ? ` title="${esc2(c[NAMECOL])}\nNo rows for this campaign in the Keywords feed over this window, so there is nothing below it to open."`
            : ` title="${esc2(c[NAMECOL])}"`;
      const body = canDrill
        ? `<span onclick="event.stopPropagation();adsDrillOpen('${channel}',${i})"`
          + ` style="cursor:pointer;border-bottom:1px dotted var(--text3)"`
          + ` onmouseover="this.style.color='var(--sp-green)'"`
          + ` onmouseout="this.style.color=''">${esc2(c[NAMECOL])}</span>`
        : esc2(c[NAMECOL]);
      return `<td${tip} style="${pad};max-width:${col.w}px;overflow:hidden;text-overflow:ellipsis${dim}">${body}</td>`;
    }
    // ⚠ TEXT IS DETECTED BY VALUE, NOT BY A LIST OF COLUMN NAMES. The old
    // check named campaign / type / status and sent everything else to the
    // numeric formatter, so a view with its own text columns rendered
    // Math.round('catnip spray') - NaN, in the first column of the table.
    if (typeof v === 'string' || col.k === 'type' || col.k === 'status') {
      return `<td style="${pad};font-family:var(--mono);font-size:10px;color:var(--text3)">${esc2(v || '—')}</td>`;
    }
    if (v == null) return `<td style="${pad};color:var(--text3)">—</td>`;
    // v11.25 - the column's declared format, defaulting to the old key rule.
    const F = adsColFmt(col);
    const out = adsFmtNum(v, F);
    // /!\ The sub-1 warning follows the resolved FORMAT, not the literal key
    // 'roas', so a second ratio column turns red for the same reason the
    // first one does. Among the pre-v11.25 registries only `roas` resolves to
    // 'x', so this is a no-op for every existing table.
    // v11.52 - against the CHANNEL'S break-even, not a flat 1.0. On Amazon
    // and Chewy the floor is still 1.0 and this is a no-op; on Walmart 1P a
    // 2.50x is a loss and now reads as one.
    // v11.59 - a gap column IS the comparison, so its own threshold is zero.
    // Reusing the 'x' rule would test the gap against the break-even itself.
    const warn = (F === 'xs' && v < 0)
      || (F === 'x' && v < adsRoasFloor(channel, adsBrandFilterValue(ch)))
      || (F === '%' && col.k === 'acos' && v > 100);
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
            + COLS.map(col => cellOf(c, col, i)).join('') + '</tr>';
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
    adsUpdateChart({ ch, channel, view, COLS, res, win, list, sel, grain, totals: t, prev });
  } catch (e) { console.warn('ads trend chart:', (e && e.message) || e); }

  // v11.52 - derive the break-even once per channel, then repaint so the
  // colouring and the coverage line pick it up. Guarded on the cache entry,
  // so this cannot loop: the entry is set to {pending} before the await.
  if (_adsBreakEven[channel] === undefined) {
    adsLoadBreakEven(channel).then(() => {
      try { renderAdsCampaigns(channel, view); } catch (_) {}
    });
  }

  const cov = document.getElementById(ch.host + '-cov');
  if (cov) {
    const parts = [];
    // v11.52 - a threshold nobody can see is a threshold nobody can act on.
    const beNote = adsBreakEvenNote(channel, adsBrandFilterValue(ch));
    if (beNote) parts.push(beNote);
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
    // v12.03 - /!\ A VIEW THAT CANNOT HONOUR THE PAGE'S BRAND CONTROL SAYS SO.
    // The Walmart Daily feed is an ACCOUNT TOTAL with no campaign dimension,
    // so picking Doggijuana cannot narrow it. Reporting the whole account
    // while a brand sits selected one row above would be a confident wrong
    // answer (v10.19) - the one failure this line exists to prevent.
    if (typeof ch.brandless === 'function') {
      const bn = ch.brandless();
      if (bn) parts.push(bn);
    } else if (brand) parts.push(brand);
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
  // v11.59 - the DECIMAL rule now comes from adsColFmt, the same resolver the
  // table uses, rather than from a hardcoded key list. That list was missing
  // `omniRoas`, so Walmart's Omni ROAS exported as a rounded integer - 2.08x
  // written as "2" - while the table rendered it right. Exactly the defect the
  // comment above describes, one column over.
  const val = (c, col) => {
    const k = col.k, v = c[k];
    if (typeof v === 'string') return v;
    if (v == null) return '';
    const F = adsColFmt(col);
    return (F === '$' || F === '$2' || F === '%' || F === 'x' || F === 'xs')
      ? f2(v) : i0(v);
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
  for (const c of res.campaigns) lines.push(COLS.map(col => esc(val(c, col))).join(','));
  lines.push(COLS.map((col, i) => i === 0 ? 'TOTAL' : esc(val(res.totals, col))).join(','));

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
      adsFillBrands(channel, view);
    }
    if (channel === 'walmart') {
      // v12.07 - the channel declares its own `load` now (campaign x day), so
      // the branch above has already run it and there is no second feed to
      // fetch here. Only the brand picker is Walmart's own.
      adsFillBrands(channel, view);
    }
    renderAdsCampaigns(channel, view);
  } catch (e) {
    if (tb) tb.innerHTML = `<tr><td colspan="${(ch.columns || ADS_COLUMNS[channel]).length + 1}" style="text-align:center;padding:24px;color:var(--sp-red,#d63f2a);font-family:var(--mono);font-size:11px">✗ ${esc2(e.message || e)}</td></tr>`;
  }
}

// The Chewy brand picker is filled from the DATA, not a hardcoded list, so an
// advertiser account that appears later shows up with no code change.
// v11.25 - was adsFillChewyBrands, with Chewy's element id and its raw column
// name both written in. Walmart needs the same control, and a second copy is
// the divergence hard rule #1 exists to stop.
//
// /!\ The options come through the adapter's OWN map, never off a raw column.
// The table filters on `map(r).brand`, so reading a different field here is
// exactly how a picker comes to offer a value that matches no row. On Walmart
// the raw column would be the ACCOUNT, which is "Kitty Ka-Zoom (SmarterPaw
// LLC)" and carries Doggijuana campaigns inside it.
function adsFillBrands(channel, view) {
  const ch = adsViewCfg(channel, view);
  if (!ch) return;
  const sel = document.getElementById(ch.host + '-brand');
  if (!sel) return;
  const keep = sel.value;
  const names = [...new Set((ch.rows() || [])
    .map(r => String(ch.map(r).brand || '').trim()).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">All Brands</option>'
    + names.map(n => `<option value="${esc2(n)}">${esc2(n)}</option>`).join('');
  if (keep && names.includes(keep)) sel.value = keep;
}



// Amazon: two campaigns, one of them under TWO ad products, plus legacy rows
// with no campaign at all (the pre-v11.15 shape).
const AMZ = [
  { date:'2026-10-01', region:'US', campaign:'SP - Exact',  ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:1000, clicks:50, spend:10, purchases:5, attributed_sales:100 },
  { date:'2026-10-02', region:'US', campaign:'SP - Exact',  ad_product:'sponsored_brands',
    asin:'B1', master_id:'M1', impressions:2000, clicks:50, spend:20, purchases:5, attributed_sales:100 },
  { date:'2026-10-02', region:'US', campaign:'SB - Defense', ad_product:'sponsored_brands',
    asin:'B2', master_id:'M2', impressions:1000, clicks:0,  spend:20, purchases:0, attributed_sales:0 },
  // legacy: no campaign, and it is the BIGGEST spender in the window
  { date:'2026-10-03', region:'US', campaign:null, ad_product:'sponsored_display',
    asin:'B3', master_id:'M3', impressions:6000, clicks:100, spend:450, purchases:10, attributed_sales:300 },
  // outside the window - must not be counted at all
  { date:'2026-09-01', region:'US', campaign:'SP - Exact',  ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:9999, clicks:999, spend:999, purchases:99, attributed_sales:999 },
];

const CHW = [
  { date:'2026-10-01', advertiser:'Kitty Ka-Zoom', campaign:'KKZ Max', campaign_type:'Chewy Max',
    campaign_status:'Active', chewy_sku:'S1', impressions:5000, clicks:100, spend:50,
    direct_units:20, total_orders:10, direct_sales:200, ntb_customers:8, autoship_signups:3 },
  { date:'2026-10-02', advertiser:'Kitty Ka-Zoom', campaign:'KKZ Max', campaign_type:'Chewy Max',
    campaign_status:'Active', chewy_sku:'S2', impressions:5000, clicks:100, spend:50,
    direct_units:10, total_orders:5, direct_sales:100, ntb_customers:2, autoship_signups:1 },
  { date:'2026-10-02', advertiser:'Meowijuana', campaign:'Meowi SP', campaign_type:'Sponsored Product',
    campaign_status:'Paused', chewy_sku:'S3', impressions:1000, clicks:10, spend:5,
    direct_units:1, total_orders:1, direct_sales:9, ntb_customers:1, autoship_signups:0 },
];
const W = { from:'2026-10-01', to:'2026-10-31' };
const run = (channel, rows, extra) => adsCampaignRollup(Object.assign(
  { channel, rows, from: W.from, to: W.to, regionOk: false }, extra || {}));


const out = {};
const a = run('amazon', AMZ);
const c = run('chewy', CHW);

out.amzNames = a.campaigns.map(x => x.campaign).sort();
out.amzCount = a.coverage.campaignCount;          // NAMED campaigns only
out.amzRows  = a.campaigns.length;                 // including the bucket
out.amzSpend = a.totals.spend;
out.amzNoCampSpend = a.coverage.noCampaignSpend;
out.amzNoCampPct   = +a.coverage.noCampaignPct.toFixed(2);

// one campaign spanning TWO ad products collects both
const exact = a.campaigns.find(x => x.campaign === 'SP - Exact');
out.exactType  = exact.type;
out.exactSpend = exact.spend;
out.exactSkus  = exact.skus;
out.exactRoas  = exact.roas;
out.exactCtr   = +exact.ctr.toFixed(4);

// THE REGRESSION GUARD: the naive read that drops rows with no campaign.
const naive = a.campaigns.filter(x => !x.noCampaign)
  .reduce((t, x) => t + x.spend, 0);
out.naiveSpend = naive;
out.naiveUnderstatesBy = +(a.totals.spend - naive).toFixed(2);

// TOTALS ARE SUMMED, NOT AVERAGED. Mean of the per-campaign ROAS vs the real
// portfolio ROAS - the fixture is built so the two differ visibly.
const roasList = a.campaigns.map(x => x.roas).filter(v => v != null);
out.meanOfRoas  = +(roasList.reduce((s, v) => s + v, 0) / roasList.length).toFixed(4);
out.totalRoas   = +a.totals.roas.toFixed(4);

// ZERO DENOMINATORS
const sb = a.campaigns.find(x => x.campaign === 'SB - Defense');
out.zeroClicks = { cpc: sb.cpc, ctr: sb.ctr, roas: sb.roas, acos: sb.acos, cpa: sb.cpa };
out.zeroBlob   = JSON.stringify(a.campaigns) + JSON.stringify(a.totals);
out.zeroBad    = /Infinity|NaN|null,"?undefined/.test(out.zeroBlob);

// the window really excludes the September row
out.amzInWindow = a.coverage.inWindow;

// Chewy: brand filter narrows, metrics Amazon does not have are present
out.chwNames  = c.campaigns.map(x => x.campaign).sort();
out.chwNtb    = c.totals.ntb;
out.chwUnits  = c.totals.units;
out.chwStatus = (c.campaigns.find(x => x.campaign === 'Meowi SP') || {}).status;
const kkz = run('chewy', CHW, { brand: 'Kitty Ka-Zoom' });
out.chwBrandNames = kkz.campaigns.map(x => x.campaign);
out.chwBrandSpend = kkz.totals.spend;
out.chwSkus = c.campaigns.find(x => x.campaign === 'KKZ Max').skus;

// Amazon reports no units / no NTB: those stay NULL, never a fabricated 0.
out.amzUnits = a.totals.units;
out.amzNtb   = a.totals.ntb;

// adsTypeLabel de-slugs and keeps the acronyms upper
out.typeLabels = ['sponsored_products','sponsored_tv','dsp','some_new_format','', null]
  .map(adsTypeLabel);

// adsDiv guards
out.div = [adsDiv(1,0), adsDiv(0,0), adsDiv(1,'x'), adsDiv(null,2), adsDiv(10,4)];

// degenerate shapes
out.degenerate = [];
for (const rows of [[], [{}], [{ date:'2026-10-01' }]]) {
  try {
    const r = adsCampaignRollup({ channel:'amazon', rows, from:W.from, to:W.to, regionOk:false });
    out.degenerate.push({ rows: r.campaigns.length, spend: r.totals.spend,
      bad: /Infinity|NaN/.test(JSON.stringify(r.totals)) });
  } catch (e) { out.degenerate.push({ threw: String(e.message || e) }); }
}
console.log(JSON.stringify(out));
