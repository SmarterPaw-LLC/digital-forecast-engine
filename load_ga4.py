#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
load_ga4.py - ingest GA4 pull folders into Supabase.

Reads the ga4-data/<YYYY-MM-DD>/ snapshot folders that smarterpaw-blog/ga4_pull.py
produces and writes them into the ga4_* tables created by
supabase_v11_36_ga4.sql.

The pull script and its OAuth token STAY in smarterpaw-blog where they already
work; this loader only reads their output folders by path. That is the same
split supabase_v10_73_gsc_seo.sql established for GSC, and the `property`
vocabulary is deliberately identical ('smarterpaw', 'kittykazoom') so one
picker can drive both feeds.

----------------------------------------------------------------------------
THE CONNECTION IS load_gsc.py's
----------------------------------------------------------------------------
Supa / sign_in / load_env are imported, not re-implemented. One credential
path, one retry policy, one place where the `authenticated` role is obtained.
A second copy would be a second thing to fix when Supabase changes.

----------------------------------------------------------------------------
UPSERT, NOT APPEND
----------------------------------------------------------------------------
Every ga4_* series table is keyed on (property, <grain>) and upserted, so
re-running a backfill is free rather than duplicating 195k rows. GA4 settles a
day within ~48h and does not restate, which is why these are not snapshot-
scoped the way gsc_query is. `snapshot_date` records which pull last wrote each
row, so provenance survives without a row per pull.

----------------------------------------------------------------------------
by_source_medium.csv IS DELIBERATELY NOT LOADED
----------------------------------------------------------------------------
It is a PERIOD AGGREGATE with no date column, so loading it would put a figure
in the database whose window is whatever the last pull happened to use - the
v11.22 trap. Channel group is the rolled-up version of the same thing and IS at
date grain. The file is still written for ad-hoc work.

----------------------------------------------------------------------------
USAGE
----------------------------------------------------------------------------
    python load_ga4.py --check                 # verify credentials + tables
    python load_ga4.py --dry-run               # parse + report, write nothing
    python load_ga4.py                         # load the newest snapshot
    python load_ga4.py --only 2026-11-02       # one snapshot by folder name
    python load_ga4.py --all                   # every snapshot, oldest first
    python load_ga4.py --dir "C:\\path\\to\\ga4-data"
