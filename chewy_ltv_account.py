#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chewy LTV + account-level program efficiency.

Two questions this answers, neither of which the per-SKU break-even model can:

  1. AUTOSHIP LTV. The BE model prices the first order plus any recurring
     orders that already landed inside the reporting window. It does not price
     FUTURE reorders. Chewy gives us autoship_signups and
     autoship_actualized_orders per SKU per day, so:

         recurring orders in month M = actualized_orders(M) - signups(M)

     Fit a geometric retention curve (survival(k) = rho^k) against that series
     and the expected lifetime orders per signup falls out:

         LTV_orders = 1 + rho / (1 - rho)

     That turns into an LTV multiplier on contribution per ad-driven unit:

         multiplier = 1 + p_autoship * (LTV_orders - 1) * units_per_order

     and an LTV-adjusted break-even ROAS = list / (contribution * multiplier).

  2. ACCOUNT-LEVEL PROGRAM EFFICIENCY. Per-SKU realized ROAS only counts
     Chewy's own click attribution. It ignores every unit that sold without a
     click, and it ignores that ad-driven NTB customers seed later organic +
     autoship volume. chewy_sales_weekly carries TOTAL sell-through per SKU per
     week, so the account-level read is:

         organic units      = total sell-through - ad-attributed units
         total contribution = SUM(units * contribution_per_unit)
         program net        = total contribution - total ad spend
         TACOS              = ad spend / total retail sell-through

Reads per-SKU economics from chewy_be_audit.csv (run chewy_be_audit.py first).
Writes chewy_ltv_cohorts.csv + chewy_account_monthly.csv. Prints nothing
sensitive.
"""
import os, io, csv, json, sys, urllib.request, urllib.error
from collections import defaultdict

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
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError('query failed: %s' % e.read().decode()[:700])


class _Money(object):
    """`money % 12345.6` -> "$12,346".

    Python's % formatting has no thousands-separator flag, so this wraps
    format(v, ',.0f') in an object that keeps the % call sites unchanged.
    """
    def __mod__(self, v):
        try:
            return '$' + format(float(v or 0), ',.0f')
        except (TypeError, ValueError):
            return '$0'


money = _Money()


def f(v, d=0.0):
    try:
        if v is None or v == '':
            return d
        return float(v)
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------- SQL

# Monthly autoship + ad series, account-wide and per brand.
SQL_ADS_MONTHLY = """
select
  to_char(date_trunc('month', a.date), 'YYYY-MM') as mo,
  coalesce(p.brand, a.advertiser)                 as brand,
  sum(a.spend)                      as spend,
  sum(a.impressions)                as impressions,
  sum(a.clicks)                     as clicks,
  sum(a.direct_units)               as direct_units,
  sum(a.direct_sales)               as direct_sales,
  sum(a.total_orders)               as total_orders,
  sum(a.ntb_customers)              as ntb_customers,
  sum(a.autoship_signups)           as signups,
  sum(a.autoship_actualized_orders) as as_orders,
  sum(a.autoship_actualized_sales)  as as_sales
from chewy_ad_spend a
left join products p on p.chewy_sku = a.chewy_sku
group by 1, 2
order by 1, 2
"""

# Total Chewy sell-through per month (every unit, not just ad-attributed).
SQL_SELL_MONTHLY = """
select
  to_char(date_trunc('month', s.week_start), 'YYYY-MM') as mo,
  coalesce(p.brand, 'Unknown')                          as brand,
  sum(s.units_sold)     as units_sold,
  sum(s.autoship_units) as autoship_units,
  sum(s.merch_sales)    as merch_sales
from chewy_sales_weekly s
left join products p on p.master_id = s.master_id
group by 1, 2
order by 1, 2
"""

# Per-SKU sell-through so we can weight contribution correctly.
SQL_SELL_SKU = """
select
  to_char(date_trunc('month', s.week_start), 'YYYY-MM') as mo,
  s.chewy_sku,
  sum(s.units_sold)     as units_sold,
  sum(s.autoship_units) as autoship_units,
  sum(s.merch_sales)    as merch_sales
from chewy_sales_weekly s
group by 1, 2
order by 1, 2
"""

# Ad-attributed units per SKU per month, for the organic split.
SQL_ADS_SKU = """
select
  to_char(date_trunc('month', a.date), 'YYYY-MM') as mo,
  a.chewy_sku,
  sum(a.spend)            as spend,
  sum(a.direct_units)     as direct_units,
  sum(a.autoship_signups) as signups,
  sum(a.ntb_customers)    as ntb_customers
