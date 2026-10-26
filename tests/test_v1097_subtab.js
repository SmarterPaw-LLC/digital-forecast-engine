
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

// -- DOM stub ------------------------------------------------------------
let NODES = {};
let CLICKS = [];
function mkBtn(id, label) {
  return { id, className: 'subtab', style: {}, textContent: label || id,
           click() { CLICKS.push(this.id); } };
}
const document = { getElementById: (id) => NODES[id] || null };
function pageSettingsCurrentNavKey() { return NAVKEY; }
let NAVKEY = 'pnl_amazon';
let _globalSubtabVis = null;
// Module-scope state subtabApply owns, lifted so the real function runs intact.
const _subtabRegistry = {};
let _subtabHealing = false;

function subtabStripKey(pairs) {
  const ids = (pairs || []).map(p => String(p[0] || '')).filter(Boolean);
  if (!ids.length) return '';
  let pre = ids[0];
  for (const id of ids.slice(1)) {
    let i = 0;
    while (i < pre.length && i < id.length && pre[i] === id[i]) i++;
    pre = pre.slice(0, i);
  }
  return pre.replace(/-+$/, '') || ids[0];
}
function subtabIsHidden(stripKey, viewKey) {
  const strip = (_globalSubtabVis || {})[stripKey];
  return !!(strip && strip[viewKey] === false);
}
function subtabApply(pairs, activeKey) {
  const stripKey = subtabStripKey(pairs);

  // Register for the settings panel: ids, keys and the label as rendered.
  if (stripKey) {
    _subtabRegistry[stripKey] = {
      stripKey,
      pairs: pairs.map(p => [p[0], p[1]]),
      navKey: (typeof pageSettingsCurrentNavKey === 'function') ? pageSettingsCurrentNavKey() : '',
      labels: Object.fromEntries(pairs.map(([btnId, key]) => {
        const b = document.getElementById(btnId);
        return [key, (b ? b.textContent : key).trim()];
      })),
    };
  }

  // ⚠ Never hide every tab in a strip. An all-hidden strip is a page with no
  // way back into itself, and nothing on screen would explain why.
  const visible = pairs.filter(([, key]) => !subtabIsHidden(stripKey, key));
  const enforce = visible.length > 0;

  for (const [btnId, key] of pairs) {
    const b = document.getElementById(btnId);
    if (!b) continue;
    b.className = 'subtab' + (key === activeKey ? ' on' : '');
    b.style.display = (enforce && subtabIsHidden(stripKey, key)) ? 'none' : '';
  }

  // ⚠ Self-heal: if the tab you are ON gets hidden, move to the first visible
  // one rather than stranding the user on a panel with no lit tab. Clicking the
  // button reuses the strip's own switch function, so no routing is duplicated
  // here. The flag stops the re-entrant subtabApply from looping.
  if (enforce && !_subtabHealing && subtabIsHidden(stripKey, activeKey)) {
    const first = visible[0] && document.getElementById(visible[0][0]);
    if (first) {
      _subtabHealing = true;
      try { first.click(); } catch (e) { console.warn('subtab heal failed', e); }
      finally { _subtabHealing = false; }
    }
  }
}

function build(pairs) {
  NODES = {}; CLICKS = [];
  for (const [id, key] of pairs) NODES[id] = mkBtn(id, 'Label ' + key);
}
const shown = (pairs) => pairs.filter(([id]) => NODES[id].style.display !== 'none').map(([, k]) => k);

// -- 1. Strip keys, against the app's REAL strips ------------------------
const REAL = [[["dst-uploads", "uploads"], ["dst-history", "history"], ["dst-query", "query"]], [["pricing-mode-new", "new"], ["pricing-mode-existing", "existing"], ["pricing-mode-chewy", "chewy"]], [["pnl-amzn-tab-summary", "summary"], ["pnl-amzn-tab-perf", "performance"], ["pnl-amzn-tab-diag", "diagnostics"], ["pnl-amzn-tab-changelog", "changelog"], ["pnl-amzn-tab-growth", "growth"], ["pnl-amzn-tab-opps", "opportunities"], ["pnl-amzn-tab-adactivity", "adactivity"], ["pnl-amzn-tab-breakeven", "breakeven"]], [["ipv-planning", "planning"], ["ipv-reorder", "reorder"]], [["ds-view-grid", "grid"], ["ds-view-reports", "reports"]]];
const keys = REAL.map(p => subtabStripKey(p));
t('C1 every real strip yields a non-empty key', keys.every(k => !!k), true);
t('C2 strip keys are unique - no two strips collide',
  new Set(keys).size, keys.length);
