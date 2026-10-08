
function ipVelTrendLabel(t) {
  if (t.isNew) return { txt: '\u2191\u2191 New', cls: 'var(--sp-green)', rank: 3 };
  // v9.93 — distinguish "sales history has not finished loading" from "this
  // product genuinely did not sell". The first is transient and resolves on
  // its own; the second is a real signal. Rendering both as "No data" made a
  // loading race look like a catalog-wide collapse.
  if (t.ready === false && !(t.prev > 0) && !(t.now > 0)) {
    return { txt: '\u23f3 loading\u2026', cls: 'var(--text3)', rank: 0 };
  }
  if (!(t.prev > 0) && !(t.now > 0)) return { txt: '\u2014 No data', cls: 'var(--text3)', rank: 0 };
  const ratio = t.prev > 0 ? t.now / t.prev : 1;
  // v9.99 — Jason: "i need a larger callout and format for high acceleration
  // items — there is a lot of green on here." He was looking at a column where
  // roughly four rows in five read "Accelerating", which is a column that has
  // stopped carrying information. Two causes, both fixed here:
  //   1. Everything above 1.3× collapsed into ONE bucket, so a 1.31× and a
  //      3.8× rendered identically. Split the top off at 2×.
  //   2. The label never showed MAGNITUDE, so the only way to rank the green
  //      was to enable a second column. The render now carries the % inline.
  // `strong` gets a filled chip, `quiet` gets dimmed — so the eye lands on the
  // genuine movers instead of an undifferentiated wall of green.
  if (ratio >= 2)   return { txt: '🔥 Surging',       cls: 'var(--sp-green)',  rank: 4, strong: true };
  if (ratio > 1.3)  return { txt: '\u2191\u2191 Accelerating', cls: 'var(--sp-green)',  rank: 2 };
  if (ratio > 1.08) return { txt: '\u2191 Growing',      cls: 'var(--sp-green2)', rank: 1, quiet: true };
  if (ratio < 0.7)  return { txt: '\u2193\u2193 Declining',   cls: 'var(--sp-red)',    rank: -2 };
  if (ratio < 0.92) return { txt: '\u2193 Slowing',      cls: 'var(--sp-orange)', rank: -1 };
  return { txt: '\u2192 Steady', cls: 'var(--text2)', rank: 0, quiet: true };
}

// Shared hover text — says what both windows actually cover, so a number that
// differs from Vel/day is explainable rather than mysterious.
// v10.1 — the trend cell, lifted out of the Inventory Planning column so the
// Demand Forecast page and the per-channel columns render identically instead
// of accumulating copies that drift (the v10.0 Excel bug was exactly that).
function ipVelTrendFor(r){ return r.__t; }
function velTrendCsv(t) {
  const l = ipVelTrendLabel(t);
  const base = l.txt.replace(/[\u2191\u2193\u2192\u2014\u{1F525}]/gu, '').trim();
  return (t.pct == null || l.rank === 0) ? base
    : `${base} ${t.pct > 0 ? '+' : ''}${Math.round(t.pct)}%`;
}
const _wrapCsv = { csv: r => velTrendCsv(ipVelTrendFor(r)) };
const COL = _wrapCsv;
  const C = {
    headBg:'FF2F3A26', headFg:'FFFFFFFF',
    grpTotal:'FF3E5230', grpBase:'FF2B4257', grpReorder:'FF6B3A17', grpOther:'FF3A3A3A',
    now:'FFFBDAD5', soon:'FFFDEBCF', plan:'FFFEF6D6', ok:'FFDFF2DA',
    short:'FFC0392B', surplus:'FF1E8449', up:'FF1E8449', down:'FFC0392B', mute:'FF888888',
    // v10.0 — the top trend tier gets a FILL, not just a colour, so it survives
    // being scanned in a static sheet. `upSoft` lets Growing recede the way it
    // does on screen instead of competing with Accelerating.
    surgeBg:'FF1E8449', surgeFg:'FFFFFFFF', upSoft:'FF5FA776',
    band:'FFF7F9F4', border:'FFD9DED3',
  };

// The shipped styling branch, wrapped so it can be driven per value.
function styleFor(v) {
  const cell = {};
  const keyOf = () => 'vel_trend';
  const col = null;
        if (keyOf(col) === 'vel_trend' && typeof v === 'string') {
          // v10.0 — Jason: "can we call them out more on the export?"
          //
          // Two things were wrong. The regex below never mentioned Surging, so
          // the v9.99 top tier fell through to C.mute and exported GREY — less
          // prominent than Accelerating, the exact inversion of what it means.
          // And every upward bucket shared one green, so the export had the
          // same undifferentiated-wall problem the screen had before v9.99.
          //
          // Surging now gets a solid fill + white bold, mirroring the on-screen
          // chip; Accelerating keeps the green text; Growing recedes to a
          // softer green so the eye lands on the movers.
          if (/Surging/.test(v)) {
            cell.fill = { type:'pattern', pattern:'solid', fgColor:{ argb: C.surgeBg } };
            cell.font = { size: 10, bold: true, color: { argb: C.surgeFg } };
          } else {
            cell.font = { size: 10, bold: /Accel|Declin|New/.test(v),
              color: { argb: /Accel|New/.test(v) ? C.up
                           : /Growing/.test(v)   ? C.upSoft
                           : /Declin/.test(v)    ? C.down
                           : /Slowing/.test(v)   ? 'FFD68910'
                           : C.mute } };
          }
        }

  return cell;
}

