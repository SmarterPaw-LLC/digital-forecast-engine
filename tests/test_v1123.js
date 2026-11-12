const PNL_GRAIN_ORDER = ['day', 'week', 'month'];
const PNL_FILL_ALPHA = { sheer: '55', solid: 'd9' };
const PNL_FILL_LINE = '22';
function pnlChartGrain() {
  try {
    const v = localStorage.getItem('pnlChartGrain');
    return PNL_GRAIN_ORDER.includes(v) ? v : 'auto';
  } catch (_) { return 'auto'; }
}
function pnlGrainAuto(win) {
  if (!win || !win.from || !win.to) return 'week';
  const days = Math.round((new Date(win.to + 'T00:00:00') - new Date(win.from + 'T00:00:00')) / 86400000) + 1;
  if (!isFinite(days) || days <= 0) return 'week';
  if (days <= 70) return 'day';
  if (days <= 400) return 'week';
  return 'month';
}
function pnlGrainResolve(win, allowed) {
  const can = (allowed && allowed.length) ? allowed : PNL_GRAIN_ORDER;
  const want = pnlChartGrain();
  if (want !== 'auto' && can.includes(want)) return want;
  const auto = pnlGrainAuto(win);
  if (can.includes(auto)) return auto;
  // Nearest the chart CAN do, COARSER first: a finer grain than the rows
  // carry would be invented, a coarser one is only a rollup.
  const i = PNL_GRAIN_ORDER.indexOf(auto);
  for (let k = i; k < PNL_GRAIN_ORDER.length; k++) if (can.includes(PNL_GRAIN_ORDER[k])) return PNL_GRAIN_ORDER[k];
  for (let k = i; k >= 0; k--) if (can.includes(PNL_GRAIN_ORDER[k])) return PNL_GRAIN_ORDER[k];
  return 'week';
}
function pnlGrainKey(d, grain) {
  const s = String(d || '');
  if (!/^\d{4}-\d{2}-\d{2}/.test(s)) return s;       // already a month key, or junk
  if (grain === 'month') return s.slice(0, 7);
  if (grain !== 'week') return s.slice(0, 10);
  const x = new Date(s.slice(0, 10) + 'T00:00:00');
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
}
function pnlGrainAdv(grain) {
  return grain === 'day' ? 'daily' : grain === 'week' ? 'weekly'
       : grain === 'month' ? 'monthly' : (grain + 'ly');
}
function pnlChartFill() {
  try { return localStorage.getItem('pnlChartFill') === 'solid' ? 'solid' : 'sheer'; }
  catch (_) { return 'sheer'; }
}
function pnlStackAlpha() { return PNL_FILL_ALPHA[pnlChartFill()] || PNL_FILL_ALPHA.sheer; }
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
let _adsBreakEven = {}, _adsAttribDeflate = {};

// The brand the ads panel is currently scoped to, or '' for all. The
// break-even differs materially by brand - Kitty Ka-Zoom keeps 52.6% of
// retail against 57.2% blended - so the floor follows the filter.
function adsBrandFilterValue(ch) {
  try { return (ch && typeof ch.brand === 'function') ? (ch.brand() || '') : ''; }
  catch (_) { return ''; }
}

