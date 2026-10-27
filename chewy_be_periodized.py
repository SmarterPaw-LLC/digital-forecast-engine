#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chewy break-even with PERIOD-MATCHED allowances.

The defect this fixes: chewyPricingDeriveAllowances() takes the most recent
rate per rebate name and applies it flat across all history. But the standing
stack is not static. Agreement 100-17384 carried Damages 2% alone through
P4-26, then gained MDF/Coop 16%, Freight 1.5% and Satisfaction 2% from P5-26
(2026-06-01). Applying 26.50% to 2025 overstates every break-even there.

Produces the two reads that answer different questions:

  CURRENT TERMS   - the rate in force today. Answers "should we advertise
                    this going forward", which is what Blake asked.
  PERIOD-MATCHED  - the revenue-weighted blend actually in force across the
                    spend window. Answers "did the money we already spent
                    pay", which is what realised ROAS is measuring against.

Writes chewy_be_periodized.csv. Prints nothing sensitive.
"""
import os, io, csv, json, datetime, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = 'https://yjcnuyoaemlipvuinptp.supabase.co'
DEFAULT_ANON = ('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.'
                'eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlqY251eW9hZW1saXB2dWlucHRwIiwicm9sZSI6ImFub24i'
                'LCJpYXQiOjE3NzgyNTY4NjcsImV4cCI6MjA5MzgzMjg2N30.'
                'CACwOGjnC370ZPjKlXG4dDpU9bVwCP4JDBD451WvwaM')

# Mirrors CHEWY_STANDING_CATS in index.html.
STANDING = ['trade_allowance', 'autoship', 'damages', 'freight',
            'coop_marketing', 'ad_spend', 'satisfaction_guarantee']
# ad_spend is rated 0% on purpose: the Chewy Onsite Ads invoice line is the
# same money as the per-SKU Promoted Products spend, so rating it here would
# charge it twice.
COGS_PREF = ['chewy_cogs', 'landed_cost', 'dtc_cogs', 'amazon_cogs']

WINDOW_FROM = '2025-10-27'
WINDOW_TO   = '2026-10-27'


def load_env():
    p = os.path.join(HERE, '.env')
    if not os.path.exists(p):
        return
    for line in io.open(p, encoding='utf-8-sig'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def sign_in(url, anon, email, pw):
    req = urllib.request.Request('%s/auth/v1/token?grant_type=password' % url,
                                 data=json.dumps({'email': email, 'password': pw}).encode(),
                                 method='POST')
    req.add_header('apikey', anon); req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=30) as r:
        tok = json.loads(r.read().decode())
    if not tok.get('access_token'):
        raise RuntimeError('sign-in returned no access_token')
    return tok['access_token']


def q(url, anon, token, sql):
    req = urllib.request.Request('%s/rest/v1/rpc/exec_sql' % url,
                                 data=json.dumps({'query': sql.strip()}).encode(), method='POST')
    req.add_header('apikey', anon); req.add_header('Authorization', 'Bearer %s' % token)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError('query failed: %s' % e.read().decode()[:600])


# One row per (agreement period, rebate name) with its rate. Deduped so a
# period invoiced twice cannot double-count its own rate.
SQL_PERIODS = """
select distinct
  r.agreement_no,
  r.agreement_period_label                              as period,
  r.agreement_period_start                              as per_start,
  r.agreement_period_end                                as per_end,
  r.rebate_name,
  r.category,
  r.rebate_pct_rate                                     as rate
from chewy_rebates r
where r.rebate_pct_rate is not null and r.rebate_pct_rate > 0
  and r.agreement_period_start is not null
  and r.agreement_period_end is not null
order by r.agreement_period_start, r.rebate_name
"""

SQL_WEEKLY_REV = """
select s.week_start,
       sum(s.units_sold *
           case when upper(coalesce(cc.purchase_uom,'')) in ('CS','CASE','CA','CTN','CT')
                     and coalesce(p.case_qty,0) > 0 then cc.cost / p.case_qty
                when upper(coalesce(cc.purchase_uom,'')) in ('EA','EACH','UN','UNIT','E')
                     then cc.cost end) as our_rev,
       sum(s.merch_sales) as retail
from chewy_sales_weekly s
join products p       on p.chewy_sku = s.chewy_sku
join chewy_catalog cc on cc.chewy_sku = s.chewy_sku
group by 1 order by 1
"""

SQL_SKUS = """
select p.master_id, p.brand, p.title, p.chewy_sku, p.case_qty,
       cc.cost as catalog_cost, cc.purchase_uom,
       pc.chewy_cogs, pc.landed_cost, pc.dtc_cogs, pc.amazon_cogs
