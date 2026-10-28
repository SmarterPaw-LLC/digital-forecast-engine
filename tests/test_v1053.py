# -*- coding: utf-8 -*-
r"""v10.53 - one label, one measure across the Chewy tabs. Plus the sweep.

Jason: "i swear to god. why is it not part of your method to make sure you
aren't adding confusing or contradictory measures? in what world would i want
to add so much confusion?"

Because the rule logged in v10.50 covered RENDERERS and ICONS and said nothing
about MEASURES. The Sales (v8.38), Cost to Chewy (v10.11) and Break-Even
(v10.36) tabs were each built without auditing the other two, so four labels
ended up meaning two different things - worst of them "Units", which is
sell-through on two tabs and AD-DRIVEN ONLY on the third.

The durable half is CHEWY_MEASURE_VOCAB: every column and scorecard label on
those tabs has to be declared with what it means. This suite fails when a label
is undeclared, when two labels claim the same meaning without being declared an
abbreviation pair, or when an abbreviation drifts away from its long form.
"""
import io, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)


# index.html stores some glyphs as the LITERAL six characters \uXXXX inside JS
# string literals (the JS parser resolves them at runtime; a raw source read
# does not). Normalise before comparing against the vocabulary.
_ESC = re.compile(r'\\u([0-9a-fA-F]{4})')
def norm(lbl):
    return _ESC.sub(lambda m: chr(int(m.group(1), 16)), lbl).strip()


