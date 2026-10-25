
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

// STATE.pick simulates which radio the operator left selected. null exercises
// the `|| 'visible'` fallback (no radios rendered at all).
const STATE = { pick: null, html: '', removed: 0 };

function mkOv() {
  return {
    id: '', style: {}, dataset: {},
    set innerHTML(v) { STATE.html = v; },
    get innerHTML() { return STATE.html; },
    addEventListener(_, h) { this._h = h; },
    remove() { STATE.removed++; },
    querySelector(sel) {
      if (sel.includes('exp-cols') && STATE.pick) return { value: STATE.pick };
      return null;
    },
  };
}
let LAST = null;
const document = {
  getElementById: () => null,
  body: { appendChild(){} },
  createElement: () => (LAST = mkOv()),
};

function colScopeFieldsetHtml(visibleColCount, totalColCount) {
  return `<div style="background:var(--surface2);border:1px solid var(--border);border-radius:7px;padding:10px 14px;margin-bottom:14px">
        <div style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Columns</div>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;color:var(--text);padding:3px 0">
          <input type="radio" name="exp-cols" value="visible" checked style="cursor:pointer">
          Visible columns <span style="color:var(--text3);font-size:11px">(${visibleColCount} — match what's in the table)</span>
        </label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;color:var(--text);padding:3px 0">
          <input type="radio" name="exp-cols" value="all" style="cursor:pointer">
          All columns <span style="color:var(--text3);font-size:11px">(${totalColCount} — every column in the registry)</span>
        </label>
      </div>`;
}
function readColScope(root) {
  return (root || document).querySelector('input[name="exp-cols"]:checked')?.value || 'visible';
}
function pnlExportScopeDialog({ title, filtered, everything, everythingLabel, everythingSub, cols, onPick }) {
  // v10.81 - `cols` is { visible, all }. Columns are the other half of "what
  // am I exporting", and leaving them out is why this got asked for 3 times.
  const sameRows = filtered.length === everything.length;
  const hasCols  = !!(cols && cols.all > cols.visible);
  // Neither axis has a choice in it, so there is no question to ask.
  if (sameRows && !hasCols) { onPick(filtered, 'visible'); return; }

  document.getElementById('pnlExportDlg')?.remove();
  const ov = document.createElement('div');
  ov.id = 'pnlExportDlg';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:10600;display:flex;align-items:center;justify-content:center';
  const btn = (bg, label, sub) =>
    `<button data-pick="${bg}" style="display:block;width:100%;text-align:left;padding:11px 14px;margin-bottom:8px;border:1px solid var(--border2);border-radius:7px;cursor:pointer;
      background:${bg === 'filtered' ? 'var(--sp-green)' : 'var(--surface2)'};color:${bg === 'filtered' ? '#fff' : 'var(--text)'};font-family:var(--display);font-size:13px;font-weight:700">
      ${label}<div style="font-family:var(--mono);font-size:10px;font-weight:400;opacity:.8;margin-top:2px">${sub}</div></button>`;
  const secHdr = t => `<div style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin:2px 0 6px">${t}</div>`;
  ov.innerHTML = `<div style="background:var(--surface);border:1px solid var(--border2);border-radius:10px;padding:18px;width:420px;max-width:92vw">
      <div style="font-family:var(--display);font-weight:800;font-size:15px;margin-bottom:4px">↓ Export CSV</div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--text3);margin-bottom:14px">${title}</div>
      ${hasCols ? colScopeFieldsetHtml(cols.visible, cols.all) : ''}
      ${sameRows ? '' : secHdr('Rows')}
      ${sameRows
        ? btn('filtered', 'Export', `${filtered.length} rows`)
        : btn('filtered', 'Filtered results', `${filtered.length} rows · on screen now`)
          + btn('everything', everythingLabel, `${everything.length} rows${everythingSub ? ' · ' + everythingSub : ''}`)}
      <button data-pick="cancel" style="width:100%;padding:8px;border:none;border-radius:6px;cursor:pointer;background:transparent;color:var(--text3);font-family:var(--mono);font-size:11px">Cancel</button>
    </div>`;
  ov.addEventListener('click', e => {
    const pick = e.target.closest('[data-pick]')?.dataset.pick;
    if (!pick && e.target !== ov) return;
    const colScope = readColScope(ov);   // read BEFORE the node is destroyed
    ov.remove();
    if (pick === 'filtered') onPick(filtered, colScope);
    else if (pick === 'everything') onPick(everything, colScope);
  });
  document.body.appendChild(ov);
}

