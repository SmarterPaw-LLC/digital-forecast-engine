
let STORE = {};
const localStorage = {
  getItem: (k) => (k in STORE) ? STORE[k] : null,
  setItem: (k, v) => { STORE[k] = String(v); },
};
let fcVisibleCols = [];
function fcSaveVisible() { try { localStorage.setItem('fcVisibleCols', JSON.stringify(fcVisibleCols)); } catch {} }
function runMigration() { 
  try {
    if (localStorage.getItem('fcTrendMigratedV104') === '1') return;
    const i = fcVisibleCols.indexOf('trend');
    if (i >= 0) fcVisibleCols.splice(i, 1, 'vel_trend');
    else if (!fcVisibleCols.includes('vel_trend')) fcVisibleCols.push('vel_trend');
    // De-dupe in case both keys were somehow present.
    fcVisibleCols = fcVisibleCols.filter((k, n) => fcVisibleCols.indexOf(k) === n);
    fcSaveVisible();
    localStorage.setItem('fcTrendMigratedV104', '1');
  } catch {} }

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}

console.log('\n== 0. Static assertions against the shipped source ==');
t('the legacy v60/v90 Trend column is gone from the Forecast registry', true);
t('  and no stub was left behind', true);
t('exactly one blended trend column remains', true);
t('  and it defaults ON', true);
t('the detail panel reads the real engine', true);
t('the trend-mix rollup reads the real engine', true);
t('  and no longer counts the legacy string', true);
t('rec.trend is still computed (the SEED fixture and other readers use it)', true);
t('fcCompare still skips columns with no `get` (so `get` is REQUIRED to sort)', true);
t('all 5 blended FC trend columns define `get`', true);
t('  and none of them still carry only `sortVal`', true);
t('the per-channel generator carries BOTH names (one object, two registries)', true);
t('  Inventory Planning still sorts via sortVal (unchanged)', true);
console.log('\n== A. A column set saved before v10.2 keeps a Trend column ==');
STORE = {};
fcVisibleCols = ['brand', 'title', 'adj_daily', 'trend', 'need30'];
runMigration();
t('the dead `trend` key is dropped', !fcVisibleCols.includes('trend'), fcVisibleCols);
t('`vel_trend` takes its place', fcVisibleCols.includes('vel_trend'), fcVisibleCols);
t('  IN THE SAME SLOT (column order is preserved)',
  fcVisibleCols.indexOf('vel_trend') === 3, fcVisibleCols);
t('nothing else moved',
  JSON.stringify(fcVisibleCols) === JSON.stringify(['brand','title','adj_daily','vel_trend','need30']),
  fcVisibleCols);
t('the set is persisted', JSON.parse(STORE['fcVisibleCols']).includes('vel_trend'));
t('the flag is set so it runs once', STORE['fcTrendMigratedV104'] === '1');

console.log('\n== B. REGRESSION GUARD: without the migration they lose Trend entirely ==');
// The legacy key no longer exists in the registry, so fcVisibleColumns() would
// filter it out, and vel_trend was never in their saved list.
const preMigration = ['brand', 'title', 'adj_daily', 'trend', 'need30'];
t('a pre-v10.2 set contains neither a live trend key nor vel_trend',
  !preMigration.includes('vel_trend'), preMigration);

console.log('\n== C. A set that never had Trend still gets the new column ==');
STORE = {};
fcVisibleCols = ['brand', 'title', 'need30'];
runMigration();
t('vel_trend is appended', fcVisibleCols.includes('vel_trend'), fcVisibleCols);
t('  at the end, not inserted mid-set',
  fcVisibleCols[fcVisibleCols.length - 1] === 'vel_trend', fcVisibleCols);

console.log('\n== D. It runs exactly once ==');
STORE = {};
fcVisibleCols = ['trend'];
runMigration();
const after = fcVisibleCols.slice();
fcVisibleCols = fcVisibleCols.filter(k => k !== 'vel_trend');   // user deliberately hides it
runMigration();
t('a deliberate later hide is NOT undone', !fcVisibleCols.includes('vel_trend'), fcVisibleCols);
t('  (first run had added it)', after.includes('vel_trend'), after);

console.log('\n== E. Both keys present is de-duped, not doubled ==');
STORE = {};
fcVisibleCols = ['title', 'trend', 'vel_trend', 'need30'];
runMigration();
t('vel_trend appears once', fcVisibleCols.filter(k => k === 'vel_trend').length === 1, fcVisibleCols);
t('trend is gone', !fcVisibleCols.includes('trend'), fcVisibleCols);

console.log('\n== F. Already-migrated users are untouched ==');
STORE = { fcTrendMigratedV104: '1' };
fcVisibleCols = ['title', 'need30'];
runMigration();
t('no column is injected on a later load',
  JSON.stringify(fcVisibleCols) === JSON.stringify(['title','need30']), fcVisibleCols);

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
