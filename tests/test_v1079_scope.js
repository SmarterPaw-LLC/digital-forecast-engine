
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

// The skip path never touches the DOM, which is exactly why it is the one
// worth driving in node.
const document = { getElementById: () => null, body: { appendChild(){} },
                   createElement: () => ({ style:{}, set innerHTML(v){}, addEventListener(){} }) };

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

// C1 - nothing is narrowing the view, so there is no question to ask.
let picked = null, opened = 0;
const origCreate = document.createElement;
document.createElement = (...a) => { opened++; return origCreate(...a); };
const three = [1,2,3];
pnlExportScopeDialog({ title:'x', filtered: three, everything: three,
                       everythingLabel:'All', onPick: r => { picked = r; } });
t('C1  equal counts -> exports immediately, no dialog', [picked, opened], [three, 0]);

// C2 - counts differ, so it must ask rather than guess.
picked = null; opened = 0;
pnlExportScopeDialog({ title:'x', filtered: [1], everything: three,
                       everythingLabel:'All', onPick: r => { picked = r; } });
t('C2  differing counts -> asks, exports nothing yet', [picked, opened > 0], [null, true]);

console.log(JSON.stringify(out));
