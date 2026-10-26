
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// -- stubs ---------------------------------------------------------------
const UH_SOURCES = {
  big:   { dateField: 'reporting_month', label: 'Big' },
  meta:  { dateField: 'reporting_month', label: 'Meta', rowCountField: 'row_count' },
};
function dzSourceKey(src) {
  return src.table + (src.filter ? '|' + Object.entries(src.filter).map(([k, v]) => k + '=' + v).join(',') : '');
}
let _dzRecentCache = {};

// Rows are served newest-upload-first, exactly as the real query orders them.
let ROWS = [], EQ_CALLS = [], RANGES = [], ERROR_ON_PAGE = -1, PAGE_HITS = 0;
// db-max-rows: PostgREST silently truncates ANY response past this. The whole
// bug was asking for 4000 and getting 1000 with no error.
const DB_MAX_ROWS = 1000;

function builder(table) {
  const b = { _eq: [] };
  b.select = () => b;
  b.eq = (col, val) => { b._eq.push([col, val]); return b; };
  b.order = () => b;
  b.limit = (n) => { b._limit = n; return b; };
  b.range = async (from, to) => {
    const page = PAGE_HITS++;
    RANGES.push([from, to]);
    EQ_CALLS.push(b._eq.slice());
    if (page === ERROR_ON_PAGE) return { data: null, error: { message: 'boom' } };
    let rows = ROWS;
    for (const [c, v] of b._eq) rows = rows.filter(r => r[c] === v);
    const want = to - from + 1;
    return { data: rows.slice(from, from + Math.min(want, DB_MAX_ROWS)), error: null };
  };
  // The pre-v10.92 path: one shot, capped by the server.
  b.run_limit = async () => {
    EQ_CALLS.push(b._eq.slice());
    let rows = ROWS;
    for (const [c, v] of b._eq) rows = rows.filter(r => r[c] === v);
    return { data: rows.slice(0, DB_MAX_ROWS), error: null };
  };
  return b;
}
async function getSB() { return { from: (t) => builder(t) }; }

function reset() { EQ_CALLS = []; RANGES = []; ERROR_ON_PAGE = -1; PAGE_HITS = 0; _dzRecentCache = {}; }

// N sessions, each `per` rows, NEWEST FIRST (i = 0 is newest) - the order the
// real query returns. Timestamps strictly descend and months roll across the
// year boundary, so `oldest by ts` and `newest by period` are unambiguous even
// at 16 sessions.
function tsStr(i)  { return '2026-09-01T' + String(23 - i).padStart(2, '0') + ':00:00'; }
function monStr(i) {                 // i = 0 -> 2027-04, then back one month
  const t = 2027 * 12 + 3 - i;
  return String(Math.floor(t / 12)) + '-' + String((t % 12) + 1).padStart(2, '0');
}
function build(sessions, per, extra) {
  const rows = [];
  for (let i = 0; i < sessions; i++) {
    const ts = tsStr(i), mon = monStr(i);
    for (let k = 0; k < per; k++) rows.push(Object.assign({ uploaded_at: ts, reporting_month: mon }, extra || {}));
  }
  return rows;
}

