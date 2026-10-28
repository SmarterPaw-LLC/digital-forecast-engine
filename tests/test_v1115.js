function parseCSV(line){
  const res=[]; let cur='',inQ=false;
  for(let i=0;i<(line||'').length;i++){
    const c=line[i];
    if(c==='"'){inQ=!inQ;}
    else if(c===','&&!inQ){res.push(cur);cur='';}
    else cur+=c;
  }
  res.push(cur); return res;
}
function adsProductSlug(label) {
  const s = String(label || '').toLowerCase().trim();
  if (s.includes('sponsored products')) return 'sponsored_products';   // SKIPPED at write
  if (s.includes('sponsored brands'))   return 'sponsored_brands';
  if (s.includes('sponsored display'))  return 'sponsored_display';
  if (s.includes('sponsored tv'))       return 'sponsored_tv';
  if (s.includes('dsp'))                return 'dsp';
  return null;
}
function adsParseDate(s) {
  if (!s) return null;
  const str = String(s).trim();
  // Native ISO already-normal
  if (/^\d{4}-\d{2}-\d{2}/.test(str)) return str.slice(0, 10);
  // Amazon format: "Mar 27, 2026"
  const m = str.match(/^([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})$/);
  if (m) {
    const months = { jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12 };
    const mo = months[m[1].toLowerCase()]; if (!mo) return null;
    return `${m[3]}-${String(mo).padStart(2,'0')}-${String(+m[2]).padStart(2,'0')}`;
  }
  // Fallback to existing helper
  if (typeof parseLocalDate === 'function' && typeof fmtLocalYMD === 'function') {
    const d = parseLocalDate(str); return d ? fmtLocalYMD(d) : null;
  }
  return null;
}
function adsStripExcel(v) {
  const s = String(v || '').trim();
  const m = s.match(/^="(.*)"$/);
  return m ? m[1] : s;
}
function adsMarketplaceToRegion(marketplace, country) {
  const m = String(marketplace || '').trim().toUpperCase();
  if (m === 'AMAZON.COM')       return 'US';
  if (m === 'AMAZON.CA')        return 'CA';
  if (m === 'AMAZON.COM.MX')    return 'MX';
  if (m === 'AMAZON.CO.UK')     return 'EU/UK';
  if (m === 'AMAZON.DE' || m === 'AMAZON.FR' || m === 'AMAZON.IT'
      || m === 'AMAZON.ES' || m === 'AMAZON.NL') return 'EU/UK';
  // Fallback on Country when marketplace is blank.
  const c = String(country || '').trim().toLowerCase();
  if (c === 'united states' || c === 'us') return 'US';
  if (c === 'canada'        || c === 'ca') return 'CA';
  if (c === 'mexico'        || c === 'mx') return 'MX';
  return 'US';   // safe default — every account we serve is US-primary
}
function adsAdvertiserToBrand(name) {
  const s = String(name || '').toLowerCase();
  if (s.includes('meowi')) return 'Meowijuana';
  if (s.includes('doggi')) return 'Doggijuana';
  if (s.includes('kitty') || s.includes('ka-zoom') || s.includes('kazoom')) return 'Kitty Ka-Zoom';
  return null;   // unknown — left null so the P&L brand-level fallback knows
}
function parseAmazonAdsUnified(text) {
  if (typeof parseCSV !== 'function') throw new Error('parseCSV helper missing');
  const lines = String(text || '').split(/\r?\n/).filter(l => l.length > 0);
  if (lines.length < 2) throw new Error('File appears empty.');
  const header = parseCSV(lines[0]).map(h => String(h || '').trim().toLowerCase());

  const ci = (...aliases) => {
    for (const a of aliases) {
      const idx = header.indexOf(String(a).toLowerCase());
      if (idx !== -1) return idx;
    }
    return -1;
  };
  const colDate    = ci('date');
  const colCountry = ci('country');
  const colAsin    = ci('advertised product id');
  const colMkt     = ci('advertised product marketplace');
  const colAdProd  = ci('ad product');
  const colAdvName = ci('advertiser account name');
  const colCurr    = ci('budget currency', 'currency');
  const colSpend   = ci('total cost', 'spend', 'cost');
  const colImp     = ci('impressions');
  const colClk     = ci('clicks');
  const colPurch   = ci('purchases', '14 day total purchases');
  const colSales   = ci('sales', '14 day total sales');
  // v11.15 — Campaign name, the dimension the Ads sub-tab is built on.
  // Optional: an export pulled before the column was ticked still parses,
  // and every row comes back campaign=null rather than guessing one.
  const colCamp    = ci('campaign name', 'campaign');

  if (colDate === -1 || colSpend === -1 || colAdProd === -1) {
    throw new Error('Required columns missing. Need at minimum: Date, Total cost, Ad product.');
  }

  const productByAsin = new Map();
  for (const p of allProducts || []) {
    if (p.asin) productByAsin.set(String(p.asin).trim().toUpperCase(), p.master_id);
  }

  const agg = new Map();     // key → row
  let skippedSp = 0, skippedBlankDate = 0, skippedZero = 0, totalRows = 0;
  const seenAdProducts = new Set();

  for (let i = 1; i < lines.length; i++) {
    const cells = parseCSV(lines[i]);
    if (!cells || cells.length < 2) continue;
    totalRows++;

    const adProdLabel = String(cells[colAdProd] || '');
    const slug = adsProductSlug(adProdLabel);
    if (!slug)                           { continue; }
    seenAdProducts.add(slug);
    // v8.17 — Sponsored Products used to be dropped here because v6.76
    // assumed SP was fully covered by SKU Economics. That was correct for
    // SPEND but wrong for ATTRIBUTED SALES — Amazon SKU Economics has no
    // per-ASIN ad-attributed sales column, only the "Sales" column in this
    // Amazon Ads report has it (per ASIN, per day). We now KEEP SP rows so
    // attributed_sales lands in amazon_ad_spend for real per-product ROAS.
    // The aggregator prefers sku_economics.sponsored_products_total for SP
    // SPEND (matches the P&L math and Amazon's official SP charge line)
    // and adds only the ATTRIBUTED SALES from amazon_ad_spend's SP rows —
    // no double-counting of the spend.

    const dateStr = adsParseDate(cells[colDate]);
    if (!dateStr) { skippedBlankDate++; continue; }

    const asinRaw = colAsin >= 0 ? adsStripExcel(cells[colAsin]) : '';
    const asin    = asinRaw && asinRaw.trim() ? asinRaw.trim().toUpperCase() : null;
    const mkt     = colMkt >= 0 ? String(cells[colMkt] || '').trim() : '';
    const country = colCountry >= 0 ? String(cells[colCountry] || '').trim() : '';
    const region  = adsMarketplaceToRegion(mkt, country);
    const brand   = colAdvName >= 0 ? adsAdvertiserToBrand(cells[colAdvName]) : null;
    // Blank stays NULL, never the empty string: '' would read as a real
    // campaign named nothing and sit beside the genuine pre-v11.15 nulls
    // as if it were a different thing.
    const campaign = colCamp >= 0
      ? (String(cells[colCamp] || '').trim() || null) : null;
    const curr    = colCurr >= 0 ? String(cells[colCurr] || 'USD').trim() : 'USD';

    const spend   = parseFloat(cells[colSpend])  || 0;
    const imp     = parseInt(cells[colImp])      || 0;
    const clk     = parseInt(cells[colClk])      || 0;
    const purch   = parseInt(cells[colPurch])    || 0;
    const sales   = parseFloat(cells[colSales])  || 0;

    // Skip rows that are pure zero across the board (Amazon often emits
    // these as placeholders for campaigns that ran but had no activity on a
    // given day — they bloat the upload but add nothing).
    if (spend === 0 && imp === 0 && clk === 0 && purch === 0 && sales === 0) {
      skippedZero++; continue;
    }

    // master_id resolution. Null is fine — TV/DSP rows are intentionally
    // brand-level, and unmatched ASINs surface as "unattributed" in the P&L
    // for triage rather than silently double-counting somewhere.
    const masterId = asin && productByAsin.get(asin) || null;

    const key = `${dateStr}|${region}|${slug}|${asin || ''}|${brand || ''}|${campaign || ''}`;
    let row = agg.get(key);
    if (!row) {
      row = {
        date: dateStr, region, ad_product: slug,
        advertiser_brand: brand, asin, master_id: masterId,
        marketplace: mkt || null,
        spend: 0, impressions: 0, clicks: 0, purchases: 0, attributed_sales: 0,
        currency: curr, source: 'amazon-ads-unified',
        // v11.15 ⚠ campaign is part of the KEY above, not just carried here.
        // Were it only carried, two campaigns on one (date, region, ad product,
        // ASIN, brand) would collapse into a single row wearing the first
        // campaign's name - the whole window's spend attributed to one of them.
        //
        // Every consumer of amazonAdSpendData accumulates (+=) or set-adds
        // (buildAdSpendBuckets, the two perSlugSpend scans, the SP coverage
        // probe), so the finer grain leaves every existing total byte-identical.
        // Checked before shipping; a consumer that OVERWROTE on a key would
        // start dropping rows here instead.
        campaign,
      };
      agg.set(key, row);
    }
    row.spend            += spend;
    row.impressions      += imp;
    row.clicks           += clk;
    row.purchases        += purch;
    row.attributed_sales += sales;
  }

  // Round to 4 decimals on totals (Amazon emits up to 4dp; avoid float noise).
  const rows = Array.from(agg.values()).map(r => ({
    ...r,
    spend:            +r.spend.toFixed(4),
    attributed_sales: +r.attributed_sales.toFixed(4),
  }));
  return {
    rows,
    totalRows,
    skippedSp, skippedBlankDate, skippedZero,
    distinctDays: new Set(rows.map(r => r.date)).size,
    distinctAsins: new Set(rows.filter(r => r.asin).map(r => r.asin)).size,
    seenAdProducts: [...seenAdProducts],
    // hasCampaignCol distinguishes 'the export did not carry the column' from
    // 'it carried it and every value was blank'. The operator's next move is
    // different in each case, so the status line must not merge them.
    hasCampaignCol: colCamp >= 0,
    distinctCampaigns: new Set(rows.filter(r => r.campaign).map(r => r.campaign)).size,
  };
}

