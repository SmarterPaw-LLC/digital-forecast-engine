#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" v11.59 - `vs Break-Even`, a judged ROAS on the Walmart ads tables.

Jason: "I need a break-even roas dimension."

v11.52 derived the Walmart break-even and only ever used it to colour the ROAS
text red. This puts the gap itself on the table as a sortable number.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1159_")
s = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8", newline="").read()
js = max(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", s), key=len)

passed = failed = 0


def ok(cond, label, extra=None):
    global passed, failed
    if cond:
        passed += 1; print("  ok    %s" % label)
    else:
        failed += 1
        print("  FAIL  %s%s" % (label, ("  got: %s" % ascii(extra)) if extra is not None else ""))


def eq(label, got, want):
    ok(got == want, label, None if got == want else "%s want %s" % (ascii(got), ascii(want)))


def fn(name):
    i = js.index("function " + name + "(")
    if js[i - 6:i] == "async ":
        i -= 6
    d, started, k = 0, False, js.index("{", js.index("function " + name + "("))
    while k < len(js):
        c = js[k]
        if c == "{":
            d += 1; started = True
        elif c == "}":
            d -= 1
            if started and d == 0:
                return js[i:k + 1]
        k += 1
    raise RuntimeError("unbalanced " + name)


def run(body):
    p = os.path.join(SP, "h.js")
    io.open(p, "w", encoding="utf-8", newline="").write(body)
    r = subprocess.run(["node", p], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])
    return json.loads(r.stdout)


CORE = "\n".join([
    "let _adsBreakEven = {};",
    fn("adsRoasFloor"),
    fn("adsRoasFloorKnown"),
    fn("adsStampBreakEven"),
    fn("adsFmtNum"),
    fn("adsColFmt"),
])

# ===========================================================================
print("\nA. The column exists on BOTH Walmart tables and nowhere else")
# ===========================================================================
# v12.03 - RE-POINTED from 2 to 3. The guarantee is that this column is on
# EVERY Walmart ads table and nowhere else, with all four of its fields
# coming from the one declaration - not that there are two tables. The
# Advertiser daily view is the third, and it carries break-even for the
# same reason the other two do: it reports ROAS.
# v12.07 - TWO. The Advertiser daily and monthly Campaigns feeds are
# retired; what is left is the channel's own registry (campaign x day)
# and Keywords. The guarantee is unchanged: this column is on EVERY
# Walmart ads table and nowhere else.
WM_ADS_TABLES = 2
eq("A1  declared on every Walmart ads table", s.count("k: 'roasVsBe'"), WM_ADS_TABLES)
eq("A2  all of them read the shared tip", s.count("tip: WM_ADS_TIP.roasVsBe"), WM_ADS_TABLES)
eq("A3  label is the app's existing words", s.count("label: 'vs Break-Even'"), WM_ADS_TABLES)
eq("A4  signed-multiple format", s.count("fmt: 'xs'"), WM_ADS_TABLES)

for chan in ["amazon", "chewy"]:
    i = s.index("  %s: [" % chan, s.index("const ADS_COLUMNS = {"))
    blk = s[i:s.index("\n  ],", i)]
    ok("roasVsBe" not in blk, "A5  absent from the %s registry" % chan)

# /!\ Scoped to Walmart at Jason's instruction. Chewy is ALSO 1P and its 1.0
# floor is wrong - recorded in CLAUDE.md, deliberately not widened into here.
ok("CHEWY IS 1P WHOLESALE" in io.open(os.path.join(ROOT, "CLAUDE.md"),
                                     encoding="utf-8", newline="").read(),
   "A6  the Chewy defect is written down rather than silently fixed")