async function dzLoadRecentUploads(src) {
  // Accepts a bare table name (every caller before v10.89) or { table, filter }.
  const source = (typeof src === 'string') ? { table: src } : (src || {});
  const table = source.table;
  if (!table) return [];
  const ckey = dzSourceKey(source);
  if (_dzRecentCache[ckey]) return _dzRecentCache[ckey];
  const cfg = (typeof UH_SOURCES !== 'undefined') ? UH_SOURCES[table] : null;
  if (!cfg) return [];
  try {
    const sb = await getSB();
    // A metadata table stores one row PER UPLOAD with the real count in a
    // column; counting its rows would report "1 rows" for every session.
    const rcField = cfg.rowCountField || null;
    // ⚠ .limit(4000) was a LIE: PostgREST caps a response at db-max-rows
    // (1000 by default), so a table whose newest upload is >=1000 rows
    // returned exactly that one session and the rail reported "1 upload".
    // Architecture Rule #4 - page with .range() instead.
    //
    // Paginate by SESSION, not by row: rows come back newest-upload-first,
    // so once a page reveals an OLDER uploaded_at, every newer session in
    // hand is complete. Stop as soon as enough complete sessions exist.
    const PAGE = 1000, MAX_PAGES = 15, WANT_SESSIONS = 14;
    const data = [];
    let pageFrom = 0, exhausted = false;
    for (let pageNo = 0; pageNo < MAX_PAGES; pageNo++) {
      let q = sb.from(table)
        .select(`uploaded_at, ${cfg.dateField}${rcField ? ', ' + rcField : ''}`);
      for (const [col, val] of Object.entries(source.filter || {})) q = q.eq(col, val);
      const { data: page, error } = await q
        .order('uploaded_at', { ascending: false })
        .range(pageFrom, pageFrom + PAGE - 1);
      if (error) { if (!data.length) return []; break; }
      if (!page || !page.length) { exhausted = true; break; }
      data.push(...page);
      if (page.length < PAGE) { exhausted = true; break; }
      // Count only sessions we KNOW are closed - the oldest one in hand may
      // still have rows on the next page.
      const seen = new Set(data.map(r => String(r.uploaded_at).slice(0, 19)));
      if (seen.size > WANT_SESSIONS) break;
      pageFrom += PAGE;
    }
    if (!data.length) return [];
    // Group by uploaded_at truncated to the second — one upload writes every
    // row inside the same second (the v6.88 convention).
    const byTs = new Map();
    for (const r of data) {
      if (!r.uploaded_at) continue;
      const ts = String(r.uploaded_at).slice(0, 19);
      let g = byTs.get(ts);
      if (!g) { g = { ts, rows: 0, min: null, max: null, table, periods: new Set() }; byTs.set(ts, g); }
      g.rows += rcField ? (Number(r[rcField]) || 0) : 1;
      const v = r[cfg.dateField];
      if (v != null) {
        const sv = String(v);
        g.periods.add(sv);
        if (g.min === null || sv < g.min) g.min = sv;
        if (g.max === null || sv > g.max) g.max = sv;
      }
    }
    // ⚠ If we stopped on the page cap rather than running out of rows, the
    // OLDEST session in hand may be cut mid-way, so its range and row count
    // would both be wrong. Drop it rather than print a number that looks
    // fine - a short list is honest, a wrong range is not.
    if (!exhausted && byTs.size > 1) {
      let oldest = null;
      for (const g of byTs.values()) if (!oldest || g.ts < oldest.ts) oldest = g;
      if (oldest) byTs.delete(oldest.ts);
    }
    // v10.90 - sort by the DATA PERIOD, not by upload time. Jason's spec was
    // "the most recent date range first", and the period is what the row
    // shows - ordering by a hidden field made the list look unsorted.
    // Upload time only breaks ties (several CSVs dropped in one go).
    const out = [...byTs.values()].sort((a, b) =>
      String(b.max || '').localeCompare(String(a.max || '')) ||
      String(b.min || '').localeCompare(String(a.min || '')) ||
      String(b.ts).localeCompare(String(a.ts)));
    _dzRecentCache[ckey] = out;
    return out;
  } catch (e) {
    console.warn('recent uploads unavailable for', table, e && e.message);
    return [];
  }
}

