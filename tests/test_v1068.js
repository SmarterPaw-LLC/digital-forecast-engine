
function runStrip(input) {
  let sql = String(input).trim();
sql = sql.replace(/;\s*$/g, '').trim();
// v10.68 - strip TRAILING comments too, then re-strip the `;` they were
  // hiding. The .sql files in this repo are written as ONE live section with
  // the alternates parked in block comments underneath, so a whole-file paste
  // ends in a comment and the real `;` sits mid-string, landing inside the
  // wrapper. v4.43 handled the leading-comment mirror of this.
  while (true) {
    const before = sql;
    sql = sql.replace(/\s+$/, '');
    sql = sql.replace(/\/\*[\s\S]*?\*\/\s*$/, '');    // trailing block comment
    sql = sql.replace(/(^|\n)[ \t]*--[^\n]*$/, '$1');  // trailing line comment
    sql = sql.replace(/;\s*$/, '');                    // the `;` it was hiding
    if (sql === before) break;
  }
  sql = sql.trim();
// Strip LEADING -- line comments and /* */ block comments. exec_sql's
  // SECURITY guard checks `upper(left(trimmed, 6))` to confirm the query
  // starts with SELECT or WITH — a preset that begins with `-- explainer`
  // would otherwise be rejected before it ran. Comments inside the body of
  // the query are fine; only the leading ones trip the check.
  while (true) {
    const before = sql;
    sql = sql.replace(/^\s*--[^\n]*\n?/, '');      // leading line comment
    sql = sql.replace(/^\s*\/\*[\s\S]*?\*\/\s*/, ''); // leading block comment
    sql = sql.replace(/^\s+/, '');                  // leading whitespace
    if (sql === before) break;
  }
  const stripped = sql.replace(/--.*$/gm,'').replace(/\/\*[\s\S]*?\*\//g,'').trim().toUpperCase();
  const _noStr = stripped.replace(/'(?:[^']|'')*'/g, "QQ");
  return {
    sql,
    startsOk: stripped.startsWith('SELECT') || stripped.startsWith('WITH'),
    multiStatement: _noStr.includes(';'),
  };
}
const results = {};
const _cases = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
for (const [name, text] of Object.entries(_cases)) {
  try { results[name] = runStrip(text); }
  catch (e) { results[name] = { error: String(e && e.message) }; }
}
console.log(JSON.stringify(results));
