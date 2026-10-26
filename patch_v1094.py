# -*- coding: utf-8 -*-
r"""v10.94 - remove the three truncating probes from refreshUploadDataRanges.

Run once:  python patch_v1094.py
Writes index.html via a temp file + os.replace (atomic, so a failed patch
leaves the original in place).
"""
import io, os, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
s = io.open(SRC, encoding='utf-8', newline='').read()
orig_len = len(s)

# ---- locate refreshUploadDataRanges by brace balance ----------------------
m = re.search(r'async function refreshUploadDataRanges\(\) \{', s)
if not m:
    sys.exit('refreshUploadDataRanges not found')
j = s.index('{', m.end() - 1)
d = 0; k = j
while True:
    if s[k] == '{': d += 1
    elif s[k] == '}':
        d -= 1
        if d == 0: break
    k += 1
START, END = m.start(), k + 1
fnsrc = s[START:END]

edits = []   # (label, old, new)

# =========================================================================
# 1. `sb` at FUNCTION scope. It was `const sb` inside the try block, which
#    the helpers out here cannot see - every findWeeklyGaps call threw
#    ReferenceError into its own catch.
# =========================================================================
edits.append(('sb hoisted to function scope', """async function refreshUploadDataRanges() {
  const setLast = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };""",
"""async function refreshUploadDataRanges() {
  // \u26a0 v10.94 - `sb` MUST live at FUNCTION scope. It used to be declared
  // `const sb = await getSB()` INSIDE the try block below - a nested block
  // scope - so the helpers defined out here (findWeeklyGaps, and the v10.94
  // per-region probes) could not see it and every call threw ReferenceError
  // straight into its own catch. That is why the v8.72 gap audit reported
  // "no gaps" for every table since the day it shipped: valid JavaScript,
  // clean `node --check`, dead at runtime - the v10.8 called-but-undefined
  // class. Do not re-declare it inside a block.
  let sb = null;
  const setLast = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };"""))

edits.append(('try block assigns the hoisted sb', """  try {
    const sb = await getSB();""",
"""  try {
    sb = await getSB();"""))

# =========================================================================
# 2. The per-region probe helpers, in front of findWeeklyGaps.
# =========================================================================
edits.append(('per-region probe helpers added', """  // v8.72 \u2014 Missing-week gap detection. Query all week_start values back to""",
"""  // v10.94 \u2014 the distinct values of a column, without a DISTINCT (PostgREST
  // has none). Keyset walk: ask for the smallest value ABOVE the last one
  // seen, one row at a time, until nothing is above it. Costs a round trip
  // per distinct value instead of one per 1000 rows - and, the whole point,
  // it cannot truncate the way a newest-N-rows window does.
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
  // v10.94 \u2014 what ORDER the region chips print in. The SET always comes from
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
  // v10.94 \u2014 the newest date for ONE region: the v10.89 per-view probe shape
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
  // v10.94 \u2014 max(uploaded_at) for a table, which is what every card's
  // "uploaded X ago" has always meant. One probe, no region needed.
  const latestUploadedAt = async (table) => {
    const { data, error } = await sb.from(table)
      .select('uploaded_at').order('uploaded_at', { ascending: false }).limit(1);
    if (error || !data || !data.length) return null;
    return data[0].uploaded_at;
  };
  // v10.94 \u2014 [[region, 'YYYY-MM-DD'], ...] in display order, regions with
  // no data left out. The three cards that print `REG: date \u00b7 REG: date` all
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
  // v8.72 \u2014 Missing-week gap detection. Query all week_start values back to"""))

# =========================================================================
# 3. findWeeklyGaps: page by DATE instead of taking 500 newest rows.
# =========================================================================
edits.append(('findWeeklyGaps paginates', """      let q = sb.from(table).select(dateCol).gte(dateCol, cutoffStr);
      if (extraFilter) q = extraFilter(q);
      const { data, error } = await q.order(dateCol, { ascending: false }).limit(500);
      if (error || !data || !data.length) return { missing: [], latest: null, first: null };
      const weeks = [...new Set(data.map(r => String(r[dateCol]).slice(0, 10)))].sort();""",
"""      // \u26a0 v10.94 - this asked for `.limit(500)` and called the result 26
      // weeks. sku_economics carries ~500 ASINs per week, so 500 newest rows
      // covered ONE week: the audit silently inspected a one-week window and
      // under-reported every gap outside it. Architecture Rule #4, the same
      // class as the v10.92 rail - a ROW window read as a DATE window.
      //
      // Page by DATE rather than by row offset: each round trip takes the
      // newest PAGE rows below the cursor, records every date in them, then
      // drops the cursor BELOW the oldest date it saw - so the rest of that
      // date's rows are never fetched. Distinct dates is all this needs, so
      // the walk costs round trips per WEEK at worst, never per row, and it
      // ends only when the data inside the window runs out.
      const PAGE = 1000, MAX_PAGES = 40;
      const seen = new Set();
      let cursor = null, ranOut = false;
      for (let pageNo = 0; pageNo < MAX_PAGES; pageNo++) {
        let q = sb.from(table).select(dateCol).gte(dateCol, cutoffStr);
        if (cursor) q = q.lt(dateCol, cursor);
        if (extraFilter) q = extraFilter(q);
        const { data, error } = await q.order(dateCol, { ascending: false }).range(0, PAGE - 1);
        if (error || !data || !data.length) { ranOut = !error; break; }
        for (const r of data) seen.add(String(r[dateCol]).slice(0, 10));
        if (data.length < PAGE) { ranOut = true; break; }
        const oldest = String(data[data.length - 1][dateCol]).slice(0, 10);
        if (oldest === cursor) break;   // no progress - bail rather than spin
        cursor = oldest;
      }
      // Truncation makes this MISS gaps, never invent them, so whatever it
      // found is still real - but say so in the console rather than let a
      // short window pass for a 26-week audit.
      if (!ranOut) console.warn(`findWeeklyGaps(${table}): stopped before the ${maxWeeksBack}-week window was read - gaps may be under-reported`);
      const weeks = [...seen].sort();"""))

