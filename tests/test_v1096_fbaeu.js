
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

function mkEl(id) {
  return {
    id, _text: '', children: [], style: {}, className: '', title: '',
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); this.children = []; },
    appendChild(c) { this.children.push(c); return c; },
    querySelector(sel) {
      const cls = sel.replace('.', '');
      return this.children.find(c => (c.className || '') === cls) || null;
    },
  };
}
const ELS = {};
const document = {
  getElementById: (id) => (ELS[id] || (ELS[id] = mkEl(id))),
  createElement: () => mkEl('new'),
};
function txt(id) { return (ELS[id] || {})._text || ''; }
function reset() { for (const k of Object.keys(ELS)) delete ELS[k]; }

const AMAZON_BR_REGIONS = [
  { code: 'US' }, { code: 'CA' }, { code: 'MX' }, { code: 'GB' }, { code: 'DE' },
  { code: 'FR' }, { code: 'IT' }, { code: 'ES' }, { code: 'NL' }, { code: 'AU' }, { code: 'JP' },
];
const FBA_REGION_OPTIONS = [{ code: 'US' }, { code: 'CA' }, { code: 'MX' }, { code: 'EU/UK' }, { code: 'AU' }, { code: 'JP' }];
const EU_REGIONS = new Set(['GB', 'DE', 'FR', 'IT', 'ES', 'NL']);
function walmartWeekToDate(c) { const y = Math.floor(c / 100), w = c % 100; const d = new Date(y, 0, 3); d.setDate(d.getDate() + (w - 1) * 7); return d; }
function updateShopifyReportLink() {}
function dzRecentInvalidate() {}
function renderAllDzRecentUploads() {}

let WARNED = [];
const _warn = console.warn;
console.warn = (...a) => { WARNED.push(a.map(String).join(' ')); };

const DB_MAX_ROWS = 1000;
let TABLES = {};
function builder(table) {
  const b = { table, _f: [], _order: null, _asc: true, _from: 0, _to: null };
  b.select = () => b;
  b.eq  = (c, v) => { b._f.push(['eq', c, v]);  return b; };
  b.gt  = (c, v) => { b._f.push(['gt', c, v]);  return b; };
  b.lt  = (c, v) => { b._f.push(['lt', c, v]);  return b; };
  b.gte = (c, v) => { b._f.push(['gte', c, v]); return b; };
  b.order = (c, o) => { b._order = c; b._asc = !!(o && o.ascending); return b; };
  b.limit = (n) => { b._from = 0; b._to = n - 1; return b; };
  b.range = (a, z) => { b._from = a; b._to = z; return b; };
  b._exec = async () => {
    let rows = TABLES[table] || null;
    if (rows === null) return { data: null, error: { message: 'missing' } };
    rows = rows.slice();
    for (const [op, c, v] of b._f) {
      if (op === 'eq')  rows = rows.filter(r => r[c] === v);
      if (op === 'gt')  rows = rows.filter(r => r[c] >  v);
      if (op === 'lt')  rows = rows.filter(r => r[c] <  v);
      if (op === 'gte') rows = rows.filter(r => r[c] >= v);
    }
    if (b._order) { const c = b._order, sg = b._asc ? 1 : -1; rows.sort((x, y) => (x[c] < y[c] ? -1 : x[c] > y[c] ? 1 : 0) * sg); }
    const to = (b._to == null) ? rows.length - 1 : b._to;
    const want = to - b._from + 1;
    return { data: rows.slice(b._from, b._from + Math.min(want, DB_MAX_ROWS)), error: null };
  };
  b.then = (res, rej) => b._exec().then(res, rej);
  return b;
}
async function getSB() { return { from: (t) => builder(t) }; }

// One row per ASIN per snapshot - the shape that made .limit(10) hopeless.
function snaps(spec) {
  const rows = [];
  for (const [region, date, n] of spec)
    for (let i = 0; i < (n || 400); i++) rows.push({ snapshot_date: date, region, asin: region + i });
  return rows;
}
function setTables(fba) {
  TABLES = { sku_economics: [], sku_economics_eu: [], walmart_sales_weekly: [], fba_inventory_snapshots: fba };
}

