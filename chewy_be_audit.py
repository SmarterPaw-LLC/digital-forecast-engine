#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit the Chewy break-even ROAS inputs, per Blake's 2026-10-26 email.

Blake: "please verify the BE cost on Chewy for most Kitty Zoom products,
600+ ROAS, some as high as 900+. These products are not advertisable."

Reproduces chewyBreakevenEcon() from index.html against live data so each
SKU's BE ROAS can be traced back to the four inputs that produce it:

    net          = wholesale/each * (1 - standing_allowance)
    contribution = net - cogs
    BE ROAS      = list_price / contribution * 100

Two known accuracy risks pull in OPPOSITE directions, so which one bites
decides whether Blake's figures are too high or too low:

  1. v10.69 - COGS basis. chewy_cogs -> landed_cost -> dtc_cogs -> amazon_cogs.
     dtc_cogs carries DTC shipping + pick/pack + overhead; amazon_cogs carries
     the FBA fulfilment fee. NEITHER applies to a 1P pallet going to a Chewy
     DC. A SKU on either reads a worse margin and a HIGHER BE ROAS than real.

  2. v10.51 - trade_allowance contributes 0%. The FTAS lines carry their rate
     inside the rebate NAME ("Treats 35% FTAS") and parse with
     rebate_pct_rate = null, so they are rate-less to the model. That
     UNDERSTATES the allowance, which OVERSTATES contribution and therefore
     reads a LOWER BE ROAS than real.

Writes a CSV next to this script. Prints nothing sensitive.
"""
import os, io, csv, json, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = 'https://yjcnuyoaemlipvuinptp.supabase.co'
DEFAULT_ANON = ('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.'
                'eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlqY251eW9hZW1saXB2dWlucHRwIiwicm9sZSI6ImFub24i'
                'LCJpYXQiOjE3NzgyNTY4NjcsImV4cCI6MjA5MzgzMjg2N30.'
                'CACwOGjnC370ZPjKlXG4dDpU9bVwCP4JDBD451WvwaM')


def load_env():
    p = os.path.join(HERE, '.env')
    if not os.path.exists(p):
        return
    # utf-8-sig: Notepad writes a BOM which would otherwise land inside the
    # first key's name (v10.74).
    for line in io.open(p, encoding='utf-8-sig'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def sign_in(url, anon, email, pw):
    req = urllib.request.Request(
        '%s/auth/v1/token?grant_type=password' % url,
        data=json.dumps({'email': email, 'password': pw}).encode(),
        method='POST')
    req.add_header('apikey', anon)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=30) as r:
        tok = json.loads(r.read().decode())
    if not tok.get('access_token'):
        raise RuntimeError('sign-in returned no access_token')
    return tok['access_token']


def q(url, anon, token, sql):
    req = urllib.request.Request(
        '%s/rest/v1/rpc/exec_sql' % url,
        data=json.dumps({'query': sql.strip()}).encode(), method='POST')
    req.add_header('apikey', anon)
    req.add_header('Authorization', 'Bearer %s' % token)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError('query failed: %s' % e.read().decode()[:600])


SQL_ROWS = """
select
  p.master_id,
  p.brand,
  p.title,
  p.chewy_sku,
  p.case_qty,
  cc.cost            as catalog_cost,
  cc.purchase_uom,
  cc.item_name       as catalog_name,
  pc.chewy_cogs,
  pc.landed_cost,
  pc.dtc_cogs,
  pc.amazon_cogs,
  pc.fulfillment_chewy,
  pc.fulfillment_dtc,
  pc.fulfillment_amazon,
  pc.shipping_cost,
  pc.overhead_dtc,
  pc.production_labor,
  ad.spend,
  ad.direct_units,
  ad.direct_sales,
  ad.list_price
from products p
left join chewy_catalog cc on cc.chewy_sku = p.chewy_sku
left join product_cogs  pc on pc.master_id = p.master_id
left join lateral (
  select sum(a.spend) as spend,
         sum(a.direct_units) as direct_units,
         sum(a.direct_sales) as direct_sales,
         case when sum(a.impressions) > 0
              then sum(a.chewy_list_price * a.impressions) / nullif(sum(a.impressions),0)
              else max(a.chewy_list_price) end as list_price
  from chewy_ad_spend a
  where a.chewy_sku = p.chewy_sku
    and a.date >= current_date - interval '90 days'
) ad on true
where p.chewy_sku is not null and p.chewy_sku <> ''
  and coalesce(p.active, true) = true