const three = [1,2,3];
const call = (opts) => {
  STATE.html = ''; STATE.removed = 0; LAST = null;
  let got = null;
  pnlExportScopeDialog(Object.assign({
    title: 'x', filtered: three, everything: three, everythingLabel: 'All',
    onPick: (rows, scope) => { got = { n: rows.length, scope }; },
  }, opts));
  return got;
};

// N1 - neither axis has a choice, so it must not ask. This is the only path
// that can legitimately skip the dialog.
t('N1  no column choice + same rows -> exports immediately as visible',
  call({ cols: { visible: 39, all: 39 } }), { n: 3, scope: 'visible' });

// N2 - the rows are identical but the COLUMNS are not. Pre-v10.81 this
// skipped the dialog and exported all 39. It must ask now.
let got = call({ cols: { visible: 8, all: 39 } });
t('N2  column choice + same rows -> asks instead of guessing', [got, STATE.html.length > 0], [null, true]);
t('N3  the Columns fieldset is rendered', STATE.html.includes('exp-cols'), true);
t('N4  visible is pre-checked, so the default honours the screen',
  /value="visible" checked/.test(STATE.html), true);
t('N5  both counts are shown so the choice is legible',
  [STATE.html.includes('8'), STATE.html.includes('39')], [true, true]);

// N6 - identical row sets must not render a 2-option Rows section.
t('N6  same rows -> one row button, no Rows header',
  [(STATE.html.match(/data-pick="/g) || []).length, STATE.html.includes('>Rows<')],
  [2, false]);   // filtered + cancel

// N7 - differing rows DO get the labelled two-option Rows section.
call({ filtered: [1], cols: { visible: 8, all: 39 } });
t('N7  differing rows -> two row buttons + a Rows header',
  [(STATE.html.match(/data-pick="/g) || []).length, STATE.html.includes('>Rows<')],
  [3, true]);   // filtered + everything + cancel

// N8/N9 - the chosen scope must actually reach onPick. This is the assertion
// the whole version exists for.
const click = (pick) => {
  const h = LAST._h;
  h({ target: { closest: () => ({ dataset: { pick } }) } });
};
STATE.pick = 'visible';
let seen = null;
STATE.html = ''; LAST = null;
pnlExportScopeDialog({ title:'x', filtered:[1], everything:three, everythingLabel:'All',
  cols: { visible: 8, all: 39 }, onPick: (r, sc) => { seen = { n: r.length, scope: sc }; } });
click('filtered');
t('N8  picking the visible radio returns scope=visible', seen, { n: 1, scope: 'visible' });

STATE.pick = 'all';
seen = null; STATE.html = ''; LAST = null;
pnlExportScopeDialog({ title:'x', filtered:[1], everything:three, everythingLabel:'All',
  cols: { visible: 8, all: 39 }, onPick: (r, sc) => { seen = { n: r.length, scope: sc }; } });
click('everything');
t('N9  picking all columns + all rows returns both choices',
  seen, { n: 3, scope: 'all' });

// N10 - the scope is read BEFORE ov.remove(), or it would always fall back.
STATE.pick = 'all';
seen = null; STATE.html = ''; LAST = null;
pnlExportScopeDialog({ title:'x', filtered:[1], everything:three, everythingLabel:'All',
  cols: { visible: 8, all: 39 }, onPick: (r, sc) => { seen = { n: r.length, scope: sc }; } });
click('filtered');
t('N10 scope survives the node teardown (read before remove)',
  seen && seen.scope, 'all');

console.log(JSON.stringify(out));