var allProducts = [{ asin: 'B07KPRTSMT', master_id: 'SP-0001' },
                   { asin: 'B08ZZZZZZZ', master_id: 'SP-0002' }];

const HDR_CAMP = 'Date,Country,Advertised product id,Advertised product marketplace,'
  + 'Ad product,Advertiser account name,Campaign name,Budget currency,Total cost,'
  + 'Impressions,Clicks,Purchases,Sales';
const HDR_BARE = 'Date,Country,Advertised product id,Advertised product marketplace,'
  + 'Ad product,Advertiser account name,Budget currency,Total cost,'
  + 'Impressions,Clicks,Purchases,Sales';

// date, asin, ad product, campaign, cost, imp, clk, purch, sales
const DATA = [
  ['2026-10-01','B07KPRTSMT','Sponsored Products','SP - Meowi Exact',    10, 1000, 50, 5, 100],
  ['2026-10-01','B07KPRTSMT','Sponsored Products','SP - Meowi Broad',    20, 2000, 40, 3,  60],
  ['2026-10-01','B07KPRTSMT','Sponsored Brands',  'SB - Brand Defense',  30, 3000, 30, 2,  40],
  ['2026-10-02','B07KPRTSMT','Sponsored Products','SP - Meowi Exact',    15, 1500, 20, 1,  25],
  ['2026-10-02','B08ZZZZZZZ','Sponsored Products','SP - Meowi Exact',     5,  500, 10, 1,  11],
  ['2026-10-03',''          ,'Sponsored TV',      'TV - Awareness',      40, 9000,  0, 0,   0],
  // a blank campaign cell on an export that HAS the column
  ['2026-10-03','B07KPRTSMT','Sponsored Display', '',                     7,  700,  7, 0,   0],
];

