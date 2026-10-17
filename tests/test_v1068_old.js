
function oldStrip(input) {
  let sql = String(input).trim();
  sql = sql.replace(/;\s*$/g, '').trim();
  while (true) {
    const before = sql;
    sql = sql.replace(/^\s*--[^\n]*\n?/, '');
    sql = sql.replace(/^\s*\/\*[\s\S]*?\*\/\s*/, '');
    sql = sql.replace(/^\s+/, '');
    if (sql === before) break;
  }
  const stripped = sql.replace(/--.*$/gm,'').replace(/\/\*[\s\S]*?\*\//g,'').trim().toUpperCase();
  return { sql, hadSemi: stripped.includes(';') };
}
const out = {};
const _gc = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
for (const [k, v] of Object.entries(_gc)) out[k] = oldStrip(v);
console.log(JSON.stringify(out));