def fnbody(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), RAW)
    if not m: raise SystemExit('FAIL: cannot slice %s' % name)
    i = RAW.index('{', m.start()); depth = 0
    while True:
        c = RAW[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return RAW[m.start():i + 1]
        i += 1


def parse_obj(const_name):
    """Parse a flat `const X = { 'k': 'v', ... };` literal into a dict."""
    m = re.search(r'const %s\s*=\s*\{' % re.escape(const_name), RAW)
    if not m: return None
    i = RAW.index('{', m.start()); depth = 0
    while True:
        c = RAW[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: body = RAW[m.start():i + 1]; break
        i += 1
    out = {}
    pair = re.compile(r"""^\s*('[^']*'|"[^"]*")\s*:\s*('[^']*'|"[^"]*")\s*,?\s*$""")
    for line in body.split('\n'):
        mm = pair.match(line)
        if mm:
            out[norm(mm.group(1)[1:-1])] = norm(mm.group(2)[1:-1])
    return out


# ============ A. the vocabulary is declared, and says what it is for ============
print('A. static - the vocabulary exists and encodes the standing conventions')

VOCAB = parse_obj('CHEWY_MEASURE_VOCAB')
ALIAS = parse_obj('CHEWY_MEASURE_ALIASES')

ok(VOCAB is not None and len(VOCAB) >= 30,
   'CHEWY_MEASURE_VOCAB declares every Chewy measure in one place',
   None if VOCAB is None else len(VOCAB))
ok(ALIAS is not None and len(ALIAS) >= 5,
   'CHEWY_MEASURE_ALIASES declares the deliberate abbreviation pairs',
   None if ALIAS is None else len(ALIAS))

ok('WHOLESALE basis' in RAW and 'RETAIL basis' in RAW,
   'the wholesale-vs-retail basis convention is stated in the source')
ok('scoped to ad-driven activity only' in RAW,
   '  and so is the "Ad ..." prefix convention')
ok('tests/test_v1053.py' in RAW,
   'the vocabulary names the suite that keeps it honest')


# ============ B. the four ad-scope collisions are renamed ============
print('\nB. static - the four Break-Even labels that meant two things are scoped')

# v10.57 hoisted the Chewy registries to module scope so the column picker
# can read them, so slice the file rather than the render-function body.
be = RAW[RAW.index('const CHEWY_BE_COLUMNS = ['):]
for key, want, gone in [
    ('direct_units',  'Ad Units',          'Units'),
    ('cpu',           'Ad $/unit',         'Cost/unit'),
    ('ourRev',        'Ad Our Rev',        'Our Rev'),
    ('vendorContrib', 'Ad Vendor Contrib', 'Vendor Contrib'),
]:
    m = re.search(r"\bkey:\s*'%s',\s*label:\s*'([^']*)'" % re.escape(key), be)
    ok(m is not None and m.group(1) == want,
       "Break-Even %-14s reads '%s' (was '%s')" % (key, want, gone),
       None if m is None else m.group(1))

# the un-scoped forms must still exist on the Sales tab - that is the whole
# point: same word, different scope, so only ONE of them may wear the bare name
sales = RAW[RAW.index('const CHEWY_SALES_COLUMNS = ['):]
ok(re.search(r"label:\s*'Our Rev'", sales) is not None,
   "Sales keeps the bare 'Our Rev' (all sell-through units)")
ok(re.search(r"label:\s*'Vendor Contrib'", sales) is not None,
   "  and the bare 'Vendor Contrib'")
ok(re.search(r"label:\s*'Units'", sales) is not None,
   "  and the bare 'Units'")


# ============ C. the sweep - every label on every Chewy tab is declared ============
print('\nC. sweep - no Chewy column or scorecard label is undeclared')

# Keys are camelCase on Break-Even (ourRev, beRoas, gmPct) and snake_case on
# the other two tabs, so the character class has to carry both - an
# [a-z_0-9]-only pattern silently skipped 9 of the 18 Break-Even columns and the
# sweep passed against a short haystack.
COL    = re.compile(r"\{[^{}]*?\bk(?:ey)?:\s*'([A-Za-z_0-9]+)'[^{}]*?\blabel:\s*'([^']*)'")
# Break-Even builds its scorecards through card('...'); Sales and Cost to Chewy
# use the { l: '...' } shorthand. Both are scorecard labels.
CARD   = re.compile(r"card\('([^']*)'")
CARD_L = re.compile(r"\bl\s*:\s*'([^']*)'")

# Columns now live in module-scope registries (v10.57); scorecards are still
# built inside the render functions. Sweep both so neither surface can add an
# undeclared label.
# v11.01 - the Program tab joins the sweep. Its columns are at module scope
# for the same reason the other three are: so this rule can reach them.
COL_REGISTRIES = [
    ('Sales',         'CHEWY_SALES_COLUMNS'),
    ('Cost to Chewy', 'CHEWY_COST_COLUMNS'),
    ('Break-Even',    'CHEWY_BE_COLUMNS'),
    ('Program',       'CHEWY_PROGRAM_COLUMNS'),
]
# v11.16 - the Ads tab joins the sweep, which is why this went red when it
# shipped. Its columns do NOT live in a CHEWY_* const: the Ads view is ONE
# renderer serving both P&Ls (hard rule #1), so its registry is the
# per-channel ADS_COLUMNS map. The sweep reaches into that map's `chewy`
# half rather than the code growing a second, parallel registry just to
# satisfy this extractor. The AMAZON half is deliberately out of scope:
# this rule polices the CHEWY page group, and Amazon's labels follow its
# own console's wording.
_adsI = RAW.index('const ADS_COLUMNS = {')
_adsC = RAW.index('chewy: [', _adsI)
ADS_CHEWY_SLICE = RAW[_adsC:RAW.index('\n  ],', _adsC)]
# Guard the guard: a slice that silently came back empty would make every
# Ads label look undeclared-but-unrendered, or pass vacuously (v10.20).
assert ADS_CHEWY_SLICE.count('label:') >= 10, 'Ads chewy slice looks wrong'
TABS = [
    ('Sales',         'renderChewyPnlSales'),
    ('Cost to Chewy', 'renderChewyPnlCost'),
    ('Break-Even',    'renderChewyBreakeven'),
    ('Program',       'renderChewyProgram'),
]

found = {}          # label -> [(tab, kind, key)]
for tab, const in COL_REGISTRIES:
    i = RAW.index('const %s = [' % const)
    j = RAW.index('\n];', i)
    for k, lab in COL.findall(RAW[i:j]):
        found.setdefault(norm(lab), []).append((tab, 'col', k))
for k, lab in COL.findall(ADS_CHEWY_SLICE):
    found.setdefault(norm(lab), []).append(('Ads', 'col', k))
for tab, fname in TABS:
    b = fnbody(fname)
    for lab in CARD.findall(b) + CARD_L.findall(b):
        found.setdefault(norm(lab), []).append((tab, 'card', ''))

# guard the guard: a sweep that finds nothing passes vacuously
ok(len(found) >= 40, 'the extractor actually finds the Chewy labels', len(found))
ok('Ad Units' in found and 'Merch Sales' in found and 'GM $/u' in found,
   '  and finds labels from all three tabs')

undeclared = sorted(l for l in found if VOCAB and l not in VOCAB)
ok(not undeclared,
   'every extracted label is declared in CHEWY_MEASURE_VOCAB',
   undeclared or None)

# and the reverse direction, so the vocabulary cannot rot into a list of
# measures that no longer exist on any tab
orphans = sorted(l for l in (VOCAB or {}) if l not in found)
ok(not orphans,
   'every declared measure is actually rendered somewhere',
   orphans or None)


# ============ D. two labels may not claim the same meaning ============
print('\nD. static - one meaning, one label (abbreviations declared explicitly)')

def undeclared_clashes(vocab, alias):
    by_def = {}
    for lab, d in vocab.items():
        by_def.setdefault(d, []).append(lab)
    out = []
    for d, labs in by_def.items():
        if len(labs) < 2: continue
        labs_s = sorted(labs)
        # allowed only when every label in the group is one half of a declared pair
        declared = all(
            alias.get(l) in labs_s or l in alias.values()
            for l in labs_s
        )
        if not declared: out.append((d, labs_s))
    return out

collisions = undeclared_clashes(VOCAB or {}, ALIAS or {})
ok(not collisions,
   'no two labels share a definition unless declared an abbreviation pair',
   collisions or None)

# every alias pair must exist, and must carry an IDENTICAL definition
bad_alias = []
for long_form, short_form in (ALIAS or {}).items():
    if long_form not in (VOCAB or {}) or short_form not in (VOCAB or {}):
        bad_alias.append((long_form, short_form, 'missing from vocabulary')); continue
    if VOCAB[long_form] != VOCAB[short_form]:
        bad_alias.append((long_form, short_form, 'definitions differ'))

ok(not bad_alias,
   'every abbreviation carries the same definition as its long form',
   bad_alias or None)

# both halves of each pair must really be on screen somewhere, else the pair is
# decoration rather than a live convention
unused_alias = sorted(
    (l, s) for l, s in (ALIAS or {}).items() if l not in found or s not in found
)
ok(not unused_alias,
   '  and both halves of each pair are actually rendered',
   unused_alias or None)


# ============ E. the guard has teeth ============
print('\nE. the guard has teeth')

fake_vocab = dict(VOCAB or {})
fake_vocab.pop('Ad Units', None)
ok(any(l not in fake_vocab for l in found),
   'removing a measure from the vocabulary WOULD be caught by section C')

fake = dict(VOCAB or {})
fake['Headroom'] = fake['Spend']          # two labels, one meaning, undeclared
ok(bool(undeclared_clashes(fake, ALIAS or {})),
   'an undeclared same-meaning pair WOULD be caught by section D')

fake2 = dict(VOCAB or {})
fake2['Total COGS'] = 'something else entirely'
ok(any(fake2[l] != fake2[s] for l, s in (ALIAS or {}).items()
       if l in fake2 and s in fake2),
   'an abbreviation drifting from its long form WOULD be caught by section D')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d): %s' % (F, ', '.join(fails[:8])))
    sys.exit(1)
print('v10.53 - all green (%d static assertions)' % P)
