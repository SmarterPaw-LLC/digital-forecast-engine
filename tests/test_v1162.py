#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" v11.62 - the landing page opens.

Jason, on the GA4 landing-page table: "give me a click to open link here."

A landing page is a GA4 string and this one goes in an `href`, so most of this
suite is about what does NOT become a link.
"""
import io, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = tempfile.mkdtemp(prefix="v1162_")
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


def nocomment(t):
    t = re.sub(r"(?m)^\s*//.*$", "", t)
    return re.sub(r"/\*[\s\S]*?\*/", "", t)


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
        raise RuntimeError(r.stderr[-2500:])
    return json.loads(r.stdout)


CODE = nocomment(js)
SITE = re.search(r"const SEO_TR_SITE = \{[^}]*\};", js).group(0)

# ===========================================================================
print("\nA. The property and its origin are declared ONCE, together")
# ===========================================================================
eq("A1  SEO_TR_SITE declared once", CODE.count("const SEO_TR_SITE = {"), 1)
ok("property: 'smarterpaw'" in SITE, "A2  carries the GA4 property")
ok("origin: 'https://smarterpaw.com'" in SITE, "A3  and the site it describes")
# /!\ The origin is spelled in exactly one place. A second spelling is how the
# link and the fetch end up describing different sites.
eq("A4  the origin appears nowhere else", js.count("https://smarterpaw.com"), 1)
ok("const PROP = SEO_TR_SITE.property;" in js, "A5  the loader reads it")
ok("const PROP = 'smarterpaw';" not in js, "A6  the hardcoded string is gone")

# ===========================================================================
print("\nB. THE REAL seoTrPageUrl - mostly about what does NOT become a link")
# ===========================================================================
B = run(SITE + "\n" + fn("seoTrPageUrl") + r"""
const T = {};
const t = (name, v) => { T[name] = seoTrPageUrl(v); };
t('root', '/');
t('product', '/products/catnip-and-honeysuckle-bubbles');
t('query', '/collections/all?sort_by=best-selling');
t('space', '/pages/my page');
t('unicode', '/blogs/news/café');
// --- the ones that must NOT link ---
t('notSet', '(not set)');
t('blank', '');
t('nullish', null);
t('relative', 'products/thing');
t('absoluteHttp', 'http://evil.example/x');
t('absoluteHttps', 'https://evil.example/x');
t('protocolRelative', '//evil.example/x');
t('backslash', '/\\evil.example/x');
t('javascriptUri', 'javascript:alert(1)');
t('dataUri', 'data:text/html,<script>1</script>');
t('atTrick', '/@evil.example');
t('crlf', '/foo\nbar');
console.log(JSON.stringify(T));
""")

ORIGIN = "https://smarterpaw.com"
eq("B1  the site root links", B["root"], ORIGIN + "/")
eq("B2  a product path links", B["product"], ORIGIN + "/products/catnip-and-honeysuckle-bubbles")
eq("B3  a query string survives", B["query"], ORIGIN + "/collections/all?sort_by=best-selling")
eq("B4  a space is encoded", B["space"], ORIGIN + "/pages/my%20page")
eq("B5  non-ASCII is encoded", B["unicode"], ORIGIN + "/blogs/news/caf%C3%A9")

for name, why in [
    ("notSet", "GA4's own (not set) bucket"),
    ("blank", "an empty landing page"),
    ("nullish", "a null"),
    ("relative", "a path with no leading slash"),
    ("absoluteHttp", "an absolute http URL"),
    ("absoluteHttps", "an absolute https URL to ANOTHER host"),
    ("protocolRelative", "a protocol-relative //host"),
    ("backslash", "the backslash form of //host"),
    ("javascriptUri", "a javascript: URI"),
    ("dataUri", "a data: URI"),
]:
    eq("B6  NOT a link: %s" % why, B[name], "")

# `/@host` and a CRLF are ordinary paths on our own origin - they link, and
# that is correct; the origin check is what matters, not a blocklist.
ok(B["atTrick"].startswith(ORIGIN + "/"), "B7  /@something stays on our origin", B["atTrick"])
ok(B["crlf"].startswith(ORIGIN + "/"), "B8  a newline is encoded, not injected", B["crlf"])
ok("\n" not in B["crlf"], "B8b ...and no raw newline survives into the URL")

# ===========================================================================
print("\nC. A REAL anchor, and nothing unescaped reaches the markup")
# ===========================================================================
cell = js[js.index("const href = (k === ''"):]
cell = cell[:cell.index("</tr>")]
ok("<a href=" in cell, "C1  a real <a href>, not an onclick")
# /!\ v11.37's rule: a real href means ctrl/cmd-click, middle-click and
# open-in-new-tab work for free. An onclick would break all three.
#
# v11.65 - the ROW around this cell toggles the page onto the chart, so "no
# onclick in this region" stopped being the guarantee. The one that matters is
# asserted directly instead, and more precisely than before: the anchor
# navigates through its HREF and never through script, and its only handler is
# the one that stops the row from also toggling.
anchor = cell[cell.index("<a href="):cell.index("</a>")]
ok(re.search(r'onclick="(?!event\.stopPropagation\(\)")', anchor) is None,
   "C2  the anchor carries no handler but the row-toggle guard", anchor)
ok(re.search(r"\b(location|window\.open|showPage|routeApply)\b", anchor) is None,
   "C2b and it never navigates by script")
ok("event.stopPropagation()" in anchor,
   "C2c the link wins its own click, so one click cannot both open and toggle")
ok('target="_blank"' in cell, "C3  opens in a new tab (the storefront, not this app)")
ok('rel="noopener"' in cell, "C4  with rel=noopener")
# v11.65 - the row's markup READS `k` several times to choose a tint, a
# checked attribute and a data flag, and each time it emits a LITERAL rather
# than the value. So the question is not whether an interpolation mentions an
# untrusted name - it is what the interpolation EMITS. A conditional's test may
# read k freely; its branches are what reach the markup.
#
# (An allowlist of the exact expressions was the first cut, and it missed one
# of the three on the first run - a guard that goes stale is a guard that will.)
_risky = []
for _x in re.findall(r"\$\{([^}]*)\}", cell):
    _x = _x.strip()
    if _x.startswith("esc2("):
        continue
    _emits = _x.split("?", 1)[1] if "?" in _x else _x
    if re.search(r"\b(href|label|k)\b", _emits):
        _risky.append(_x)
ok(not _risky, "C5  every interpolated VALUE goes through esc2", _risky)

# ...and the guard is not vacuous: an unescaped `${label}` has to fail it.
_probe = []
for _x in ["esc2(label)", "pOn(k) ? ' checked' : ''", "label", "href ? a : k"]:
    _emits = _x.split("?", 1)[1] if "?" in _x else _x
    if not _x.startswith("esc2(") and re.search(r"\b(href|label|k)\b", _emits):
        _probe.append(_x)
eq("C5b the same rule REJECTS an unescaped value", _probe, ["label", "href ? a : k"])
ok("(not set)" in cell and "k === ''" in cell,
   "C6  the two non-page buckets are excluded before a URL is even built")

D = run(SITE + "\n" + fn("seoTrPageUrl") + r"""
// The app's own escaper, so this is the real pairing.
""" + fn("esc2") + r"""
const render = (k) => {
  const label = k === '' ? '(blank)' : k;
  const href = (k === '' || k === '(not set)') ? '' : seoTrPageUrl(k);
  return href
    ? `<a href="${esc2(href)}" target="_blank" rel="noopener" style="color:var(--blue);text-decoration:none" title="${esc2(href)}">${esc2(label)}</a>`
    : `<span title="${esc2(label)}">${esc2(label)}</span>`;
};
const NASTY = `/products/" onmouseover="alert(1)" x="`;
const TAGGY = `/products/<img src=x onerror=alert(1)>`;
console.log(JSON.stringify({
  nasty: render(NASTY),
  taggy: render(TAGGY),
  notSet: render('(not set)'),
  blank: render(''),
  plain: render('/pages/meowijuana')
}));
""")
ok('onmouseover="alert' not in D["nasty"], "C7  a quote-breaking path cannot escape the attribute")
ok(D["nasty"].count('<a ') == 1 and D["nasty"].count('"') % 2 == 0,
   "C8  ...and the anchor stays one well-formed tag")
ok("<img" not in D["taggy"], "C9  a tag in the path renders as text, not markup")
ok("<a " not in D["notSet"], "C10 (not set) renders as plain text")
ok("<a " not in D["blank"], "C11 a blank renders as plain text")
ok('href="https://smarterpaw.com/pages/meowijuana"' in D["plain"],
   "C12 an ordinary page renders the link", D["plain"])

# ===========================================================================
print("\nD. The rest of the table is untouched")
# ===========================================================================
pg = js[js.index("function seoTrRenderPages("):]
pg = pg[:pg.index("\n}")]
ok("a ranking, not a total" in pg, "D1  the ranking caution survives")
ok("have no landing page on record" in pg, "D2  the (not set) count line survives")
# /! `<th` also matches `<thead>` - the v11.57 mistake, made again.
# v11.65 - the selection checkbox is the seventh. Census going red on a column
# change is the test doing its job.
eq("D3  seven columns, the leading checkbox included",
   len(re.findall(r"<th[ >]", pg)), 7)
ok('colspan="7"' in pg, "D4  the empty state spans them")

p = os.path.join(SP, "app.js")
io.open(p, "w", encoding="utf-8", newline="").write(js)
r = subprocess.run(["node", "--check", p], capture_output=True, text=True, encoding="utf-8")
eq("D5  node --check clean", r.returncode, 0)

print("\n%s  %d passed, %d failed" % ("PASS" if not failed else "FAIL", passed, failed))
sys.exit(1 if failed else 0)