"""
from __future__ import print_function

import argparse
import csv
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# One connection implementation, shared with the GSC loader.
from load_gsc import Supa, sign_in, load_env  # noqa: E402

DEFAULT_GA4_DIR = r"C:\Users\Jason\smarterpaw-blog\ga4-data"
PROPERTY = "smarterpaw"

INT_COLS = ("sessions", "total_users", "new_users", "engaged_sessions",
            "transactions", "purchasers", "key_events")
NUM_COLS = ("revenue",)

# file -> (table, conflict key, dimension columns)
REPORTS = [
    ("by_date.csv",              "ga4_by_date",              "property,day",                       ("day",)),
    ("by_month.csv",             "ga4_by_month",             "property,month",                     ("month",)),
    ("by_month_channel.csv",     "ga4_by_month_channel",     "property,month,channel",             ("month", "channel")),
    ("by_date_channel.csv",      "ga4_by_date_channel",      "property,day,channel",               ("day", "channel")),
    ("by_date_device.csv",       "ga4_by_date_device",       "property,day,device",                ("day", "device")),
    ("by_date_landing_page.csv", "ga4_by_date_landing_page", "property,day,landing_page,channel",  ("day", "landing_page", "channel")),
]

# meta.json row_counts key -> ga4_snapshots column
SNAP_COUNTS = {
    "by_date.csv": "date_rows",
    "by_month.csv": "month_rows",
    "by_date_channel.csv": "channel_rows",
    "by_date_device.csv": "device_rows",
    "by_date_landing_page.csv": "page_rows",
}


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(v, cast):
    """GA4 writes '' for a metric it has no value for. That is not zero in
    general, but every metric here is an accumulated count or sum, so an absent
    one genuinely is 0 - and the column is NOT NULL."""
    if v is None:
        return 0
    v = str(v).strip()
    if not v:
        return 0
    try:
        return cast(float(v))
    except ValueError:
        return 0


def build_rows(path, dims, snapshot_date):
    """CSV headers were written to match the table columns exactly, so the
    mapping is identity plus provenance. A header that does not match is a
    REFUSAL, not a silently dropped column."""
    raw = read_csv(path)
    if not raw:
        return []
    have = set(raw[0].keys())
    missing = [d for d in dims if d not in have]
    if missing:
        raise RuntimeError("%s is missing dimension column(s) %s; got %s"
                           % (os.path.basename(path), missing, sorted(have)))
    metrics = [c for c in have if c not in dims]
    unknown = [c for c in metrics if c not in INT_COLS + NUM_COLS]
    if unknown:
        raise RuntimeError("%s carries unknown column(s) %s - the pull and this "
                           "loader have drifted apart"
                           % (os.path.basename(path), sorted(unknown)))
    out = []
    for r in raw:
        row = {"property": PROPERTY, "snapshot_date": snapshot_date}
        for d in dims:
            row[d] = (r.get(d) or "")
        for c in metrics:
            row[c] = num(r.get(c), float if c in NUM_COLS else int)
        out.append(row)
    return out


def discover(ga4_dir):
    if not os.path.isdir(ga4_dir):
        raise RuntimeError("no such folder: %s" % ga4_dir)
    return sorted(d for d in os.listdir(ga4_dir)
                  if os.path.isdir(os.path.join(ga4_dir, d))
                  and len(d) == 10 and d[4] == "-" and d[7] == "-")


def load_snapshot(sb, folder, snapshot_date, dry):
    meta_path = os.path.join(folder, "meta.json")
    meta = {}
    if os.path.isfile(meta_path):
        meta = json.load(io.open(meta_path, encoding="utf-8"))

    print("  snapshot %s" % snapshot_date)
    if meta:
        print("    window %s .. %s  (pulled %s)"
              % (meta.get("window_start"), meta.get("window_end"), meta.get("pulled_at")))

    total = 0
    for fname, table, conflict, dims in REPORTS:
        p = os.path.join(folder, fname)
        if not os.path.isfile(p):
            print("    %-28s MISSING - skipped" % fname)
            continue
        rows = build_rows(p, dims, snapshot_date)
        t0 = time.time()
        sb.insert(table, rows, batch=2000, upsert_on=conflict)
        total += len(rows)
        print("    %-28s %7d rows -> %-26s %5.1fs"
              % (fname, len(rows), table, time.time() - t0))

    snap = {
        "property": PROPERTY,
        "property_id": str(meta.get("property_id") or ""),
        "site": meta.get("site") or "smarterpaw.com",
        "snapshot_date": snapshot_date,
        "window_start": meta.get("window_start"),
        "window_end": meta.get("window_end"),
        "pulled_at": meta.get("pulled_at"),
    }
    for k, col in SNAP_COUNTS.items():
        snap[col] = int((meta.get("row_counts") or {}).get(k) or 0)
    sb.insert("ga4_snapshots", [snap], upsert_on="property,snapshot_date")

    print("    %-28s %7d rows total" % ("", total))
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_GA4_DIR)
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    url, anon, svc, email, pw = load_env()
    if not (email and pw) and not svc:
        sys.exit("Set SUPABASE_EMAIL + SUPABASE_PASSWORD in .env next to this file.")
    key = svc or sign_in(url, anon, email, pw)
    # Supa(url, key, dry, apikey): with a user token the apikey header stays
    # the ANON key while the bearer carries the user's JWT.
    sb = Supa(url, key, dry=args.dry_run, apikey=anon)
    print("signed in as %s" % ("service_role" if svc else email))

    if args.check:
        for _, table, _, _ in REPORTS:
            n = sb.get("%s?select=property&limit=1" % table)
            print("  %-28s reachable (%d row sample)" % (table, len(n)))
        sb.get("ga4_snapshots?select=property&limit=1")
        print("  ga4_snapshots                reachable")
        print("OK - schema is in place.")
        return

    folders = discover(args.dir)
    if not folders:
        sys.exit("no snapshot folders in %s" % args.dir)
    if args.only:
        if args.only not in folders:
            sys.exit("no snapshot %s in %s (have: %s)" % (args.only, args.dir, ", ".join(folders)))
        folders = [args.only]
    elif not args.all:
        folders = folders[-1:]

    print("%s%d snapshot(s) from %s"
          % ("DRY RUN - " if args.dry_run else "", len(folders), args.dir))
    grand = 0
    for d in folders:
        grand += load_snapshot(sb, os.path.join(args.dir, d), d, args.dry_run)

    print("\n%s %d rows across %d snapshot(s)"
          % ("would write" if args.dry_run else "wrote", grand, len(folders)))
    if not args.dry_run:
        for t in ("ga4_by_date", "ga4_by_month", "ga4_by_date_landing_page"):
            n = sb.get("%s?select=property&limit=1" % t)
            print("  %s: readable" % t)


if __name__ == "__main__":
    main()