function line(r, withCamp) {
  const cells = ['' + r[0], 'US', r[1], 'AMAZON.COM', r[2], 'Meowijuana Store'];
  if (withCamp) cells.push('"' + r[3] + '"');
  cells.push('USD', r[4], r[5], r[6], r[7], r[8]);
  return cells.join(',');
}
const CSV_CAMP = [HDR_CAMP].concat(DATA.map(r => line(r, true ))).join('\n');
const CSV_BARE = [HDR_BARE].concat(DATA.map(r => line(r, false))).join('\n');


const out = {};
const sum = (rows, f) => +rows.reduce((a, r) => a + (+r[f] || 0), 0).toFixed(4);

const withC = parseAmazonAdsUnified(CSV_CAMP);
const noC   = parseAmazonAdsUnified(CSV_BARE);

out.withRows = withC.rows.length;
out.noRows   = noC.rows.length;
out.hasCol   = { withC: withC.hasCampaignCol, noC: noC.hasCampaignCol };
out.distinct = { withC: withC.distinctCampaigns, noC: noC.distinctCampaigns };

// The two SP campaigns on 2026-10-01 / B07KPRTSMT must be two rows.
const d1 = withC.rows.filter(r => r.date === '2026-10-01'
  && r.asin === 'B07KPRTSMT' && r.ad_product === 'sponsored_products');
