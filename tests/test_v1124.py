# -*- coding: utf-8 -*-
"""v11.24 - one uploader had four names and the commonest one was false.

Jason, pointing at the Amazon Ads upload card: "is this the one? if so, why
give it a new name all of a sudden?"

I had not renamed it. It was carrying two names stacked on top of each other
in his screenshot, and two more elsewhere:

    group header    Amazon Ads - SB / SD / DSP / TV (per-ASIN)
    card title      Amazon Ads - Unified Report
    source chip     Amazon Ads (non-SP)       <- on every scorecard
    upload history  Amazon Ads (non-SP)

The assertions that earn their keep:

  * B1 THE LABEL WAS FALSE, NOT JUST INCONSISTENT. v6.76 dropped Sponsored
    Products, so "(non-SP)" was true then. v8.17 started KEEPING them. The
    guard drives the REAL parser on a mixed export and proves SP rows land in
    the table, so a label claiming the source excludes SP is wrong by
    construction rather than by my say-so. On the live data that is 78.1% of
    the table, and the v11.16 Ads tab reads all of it.

  * A2 THREE REGISTRIES, ONE NAME. The scorecard chip, the upload-history
    picker and the Ads adapter each carry a label for amazon_ad_spend. They
    are compared to each other, so a fifth name cannot appear in one of them
    and go unnoticed.

  * C1 HTML COMMENTS BALANCE. Fixing this, I replaced a one-line comment with
    text that dropped its own `-->`. An unterminated comment in this file
    swallows every element after it until the next one - the whole Amazon Ads
    upload group, in that case. Caught by reading the output back, and now by
    an assertion.

NOT asserted: that a group header must equal its card title. Fifteen groups
are legitimately hierarchical - "Amazon Brand Analytics - SQP, ASIN view" over
"Search Query Performance - ASIN view" is a source system over a file, not a
contradiction. What was wrong here was a header naming a different SCOPE, not
a broader one.
"""
import io, os, re, sys, json, subprocess

SRC = r'C:\Users\Jason\digital-forecast-engine\index.html'
SP  = os.path.dirname(os.path.abspath(__file__))
s   = io.open(SRC, encoding='utf-8').read()
js  = max(re.findall(r'<script\b[^>]*>(.*?)</script>', s, re.S), key=len)

passed = failed = 0
def ok(cond, name, got=None):
    global passed, failed
    if cond: passed += 1; print('  ok    ' + name)
    else:    failed += 1; print('  FAIL  %s%s' % (name, '' if got is None else '  got: ' + ascii(got)))

def eq(name, got, want):
    ok(got == want, name, None if got == want else got)


print('\n== A. one source, one name ==')

ok('Amazon Ads (non-SP)' not in s,
   'A1a the false label is GONE from the file, not merely bypassed')
ok('SB / SD / DSP / TV (per-ASIN)' not in s,
   'A1b and so is the group header that claimed the same exclusion')

# the three registries that each hold a label for this one table
m_ds = re.search(r"amazon_ad_spend:\s*\{\s*icon:\s*'([^']+)',\s*label:\s*'([^']+)'", js)
m_uh = re.search(r"amazon_ad_spend:\s*\{\s*label:\s*'([^']+)'", js)
m_ch = re.search(r"amazon:\s*\{\s*label:\s*'([^']+)',\s*icon:\s*'([^']+)'", js)
ok(bool(m_ds and m_uh and m_ch), 'A2a all three registries carry a label')
labels = {'DATA_SOURCES': m_ds.group(2) if m_ds else None,
          'UH_SOURCES':   m_uh.group(1) if m_uh else None,
          'ADS_CHANNELS': m_ch.group(1) if m_ch else None}
eq('A2b and they are the SAME name - a fifth label cannot appear in one of '
   'them unnoticed', len(set(labels.values())), 1)
eq('A2c which is the short form', labels['DATA_SOURCES'], 'Amazon Ads')

# the icon too - one concept, one glyph (rule #2).
# ⚠ DATA_SOURCES writes the glyph as a source-literal surrogate escape and
# ADS_CHANNELS writes the character. Decoded through json, which resolves the
# surrogate pair the way the browser does - `unicode_escape` does not, and my
# first version of this line failed on two glyphs that were already identical.
def _glyph(t):
    return json.loads('"' + t.replace('"', '\\"') + '"')
eq('A2d and one glyph across the registries',
   len({_glyph(m_ds.group(1)), _glyph(m_ch.group(2))}), 1)

# the uploader's own two labels, which Jason saw stacked
grp = s[s.index('<div class="up-grp" id="grp-amazon-ads"'):]
grp = grp[:grp.index('<div class="up-grp" id="', 10)] if '<div class="up-grp" id="' in grp[10:] else grp
grp_nc = re.sub(r'<!--.*?-->', '', grp, flags=re.S)
hdr = re.search(r'<div class="up-grp-title">(.*?)</div>', grp_nc).group(1)
dzs = re.findall(r'<div class="dz-title">(.*?)</div>', grp_nc)
eq('A3a the group holds exactly ONE dropzone, so its header and that card '
   'title describe one thing', len(dzs), 1)
