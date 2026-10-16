#!/usr/bin/env python3
"""Import a department transfer-status sheet (CSV) for one NAS.

  python3 import_transfer.py --nas "CMC NAS" --at "2026-10-07 06:41" imports/cmc_transfer_2026-10-07.csv

Columns: department,share,checked,samples,complete,partial,not_started,pending,no_files,size_gb,copied_gb,pending_gb
Each department with a destination share also becomes a "user" row (its copied GB),
so it shows in the user-wise breakdown and its day-wise history.
"""
import argparse
import csv
import datetime as dt

from db import connect, load_config

GB = 1024 ** 3
INT_COLS = ("samples", "complete", "partial", "not_started", "pending", "no_files")
NUM_COLS = ("size_gb", "copied_gb", "pending_gb")


def num(v, cast):
    v = (v or "").strip().replace(",", "")
    return cast(v) if v and v.lower() != "n/a" else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--nas", required=True)
    ap.add_argument("--at", required=True, help='report time, e.g. "2026-10-07 06:41"')
    ap.add_argument("--config")
    args = ap.parse_args()

    cfg = load_config(args.config)
    nas = next((n for n in cfg["nas"] if n["name"] == args.nas), None)
    if not nas:
        raise SystemExit(f"NAS {args.nas!r} is not in config.json")
    at = dt.datetime.fromisoformat(args.at)
    day = at.date().isoformat()

    with open(args.csv, newline="") as f:
        rows = list(csv.DictReader(f))
    conn = connect(cfg["db"])
    with conn:
        conn.execute("DELETE FROM transfer_status WHERE day=? AND nas=?", (day, args.nas))
        for r in rows:
            vals = {c: num(r.get(c), int) for c in INT_COLS} | {c: num(r.get(c), float) for c in NUM_COLS}
            conn.execute(
                "INSERT INTO transfer_status VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (day, args.nas, r["department"].strip(), (r.get("share") or "").strip() or None, r.get("checked"),
                 *[vals[c] for c in INT_COLS], *[vals[c] for c in NUM_COLS]))
        # only write usage rows if no real scan exists for that day
        scanned = conn.execute("SELECT scan_secs FROM nas_snapshot WHERE day=? AND nas=?", (day, args.nas)).fetchone()
        if not scanned or scanned["scan_secs"] is None:
            users = [(f"{r['department'].strip()} ({r['share'].strip()})" if "user" not in r["department"] else r["department"].strip(),
                      int(num(r["copied_gb"], float) * GB))
                     for r in rows if (r.get("share") or "").strip() and num(r.get("copied_gb"), float) is not None]
            conn.execute("DELETE FROM user_usage WHERE day=? AND nas=?", (day, args.nas))
            conn.executemany("INSERT INTO user_usage (day, nas, user, bytes, files) VALUES (?,?,?,?,NULL)",
                             [(day, args.nas, u, b) for u, b in users])
            used = sum(b for _, b in users)
            cap = nas.get("capacity_bytes")
            conn.execute("INSERT OR REPLACE INTO nas_snapshot VALUES (?,?,?,?,?,?,NULL,0)",
                         (day, args.nas, cap, used, cap - used if cap else None, at.isoformat(timespec="seconds")))
    print(f"Imported {len(rows)} departments for {args.nas} on {day}")


if __name__ == "__main__":
    main()
