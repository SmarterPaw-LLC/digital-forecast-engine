function chewyProgramMonthly(opts) {
  const salesRows = opts.salesRows || [];
  const adRows = opts.adRows || [];
  const contribBySku = opts.contribBySku || {};      // chewy_sku -> $/unit
  const brandBySku = opts.brandBySku || {};
  const brand = opts.brand || '';
  const mo = (d) => String(d || '').slice(0, 7);     // YYYY-MM-DD -> YYYY-MM
  // v11.02 - the shared period window, as YYYY-MM-DD. Absent, every
  // comparable month is shown (the v11.01 behaviour).
  const winFrom = opts.from || null;
  const winTo = opts.to || null;

  const blank = () => ({
    totalUnits: 0, autoshipUnits: 0, retail: 0, contribution: 0, pricedUnits: 0,
    adUnits: 0, spend: 0, ntb: 0, signups: 0, adSales: 0,
  });
  const by = {};
  const touch = (m) => (by[m] || (by[m] = blank()));

  const sellMonths = new Set();
  for (const r of salesRows) {
    const m = mo(r.week_start);
    if (!m) continue;
    const sku = String(r.chewy_sku || '');
    if (brand && (brandBySku[sku] || '') !== brand) continue;
    sellMonths.add(m);
    const a = touch(m);
    const u = Number(r.units) || 0;
    a.totalUnits += u;
    a.autoshipUnits += Number(r.autoship) || 0;
    a.retail += Number(r.merch_sales) || 0;
    const c = contribBySku[sku];
    if (c != null && isFinite(c)) { a.contribution += u * c; a.pricedUnits += u; }
  }

  const adMonths = new Set();
  for (const r of adRows) {
    const m = mo(r.date);
    if (!m) continue;
    const sku = String(r.chewy_sku || '');
    if (brand && (brandBySku[sku] || '') !== brand) continue;
    adMonths.add(m);
    const a = touch(m);
    a.adUnits += Number(r.direct_units) || 0;
    a.spend += Number(r.spend) || 0;
    a.adSales += Number(r.direct_sales) || 0;
    a.ntb += Number(r.ntb_customers) || 0;
    a.signups += Number(r.autoship_signups) || 0;
  }

  const comparable = [...sellMonths].filter(m => adMonths.has(m)).sort();

  // ⚠ The window scopes what is SHOWN, never what is aggregated. allMonths
  // stays over the full comparable set so the year-over-year read below has a
  // prior-year twin to pair against - a 365-day window contains none by
  // definition, and windowing the aggregate would silently kill that panel.
  //
  // A month is IN when it overlaps the window at all. A month only partly
  // covered is shown and flagged rather than dropped: dropping it would lose
  // the current month-to-date, which is the month a month-over-month tracker
  // most needs. Partial months are excluded from the YoY pairing instead,
  // because comparing a part-month against a full one is precisely the
  // distortion the year-over-year read exists to remove.
  const monthEnd = (m) => {
    const y = Number(m.slice(0, 4)), mm = Number(m.slice(5, 7));
    const d = new Date(Date.UTC(y, mm, 0));             // day 0 of next month
    return m + '-' + String(d.getUTCDate()).padStart(2, '0');
  };
  const inWindow = (m) => {
    if (winTo && (m + '-01') > winTo) return false;
    if (winFrom && monthEnd(m) < winFrom) return false;
    return true;
  };
  const isPartial = (m) => {
    if (winFrom && winFrom > (m + '-01')) return true;
    if (winTo && winTo < monthEnd(m)) return true;
    return false;
  };

  const allMonths = comparable.map(m => {
    const a = by[m];
    const organic = a.totalUnits - a.adUnits;
    return {
      month: m,
      totalUnits: a.totalUnits,
      adUnits: a.adUnits,
      // ⚠ Can go NEGATIVE when Chewy attributes more units to clicks than the
      // sell-through feed recorded for the month - the two feeds are stamped on
      // different dates. Surfaced as-is rather than clamped to 0, because a
      // clamp would hide a feed disagreement worth knowing about.
      organicUnits: organic,
      autoshipUnits: a.autoshipUnits,
      adSharePct: a.totalUnits > 0 ? (a.adUnits / a.totalUnits) * 100 : null,
      autoshipSharePct: a.totalUnits > 0 ? (a.autoshipUnits / a.totalUnits) * 100 : null,
      retail: a.retail,
      contribution: a.contribution,
      pricedUnits: a.pricedUnits,
      pricedSharePct: a.totalUnits > 0 ? (a.pricedUnits / a.totalUnits) * 100 : null,
      spend: a.spend,
      programNet: a.contribution - a.spend,
      tacosPct: a.retail > 0 ? (a.spend / a.retail) * 100 : null,
      ntb: a.ntb,
      signups: a.signups,
      adSales: a.adSales,
      inWindow: inWindow(m),
      partial: inWindow(m) && isPartial(m),
    };
  });

  // v11.03 - month-over-month on UNITS, against the immediately preceding
  // COMPARABLE month.
  // ⚠ Read off allMonths, not the windowed set, so the FIRST month in the
  // window still has a predecessor when one exists on either side of the edge.
  // ⚠ null unless the predecessor is the literal previous calendar month - a
  // gap in the feed would otherwise be reported as a one-month change.
  // ⚠ null on a part-month: fewer days is not a decline.
  const prevMonthKey = (m) => {
    const y = Number(m.slice(0, 4)), mm = Number(m.slice(5, 7));
    return mm === 1 ? (y - 1) + '-12' : y + '-' + String(mm - 1).padStart(2, '0');
  };
  allMonths.forEach((r, i) => {
    const p = i > 0 ? allMonths[i - 1] : null;
    const ok = !!p && p.month === prevMonthKey(r.month) && !r.partial && !p.partial;
    r.momPrior = ok ? p.month : null;
    r.momPct = (ok && p.totalUnits > 0)
      ? ((r.totalUnits - p.totalUnits) / p.totalUnits) * 100 : null;
  });

  const months = allMonths.filter(r => r.inWindow);

  // v11.03 - ONE totals function. The scorecards compare this window against
  // a prior one, and two hand-written roll-ups would be two chances to
  // disagree about what Program Net means. Byte-identical to the v11.01
  // inline block for the same rows (asserted).
  const totalsOver = (rows) => {
    const sum = (k) => rows.reduce((t, r) => t + (Number(r[k]) || 0), 0);
    const o = {
      monthCount: rows.length,
      totalUnits: sum('totalUnits'), adUnits: sum('adUnits'),
      organicUnits: sum('organicUnits'), autoshipUnits: sum('autoshipUnits'),
      retail: sum('retail'), contribution: sum('contribution'),
      pricedUnits: sum('pricedUnits'), spend: sum('spend'), ntb: sum('ntb'),
    };
    o.programNet = o.contribution - o.spend;
    o.adSharePct = o.totalUnits > 0 ? (o.adUnits / o.totalUnits) * 100 : null;
    o.organicSharePct = o.totalUnits > 0 ? (o.organicUnits / o.totalUnits) * 100 : null;
    o.autoshipSharePct = o.totalUnits > 0 ? (o.autoshipUnits / o.totalUnits) * 100 : null;
    o.tacosPct = o.retail > 0 ? (o.spend / o.retail) * 100 : null;
    o.spendShareOfContribPct = o.contribution > 0 ? (o.spend / o.contribution) * 100 : null;
    o.pricedSharePct = o.totalUnits > 0 ? (o.pricedUnits / o.totalUnits) * 100 : null;
    return o;
  };
  const totals = totalsOver(months);

  // ── Year-over-year incrementality.
  //
  // ⚠ This is the only honest way to read incrementality from this data. A
  // before/after on the ad ramp would credit the ads with every seasonal and
  // merchandising move in between; comparing the SAME CALENDAR MONTHS one year
  // apart strips the seasonality out. It still cannot separate the ads from
  // category growth or Chewy's own merchandising, which is why the panel calls
  // the result directional rather than causal.
  //
  //   incrementality = delta total units / delta ad-attributed units
  //     100% = every ad-attributed unit was genuinely new
  //      <0% = total shrank while attribution grew - pure attribution shift
  // ⚠ Indexed over ALL comparable months, not the windowed ones. The prior
  // year sits OUTSIDE any window shorter than two years, so indexing the
  // windowed set would leave this panel permanently empty.
  const idx = {};
  allMonths.forEach(r => { idx[r.month] = r; });

  // v11.07 — ⚠ THE PRIOR-YEAR SIDE ACCEPTS A MONTH WITH NO ADS.
  // Jason: *"i don't know why your kitty kazoom is missing august and sept last
  // year."* KKZ ads went dark 2025-07 through 2026-02, so those months never
  // entered `comparable` (which requires BOTH feeds) and could not pair with
  // their 2026 twins. The KKZ incrementality read ran on 3 months, not 5.
  //
  // The comparable-months rule is right for the ROLL-UP, where a pre-ramp month
  // would dilute TACOS and flatter the program, and it still governs `months`
  // and `totals`. It is WRONG as a baseline filter: **a zero-ad prior-year month
  // is the cleanest counterfactual an incrementality read can have**, and
  // excluding it threw away exactly what the panel exists to measure.
  //
  // ⚠ Only the PRIOR side relaxes. The current side still comes from `months`,
  // so it still requires ads - without them there is nothing to measure.
  const priorIdx = Object.assign({}, idx);
  sellMonths.forEach(m => {
    if (priorIdx[m]) return;
    const a = by[m];
    if (!a) return;
    priorIdx[m] = {
      month: m, totalUnits: a.totalUnits, adUnits: a.adUnits,
      organicUnits: a.totalUnits - a.adUnits, autoshipUnits: a.autoshipUnits,
      retail: a.retail, contribution: a.contribution, pricedUnits: a.pricedUnits,
      spend: a.spend, ntb: a.ntb, signups: a.signups, adSales: a.adSales,
      programNet: a.contribution - a.spend,
      // ⚠ MUST match allMonths' semantics: `inWindow && isPartial`. Bare
      // isPartial() is TRUE for every month BEFORE the window start, so a bare
      // call flags every relaxed baseline month as a part-month and the pairs
      // filter drops it again - the fix would look applied and do nothing.
      partial: inWindow(m) && isPartial(m),
      // Flagged so a caller can say WHY a baseline month carries no spend
      // rather than leaving it to look like a gap in the data.
      noAdsInPeriod: true,
    };
  });
  const pairs = months.filter(r => {
    if (r.partial) return false;          // part-month vs full month is the distortion
    const [y, m] = r.month.split('-');
    const prior = priorIdx[(Number(y) - 1) + '-' + m];
    return !!prior && !prior.partial;
  });
  let yoy = null;
  if (pairs.length >= 2) {
    const ty = pairs;
    const ly = pairs.map(r => {
      const [y, m] = r.month.split('-');
      return priorIdx[(Number(y) - 1) + '-' + m];
    });
    const agg = (rows, k) => rows.reduce((t, r) => t + (Number(r[k]) || 0), 0);
    const dUnits = agg(ty, 'totalUnits') - agg(ly, 'totalUnits');
    const dAd = agg(ty, 'adUnits') - agg(ly, 'adUnits');
    const dOrg = agg(ty, 'organicUnits') - agg(ly, 'organicUnits');
    const dSpend = agg(ty, 'spend') - agg(ly, 'spend');
    const cpu = agg(ty, 'pricedUnits') > 0 ? agg(ty, 'contribution') / agg(ty, 'pricedUnits') : null;
    const incrContrib = cpu != null ? dUnits * cpu : null;
    yoy = {
      months: ty.map(r => r.month),
      priorMonths: ly.map(r => r.month),
      monthCount: ty.length,
      unitsNow: agg(ty, 'totalUnits'), unitsPrior: agg(ly, 'totalUnits'),
      adUnitsNow: agg(ty, 'adUnits'), adUnitsPrior: agg(ly, 'adUnits'),
      organicNow: agg(ty, 'organicUnits'), organicPrior: agg(ly, 'organicUnits'),
      autoshipNow: agg(ty, 'autoshipUnits'), autoshipPrior: agg(ly, 'autoshipUnits'),
      ntbNow: agg(ty, 'ntb'), ntbPrior: agg(ly, 'ntb'),
      spendNow: agg(ty, 'spend'), spendPrior: agg(ly, 'spend'),
      deltaUnits: dUnits, deltaAdUnits: dAd, deltaOrganic: dOrg, deltaSpend: dSpend,
      unitsGrowthPct: agg(ly, 'totalUnits') > 0 ? (dUnits / agg(ly, 'totalUnits')) * 100 : null,
      organicGrowthPct: agg(ly, 'organicUnits') > 0 ? (dOrg / agg(ly, 'organicUnits')) * 100 : null,
      // Only meaningful when attribution actually grew; a flat or shrinking
      // ad-attributed base makes the ratio a divide-by-noise.
      incrementalityPct: dAd > 0 ? (dUnits / dAd) * 100 : null,
      contributionPerUnit: cpu,
      incrementalContribution: incrContrib,
      incrementalRoiPct: (incrContrib != null && dSpend > 0) ? (incrContrib / dSpend) * 100 : null,
      incrementalNet: (incrContrib != null) ? incrContrib - dSpend : null,
    };
  }

  // v11.03 - the two bases the scorecards compare against. Both reuse the
  // YoY pairing rule: full months only, matched one-for-one, so a window
  // whose prior side is short compares like-for-like instead of a 5-month
  // total against a 3-month one.
  //
  // ⚠ prevYear is well defined on ALL TIME - it pairs months out of the
  // data, not windows - which is why this tab overrides the global all-time
  // delta suppression. prevPeriod is not, and comes back null there.
  const addMonths = (m, n) => {
    const y = Number(m.slice(0, 4)), mm = Number(m.slice(5, 7)) - 1 + n;
    const ny = y + Math.floor(mm / 12), nm = ((mm % 12) + 12) % 12;
    return ny + '-' + String(nm + 1).padStart(2, '0');
  };
  const pairOn = (shift) => {
    const now = [], prior = [];
    for (const r of months) {
      if (r.partial) continue;
      const p = priorIdx[shift(r.month)];
      if (!p || p.partial) continue;
      now.push(r); prior.push(p);
    }
    if (!now.length) return null;
    return {
      now: totalsOver(now), prior: totalsOver(prior),
      months: now.map(r => r.month), priorMonths: prior.map(r => r.month),
      // ⚠ Two plain counts rather than a `complete` boolean. A month goes
      // unpaired either because it is a part-month OR because its twin simply is
      // not on record - which is the NORMAL case on all time, where the earliest
      // year has nothing before it. One flag cannot distinguish them, and a note
      // built on it blamed part-months for both.
      paired: now.length,
      candidates: months.filter(r => !r.partial).length,
    };
  };
  const compare = {
    year:   pairOn(m => addMonths(m, -12)),
    period: months.length ? pairOn(m => addMonths(m, -months.length)) : null,
  };

  return {
    months, totals, yoy, compare,
    // v11.03 - the full comparable series. The chart's prior-year overlay
    // needs months OUTSIDE the window for the same reason the YoY index does.
    allMonths,
    coverage: {
      sellMonths: [...sellMonths].sort(),
      adMonths: [...adMonths].sort(),
      comparable,
      adOnly: [...adMonths].filter(m => !sellMonths.has(m)).sort(),
      sellOnly: [...sellMonths].filter(m => !adMonths.has(m)).sort(),
      // v11.02 - named, not silently dropped, same as the lagging tail above.
      partialMonths: months.filter(r => r.partial).map(r => r.month),
      outsideWindow: allMonths.filter(r => !r.inWindow).map(r => r.month),
      window: (winFrom || winTo) ? { from: winFrom, to: winTo } : null,
    },
  };
}

