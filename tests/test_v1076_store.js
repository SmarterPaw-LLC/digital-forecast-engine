
async function loadSalesGoals() {
  try {
    const sb = await getSB();
    const { data, error } = await sb.from('app_settings')
      .select('value').eq('key', 'sales_unit_goals').maybeSingle();
    if (error) throw error;
    const v = data?.value;
    salesGoals = (v && typeof v === 'object' && !Array.isArray(v)) ? v : {};
    _salesGoalsLoaded = true;
  } catch (e) {
    // Fail open — no goals rather than a broken page. Same precedence
    // loadGlobalViewDefaults sets: a settings read that cannot complete must
    // never change what anyone sees.
    console.warn('[sales goals] unavailable (chart renders without the goal line):', e?.message || e);
    salesGoals = {};
  }
  return salesGoals;
}
async function writeSalesGoals(next) {
  const sb = await getSB();
  // Prune to positive integers and drop empty channels, so a month the
  // operator blanked out really does become "no goal set" rather than 0.
  const clean = {};
  Object.entries(next || {}).forEach(([ch, months]) => {
    const m = {};
    Object.entries(months || {}).forEach(([k, v]) => {
      const num = Number(v);
      if (isFinite(num) && num > 0) m[k] = Math.round(num);
    });
    if (Object.keys(m).length) clean[ch] = m;
  });
  const payload = Object.keys(clean).length ? clean : null;
  const { error } = await sb.from('app_settings')
    .upsert({ key: 'sales_unit_goals', value: payload }, { onConflict: 'key' });
  if (error) throw error;
  salesGoals = clean;
}

let salesGoals = {};
let _salesGoalsLoaded = false;
let _sent = null, _mode = 'ok', _stored = null;

const getSB = async () => ({
  from: () => ({
    select: () => ({ eq: () => ({ maybeSingle: async () =>
      _mode === 'err'   ? { data: null, error: { message: 'relation "app_settings" does not exist' } }
    : _mode === 'array' ? { data: { value: [1, 2, 3] }, error: null }
    : _mode === 'null'  ? { data: null, error: null }
    :                     { data: { value: _stored }, error: null }
    }) }),
    upsert: async (row) => { _sent = row; return { error: null }; },
  }),
});

const out = [];
const T = (name, got, want) => out.push({ name, got, want, pass: JSON.stringify(got) === JSON.stringify(want) });

(async () => {
  // write prunes
  await writeSalesGoals({
    amazon_us: { '2026-01': 3100, '2026-02': 0, '2026-03': '', '2026-04': -5, '2026-05': '4200' },
    shopify:   { '2026-01': null },
    chewy:     {},
  });
  T('E1 blanks / zero / negatives are dropped; strings coerce; empty channels vanish',
    _sent.value, { amazon_us: { '2026-01': 3100, '2026-05': 4200 } });
  T('E2 upsert targets the app_settings key', _sent.key, 'sales_unit_goals');
  T('E3 the in-memory copy matches what was stored',
    salesGoals, { amazon_us: { '2026-01': 3100, '2026-05': 4200 } });

  await writeSalesGoals({ amazon_us: { '2026-01': 0 } });
  T('E4 an all-blank grid stores null, not an empty object', _sent.value, null);

  // load
  _mode = 'ok'; _stored = { shopify: { '2026-06': 900 } };
  salesGoals = { stale: {} };
  await loadSalesGoals();
  T('E5 load replaces the local copy with the shared one', salesGoals, { shopify: { '2026-06': 900 } });
  T('E6 load marks itself done so the toggle stops re-fetching', _salesGoalsLoaded, true);

  _mode = 'err'; salesGoals = { shopify: { '2026-06': 900 } };
  await loadSalesGoals();
  T('E7 a failed read FAILS OPEN to no goals (never a broken page)', salesGoals, {});

  _mode = 'array';
  await loadSalesGoals();
  T('E8 a non-object stored value is rejected rather than indexed into', salesGoals, {});

  _mode = 'null';
  await loadSalesGoals();
  T('E9 an empty app_settings row reads as no goals', salesGoals, {});

  console.log(JSON.stringify(out));
})();
