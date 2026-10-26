
const out = [];
function t(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  out.push({ name, pass: g === w, got: g, want: w });
}

function pnlGrowthMonthWindow(haveList, span) {
  const n = span || 12;
  const toIdx = (m) => {
    const p = String(m || '').split('-');
    const y = parseInt(p[0], 10), mo = parseInt(p[1], 10);
    return (Number.isFinite(y) && Number.isFinite(mo)) ? y * 12 + (mo - 1) : null;
  };
  const toStr = (i) => String(Math.floor(i / 12)) + '-' + String((i % 12) + 1).padStart(2, '0');

  const have = [...new Set((haveList || []).filter(Boolean).map(String))].sort();
  const haveIdx = have.map(toIdx).filter(i => i !== null);

  const now = new Date();
  let end = now.getFullYear() * 12 + now.getMonth() - 1;   // last COMPLETE month
  if (haveIdx.length) end = Math.max(end, Math.max(...haveIdx));
  const start = end - (n - 1);

  const all = [];
  for (let i = start; i <= end; i++) all.push(toStr(i));
  const haveSet = new Set(have);
  return {
    start: toStr(start), end: toStr(end), span: n,
    all,
    have,
    inWindow: all.filter(m => haveSet.has(m)),
    missing: all.filter(m => !haveSet.has(m)),
    // Months older than the window. Not a gap - just not counted toward it.
    older: haveIdx.filter(i => i < start).sort((a, b) => a - b).map(toStr),
  };
}

const now = new Date();
const curIdx = now.getFullYear() * 12 + now.getMonth();
const toStr = (i) => String(Math.floor(i / 12)) + '-' + String((i % 12) + 1).padStart(2, '0');
const lastComplete = toStr(curIdx - 1);
const thisMonth    = toStr(curIdx);

// -- 1. The window ends at LAST COMPLETE month, never the current one.
let w = pnlGrowthMonthWindow([], 12);
t('E1 window ends at last complete month', w.end, lastComplete);
t('E2 the current month is never listed as missing', w.missing.includes(thisMonth), false);
t('E3 an empty history reports all 12 as missing', [w.all.length, w.missing.length], [12, 12]);
t('E4 window start is 11 months before the end', w.start, toStr(curIdx - 12));

// -- 2. Gaps inside the window.
const have = [toStr(curIdx - 1), toStr(curIdx - 2), toStr(curIdx - 5)];
w = pnlGrowthMonthWindow(have, 12);
t('E5 loaded months are not reported missing',
  have.every(m => !w.missing.includes(m)), true);
t('E6 the gaps are exactly the window minus what is loaded',
  w.missing.length, 12 - have.length);
t('E7 inWindow lists only what is both loaded and in range',
  w.inWindow.slice().sort(), have.slice().sort());
t('E8 missing is ordered oldest first, so it reads as a pull list',
  w.missing.slice().sort().join() === w.missing.join(), true);

// -- 3. Months older than the window are separated, not called gaps.
const old1 = toStr(curIdx - 30);
w = pnlGrowthMonthWindow([old1, toStr(curIdx - 1)], 12);
t('E9  an older month is reported separately', w.older, [old1]);
t('E10 ...and is NOT counted as missing', w.missing.includes(old1), false);
t('E11 ...and is NOT counted as in-window', w.inWindow.includes(old1), false);

// -- 4. If somehow NEWER than last-complete exists, extend rather than
//       calling a real upload "extra".
w = pnlGrowthMonthWindow([thisMonth], 12);
t('E12 a month newer than last-complete extends the window', w.end, thisMonth);
t('E13 ...and is counted as loaded, not older', [w.inWindow, w.older], [[thisMonth], []]);

// -- 5. Full coverage.
const full = pnlGrowthMonthWindow([], 12).all;
w = pnlGrowthMonthWindow(full, 12);
t('E14 full coverage reports no gaps', w.missing, []);
t('E15 ...and no spurious older months', w.older, []);

// -- 6. Year boundary + span + junk input.
t('E16 December rolls to January cleanly',
  pnlGrowthMonthWindow(['2025-12', '2026-01'], 12).have, ['2025-12', '2026-01']);
t('E17 span is honoured', pnlGrowthMonthWindow([], 6).all.length, 6);
t('E18 default span is 12', pnlGrowthMonthWindow([]).all.length, 12);
t('E19 duplicates collapse', pnlGrowthMonthWindow([lastComplete, lastComplete]).have, [lastComplete]);
t('E20 junk + blanks are dropped without throwing',
  pnlGrowthMonthWindow([null, '', 'nope', undefined, lastComplete]).inWindow, [lastComplete]);
t('E21 every emitted month is a valid YYYY-MM',
  pnlGrowthMonthWindow([], 12).all.every(m => /^\d{4}-(0[1-9]|1[0-2])$/.test(m)), true);

console.log(JSON.stringify(out));