let pass = 0, fail = 0;
function t(name, cond, got) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (got !== undefined ? '  got: ' + JSON.stringify(got) : '')); }
}
const trend = (ratio) => { const prev = 10, now = 10 * ratio;
  return { __t: { now, prev, pct: (ratio - 1) * 100, lags: [], isNew: false, ready: true,
                  rawNow: now, rawPrev: prev, seaNow: 1, seaPrev: 1, w: 30, off: 30, keys: [] } }; };

console.log('\n== A. The exported VALUE carries label + magnitude ==');
for (const [ratio, want] of [[3.8,'Surging +280%'], [2.0,'Surging +100%'], [1.9,'Accelerating +90%'],
                             [1.15,'Growing +15%'], [0.85,'Slowing -15%'], [0.45,'Declining -55%']]) {
  const got = COL.csv(trend(ratio));
  t(`${ratio}x -> "${want}"`, got === want, got);
}
t('Steady carries no magnitude (a 0% delta is noise)', COL.csv(trend(1.0)) === 'Steady', COL.csv(trend(1.0)));
t('no arrows or glyphs survive into the cell',
  !/[\u2191\u2193\u2192\u2014\u{1F525}]/u.test([3.8,1.9,1.15,0.85,0.45,1.0].map(r => COL.csv(trend(r))).join(' ')));

console.log('\n== B. REGRESSION GUARD: Surging used to export GREY ==');
// Pre-v10.0 the branch tested /Accel|Growing|New/ and nothing else, so
// "Surging" fell through to C.mute - dimmer than Accelerating, inverting what
// the tier means.
const oldColor = (v) => /Accel|Growing|New/.test(v) ? C.up : /Declin|Slowing/.test(v) ? C.down : C.mute;
t('the old branch really did colour Surging grey', oldColor('Surging +280%') === C.mute);
t('  ...and it is no longer grey', styleFor('Surging +280%').font.color.argb !== C.mute);

console.log('\n== C. Surging is the only bucket with a FILL ==');
const sur = styleFor('Surging +280%');
t('Surging gets a solid fill', !!sur.fill && sur.fill.pattern === 'solid', sur.fill);
t('  in the surge green', sur.fill.fgColor.argb === C.surgeBg, sur.fill.fgColor);
t('  with white bold text', sur.font.color.argb === C.surgeFg && sur.font.bold === true, sur.font);
for (const v of ['Accelerating +90%', 'Growing +15%', 'Steady', 'Slowing -15%', 'Declining -55%', '\u2014 No data']) {
  t(`no fill on "${v}"`, !styleFor(v).fill, styleFor(v).fill);
}

console.log('\n== D. Everything below it is tiered, not one flat green ==');
t('Accelerating -> up green, bold',
  styleFor('Accelerating +90%').font.color.argb === C.up && styleFor('Accelerating +90%').font.bold === true);
t('Growing -> SOFTER green, not bold (recedes, as on screen)',
  styleFor('Growing +15%').font.color.argb === C.upSoft && styleFor('Growing +15%').font.bold === false);
t('  and upSoft is genuinely a different colour from up', C.upSoft !== C.up, { up: C.up, soft: C.upSoft });
t('Declining -> down red, bold',
  styleFor('Declining -55%').font.color.argb === C.down && styleFor('Declining -55%').font.bold === true);
t('Slowing -> amber, not bold',
  styleFor('Slowing -15%').font.color.argb === 'FFD68910' && styleFor('Slowing -15%').font.bold === false);
t('Steady -> mute', styleFor('Steady').font.color.argb === C.mute);
t('No data -> mute', styleFor('\u2014 No data').font.color.argb === C.mute);
t('New -> up green, bold (a launch is a mover)',
  styleFor('\u2191\u2191 New').font.color.argb === C.up && styleFor('\u2191\u2191 New').font.bold === true);

console.log('\n== E. The % suffix cannot break the matching ==');
t('"Growing +15%" does not match Accel', styleFor('Growing +15%').font.color.argb !== C.up);
t('"Declining -55%" does not match Growing', styleFor('Declining -55%').font.color.argb === C.down);
t('every bucket resolves to a real argb',
  ['Surging +280%','Accelerating +90%','Growing +15%','Steady','Slowing -15%','Declining -55%','\u2014 No data']
    .every(v => { const c = styleFor(v); const a = (c.font && c.font.color && c.font.color.argb) || (c.fill && C.surgeFg);
                  return typeof a === 'string' && /^FF[0-9A-F]{6}$/.test(a); }));

console.log('\n' + (fail ? '\u2717 ' + fail + ' FAILED, ' : '\u2713 ') + pass + ' passed');
process.exit(fail ? 1 : 0);