const SELL = [], ADS = [];
const MO = [];
for (let y = 2025, m = 5; !(y === 2026 && m === 10); ) {
  MO.push(y + '-' + String(m).padStart(2,'0'));
  m++; if (m === 13) { m = 1; y++; }
}
MO.forEach((mo, i) => {
  SELL.push({ week_start: mo + '-07', chewy_sku: 'S', units: 1000 + i * 10,
              units_sold: 1000 + i * 10, autoship: 400, autoship_units: 400,
              merch_sales: 10000 });
});
const AD_MONTHS = ['2025-05','2025-06','2025-07',
                   '2026-03','2026-04','2026-05','2026-06','2026-07','2026-08','2026-09'];
AD_MONTHS.forEach(mo => {
  const dark = mo.startsWith('2025');
  ADS.push({ date: mo + '-07', chewy_sku: 'S',
             direct_units: dark ? (mo === '2025-07' ? 0 : 30) : 600,
             spend: dark ? (mo === '2025-07' ? 0 : 150) : 1500,
             direct_sales: dark ? 300 : 6000,
             ntb_customers: dark ? 25 : 700, autoship_signups: dark ? 3 : 100,
             chewy_list_price: 10 });
});
const run = (o) => chewyProgramMonthly(Object.assign({
  salesRows: SELL, adRows: ADS, contribBySku: { S: 2 }, brandBySku: {} }, o || {}));