// v12.20 - /!\ THE FLOOR IS EXPRESSED ON THE BASIS THE ROAS IS MEASURED ON.
//
// The break-even is derived from REAL sales: 2.90x means we need $2.90 of
// actual retail for every $1 of spend. The ROAS beside it divides by
// ATTRIBUTED sales, which on Walmart run ~197% of what the channel sold. So
// the two were never comparable, and `vs Break-Even` read green on a table
// where nothing cleared.
//
// Dividing the floor by the over-claim puts both on the attributed basis:
// 2.90 / 0.5074 = 5.72x. ONE ROAS, ONE floor, and the comparison means
// something. The ratio itself is untouched - it is Walmart's own number and
// has to keep matching their console.
function adsRoasFloor(channel, brand) {
  const be = _adsBreakEven[channel];
  if (!be || be.pending) return 1;
  const row = (brand && be.byBrand && be.byBrand[brand]) || be.overall;
  if (!(row && row.roas > 0)) return 1;
  const d = _adsAttribDeflate[channel];
  return (d != null && d > 0 && d < 1) ? row.roas / d : row.roas;
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
  // v12.20 - already on the ROAS's own basis (see adsRoasFloor), so there is
  // nothing to correct per row and no second ROAS column.
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
  const d = _adsAttribDeflate[channel];
  const adj = (d != null && d > 0 && d < 1);
  return `break-even ROAS ${(adj ? row.roas / d : row.roas).toFixed(2)}x`
    + ` (we keep ${row.sharePct.toFixed(0)}% of retail, ${row.gmPct.toFixed(0)}% GM on that`
    + (adj ? `, and attribution claims ${Math.round(100 / d)}% of what the channel sold`
             + ` \u2014 ${row.roas.toFixed(2)}x on actual sales` : '')
    + ')';
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
  roasVsBe:     'ROAS minus break-even ROAS, in ROAS points. Below zero the row spent more than the unit could pay back.\n\nBreak-even = 1 / (our share of Walmart retail \u00d7 our GM on that wholesale), derived per brand from walmart_sales_weekly, walmart_cost_per_each and product_cogs. Scaled onto the ROAS column\u2019s own ATTRIBUTED basis when attribution claims more than the channel sold, so the two sides are comparable. Blank when the break-even could not be derived.',
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
  // v12.15 - /!\ WHEREVER IT CAN BE COMPUTED, which is the same registry the
  // CARD is gated on. v12.02 wrote `channel === 'amazon'` when Amazon was the
  // only channel with a total-sales feed; since v12.08 the two 1P channels
  // have one too, and the card appeared on them while the + did not.
  if (typeof TACOS_SRC !== 'undefined' && TACOS_SRC[channel]) {
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
// v12.08 - /!\ THE CARD'S SOURCES FOLLOW THE CHANNEL. They were hardcoded to
// Amazon's two feeds, so the Walmart tab cited `amazon_ad_spend` under a card
// that could never hold a number - which is what Jason caught. A channel
// absent from this map gets no card at all, so the registry and the helper's
// own refusal cannot disagree about where TACoS belongs.
const TACOS_SRC = {
  amazon:  ['amazon_ad_spend', 'sku_economics'],
  walmart: ['walmart_ad_campaign_daily', 'walmart_sales_weekly', 'walmart_cost_per_each'],
  chewy:   ['chewy_ad_spend', 'chewy_sales_weekly', 'chewy_catalog'],
};

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
    // v12.15 - /!\ THE DENOMINATOR COMES FROM THE CHANNEL'S OWN FEED.
    // v12.02 reached straight for amzFeeAgg, which is Amazon's aggregate and
    // knows nothing about the 1P sell-through feeds - so TACoS could not be
    // plotted anywhere else even once the card worked there.
    //
    // Amazon reads a cache, so a call per bucket is cheap. The 1P channels
    // read the WEEKS their window's single fetch already returned, which is
    // why this is not a round trip per point on the line.
    if (plot.some(x => x.needsNetSales)) {
      buckets.forEach((b, i) => {
        const r = (typeof pnlBucketRange === 'function') ? pnlBucketRange(b, grain) : null;
        if (!r) return;
        try {
          if (channel === 'amazon') {
            if (typeof amzFeeAgg !== 'function') return;
            const a = amzFeeAgg(r);
            if (a && a.tot) perB[i].netSales = a.tot.netSales || 0;
          } else if (win && win.from && win.to) {
            const v = adsOurRevBucket(channel, { from: win.from, to: win.to }, r.from, r.to);
            if (v != null) perB[i].netSales = v;
          }
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
  // v12.27 - /!\ THE NOTES PANEL AND THE CHART MARKS COME FROM ONE PASS, so
  // a flag on the timeline and the row under it can never describe different
  // notes. The note is placed by SPAN (adsNoteBucketIdx), never by matching
  // the bucket key - the Sunday/Monday trap from v12.15.
  const _noteCamps = (res.campaigns || []).map(c => c[NAMECOL]).filter(Boolean);
  const _noteSel = (sel && sel.size) ? [...sel] : null;
  let _noteEvents = [];
  try {
    if (adsNotesEnsure(channel, ch)) {
      adsNotesRenderList(channel, ch, _noteCamps, _noteSel);
      _noteEvents = adsNotesFor(channel, _noteSel).map(r => {
        const k = ADS_NOTE_KINDS[r.kind] || ADS_NOTE_KINDS.observation;
        return { idx: adsNoteBucketIdx(r.note_date, buckets, grain), color: k.color };
      }).filter(e => e.idx >= 0);
    }
  } catch (e) { console.warn('ads notes panel:', e && e.message); }

  pnlTrendRender({
    canvasId: ch.host + '-chart-canvas', instance: _adsChartInstance[key], periodHost: ch.periodHost,
    buckets, datasets: built.datasets, mode: built.mode,
    isPct: !!m.isPct, unit: m.unit,
  }).then(inst => { _adsChartInstance[key] = inst;
                    if (inst) {
                      inst.$overlaySync = _adsSync;
                      // /!\ The events ride on the INSTANCE and the chart is
                      // nudged, because they are attached after the first
                      // draw and the plugin only runs on a draw.
                      inst.$spEvents = _noteEvents;
                      try { inst.update('none'); } catch (_) {}
                    } })
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
    // v12.29 - /!\ NOTES ARE PART OF THE SHELL. Built once with the host,
    // between the chart and the table, exactly like every other panel here.
    + `<div id="${ch.host}-notes" class="ds" style="margin-bottom:14px">`
    +   `<div class="ds-hdr">`
    +     `<div style="flex:1;min-width:0">`
    +       `<div class="ds-title">\ud83d\udcdd Notes &amp; events</div>`
    +       `<div class="ds-sub" id="${ch.host}-notes-count"></div></div>`
    +     `<span id="adsnote-status" style="font-family:var(--mono);font-size:10px;color:var(--text3)"></span>`
    +   `</div>`
    +   `<div class="ds-body" style="padding:12px 14px">`
    // v12.30 - /!\ ONE WAY TO WRITE A NOTE, and it is on the row. What is
    // left here is the account-level note, which no campaign row can own.
    +     `<div style="margin-bottom:10px">`
    +       `<button type="button" onclick="adsNoteCompose('${channel}','')" style="font-family:var(--display);font-weight:700;font-size:11px;padding:5px 12px;border:1px solid var(--border2);border-radius:5px;background:var(--surface2);color:var(--text2);cursor:pointer">+ Account-level note</button>`
    +       `<span style="margin-left:10px;font-family:var(--mono);font-size:10px;color:var(--text3)">for a campaign, use the \ud83d\udcdd on its row</span>`
    +     `</div>`
    +     `<div id="${ch.host}-notes-list"></div>`
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
// ===========================================================================
// v12.08 - OUR REVENUE, PER CHANNEL, FOR A WINDOW
// ===========================================================================
// The denominator TACoS needs on a 1P channel.
//
// /!\ IT IS NOT THE SALES FIGURE THOSE FEEDS REPORT. On Amazon, net sales IS
// what we receive. On Walmart and Chewy we are 1P: the sales number in the
// feed is RETAIL - what the shopper paid Walmart or Chewy - and the app
// already calls Chewy's "a vanity. We never see this money."
//
// Measured on the live database, 2026-08-11 -> 2026-11-09:
//     Walmart retail $16,579   our revenue $6,179   (we keep ~37%)
// Dividing ad spend by retail would make Walmart look roughly TWICE as
// efficient as Amazon for the same dollars, under a label that already means
// something else one tab over. Jason picked our revenue.
//
// /!\ AND AN UNPRICED SKU IS REPORTED, NOT SWALLOWED. A SKU that sold but has
// no cost-per-each contributes nothing to the denominator, which makes TACoS
// read HIGH. Silently that is a confident wrong answer; the card names the
// gap instead.
const _adsOurRev = {};

function _adsOurRevKey(channel, range) {
  return [channel, (range && range.from) || '', (range && range.to) || ''].join('|');
}

function adsOurRevFor(channel, range) {
  return _adsOurRev[_adsOurRevKey(channel, range)];
}

// v12.15 - the denominator for ONE bucket of the chart, summed from the weeks
// the window's fetch already returned.
//
// /!\ BY SPAN, NOT BY KEY - the same rule v12.02 settled for Amazon. A week
// is in a bucket when its week_start falls inside the bucket's own date span,
// so a Sunday-keyed ads bucket and a Monday-keyed sales week line up without
// either side knowing about the other's convention.
function adsOurRevBucket(channel, range, from, to) {
  const r = adsOurRevFor(channel, range);
  if (!r || r.pending || !r.weeks || !from || !to) return null;
  // v12.21 - /!\ RETAIL, matching the card. Two surfaces of one measure may
  // not divide by two different numbers (rule #5).
  let rev = 0, any = false;
  for (const w of r.weeks) {
    if (w.w >= from && w.w <= to) { rev += w.retail; any = true; }
  }
  // /!\ A BUCKET WITH NO WEEK IN IT IS A GAP, NEVER 0 (v11.16). Returning 0
  // would draw a point at zero TACoS, which reads as "spent nothing".
  return any ? rev : null;
}

// A window is only ever built by the period controls, but it reaches a SQL
// string here, so the shape is checked rather than trusted.
function _adsIsYmd(d) { return /^\d{4}-\d{2}-\d{2}$/.test(String(d || '')); }

async function adsLoadOurRev(channel, range) {
  const k = _adsOurRevKey(channel, range);
  if (_adsOurRev[k] !== undefined) return;
  if (!range || !_adsIsYmd(range.from) || !_adsIsYmd(range.to)) {
    _adsOurRev[k] = { rev: null, why: 'This window has no date range.' };
    return;
  }
  _adsOurRev[k] = { pending: true };
  const from = range.from, to = range.to;

  // v12.24 - /!\ THE ROWS ARE ALREADY HERE. `walmartPnlData` is what the
  // Sales tab renders: one row per product per week, carrying net_sales.
  // Summing it is the denominator, so this answer is available SYNCHRONOUSLY
  // - before any await, before the cards are built, with no request to hang
  // and no repaint to depend on.
  //
  // /!\ AND IT IS THE SAME ROWS THE SALES TAB SUMS, so the two surfaces
  // cannot report different sell-through for one window.
  if (channel === 'walmart') {
    try {
      if (Array.isArray(walmartPnlData) && walmartPnlData.length) {
        const byWk = new Map();
        for (const row of walmartPnlData) {
          const w = String(row.week_start || '').slice(0, 10);
          if (!w || w < from || w > to) continue;
          const slot = byWk.get(w) || { w, rev: 0, retail: 0, capped: 0, cappedAmt: 0 };
          slot.retail += Number(row.net_sales) || 0;
          byWk.set(w, slot);
        }
        const wk0 = [...byWk.values()].sort((x, y) => (x.w < y.w ? -1 : x.w > y.w ? 1 : 0));
        if (wk0.length) {
          _adsOurRev[k] = {
            bases: [], rev: null,
            retail: wk0.reduce((t, x) => t + x.retail, 0),
            priced: 0, unpricedSkus: 0, unpricedUnits: 0,
            cappedRows: 0, cappedAmt: 0, cappedWeeks: [],
            from: wk0[0].w, to: wk0[wk0.length - 1].w,
            weeks: wk0, weekly: true, fromMemory: true, why: null,
          };
        }
      }
    } catch (e) { console.warn('TACoS denominator from memory:', e && e.message); }

    // /!\ AND IF THE SALES TAB HAS NEVER BEEN OPENED the array is empty, so
    // the rows are loaded through the loader that already owns them rather
    // than through a second query of my own. It repaints when they land.
    if (!(Array.isArray(walmartPnlData) && walmartPnlData.length)
        && typeof loadWalmartPnl === 'function') {
      Promise.resolve().then(() => loadWalmartPnl()).then(() => {
        delete _adsOurRev[k];
        if (typeof renderAdsCampaigns === 'function') renderAdsCampaigns(channel, '');
      }).catch(e => console.warn('walmart sales load:', e && e.message));
    }
  }

  try {
    const sb = await getSB();
    if (channel === 'walmart') {
      // /!\ THE SAME JOIN adsLoadBreakEven USES, windowed. One definition of
      // "what Walmart pays us" - units x the per-each cost on our agreement -
      // so the break-even line and this denominator cannot disagree.
      // v12.15 - /!\ PER WEEK, not one total. The chart needs a denominator
      // per bucket, and these feeds are weekly - so one query returns the
      // weeks and every bucket is summed from them in the browser. A query
      // per bucket would be a round trip per point on the line.
      // v12.18 - /!\ A MARKED-DOWN UNIT WAS NOT REPLENISHED AT STANDARD COST.
      // units x cost_per_each models our revenue by assuming every unit sold
      // out was bought from us at the agreement price. On a clearance Walmart
      // is liquidating stock it ALREADY paid for, so the model credits us for
      // goods paid for months earlier - and the tell is self-evident: the
      // modelled revenue comes out ABOVE the retail it sold for, which is
      // impossible on 1P. Capped at the retail, and the shortfall is carried
      // so the card can say the window holds a markdown.
      const sql = `select w.week_start,
          sum(case when w.net_sales > 0 and w.units * c.cost_per_each > w.net_sales
                   then w.net_sales else w.units * c.cost_per_each end) rev,
          sum(w.units * c.cost_per_each) rev_raw,
          sum(case when w.net_sales > 0 and w.units * c.cost_per_each > w.net_sales
                   then 1 else 0 end) capped,
          sum(w.net_sales) retail,
          count(distinct w.master_id) priced,
          max(w.source) basis
        from public.walmart_sales_weekly w
        join public.walmart_cost_per_each c on c.master_id = w.master_id
        where w.week_start >= '${from}' and w.week_start <= '${to}'
        group by 1 order by 1`;
      const gapSql = `select count(distinct w.master_id) skus, sum(w.units) units
        from public.walmart_sales_weekly w
        left join public.walmart_cost_per_each c on c.master_id = w.master_id
        where c.master_id is null
          and w.week_start >= '${from}' and w.week_start <= '${to}'`;
      const [a, b] = await Promise.all([
        sb.rpc('exec_sql', { query: sql }),
        sb.rpc('exec_sql', { query: gapSql }),
      ]);
      if (a.error) throw a.error;
      const wk = (a.data || []).map(x => ({
        w: String(x.week_start).slice(0, 10),
        rev: Number(x.rev) || 0, retail: Number(x.retail) || 0,
        capped: Number(x.capped) || 0,
        cappedAmt: Math.max(0, (Number(x.rev_raw) || 0) - (Number(x.rev) || 0)),
      }));
      const g = (b.error ? {} : ((b.data || [])[0] || {}));
      // /!\ THE TOTAL IS THE SUM OF THE WEEKS, not a second aggregate. Two
      // ways to total the same rows is two numbers that can disagree, and
      // the card and the chart would be the two surfaces showing them.
      const priced = (a.data || []).reduce((m, x) => Math.max(m, Number(x.priced) || 0), 0);
      // v12.16 - whichever basis the loaded rows were uploaded under. Mixed
      // bases would be a worse problem than either one, so they are collected
      // rather than reduced to the first.
      const bases = [...new Set((a.data || []).map(x => x.basis).filter(Boolean))];
      // /!\ The query ADDS our revenue and the markdown cap to an answer the
      // page already has. It never replaces a good retail figure with a
      // pending one, and it cannot un-answer the card.
      _adsOurRev[k] = {
        bases,
        rev: wk.reduce((t, x) => t + x.rev, 0),
        retail: wk.reduce((t, x) => t + x.retail, 0),
        priced,
        unpricedSkus: Number(g.skus) || 0, unpricedUnits: Number(g.units) || 0,
        cappedRows: wk.reduce((t, x) => t + x.capped, 0),
        cappedAmt: wk.reduce((t, x) => t + x.cappedAmt, 0),
        cappedWeeks: wk.filter(x => x.capped > 0).map(x => x.w),
        from: wk.length ? wk[0].w : from, to: wk.length ? wk[wk.length - 1].w : to,
        weeks: wk, weekly: true, why: null,
      };
      return;
    }
    if (channel === 'chewy') {
      // /!\ CHEWY'S PER-EACH PRICE IS NOT A COLUMN. It is cost / case_qty for
      // a CS row and cost as-is for an EA row, and the UOM test lives in
      // chewyCatalogPricePerEach. Doing that division in SQL would be a
      // SECOND spelling of the one number the Cost to Chewy tab is built on,
      // so the units are fetched and the price applied through the EXISTING
      // helper (hard rule #1).
      if (typeof loadChewyCatalog === 'function') { try { await loadChewyCatalog(); } catch (_) {} }
      if (typeof loadProducts === 'function' && (typeof allProducts === 'undefined' || !allProducts.length)) {
        try { await loadProducts(); } catch (_) {}
      }
      // v12.15 - by WEEK and sku, so the chart can bucket it. The per-each
      // price still has to be applied per sku in JS (it is cost / case_qty
      // on a CS row), so the week comes back on every row rather than the
      // rows being pre-aggregated.
      const sql = `select week_start, master_id, sum(units_sold) units, sum(merch_sales) retail
        from public.chewy_sales_weekly
        where week_start >= '${from}' and week_start <= '${to}'
          and master_id is not null
        group by 1, 2 order by 1`;
      const [a] = await Promise.all([sb.rpc('exec_sql', { query: sql })]);
      if (a.error) throw a.error;
      const byMid = {};
      (typeof allProducts !== 'undefined' ? allProducts : []).forEach(p => { byMid[p.master_id] = p; });
      let rev = 0, retail = 0, unpricedUnits = 0;
      const byWeek = new Map();
      const pricedSet = new Set(), unpricedSet = new Set();
      for (const row of (a.data || [])) {
        const units = Number(row.units) || 0;
        const ret = Number(row.retail) || 0;
        const w = String(row.week_start).slice(0, 10);
        retail += ret;
        const cat = (typeof chewyCatalogFor === 'function') ? chewyCatalogFor(row.master_id) : null;
        const pe = (typeof chewyCatalogPricePerEach === 'function')
          ? chewyCatalogPricePerEach(cat, (byMid[row.master_id] || {}).case_qty) : { price: null };
        const slot = byWeek.get(w) || { w, rev: 0, retail: 0 };
        slot.retail += ret;
        if (pe && pe.price != null) {
          const v = pe.price * units;
          rev += v; slot.rev += v;
          pricedSet.add(row.master_id);
        } else {
          // /!\ COUNTED ONCE PER SKU, not once per week it sold in - the card
          // says "26 SKU(s) unpriced" and that has to mean SKUs.
          unpricedSet.add(row.master_id); unpricedUnits += units;
        }
        byWeek.set(w, slot);
      }
      const wk = [...byWeek.values()].sort((x, y) => x.w < y.w ? -1 : 1);
      _adsOurRev[k] = { rev, retail, priced: pricedSet.size,
                        unpricedSkus: unpricedSet.size, unpricedUnits,
                        from: wk.length ? wk[0].w : from, to: wk.length ? wk[wk.length - 1].w : to,
                        weeks: wk, weekly: true, why: null };
      return;
    }
    _adsOurRev[k] = { rev: null, why: 'No total-sales feed is wired for this channel.' };
  } catch (e) {
    // /!\ A FAILED DERIVATION REPORTS ITS REASON. "statement timeout" is more
    // useful than a dash, and it must not be retried on every repaint - the
    // entry is written either way, which is what stops the loop.
    console.warn('ads our-revenue unavailable for', channel, e && e.message);
    // v12.24 - /!\ A FAILED QUERY MAY NOT ERASE THE ANSWER MEMORY ALREADY
    // GAVE. It only ever had our revenue and the cap to add.
    const had = _adsOurRev[k];
    _adsOurRev[k] = (had && had.fromMemory && had.retail > 0)
      ? had
      : { rev: null, why: 'Sales could not be read: ' + ((e && e.message) || e) };
  }
}

// v12.08 - /!\ HOW MUCH OF THE WINDOW THE AD FEED ACTUALLY COVERS.
// TACoS divides spend by sales over THE SAME window. If the spend feed only
// reaches part of it, the ratio is a partial numerator over a full
// denominator - and it reads LOW, which is the direction that looks like good
// news. Measured on the live data the day this shipped: Walmart's ad feed
// covered 6 of the 91 days in a 90-day window, and TACoS would have read
// 16.5% where the one fully-covered week reads 181%.
//
// The span is used rather than a day count because a feed with a hole in the
// middle is a different problem (the coverage line already reports row counts);
// this catches the one that silently halves a ratio.
const TACOS_MIN_COVERAGE = 0.8;

function _adsDayCount(from, to) {
  if (!from || !to) return 0;
  const a = Date.parse(from + 'T00:00:00'), b = Date.parse(to + 'T00:00:00');
  if (isNaN(a) || isNaN(b) || b < a) return 0;
  return Math.round((b - a) / 86400000) + 1;
}

// ===========================================================================
// v12.27 - CAMPAIGN NOTES, and the events they put on the timeline.
//
// Jason: "i need a 'notes' section that i can set per campaign level, with an
// event that appears on the timeline ... i just changed the kitty ka zoom
// manual campaign to dynamic bidding today, and i want to record that change"
//
// /!\ A note with NO campaign is an ACCOUNT-level event and draws on every
// campaign's timeline. A note WITH one draws only there. That is the whole of
// the scoping rule, and it is applied in one place (adsNotesFor) so the list
// and the chart cannot disagree about which notes belong to a view.
// ===========================================================================
const ADS_NOTE_KINDS = {
  change:      { label: 'Setting change', color: '#4a7fe0' },
  creative:    { label: 'Creative',       color: '#8a63d2' },
  budget:      { label: 'Budget',         color: '#2e9e6b' },
  test:        { label: 'Test',           color: '#d98c1f' },
  external:    { label: 'External',       color: '#b05b9e' },
  observation: { label: 'Observation',    color: '#7a8088' },
};

let _adsNotes = {};          // channel -> { pending } | { rows: [...] }

function adsNotesRows(channel) {
  const e = _adsNotes[channel];
  return (e && Array.isArray(e.rows)) ? e.rows : [];
}

// /!\ ONE SCOPING RULE. Account-level notes (campaign null) always apply;
// a campaign note applies only to its own campaign. With nothing selected the
// view is the whole account, so every note is in scope.
function adsNotesFor(channel, campaignNames) {
  const rows = adsNotesRows(channel);
  if (!campaignNames || !campaignNames.length) return rows;
  const want = new Set(campaignNames);
  return rows.filter(r => !r.campaign || want.has(r.campaign));
}

async function adsNotesLoad(channel, force) {
  if (!force && _adsNotes[channel] !== undefined) return;
  _adsNotes[channel] = { pending: true };
  try {
    const sb = await getSB();
    const { data, error } = await sb.from('ads_campaign_notes')
      .select('*').eq('channel', channel).order('note_date', { ascending: false });
    if (error) throw error;
    _adsNotes[channel] = { rows: (data || []) };
  } catch (e) {
    // /!\ The table may not exist yet. Say which file creates it rather than
    // printing a Postgres message nobody can act on (the v12.03 rule).
    const msg = String((e && e.message) || e);
    _adsNotes[channel] = {
      rows: [],
      why: /ads_campaign_notes/.test(msg) && /exist|schema|relation/i.test(msg)
        ? 'Run supabase_v12_27_ads_campaign_notes.sql to enable notes.'
        : 'Notes could not be read: ' + msg,
    };
    console.warn('ads notes:', msg);
  }
}



async function adsNoteDelete(channel, id) {
  // /!\ A note is a record of a decision. Deleting one silently would lose
  // the only account of why a line moved.
  const row = adsNotesRows(channel).find(r => String(r.id) === String(id));
  if (!confirm('Delete this note?\n\n' + (row ? (row.note_date + ' \u00b7 ' + row.note) : id)
               + '\n\nThis cannot be undone.')) return;
  try {
    const sb = await getSB();
    const { error } = await sb.from('ads_campaign_notes').delete().eq('id', id);
    if (error) throw error;
    await adsNotesLoad(channel, true);
    adsNotesRepaint(channel);
  } catch (e) { console.warn('ads note delete:', (e && e.message) || e); }
}

// /!\ A NOTE IS PLACED BY SPAN, NOT BY KEY - the Sunday/Monday trap (v12.15).
// A note dated any day inside a bucket belongs to that bucket, whatever the
// grain and whichever day the bucket is keyed on.
function adsNoteBucketIdx(noteDate, buckets, grain) {
  if (!noteDate || !Array.isArray(buckets) || !buckets.length) return -1;
  const d = String(noteDate).slice(0, 10);
  for (let i = 0; i < buckets.length; i++) {
    let span = null;
    try { span = (typeof pnlBucketRange === 'function') ? pnlBucketRange(buckets[i], grain) : null; }
    catch (_) { span = null; }
    if (span && span.from && span.to) {
      if (d >= span.from && d <= span.to) return i;
    } else if (String(buckets[i]).slice(0, 10) === d) {
      return i;
    }
  }
  return -1;
}

// /!\ ONE PANEL, BUILT ONCE AND THEN REPAINTED - the v10.99 rule. Rewriting
// the whole block on every render would blow away the note field's focus and
// caret mid-sentence, which is exactly what that rule exists for: only the
// LIST is repainted, never the form.
let _adsNotesChannel = {};   // host -> channel, so the repaint knows its scope

// v12.30 - /!\ THE COMPOSER, SCOPED BEFORE IT OPENS. Built in the app's own
// dialog shape (the uploadGuardDialog pattern, hard rule #1) rather than a
// tenth bespoke modal. The campaign is SHOWN, never chosen: it is whichever
// row was clicked, so the note cannot be filed against the wrong one.
function adsNoteCompose(channel, campaign) {
  const name = campaign || '';
  const dlg = document.createElement('div');
  dlg.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center';
  const opts = Object.entries(ADS_NOTE_KINDS)
    .map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('');
  let today = '';
  try { today = new Date().toISOString().slice(0, 10); } catch (_) {}
  dlg.innerHTML =
    '<div style="background:var(--surface);border:1px solid var(--border2);border-radius:12px;padding:22px 26px;max-width:520px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.5)">'
    + '<div style="font-family:var(--display);font-weight:800;font-size:15px;color:var(--text);margin-bottom:4px">\ud83d\udcdd Add a note</div>'
    + `<div style="font-family:var(--mono);font-size:11px;color:var(--text3);margin-bottom:16px">${name ? esc2(name) : 'whole account'}</div>`
    + '<div style="display:flex;gap:8px;margin-bottom:10px">'
    +   `<input type="date" id="anc-date" value="${today}" style="font-family:var(--mono);font-size:12px;padding:7px 9px;border:1px solid var(--border2);border-radius:6px;background:var(--surface2);color:var(--text)">`
    +   `<select id="anc-kind" style="flex:1;font-family:var(--mono);font-size:12px;padding:7px 9px;border:1px solid var(--border2);border-radius:6px;background:var(--surface2);color:var(--text)">${opts}</select>`
    + '</div>'
    + '<textarea id="anc-text" rows="3" placeholder="what changed, and why" style="width:100%;box-sizing:border-box;font-family:var(--mono);font-size:12px;padding:8px 10px;border:1px solid var(--border2);border-radius:6px;background:var(--surface2);color:var(--text);resize:vertical;margin-bottom:6px"></textarea>'
    + '<div id="anc-err" style="font-family:var(--mono);font-size:11px;color:var(--sp-red,#d63f2a);min-height:15px;margin-bottom:10px"></div>'
    + '<div style="display:flex;gap:8px">'
    +   '<button id="anc-no" style="flex:1;background:var(--surface2);border:1px solid var(--border2);border-radius:7px;color:var(--text2);font-family:var(--display);font-weight:700;font-size:12px;padding:9px;cursor:pointer">Cancel</button>'
    +   '<button id="anc-yes" style="flex:1;background:var(--sp-green,#4a9e38);border:1px solid var(--sp-green,#4a9e38);border-radius:7px;color:#fff;font-family:var(--display);font-weight:700;font-size:12px;padding:9px;cursor:pointer">Save note</button>'
    + '</div></div>';
  document.body.appendChild(dlg);
  const g = id => dlg.querySelector('#' + id);
  const close = () => { try { dlg.remove(); } catch (_) {} };
  g('anc-no').onclick = close;
  dlg.onclick = e => { if (e.target === dlg) close(); };
  setTimeout(() => { try { g('anc-text').focus(); } catch (_) {} }, 0);
  g('anc-yes').onclick = async () => {
    const date = g('anc-date').value || '';
    const text = (g('anc-text').value || '').trim();
    const err = g('anc-err');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) { err.textContent = 'Pick a date.'; return; }
    if (!text) { err.textContent = 'Write the note.'; return; }
    err.textContent = '';
    g('anc-yes').disabled = true; g('anc-yes').textContent = 'Saving\u2026';
    try {
      const sb = await getSB();
      const { error } = await sb.from('ads_campaign_notes').insert([{
        channel, account: null, campaign: name || null,
        note_date: date, kind: g('anc-kind').value || 'change', note: text,
      }]);
      if (error) throw error;
      close();
      await adsNotesLoad(channel, true);
      adsNotesRepaint(channel);
    } catch (e) {
      g('anc-yes').disabled = false; g('anc-yes').textContent = 'Save note';
      err.textContent = 'Could not save: ' + ((e && e.message) || e);
    }
  };
}

// How many notes this campaign carries. Account-level notes are deliberately
// NOT counted here: they belong to every row, so adding them to each count
// would report the same note five times.
function adsNoteCountFor(channel, campaign) {
  if (!campaign) return 0;
  return adsNotesRows(channel).filter(r => r.campaign === campaign).length;
}

function adsNotesEnsure(channel, ch) {
  // v12.29 - /!\ THE PANEL IS IN THE SHELL NOW. This only finds it, records
  // the scope for the repaint, and seeds the date field once. Creating it by
  // DOM insertion was a mechanism this page uses nowhere else, and it did not
  // survive contact with the live render.
  const box = document.getElementById(ch.host + '-notes');
  if (!box) return null;
  _adsNotesChannel[ch.host] = channel;
  return box;
}


function adsNotesRenderList(channel, ch, campaignNames, selectedNames) {
  const list = document.getElementById(ch.host + '-notes-list');
  const cnt  = document.getElementById(ch.host + '-notes-count');
  if (!list) return;
  const entry = _adsNotes[channel];
  if (entry && entry.pending) { list.innerHTML = ''; if (cnt) cnt.textContent = 'reading\u2026'; return; }
  if (entry && entry.why) {
    list.innerHTML = `<div style="font-family:var(--mono);font-size:11px;color:var(--sp-orange,#c2771f)">\u26a0 ${esc2(entry.why)}</div>`;
    if (cnt) cnt.textContent = '';
    return;
  }
  const rows = adsNotesFor(channel, selectedNames);
  if (cnt) {
    cnt.textContent = rows.length
      ? (rows.length + ' in view' + (selectedNames && selectedNames.length ? ' \u00b7 selection' : ''))
      : 'nothing recorded yet \u00b7 use the \ud83d\udcdd on a campaign row';
  }
  if (!rows.length) { list.innerHTML = ''; return; }
  list.innerHTML = rows.slice(0, 40).map(r => {
    const k = ADS_NOTE_KINDS[r.kind] || ADS_NOTE_KINDS.observation;
    const scope = r.campaign ? esc2(r.campaign) : 'whole account';
    return `<div style="display:flex;gap:8px;align-items:flex-start;padding:5px 0;border-top:1px solid var(--border2)">
        <span style="font-family:var(--mono);font-size:10px;color:var(--text3);min-width:78px">${esc2(String(r.note_date).slice(0,10))}</span>
        <span style="font-family:var(--mono);font-size:9px;color:#fff;background:${k.color};border-radius:3px;padding:1px 6px;white-space:nowrap">${k.label}</span>
        <span style="font-family:var(--mono);font-size:11px;color:var(--text);flex:1;min-width:0">${esc2(r.note)}
          <span style="color:var(--text3)"> \u00b7 ${scope}</span></span>
        <button type="button" title="Delete this note" onclick="adsNoteDelete('${channel}', ${Number(r.id)})"
          style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:12px;line-height:1">\u00d7</button>
      </div>`;
  }).join('');
}


// /!\ Repaint through the renderer, so the chart marks and the list are built
// from one pass. A second path that refreshed only the list is how the flag
// on the chart and the row under it come to disagree.
function adsNotesRepaint(channel) {
  for (const [host, chn] of Object.entries(_adsNotesChannel)) {
    if (chn !== channel) continue;
    const re = window['_adsRe_' + host];
    if (typeof re === 'function') { try { re(); } catch (_) {} }
  }
}

function adsTacosFor(channel, selRows, spend, range, adSpan, adSales) {
  const no = (why) => ({ pct: null, netSales: null, why });

  // v12.08 - three channels have a total-sales feed now. The two 1P ones
  // divide by OUR REVENUE rather than by the retail figure their feeds
  // report - see the header on adsLoadOurRev.
  if (channel !== 'amazon' && channel !== 'walmart' && channel !== 'chewy') {
    return no('TACoS needs this channel\u2019s total sales, and this one has no feed carrying them.');
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
  if (channel !== 'amazon') {
    // /!\ NO RANGE, NO ANSWER - the same rule as the Amazon branch below, for
    // the same reason: a denominator fetched over a different window than the
    // spend beside it is two windows in one ratio.
    if (!range || !range.from || !range.to) {
      return no('This window has no date range, so TACoS cannot match its sales to its spend.');
    }
    // /!\ AND NO ANSWER WHEN THE AD FEED COVERS ONLY PART OF IT.
    const winDays = _adsDayCount(range.from, range.to);
    const adDays  = adSpan ? _adsDayCount(adSpan.from, adSpan.to) : 0;
    // v12.22 - /!\ PARTIAL COVERAGE NARROWS THE DENOMINATOR, it does not
    // refuse the card. v12.08 was right that spend over 231 days divided by
    // sales over 335 reads far too low, and wrong that a dash was the answer:
    // the weekly rows are already in hand, so both sides can be taken over
    // the span the ads actually ran.
    const narrow = (winDays > 0 && adDays > 0 && (adDays / winDays) < TACOS_MIN_COVERAGE
                    && adSpan && _adsIsYmd(adSpan.from) && _adsIsYmd(adSpan.to));
    const r = (typeof adsOurRevFor === 'function') ? adsOurRevFor(channel, range) : null;
    // v12.23 - /!\ NEVER-REQUESTED AND IN-FLIGHT ARE BOTH LOADING, NOT
    // MISSING. `not available` is a statement about the data; until the fetch
    // has answered, the only true statement is that it has not answered yet.
    if (!r || r.pending) {
      return { pct: null, netSales: null, pending: true, why: 'Reading sales\u2026' };
    }
    if (r.why) return no(r.why);
    // v12.21 - /!\ SELL-THROUGH, the same basis the Amazon tab divides by.
    // `sku_economics.net_sales` is what the customer paid; on a 1P channel
    // that is the retailer's own sell-through, NOT what they pay us. Dividing
    // by our revenue made one label mean two things a tab apart (rule 3a) and
    // matched nothing else on the page.
    // /!\ THE DENOMINATOR, AND THE SPAN IT IS TAKEN OVER, TRAVEL TOGETHER.
    // A figure without the period it covers is the thing that made this card
    // unreadable in the first place.
    let denom = r.retail, dFrom = r.from, dTo = r.to, narrowed = false;
    if (narrow && Array.isArray(r.weeks)) {
      let sum = 0, lo = null, hi = null;
      for (const w of r.weeks) {
        if (w.w >= adSpan.from && w.w <= adSpan.to) {
          sum += w.retail;
          if (lo == null || w.w < lo) lo = w.w;
          if (hi == null || w.w > hi) hi = w.w;
        }
      }
      if (sum > 0) { denom = sum; dFrom = lo; dTo = hi; narrowed = true; }
    }
    if (!(denom > 0)) {
      return no('No sales in this window, so TACoS has no denominator. Widen the period.');
    }
    // v12.17 - /!\ ATTRIBUTION OVER-COUNTS, AND THAT IS NOT A REASON TO REFUSE.
    //
    // v12.13 refused whenever ad-attributed sales exceeded total sell-through,
    // reasoning that ad sales are a SUBSET of total sales so the denominator
    // had to be incomplete. Measured on the real data, that is wrong here:
    //
    //     28 weeks, 2026-03-25 -> 2026-11-10
    //     total eComm sales (AUTH)   8,613 units   $44,862
    //     ads claim attributed       9,441 units   $60,235
    //
    // The feed is complete - one vendor number, 33 items, both advertised
    // brands, 0 unmapped rows, 0 without a cost_per_each, and AUTH within
    // 0.1% of shipped. It is Walmart's 14-day post-click window crediting
    // more than the channel sold.
    //
    // /!\ AND TACoS DOES NOT USE THE NUMERATOR. It is spend over TOTAL sales.
    // Withholding a correct number because a DIFFERENT number looks odd is
    // the opposite of the job. The comparison survives as a note, because it
    // does say the ROAS and ACOS beside it are on a basis that cannot be
    // reconciled to sell-through.
    const overAttr = (adSales != null && r.retail > 0 && adSales > r.retail)
      ? { adSales, retail: r.retail, pct: (adSales / r.retail) * 100 }
      : null;

    // /!\ THE BASIS IS NAMED ON THE RESULT, because on these two channels it
    // is NOT the number their own console shows. 1P sales are retail; this is
    // what the retailer pays us.
    // v12.17 - which export the denominator came from, carried so the card
    // can say it. The app stamps walmart:shipped / walmart:pos at upload
    // (v12.16); a figure whose provenance is on the tooltip is one nobody
    // has to guess at from a column name - which is how three wrong
    // explanations got shipped.
    const salesBasis = (r.bases || []).map(b2 => String(b2).replace(/^walmart:/, ''))
      .filter(Boolean).join(' + ') || null;
    return { pct: (spend || 0) / denom * 100, netSales: denom, salesBasis,
             ourRev: r.rev, narrowed, adDays, winDays,
             from: dFrom, to: dTo, basis: 'ourRev',
             retail: r.retail, unpricedSkus: r.unpricedSkus,
             unpricedUnits: r.unpricedUnits, overAttr,
             cappedRows: r.cappedRows || 0, cappedAmt: r.cappedAmt || 0,
             cappedWeeks: r.cappedWeeks || [], why: null };
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

  // v12.27 - the notes, on the same principle: asked for before anything
  // draws, and a repaint when they land.
  if (_adsNotes[channel] === undefined) {
    adsNotesLoad(channel).then(() => renderAdsCampaigns(channel, view))
      .catch(e => console.warn('ads notes:', e && e.message));
  }

  // v12.23 - /!\ BEFORE ANY READER, not after every card. The break-even
  // deflator, the Sell-Through card and the TACoS card all read this cache
  // while the strip is being built; kicking the fetch off at the BOTTOM of
  // this function guaranteed that the first render of every window drew all
  // three from an empty cache.
  //
  // It cannot loop: adsLoadOurRev writes its entry synchronously before the
  // first await and on every failure path, so the `=== undefined` test is
  // false from the moment it starts.
  if (channel !== 'amazon' && TACOS_SRC[channel] && win && win.from && win.to
      && _adsOurRev[_adsOurRevKey(channel, win)] === undefined) {
    adsLoadOurRev(channel, { from: win.from, to: win.to }).then(() => {
      renderAdsCampaigns(channel, view);
    }).catch(e => console.warn('TACoS sales fetch:', e && e.message));
  }
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
  let _adsSellThru = null;
  // v12.20 - the over-attribution factor, measured rather than assumed: the
  // channel's own sell-through over the attributed sales claimed against it.
  // Only below 1 - attribution claiming LESS than the channel sold is normal
  // and nothing to correct.
  //
  // /!\ IT IS SET BEFORE THE STAMP, because adsRoasFloor reads it and FOUR
  // things read adsRoasFloor: the stamp, the TOTAL row, the sub-floor red
  // colour and the break-even note. Setting it in one place converts all
  // four (rule #5).
  _adsAttribDeflate[channel] = null;
  try {
    const _r = (typeof adsOurRevFor === 'function' && TACOS_SRC[channel] && win && win.from && win.to)
      ? adsOurRevFor(channel, { from: win.from, to: win.to }) : null;
    if (_r && !_r.pending && _r.retail > 0 && res.totals && res.totals.sales > _r.retail) {
      _adsAttribDeflate[channel] = _r.retail / res.totals.sales;
    }
    _adsSellThru = (_r && !_r.pending && _r.retail > 0) ? _r : null;
  } catch (_) { _adsAttribDeflate[channel] = null; _adsSellThru = null; }
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
    // /!\ `t` is the window's own rollup, so firstDate / lastDate are the
    // AD rows' actual span - not the window's, and not the selection's.
    // /!\ `t.sales` is the window's ad-attributed sales on the SAME retail
    // basis the sell-through feed reports, which is what makes the comparison
    // inside adsTacosFor legitimate rather than apples-to-oranges.
    tacos = adsTacosFor(channel, selRows, t && t.spend, tacosRange,
                        t ? { from: t.firstDate, to: t.lastDate } : null,
                        t ? t.sales : null);
    if (!selRows && prev && tacosRange && typeof getPnlPrevDateRange === 'function') {
      tacosPrev = adsTacosFor(channel, null, pt && pt.spend, getPnlPrevDateRange(tacosRange),
                              pt ? { from: pt.firstDate, to: pt.lastDate } : null,
                              pt ? pt.sales : null);
    }
  } catch (e) {
    console.warn('TACoS card:', e && e.message);
    tacos = { pct: null, why: 'TACoS could not be computed: ' + (e && e.message) };
    tacosPrev = { pct: null };
  }

  // v12.25 - the TACoS tooltip prints the numerator, and its declaration was
  // deleted with v12.19's Ceiling ROAS block. A ReferenceError that took the
  // whole tab down, and `node --check` passed it: scope is not syntax.
  const spendForTip = (t && t.spend) || 0;
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
      // v12.20 - /!\ THE MISSING RUNG. Jason: "the tacos number STILL does not
      // match sales". Ad Sales is ATTRIBUTED and retail; the TACoS denominator
      // is TOTAL and our revenue. With nothing between them the strip showed
      // two figures 5x apart under one word. This is the channel's own
      // sell-through, which both of them are derived from.
      ...(_adsSellThru ? [{
        label: 'Sell-Through',
        val: $0(_adsSellThru.retail),
        // v12.26 - /!\ UNDER A SELECTION THIS IS THE CHANNEL, NOT THE ROWS
        // TICKED. Organic sales do not belong to a campaign, so it cannot be
        // narrowed - and a card that silently keeps answering a control it
        // cannot honour is the v10.19 defect.
        sub: selRows
          ? ('\u26a0 whole channel \u00b7 selection NOT applied')
          : ('everything the channel sold \u00b7 retail'
             + (t && t.sales > 0 && _adsSellThru.retail > 0
                ? ' \u00b7 ads claim ' + Math.round(100 * t.sales / _adsSellThru.retail) + '%'
                : '')),
        color: selRows ? 'var(--text3)' : 'var(--text)',
        delta: null,
        src: TACOS_SRC[channel],
        tip: 'Walmart 1P sell-through over this window\u2019s weeks, at RETAIL.'
           + '\n\nAd Sales above is the ad-attributed slice of this, on the same basis.'
           + (selRows
              ? '\n\n\u26a0 Sales are not attributable to a campaign, so this stays the '
                + 'whole channel while the cards around it show your selection.'
              : ''),
      }] : []),
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
    // v12.08 - /!\ ON EVERY CHANNEL THAT HAS A DENOMINATOR, which is now all
    // three. v12.07 gated this to Amazon because on the other two it rendered
    // a permanent dash citing `amazon_ad_spend` - but the fix for a card that
    // cannot compute is to GIVE IT ITS DENOMINATOR, not to hide it. The
    // sources follow the channel, so no tab cites another's feeds.
    ].concat(TACOS_SRC[channel] ? [{
      label: 'TACoS %',
      val: tacos.pct == null ? '—' : tacos.pct.toFixed(1) + '%',
      sub: tacos.pending ? 'reading sales\u2026'
        : tacos.pct == null
        ? 'not available'
        // /!\ THE BASIS IS IN THE SUB-LINE, not only the tooltip. On Walmart
        // and Chewy this denominator is NOT the sales figure their consoles
        // show - it is what the retailer pays us, roughly a third of retail -
        // so a reader comparing this with Amazon's TACoS has to be told.
        : 'of $' + Math.round(tacos.netSales).toLocaleString()
          + (tacos.basis === 'ourRev' ? ' sell-through' : ' net sales')
          + (tacos.narrowed ? ' \u00b7 ' + tacos.from + ' to ' + tacos.to : ''),
      color: tacos.pct == null ? 'var(--text3)'
           : (tacos.pct > 30 ? 'var(--sp-red)' : tacos.pct > 20 ? 'var(--sp-orange)' : 'var(--text)'),
      delta: (tacos.pct == null || tacosPrev.pct == null) ? null
           : chip(tacos.pct, tacosPrev.pct, false, true),
      src: TACOS_SRC[channel],
      plot: plotOf('tacos'),
      // /!\ DERIVATION ONLY. The operands, the window, and anything that
      // makes the number read high or low. Not why the basis is right, not
      // how it compares with another tab, not what attribution does to the
      // cards beside it - that belongs in CLAUDE.md, not on a hover.
      tip: tacos.pct == null
        ? tacos.why
        : tacos.basis === 'ourRev'
        ? ('Ad spend \u00f7 the channel\u2019s own sell-through: $'
           + Math.round(spendForTip).toLocaleString() + ' \u00f7 $'
           + Math.round(tacos.netSales).toLocaleString() + ', weeks '
           + tacos.from + ' to ' + tacos.to + '.'
           + '\n\nSame basis as the Amazon tab: what the shopper paid.'
           + (tacos.narrowed
              ? '\n\n\u26a0 Ads ran on ' + tacos.adDays + ' of this window\u2019s '
                + tacos.winDays + ' days, so both sides are taken over the weeks they ran. '
                + 'The whole window would divide part of the spend by all of the sales.'
              : '')
           + (tacos.ourRev > 0
              ? '\n\nOn what the retailer pays US it is '
                + ((spendForTip / tacos.ourRev) * 100).toFixed(1) + '%.'
              : ''))
        : ('Ad spend \u00f7 net sales, every ad product.'
           + '\n\nSales are weekly, so this window covers ' + tacos.from + ' to '
           + tacos.to + '.'),
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
      // v12.30 - /!\ THE NOTE IS WRITTEN WHERE THE CAMPAIGN IS. A count when
      // the row has notes, a faint + when it does not, and the composer opens
      // already scoped to this name - never a dropdown to re-pick it in.
      //
      // /!\ The FOOTER calls cellOf with no index (i < 0) and is not a
      // campaign, so it gets no affordance - the same guard the drill uses.
      let noteBtn = '';
      if (i >= 0 && !c.noCampaign && TACOS_SRC[channel] && c[NAMECOL]) {
        const n = (typeof adsNoteCountFor === 'function') ? adsNoteCountFor(channel, c[NAMECOL]) : 0;
        const _nm = String(c[NAMECOL]).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        noteBtn = `<span onclick="event.stopPropagation();adsNoteCompose('${channel}','${esc2(_nm)}')"`
          + ` title="${n ? (n + ' note' + (n === 1 ? '' : 's') + ' on this campaign. Click to add another.') : 'Add a note to this campaign'}"`
          + ` style="margin-left:7px;cursor:pointer;font-size:10px;font-family:var(--mono);`
          + `color:${n ? 'var(--sp-green,#4a9e38)' : 'var(--text3)'};opacity:${n ? 1 : .55}">`
          + `${n ? '\ud83d\udcdd' + n : '\ud83d\udcdd+'}</span>`;
      }
      return `<td${tip} style="${pad};max-width:${col.w}px;overflow:hidden;text-overflow:ellipsis${dim}">${body}${noteBtn}</td>`;
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

  // v12.08 - the TACoS denominator for the 1P channels, fetched once per
  // (channel, window) and then repainted. Guarded on the cache entry exactly
  // as the break-even above is, so it cannot loop: the entry is written
  // before the await and on every failure path.

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



// Two campaigns an ORDER OF MAGNITUDE apart, so a summed ratio and an
// averaged one are visibly different numbers.
var amazonAdSpendData = [
  { date:'2026-10-01', region:'US', campaign:'Big', ad_product:'sponsored_products',
    asin:'B1', master_id:'M1', impressions:100000, clicks:2000, spend:2000,
    purchases:200, attributed_sales:2000 },
  { date:'2026-10-08', region:'US', campaign:'Big', ad_product:'sponsored_brands',
    asin:'B1', master_id:'M1', impressions:50000, clicks:500, spend:0,
    purchases:0, attributed_sales:0 },
  { date:'2026-10-15', region:'US', campaign:'Small', ad_product:'sponsored_products',
    asin:'B2', master_id:'M2', impressions:1000, clicks:40, spend:20,
    purchases:8, attributed_sales:200 },
  { date:'2026-10-22', region:'US', campaign:'Quiet', ad_product:'sponsored_tv',
    asin:null, master_id:null, impressions:9000, clicks:0, spend:40,
    purchases:0, attributed_sales:0 },
];
// The Keywords view reads a DIFFERENT TABLE, which is what makes C1 provable.
var amazonSpSearchTermCache = [
  { reporting_month:'2026-09', reporting_date:'2026-09-30', customer_search_term:'catnip spray',
    match_type:'broad', campaign_name:'SP - Auto', ad_group_name:'AG1', asin:'B1',
    impressions:500, clicks:20, spend:30, orders_7d:2, units_7d:3, sales_7d:60 },
  { reporting_month:'2026-10', reporting_date:'2026-10-31', customer_search_term:'catnip spray',
    match_type:'exact', campaign_name:'SP - KW', ad_group_name:'AG2', asin:'B1',
    impressions:800, clicks:40, spend:70, orders_7d:6, units_7d:7, sales_7d:300 },
  { reporting_month:'2026-10', reporting_date:'2026-10-31', customer_search_term:'cat toys',
    match_type:'broad', campaign_name:'SP - Auto', ad_group_name:'AG1', asin:'B2',
    impressions:200, clicks:5, spend:9, orders_7d:0, units_7d:0, sales_7d:0 },
];
var pnlRegion = 'US';
const W = { from:'2026-10-01', to:'2026-10-31' };
const run = (opts) => adsCampaignRollup(Object.assign(
  { channel:'amazon', from:W.from, to:W.to, regionOk:false }, opts || {}));


const out = {};

// ── A1 the pre-v11.23 hand-written total loop, reproduced verbatim ────────
function oldTotals(campaigns, GROUP) {
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
  return adsDeriveRow(t, GROUP);
}
const plain = (o) => JSON.stringify(o, (k, v) =>
  (v instanceof Set) ? [...v].sort() : v);

const base = run();
// v11.25 - the old loop knew nothing of inStoreSales / dpv / atc, so a
// whole-object compare now differs on SHAPE while every number matches.
// Compared field by field instead, which is what the label claims.
const OLD_FIELDS = ['campaign', 'impressions', 'clicks', 'spend', 'orders',
                    'units', 'sales', 'ntb', 'signups', 'hasUnits', 'hasNtb',
                    'types', 'statuses', 'skuSet', 'matches', 'campaigns',
                    'adgroups', 'firstDate', 'lastDate', 'skus', 'cvr', 'ctr',
                    'cpc', 'cpa', 'roas', 'acos', 'type', 'status'];
const pick = (o) => plain(Object.fromEntries(OLD_FIELDS.map(k => [k, o[k]])));
const oldT = oldTotals(base.campaigns.map(c => c), 'campaign');
out.oldVsNew = pick(oldT) === pick(base.totals);
out.oldVsNewDiff = OLD_FIELDS.filter(k => plain(oldT[k]) !== plain(base.totals[k]));
// /!\ The slots a non-Walmart channel does not report must be NULL, never 0.
out.amzInStore = base.totals.inStoreSales;
out.amzOmni    = base.totals.omniRoas;
out.amzDpv     = base.totals.dpv;
out.amzAtc     = base.totals.atc;
out.totalSpend = base.totals.spend;
out.totalRoas  = +base.totals.roas.toFixed(4);

// ── A2 unbucketed vs bucketed ─────────────────────────────────────────────
const noB = run();
const wkB = run({ bucket: 'week' });
out.noSeriesKey   = !('series'  in noB);
out.noBucketsKey  = !('buckets' in noB);
out.hasSeriesKey  = ('series' in wkB) && ('buckets' in wkB);
const strip = (o) => { const c = Object.assign({}, o); delete c.series; delete c.buckets; return plain(c); };
out.bucketIsAdditive = strip(noB) === strip(wkB);

// ── B selection arithmetic ────────────────────────────────────────────────
const big   = base.campaigns.find(c => c.campaign === 'Big');
const small = base.campaigns.find(c => c.campaign === 'Small');
out.bigRoas   = +big.roas.toFixed(4);
out.smallRoas = +small.roas.toFixed(4);
out.meanRoas  = +((big.roas + small.roas) / 2).toFixed(4);
const selBoth = adsSumRows([big, small], 'campaign');
out.selRoas   = +selBoth.roas.toFixed(4);
out.selSpend  = selBoth.spend;
out.selSkus   = selBoth.skus;
const selOne  = adsSumRows([small], 'campaign');
out.oneSpend  = selOne.spend;
out.oneRoas   = +selOne.roas.toFixed(4);
const selNone = adsSumRows([], 'campaign');
out.noneShape = { spend: selNone.spend, roas: selNone.roas, ctr: selNone.ctr,
                  bad: /NaN|Infinity/.test(JSON.stringify(selNone)) };

// ── C the prior period dropped the view and the filters ───────────────────
const kwNow  = adsCampaignRollup({ channel:'amazon', view:'keywords', from:W.from, to:W.to, regionOk:false });
const oldPrev = adsCampaignRollup({ channel:'amazon', from:W.from, to:W.to, regionOk:false });
out.kwSpend      = kwNow.totals.spend;
out.oldPrevSpend = oldPrev.totals.spend;
out.kwReadsOtherTable = kwNow.totals.spend !== oldPrev.totals.spend;

const filt    = run({ filters: { type: new Set(['Sponsored Products']) } });
const unfilt  = run();
out.filtSpend   = filt.totals.spend;
out.unfiltSpend = unfilt.totals.spend;

// ── D the monthly prior block, through the REAL renderer code ─────────────
// A 15-day window inside one month: shifting it back 15 days lands in the
// SAME month, which is the bug.
function prevFor(view, win, res) {
  const ch = adsViewCfg('amazon', view);
  const channel = 'amazon', brand = '', picked = {};
  // v11.68 - the block now asks for the same bucket grain the chart resolved,
  // so the prior rollup carries a SERIES and not just totals. Supplied here
  // the way every other local this slice reads is (the v11.51 pattern); what
  // D asserts is still the monthly prior WINDOW, which the grain cannot move.
  const grain = adsGrain(win, ch);
  let __out = null;
  (function () {
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

    __out = prev;
  })();
  return __out;
}
const kwMid = adsCampaignRollup({ channel:'amazon', view:'keywords',
  from:'2026-10-15', to:'2026-10-29', regionOk:false });
out.kwMidMonths = kwMid.coverage.months;
const kwPrev = prevFor('keywords', { from:'2026-10-15', to:'2026-10-29' }, kwMid);
out.kwPrevMonths = kwPrev ? kwPrev.coverage.months : null;
out.kwPrevWindow = kwPrev ? [kwPrev.coverage.from, kwPrev.coverage.to] : null;
// the naive day-shift, reproduced
const d0 = new Date('2026-10-15T00:00:00'), d1 = new Date('2026-10-29T00:00:00');
const len = Math.round((d1 - d0) / 86400000) + 1;
const nTo = new Date(d0.getTime() - 86400000);
const nFrom = new Date(nTo.getTime() - (len - 1) * 86400000);
const naive = adsCampaignRollup({ channel:'amazon', view:'keywords',
  from: adsYmd(nFrom), to: adsYmd(nTo), regionOk:false });
out.naivePrevMonths = naive.coverage.months;

// a daily view still gets the day-shifted block
const dayPrev = prevFor('', { from:'2026-10-15', to:'2026-10-29' }, run());
out.dayPrevWindow = dayPrev ? [dayPrev.coverage.from, dayPrev.coverage.to] : null;

// ── F bucketing ───────────────────────────────────────────────────────────
const chAmz = adsViewCfg('amazon', '');
const chKw  = adsViewCfg('amazon', 'keywords');
out.grain14  = adsGrain({ from:'2026-10-01', to:'2026-10-14' }, chAmz);
out.grain180 = adsGrain({ from:'2026-05-01', to:'2026-10-27' }, chAmz);
out.grain500 = adsGrain({ from:'2025-06-01', to:'2026-10-13' }, chAmz);
out.grainKw  = adsGrain({ from:'2026-10-01', to:'2026-10-14' }, chKw);
out.grainNoWin = adsGrain({}, chAmz);

const wk = run({ bucket:'week' });
out.weekBuckets = wk.buckets;
out.allSundays  = wk.buckets.every(b => new Date(b + 'T00:00:00').getDay() === 0);
// the series must sum back to the campaign totals, or the chart and the
// table are describing different data
out.seriesMatchesTable = base.campaigns.every(c => {
  const by = wk.series[c.campaign] || {};
  const sum = Object.values(by).reduce((a, s) => a + s.spend, 0);
  return Math.abs(sum - c.spend) < 1e-9;
});
const dayR = run({ bucket:'day' });
out.dayBuckets = dayR.buckets;
const kwB = adsCampaignRollup({ channel:'amazon', view:'keywords', from:W.from, to:W.to,
  regionOk:false, bucket:'day' });
out.kwBuckets = kwB.buckets;   // a monthly feed buckets by MONTH whatever is asked

// ── G partial edge buckets ────────────────────────────────────────────────
out.edgesDay  = adsBucketEdges(dayR.buckets, 'day', W);
out.edgesWeek = adsBucketEdges(wk.buckets, 'week', W);
// a window that starts AND ends on a week boundary has no partial edge
out.edgesAligned = adsBucketEdges(['2026-10-04','2026-10-11'], 'week',
  { from:'2026-10-04', to:'2026-10-17' });

// ── H metrics from the registry ───────────────────────────────────────────
const mAmz = adsChartMetrics(ADS_COLUMNS.amazon).map(m => m.k);
const mChw = adsChartMetrics(ADS_COLUMNS.chewy).map(m => m.k);
const mKw  = adsChartMetrics(adsViewCfg('amazon','keywords').columns).map(m => m.k);
out.mAmz = mAmz; out.mChw = mChw; out.mKw = mKw;
const roas = adsChartMetrics(ADS_COLUMNS.amazon).find(m => m.k === 'roas');
out.roasSpec = { unit: roas.unit, noStack: !!roas.noStack, isPct: !!roas.isPct };
const acos = adsChartMetrics(ADS_COLUMNS.amazon).find(m => m.k === 'acos');
out.acosSpec = { unit: acos.unit, noStack: !!acos.noStack, isPct: !!acos.isPct };
// derived from a SUMMED slot, never averaged
out.roasOfSum = roas.sum({ spend: 100, sales: 400 });
out.roasOfZero = roas.sum({ spend: 0, sales: 400 });
out.ctrOfSum = +adsChartMetrics(ADS_COLUMNS.amazon).find(m => m.k === 'ctr')
  .sum({ clicks: 25, impressions: 1000 }).toFixed(4);

// ── I the exporter's old text rule ────────────────────────────────────────
const f2 = (v) => v == null ? '' : Number(v).toFixed(2);
const i0 = (v) => v == null ? '' : String(Math.round(Number(v)));
const oldVal = (c, k) => {
  if (k === 'campaign' || k === 'type' || k === 'status') return c[k] || '';
  if (k === 'spend' || k === 'sales' || k === 'cpc' || k === 'cpa'
      || k === 'ctr' || k === 'acos' || k === 'roas') return f2(c[k]);
  return i0(c[k]);
};
const newVal = (c, k) => {
  const v = c[k];
  if (typeof v === 'string') return v;
  if (v == null) return '';
  if (k === 'spend' || k === 'sales' || k === 'cpc' || k === 'cpa'
      || k === 'ctr' || k === 'acos' || k === 'roas') return f2(v);
  return i0(v);
};
const kwRow = kwNow.campaigns.find(c => c.term === 'catnip spray');
// A WIDER window, so the same term's two match types merge into one row and
// the joined list is a real string rather than a single value.
const kwWide = adsCampaignRollup({ channel:'amazon', view:'keywords',
  from:'2026-09-01', to:'2026-10-31', regionOk:false });
const kwWideRow = kwWide.campaigns.find(c => c.term === 'catnip spray');
out.wideValMatch = newVal(kwWideRow, 'match');
out.wideValSpend = newVal(kwWideRow, 'spend');
out.wideOldMatch = oldVal(kwWideRow, 'match');
out.oldValTerm  = oldVal(kwRow, 'term');
out.oldValMatch = oldVal(kwRow, 'match');
out.newValTerm  = newVal(kwRow, 'term');
out.newValMatch = newVal(kwRow, 'match');
out.newValSpend = newVal(kwRow, 'spend');

// ── J the search haystack ─────────────────────────────────────────────────
const hay = (c, COLS) => COLS.map(col => c[col.k])
  .filter(v => typeof v === 'string').join(' ').toLowerCase();
const oldHay = (c) => (c.campaign + ' ' + c.type + ' ' + c.status).toLowerCase();
out.oldHayFindsTerm = oldHay(kwRow).indexOf('catnip spray') > -1;
out.newHayFindsTerm = hay(kwRow, adsViewCfg('amazon','keywords').columns).indexOf('catnip spray') > -1;

console.log(JSON.stringify(out));