# =========================================================================
# 4. SKU Economics US/CA - probe per region.
# =========================================================================
edits.append(('SKU Economics US/CA probes per region', """    // \u2500\u2500 SKU Economics US/CA \u2014 latest week per region.
    const { data: seRows } = await sb.from('sku_economics')
      .select('week_start, region, uploaded_at').order('week_start', { ascending: false }).limit(200);
    let amzUsCaLatest = null;
    if (seRows && seRows.length) {
      const byRegion = {};
      const byRegionUp = {};
      for (const r of seRows) {
        if (!byRegion[r.region])   byRegion[r.region]   = r.week_start;
        if (!byRegionUp[r.region] || (r.uploaded_at || '') > byRegionUp[r.region]) byRegionUp[r.region] = r.uploaded_at;
      }
      amzUsCaLatest = Object.values(byRegion).sort().reverse()[0];
      const parts = Object.entries(byRegion)
        .sort((a,b) => a[0].localeCompare(b[0]))
        .map(([reg, wk]) => `${reg}: thru Sat ${endOfWeek(wk, 5)}`);
      const lastUp = Object.values(byRegionUp).sort().reverse()[0];
      setLast('last-sales-skuecon', `\U0001f4c5 Data ${parts.join(' \u00b7 ')} \u00b7 uploaded ${ago(lastUp) || '\u2014'}`);
      // v8.72 \u2014 per-region gap scan for SKU Economics US/CA
      const allGaps = [];
      for (const reg of Object.keys(byRegion)) {
        const gaps = await findWeeklyGaps('sku_economics', 'week_start', q => q.eq('region', reg));
        if (gaps.missing.length) allGaps.push(...gaps.missing.map(m => `${reg}: ${m}`));
      }
      appendGapChip('last-amz-sales-grp', allGaps);
    } else {
      setLast('last-sales-skuecon', '\U0001f4c5 No SKU Economics data loaded yet');
    }""",
"""    // \u2500\u2500 SKU Economics US/CA \u2014 latest week per region.
    // \u26a0 v10.94 - this was ONE `.select('week_start, region, uploaded_at')`
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
      setLast('last-sales-skuecon', `\U0001f4c5 Data ${parts.join(' \u00b7 ')} \u00b7 uploaded ${ago(lastUp) || '\u2014'}`);
      // v8.72 \u2014 per-region gap scan for SKU Economics US/CA.
      // \u26a0 v10.94 - the chip is appended further down, AFTER the Amazon group
      //   rollup writes that element's textContent. v8.72 appended it here,
      //   so the rollup wiped it a few lines later - even a working audit
      //   could never have shown on this card.
      for (const [reg] of sePairs) {
        const gaps = await findWeeklyGaps('sku_economics', 'week_start', q => q.eq('region', reg));
        if (gaps.missing.length) amzUsCaGaps.push(...gaps.missing.map(m => `${reg}: ${m}`));
      }
    } else {
      setLast('last-sales-skuecon', '\U0001f4c5 No SKU Economics data loaded yet');
    }"""))

