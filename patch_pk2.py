# query_paid_keywords.sql: separate ASIN PLACEMENTS from real search terms.
#
# Jason spotted "b0fx5qplxl" sitting in the keyword column. That is an ASIN
# (B0FX5QPLXL), not a search query. When an ad runs on a product DETAIL PAGE
# rather than in search results, Amazon reports the "customer search term" as
# the ASIN of the page it appeared on. The TARGETING_EXPRESSION match type on
# those rows confirms it: auto / product targeting, not keyword targeting.
#
# Mixing placements into a column called "keyword" is misleading, and it also
# means any keyword count or keyword export silently includes things that are
# not keywords. So:
#   - term_type          'search term' vs 'ASIN placement'
#   - keyword            ASINs rendered back in uppercase so they read as ASINs
#   - placement_product  if the ASIN is OURS, name it. Paying to place ads on
#                        your own detail page is worth seeing explicitly.
import io, os

P = r'C:\Users\Jason\digital-forecast-engine\query_paid_keywords.sql'
s = io.open(P, encoding='utf-8').read()
orig = len(s)
n = 0

def rep(old, new, label, count=1):
    global s, n
    got = s.count(old)
    assert got == count, 'ANCHOR %s: expected %d, found %d' % (label, count, got)
    s = s.replace(old, new, count)
    n += 1
    print('  ok  %s' % label)

# ---- header note
rep('''-- "keyword" is the CUSTOMER SEARCH TERM, what the shopper actually typed. What
-- we bid on to match it is summarised as match_types / campaigns / bid_targets,
-- because one search term is commonly matched by several keywords, ad groups
-- and match types.''',
'''-- "keyword" is the CUSTOMER SEARCH TERM, what the shopper actually typed. What
-- we bid on to match it is summarised as match_types / campaigns / bid_targets,
-- because one search term is commonly matched by several keywords, ad groups
-- and match types.
--
-- NOT EVERY ROW IS A KEYWORD. When an ad runs on a product DETAIL PAGE rather
-- than in search results, Amazon reports the "customer search term" as the ASIN
-- of the page the ad appeared on (these show a TARGETING_EXPRESSION match type).
-- Those are PLACEMENTS, not search queries. term_type separates them, and
-- placement_product names the ASIN when it is one of ours - paying to place ads
-- on your own detail page is worth seeing rather than filtering out silently.''',
'header explains ASIN placements')

# ---- select: classify + restore ASIN casing + resolve our own ASINs
rep('''  a.keyword,
  a.match_types,''',
'''  -- An ASIN is 10 chars starting B0. Rendered back in uppercase so it reads as
  -- an ASIN rather than as gibberish lowercased by the normalisation above.
  case when a.keyword ~ '^b0[a-z0-9]{8}$'
       then 'ASIN placement' else 'search term' end              as term_type,
  case when a.keyword ~ '^b0[a-z0-9]{8}$'
       then upper(a.keyword) else a.keyword end                  as keyword,
  case when a.keyword ~ '^b0[a-z0-9]{8}$'
       then coalesce(tp.short_name, tp.title, '(not one of ours)') end
                                                                 as placement_product,
  a.match_types,''',
'term_type + ASIN casing + placement_product')

# ---- join to resolve placement ASINs against our own catalog
rep('''left join products pa on a.master_id is null and pa.asin = nullif(a.akey, '')''',
'''left join products pa on a.master_id is null and pa.asin = nullif(a.akey, '')
-- Resolve the PLACEMENT ASIN (the page the ad ran on), which is a different
-- product from the one being advertised.
left join products tp on tp.asin = upper(a.keyword)''',
'join placement ASIN to catalog')

# ---- flag self-targeting
rep('''  case
    when a.clicks = 0        then 'no clicks - impressions only'
    when a.orders = 0        then 'SPEND, NO ORDERS'
    when a.spend > a.sales   then 'losing money'
    else 'profitable'
  end                                                           as flag''',
'''  case
    when a.clicks = 0        then 'no clicks - impressions only'
    when a.orders = 0        then 'SPEND, NO ORDERS'
    when a.spend > a.sales   then 'losing money'
    else 'profitable'
  end                                                           as flag,

  -- Advertising one of our own products onto another of our own detail pages.
  -- Sometimes deliberate (defending the page from competitor ads), sometimes
  -- just paying for a customer who had already found us.
  case when tp.master_id is not null and tp.master_id is distinct from a.master_id
       then 'ads on our OWN product page'
       when tp.master_id is not null then 'ads on its own detail page'
  end                                                           as self_targeting''',
'self-targeting flag')

tmp = P + '.tmp'
io.open(tmp, 'w', encoding='utf-8', newline='').write(s)
os.replace(tmp, P)
print('\n%d edits. %d -> %d' % (n, orig, len(s)))