const out = {};
const W = { from: '2025-10-27', to: '2026-10-27' };
const r = run(W);
out.yoyMonths      = r.yoy ? r.yoy.months : null;
out.yoyPriorMonths = r.yoy ? r.yoy.priorMonths : null;
out.yoyCount       = r.yoy ? r.yoy.monthCount : 0;
out.unitsPrior     = r.yoy ? r.yoy.unitsPrior : null;
out.adUnitsPrior   = r.yoy ? r.yoy.adUnitsPrior : null;
out.organicPrior   = r.yoy ? r.yoy.organicPrior : null;

// THE REGRESSION GUARD: rebuild the pre-v11.07 index (comparable months only)
// and pair against it exactly as v11.06 did.
const comparableSet = new Set(r.allMonths.map(x => x.month));
const oldPairs = r.months.filter(x => {
  if (x.partial) return false;
  const [y, m] = x.month.split('-');
  return comparableSet.has((Number(y) - 1) + '-' + m);
});
out.oldPairCount  = oldPairs.length;
out.oldPairMonths = oldPairs.map(x => x.month);

// The roll-up must be unchanged: comparable months only.
out.rollupMonths = r.months.map(x => x.month);
out.allMonths    = r.allMonths.map(x => x.month);

// A current month with NO ads must never enter the current side.
out.currentHasDarkMonth = r.months.some(x => x.month >= '2025-08' && x.month <= '2026-02');

// compare.year uses the same relaxed baseline, so "vs last year" means one thing.
out.cmpYearPaired     = r.compare && r.compare.year ? r.compare.year.paired : null;
out.cmpYearCandidates = r.compare && r.compare.year ? r.compare.year.candidates : null;
console.log(JSON.stringify(out));