t('C3 no key keeps a trailing dash', keys.every(k => !/-$/.test(k)), true);
t('C4 the Amazon P&L strip resolves to its shared prefix',
  subtabStripKey([['pnl-amzn-tab-summary','summary'],['pnl-amzn-tab-perf','performance']]),
  'pnl-amzn-tab');
t('C5 a single-button strip still yields a key',
  subtabStripKey([['ipv-planning','planning']]), 'ipv-planning');
t('C6 empty input does not throw', subtabStripKey([]), '');

// -- 2. Hiding ------------------------------------------------------------
const AMZ = [['pnl-amzn-tab-summary','summary'],['pnl-amzn-tab-perf','performance'],
             ['pnl-amzn-tab-adactivity','adactivity']];
build(AMZ);
_globalSubtabVis = { 'pnl-amzn-tab': { adactivity: false } };
subtabApply(AMZ, 'summary');
t('C7 a hidden sub-tab is removed from the strip', shown(AMZ), ['summary','performance']);
t('C8 the active tab is still marked on', NODES['pnl-amzn-tab-summary'].className, 'subtab on');
t('C9 hiding does not click anything', CLICKS, []);

// Visible again the moment it is ticked back on - nothing is deleted.
build(AMZ);
_globalSubtabVis = {};
subtabApply(AMZ, 'summary');
t('C10 absent from the hide-list means visible', shown(AMZ), ['summary','performance','adactivity']);

// A sub-tab nobody has an opinion about is visible, so a NEW one added in a
// later version does not inherit an old hide-list.
build(AMZ);
_globalSubtabVis = { 'pnl-amzn-tab': { somethingRemoved: false } };
subtabApply(AMZ, 'summary');
t('C11 a stale key for a tab that no longer exists hides nothing',
  shown(AMZ), ['summary','performance','adactivity']);

// -- 3. Never leave a strip with zero tabs -------------------------------
build(AMZ);
_globalSubtabVis = { 'pnl-amzn-tab': { summary: false, performance: false, adactivity: false } };
subtabApply(AMZ, 'summary');
t('C12 an all-hidden strip is ignored - every tab stays visible',
  shown(AMZ), ['summary','performance','adactivity']);
t('C13 ...and it does not try to heal into nothing', CLICKS, []);

// -- 4. Self-heal when the ACTIVE tab is hidden --------------------------
build(AMZ);
_globalSubtabVis = { 'pnl-amzn-tab': { adactivity: false } };
subtabApply(AMZ, 'adactivity');
t('C14 being on a hidden tab moves you to the first visible one',
  CLICKS, ['pnl-amzn-tab-summary']);

// The heal must not loop: the re-entrant call during the click is suppressed.
build(AMZ);
NODES['pnl-amzn-tab-summary'].click = function () {
  CLICKS.push(this.id);
  subtabApply(AMZ, 'adactivity');   // what the real switch fn would do
};
_globalSubtabVis = { 'pnl-amzn-tab': { adactivity: false } };
subtabApply(AMZ, 'adactivity');
t('C15 the heal cannot loop', CLICKS.length, 1);

// Healing to the first VISIBLE tab, not merely the first tab.
const S2 = [['x-a','a'],['x-b','b'],['x-c','c']];
build(S2);
_globalSubtabVis = { 'x': { a: false, c: false } };
subtabApply(S2, 'c');
t('C16 it heals to the first VISIBLE tab, skipping hidden ones', CLICKS, ['x-b']);

// -- 5. The registry the settings panel reads ----------------------------
build(AMZ);
_globalSubtabVis = null;
NAVKEY = 'pnl_amazon_changelog';
subtabApply(AMZ, 'summary');
t('C17 the strip registers itself with the nav key it rendered under',
  [_subtabRegistry['pnl-amzn-tab'].stripKey, _subtabRegistry['pnl-amzn-tab'].navKey],
  ['pnl-amzn-tab', 'pnl_amazon_changelog']);
t('C18 ...and captures the rendered labels for the panel',
  _subtabRegistry['pnl-amzn-tab'].labels.adactivity, 'Label adactivity');

console.log(JSON.stringify(out));
