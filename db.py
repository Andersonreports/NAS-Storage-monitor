"""Shared config + SQLite helpers."""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCHEMA = """
CREATE TABLE IF NOT EXISTS nas_snapshot (
    day         TEXT NOT NULL,          -- YYYY-MM-DD
    nas         TEXT NOT NULL,
    total_bytes INTEGER NOT NULL,
    used_bytes  INTEGER NOT NULL,
    free_bytes  INTEGER NOT NULL,
    scanned_at  TEXT NOT NULL,          -- ISO timestamp of the scan
    scan_secs   REAL,
    errors      INTEGER DEFAULT 0,
    PRIMARY KEY (day, nas)
);
CREATE TABLE IF NOT EXISTS user_usage (
    day     TEXT NOT NULL,
    nas     TEXT NOT NULL,
    user    TEXT NOT NULL,
    bytes   INTEGER NOT NULL,
    files   INTEGER NOT NULL,
    PRIMARY KEY (day, nas, user)
);
CREATE INDEX IF NOT EXISTS idx_user_usage_nas_user ON user_usage (nas, user, day);
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
