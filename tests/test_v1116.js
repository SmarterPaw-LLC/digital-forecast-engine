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
  const ch = ADS_CHANNELS[o.channel];
  if (!ch) return null;
  const from = o.from || null, to = o.to || null;
  const brand = o.brand || '';
  const rows = o.rows || ch.rows();
  const agg = new Map();
  let scanned = 0, inWindow = 0;
  for (const raw of rows) {
    scanned++;
    const d = String(raw[ch.dateField] || '');
    if (from && d < from) continue;
    if (to && d > to) continue;
    if (o.regionOk !== false && typeof ch.regionOk === 'function' && !ch.regionOk(raw)) continue;
    const r = ch.map(raw);
    if (brand && String(r.brand || '') !== brand) continue;
    inWindow++;
    const name = r.campaign || ADS_NO_CAMPAIGN;
    let c = agg.get(name);
    if (!c) {
      c = { campaign: name, noCampaign: !r.campaign, types: new Set(), statuses: new Set(),
            skuSet: new Set(), impressions: 0, clicks: 0, spend: 0, orders: 0,
            units: 0, sales: 0, ntb: 0, signups: 0,
            hasUnits: false, hasNtb: false, firstDate: d, lastDate: d };
      agg.set(name, c);
    }
    if (r.type)   c.types.add(r.type);
    if (r.status) c.statuses.add(r.status);
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
    c.skus   = c.skuSet.size;
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
    coverage: {
      scanned, inWindow, from, to, brand,
      campaignCount: campaigns.filter(c => !c.noCampaign).length,
      noCampaignSpend: noCamp ? noCamp.spend : 0,
      noCampaignPct: t.spend > 0 && noCamp ? (100 * noCamp.spend / t.spend) : 0,
    },
  };
}

// Sort + search state, per channel so switching P&L pages does not reset the
// other one. Default: biggest spender first, which is the order anyone opening
// an ads page is looking for.
const _adsState = {
  amazon: { sortK: 'spend', sortDir: -1 },
  chewy:  { sortK: 'spend', sortDir: -1 },
};
let _adsExport = { amazon: null, chewy: null };

function adsSortBy(channel, k) {
  const st = _adsState[channel]; if (!st) return;
  if (st.sortK === k) st.sortDir = -st.sortDir;
  else { st.sortK = k; st.sortDir = (k === 'campaign' || k === 'type' || k === 'status') ? 1 : -1; }
  renderAdsCampaigns(channel);
}
function adsSearchChanged(channel) { renderAdsCampaigns(channel); }

