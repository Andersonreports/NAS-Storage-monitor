#!/usr/bin/env python3
"""Write data.json from the database: the file the GitHub Pages copy of the dashboard reads.

  python3 export.py
"""
import argparse
import json
import os

from db import BASE_DIR, build_data, load_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "data.json"))
    ap.add_argument("--days", type=int, default=400)
    args = ap.parse_args()
    data = build_data(load_config(args.config), args.days)
    with open(args.out, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"Wrote {args.out} ({os.path.getsize(args.out) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
