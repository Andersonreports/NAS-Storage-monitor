#!/usr/bin/env python3
"""Fill a separate demo database with 120 days of realistic fake data.

  python3 seed_demo.py                       # writes data/demo.db
  NAS_MONITOR_CONFIG=demo_config.json python3 server.py
"""
import datetime as dt
import json
import os
import random

from db import BASE_DIR, connect

TB = 1024 ** 4
GB = 1024 ** 3

DEMO = {
    "NAS-01": (8 * TB, ["accounts", "admin", "billing", "hr", "lab-reports", "it", "purchase", "quality"]),
    "NAS-02": (16 * TB, ["pacs-images", "radiology", "backup", "lab-reports", "marketing", "it", "scans", "archive"]),
}


def main():
    cfg_path = os.path.join(BASE_DIR, "demo_config.json")
    with open(os.path.join(BASE_DIR, "config.json")) as f:
        cfg = json.load(f)
    cfg["db"] = "data/demo.db"
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)

    db_path = os.path.join(BASE_DIR, cfg["db"])
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = connect(db_path)
    rnd = random.Random(42)
    today = dt.date.today()

    for name, (total, users) in DEMO.items():
        size = {u: rnd.uniform(40, 900) * GB for u in users}
        growth = {u: rnd.uniform(-0.5, 12) * GB for u in users}
        avg_file = {u: rnd.uniform(0.5, 8) * 1024 ** 2 for u in users}
        if name == "NAS-02":
            size["pacs-images"] = 5.5 * TB
            growth["pacs-images"] = 28 * GB
        overhead = 0.04 * total
        for i in range(120, -1, -1):
            day = (today - dt.timedelta(days=i)).isoformat()
            for u in users:
                size[u] = max(1 * GB, size[u] + growth[u] * rnd.uniform(0.2, 1.8))
                if rnd.random() < 0.02 and size[u] < TB:  # occasional cleanup
                    size[u] *= rnd.uniform(0.75, 0.92)
            used = int(sum(size.values()) + overhead)
            conn.executemany("INSERT INTO user_usage VALUES (?,?,?,?,?)",
                             [(day, name, u, int(b), int(b / avg_file[u])) for u, b in size.items()])
            conn.execute("INSERT INTO nas_snapshot VALUES (?,?,?,?,?,?,?,?)",
                         (day, name, total, used, total - used, f"{day}T01:30:00", 600.0, 0))
    conn.commit()
    print(f"Demo data written to {db_path}\nRun:  NAS_MONITOR_CONFIG={cfg_path} python3 server.py")


if __name__ == "__main__":
    main()
