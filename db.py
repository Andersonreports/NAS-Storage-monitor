"""Shared config + SQLite helpers."""
import datetime as dt
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_DB = os.path.join(BASE_DIR, "data", "demo.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS nas_snapshot (
    day         TEXT NOT NULL,          -- YYYY-MM-DD
    nas         TEXT NOT NULL,
    total_bytes INTEGER,                -- NULL when capacity is unknown
    used_bytes  INTEGER NOT NULL,
    free_bytes  INTEGER,
    scanned_at  TEXT NOT NULL,          -- ISO timestamp of the scan / report
    scan_secs   REAL,
    errors      INTEGER DEFAULT 0,
    PRIMARY KEY (day, nas)
);
CREATE TABLE IF NOT EXISTS user_usage (
    day     TEXT NOT NULL,
    nas     TEXT NOT NULL,
    user    TEXT NOT NULL,
    bytes   INTEGER NOT NULL,
    files   INTEGER,
    PRIMARY KEY (day, nas, user)
);
CREATE INDEX IF NOT EXISTS idx_user_usage_nas_user ON user_usage (nas, user, day);
CREATE TABLE IF NOT EXISTS transfer_status (
    day         TEXT NOT NULL,
    nas         TEXT NOT NULL,
    department  TEXT NOT NULL,
    share       TEXT,
    checked     TEXT,
    samples     INTEGER,
    complete    INTEGER,
    partial     INTEGER,
    not_started INTEGER,
    pending     INTEGER,
    no_files    INTEGER,
    size_gb     REAL,
    copied_gb   REAL,
    pending_gb  REAL,
    PRIMARY KEY (day, nas, department)
);
"""


def load_config(path=None):
    path = path or os.environ.get("NAS_MONITOR_CONFIG") or os.path.join(BASE_DIR, "config.json")
    with open(path) as f:
        cfg = json.load(f)
    db = cfg.get("db", "data/storage.db")
    if not os.path.isabs(db):
        db = os.path.join(BASE_DIR, db)
    cfg["db"] = db
    return cfg


def connect(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _nas_data(conn, nas, since):
    name = nas["name"]
    snaps = conn.execute(
        "SELECT day, total_bytes, used_bytes, free_bytes, scanned_at FROM nas_snapshot "
        "WHERE nas=? AND day>=? ORDER BY day", (name, since)).fetchall()
    day_list = [r["day"] for r in snaps]
    idx = {d: i for i, d in enumerate(day_list)}
    users = {}
    for r in conn.execute("SELECT day, user, bytes, files FROM user_usage WHERE nas=? AND day>=?", (name, since)):
        i = idx.get(r["day"])
        if i is None:
            continue
        u = users.setdefault(r["user"], {"bytes": [None] * len(day_list), "files": [None] * len(day_list)})
        u["bytes"][i] = r["bytes"]
        u["files"][i] = r["files"]
    # capacity from config overrides / fills in what the scan could not measure
    cap = nas.get("capacity_bytes")
    total = [cap or r["total_bytes"] for r in snaps]
    free = [(t - r["used_bytes"]) if cap else r["free_bytes"] for t, r in zip(total, snaps)]
    tday = conn.execute("SELECT MAX(day) FROM transfer_status WHERE nas=?", (name,)).fetchone()[0]
    transfer = None
    if tday:
        rows = conn.execute("SELECT * FROM transfer_status WHERE nas=? AND day=? ORDER BY department",
                            (name, tday)).fetchall()
        transfer = {"day": tday, "rows": [{k: r[k] for k in r.keys() if k not in ("day", "nas")} for r in rows]}
    return {
        "name": name,
        "path": nas["path"],
        "description": nas.get("description", ""),
        "demo": bool(nas.get("demo")),
        "capacity": cap,
        "raw_capacity": nas.get("raw_capacity_bytes"),
        "sheet_url": nas.get("sheet_url"),
        "days": day_list,
        "total": total,
        "used": [r["used_bytes"] for r in snaps],
        "free": free,
        "scanned_at": snaps[-1]["scanned_at"] if snaps else None,
        "users": users,
        "transfer": transfer,
    }


def build_data(cfg, days=400):
    """Everything the dashboard needs, as one JSON-serialisable dict.

    Per NAS, `days` is the list of scan dates; every other array is aligned to it
    (null where a user had no data that day). NAS marked "demo": true in the config
    are read from data/demo.db (see seed_demo.py) instead of the real database.
    """
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    real = connect(cfg["db"])
    demo = connect(DEMO_DB) if any(n.get("demo") for n in cfg["nas"]) else None
    try:
        out = [_nas_data(demo if n.get("demo") else real, n, since) for n in cfg["nas"]]
    finally:
        real.close()
        if demo:
            demo.close()
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "thresholds": cfg.get("thresholds", {"warning": 80, "critical": 90}),
        "user_departments": {k.lower(): v for k, v in cfg.get("users", {}).items()},
        "nas": out,
    }