# =========================================================================
# 5. SKU Economics EU - probe per country.
# =========================================================================
edits.append(('SKU Economics EU probes per country', """      const { data: euRows } = await sb.from('sku_economics_eu')
        .select('week_start, region, uploaded_at').order('week_start', { ascending: false }).limit(200);
      if (euRows && euRows.length) {
        amzEuLatest = euRows[0].week_start;
        const byEu = {}, byEuUp = {};
        for (const r of euRows) {
          if (!byEu[r.region])   byEu[r.region]   = r.week_start;
          if (!byEuUp[r.region] || (r.uploaded_at || '') > byEuUp[r.region]) byEuUp[r.region] = r.uploaded_at;
        }
        const parts = Object.entries(byEu).sort().map(([reg, wk]) => `${reg}: thru Sat ${endOfWeek(wk, 5)}`);
        const lastUp = Object.values(byEuUp).sort().reverse()[0];""",
"""      // \u26a0 v10.94 - the same `.limit(200)` row window as the US/CA card, and
      //   worse here: six countries share this table, so 200 newest rows can
      //   easily be one country's newest week and the other five read as
      //   never uploaded.
      const euPairs = await latestByRegion('sku_economics_eu', 'week_start');
      if (euPairs.length) {
        amzEuLatest = euPairs.map(([, wk]) => wk).sort().reverse()[0];
        const parts = euPairs.map(([reg, wk]) => `${reg}: thru Sat ${endOfWeek(wk, 5)}`);
        const lastUp = await latestUploadedAt('sku_economics_eu');"""))

edits.append(('EU gap scan walks the probed countries', """          const euGaps = [];
          for (const reg of Object.keys(byEu)) {""",
"""          const euGaps = [];
          for (const [reg] of euPairs) {"""))

# =========================================================================
# 6. The Amazon group rollup wipes the chip - append after it.
# =========================================================================
edits.append(('gap chip appended after the rollup', """      setLast('last-amz-sales-grp', `thru Sat ${amzSat} (${relDays(amzSat)})`);
    } else {
      setLast('last-amz-sales-grp', '\u2014 Never');
    }""",
"""      setLast('last-amz-sales-grp', `thru Sat ${amzSat} (${relDays(amzSat)})`);
    } else {
      setLast('last-amz-sales-grp', '\u2014 Never');
    }
    // v10.94 - the gap chip goes on only AFTER the rollup has written this
    // element's textContent, or the rollup wipes it (see the US/CA block).
    appendGapChip('last-amz-sales-grp', amzUsCaGaps);"""))

# =========================================================================
# 7. FBA inventory snapshots - probe per region.
# =========================================================================
edits.append(('FBA snapshot probes per region', """    // \u2500\u2500 FBA Inventory Snapshot \u2014 latest snapshot_date (v4.168).
    try {
      const { data: fiRows } = await sb.from('fba_inventory_snapshots')
        .select('snapshot_date, region').order('snapshot_date', { ascending: false }).limit(10);
      if (fiRows && fiRows.length) {
        const byR = {};
        for (const r of fiRows) { if (!byR[r.region]) byR[r.region] = r.snapshot_date; }
        const parts = Object.entries(byR).map(([reg, d]) => `${reg}: ${d}`);
        setLast('last-fba-inv', `\U0001f4c5 ${parts.join(' \u00b7 ')}`);
        setLast('last-fba-inv-grp', `${fiRows[0].snapshot_date} (${relDays(fiRows[0].snapshot_date)})`);
      } else {""",
"""    // \u2500\u2500 FBA Inventory Snapshot \u2014 latest snapshot_date per region (v4.168).
    // \u26a0 v10.94 - was `.limit(10)`, walked for the first row per region, on a
    //   table that holds one row per ASIN per snapshot. TEN rows: they can
    //   trivially all belong to one region, so a region whose last snapshot
    //   is a single day older read as having no snapshot at all. The most
    //   fragile of the three windows this release removed.
    try {
      const fiPairs = await latestByRegion('fba_inventory_snapshots', 'snapshot_date');
      if (fiPairs.length) {
        const parts = fiPairs.map(([reg, d]) => `${reg}: ${d}`);
        setLast('last-fba-inv', `\U0001f4c5 ${parts.join(' \u00b7 ')}`);
        const fiNewest = fiPairs.map(([, d]) => d).sort().reverse()[0];
        setLast('last-fba-inv-grp', `${fiNewest} (${relDays(fiNewest)})`);
      } else {"""))

# ---- apply ---------------------------------------------------------------
for label, old, new in edits:
    n = fnsrc.count(old)
    if n != 1:
        sys.exit('ABORT: "%s" matched %d times (want 1)' % (label, n))
    fnsrc = fnsrc.replace(old, new, 1)
    print('  patched: %s' % label)

s = s[:START] + fnsrc + s[END:]

# ---- version chip --------------------------------------------------------
CHIP_OLD = 'v10.93 \u00b7 2026-10-26</span>'
CHIP_NEW = 'v10.94 \u00b7 2026-10-26</span>'
if s.count(CHIP_OLD) != 1:
    sys.exit('ABORT: version chip matched %d times' % s.count(CHIP_OLD))
s = s.replace(CHIP_OLD, CHIP_NEW, 1)
print('  patched: version chip -> v10.94')

tmp = SRC + '.tmp'
io.open(tmp, 'w', encoding='utf-8', newline='').write(s)
os.replace(tmp, SRC)
print('\nwrote index.html  (%d -> %d chars)' % (orig_len, len(s)))