(async () => {

// -- 1. Jason's case: three 1000-row monthly uploads ---------------------
reset();
ROWS = build(3, 1000);
let r = await dzLoadRecentUploads('big');
t('D1  three 1000-row uploads surface as THREE sessions', r.length, 3);
t('D2  each reports its real row count', r.map(x => x.rows), [1000, 1000, 1000]);
t('D3  sorted newest data period first', r.map(x => x.max), [monStr(0), monStr(1), monStr(2)]);
t('D3b the fixture itself is sane - strictly descending valid timestamps',
  [tsStr(0), tsStr(15), monStr(0), monStr(15)],
  ['2026-09-01T23:00:00', '2026-09-01T08:00:00', '2027-04', '2026-01']);

// -- 2. The regression guard: reproduce the pre-v10.92 behaviour ---------
reset();
ROWS = build(3, 1000);
const sbOld = await getSB();
const oldRes = await sbOld.from('big').select('x').order().limit(4000).run_limit();
const oldTs = new Set(oldRes.data.map(x => String(x.uploaded_at).slice(0, 19)));
t('D4  the OLD single-.limit path really did see one session', oldTs.size, 1);
t('D5  ...and really did report exactly the cap as its row count', oldRes.data.length, 1000);

// -- 3. One big upload mid-page: the row count is now whole --------------
reset();
ROWS = build(1, 2500);
r = await dzLoadRecentUploads('big');
t('D6  a single 2,500-row upload reports 2,500 rows, not the 1,000 cap',
  [r.length, r[0].rows], [1, 2500]);
t('D7  a run that exhausted the rows keeps its only session', r.length, 1);

// -- 4. The page cap drops the session it may have cut ------------------
reset();
ROWS = build(16, 1000);          // 16,000 rows - more than MAX_PAGES can read
r = await dzLoadRecentUploads('big');
t('D8  the cap stops the walk without printing a cut session', r.length, 14);
const months = r.map(x => x.max);
t('D9  it is the OLDEST session that was dropped - the newest survives',
  [months[0], months.includes(monStr(15)), months.length], [monStr(0), false, 14]);
t('D10 every surviving session is whole', r.every(x => x.rows === 1000), true);

// -- 5. The filter is re-applied on every page --------------------------
reset();
ROWS = build(3, 1000, { view_type: 'brand' })
  .concat(build(2, 1000, { view_type: 'asin' }));
r = await dzLoadRecentUploads({ table: 'big', filter: { view_type: 'brand' } });
t('D11 a filtered source still pages', r.length >= 3, true);
t('D12 the filter rode along on EVERY page',
  EQ_CALLS.length > 1 && EQ_CALLS.every(c => c.length === 1 && c[0][0] === 'view_type' && c[0][1] === 'brand'),
  true);
t('D13 pages advance - no page served twice',
  RANGES.length > 1 && RANGES[1][0] > RANGES[0][0], true);

// -- 6. Errors ----------------------------------------------------------
reset();
ROWS = build(3, 1000); ERROR_ON_PAGE = 0;
r = await dzLoadRecentUploads('big');
t('D14 an error on the FIRST page returns nothing rather than guessing', r.length, 0);

reset();
ROWS = build(3, 1000); ERROR_ON_PAGE = 2;
r = await dzLoadRecentUploads('big');
t('D15 an error on a LATER page keeps the sessions already in hand', r.length >= 1, true);
t('D16 ...and drops the one it could not finish reading', r.every(x => x.rows === 1000), true);

// -- 7. rowCountField still wins over counting rows ---------------------
reset();
ROWS = build(2, 1, { row_count: 4321 });
r = await dzLoadRecentUploads('meta');
t('D17 a metadata table reports its stored count, not "1 rows"',
  r.map(x => x.rows), [4321, 4321]);

// -- 8. Cache -----------------------------------------------------------
reset();
ROWS = build(2, 1000);
await dzLoadRecentUploads('big');
const hitsAfterFirst = PAGE_HITS;
await dzLoadRecentUploads('big');
t('D18 a second call is served from cache, not re-queried', PAGE_HITS, hitsAfterFirst);

// -- 9. An unknown table degrades quietly -------------------------------
reset();
r = await dzLoadRecentUploads('not_in_uh_sources');
t('D19 a table missing from UH_SOURCES returns [] without throwing', r.length, 0);

console.log(JSON.stringify(out));
})();