async function refreshUploadDataRanges() {
  // ⚠ v10.95 - `sb` MUST live at FUNCTION scope. It used to be declared
  // `const sb = await getSB()` INSIDE the try block below - a nested block
  // scope - so the helpers defined out here (findWeeklyGaps, and the v10.95
  // per-region probes) could not see it and every call threw ReferenceError
  // straight into its own catch. That is why the v8.72 gap audit reported
  // "no gaps" for every table since the day it shipped: valid JavaScript,
  // clean `node --check`, dead at runtime - the v10.8 called-but-undefined
  // class. Do not re-declare it inside a block.
  let sb = null;
  const setLast = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
  // v7.04 — invalidate the "📥 Last report" cache on every upload cycle so
  // switching to that preset after a fresh SKU Economics upload shows the
  // new range instead of the stale one. Cheap — the cache repopulates on
  // the next resolvePnlLastReport() call.
  if (typeof _pnlLastReportCache !== 'undefined') _pnlLastReportCache.clear();
  // week_start is always stored as a MONDAY. The data window's END day
  // depends on the channel's reporting convention:
  //   • Amazon SKU Economics runs Sunday→Saturday. The parser maps that
  //     Sun-Sat week onto the Monday of the overlapping Mon-Sun week
  //     (v4.91), so the report's actual Saturday end = week_start + 5.
  //   • Shopify genuinely runs Monday→Sunday → end = week_start + 6.
  const endOfWeek = (mondayStr, offset) => {
    if (!mondayStr) return '';
    const d = new Date(mondayStr + 'T00:00:00');
    d.setDate(d.getDate() + (offset == null ? 6 : offset));
    return d.toISOString().slice(0, 10);
  };
  // Short relative-date for the group-level rollup row.
  const relDays = (dateStr) => {
    if (!dateStr) return null;
    const d = new Date(dateStr + 'T00:00:00');
    const days = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (days <= 0) return 'today';
    if (days === 1) return 'yesterday';
    if (days < 7) return `${days}d ago`;
    if (days < 30) return `${Math.floor(days/7)}w ago`;
    return `${Math.floor(days/30)}mo ago`;
  };
  // v6.87 — unified relative-time formatter for "uploaded X ago" lines.
  // Same human cadence as relDays (today / yesterday / Nd ago / Nw ago / Nmo
  // ago) but keyed off a timestamptz (uploaded_at) instead of a date string,
  // so we can show minutes/hours when it really did just happen.
  const ago = (ts) => {
    if (!ts) return null;
    const t = new Date(ts).getTime(); if (!Number.isFinite(t)) return null;
    const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
    if (sec < 60)        return 'just now';
    if (sec < 3600)      return `${Math.floor(sec/60)}m ago`;
    if (sec < 86400)     return `${Math.floor(sec/3600)}h ago`;
    if (sec < 86400*7)   return `${Math.floor(sec/86400)}d ago`;
    if (sec < 86400*30)  return `${Math.floor(sec/86400/7)}w ago`;
    return `${Math.floor(sec/86400/30)}mo ago`;
  };
  // v6.87 — every card now uses the SAME two-fact format:
  //   📅 Data thru {date} · uploaded {ago}
  // so the user can scan all rows for "is this fresh?" at a glance.
  // dataThru is whatever the table's natural latest-data field is (Saturday
  // week-end for weekly tables, the literal date for daily, last day of
  // month for tracker). uploadedAt is the table's max(uploaded_at).
  const renderCardFreshness = (id, dataThru, uploadedAt, emptyText) => {
    if (!dataThru && !uploadedAt) { setLast(id, emptyText); return; }
    const a = ago(uploadedAt);
    setLast(id, `📅 Data thru ${dataThru || '—'} · uploaded ${a || '—'}`);
  };
  // v10.95 — the DISTINCT values of a date-ish column inside a window, read
  // by keyset paging instead of a newest-N-rows sample.
  //
  // Each round trip takes the newest PAGE rows below the cursor, records
  // every value in them, then drops the cursor BELOW the oldest value it
  // saw - so the remaining rows carrying that value are never fetched.
  // Distinct values is all a gap audit needs, so the walk costs round trips
  // per DISTINCT VALUE at worst, never per row, and it ends only when the
  // data inside the window runs out.
  //
  // `complete: false` means the walk stopped early, so the caller inspected
  // a SHORTER window than it asked for. Both gap audits route through here,
  // rather than each keeping its own row sample (hard rule #1).
  const distinctValuesInWindow = async (table, col, cutoff, extraFilter) => {
    const PAGE = 1000, MAX_PAGES = 40;
    const seen = new Set();
    let cursor = null, complete = false;
    for (let pageNo = 0; pageNo < MAX_PAGES; pageNo++) {
      let q = sb.from(table).select(col);
      if (cutoff != null) q = q.gte(col, cutoff);
      if (cursor != null) q = q.lt(col, cursor);
      if (extraFilter) q = extraFilter(q);
      const { data, error } = await q.order(col, { ascending: false }).range(0, PAGE - 1);
      if (error || !data || !data.length) { complete = !error; break; }
      for (const r of data) { if (r[col] != null) seen.add(r[col]); }
      if (data.length < PAGE) { complete = true; break; }
      const oldest = data[data.length - 1][col];
      if (oldest == null || oldest === cursor) break;   // no progress - bail rather than spin
      cursor = oldest;
    }
    if (!complete) console.warn(`distinctValuesInWindow(${table}.${col}): stopped before the window was read - gaps may be under-reported`);
    // Numeric columns (Walmart's yyyyww) must sort numerically, not as text.
    const values = [...seen].sort((a, b) =>
      (typeof a === 'number' && typeof b === 'number') ? a - b : String(a).localeCompare(String(b)));
    return { values, complete };
  };
  // v10.95 — the distinct values of a plain column, without a DISTINCT
  // (PostgREST has none). Keyset walk: ask for the smallest value ABOVE the
  // last one seen, one row at a time, until nothing is above it. Costs a
  // round trip per distinct value instead of one per 1000 rows - and, the
  // whole point, it cannot truncate the way a row window does.
  //
  // Every per-region card gets its region list from HERE rather than from a
  // hardcoded array, so a region nobody has uploaded before appears on its
  // card without a code change.
  const distinctColumnValues = async (table, col, cap = 40) => {
    const out = [];
    let last = null;
    for (let i = 0; i < cap; i++) {
      let q = sb.from(table).select(col);
      if (last !== null) q = q.gt(col, last);
      const { data, error } = await q.order(col, { ascending: true }).limit(1);
      if (error || !data || !data.length) break;
      const v = data[0][col];
      // A null (Postgres sorts those last on ASC) or a repeat means there is
      // nothing above the cursor - stop rather than spin.
      if (v == null || v === last) break;
      out.push(v);
      last = v;
    }
    if (out.length === cap) console.warn(`distinctColumnValues(${table}.${col}): hit the ${cap} cap - the list may be short`);
    return out;
  };
  // v10.95 — what ORDER the region chips print in. The SET always comes from
  // the data (distinctColumnValues); this only ranks it, so an unrecognised
  // region sorts after the known marketplaces instead of being dropped.
  // Reuses the app's own marketplace ladders rather than writing a third
  // region list (design-pattern hard rule #1).
  const regionDisplayOrder = (regions) => {
    const ladder = []
      .concat(typeof AMAZON_BR_REGIONS  !== 'undefined' ? AMAZON_BR_REGIONS.map(r => r.code)  : [])
      .concat(typeof FBA_REGION_OPTIONS !== 'undefined' ? FBA_REGION_OPTIONS.map(r => r.code) : []);
    const rank = (r) => { const i = ladder.indexOf(r); return i < 0 ? ladder.length : i; };
    return [...regions].sort((a, b) => rank(a) - rank(b) || String(a).localeCompare(String(b)));
  };
  // v10.95 — the newest date for ONE region: the v10.89 per-view probe shape
  // (`.eq()` + `.limit(1)`). The SERVER picks the max, so there is no row
  // window to truncate and a region that skipped the newest week still
  // reports its own latest.
  const latestDateForRegion = async (table, dateCol, region) => {
    const { data, error } = await sb.from(table).select(dateCol)
      .eq('region', region).order(dateCol, { ascending: false }).limit(1);
    if (error || !data || !data.length) return null;
    const v = data[0][dateCol];
    return v == null ? null : String(v).slice(0, 10);
  };
  // v10.95 — max(uploaded_at) for a table, which is what every card's
  // "uploaded X ago" has always meant. One probe, no region needed.
  const latestUploadedAt = async (table) => {
    const { data, error } = await sb.from(table)
      .select('uploaded_at').order('uploaded_at', { ascending: false }).limit(1);
    if (error || !data || !data.length) return null;
    return data[0].uploaded_at;
  };
  // v10.95 — [[region, 'YYYY-MM-DD'], ...] in display order, regions with
  // no data left out. The three cards that print `REG: date · REG: date` all
  // build their line from this one walk.
  const latestByRegion = async (table, dateCol) => {
    const regions = regionDisplayOrder(await distinctColumnValues(table, 'region'));
    const out = [];
    for (const reg of regions) {
      const d = await latestDateForRegion(table, dateCol, reg);
      if (d) out.push([reg, d]);
    }
    return out;
  };
  // v8.72 — Missing-week gap detection. Query all week_start values back to
  // maxWeeksBack, compute the expected Monday sequence between min and max
  // dates in the data, and return whichever expected Mondays are absent.
  // Weekly grain — daily grain (Shopify, Amazon Ads non-SP) is skipped
  // because the user genuinely might not sell every day.
  const findWeeklyGaps = async (table, dateCol, extraFilter, maxWeeksBack = 26) => {
    try {
      const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - maxWeeksBack * 7);
      const cutoffStr = `${cutoff.getFullYear()}-${String(cutoff.getMonth() + 1).padStart(2, '0')}-${String(cutoff.getDate()).padStart(2, '0')}`;
      // ⚠ v10.95 - this asked for `.limit(500)` and called the result 26
      // weeks. sku_economics carries ~500 ASINs per week, so 500 newest rows
      // covered ONE week: the audit silently inspected a one-week window and
      // under-reported every gap outside it. Architecture Rule #4, the same
      // class as the v10.92 rail - a ROW window read as a DATE window.
      const { values } = await distinctValuesInWindow(table, dateCol, cutoffStr, extraFilter);
      const weeks = [...new Set(values.map(v => String(v).slice(0, 10)))].sort();
      if (weeks.length < 2) return { missing: [], latest: weeks[weeks.length - 1] || null, first: weeks[0] || null };
      const missing = [];
      const start = new Date(weeks[0] + 'T00:00:00');
      const end = new Date(weeks[weeks.length - 1] + 'T00:00:00');
      const have = new Set(weeks);
      for (let d = new Date(start); d.getTime() <= end.getTime(); d.setDate(d.getDate() + 7)) {
        const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        if (!have.has(ymd)) missing.push(ymd);
      }
      return { missing, latest: weeks[weeks.length - 1], first: weeks[0] };
    } catch (_) { return { missing: [], latest: null, first: null }; }
  };
  // v8.72 — Render a "⚠ N gaps" chip next to the group's Latest Data label
  // when weekly gaps exist. Full missing list surfaces in the hover title.
  const appendGapChip = (groupId, gaps) => {
    const el = document.getElementById(groupId); if (!el) return;
    if (!gaps || !gaps.length) return;
    const preview = gaps.slice(0, 8).join(', ') + (gaps.length > 8 ? `, +${gaps.length - 8} more` : '');
    const chip = document.createElement('span');
    chip.style.cssText = 'margin-left:8px;padding:2px 7px;background:rgba(232,96,26,.14);color:var(--sp-orange);border:1px solid var(--sp-orange);border-radius:4px;font-family:var(--mono);font-size:10px;font-weight:700;cursor:help';
    chip.textContent = `⚠ ${gaps.length} gap${gaps.length === 1 ? '' : 's'}`;
    chip.title = `Missing week_start values in the last 26 weeks (between first + latest data):\n${gaps.join('\n')}\n\nRe-upload the report for these weeks.`;
    el.appendChild(chip);
  };
  try {
    sb = await getSB();
    // ── SKU Economics US/CA — latest week per region.
    // ⚠ v10.95 - this was ONE `.select('week_start, region, uploaded_at')`
    //   ordered week_start desc with `.limit(200)`, walked for the first row
    //   per region. sku_economics carries ~500 ASINs per week, so all 200
    //   rows can belong to a SINGLE week - and a region that skipped that
    //   week then read as having NO DATA AT ALL, on a card whose entire job
    //   is to say whether a region is up to date. One probe per region now.
    let amzUsCaLatest = null;
    const amzUsCaGaps = [];
    const sePairs = await latestByRegion('sku_economics', 'week_start');
    if (sePairs.length) {
      amzUsCaLatest = sePairs.map(([, wk]) => wk).sort().reverse()[0];
      const parts = sePairs.map(([reg, wk]) => `${reg}: thru Sat ${endOfWeek(wk, 5)}`);
      const lastUp = await latestUploadedAt('sku_economics');
      setLast('last-sales-skuecon', `📅 Data ${parts.join(' · ')} · uploaded ${ago(lastUp) || '—'}`);
      // v8.72 — per-region gap scan for SKU Economics US/CA.
      // ⚠ v10.95 - the chip is appended further down, AFTER the Amazon group
      //   rollup writes that element's textContent. v8.72 appended it here,
      //   so the rollup wiped it a few lines later - even a working audit
      //   could never have shown on this card.
      for (const [reg] of sePairs) {
        const gaps = await findWeeklyGaps('sku_economics', 'week_start', q => q.eq('region', reg));
        if (gaps.missing.length) amzUsCaGaps.push(...gaps.missing.map(m => `${reg}: ${m}`));
      }
    } else {
      setLast('last-sales-skuecon', '📅 No SKU Economics data loaded yet');
    }
    // ── SKU Economics EU — latest week per country.
    // v6.87 — display Saturday end-of-week (Mon + 5) to match US/CA convention.
    // Prior version showed raw week_start (Monday), which made the same uploaded
    // week look 5 days "older" on the EU card than the US/CA card.
    let amzEuLatest = null;
    try {
      // ⚠ v10.95 - the same `.limit(200)` row window as the US/CA card, and
      //   worse here: six countries share this table, so 200 newest rows can
      //   easily be one country's newest week and the other five read as
      //   never uploaded.
      const euPairs = await latestByRegion('sku_economics_eu', 'week_start');
      if (euPairs.length) {
        amzEuLatest = euPairs.map(([, wk]) => wk).sort().reverse()[0];
        const parts = euPairs.map(([reg, wk]) => `${reg}: thru Sat ${endOfWeek(wk, 5)}`);
        const lastUp = await latestUploadedAt('sku_economics_eu');
        setLast('last-sales-skuecon-eu', `📅 ${parts.slice(0,4).join(' · ')}${parts.length>4?` +${parts.length-4} more`:''} · uploaded ${ago(lastUp) || '—'}`);
        // v8.72 — per-country gap scan for SKU Economics EU
        try {
          const euGaps = [];
          for (const [reg] of euPairs) {
            const gaps = await findWeeklyGaps('sku_economics_eu', 'week_start', q => q.eq('region', reg));
            if (gaps.missing.length) euGaps.push(...gaps.missing.map(m => `${reg}: ${m}`));
          }
          if (euGaps.length) {
            const el = document.getElementById('last-sales-skuecon-eu');
            if (el && !el.querySelector('.gap-chip-eu')) {
              const chip = document.createElement('span');
              chip.className = 'gap-chip-eu';
              chip.style.cssText = 'margin-left:8px;padding:2px 7px;background:rgba(232,96,26,.14);color:var(--sp-orange);border:1px solid var(--sp-orange);border-radius:4px;font-family:var(--mono);font-size:10px;font-weight:700;cursor:help';
              const preview = euGaps.slice(0, 8).join(', ') + (euGaps.length > 8 ? `, +${euGaps.length - 8} more` : '');
              chip.textContent = `⚠ ${euGaps.length} gap${euGaps.length === 1 ? '' : 's'}`;
              chip.title = `Missing week_start values in the last 26 weeks by country:\n${euGaps.join('\n')}\n\nRe-upload EU reports for these weeks.`;
              el.appendChild(chip);
            }
          }
        } catch (_) { /* silent */ }
      } else {
        setLast('last-sales-skuecon-eu', '📅 No EU data yet');
      }
    } catch (_) { /* table may not exist */ }
    // Amazon group rollup — most recent of US/CA + EU.
    const amzAll = [amzUsCaLatest, amzEuLatest].filter(Boolean).sort().reverse();
    if (amzAll[0]) {
      const amzSat = endOfWeek(amzAll[0], 5);
      setLast('last-amz-sales-grp', `thru Sat ${amzSat} (${relDays(amzSat)})`);
    } else {
      setLast('last-amz-sales-grp', '— Never');
    }
    // v10.95 - the gap chip goes on only AFTER the rollup has written this
    // element's textContent, or the rollup wipes it (see the US/CA block).
    appendGapChip('last-amz-sales-grp', amzUsCaGaps);

    // ── Shopify DTC — v6.87 reads from shopify_sales_daily (post-v5.98 home).
    // Prior version queried sales_weekly where channel='shopify' which is no
    // longer written → cards always read "No Shopify data loaded yet".
    try {
      const { data: shRows } = await sb.from('shopify_sales_daily')
        .select('day, uploaded_at').order('day', { ascending: false }).limit(1);
      if (shRows && shRows.length) {
        renderCardFreshness('last-sales-shopify', shRows[0].day, shRows[0].uploaded_at, '📅 No Shopify data loaded yet');
        setLast('last-shopify-sales-grp', `${shRows[0].day} (${relDays(shRows[0].day)})`);
        // v7.43 — auto-update the "Open Shopify report" link's SINCE to the
        // last uploaded day (inclusive so any late updates for that day
        // land — the parser's upsert is idempotent per shopify_sku+day).
        if (typeof updateShopifyReportLink === 'function') updateShopifyReportLink(shRows[0].day);
      } else {
        setLast('last-sales-shopify', '📅 No Shopify data loaded yet');
        setLast('last-shopify-sales-grp', '— Never');
        if (typeof updateShopifyReportLink === 'function') updateShopifyReportLink(null);
      }
    } catch (_) {
      setLast('last-sales-shopify', '📅 No Shopify data loaded yet');
      setLast('last-shopify-sales-grp', '— Never');
      if (typeof updateShopifyReportLink === 'function') updateShopifyReportLink(null);
    }
    // ── Chewy — latest snapshot date + furthest forecast month.
    const { data: cfSnap } = await sb.from('chewy_forecasts')
      .select('upload_date, uploaded_at').order('upload_date', { ascending: false }).limit(1);
    const { data: cfMonth } = await sb.from('chewy_forecasts')
      .select('forecast_month').order('forecast_month', { ascending: false }).limit(1);
    if (cfSnap && cfSnap.length) {
      const lastMonth = (cfMonth && cfMonth.length) ? cfMonth[0].forecast_month : '?';
      const upTs = cfSnap[0].uploaded_at;
      setLast('last-sales-chewy', `📅 Data thru ${cfSnap[0].upload_date} · forecasts thru ${lastMonth} · uploaded ${ago(upTs) || '—'}`);
      setLast('last-chewy-sales-grp', `${cfSnap[0].upload_date} (${relDays(cfSnap[0].upload_date)})`);
    } else {
      setLast('last-sales-chewy', '📅 No Chewy forecasts loaded yet');
      setLast('last-chewy-sales-grp', '— Never');
    }

    // ── Walmart 1P — v6.87 new probe. walmart_sales_weekly stores week as
    // YYYYWW integer (e.g. 202611). walmartWeekToDate(yyyyww) returns the
    // Saturday end-of-week for the Walmart fiscal calendar.
    try {
      const { data: wmRows } = await sb.from('walmart_sales_weekly')
        .select('walmart_calendar_week, uploaded_at').order('walmart_calendar_week', { ascending: false }).limit(1);
      if (wmRows && wmRows.length) {
        const yyyyww = wmRows[0].walmart_calendar_week;
        // v8.72 — walmartWeekToDate returns a Date object, not a string. Was
        // interpolating the raw Date into the template literal ("Sat Sep 05
        // 2026 00:00:00 GMT-0500 (Central Daylight Time)") and passing it to
        // relDays which does string math → NaN. Format to YYYY-MM-DD first.
        const satDate = (typeof walmartWeekToDate === 'function') ? walmartWeekToDate(yyyyww) : null;
        const satStr = (satDate instanceof Date && !isNaN(satDate.getTime()))
          ? `${satDate.getFullYear()}-${String(satDate.getMonth() + 1).padStart(2, '0')}-${String(satDate.getDate()).padStart(2, '0')}`
          : String(yyyyww);
        renderCardFreshness('last-sales-walmart', `Sat ${satStr}`, wmRows[0].uploaded_at, '📅 No Walmart data loaded yet');
        setLast('last-walmart-sales-grp', `thru Sat ${satStr} (${relDays(satStr)})`);
        // v8.72 — Walmart gap detection. Storage is yyyyww integers, so decode
        // each to a Date via walmartWeekToDate, sort, and compare consecutive
        // weeks. Missing = expected Saturday values between first + last.
        try {
          if (typeof walmartWeekToDate === 'function') {
            const cutoffCode = (() => {
              const d = new Date(); d.setDate(d.getDate() - 26 * 7);
              const y = d.getFullYear(); const w = Math.max(1, Math.ceil((d - new Date(y, 0, 1)) / (7 * 864e5)));
              return y * 100 + w;
            })();
            // ⚠ v10.95 - was `.order(asc).limit(500)`, the FOURTH row window
            //   in this function and the sneakiest: ASCENDING, so it read the
            //   500 OLDEST rows in the 26-week window and a missing RECENT
            //   week could never be flagged. It also hid from the v10.92
            //   section-F guard, which asserted the SET of limit values -
            //   so this 500 and findWeeklyGaps' 500 collapsed into one entry
            //   and the guard reported three probes when there were four.
            //   A sweep that de-duplicates can hide a whole site.
            const { values: wmCodes } = await distinctValuesInWindow('walmart_sales_weekly', 'walmart_calendar_week', cutoffCode);
            if (wmCodes.length > 1) {
              const dates = wmCodes
                .map(c => { const d = walmartWeekToDate(c); return d instanceof Date && !isNaN(d.getTime()) ? d : null; })
                .filter(Boolean).sort((a, b) => a - b);
              const missing = [];
              if (dates.length >= 2) {
                const have = new Set(dates.map(d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`));
                for (let d = new Date(dates[0]); d.getTime() <= dates[dates.length-1].getTime(); d.setDate(d.getDate() + 7)) {
                  const ymd = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
                  if (!have.has(ymd)) missing.push(ymd);
                }
              }
              appendGapChip('last-walmart-sales-grp', missing);
            }
          }
        } catch (_) { /* silent */ }
      } else {
        setLast('last-sales-walmart', '📅 No Walmart data loaded yet');
        setLast('last-walmart-sales-grp', '— Never');
      }
    } catch (_) {
      setLast('last-sales-walmart', '📅 No Walmart data loaded yet');
      setLast('last-walmart-sales-grp', '— Never');
    }

    // ── Amazon Ads (non-SP) — v6.87 new probe. amazon_ad_spend is daily-grain.
    try {
      const { data: aaRows } = await sb.from('amazon_ad_spend')
        .select('date, uploaded_at').order('date', { ascending: false }).limit(1);
      if (aaRows && aaRows.length) {
        renderCardFreshness('last-amazon-ads', aaRows[0].date, aaRows[0].uploaded_at, '📅 No Amazon Ads (non-SP) data loaded yet');
        setLast('last-amazon-ads-grp', `${aaRows[0].date} (${relDays(aaRows[0].date)})`);
      } else {
        setLast('last-amazon-ads', '📅 No Amazon Ads (non-SP) data loaded yet');
        setLast('last-amazon-ads-grp', '— Never');
      }
    } catch (_) {
      setLast('last-amazon-ads', '📅 No Amazon Ads (non-SP) data loaded yet');
      setLast('last-amazon-ads-grp', '— Never');
    }

    // ── v8.96 — Amazon Ads Bulk Sheet. snapshot_date + uploaded_at.
    try {
      const { data: bulkRows } = await sb.from('amazon_ads_bulk_upload')
        .select('snapshot_date, uploaded_at, row_count').order('snapshot_date', { ascending: false }).limit(1);
      if (bulkRows && bulkRows.length) {
        const b = bulkRows[0];
        setLast('last-amazon-ads-bulk', `📅 Latest snapshot ${b.snapshot_date} · ${(b.row_count || 0).toLocaleString()} rows · uploaded ${ago(b.uploaded_at) || 'recently'}`);
        setLast('last-amazon-ads-bulk-grp', `${b.snapshot_date} · uploaded ${ago(b.uploaded_at) || 'recently'}`);
      } else {
        setLast('last-amazon-ads-bulk', '📅 No Amazon Ads Bulk Sheet uploaded yet');
        setLast('last-amazon-ads-bulk-grp', '— Never');
      }
    } catch (_) {
      setLast('last-amazon-ads-bulk', '📅 No Amazon Ads Bulk Sheet uploaded yet');
      setLast('last-amazon-ads-bulk-grp', '— Never');
    }

    // ── v10.86 — Sales & Traffic. Routes to one of two tables, so probe the
    // newest of both rather than claiming "Never" when only one has data.
    try {
      const [wk, snap] = await Promise.all([
        sb.from('amazon_sales_traffic').select('week_start, uploaded_at')
          .order('uploaded_at', { ascending: false }).limit(1),
        sb.from('amazon_sales_traffic_snapshot').select('period_end, uploaded_at')
          .order('uploaded_at', { ascending: false }).limit(1),
      ]);
      const cands = [];
      if (wk.data && wk.data.length)     cands.push({ thru: wk.data[0].week_start,    up: wk.data[0].uploaded_at });
      if (snap.data && snap.data.length) cands.push({ thru: snap.data[0].period_end,  up: snap.data[0].uploaded_at });
      cands.sort((a, b) => String(b.up).localeCompare(String(a.up)));
      if (cands.length) {
        setLast('last-sales-traffic', `📅 Data thru ${cands[0].thru} · uploaded ${ago(cands[0].up) || 'recently'}`);
        setLast('last-sales-traffic-grp', `${cands[0].thru} · uploaded ${ago(cands[0].up) || 'recently'}`);
      } else {
        setLast('last-sales-traffic', '📅 No Sales & Traffic data loaded yet');
        setLast('last-sales-traffic-grp', '— Never');
      }
    } catch (_) {
      setLast('last-sales-traffic', '📅 No Sales & Traffic data loaded yet');
      setLast('last-sales-traffic-grp', '— Never');
    }

    // ── v10.86 — FBA Fee Preview group rollup (the per-card line already existed).
    try {
      const { data: fpRows } = await sb.from('fba_fee_preview')
        .select('snapshot_date, uploaded_at').order('snapshot_date', { ascending: false }).limit(1);
      if (fpRows && fpRows.length) {
        setLast('last-fba-fee-preview-grp', `${fpRows[0].snapshot_date} · uploaded ${ago(fpRows[0].uploaded_at) || 'recently'}`);
      } else {
        setLast('last-fba-fee-preview-grp', '— Never');
      }
    } catch (_) {
      setLast('last-fba-fee-preview-grp', '— Never');
    }

    // ── v10.89 — SQP, probed PER VIEW. Both views share one table behind a
    // view_type discriminator, so a single probe reported the newest month
    // across BOTH — a fresh Brand pull masked a stale ASIN pull, and the
    // Growth Model reads view_type='asin'. One probe per card now.
    for (const [vt, cardId, grpId, human] of [
      ['asin',  'last-amz-sqp-asin',  'last-amz-sqp-asin-grp',  'ASIN view'],
      ['brand', 'last-amz-sqp-brand', 'last-amz-sqp-brand-grp', 'Brand view'],
    ]) {
      try {
        const { data: rows } = await sb.from('amazon_query_performance_asin')
          .select('reporting_month, uploaded_at').eq('view_type', vt)
          .order('reporting_month', { ascending: false }).limit(1);
        if (rows && rows.length) {
          setLast(cardId, `📅 Latest month ${rows[0].reporting_month} · uploaded ${ago(rows[0].uploaded_at) || 'recently'}`);
          setLast(grpId,  `${rows[0].reporting_month} · uploaded ${ago(rows[0].uploaded_at) || 'recently'}`);
        } else {
          setLast(cardId, `📅 No SQP ${human} data loaded yet`);
          setLast(grpId, '— Never');
        }
      } catch (_) {
        setLast(cardId, `📅 No SQP ${human} data loaded yet`);
        setLast(grpId, '— Never');
      }
    }

    // ── v8.44 — SP Search Term Report. reporting_month + uploaded_at.
    try {
      const { data: stRows } = await sb.from('amazon_sp_search_term')
        .select('reporting_month, uploaded_at').order('reporting_month', { ascending: false }).limit(1);
      if (stRows && stRows.length) {
        setLast('last-amz-sp-search-term', `📅 Latest month ${stRows[0].reporting_month} · uploaded ${ago(stRows[0].uploaded_at) || 'recently'}`);
        setLast('last-amz-sp-search-term-grp', `${stRows[0].reporting_month} · uploaded ${ago(stRows[0].uploaded_at) || 'recently'}`);
      } else {
        setLast('last-amz-sp-search-term', '📅 No SP Search Term data loaded yet');
        setLast('last-amz-sp-search-term-grp', '— Never');
      }
    } catch (_) {
      setLast('last-amz-sp-search-term', '📅 No SP Search Term data loaded yet');
      setLast('last-amz-sp-search-term-grp', '— Never');
    }

    // ── v8.54 — SP Campaign Snapshot (Impression Share diagnostics).
    try {
      const { data: cmpRows } = await sb.from('amazon_sp_campaign_snapshot')
        .select('reporting_month, uploaded_at').order('reporting_month', { ascending: false }).limit(1);
      if (cmpRows && cmpRows.length) {
        setLast('last-amz-sp-campaign', `📅 Latest month ${cmpRows[0].reporting_month} · uploaded ${ago(cmpRows[0].uploaded_at) || 'recently'}`);
        setLast('last-amz-sp-campaign-grp', `${cmpRows[0].reporting_month} · uploaded ${ago(cmpRows[0].uploaded_at) || 'recently'}`);
      } else {
        setLast('last-amz-sp-campaign', '📅 No SP Campaign snapshot data loaded yet');
        setLast('last-amz-sp-campaign-grp', '— Never');
      }
    } catch (_) {
      setLast('last-amz-sp-campaign', '📅 No SP Campaign snapshot data loaded yet');
      setLast('last-amz-sp-campaign-grp', '— Never');
    }

    // ── Digital Sales Tracker — v6.87 probe, v7.98 fix.
    // digital_sales_tracker is FORECAST data — every upload contains rows
    // for the current + future months. Pre-v7.98 the group rollup showed the
    // MAX (year, month) tuple in the data, which was always today's month or
    // later (Dec 2026 for a 2026 file). relDays clamped negative diffs (future
    // dates) to 'today', so the header read "2026-12 (today)" even when the
    // last upload was weeks ago — falsely signaling fresh data. Fixed: show
    // `uploaded {N ago}` as the primary cadence signal (matches every other
    // source), with the max forecast month as secondary context.
    try {
      const { data: dsRows } = await sb.from('digital_sales_tracker')
        .select('year, month, uploaded_at').order('year', { ascending: false }).order('month', { ascending: false }).limit(1);
      if (dsRows && dsRows.length) {
        const y = dsRows[0].year, m = dsRows[0].month;
        const monthTag = `${y}-${String(m).padStart(2,'0')}`;
        const relUp = ago(dsRows[0].uploaded_at) || '— never';
        // Card: primary line = when it was uploaded; secondary line = forecast horizon.
        renderCardFreshness('last-digital-sales', `upload · forecasts through ${monthTag}`, dsRows[0].uploaded_at, '📅 No Digital Sales Tracker data loaded yet');
        // Group rollup: `uploaded 2w ago · thru 2026-12`. Matches the
        // "uploaded X ago" cadence every other source uses.
        setLast('last-digital-sales-grp', `uploaded ${relUp} · thru ${monthTag}`);
      } else {
        setLast('last-digital-sales', '📅 No Digital Sales Tracker data loaded yet');
        setLast('last-digital-sales-grp', '— Never');
      }
    } catch (_) {
      setLast('last-digital-sales', '📅 No Digital Sales Tracker data loaded yet');
      setLast('last-digital-sales-grp', '— Never');
    }

    // ── Warehouse rollup — comes from inventory.warehouse refresh, which is
    // tracked via the existing #refreshLabel set by the Shopify Inventory handler.
    setLast('last-warehouse-grp', document.getElementById('refreshLabel')?.textContent || '— Not wired');

    // ── FBA Inventory Snapshot — latest snapshot_date per region (v4.168).
    // ⚠ v10.95 - was `.limit(10)`, walked for the first row per region, on a
    //   table that holds one row per ASIN per snapshot. TEN rows: they can
    //   trivially all belong to one region, so a region whose last snapshot
    //   is a single day older read as having no snapshot at all. The most
    //   fragile of the four windows this release removed.
    // ⚠ v10.96 - there are TWO dropzones here (v5.14: the NA/APAC gateway
    //   and the EU/UK one) and only the first card was ever refreshed. The
    //   EU card was written solely by handleFbaInventoryUpload, so it showed
    //   its snapshot until the next page load and then went blank - the one
    //   card on the page that could not answer "is this stale?". Both cards
    //   now render from the SAME walk, through the SAME formatter, and
    //   differ only in which regions each one claims.
    try {
      const fiPairs = await latestByRegion('fba_inventory_snapshots', 'snapshot_date');
      // The EU dropzone always files its upload under 'EU/UK' (one report
      // covers GB + DE/FR/IT/ES/NL/...), but accept the per-country codes
      // too so a row written any other way still lands on the right card.
      // Reuses EU_REGIONS rather than writing a second EU list.
      const fiIsEu = (reg) => reg === 'EU/UK' || (typeof EU_REGIONS !== 'undefined' && EU_REGIONS.has(reg));
      const fiLine = (pairs) => `📅 ${pairs.map(([reg, d]) => `${reg}: ${d}`).join(' · ')}`;
      // An unrecognised region stays on the NA/APAC card - that is the
      // dropzone with the region picker, so it is where a stray code came
      // from. Never drop one: a region with no card is a region with no
      // freshness, which is the bug this release is fixing.
      const fiEu = fiPairs.filter(([reg]) => fiIsEu(reg));
      const fiNa = fiPairs.filter(([reg]) => !fiIsEu(reg));
      setLast('last-fba-inv',    fiNa.length ? fiLine(fiNa) : '📅 No FBA snapshot loaded yet');
      setLast('last-fba-inv-eu', fiEu.length ? fiLine(fiEu) : '📅 No EU FBA snapshot loaded yet');
      // The group rollup stays whole-table: it answers "when did ANY FBA
      // snapshot last land?", which neither card alone can.
      if (fiPairs.length) {
        const fiNewest = fiPairs.map(([, d]) => d).sort().reverse()[0];
        setLast('last-fba-inv-grp', `${fiNewest} (${relDays(fiNewest)})`);
      } else {
        setLast('last-fba-inv-grp', '— Never');
      }
    } catch (_) { /* table may not exist */ }

    // ── FBA Shipment Detail — latest created_date (v4.168).
    try {
      const { data: shipRows } = await sb.from('fba_shipments')
        .select('created_date, shipment_id').order('created_date', { ascending: false, nullsLast: true }).limit(1);
      if (shipRows && shipRows.length && shipRows[0].created_date) {
        setLast('last-fba-ship', `📅 Last shipment ${shipRows[0].shipment_id} · ${shipRows[0].created_date}`);
        setLast('last-fba-ship-grp', `${shipRows[0].created_date} (${relDays(shipRows[0].created_date)})`);
      } else {
        setLast('last-fba-ship', '📅 No shipments uploaded yet');
        setLast('last-fba-ship-grp', '— Never');
      }
    } catch (_) {}

    // ── FBA Shipment Summary — most recent uploaded_at (v4.168).
    try {
      const { data: sumRows } = await sb.from('fba_shipment_summaries')
        .select('uploaded_at, last_updated').order('uploaded_at', { ascending: false }).limit(1);
      if (sumRows && sumRows.length) {
        const d = (sumRows[0].uploaded_at || '').slice(0,10);
        setLast('last-fba-ship-sum', `📅 Last refresh ${d}`);
        setLast('last-fba-ship-sum-grp', `${d} (${relDays(d)})`);
      } else {
        setLast('last-fba-ship-sum', '📅 No summary uploaded yet');
        setLast('last-fba-ship-sum-grp', '— Never');
      }
    } catch (_) {}

    // ── v7.03 — Chewy Rebate Invoices (PDF). Latest invoice_date + uploaded_at.
    try {
      const { data: cbRows } = await sb.from('chewy_rebates')
        .select('invoice_date, uploaded_at').order('invoice_date', { ascending: false }).limit(1);
      if (cbRows && cbRows.length) {
        renderCardFreshness('last-chewy-rebates', cbRows[0].invoice_date, cbRows[0].uploaded_at, '📅 No Chewy rebates loaded yet');
      } else {
        setLast('last-chewy-rebates', '📅 No Chewy rebates loaded yet');
      }
    } catch (_) {
      setLast('last-chewy-rebates', '📅 No Chewy rebates loaded yet');
    }

    // ── v7.73 — Chewy Weekly Sales Actuals. Latest week_start + uploaded_at.
    try {
      const { data: caRows } = await sb.from('chewy_sales_weekly')
        .select('week_start, uploaded_at').order('week_start', { ascending: false }).limit(1);
      if (caRows && caRows.length) {
        renderCardFreshness('last-chewy-actuals', caRows[0].week_start, caRows[0].uploaded_at, '📅 No Chewy actuals loaded yet');
        setLast('last-chewy-actuals-grp', `wk ${caRows[0].week_start} (${relDays(caRows[0].week_start)})`);
        // v8.72 — Chewy weekly gap detection
        const gaps = await findWeeklyGaps('chewy_sales_weekly', 'week_start');
        appendGapChip('last-chewy-actuals-grp', gaps.missing);
      } else {
        setLast('last-chewy-actuals', '📅 No Chewy actuals loaded yet');
        setLast('last-chewy-actuals-grp', '— Never');
      }
    } catch (_) {
      setLast('last-chewy-actuals', '📅 No Chewy actuals loaded yet · run supabase_v7_73_chewy_sales_weekly.sql');
      setLast('last-chewy-actuals-grp', '— Never');
    }

    // ── v10.39 — Chewy Ads (Promoted products). Latest ad day + uploaded_at.
    try {
      const { data: adRows } = await sb.from('chewy_ad_spend')
        .select('date, uploaded_at').order('date', { ascending: false }).limit(1);
      if (adRows && adRows.length) {
        renderCardFreshness('last-chewy-ads', adRows[0].date, adRows[0].uploaded_at, '📅 No Chewy ad spend loaded yet');
        setLast('last-chewy-ads-grp', `thru ${adRows[0].date} (${relDays(adRows[0].date)})`);
      } else {
        setLast('last-chewy-ads', '📅 No Chewy ad spend loaded yet');
        setLast('last-chewy-ads-grp', '— Never');
      }
    } catch (_) {
      setLast('last-chewy-ads', '📅 No Chewy ad spend loaded yet · run supabase_v10_36_chewy_ad_spend.sql');
      setLast('last-chewy-ads-grp', '— Never');
    }
  } catch (e) {
    console.warn('refreshUploadDataRanges:', e?.message || e);
  }

  // v10.85 - a fresh upload must appear in its own recent-uploads rail
  // right away, so drop the cache and re-render.
  try { dzRecentInvalidate(); renderAllDzRecentUploads(); } catch (_) {}
}

(async () => {

// -- 1. Both gateways loaded ------------------------------------------
reset(); WARNED = [];
setTables(snaps([['US', '2026-05-16'], ['CA', '2026-05-16'], ['EU/UK', '2026-05-09']]));
await refreshUploadDataRanges();
t('B1  the NA card lists only the NA/APAC gateway regions',
  txt('last-fba-inv'), '\u{1F4C5} US: 2026-05-16 \u00b7 CA: 2026-05-16');
t('B2  the EU card is populated by the REFRESH - the whole fix',
  txt('last-fba-inv-eu'), '\u{1F4C5} EU/UK: 2026-05-09');
t('B3  the two cards use the same format',
  /^\u{1F4C5} [^:]+: \d{4}-\d\d-\d\d/u.test(txt('last-fba-inv-eu')), true);
t('B4  the group rollup is the newest across BOTH cards',
  txt('last-fba-inv-grp').startsWith('2026-05-16 ('), true);
t('B5  nothing reached the outer catch',
  WARNED.filter(w => w.startsWith('refreshUploadDataRanges:')), []);

// -- 2. The regression guard: v10.95 put EU/UK on the NA card ----------
{
  const pairs = [['US', '2026-05-16'], ['CA', '2026-05-16'], ['EU/UK', '2026-05-09']];
  const v1095Line = '\u{1F4C5} ' + pairs.map(([r, d]) => `${r}: ${d}`).join(' \u00b7 ');
  t('B6  the pre-v10.96 NA card really did swallow the EU snapshot',
    v1095Line.includes('EU/UK'), true);
  t('B7  ...and the EU card really was left blank by the refresh',
    v1095Line === txt('last-fba-inv'), false);
}

// -- 3. EU only: the NA card must say so, not go stale -----------------
reset(); WARNED = [];
setTables(snaps([['EU/UK', '2026-05-09']]));
await refreshUploadDataRanges();
t('B8  EU-only data leaves the NA card on its empty state',
  txt('last-fba-inv'), '\u{1F4C5} No FBA snapshot loaded yet');
t('B9  ...and the EU card reports the snapshot',
  txt('last-fba-inv-eu'), '\u{1F4C5} EU/UK: 2026-05-09');
t('B10 ...and the rollup is the EU date', txt('last-fba-inv-grp').startsWith('2026-05-09 ('), true);

// -- 4. NA only: the EU card gets its OWN empty state ------------------
reset();
setTables(snaps([['US', '2026-05-16']]));
await refreshUploadDataRanges();
t('B11 the EU card says it is empty rather than staying blank',
  txt('last-fba-inv-eu'), '\u{1F4C5} No EU FBA snapshot loaded yet');
t('B12 ...which is distinguishable from the NA empty state',
  txt('last-fba-inv-eu') !== '\u{1F4C5} No FBA snapshot loaded yet', true);

// -- 5. Per-country EU codes land on the EU card -----------------------
reset();
setTables(snaps([['US', '2026-05-16'], ['GB', '2026-05-09'], ['DE', '2026-05-02']]));
await refreshUploadDataRanges();
t('B13 GB and DE are EU, not NA', txt('last-fba-inv'), '\u{1F4C5} US: 2026-05-16');
t('B14 ...and print on the EU card in marketplace order',
  txt('last-fba-inv-eu'), '\u{1F4C5} GB: 2026-05-09 \u00b7 DE: 2026-05-02');

// -- 6. An unrecognised region is never dropped ------------------------
reset();
setTables(snaps([['US', '2026-05-16'], ['ZZ', '2026-05-09'], ['EU/UK', '2026-05-02']]));
await refreshUploadDataRanges();
t('B15 an unknown region stays on the card whose dropzone has the picker',
  txt('last-fba-inv').includes('ZZ: 2026-05-09'), true);
t('B16 ...and does not leak onto the EU card',
  txt('last-fba-inv-eu'), '\u{1F4C5} EU/UK: 2026-05-02');
t('B17 every region in the table is printed SOMEWHERE - none vanishes',
  ['US', 'ZZ', 'EU/UK'].every(r => (txt('last-fba-inv') + txt('last-fba-inv-eu')).includes(r + ':')), true);

// -- 7. Empty + missing table ------------------------------------------
reset(); WARNED = [];
setTables([]);
await refreshUploadDataRanges();
t('B18 an empty table puts BOTH cards on their empty states',
  [txt('last-fba-inv'), txt('last-fba-inv-eu')],
  ['\u{1F4C5} No FBA snapshot loaded yet', '\u{1F4C5} No EU FBA snapshot loaded yet']);
t('B19 ...and the rollup says Never', txt('last-fba-inv-grp'), '\u2014 Never');

reset(); WARNED = [];
TABLES = { sku_economics: [] };          // fba table errors outright
await refreshUploadDataRanges();
t('B20 a missing table degrades quietly', WARNED.filter(w => w.startsWith('refreshUploadDataRanges:')), []);

console.warn = _warn;
console.log(JSON.stringify(out));
})();
