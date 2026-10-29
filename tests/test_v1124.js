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

var allProducts = [];
const LINES = [
  'Date,Country,Advertised product ID,Ad product,Advertiser account name,Campaign name,Total cost,Impressions,Clicks,Purchases,Sales',
  '2026-10-01,US,B0SP00001,Sponsored Products,Meowijuana,SP - AUTO,100.00,5000,80,6,400',
  '2026-10-01,US,B0SB00002,Sponsored Brands,Meowijuana,SBV - KW,50.00,3000,20,1,90',
  '2026-10-02,US,B0SD00003,Sponsored Display,Meowijuana,SD - RT,9.00,900,4,0,0',
  '2026-10-02,US,,Sponsored TV,Meowijuana,TV - In Market,25.00,9000,0,0,0',
];
const parsed = parseAmazonAdsUnified(LINES.join('\n'));
const bySlug = {};
for (const r of parsed.rows) bySlug[r.ad_product] = (bySlug[r.ad_product] || 0) + r.spend;
console.log(JSON.stringify({
  slugs: Object.keys(bySlug).sort(),
  spSpend: bySlug['sponsored_products'] || 0,
  total: parsed.rows.reduce((a, r) => a + r.spend, 0),
  spRows: parsed.rows.filter(r => r.ad_product === 'sponsored_products').length,
}));