// ⚠ The shell is built ONCE per host and then only repainted. Re-emitting the
// controls on every render would blow away the search box's focus and caret
// mid-keystroke — the v10.99 "do not rewrite the field while you type" rule,
// applied to the whole control row.
function adsEnsureShell(channel) {
  const ch = ADS_CHANNELS[channel]; if (!ch) return null;
  const host = document.getElementById(ch.host + '-host');
  if (!host) return null;
  if (host.dataset.built) return host;
  const brandPicker = channel === 'chewy'
    ? `<select id="chads-brand" onchange="renderAdsCampaigns('chewy')" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:4px 8px"><option value="">All Brands</option></select>`
    : '';
  host.innerHTML =
      `<div id="${ch.host}-freshness" style="margin-bottom:10px"></div>`
    + `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px">`
    +   `<input type="text" id="${ch.host}-search" placeholder="Search campaign, type or status…" oninput="adsSearchChanged('${channel}')" autocomplete="off" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:5px 10px;width:260px">`
    +   brandPicker
    +   `<label style="font-family:var(--mono);font-size:11px;color:var(--text2);cursor:pointer" title="Campaigns with no spend in this window. Hidden by default because a long tail of paused campaigns buries the ones actually running.">`
    +     `<input type="checkbox" id="${ch.host}-zero" onchange="renderAdsCampaigns('${channel}')"> show zero-spend</label>`
    +   `<button onclick="downloadAdsCampaignsCSV('${channel}')" style="font-family:var(--mono);font-size:11px;background:var(--surface2);color:var(--text2);border:1px solid var(--border2);border-radius:6px;padding:5px 12px;cursor:pointer">↓ CSV</button>`
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

function renderAdsCampaigns(channel) {
  const ch = ADS_CHANNELS[channel]; if (!ch) return;
  if (!adsEnsureShell(channel)) return;
  const COLS = ADS_COLUMNS[channel];
  if (typeof renderPageFreshness === 'function') {
    renderPageFreshness(ch.host + '-freshness', ch.freshness).catch(console.warn);
  }

  const win = ch.range() || {};
  const brand = ch.brand();
  const res = adsCampaignRollup({ channel, from: win.from, to: win.to, brand });
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
  _adsExport[channel] = { res, win, brand, channel };

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
      { label: 'Ad Spend', val: $0(t.spend), sub: res.coverage.campaignCount + ' campaign' + (res.coverage.campaignCount === 1 ? '' : 's'),
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
  const st = _adsState[channel];
  const th = document.getElementById(ch.host + '-thead');
  if (th) th.innerHTML = COLS.map(c => {
    const arrow = st.sortK === c.k ? (st.sortDir < 0 ? ' ▼' : ' ▲') : '';
    return `<th onclick="adsSortBy('${channel}','${c.k}')" title="${esc2(c.tip || c.label)}"`
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
  const cellOf = (c, col) => {
    const v = c[col.k];
    const pad = `padding:5px 8px;text-align:${col.align};white-space:nowrap`;
    if (col.k === 'campaign') {
      // The no-campaign bucket is DIMMED AND NAMED, not hidden, and says why.
      const dim = c.noCampaign ? ';color:var(--text3);font-style:italic' : '';
      const tip = c.noCampaign
        ? ' title="Spend uploaded before the Campaign name column existed. Re-upload this window from Amazon Ads → Reports with Campaign name as a dimension to fill it in."'
        : ` title="${esc2(c.campaign)}"`;
      return `<td${tip} style="${pad};max-width:${col.w}px;overflow:hidden;text-overflow:ellipsis${dim}">${esc2(c.campaign)}</td>`;
    }
    if (col.k === 'type' || col.k === 'status') {
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
            ? 'No campaigns with spend in this window.'
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
    shown.campaign = list.length + ' row' + (list.length === 1 ? '' : 's');
    shown.type = ''; shown.status = '';
    tf.innerHTML = COLS.map(col => {
      if (col.k === 'campaign') return `<td style="padding:6px 8px;text-align:left;font-family:var(--mono);font-size:11px;border-top:1px solid var(--border2)">${esc2(shown.campaign)}</td>`;
      const c = cellOf(shown, col);
      return c.replace('<td', '<td').replace('style="padding:5px 8px', 'style="padding:6px 8px;border-top:1px solid var(--border2)');
    }).join('');
  }

  const cov = document.getElementById(ch.host + '-cov');
  if (cov) {
    const parts = [];
    parts.push((win.from || 'start') + ' → ' + (win.to || 'today'));
    if (brand) parts.push(brand);
    parts.push(res.coverage.campaignCount + ' campaign' + (res.coverage.campaignCount === 1 ? '' : 's'));
    parts.push($0(t.spend) + ' spend');
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
function downloadAdsCampaignsCSV(channel) {
  const snap = _adsExport[channel];
  const ch = ADS_CHANNELS[channel];
  if (!snap || !ch || !snap.res) {
    alert('No ' + (ch ? ch.label : 'ads') + ' data to export — open the Ads tab and let it render first.');
    return;
  }
  const { res, win, brand } = snap;
  const COLS = ADS_COLUMNS[channel];
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
  lines.push('# ' + res.coverage.campaignCount + ' named campaign'
    + (res.coverage.campaignCount === 1 ? '' : 's') + ' · '
    + res.campaigns.length + ' rows including the no-campaign bucket');
  if (res.coverage.noCampaignSpend > 0) {
    lines.push('# ' + res.coverage.noCampaignSpend.toFixed(2) + ' of spend ('
      + res.coverage.noCampaignPct.toFixed(1) + '%) has no campaign on record - uploaded '
      + 'before the Campaign name column existed. Included in the TOTAL, not dropped.');
  }
  lines.push(COLS.map(c => c.label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')).join(','));
  for (const c of res.campaigns) lines.push(COLS.map(col => esc(val(c, col.k))).join(','));
  lines.push(COLS.map((col, i) => i === 0 ? 'TOTAL' : esc(val(res.totals, col.k))).join(','));

  const name = promptCsvName('smarterpaw-ads-' + channel + '-campaigns-'
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
async function loadAdsCampaigns(channel) {
  const ch = ADS_CHANNELS[channel]; if (!ch) return;
  adsEnsureShell(channel);
  const tb = document.getElementById(ch.host + '-tbody');
  if (tb && !tb.innerHTML) {
    tb.innerHTML = `<tr><td colspan="${ADS_COLUMNS[channel].length}" style="text-align:center;padding:24px;color:var(--text3);font-family:var(--mono);font-size:11px">⏳ Loading ${ch.label}…</td></tr>`;
  }
  try {
    if (channel === 'amazon' && typeof loadAmazonAdSpend === 'function') await loadAmazonAdSpend();
    if (channel === 'chewy') {
      if (typeof loadChewyAdSpend === 'function') await loadChewyAdSpend();
      adsFillChewyBrands();
    }
    renderAdsCampaigns(channel);
  } catch (e) {
    if (tb) tb.innerHTML = `<tr><td colspan="${ADS_COLUMNS[channel].length}" style="text-align:center;padding:24px;color:var(--sp-red,#d63f2a);font-family:var(--mono);font-size:11px">✗ ${esc2(e.message || e)}</td></tr>`;
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