eq('A3b and they now say the same thing', hdr.strip(), dzs[0].strip())
ok('Unified Report' in hdr, 'A3c the card\'s own name won', hdr)

# the header's TOOLTIP has said "every ad product" since v8.17 - the title
# contradicted it one line below. Require the tooltip to survive, so the
# check cannot pass against a page that simply dropped the evidence.
ok('Sponsored Products + Sponsored Brands' in grp,
   'A3d the tooltip that the old title contradicted is still there')

print('\n== B. "non-SP" was FALSE, not just inconsistent ==')

FIX = r"""
var allProducts = [];
const LINES = [
  'Date,Country,Advertised product ID,Ad product,Advertiser account name,Campaign name,Total cost,Impressions,Clicks,Purchases,Sales',
  '2026-10-01,US,B0SP00001,Sponsored Products,Meowijuana,SP - AUTO,100.00,5000,80,6,400',
  '2026-10-01,US,B0SB00002,Sponsored Brands,Meowijuana,SBV - KW,50.00,3000,20,1,90',
  '2026-10-02,US,B0SD00003,Sponsored Display,Meowijuana,SD - RT,9.00,900,4,0,0',
  '2026-10-02,US,,Sponsored TV,Meowijuana,TV - In Market,25.00,9000,0,0,0',
];
const parsed = parseAmazonAdsUnified(LINES.join('\n'));
const bySlug = {};
for (const r of parsed.rows) bySlug[r.ad_product] = (bySlug[r.ad_product] || 0) + r.spend;
console.log(JSON.stringify({
  slugs: Object.keys(bySlug).sort(),
  spSpend: bySlug['sponsored_products'] || 0,
  total: parsed.rows.reduce((a, r) => a + r.spend, 0),
  spRows: parsed.rows.filter(r => r.ad_product === 'sponsored_products').length,
}));
"""

def fn(name, kind='function'):
    i = js.index('%s %s(' % (kind, name))
    j = js.index('{', js.index(')', i))
    d, k = 0, j
    while True:
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if d == 0: return js[i:k + 1]
        k += 1

HARNESS = '\n'.join([fn('parseCSV'), fn('adsProductSlug'), fn('adsParseDate'),
                     fn('adsStripExcel'), fn('adsMarketplaceToRegion'),
                     fn('adsAdvertiserToBrand'), fn('parseAmazonAdsUnified'), FIX])
hpath = os.path.join(SP, 'test_v1124.js')
io.open(hpath, 'w', encoding='utf-8').write(HARNESS)
res = subprocess.run(['node', hpath], capture_output=True, text=True, encoding='utf-8')
if res.returncode != 0:
    print('HARNESS FAILED:\n' + (res.stderr or '')[:2000]); sys.exit(1)
R = json.loads(res.stdout)

eq('B1a the REAL parser keeps every ad product', R['slugs'],
   ['sponsored_brands', 'sponsored_display', 'sponsored_products', 'sponsored_tv'])
eq('B1b including Sponsored Products, which v6.76 dropped and v8.17 keeps',
   R['spRows'], 1)
eq('B1c with its spend', R['spSpend'], 100)
ok(R['spSpend'] / R['total'] > 0.5,
   'B1d and on this fixture SP is the MAJORITY of the file - so a source label '
   'saying "(non-SP)" is wrong by construction, not by opinion',
   R['spSpend'] / R['total'])

print('\n== C. the near-miss: HTML comments ==')
eq('C1a every <!-- has a --> ', s.count('<!--'), s.count('-->'))
# an unterminated comment shows up as two opens with no close between them
bad = []
pos = 0
while True:
    i = s.find('<!--', pos)
    if i < 0: break
    j = s.find('-->', i)
    k = s.find('<!--', i + 4)
    if j < 0 or (k >= 0 and k < j):
        bad.append(s[i:i + 70])
    pos = i + 4
eq('C1b and no comment opens before the previous one closed - an unterminated '
   'comment here swallows every element after it', bad, [])
masked = re.sub(r'<!--.*?-->', '', s, flags=re.S)
eq('C2  div balance with comments masked (the v11.12 rule)',
   masked.count('<div'), masked.count('</div>'))

print('\n== D. "non-SP" survives where it describes a SLICE ==')
ok('Ad Spend non-SP' in s,
   'D1  the SQL view column keeps it: the P&L genuinely takes a non-SP slice '
   'of this table, because SP SPEND comes from SKU Economics to match '
   'Amazon\'s charge line and only SP SALES come from here')
ok('non-SP' in js,
   'D2  and so do the fold comments that explain that arithmetic')
ok('No Sponsored Brands / Display / DSP / TV rows in this window' in js,
   'D3  the Ad Spend tooltip describes the missing SLICE without renaming the '
   'upload it points you at')

print('\n' + '-' * 60)
print('v11.24: %d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
