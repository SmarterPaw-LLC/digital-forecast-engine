
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

const TBL_FIT_GUTTER = 24;   // breathing room below the table
const TBL_FIT_MIN    = 280;  // never collapse to an unusable sliver
const TBL_FIT_STICKY = 100;  // app header (54px) + the sticky global search bar

let VH = 900;
const window = { innerHeight: VH };
let ELS = [];
const document = { querySelectorAll: () => ELS };

function fitTableWrapsToViewport() {
  const vh = window.innerHeight;
  document.querySelectorAll('.tbl-wrap[data-fit="viewport"]').forEach(el => {
    if (!el.offsetParent) return;                 // hidden tab — rect would be 0
    const top = el.getBoundingClientRect().top;
    const natural = vh - top - TBL_FIT_GUTTER;
    // ⚠ v10.77 — a table measured while it sits BELOW THE FOLD has no
    // meaningful "space left": innerHeight - top goes NEGATIVE, Math.max pins it
    // at the 280px floor (~5 rows), and nothing re-fits on scroll, so it STAYS
    // there. Jason hit this on Amazon P&L, where 9 scorecards plus a 123-week
    // chart push the table off-screen at render time: 272 products, 5 visible
    // rows, dead space underneath.
    //
    // Measuring from the element is still right when the element is actually in
    // view — that is the whole v10.56 point, since each tab has different
    // chrome above its table. It is only the below-the-fold case that cannot be
    // measured, so fall back to the space the table WILL have once scrolled to:
    // the viewport minus the sticky chrome. Anything that already clears the
    // floor is left exactly as v10.56 computed it.
    const h = natural >= TBL_FIT_MIN
      ? Math.round(natural)
      : Math.max(TBL_FIT_MIN, Math.round(vh - TBL_FIT_STICKY - TBL_FIT_GUTTER));
    const want = h + 'px';
    if (el.style.maxHeight !== want) el.style.maxHeight = want;
  });
}

// The PRE-v10.77 body, for the equivalence proof and the regression guard.
function oldFit() {
  ELS.forEach(el => {
    if (!el.offsetParent) return;
    const top = el.getBoundingClientRect().top;
    const h = Math.max(TBL_FIT_MIN, Math.round(window.innerHeight - top - TBL_FIT_GUTTER));
    const want = h + 'px';
    if (el.style.maxHeight !== want) el.style.maxHeight = want;
  });
}

function mk(top, visible) {
  return { offsetParent: visible === false ? null : {}, style: { maxHeight: '' },
           getBoundingClientRect: () => ({ top }) };
}
function run(vh, top, visible, fit) {
  VH = vh; window.innerHeight = vh;
  const el = mk(top, visible); ELS = [el];
  (fit || fitTableWrapsToViewport)();
  return el.style.maxHeight;
}

// D1 - in view: unchanged. 900 - 300 - 24 = 576.
t('D1  table in view -> sized from its own position (576px)', run(900, 300, true), '576px');

// D2 - BELOW THE FOLD. Jason's Amazon P&L: 9 scorecards + a 123-week chart.
t('D2  table below the fold -> viewport minus sticky chrome (776px)', run(900, 1400, true), '776px');

// D3 - REGRESSION GUARD: the old formula pinned that same table at the floor.
t('D3  REGRESSION GUARD: pre-v10.77 pinned the below-fold table at the 280px floor',
  run(900, 1400, true, oldFit), '280px');

// D4 - partially below the fold still cannot be measured usefully.
t('D4  table partly below the fold also falls back (not the 280px floor)',
  [run(900, 800, true), run(900, 800, true, oldFit)], ['776px', '280px']);

// D5 - the floor still holds on a genuinely short viewport.
t('D5  short viewport still clamps to the 280px floor', run(350, 1000, true), '280px');

// D6 - THE EQUIVALENCE PROOF. Wherever v10.56 was already right (the element
// is in view and clears the floor), the new formula must be IDENTICAL - this
// fix must not have moved a single table that was fine.
const drift = [];
for (const vh of [700, 900, 1100, 1440]) {
  for (let top = 0; top <= vh; top += 25) {
    const a = run(vh, top, true);
    const b = run(vh, top, true, oldFit);
    if (parseInt(b, 10) > TBL_FIT_MIN && a !== b) drift.push([vh, top, a, b]);
  }
}
t('D6  EQUIVALENCE: identical to v10.56 wherever v10.56 cleared the floor', drift, []);

// D7 - hidden tab: rect is 0, so it must be skipped entirely.
t('D7  hidden tab is skipped (rect would be 0)', run(900, 0, false), '');

// D8 - the fallback never undercuts the floor by construction.
const under = [];
for (const vh of [300, 400, 600, 900, 1440]) {
  const v = parseInt(run(vh, vh + 500, true), 10);
  if (v < TBL_FIT_MIN) under.push([vh, v]);
}
t('D8  the below-fold fallback never returns less than the floor', under, []);

console.log(JSON.stringify(out));
