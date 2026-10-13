# -*- coding: utf-8 -*-
r"""v10.51 — the Chewy allowance category lists must be EXHAUSTIVE.

Found while answering "MDF/Coop is 16%, where does this go into P&L?".

chewyDeriveCategory can emit eleven categories. CHEWY_STANDING_CATS listed six
and CHEWY_PROMO_CATS three, so 'satisfaction_guarantee' was in neither and a 2%
charge that comes off every Chewy invoice contributed 0% to the allowance floor
and appeared in no total anywhere.

The proof is arithmetic, not opinion: Jason's invoice REB00224894 carries
MDF 16% + Damages 2% + Freight 1.5% + Satisfaction 2%, with Auto Ship 5% on
REB00206944, and the page displayed 24.50%. 16 + 2 + 1.5 + 5 = 24.50 exactly.

So the assertion that matters is not "satisfaction is in the list" (easy to
re-break by adding a twelfth category). It is that the classifier's OWN return
values are all accounted for.
"""
import io, os, re, subprocess, sys, tempfile

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
RAW = io.open(SRC, encoding='utf-8', newline='').read()
js  = max(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', RAW, re.S), key=len)

P = F = 0
fails = []

def ok(cond, label, got=None):
    global P, F
    if cond: P += 1; print('  ok  ' + label)
    else:
        F += 1; print('  FAIL ' + label + ('' if got is None else ('  got: ' + repr(got))))
        fails.append(label)

def fn(name):
    m = re.search(r'\n(?:async )?function %s\s*\(' % re.escape(name), js)
    if not m: raise SystemExit('FAIL: cannot slice %s' % name)
    a = m.start() + 1
    i = js.index('{', a); depth = 0
    while True:
        c = js[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return js[a:i + 1]
        i += 1

def arr(name):
    """Read a const array literal that may span lines."""
    a = js.index('const %s ' % name)
    b = js.index('];', a)
    return re.findall(r"'([a-z_]+)'", js[a:b])


# ══════════════ A. the lists are exhaustive over the classifier ══════════════
print('A. static — every category the classifier emits is accounted for')

derive = fn('chewyDeriveCategory')
emitted = sorted(set(re.findall(r"return '([a-z_]+)'", derive)))
print('     classifier emits: %s' % ', '.join(emitted))
ok(len(emitted) >= 10, 'the classifier emits a double-digit category set', len(emitted))

standing = arr('CHEWY_STANDING_CATS')
promo    = arr('CHEWY_PROMO_CATS')
excluded = arr('CHEWY_EXCLUDED_CATS')
print('     standing: %s' % ', '.join(standing))
print('     promo:    %s' % ', '.join(promo))
print('     excluded: %s' % ', '.join(excluded))

accounted = set(standing) | set(promo) | set(excluded)
orphans = [c for c in emitted if c not in accounted]
ok(not orphans,
   '\u26a0 NO category the classifier emits is missing from all three lists', orphans)

overlap = [c for c in standing if c in promo] + [c for c in standing if c in excluded] \
        + [c for c in promo if c in excluded]
ok(not overlap, 'and none is in two lists at once (it would be counted twice)', overlap)

ghosts = [c for c in accounted if c not in emitted]
ok(not ghosts, 'no list names a category the classifier can never produce', ghosts)


# ══════════════ B. the specific regression ══════════════
print('\nB. static — the one that was dropped')

ok('satisfaction_guarantee' in standing,
   'satisfaction_guarantee is in the STANDING floor (it is on every invoice)')
ok('other' in excluded,
   "'other' is explicitly excluded rather than silently dropped")
ok('other' not in standing,
   '  and is NOT folded into the floor (it is unidentified by definition)')

stack = fn('chewyAllowanceStack')
ok(stack.count('unclassifiedPct') == 2,
   'both stack paths report rates on categories in NO list', stack.count('unclassifiedPct'))
ok('!CHEWY_STANDING_CATS.includes(c) && !CHEWY_PROMO_CATS.includes(c)' in stack,
   "  as anything in NEITHER total, which is the question worth asking")
ok('unclassNote' in js and 'NOT in this floor' in js,
   'the Cost tab names an unclassified rate instead of hiding it')


# ══════════════ C. behaviour — the real sliced resolver ══════════════
print('\nC. behaviour — the real chewyAllowanceStack')

harness = r"""
let P = 0, F = 0;
const t = (label, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { P++; console.log('  ok  ' + label); }
  else { F++; console.log('  FAIL ' + label + '  got ' + g + ' want ' + w); }
};

//<<STANDING>>
//<<PROMO>>
//<<EXCLUDED>>

let _chewyPricingAllow = null, _chewyPricingDerived = null, _chewyPricingSrcNote = '';

// Jason's actual invoice shape: REB00224894 carries MDF / Damages / Freight /
// Satisfaction, and Auto Ship 5% comes off REB00206944. The FTAS and onsite-ad
// lines carry their rate in the NAME, not in rebate_pct_rate, so they parse as
// null and contribute nothing.
let chewyPnlData = [
  { category: 'coop_marketing',        rebate_name: 'MDF/Coop',     rebate_pct_rate: 16,  invoice_date: '2026-10-07' },
  { category: 'damages',               rebate_name: 'Damages',      rebate_pct_rate: 2,   invoice_date: '2026-10-07' },
  { category: 'freight',               rebate_name: 'Freight',      rebate_pct_rate: 1.5, invoice_date: '2026-10-07' },
  { category: 'satisfaction_guarantee',rebate_name: 'Satisfaction', rebate_pct_rate: 2,   invoice_date: '2026-10-07' },
  { category: 'autoship',              rebate_name: 'Auto Ship',    rebate_pct_rate: 5,   invoice_date: '2026-09-02' },
  { category: 'trade_allowance',       rebate_name: 'Cat Consumable s-MC2: Treats 35% FTAS', rebate_pct_rate: null, invoice_date: '2026-10-07' },
  { category: 'ad_spend',              rebate_name: 'Chewy Onsite Ads: MEOWIJUANA',          rebate_pct_rate: null, invoice_date: '2026-10-07' },
];

//<<DERIVE>>
//<<STACK>>

const s1 = chewyAllowanceStack();
t('the floor now includes Satisfaction (16 + 2 + 1.5 + 2 + 5)', s1.standingPct, 26.5);
t('  which is 2.00 points above what the page used to show',
  Math.round((s1.standingPct - 24.5) * 100) / 100, 2);
t('rate-less lines contribute nothing', s1.byCat.trade_allowance, undefined);
t('  so FTAS is 0% of the floor, not 35%', (s1.byCat.trade_allowance || 0), 0);
t('no promo rate on these invoices', s1.promoPct, 0);
t('nothing is unclassified here', s1.unclassifiedPct, 0);
t('the source is the invoices', s1.source, 'invoices');

// An unknown rebate name lands in 'other' and must be REPORTED, never folded in.
chewyPnlData = chewyPnlData.concat([
  { category: 'other', rebate_name: 'Mystery Line', rebate_pct_rate: 3, invoice_date: '2026-10-07' },
]);
const s2 = chewyAllowanceStack();
t("an 'other' rate does not inflate the floor", s2.standingPct, 26.5);
t('  and is surfaced instead of vanishing', s2.unclassifiedPct, 3);

// Latest-per-name: a newer invoice replaces the rate rather than adding to it.
chewyPnlData = chewyPnlData.concat([
  { category: 'coop_marketing', rebate_name: 'MDF/Coop', rebate_pct_rate: 10, invoice_date: '2026-11-01' },
]);
const s3 = chewyAllowanceStack();
t('a newer MDF rate REPLACES the old one', s3.byCat.coop_marketing, 10);
t('  so the floor moves with it', s3.standingPct, 20.5);

// Two DIFFERENT names in one category still sum.
chewyPnlData = chewyPnlData.concat([
  { category: 'coop_marketing', rebate_name: 'Co-op Digital', rebate_pct_rate: 1.5, invoice_date: '2026-11-01' },
]);
t('two distinct rebate names in one category sum',
  chewyAllowanceStack().byCat.coop_marketing, 11.5);

console.log('\n  ' + P + ' passed, ' + F + ' failed');
if (F) process.exit(1);
"""

def constline(name):
    a = js.index('const %s ' % name)
    b = js.index('];', a) + 2
    return js[a:b]

for tok, body in [('STANDING', constline('CHEWY_STANDING_CATS')),
                  ('PROMO',    constline('CHEWY_PROMO_CATS')),
                  ('EXCLUDED', constline('CHEWY_EXCLUDED_CATS')),
                  ('DERIVE',   fn('chewyPricingDeriveAllowances')),
                  ('STACK',    fn('chewyAllowanceStack'))]:
    marker = '//<<%s>>' % tok
    if harness.count(marker) != 1:
        raise SystemExit('FAIL: placeholder %s appears %d times' % (marker, harness.count(marker)))
    harness = harness.replace(marker, body, 1)

tmp = os.path.join(tempfile.gettempdir(), 'test_v1051_allow.js')
io.open(tmp, 'w', encoding='utf-8', newline='').write(harness)
r = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
print(r.stdout.rstrip())
if r.returncode != 0:
    print(r.stderr.rstrip()[:1500])
    fails.append('allowance stack behaviour')


print('\n' + ('=' * 60))
if F or fails:
    print('FAILED (%d static, %d sections): %s' % (F, len(fails), ', '.join(fails[:6])))
    sys.exit(1)
print('v10.51 — all green (%d static assertions + 1 behaviour section)' % P)
