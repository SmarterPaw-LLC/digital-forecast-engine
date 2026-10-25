
'use strict';
const out = [];
const t = (name, got, want) => out.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });

// The skip path never touches the DOM, which is exactly why it is the one
// worth driving in node.
const document = { getElementById: () => null, body: { appendChild(){} },
                   createElement: () => ({ style:{}, set innerHTML(v){}, addEventListener(){} }) };

const EXPORT_DLG_OVERLAY_CSS = 'position:fixed;inset:0;z-index:10600;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center';
const EXPORT_DLG_TONES = {
  selected: 'background:rgba(74,158,56,.18);border:1px solid rgba(74,158,56,.45);color:var(--green)',
  primary:  'background:rgba(74,158,56,.12);border:1px solid rgba(74,158,56,.3);color:var(--green)',
  neutral:  'background:rgba(255,255,255,.05);border:1px solid var(--border2);color:var(--text)',
  cancel:   'background:transparent;border:1px solid var(--border2);color:var(--text3)',
};
function exportDlgActionHtml({ id, pick, icon = '\u2193', label, note, tone = 'neutral' }) {
  const isCancel = tone === 'cancel';
  return `<button${id ? ` id="${id}"` : ''}${pick ? ` data-pick="${pick}"` : ''} style="${EXPORT_DLG_TONES[tone] || EXPORT_DLG_TONES.neutral};border-radius:7px;padding:${isCancel ? '8px 16px' : '10px 16px'};font-family:var(--display);font-weight:700;font-size:${isCancel ? '12px' : '13px'};cursor:pointer;text-align:left">
          ${icon} ${label}${note ? ` <span style="font-weight:400;font-size:11px;color:var(--text3)">${note}</span>` : ''}
        </button>`;
}
function exportDlgSectionHtml(title, inner) {
  return `<div style="background:var(--surface2);border:1px solid var(--border);border-radius:7px;padding:10px 14px;margin-bottom:14px">
        <div style="font-family:var(--mono);font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">${title}</div>
        ${inner}
      </div>`;
}
function exportDlgShellHtml({ title = '\u2193 Export CSV', subtitle = '', sections = '', actions = '' }) {
  return `<div style="background:var(--surface);border:1px solid var(--border2);border-radius:12px;padding:24px 28px;max-width:420px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.5)">
      <div style="font-family:var(--display);font-weight:800;font-size:15px;color:var(--text);margin-bottom:6px">${title}</div>
      <div style="font-size:12px;color:var(--text3);margin-bottom:18px">${subtitle}</div>
      ${sections}
      <div style="display:flex;flex-direction:column;gap:8px">${actions}</div>
    </div>`;
}
function colScopeFieldsetHtml(visibleColCount, totalColCount) {
  return exportDlgSectionHtml('Columns', `<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;color:var(--text);padding:3px 0">
          <input type="radio" name="exp-cols" value="visible" checked style="cursor:pointer">
          Visible columns <span style="color:var(--text3);font-size:11px">(${visibleColCount} — match what's in the table)</span>
        </label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;color:var(--text);padding:3px 0">
          <input type="radio" name="exp-cols" value="all" style="cursor:pointer">
          All columns <span style="color:var(--text3);font-size:11px">(${totalColCount} — every column in the registry)</span>
        </label>`);
}
function readColScope(root) {
  return (root || document).querySelector('input[name="exp-cols"]:checked')?.value || 'visible';
}
function pnlExportScopeDialog({ title, filtered, everything, everythingLabel, everythingSub, filteredLabel, cols, onPick }) {
  // v10.81 - `cols` is { visible, all }. Columns are the other half of "what
  // am I exporting", and leaving them out is why this got asked for 3 times.
  const sameRows = filtered.length === everything.length;
  const hasCols  = !!(cols && cols.all > cols.visible);
  // Neither axis has a choice in it, so there is no question to ask.
  if (sameRows && !hasCols) { onPick(filtered, 'visible'); return; }

  document.getElementById('pnlExportDlg')?.remove();
  const ov = document.createElement('div');
  ov.id = 'pnlExportDlg';
  ov.style.cssText = EXPORT_DLG_OVERLAY_CSS;
  // v10.83 - rendered through the SHARED shell, so this IS the same dialog
  // as the Inventory / Forecast one rather than a lookalike. Three things
  // v10.81 got wrong by hand-rolling the markup around a shared fieldset:
  //   * a bare uppercase "Rows" header outside any box - the canonical
  //     dialog has no row header at all, because the row choice IS the
  //     action buttons;
  //   * a solid-green-filled primary button with white text, where the
  //     canonical one is OUTLINED green on a 12%-alpha tint;
  //   * the row count on a sub-line, where the canonical one puts it inline
  //     in a muted span.
  ov.innerHTML = exportDlgShellHtml({
    subtitle: title,
    sections: hasCols ? colScopeFieldsetHtml(cols.visible, cols.all) : '',
    actions:
      (sameRows
        ? exportDlgActionHtml({ pick: 'filtered', label: 'Export',
            note: `(${filtered.length.toLocaleString()} rows)`, tone: 'primary' })
        : exportDlgActionHtml({ pick: 'filtered', label: filteredLabel || 'Filtered results',
            note: `(${filtered.length.toLocaleString()} rows)`, tone: 'primary' })
          + exportDlgActionHtml({ pick: 'everything', label: everythingLabel,
            note: `(${everything.length.toLocaleString()} rows${everythingSub ? ' · ' + everythingSub : ''})`, tone: 'neutral' }))
      + exportDlgActionHtml({ pick: 'cancel', icon: '✕', label: 'Cancel', tone: 'cancel' }),
  });
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