from chewy_ad_spend a
group by 1, 2
order by 1, 2
"""


# ---------------------------------------------------------------- retention fit

def fit_geometric_retention(months, signups, recurring):
    """Least-squares fit of survival(k) = rho^k against observed recurring orders.

    Model: a subscriber acquired in month j places a recurring order in month
    M with probability rho^(M-j). So

        predicted_recurring(M) = SUM over j<M of signups(j) * rho^(M-j)

    Scans rho on a fine grid rather than solving analytically - the objective
    is cheap (a few hundred months x a few hundred rho values) and a grid scan
    cannot land on a local minimum or diverge, which matters more here than
    speed. Returns (best_rho, r2, n_months_fitted).
    """
    n = len(months)
    if n < 4:
        return None, None, n

    # Drop the first month: it has no prior cohort, so predicted recurring is 0
    # by construction and would just anchor the fit at the origin.
    idx = list(range(1, n))

    obs = [recurring[i] for i in idx]
    obs_mean = sum(obs) / len(obs) if obs else 0.0
    ss_tot = sum((o - obs_mean) ** 2 for o in obs)

    best = (None, -1e18, None)
    rho = 0.01
    while rho < 0.995:
        pred = []
        for i in idx:
            s = 0.0
            for j in range(i):
                s += signups[j] * (rho ** (i - j))
            pred.append(s)
        ss_res = sum((o - p) ** 2 for o, p in zip(obs, pred))
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        if r2 > best[1]:
            best = (rho, r2, pred)
        rho += 0.005

    return best[0], best[1], len(idx)


def main():
    load_env()
    url = (os.environ.get('SUPABASE_URL') or DEFAULT_URL).rstrip('/')
    anon = os.environ.get('SUPABASE_ANON_KEY') or DEFAULT_ANON
    email, pw = os.environ.get('SUPABASE_EMAIL'), os.environ.get('SUPABASE_PASSWORD')
    if not email or not pw:
        print('Missing SUPABASE_EMAIL / SUPABASE_PASSWORD in .env')
        return 1

    token = sign_in(url, anon, email, pw)
    print('signed in OK')

    # ---- per-SKU economics from the audit CSV ----
    econ_path = os.path.join(HERE, 'chewy_be_audit.csv')
    if not os.path.exists(econ_path):
        print('chewy_be_audit.csv missing - run chewy_be_audit.py first')
        return 1
    econ = {}
    with io.open(econ_path, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            sku = (row.get('chewy_sku') or '').strip()
            if not sku:
                continue
            econ[sku] = {
                'brand': row.get('brand') or 'Unknown',
                'title': row.get('title') or '',
                'contribution': f(row.get('contribution'), None),
                'list_price': f(row.get('list_price'), None),
                'wholesale': f(row.get('wholesale_each'), None),
                'net_to_us': f(row.get('net_to_us'), None),
                'be_roas': f(row.get('be_roas_pct'), None),
                'gm_pct': f(row.get('gm_pct_on_wholesale'), None),
            }
    print('loaded economics for %d Chewy SKUs' % len(econ))

    ads_mo = q(url, anon, token, SQL_ADS_MONTHLY)
    sell_mo = q(url, anon, token, SQL_SELL_MONTHLY)
    sell_sku = q(url, anon, token, SQL_SELL_SKU)
    ads_sku = q(url, anon, token, SQL_ADS_SKU)
    print('pulled %d ad-month rows, %d sell-month rows, %d sell-sku rows, %d ad-sku rows'
          % (len(ads_mo), len(sell_mo), len(sell_sku), len(ads_sku)))

    out = []
    w = out.append

    # ============================================================ PART 1: LTV

    w('')
    w('=' * 78)
    w('PART 1  AUTOSHIP LTV')
    w('=' * 78)

    # Collapse to account-level monthly autoship series.
    acct = defaultdict(lambda: defaultdict(float))
    for r in ads_mo:
        m = r['mo']
        for k in ('spend', 'direct_units', 'direct_sales', 'ntb_customers',
                  'signups', 'as_orders', 'as_sales', 'total_orders',
                  'impressions', 'clicks'):
            acct[m][k] += f(r.get(k))

    months = sorted(acct.keys())
    signups = [acct[m]['signups'] for m in months]
    as_orders = [acct[m]['as_orders'] for m in months]
    recurring = [max(0.0, as_orders[i] - signups[i]) for i in range(len(months))]

    w('')
    w('Monthly autoship series (account-wide, all brands)')
    w('%-9s %10s %10s %10s %12s %12s' % ('MONTH', 'SIGNUPS', 'AS ORDERS',
                                         'RECURRING', 'AS SALES', 'AD SPEND'))
    for i, m in enumerate(months):
        w('%-9s %10.0f %10.0f %10.0f %12s %12s' % (
            m, signups[i], as_orders[i], recurring[i],
            money % acct[m]['as_sales'],
            money % acct[m]['spend']))
    w('%-9s %10.0f %10.0f %10.0f %12s %12s' % (
        'TOTAL', sum(signups), sum(as_orders), sum(recurring),
        money % sum(acct[m]['as_sales'] for m in months),
        money % sum(acct[m]['spend'] for m in months)))

    rho, r2, nfit = fit_geometric_retention(months, signups, recurring)

    w('')
    if rho is None:
        w('NOT ENOUGH MONTHS to fit a retention curve (%d months).' % len(months))
        ltv_orders = None
    else:
        ltv_orders = 1.0 + rho / (1.0 - rho)
        # Months to reach 50% survival, for a readable framing of rho.
        half_life = None
        if 0 < rho < 1:
            k = 1
            while rho ** k > 0.5 and k < 200:
                k += 1
            half_life = k
        w('Geometric retention fit')
        w('  monthly survival rho      %.3f   (%.1f%% of subscribers reorder next month)'
          % (rho, rho * 100))
        w('  fit quality R2            %.3f   over %d months' % (r2, nfit))
        if half_life:
            w('  median subscriber life    ~%d months' % half_life)
        w('  LTV orders per signup     %.2f   (1 first order + %.2f recurring)'
          % (ltv_orders, ltv_orders - 1.0))

        # Sanity check: observed recurring per signup over the whole window
        # is CENSORED (recent signups have not had time to reorder), so it is
        # a floor on the true figure, not a competing estimate.
        if sum(signups) > 0:
            obs_mult = sum(recurring) / sum(signups)
            w('  observed recurring/signup %.2f   (censored floor - recent cohorts'
              % obs_mult)
            w('                                   have not reordered yet)')

    # Units per autoship order, and the autoship attach rate on ad-driven units.
    tot_as_orders = sum(as_orders)
    tot_as_sales = sum(acct[m]['as_sales'] for m in months)
    tot_direct_units = sum(acct[m]['direct_units'] for m in months)
    tot_signups = sum(signups)

    # AOV in retail dollars, converted to units using the spend-weighted list price.
    lp_num = lp_den = 0.0
    for r in ads_sku:
        sku = (r.get('chewy_sku') or '').strip()
        e = econ.get(sku)
        if not e or not e.get('list_price'):
            continue
        sp = f(r.get('spend'))
        lp_num += e['list_price'] * sp
        lp_den += sp
    wavg_list = (lp_num / lp_den) if lp_den > 0 else None

    as_aov = (tot_as_sales / tot_as_orders) if tot_as_orders > 0 else None
    units_per_order = (as_aov / wavg_list) if (as_aov and wavg_list) else None
    attach = (tot_signups / tot_direct_units) if tot_direct_units > 0 else None

    w('')
    w('Order economics')
    w('  autoship AOV              %s' % ('$%.2f' % as_aov if as_aov else 'n/a'))
    w('  spend-weighted list price %s' % ('$%.2f' % wavg_list if wavg_list else 'n/a'))
    w('  units per autoship order  %s' % ('%.2f' % units_per_order if units_per_order else 'n/a'))
    w('  autoship attach rate      %s of ad-driven units' % ('%.1f%%' % (attach * 100) if attach else 'n/a'))

    ltv_mult = None
    if ltv_orders and attach and units_per_order:
        ltv_mult = 1.0 + attach * (ltv_orders - 1.0) * units_per_order
        w('')
        w('LTV MULTIPLIER on contribution per ad-driven unit')
        w('  1 + %.4f attach x %.2f extra orders x %.2f units/order = %.3f'
          % (attach, ltv_orders - 1.0, units_per_order, ltv_mult))
        w('  So every 100 ad-driven units are worth %.0f units of contribution'
          % (ltv_mult * 100))
        w('  over the subscriber life, not 100.')

    # ---- per-SKU LTV-adjusted break-even ----
    # Attach rate varies by SKU; use the SKU's own where volume supports it.
    sku_attach = {}
    sku_spend = defaultdict(float)
    sku_units = defaultdict(float)
    sku_signups = defaultdict(float)
    sku_ntb = defaultdict(float)
    for r in ads_sku:
        sku = (r.get('chewy_sku') or '').strip()
        sku_spend[sku] += f(r.get('spend'))
        sku_units[sku] += f(r.get('direct_units'))
        sku_signups[sku] += f(r.get('signups'))
        sku_ntb[sku] += f(r.get('ntb_customers'))
    for sku in sku_units:
        if sku_units[sku] >= 50:          # enough volume for its own rate
            sku_attach[sku] = sku_signups[sku] / sku_units[sku]

    ltv_rows = []
    if ltv_orders and units_per_order:
        for sku, e in econ.items():
            if not e.get('contribution') or e['contribution'] <= 0:
                continue
            if not e.get('list_price'):
                continue
            a = sku_attach.get(sku, attach or 0.0)
            mult = 1.0 + a * (ltv_orders - 1.0) * units_per_order
            ltv_contrib = e['contribution'] * mult
            be_first = e['list_price'] / e['contribution'] * 100.0
            be_ltv = e['list_price'] / ltv_contrib * 100.0
            realized = None
            if sku_spend.get(sku, 0) > 0:
                # realized ROAS over the whole window, retail basis
                pass
            ltv_rows.append({
                'brand': e['brand'],
                'title': e['title'][:52],
                'chewy_sku': sku,
                'attach_pct': round(a * 100, 1),
                'contribution_first': round(e['contribution'], 4),
                'ltv_multiplier': round(mult, 3),
                'contribution_ltv': round(ltv_contrib, 4),
                'list_price': e['list_price'],
                'be_roas_first_pct': round(be_first, 0),
                'be_roas_ltv_pct': round(be_ltv, 0),
                'be_improvement_pts': round(be_first - be_ltv, 0),
                'spend_alltime': round(sku_spend.get(sku, 0.0), 2),
                'direct_units_alltime': round(sku_units.get(sku, 0.0), 0),
                'signups_alltime': round(sku_signups.get(sku, 0.0), 0),
                'ntb_alltime': round(sku_ntb.get(sku, 0.0), 0),
            })
        ltv_rows.sort(key=lambda r: -r['spend_alltime'])

        p = os.path.join(HERE, 'chewy_ltv_cohorts.csv')
        with io.open(p, 'w', encoding='utf-8-sig', newline='') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(ltv_rows[0].keys()))
            wr.writeheader()
            wr.writerows(ltv_rows)
        w('')
        w('wrote %s (%d rows)' % (p, len(ltv_rows)))

        w('')
        w('Per-SKU break-even: first purchase vs lifetime (top 20 by spend)')
        w('%-40s %7s %8s %8s %8s %7s' % ('PRODUCT', 'ATTACH', 'BE 1st', 'BE LTV',
                                         'BETTER', 'SPEND'))
        for r in ltv_rows[:20]:
            w('%-40s %6.1f%% %7.0f%% %7.0f%% %7.0f %7s' % (
                r['title'][:40], r['attach_pct'], r['be_roas_first_pct'],
                r['be_roas_ltv_pct'], r['be_improvement_pts'],
                money % r['spend_alltime']))

    # ============================================= PART 2: ACCOUNT EFFICIENCY

    w('')
    w('=' * 78)
    w('PART 2  ACCOUNT-LEVEL PROGRAM EFFICIENCY')
    w('=' * 78)

    # Contribution dollars on TOTAL sell-through, per month, from per-SKU units.
    sell_by_mo = defaultdict(lambda: defaultdict(float))
    contrib_by_mo = defaultdict(float)
    priced_units_by_mo = defaultdict(float)
    for r in sell_sku:
        m = r['mo']
        sku = (r.get('chewy_sku') or '').strip()
        u = f(r.get('units_sold'))
        sell_by_mo[m]['units_sold'] += u
        sell_by_mo[m]['autoship_units'] += f(r.get('autoship_units'))
        sell_by_mo[m]['merch_sales'] += f(r.get('merch_sales'))
        e = econ.get(sku)
        if e and e.get('contribution') is not None:
            contrib_by_mo[m] += u * e['contribution']
            priced_units_by_mo[m] += u

    ads_units_by_mo = defaultdict(float)
    ads_spend_by_mo = defaultdict(float)
    ads_ntb_by_mo = defaultdict(float)
    for r in ads_sku:
        m = r['mo']
        ads_units_by_mo[m] += f(r.get('direct_units'))
        ads_spend_by_mo[m] += f(r.get('spend'))
        ads_ntb_by_mo[m] += f(r.get('ntb_customers'))

    # Only months where BOTH feeds have data are comparable. Sell-through runs
    # about two months behind the ad report, so the tail would read as a
    # collapse in organic volume if it were left in.
    both = sorted(set(sell_by_mo.keys()) & set(ads_units_by_mo.keys()))
    sell_only = sorted(set(sell_by_mo.keys()) - set(ads_units_by_mo.keys()))
    ads_only = sorted(set(ads_units_by_mo.keys()) - set(sell_by_mo.keys()))

    w('')
    w('Coverage')
    w('  sell-through months      %s -> %s (%d)' % (
        min(sell_by_mo) if sell_by_mo else '-', max(sell_by_mo) if sell_by_mo else '-',
        len(sell_by_mo)))
    w('  ad-report months         %s -> %s (%d)' % (
        min(ads_units_by_mo) if ads_units_by_mo else '-',
        max(ads_units_by_mo) if ads_units_by_mo else '-', len(ads_units_by_mo)))
    w('  comparable (both)        %d months' % len(both))
    if ads_only:
        w('  ads but no sell-through  %s  <- sell-through feed lags' % ', '.join(ads_only))
    if sell_only:
        w('  sell-through but no ads  %s' % ', '.join(sell_only))

    acct_rows = []
    w('')
    w('Account-level monthly (comparable months only)')
    w('%-9s %9s %9s %9s %7s %12s %11s %11s %7s' % (
        'MONTH', 'TOT UNITS', 'AD UNITS', 'ORGANIC', 'AD SH%',
        'RETAIL $', 'CONTRIB $', 'AD SPEND', 'TACOS'))
    for m in both:
        tu = sell_by_mo[m]['units_sold']
        au = ads_units_by_mo[m]
        org = tu - au
        retail = sell_by_mo[m]['merch_sales']
        contrib = contrib_by_mo[m]
        spend = ads_spend_by_mo[m]
        ad_share = (au / tu * 100) if tu > 0 else 0.0
        tacos = (spend / retail * 100) if retail > 0 else 0.0
        net = contrib - spend
        w('%-9s %9.0f %9.0f %9.0f %6.1f%% %12s %11s %11s %6.1f%%' % (
            m, tu, au, org, ad_share,
            money % retail, money % contrib, money % spend, tacos))
        acct_rows.append({
            'month': m,
            'total_units': round(tu, 0),
            'ad_attributed_units': round(au, 0),
            'organic_units': round(org, 0),
            'ad_share_pct': round(ad_share, 1),
            'autoship_units': round(sell_by_mo[m]['autoship_units'], 0),
            'autoship_share_pct': round(sell_by_mo[m]['autoship_units'] / tu * 100, 1) if tu > 0 else 0,
            'retail_sell_through': round(retail, 2),
            'our_contribution': round(contrib, 2),
            'ad_spend': round(spend, 2),
            'program_net': round(net, 2),
            'tacos_pct': round(tacos, 1),
            'ntb_customers': round(ads_ntb_by_mo[m], 0),
            'contribution_per_unit_priced': round(contrib / priced_units_by_mo[m], 4) if priced_units_by_mo[m] > 0 else None,
        })

    if acct_rows:
        tu = sum(r['total_units'] for r in acct_rows)
        au = sum(r['ad_attributed_units'] for r in acct_rows)
        retail = sum(r['retail_sell_through'] for r in acct_rows)
        contrib = sum(r['our_contribution'] for r in acct_rows)
        spend = sum(r['ad_spend'] for r in acct_rows)
        w('%-9s %9.0f %9.0f %9.0f %6.1f%% %12s %11s %11s %6.1f%%' % (
            'TOTAL', tu, au, tu - au, (au / tu * 100) if tu else 0,
            money % retail, money % contrib, money % spend,
            (spend / retail * 100) if retail else 0))

        w('')
        w('Program verdict over the comparable window')
        w('  total contribution       ' + (money % contrib))
        w('  total ad spend           ' + (money % spend))
        w('  program net              ' + (money % (contrib - spend)))
        w('  spend as %% of contrib    %.1f%%' % (spend / contrib * 100 if contrib else 0))
        w('  ad-attributed share      %.1f%% of units' % ((au / tu * 100) if tu else 0))
        w('  organic share            %.1f%% of units' % (((tu - au) / tu * 100) if tu else 0))

        p = os.path.join(HERE, 'chewy_account_monthly.csv')
        with io.open(p, 'w', encoding='utf-8-sig', newline='') as fh:
            wr = csv.DictWriter(fh, fieldnames=list(acct_rows[0].keys()))
            wr.writeheader()
            wr.writerows(acct_rows)
        w('')
        w('wrote %s (%d rows)' % (p, len(acct_rows)))

        # ---- NTB -> organic lift, lag correlation ----
        w('')
        w('NTB acquisition vs organic volume (does paid seed organic?)')
        ntb = [r['ntb_customers'] for r in acct_rows]
        org = [r['organic_units'] for r in acct_rows]
        for lag in (0, 1, 2, 3):
            xs = ntb[:len(ntb) - lag] if lag else ntb
            ys = org[lag:] if lag else org
            n = min(len(xs), len(ys))
            xs, ys = xs[:n], ys[:n]
            if n < 4:
                w('  lag %dmo  n=%d  too few months to correlate' % (lag, n))
                continue
            mx = sum(xs) / n
            my = sum(ys) / n
            cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
            vx = sum((x - mx) ** 2 for x in xs)
            vy = sum((y - my) ** 2 for y in ys)
            r = cov / ((vx * vy) ** 0.5) if vx > 0 and vy > 0 else 0.0
            w('  lag %dmo  n=%-3d r=%+.2f' % (lag, n, r))
        w('  (directional only at this n - not a causal estimate)')

    # ---- per-brand rollup over the comparable window ----
    if both:
        w('')
        w('Per-brand over the comparable window')
        bsell = defaultdict(lambda: defaultdict(float))
        for r in sell_mo:
            if r['mo'] in both:
                b = r['brand']
                bsell[b]['units'] += f(r.get('units_sold'))
                bsell[b]['autoship'] += f(r.get('autoship_units'))
                bsell[b]['retail'] += f(r.get('merch_sales'))
        bads = defaultdict(lambda: defaultdict(float))
        for r in ads_mo:
            if r['mo'] in both:
                b = r['brand']
                bads[b]['spend'] += f(r.get('spend'))
                bads[b]['units'] += f(r.get('direct_units'))
                bads[b]['ntb'] += f(r.get('ntb_customers'))
                bads[b]['signups'] += f(r.get('signups'))
        bcontrib = defaultdict(float)
        for r in sell_sku:
            if r['mo'] not in both:
                continue
            e = econ.get((r.get('chewy_sku') or '').strip())
            if e and e.get('contribution') is not None:
                bcontrib[e['brand']] += f(r.get('units_sold')) * e['contribution']

        w('%-16s %9s %9s %7s %11s %11s %11s %7s' % (
            'BRAND', 'TOT UNITS', 'AD UNITS', 'AD SH%', 'CONTRIB $',
            'AD SPEND', 'NET $', 'TACOS'))
        for b in sorted(set(list(bsell.keys()) + list(bads.keys()))):
            tu = bsell[b]['units']
            au = bads[b]['units']
            c = bcontrib.get(b, 0.0)
            s = bads[b]['spend']
            retail = bsell[b]['retail']
            w('%-16s %9.0f %9.0f %6.1f%% %11s %11s %11s %6.1f%%' % (
                b[:16], tu, au, (au / tu * 100) if tu else 0,
                money % c, money % s, money % (c - s),
                (s / retail * 100) if retail else 0))

    text = '\n'.join(out)
    # Console is cp1252 on Windows; write to a file and let the caller read it.
    rp = os.path.join(HERE, 'chewy_ltv_account_report.txt')
    io.open(rp, 'w', encoding='utf-8').write(text)
    print('wrote %s' % rp)
    try:
        print(text)
    except Exception:
        print('(report written to file - console encoding could not print it)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