# ===========================================================================
print("\nB. The REAL adsStampBreakEven, driven")
# ===========================================================================
B = run(CORE + """
const out = {};
const KKZ = { roas: 3.2102, sharePct: 52.6, gmPct: 59.2 };
_adsBreakEven.walmart = { overall: { roas: 2.80, sharePct: 57.2, gmPct: 62.4 },
                          byBrand: { 'Kitty Ka-Zoom': KKZ } };

// A brand with its own break-even uses it, not the blend.
let rows = [{ roas: 2.50 }, { roas: 4.00 }, { roas: null }];
adsStampBreakEven(rows, 'walmart', 'Kitty Ka-Zoom');
out.kkz = rows.map(r => ({ be: r.beRoas, gap: r.roasVsBe == null ? null : +r.roasVsBe.toFixed(4) }));

// No brand filter -> the blend.
rows = [{ roas: 2.50 }];
adsStampBreakEven(rows, 'walmart', '');
out.blended = { be: rows[0].beRoas, gap: +rows[0].roasVsBe.toFixed(4) };

// An UNKNOWN brand falls back to the blend rather than to 1.0.
rows = [{ roas: 2.50 }];
adsStampBreakEven(rows, 'walmart', 'Nope Brand');
out.unknownBrand = { be: rows[0].beRoas, gap: +rows[0].roasVsBe.toFixed(4) };

// /!\\ A DERIVATION THAT FAILED MUST NOT REPORT A GAP. v11.52 fails to 1.0 on
// purpose; a column that read that as a real line would print a confident
// -1.50x against a break-even nobody computed.
_adsBreakEven.walmart = { overall: null };
rows = [{ roas: 2.50 }];
adsStampBreakEven(rows, 'walmart', '');
out.failed = { be: rows[0].beRoas, gap: rows[0].roasVsBe, floorStillOne: adsRoasFloor('walmart','') };

// Still loading: likewise blank, not zero.
_adsBreakEven.walmart = { pending: true };
rows = [{ roas: 2.50 }];
adsStampBreakEven(rows, 'walmart', '');
out.pending = { be: rows[0].beRoas, gap: rows[0].roasVsBe };

// Amazon keeps its 1.0 floor and therefore reports no gap at all.
_adsBreakEven.amazon = { overall: null };
rows = [{ roas: 2.50 }];
adsStampBreakEven(rows, 'amazon', '');
out.amazon = { be: rows[0].beRoas, gap: rows[0].roasVsBe };

// Empty / junk input does not throw.
adsStampBreakEven(null, 'walmart', '');
adsStampBreakEven([null, undefined], 'walmart', '');
out.survivedJunk = true;
console.log(JSON.stringify(out));
""")

eq("B1  KKZ 2.50 ROAS against a 3.21 break-even", B["kkz"][0], {"be": 3.2102, "gap": -0.7102})
eq("B2  KKZ 4.00 clears it", B["kkz"][1], {"be": 3.2102, "gap": 0.7898})
eq("B3  a row with no ROAS has no gap", B["kkz"][2], {"be": 3.2102, "gap": None})
eq("B4  no brand filter uses the BLEND", B["blended"], {"be": 2.80, "gap": -0.30})
eq("B5  an unknown brand falls back to the blend, not to 1.0", B["unknownBrand"],
   {"be": 2.80, "gap": -0.30})
eq("B6  a FAILED derivation reports no gap", B["failed"]["gap"], None)
eq("B6b ...and no break-even either", B["failed"]["be"], None)
eq("B6c ...while the colour floor still falls back to 1.0", B["failed"]["floorStillOne"], 1)
eq("B7  pending reports no gap", B["pending"], {"be": None, "gap": None})
eq("B8  Amazon reports no gap (its floor is a real 1.0, not a derivation)",
   B["amazon"], {"be": None, "gap": None})
ok(B["survivedJunk"], "B9  null / holey input does not throw")

# ===========================================================================
print("\nC. The REAL adsFmtNum, and the sign that is the whole message")
# ===========================================================================
C = run(CORE + """
console.log(JSON.stringify({
  neg: adsFmtNum(-0.7102, 'xs'),
  pos: adsFmtNum(0.7898, 'xs'),
  zero: adsFmtNum(0, 'xs'),
  plainX: adsFmtNum(2.5, 'x'),
  dollars: adsFmtNum(1234.5, '$'),
  pct: adsFmtNum(40.12, '%'),
  fmtOfCol: adsColFmt({ k: 'roasVsBe', fmt: 'xs' }),
  fmtOfRoas: adsColFmt({ k: 'roas' })
}));
""")
eq("C1  a shortfall renders with a real minus sign", C["neg"], "−0.71x")
eq("C2  clearing it renders with a plus", C["pos"], "+0.79x")
eq("C3  exactly break-even is +0.00x, not blank", C["zero"], "+0.00x")
# /!\ Every pre-v11.59 format is byte-identical - the only way "no other column
# moved" is checkable rather than read off a diff.
eq("C4  plain 'x' untouched", C["plainX"], "2.50x")
eq("C5  '$' untouched", C["dollars"], "$1,235")
eq("C6  '%' untouched", C["pct"], "40.1%")
eq("C7  the registry resolves 'xs'", C["fmtOfCol"], "xs")
eq("C8  and 'roas' still resolves to 'x'", C["fmtOfRoas"], "x")