order by p.brand, p.title
"""

SQL_ALLOW = """
select distinct on (r.rebate_name)
  r.rebate_name, r.category, r.rebate_pct_rate, r.invoice_date
from chewy_rebates r
order by r.rebate_name, r.invoice_date desc
"""

# Mirrors CHEWY_STANDING_CATS in index.html.
STANDING = ['trade_allowance', 'autoship', 'damages', 'freight',
            'coop_marketing', 'ad_spend', 'satisfaction_guarantee']
PROMO = ['promo_bxgx', 'promo_lumpsum', 'evergreen_promo']

COGS_PREF = ['chewy_cogs', 'landed_cost', 'dtc_cogs', 'amazon_cogs']
# v10.69: which sources carry fulfilment that does NOT apply to a Chewy 1P
# pallet, so a SKU resolving to one reads a worse margin than reality.
WRONG_BASIS = {'dtc_cogs', 'amazon_cogs'}


def price_per_each(cost, uom, case_qty):
    """Port of chewyCatalogPricePerEach()."""
    if cost is None:
        return None, 'no-catalog'
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return None, 'no-cost'
    if cost <= 0:
        return None, 'no-cost'
    u = (uom or '').strip().upper()
    if u in ('EA', 'EACH', 'UN', 'UNIT', 'E'):
        return cost, None
    if u in ('CS', 'CASE', 'CA', 'CTN', 'CT'):
        try:
            qn = int(case_qty)
        except (TypeError, ValueError):
            return None, 'no-case-qty'
        if qn <= 0:
            return None, 'no-case-qty'
        return cost / qn, None
    return None, 'unknown-uom'


def main():
    load_env()
    url = (os.environ.get('SUPABASE_URL') or DEFAULT_URL).rstrip('/')
    anon = os.environ.get('SUPABASE_ANON_KEY') or DEFAULT_ANON
    email, pw = os.environ.get('SUPABASE_EMAIL'), os.environ.get('SUPABASE_PASSWORD')
    if not email or not pw:
        print('Missing SUPABASE_EMAIL / SUPABASE_PASSWORD in .env'); return 1

    token = sign_in(url, anon, email, pw)
    print('signed in OK')

    allow_rows = q(url, anon, token, SQL_ALLOW)
    by_cat = {}
    rateless = []
    for r in allow_rows:
        cat = r.get('category') or 'other'
        rate = r.get('rebate_pct_rate')
        if rate is None:
            rateless.append((r.get('rebate_name'), cat))
            continue
        by_cat[cat] = by_cat.get(cat, 0.0) + float(rate)

    standing = sum(by_cat.get(c, 0.0) for c in STANDING)
    promo = sum(by_cat.get(c, 0.0) for c in PROMO)
    unclassified = sum(v for k, v in by_cat.items()
                       if k not in STANDING and k not in PROMO)

    print('\n=== ALLOWANCE STACK (derived from chewy_rebates) ===')
    for cat in sorted(by_cat, key=lambda c: -by_cat[c]):
        tag = 'STANDING' if cat in STANDING else ('PROMO' if cat in PROMO else 'UNCLASSIFIED')
        print('  %-26s %6.2f%%  [%s]' % (cat, by_cat[cat], tag))
    print('  %-26s %6.2f%%' % ('STANDING TOTAL', standing))
    print('  %-26s %6.2f%%' % ('promo (not in floor)', promo))
    print('  %-26s %6.2f%%' % ('unclassified', unclassified))
    if rateless:
        print('\n  !! %d rate-less rebate lines (rate lives in the NAME, parses null):' % len(rateless))
        for n, c in rateless[:12]:
            print('     - %-46s [%s]' % ((n or '')[:46], c))
        print('     -> these contribute 0%% to the floor, so the standing rate above')
        print('        is UNDERSTATED, which makes BE ROAS read LOWER than reality.')

    rows = q(url, anon, token, SQL_ROWS)
    print('\n=== %d active products with a Chewy SKU ===' % len(rows))

    out = []
    for r in rows:
        wholesale, reason = price_per_each(r.get('catalog_cost'),
                                           r.get('purchase_uom'),
                                           r.get('case_qty'))
        cogs, cogs_field = None, None
        for f in COGS_PREF:
            if r.get(f) is not None:
                cogs, cogs_field = float(r[f]), f
                break

        lp = r.get('list_price')
        lp = float(lp) if lp not in (None, '') else None

        net = wholesale * (1 - standing / 100.0) if wholesale else None
        contrib = (net - cogs) if (net is not None and cogs is not None) else None
        be_roas = (lp / contrib * 100.0) if (contrib and contrib > 0 and lp) else None
        gm_pct = (contrib / wholesale * 100.0) if (contrib is not None and wholesale) else None

        # What the SAME SKU would read if the wrong-basis fulfilment were
        # stripped out - i.e. costed as a 1P pallet instead of a DTC parcel.
        cogs_1p, be_1p = None, None
        if cogs_field in WRONG_BASIS:
            strip = 0.0
            if cogs_field == 'dtc_cogs':
                for k in ('fulfillment_dtc', 'shipping_cost', 'overhead_dtc'):
                    strip += float(r.get(k) or 0)
            else:
                strip += float(r.get('fulfillment_amazon') or 0)
            cogs_1p = max(cogs - strip, 0.0)
            c1 = (net - cogs_1p) if net is not None else None
            be_1p = (lp / c1 * 100.0) if (c1 and c1 > 0 and lp) else None

        out.append({
            'brand': r.get('brand'), 'title': (r.get('title') or '')[:52],
            'master_id': r.get('master_id'), 'chewy_sku': r.get('chewy_sku'),
            'uom': r.get('purchase_uom'), 'case_qty': r.get('case_qty'),
            'catalog_cost': r.get('catalog_cost'),
            'wholesale_each': round(wholesale, 4) if wholesale else None,
            'blocked_reason': reason,
            'standing_pct': round(standing, 2),
            'net_to_us': round(net, 4) if net else None,
            'cogs': round(cogs, 4) if cogs is not None else None,
            'cogs_source': cogs_field,
            'cogs_basis_ok': '' if cogs_field not in WRONG_BASIS else 'WRONG-BASIS',
            'contribution': round(contrib, 4) if contrib is not None else None,
            'gm_pct_on_wholesale': round(gm_pct, 1) if gm_pct is not None else None,
            'list_price': lp,
            'be_roas_pct': round(be_roas, 0) if be_roas else None,
            'cogs_if_1p_basis': round(cogs_1p, 4) if cogs_1p is not None else None,
            'be_roas_if_1p_basis': round(be_1p, 0) if be_1p else None,
            'spend_90d': r.get('spend'),
            'direct_units_90d': r.get('direct_units'),
        })

    p = os.path.join(HERE, 'chewy_be_audit.csv')
    with io.open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    print('wrote %s (%d rows)' % (p, len(out)))

    kkz = [r for r in out if (r['brand'] or '').lower().startswith('kitty')]
    print('\n=== KITTY KA-ZOOM: %d products ===' % len(kkz))
    print('%-40s %7s %7s %7s %7s %8s %-12s %s' % (
        'PRODUCT', 'WHSL/ea', 'COGS', 'CONTRIB', 'LIST', 'BE ROAS', 'COGS SRC', 'FLAG'))
    for r in sorted(kkz, key=lambda x: -(x['be_roas_pct'] or 0)):
        print('%-40s %7s %7s %7s %7s %8s %-12s %s' % (
            (r['title'] or '')[:40],
            ('%.2f' % r['wholesale_each']) if r['wholesale_each'] else '-',
            ('%.2f' % r['cogs']) if r['cogs'] is not None else '-',
            ('%.2f' % r['contribution']) if r['contribution'] is not None else '-',
            ('%.2f' % r['list_price']) if r['list_price'] else '-',
            ('%d%%' % r['be_roas_pct']) if r['be_roas_pct'] else '-',
            r['cogs_source'] or '-',
            (r['cogs_basis_ok'] or r['blocked_reason'] or '')))

    # Which input is actually driving the high numbers?
    with_be = [r for r in kkz if r['be_roas_pct']]
    if with_be:
        bad = [r for r in with_be if r['cogs_basis_ok']]
        print('\n  %d of %d KKZ SKUs with a BE ROAS are on a WRONG-BASIS COGS source' % (len(bad), len(with_be)))
        if bad:
            print('  Re-costed as 1P (fulfilment stripped):')
            for r in bad:
                print('    %-40s %d%% -> %s' % (
                    (r['title'] or '')[:40], r['be_roas_pct'],
                    ('%d%%' % r['be_roas_if_1p_basis']) if r['be_roas_if_1p_basis'] else 'n/a'))
    blocked = [r for r in kkz if r['blocked_reason']]
    if blocked:
        print('\n  %d KKZ SKUs cannot compute wholesale/each:' % len(blocked))
        for r in blocked:
            print('    %-40s %s (uom=%s case_qty=%s)' % (
                (r['title'] or '')[:40], r['blocked_reason'], r['uom'], r['case_qty']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