from products p
left join chewy_catalog cc on cc.chewy_sku = p.chewy_sku
left join product_cogs  pc on pc.master_id = p.master_id
where p.chewy_sku is not null and p.chewy_sku <> ''
  and coalesce(p.active, true) = true
order by p.brand, p.title
"""

SQL_ADS = """
select a.chewy_sku,
       sum(a.spend)                      as spend,
       sum(a.impressions)                as impressions,
       sum(a.direct_units)               as direct_units,
       sum(a.direct_sales)               as direct_sales,
       sum(a.autoship_signups)           as signups,
       sum(a.autoship_actualized_orders) as as_orders,
       sum(a.autoship_actualized_sales)  as as_sales,
       case when sum(a.impressions) > 0
            then sum(a.chewy_list_price * a.impressions) / nullif(sum(a.impressions),0)
            else max(a.chewy_list_price) end as list_price
from chewy_ad_spend a
where a.date >= '%s' and a.date <= '%s'
group by 1
""" % (WINDOW_FROM, WINDOW_TO)


def d(s):
    return datetime.date.fromisoformat(str(s)[:10])


def rate_on(periods, day):
    """Standing rate in force on `day`. Sums each distinct rebate name once
    across whichever agreements cover that date."""
    seen, tot = set(), 0.0
    for p in periods:
        if p['cat'] not in STANDING:
            continue
        if p['start'] <= day <= p['end'] and p['name'] not in seen:
            seen.add(p['name']); tot += p['rate']
    return tot, seen


def blend(periods, weeks, frm, to):
    """Revenue-weighted standing rate over [frm, to], plus coverage."""
    num = den = uncovered = 0.0
    for wk, rev in weeks:
        if not (frm <= wk <= to) or not rev:
            continue
        r, _ = rate_on(periods, wk)
        den += rev
        if r > 0:
            num += r * rev
        else:
            uncovered += rev
    covered = den - uncovered
    return {
        'rate': (num / covered) if covered > 0 else None,
        'rev_total': den, 'rev_covered': covered, 'rev_uncovered': uncovered,
        'uncovered_pct': (100.0 * uncovered / den) if den else 0.0,
    }


def price_per_each(cost, uom, case_qty):
    if cost in (None, ''):
        return None
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return None
    if cost <= 0:
        return None
    u = (uom or '').strip().upper()
    if u in ('EA', 'EACH', 'UN', 'UNIT', 'E'):
        return cost
    if u in ('CS', 'CASE', 'CA', 'CTN', 'CT'):
        try:
            qn = int(case_qty)
        except (TypeError, ValueError):
            return None
        return cost / qn if qn > 0 else None
    return None


def main():
    load_env()
    url = (os.environ.get('SUPABASE_URL') or DEFAULT_URL).rstrip('/')
    anon = os.environ.get('SUPABASE_ANON_KEY') or DEFAULT_ANON
    email, pw = os.environ.get('SUPABASE_EMAIL'), os.environ.get('SUPABASE_PASSWORD')
    if not email or not pw:
        print('Missing SUPABASE_EMAIL / SUPABASE_PASSWORD in .env'); return 1
    token = sign_in(url, anon, email, pw)
    print('signed in OK')

    periods = [{'no': r['agreement_no'], 'label': r['period'],
                'start': d(r['per_start']), 'end': d(r['per_end']),
                'name': r['rebate_name'], 'cat': r['category'],
                'rate': float(r['rate'])}
               for r in q(url, anon, token, SQL_PERIODS)]
    weeks = [(d(r['week_start']), float(r['our_rev'] or 0)) for r in q(url, anon, token, SQL_WEEKLY_REV)]
    weeks_retail = [(d(r['week_start']), float(r['retail'] or 0))
             for r in q(url, anon, token, SQL_WEEKLY_REV)]

    print('\n=== STANDING RATE BY AGREEMENT PERIOD ===')
    seen_lbl = []
    for p in sorted(periods, key=lambda x: x['start']):
        key = (p['start'], p['end'])
        if key in seen_lbl:
            continue
        seen_lbl.append(key)
        r, names = rate_on(periods, p['start'])
        print('  %s .. %s  %6.2f%%   %s'
              % (p['start'], p['end'], r, ', '.join(sorted(names))))

    frm, to = d(WINDOW_FROM), d(WINDOW_TO)
    today_rate, today_names = rate_on(periods, max(p['end'] for p in periods))
    b = blend(periods, weeks, frm, to)

    print('\n=== THE TWO READS, window %s .. %s ===' % (WINDOW_FROM, WINDOW_TO))
    print('  CURRENT TERMS    %6.2f%%   (%s)' % (today_rate, ', '.join(sorted(today_names))))
    print('  PERIOD-MATCHED   %6.2f%%   revenue-weighted over invoiced weeks' % (b['rate'] or 0))
    print('  coverage         %6.1f%% of window revenue has NO rebate invoice'
          % b['uncovered_pct'])
    print('                   $%s covered / $%s uncovered'
          % (format(int(b['rev_covered']), ','), format(int(b['rev_uncovered']), ',')))
    print('  as modelled today 26.50%   flat, all history  <- the defect')
    br = blend(periods, weeks_retail, frm, to)
    print('  retail-weighted   %6.2f%%   (sanity check on the simpler weighting)' % (br['rate'] or 0))

    skus = q(url, anon, token, SQL_SKUS)
    ads = {r['chewy_sku']: r for r in q(url, anon, token, SQL_ADS)}

    out = []
    for s in skus:
        whsl = price_per_each(s.get('catalog_cost'), s.get('purchase_uom'), s.get('case_qty'))
        cogs = cogs_src = None
        for f in COGS_PREF:
            if s.get(f) is not None:
                cogs, cogs_src = float(s[f]), f; break
        a = ads.get(s['chewy_sku']) or {}
        spend = float(a.get('spend') or 0)
        lp = float(a['list_price']) if a.get('list_price') not in (None, '') else None
        if not (whsl and cogs is not None and lp and lp > 0):
            continue

        def be(pct):
            c = whsl * (1 - pct / 100.0) - cogs
            return (lp / c * 100.0) if c > 0 else None

        # Realised = direct retail + RECURRING autoship only. First autoship
        # orders already sit inside direct, so counting gross would double them.
        direct = float(a.get('direct_sales') or 0)
        as_sales = float(a.get('as_sales') or 0)
        as_ord = float(a.get('as_orders') or 0)
        signups = float(a.get('signups') or 0)
        recurring = as_sales * max(as_ord - signups, 0) / as_ord if as_ord > 0 else 0.0
        realised = ((direct + recurring) / spend * 100.0) if spend > 0 else None

        out.append({
            'brand': s['brand'], 'title': (s['title'] or '')[:52],
            'chewy_sku': s['chewy_sku'], 'wholesale_each': round(whsl, 4),
            'cogs': round(cogs, 4), 'cogs_source': cogs_src, 'list_price': round(lp, 2),
            'be_current_pct': round(be(today_rate)) if be(today_rate) else None,
            'be_periodmatched_pct': round(be(b['rate'])) if b['rate'] and be(b['rate']) else None,
            'be_asmodelled_pct': round(be(26.5)) if be(26.5) else None,
            'realised_roas_pct': round(realised) if realised else None,
            'spend': round(spend, 2),
            'direct_units': int(float(a.get('direct_units') or 0)),
        })

    p = os.path.join(HERE, 'chewy_be_periodized.csv')
    with io.open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print('\nwrote %s (%d rows)' % (p, len(out)))

    for brand in ('Kitty Ka-Zoom', 'Meowijuana', 'Doggijuana'):
        rows = [r for r in out if r['brand'] == brand and r['spend'] > 0]
        if not rows:
            continue
        print('\n=== %s  (window %s .. %s) ===' % (brand.upper(), WINDOW_FROM, WINDOW_TO))
        print('  %-34s %8s %8s %9s %9s %9s' %
              ('SKU', 'SPEND', 'REALISED', 'BE now', 'BE match', 'BE 26.5'))
        print('  ' + '-' * 80)
        clears_cur = clears_pm = judged = 0
        for r in sorted(rows, key=lambda x: -x['spend']):
            mark = lambda b: ('*' if (r['realised_roas_pct'] and b and r['realised_roas_pct'] >= b) else ' ')
            print('  %-34s %8s %7s%% %8s%%%s %7s%%%s %7s%%' % (
                r['title'][:34], format(int(r['spend']), ','),
                r['realised_roas_pct'] if r['realised_roas_pct'] else '-',
                r['be_current_pct'], mark(r['be_current_pct']),
                r['be_periodmatched_pct'], mark(r['be_periodmatched_pct']),
                r['be_asmodelled_pct']))
            if r['realised_roas_pct'] and r['be_current_pct']:
                judged += 1
                if r['realised_roas_pct'] >= r['be_current_pct']:
                    clears_cur += 1
                if r['be_periodmatched_pct'] and r['realised_roas_pct'] >= r['be_periodmatched_pct']:
                    clears_pm += 1
        print('  %d of %d clear on CURRENT terms  |  %d of %d clear PERIOD-MATCHED'
              % (clears_cur, judged, clears_pm, judged))
    print('\n  * = realised clears break-even at that rate')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