out.d1Count     = d1.length;
out.d1Campaigns = d1.map(r => r.campaign).sort();
out.d1Spend     = d1.map(r => r.spend).sort((a, b) => a - b);

// THE REGRESSION GUARD: rebuild the pre-v11.15 key and group by it.
const oldKeys = new Map();
for (const r of withC.rows) {
  const k = [r.date, r.region, r.ad_product, r.asin || '', r.advertiser_brand || ''].join('|');
  if (!oldKeys.has(k)) oldKeys.set(k, []);
  oldKeys.get(k).push(r);
}
const collapsed = [...oldKeys.entries()].filter(([, v]) => v.length > 1);
out.oldRowCount        = oldKeys.size;
out.oldCollapsedGroups = collapsed.length;
// what the old key would have stamped the merged row with, and the spend it
// would have carried under that one name
out.oldCollapsedExample = collapsed.length
  ? { campaignKept: collapsed[0][1][0].campaign,
      campaignLost: collapsed[0][1].slice(1).map(r => r.campaign),
      spendUnderOneName: +collapsed[0][1].reduce((a, r) => a + r.spend, 0).toFixed(4) }
  : null;

// SUMS. Finer grain must not move a single total.
for (const f of ['spend', 'impressions', 'clicks', 'purchases', 'attributed_sales']) {
  out['sum_' + f] = { withC: sum(withC.rows, f), noC: sum(noC.rows, f) };
}

// The bare export must be unchanged at the OLD grain, and campaign must be
// null on every row rather than '' or absent.
out.noCampaignValues = [...new Set(noC.rows.map(r => r.campaign))];
out.noCampaignIsNull = noC.rows.every(r => r.campaign === null);
out.noCHasKey        = noC.rows.every(r => Object.prototype.hasOwnProperty.call(r, 'campaign'));
out.bareKeysMatchOld = noC.rows.length === oldKeys.size;

// A blank cell on a column-carrying export is NULL, never ''.
const blank = withC.rows.filter(r => r.ad_product === 'sponsored_display');
out.blankCampaign = blank.map(r => r.campaign);

// Brand-level (no ASIN) rows still carry their campaign.
const tv = withC.rows.filter(r => r.ad_product === 'sponsored_tv');
out.tvCampaign = tv.map(r => r.campaign);
out.tvAsin     = tv.map(r => r.asin);

// master_id resolution is untouched by the new key.
out.mastersWithC = [...new Set(withC.rows.map(r => r.master_id))].sort();
out.mastersNoC   = [...new Set(noC.rows.map(r => r.master_id))].sort();

// Degenerate shapes must not throw or leak a bad value.
out.degenerate = [];
const BAD = [
  [HDR_CAMP, 'Date,Country,Advertised product id,Advertised product marketplace,Ad product,Advertiser account name,Campaign name,Budget currency,Total cost,Impressions,Clicks,Purchases,Sales'].join('\n'),
  HDR_CAMP + '\n2026-10-01,US,,,Sponsored Products,,,,0,0,0,0,0',
  HDR_CAMP + '\n2026-10-01,US,B07KPRTSMT,AMAZON.COM,Sponsored Products,Meowijuana Store,"   ",USD,1,1,1,0,0',
];
for (const csv of BAD) {
  try {
    const r = parseAmazonAdsUnified(csv);
    const blob = JSON.stringify(r.rows);
    out.degenerate.push({ rows: r.rows.length,
      bad: /NaN|Infinity|undefined/.test(blob),
      camps: [...new Set(r.rows.map(x => x.campaign))] });
  } catch (e) { out.degenerate.push({ threw: String(e.message || e) }); }
}
console.log(JSON.stringify(out));
