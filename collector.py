#!/usr/bin/env python3
"""Scan each configured NAS mount and record today's usage.

Run once a day (cron / systemd timer). Re-running on the same day replaces
that day's numbers, so it is safe to run more often.

  python3 collector.py              # scan all NAS in config.json
  python3 collector.py --nas NAS-01 # scan just one
"""
import argparse
import datetime as dt
import os
import pwd
import sys
import time

from db import connect, load_config


def disk_usage(path):
    st = os.statvfs(path)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = (st.f_blocks - st.f_bfree) * st.f_frsize
    return total, used, free


def walk_size(root, exclude, on_file=None):
    """Iteratively sum file sizes under root. Returns (bytes, files, errors)."""
    total = files = errors = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name in exclude:
                        continue
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            s = e.stat(follow_symlinks=False)
                            total += s.st_size
                            files += 1
                            if on_file:
                                on_file(s)
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return total, files, errors


def usage_by_folder(user_root, exclude):
    """Each top-level folder under user_root counts as one user."""
    result, errors = {}, 0
    loose_bytes = loose_files = 0
    with os.scandir(user_root) as it:
        entries = list(it)
    for e in entries:
        if e.name in exclude:
            continue
        try:
            if e.is_dir(follow_symlinks=False):
                b, f, err = walk_size(e.path, exclude)
                result[e.name] = (b, f)
                errors += err
            elif e.is_file(follow_symlinks=False):
                loose_bytes += e.stat(follow_symlinks=False).st_size
                loose_files += 1
        except OSError:
            errors += 1
    if loose_files:
        result["(files in root)"] = (loose_bytes, loose_files)
    return result, errors


def usage_by_owner(root, exclude):
    """Group by file owner (UID). Needs a mount that preserves ownership (NFS, or SMB with unix extensions)."""
    acc = {}

    def add(s):
        b, f = acc.get(s.st_uid, (0, 0))
        acc[s.st_uid] = (b + s.st_size, f + 1)

    _, _, errors = walk_size(root, exclude, on_file=add)
    result = {}
    for uid, v in acc.items():
        try:
            name = pwd.getpwuid(uid).pw_name
        except KeyError:
            name = f"uid:{uid}"
        result[name] = v
    return result, errors


def scan(nas, conn, day):
    name, path = nas["name"], nas["path"]
    exclude = set(nas.get("exclude", []))
    if not os.path.isdir(path):
        print(f"[{name}] SKIP: {path} is not mounted / not a directory", file=sys.stderr)
        return False
    if not os.path.ismount(path):
        print(f"[{name}] WARNING: {path} is not a mount point; numbers reflect the local disk", file=sys.stderr)

    t0 = time.time()
    total, used, free = disk_usage(path)
    mode = nas.get("user_mode", "folders")
    root = nas.get("user_root", path)
    if mode == "owner":
        users, errors = usage_by_owner(root, exclude)
    else:
        users, errors = usage_by_folder(root, exclude)
    secs = time.time() - t0

    with conn:
        conn.execute("DELETE FROM user_usage WHERE day=? AND nas=?", (day, name))
        conn.executemany(
            "INSERT INTO user_usage (day, nas, user, bytes, files) VALUES (?,?,?,?,?)",
            [(day, name, u, b, f) for u, (b, f) in users.items()],
        )
        conn.execute(
            "INSERT OR REPLACE INTO nas_snapshot VALUES (?,?,?,?,?,?,?,?)",
            (day, name, total, used, free, dt.datetime.now().isoformat(timespec="seconds"), secs, errors),
        )
    print(f"[{name}] {used/1024**4:.2f}/{total/1024**4:.2f} TB used, {len(users)} users, "
          f"{errors} unreadable entries, {secs:.0f}s")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--nas", help="only scan this NAS name")
    ap.add_argument("--day", help="record under this date (YYYY-MM-DD); default today")
    args = ap.parse_args()

    cfg = load_config(args.config)
    conn = connect(cfg["db"])
    day = args.day or dt.date.today().isoformat()
    ok = True
    for nas in cfg["nas"]:
        if args.nas and nas["name"] != args.nas:
            continue
        ok &= scan(nas, conn, day)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
