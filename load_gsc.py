#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
load_gsc.py - ingest archived Google Search Console pulls into Supabase.

Reads the gsc-data/<YYYY-MM-DD>/ snapshot folders that the two blog repos
already produce and writes them into the gsc_* tables created by
supabase_v10_73_gsc_seo.sql.

The pull scripts and their OAuth tokens STAY in the blog repos where they
already work. This loader only reads their output folders by path. Nothing
about the daily pull changes.

----------------------------------------------------------------------------
WHY THERE IS AN IMPRESSIONS FLOOR
----------------------------------------------------------------------------
Each pull is a 486-day (16 month) TRAILING WINDOW, not a delta, so consecutive
snapshots overlap almost entirely. On the 2026-10-19 smarterpaw snapshot, 88%
of the 112,657 queries have fewer than 10 impressions across that entire
window. Storing that tail once per snapshot means storing noise 59 times.

Measured across all 109 archived snapshots:

    floor   gsc_query    gsc_query_page    TOTAL
    0       6,323,402     9,844,871        16.26 M
    3       1,691,358     2,746,454         4.53 M
    10        734,270     1,194,433         2.02 M

So the floor is a per-run argument, recorded on every gsc_snapshots row, and
reloading a snapshot at a different floor is the documented way to change it.
Defaults: 10 for smarterpaw, 0 for kittykazoom (whose entire latest snapshot
is 1,019 queries and would be gutted by any floor at all).

----------------------------------------------------------------------------
A LIMITATION WORTH KNOWING BEFORE YOU TRUST avg_position
----------------------------------------------------------------------------
Because each pull is a 16 month aggregate, avg_position is a 16 month MEAN.
Two snapshots three months apart overlap by ~13 months, so a real ranking move
is damped roughly 5:1 in the comparison. Good enough for long-run trend, the
complete query universe, and cannibalisation mapping. NOT sharp enough to call
a week-over-week position change. The fix is a short-window (e.g. 28 day) pull
added alongside the existing one in the blog repos; that is a separate change.

----------------------------------------------------------------------------
CREDENTIALS
----------------------------------------------------------------------------
The gsc_* tables are authenticated-only with anon revoked (the v6.47 house
rule), so this signs in as a real user and uses that token, exactly as the
dashboard does. Put your dashboard login in a .env next to this file (already
gitignored):

    SUPABASE_EMAIL=jnesbitt@meowijuana.com
    SUPABASE_PASSWORD=<your dashboard password>

That is all that is needed. SUPABASE_URL and the anon key default to this
project's, and the anon key is public by design (it ships inside index.html).

A service_role key ALSO works if SUPABASE_SERVICE_KEY is set, but it is not
the recommended path here: this project grants new tables to `authenticated`
only, so service_role has no grants on them without an extra migration, and
that key bypasses RLS on every table in the database.

----------------------------------------------------------------------------
USAGE
----------------------------------------------------------------------------
    python load_gsc.py --dry-run                  # parse + report, write nothing
    python load_gsc.py --check                    # verify credentials, write nothing
    python load_gsc.py --only 2026-10-19          # one snapshot, both properties
    python load_gsc.py --property smarterpaw      # everything for one property
    python load_gsc.py --sample weekly            # thin the backfill to 1/week
    python load_gsc.py --floor 3                  # override the per-property floor
    python load_gsc.py --force --only 2026-10-19  # reload a snapshot already loaded
