
let seoRows = [], seoCompareMap = null, seoSortKey = 'impressions', seoSortDir = -1;
const DOM = { 'seo-minimp': '0', 'seo-search': '', 'seo-quick': 'all' };
function document_getElementById(id) { return (id in DOM) ? { value: DOM[id] } : null; }
const document = { getElementById: document_getElementById };

function seoVisibleRows() {
  const minImp = Math.max(0, parseInt(document.getElementById('seo-minimp')?.value, 10) || 0);
  const term = (document.getElementById('seo-search')?.value || '').trim().toLowerCase();
  const quick = document.getElementById('seo-quick')?.value || 'all';
  const out = [];
  for (const r of seoRows) {
    if (r.impressions < minImp) continue;
    if (term && !String(r.query).toLowerCase().includes(term)) continue;
    const prev = seoCompareMap ? seoCompareMap.get(r.query) : null;
    // position IMPROVES when the number goes DOWN, so the sign is flipped
    // here deliberately: dPos > 0 means "moved up the page".
    const dPos = prev && prev.avg_position != null && r.avg_position != null
      ? (prev.avg_position - r.avg_position) : null;
    const dImp = prev ? (r.impressions - prev.impressions) : null;
    if (quick === 'striking'  && !(r.avg_position > 10 && r.avg_position <= 20)) continue;
    if (quick === 'page1'     && !(r.avg_position > 0 && r.avg_position <= 10)) continue;
    if (quick === 'rising'    && !(dPos != null && dPos > 0.5)) continue;
    if (quick === 'falling'   && !(dPos != null && dPos < -0.5)) continue;
    if (quick === 'new'       && !(seoCompareMap && !prev)) continue;
    if (quick === 'noclicks'  && !(r.clicks === 0 && r.impressions > 0)) continue;
    out.push({ ...r, _dPos: dPos, _dImp: dImp, _isNew: !!(seoCompareMap && !prev) });
  }
  const k = seoSortKey;
  out.sort((a, b) => {
    let av = a[k], bv = b[k];
    if (k === '_dPos' || k === '_dImp') { av = av == null ? -1e9 : av; bv = bv == null ? -1e9 : bv; }
    if (typeof av === 'string') return seoSortDir * av.localeCompare(bv);
    return seoSortDir * ((av || 0) - (bv || 0));
  });
  return out;
}

const out = {};
function setup() {
  seoRows = [
    { query: 'meowijuana',        clicks: 1969, impressions: 19248, ctr_pct: 10.23, avg_position: 2.63 },
    { query: 'catnip spray',      clicks: 12,   impressions: 4800,  ctr_pct: 0.25,  avg_position: 14.2 },
    { query: 'silvervine sticks', clicks: 0,    impressions: 1200,  ctr_pct: 0.00,  avg_position: 17.9 },
    { query: 'cat grass',         clicks: 3,    impressions: 560,   ctr_pct: 0.54,  avg_position: 66.1 },
  ];
  seoCompareMap = new Map([
    ['meowijuana',        { avg_position: 3.4,  impressions: 18000 }],  // improved 3.4 -> 2.63
    ['catnip spray',      { avg_position: 12.1, impressions: 5200  }],  // worsened 12.1 -> 14.2
    ['silvervine sticks', { avg_position: 19.4, impressions: 900   }],  // improved
  ]);
  DOM['seo-minimp'] = '0'; DOM['seo-search'] = ''; DOM['seo-quick'] = 'all';
  seoSortKey = 'impressions'; seoSortDir = -1;
}

setup();
let r = seoVisibleRows();
out.all = r.map(x => [x.query, x._dPos === null ? null : +x._dPos.toFixed(2), x._isNew]);

// the sign convention, stated as the question a reader would ask
out.improvedIsPositive = r.find(x => x.query === 'meowijuana')._dPos > 0;
out.worsenedIsNegative = r.find(x => x.query === 'catnip spray')._dPos < 0;
out.newHasNullDelta    = r.find(x => x.query === 'cat grass')._dPos === null;
out.newIsFlagged       = r.find(x => x.query === 'cat grass')._isNew === true;

setup(); DOM['seo-quick'] = 'striking';
out.striking = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'page1';
out.page1 = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'rising';
out.rising = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'falling';
out.falling = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'new';
out.newOnly = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-quick'] = 'noclicks';
out.noclicks = seoVisibleRows().map(x => x.query);

setup(); DOM['seo-minimp'] = '1000';
out.floored = seoVisibleRows().map(x => x.query);
setup(); DOM['seo-search'] = 'CATNIP';
out.searchCaseInsensitive = seoVisibleRows().map(x => x.query);

setup(); seoSortKey = 'avg_position'; seoSortDir = 1;
out.sortByPosAsc = seoVisibleRows().map(x => x.query);

// no comparison snapshot: deltas must be null, nothing marked new
setup(); seoCompareMap = null;
const nc = seoVisibleRows();
out.noCompareAllNull = nc.every(x => x._dPos === null && x._dImp === null);
out.noCompareNoneNew = nc.every(x => x._isNew === false);

console.log(JSON.stringify(out));
