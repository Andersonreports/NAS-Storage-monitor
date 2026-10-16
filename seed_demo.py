#!/usr/bin/env python3
"""Fill data/demo.db with 120 days of realistic fake data for every NAS marked
"demo": true in config.json. Remove that flag once the real collector runs for it.

  python3 seed_demo.py
"""
import datetime as dt
import os
import random

from db import DEMO_DB, connect, load_config

TB = 1024 ** 4
GB = 1024 ** 3
FOLDERS = ["pacs-images", "radiology", "backup", "lab-reports", "marketing", "it", "scans", "archive"]


def main():
    cfg = load_config()
    if os.path.exists(DEMO_DB):
        os.remove(DEMO_DB)
    conn = connect(DEMO_DB)
    rnd = random.Random(42)
    today = dt.date.today()
    for nas in [n for n in cfg["nas"] if n.get("demo")]:
        name, total = nas["name"], nas.get("capacity_bytes") or 16 * TB
        size = {u: rnd.uniform(40, 900) * GB for u in FOLDERS}
        growth = {u: rnd.uniform(-0.5, 12) * GB for u in FOLDERS}
        avg_file = {u: rnd.uniform(0.5, 8) * 1024 ** 2 for u in FOLDERS}
        size["pacs-images"], growth["pacs-images"] = 0.34 * total, 0.0017 * total
        overhead = 0.04 * total
        for i in range(120, -1, -1):
            day = (today - dt.timedelta(days=i)).isoformat()
            for u in FOLDERS:
                size[u] = max(1 * GB, size[u] + growth[u] * rnd.uniform(0.2, 1.8))
                if rnd.random() < 0.02 and size[u] < TB:  # occasional cleanup
                    size[u] *= rnd.uniform(0.75, 0.92)
            used = int(sum(size.values()) + overhead)
            conn.executemany("INSERT INTO user_usage VALUES (?,?,?,?,?)",
                             [(day, name, u, int(b), int(b / avg_file[u])) for u, b in size.items()])
            conn.execute("INSERT INTO nas_snapshot VALUES (?,?,?,?,?,?,?,?)",
                         (day, name, total, used, total - used, f"{day}T01:30:00", 600.0, 0))
        print(f"Demo data for {name}")
    conn.commit()


if __name__ == "__main__":
    main()