"""
import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

PROPERTIES = OrderedDict([
    ('smarterpaw', {
        'dir':      r'C:\Users\Jason\smarterpaw-blog\gsc-data',
        'site_url': 'sc-domain:smarterpaw.com',
        'floor':    10,
    }),
    ('kittykazoom', {
        'dir':      r'C:\Users\Jason\kitty-kazoom-blog\gsc-data',
        'site_url': 'sc-domain:kittykazoom.com',
        # KK's whole latest snapshot is ~1,019 queries. Any floor guts it.
        'floor':    0,
    }),
])

# csv filename -> (table, dimension columns, does the floor apply?)
FILES = OrderedDict([
    ('queries.csv',        ('gsc_query',      ['query'],         True)),
    ('pages.csv',          ('gsc_page',       ['page'],          False)),
    ('queries_by_page.csv',('gsc_query_page', ['query', 'page'], True)),
])


# --------------------------------------------------------------------------- env
# This project's own public anon key, the same one index.html ships. It grants
# nothing on its own; it only identifies the project so the auth endpoint will
# answer. Every gsc_* table has anon revoked.
DEFAULT_URL = 'https://yjcnuyoaemlipvuinptp.supabase.co'
DEFAULT_ANON = ('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.'
                'eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlqY251eW9hZW1saXB2dWlucHRwIiwicm9sZSI6'
                'ImFub24iLCJpYXQiOjE3NzgyNTY4NjcsImV4cCI6MjA5MzgzMjg2N30.'
                'CACwOGjnC370ZPjKlXG4dDpU9bVwCP4JDBD451WvwaM')


def load_env():
    """Read .env next to this file, without clobbering real env vars."""
    path = os.path.join(HERE, '.env')
    if os.path.isfile(path):
        # utf-8-sig: Notepad writes a BOM, which would otherwise land inside
        # the first key's name and make it unreadable.
        for line in io.open(path, encoding='utf-8-sig'):
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    url = (os.environ.get('SUPABASE_URL') or DEFAULT_URL).rstrip('/')
    anon = os.environ.get('SUPABASE_ANON_KEY') or DEFAULT_ANON
    svc = os.environ.get('SUPABASE_SERVICE_KEY', '')
    email = os.environ.get('SUPABASE_EMAIL', '')
    pw = os.environ.get('SUPABASE_PASSWORD', '')
    return url, anon, svc, email, pw


def sign_in(url, anon, email, pw):
    """Exchange email+password for an access token with the `authenticated`
    role, which is what the gsc_* grants are written against."""
    req = urllib.request.Request(
        '%s/auth/v1/token?grant_type=password' % url,
        data=json.dumps({'email': email, 'password': pw}).encode('utf-8'),
        method='POST')
    req.add_header('apikey', anon)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            tok = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:300]
        raise RuntimeError('sign-in failed (HTTP %s): %s' % (e.code, detail))
    if not tok.get('access_token'):
        raise RuntimeError('sign-in returned no access_token')
    return tok['access_token']


# ------------------------------------------------------------------------ parsing
def parse_pct(v):
    """GSC writes ctr as the string '10.23%'."""
    if v is None:
        return None
    v = str(v).strip().replace('%', '')
    if not v:
        return None
    try:
        return round(float(v), 4)
    except ValueError:
        return None


def parse_num(v, cast=int):
    if v is None or str(v).strip() == '':
        return 0 if cast is int else None
    try:
        return cast(float(str(v).strip()))
    except ValueError:
        return 0 if cast is int else None


def read_csv(path):
    """csv.DictReader, because query text legitimately contains commas and GSC
    quotes those fields. Splitting on ',' corrupts roughly 1 row in 200."""
    if not os.path.isfile(path):
        return []
    with io.open(path, encoding='utf-8', errors='replace', newline='') as f:
        return list(csv.DictReader(f))


def parse_dimension_file(path, dims, floor):
    """Return (rows, stats). Dedupes on the dimension tuple because the table's
    primary key is (snapshot_id, <dims>); a duplicate would abort the insert."""
    raw = read_csv(path)
    seen = {}
    dropped_floor = dupes = skipped = 0
    for r in raw:
        key = tuple((r.get(d) or '').strip() for d in dims)
        if not all(key):
            skipped += 1
            continue
        imp = parse_num(r.get('impressions'))
        if floor and imp < floor:
            dropped_floor += 1
            continue
        row = {
            'clicks':       parse_num(r.get('clicks')),
            'impressions':  imp,
            'ctr_pct':      parse_pct(r.get('ctr')),
            'avg_position': parse_num(r.get('position'), float),
        }
        for d, v in zip(dims, key):
            row[d] = v
        if key in seen:
            dupes += 1
            # keep the larger-impression copy rather than last-wins
            if imp > seen[key]['impressions']:
                seen[key] = row
        else:
            seen[key] = row
    return list(seen.values()), {
        'raw': len(raw), 'kept': len(seen),
        'floored': dropped_floor, 'dupes': dupes, 'skipped': skipped,
    }


def parse_by_date(path):
    rows, seen = [], set()
    for r in read_csv(path):
        d = (r.get('date') or '').strip()
        if not d or d in seen:
            continue
        seen.add(d)
        rows.append({
            'day':          d,
            'clicks':       parse_num(r.get('clicks')),
            'impressions':  parse_num(r.get('impressions')),
            'ctr_pct':      parse_pct(r.get('ctr')),
            'avg_position': parse_num(r.get('position'), float),
        })
    rows.sort(key=lambda x: x['day'])
    return rows


# ---------------------------------------------------------------------- transport
class Supa(object):
    def __init__(self, url, key, dry=False, apikey=None):
        self.url, self.key, self.dry = url, key, dry
        # With a user token the apikey header stays the ANON key while the
        # bearer carries the user's JWT; with service_role both are the same.
        self.apikey = apikey or key
        self.writes = 0

    def _req(self, method, path, body=None, prefer=None, tries=4):
        url = '%s/rest/v1/%s' % (self.url, path)
        data = json.dumps(body).encode('utf-8') if body is not None else None
        last = None
        for attempt in range(tries):
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header('apikey', self.apikey)
            req.add_header('Authorization', 'Bearer %s' % self.key)
            req.add_header('Content-Type', 'application/json')
            if prefer:
                req.add_header('Prefer', prefer)
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    txt = resp.read().decode('utf-8') or '[]'
                    return json.loads(txt) if txt.strip().startswith(('[', '{')) else txt
            except urllib.error.HTTPError as e:
                detail = e.read().decode('utf-8', 'replace')[:600]
                last = 'HTTP %s %s' % (e.code, detail)
                # 4xx other than 429 will not fix themselves
                if e.code < 500 and e.code != 429:
                    raise RuntimeError(last)
            except Exception as e:
                last = repr(e)
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError('%s %s failed after %d tries: %s' % (method, path, tries, last))

    def get(self, path):
        return self._req('GET', path)

    def insert(self, table, rows, batch=1000, upsert_on=None):
        if self.dry:
            self.writes += len(rows)
            return
        prefer = 'return=minimal'
        if upsert_on:
            prefer = 'resolution=merge-duplicates,return=minimal'
        path = table
        if upsert_on:
            path = '%s?on_conflict=%s' % (table, upsert_on)
        for i in range(0, len(rows), batch):
            self._req('POST', path, rows[i:i + batch], prefer=prefer)
            self.writes += len(rows[i:i + batch])

    def insert_one_returning(self, table, row):
        if self.dry:
            self.writes += 1
            return {'id': -1}
        out = self._req('POST', table, [row], prefer='return=representation')
        return out[0] if isinstance(out, list) and out else {}


# ----------------------------------------------------------------------- sampling
def iso_week(d):
    y, w, _ = datetime.strptime(d, '%Y-%m-%d').isocalendar()
    return '%04d-W%02d' % (y, w)


def apply_sample(dates, mode):
    """Consecutive daily snapshots of a 16 month window are near-duplicates, so
    thinning the backfill costs very little information. Keeps the LAST snapshot
    in each bucket (the freshest data for that period)."""
    if mode == 'all':
        return list(dates)
    keyfn = iso_week if mode == 'weekly' else (lambda d: d[:7])
    buckets = OrderedDict()
    for d in sorted(dates):
        buckets[keyfn(d)] = d
    return list(buckets.values())


# --------------------------------------------------------------------------- main
def discover(prop_dir):
    if not os.path.isdir(prop_dir):
        return []
    out = []
    for name in sorted(os.listdir(prop_dir)):
        full = os.path.join(prop_dir, name)
        if not os.path.isdir(full):
            continue
        try:
            datetime.strptime(name, '%Y-%m-%d')
        except ValueError:
            continue
        if os.path.isfile(os.path.join(full, 'queries.csv')):
            out.append(name)
    return out


def main():
    ap = argparse.ArgumentParser(description='Load archived GSC pulls into Supabase.')
    ap.add_argument('--property', action='append', choices=list(PROPERTIES),
                    help='limit to one property (repeatable); default is all')
    ap.add_argument('--only', action='append', help='load only this snapshot date (repeatable)')
    ap.add_argument('--since', help='skip snapshots before this date')
    ap.add_argument('--floor', type=int, help='override the per-property impressions floor')
    ap.add_argument('--sample', choices=['all', 'weekly', 'monthly'], default='all',
                    help='thin the backfill; weekly/monthly keep the last snapshot per bucket')
    ap.add_argument('--batch', type=int, default=1000, help='rows per insert (default 1000)')
    ap.add_argument('--force', action='store_true', help='reload snapshots already present')
    ap.add_argument('--dry-run', action='store_true', help='parse and report, write nothing')
    ap.add_argument('--check', action='store_true', help='verify credentials and exit')
    a = ap.parse_args()

    url, anon, svc, email, pw = load_env()
    key, apikey, mode = '', '', ''
    if not a.dry_run:
        if email and pw:
            # Preferred: the same `authenticated` role the dashboard uses, which
            # is what this project grants new tables to.
            try:
                key = sign_in(url, anon, email, pw)
            except Exception as e:
                print('ERROR: %s' % e)
                return 2
            apikey, mode = anon, 'user (%s)' % email
        elif svc:
            key, apikey, mode = svc, svc, 'service_role'
        else:
            print('ERROR: no credentials. Add to %s (gitignored):\n'
                  '         SUPABASE_EMAIL=you@example.com\n'
                  '         SUPABASE_PASSWORD=your dashboard password\n'
                  '       Or re-run with --dry-run to validate parsing without credentials.'
                  % os.path.join(HERE, '.env'))
            return 2
        print('auth: %s' % mode)

    sb = Supa(url, key, dry=a.dry_run, apikey=apikey)

    if a.check:
        try:
            sb.get('gsc_snapshots?select=property,snapshot_date&limit=1')
            print('OK: credentials work and gsc_snapshots is readable.')
            return 0
        except Exception as e:
            print('FAILED: %s' % e)
            return 2
    props = a.property or list(PROPERTIES)

    # existing (property, snapshot_date) -> floor, so re-runs are idempotent
    existing = {}
    if not a.dry_run:
        try:
            for r in sb.get('gsc_snapshots?select=property,snapshot_date,impressions_floor'):
                existing[(r['property'], str(r['snapshot_date']))] = r['impressions_floor']
        except Exception as e:
            print('ERROR reading gsc_snapshots: %s' % e)
            print('       Has supabase_v10_73_gsc_seo.sql been run?')
            return 2

    grand = {'snapshots': 0, 'skipped': 0, 'rows': 0, 'floored': 0, 'dupes': 0}

    for prop in props:
        cfg = PROPERTIES[prop]
        floor = a.floor if a.floor is not None else cfg['floor']
        dates = discover(cfg['dir'])
        if a.only:
            dates = [d for d in dates if d in set(a.only)]
        if a.since:
            dates = [d for d in dates if d >= a.since]
        dates = apply_sample(dates, a.sample)

        print('\n%s  (%s)' % (prop, cfg['site_url']))
        print('  dir    %s' % cfg['dir'])
        print('  floor  %d   sample %s   snapshots %d' % (floor, a.sample, len(dates)))
        if not dates:
            print('  nothing to do')
            continue

        # oldest first so the newest pull wins the gsc_by_date upsert
        for d in dates:
            prev = existing.get((prop, d))
            if prev is not None and not a.force:
                print('  %s  skip (already loaded at floor %s)' % (d, prev))
                grand['skipped'] += 1
                continue

            folder = os.path.join(cfg['dir'], d)
            parsed, stats = {}, {}
            for fname, (table, dims, use_floor) in FILES.items():
                rows, st = parse_dimension_file(
                    os.path.join(folder, fname), dims, floor if use_floor else 0)
                parsed[table] = (rows, dims)
                stats[table] = st
            bydate = parse_by_date(os.path.join(folder, 'by_date.csv'))

            nq = stats['gsc_query']['kept']
            npg = stats['gsc_page']['kept']
            nqp = stats['gsc_query_page']['kept']
            fl = stats['gsc_query']['floored'] + stats['gsc_query_page']['floored']
            du = sum(s['dupes'] for s in stats.values())

            snap = {
                'property': prop, 'site_url': cfg['site_url'], 'snapshot_date': d,
                'window_start': bydate[0]['day'] if bydate else None,
                'window_end':   bydate[-1]['day'] if bydate else None,
                'impressions_floor': floor,
                'query_rows': nq, 'page_rows': npg, 'query_page_rows': nqp,
            }

            if a.force and prev is not None and not a.dry_run:
                # FK is ON DELETE CASCADE, so removing the snapshot clears its rows
                sb._req('DELETE', 'gsc_snapshots?property=eq.%s&snapshot_date=eq.%s' % (prop, d))

            rec = sb.insert_one_returning('gsc_snapshots', snap)
            sid = rec.get('id')
            if sid is None:
                print('  %s  ERROR: no snapshot id returned' % d)
                continue

            for table, (rows, dims) in parsed.items():
                if not rows:
                    continue
                for r in rows:
                    r['snapshot_id'] = sid
                    r['property'] = prop
                    r['snapshot_date'] = d
                sb.insert(table, rows, batch=a.batch)

            if bydate:
                for r in bydate:
                    r['property'] = prop
                    r['snapshot_date'] = d
                sb.insert('gsc_by_date', bydate, batch=a.batch,
                          upsert_on='property,day')

            grand['snapshots'] += 1
            grand['rows'] += nq + npg + nqp + len(bydate)
            grand['floored'] += fl
            grand['dupes'] += du
            print('  %s  query %-7d page %-5d query_page %-7d by_date %-4d '
                  '| floored %-7d dupes %-4d' % (d, nq, npg, nqp, len(bydate), fl, du))

    print('\n%s' % ('-' * 72))
    print('%s snapshots loaded %d, skipped %d' %
          ('DRY RUN: ' if a.dry_run else '', grand['snapshots'], grand['skipped']))
    print('rows %s  (floored out %s, in-file dupes collapsed %s)' %
          ('{:,}'.format(grand['rows']), '{:,}'.format(grand['floored']),
           '{:,}'.format(grand['dupes'])))
    if a.dry_run:
        print('nothing was written. drop --dry-run to load for real.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