# ===========================================================================
print("\nD. Red below ZERO, because a gap column IS the comparison")
# ===========================================================================
warn = s[s.index("const warn = (F === 'xs'"):]
warn = warn[:warn.index(";")]
ok("F === 'xs' && v < 0" in warn, "D1  the gap column reddens below zero")
ok("adsRoasFloor(channel, adsBrandFilterValue(ch))" in warn,
   "D2  the plain ROAS column still reddens below the BREAK-EVEN")
ok("col.k === 'acos'" in warn, "D3  the ACOS rule is untouched")
# The stamp resolves the SAME brand expression the colour does, so the number
# and the colour cannot disagree.
eq("D4  the stamp uses the colour's own brand expression",
   s.count("adsStampBreakEven(res.campaigns, channel, adsBrandFilterValue(ch))"), 1)
eq("D5  the TOTAL row is stamped too",
   s.count("adsStampBreakEven([res.totals], channel, adsBrandFilterValue(ch))"), 1)

# ===========================================================================
print("\nE. The CSV reads the COLUMN REGISTRY, which fixes a real defect")
# ===========================================================================
# /!\ The old formatter listed decimal columns by KEY and omniRoas was not on
# it, so Walmart's Omni ROAS exported as a rounded integer - 2.08x as "2".
ok("const val = (c, k) =>" not in s, "E1  the hardcoded key list is gone")
ok("const val = (c, col) =>" in s, "E2  the formatter takes the COLUMN")
ok("const F = adsColFmt(col);" in s, "E3  ...and asks the same resolver the table does")
ok(re.search(r"val\(c, col\.k\)", s) is None, "E4  no call site passes a bare key")

E = run(CORE + """
const f2 = v => v == null ? '' : Number(v).toFixed(2);
const i0 = v => v == null ? '' : String(Math.round(Number(v)));
const val = (c, col) => {
  const k = col.k, v = c[k];
  if (typeof v === 'string') return v;
  if (v == null) return '';
  const F = adsColFmt(col);
  return (F === '$' || F === '$2' || F === '%' || F === 'x' || F === 'xs') ? f2(v) : i0(v);
};
const row = { campaign: 'Brand Defense', omniRoas: 2.0812, roasVsBe: -0.7102,
              roas: 2.5, impressions: 41233.6, spend: 1234.567, acos: 40.1234, units: null };
console.log(JSON.stringify({
  omni:  val(row, { k: 'omniRoas', fmt: 'x' }),
  gap:   val(row, { k: 'roasVsBe', fmt: 'xs' }),
  roas:  val(row, { k: 'roas' }),
  imps:  val(row, { k: 'impressions' }),
  spend: val(row, { k: 'spend' }),
  acos:  val(row, { k: 'acos' }),
  text:  val(row, { k: 'campaign' }),
  empty: val(row, { k: 'units' }),
  omniUnderOldRule: i0(row.omniRoas)
}));
""")
eq("E5  Omni ROAS exports with its decimals", E["omni"], "2.08")
eq("E5b ...where the OLD rule wrote this", E["omniUnderOldRule"], "2")
eq("E6  the gap exports signed, two decimals", E["gap"], "-0.71")
eq("E7  roas unchanged", E["roas"], "2.50")
eq("E8  a count is still rounded", E["imps"], "41234")
eq("E9  dollars unchanged", E["spend"], "1234.57")
eq("E10 acos unchanged", E["acos"], "40.12")
eq("E11 text is still text", E["text"], "Brand Defense")
eq("E12 a null is still blank", E["empty"], "")

# ===========================================================================
print("\nF. The file still parses")
# ===========================================================================
p = os.path.join(SP, "app.js")
io.open(p, "w", encoding="utf-8", newline="").write(js)
r = subprocess.run(["node", "--check", p], capture_output=True, text=True, encoding="utf-8")
eq("F1  node --check clean", r.returncode, 0)

print("\n%s  %d passed, %d failed" % ("PASS" if not failed else "FAIL", passed, failed))
sys.exit(1 if failed else 0)
