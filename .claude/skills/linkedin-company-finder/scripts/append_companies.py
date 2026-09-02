#!/usr/bin/env python3
"""
append_companies.py - Deduplicates and appends new company rows to the ONE master tracker.

There is exactly one data file: connections.csv in the project root. This script will
refuse to write to any other filename, always creates the master with the full
canonical header if it is missing, and always writes rows that match the existing
header exactly - so the column layout can never drift out of sync with the dashboard.

Usage:
    python append_companies.py --companies '[{"company_id": "acme", ...}, ...]'

The --companies argument is a JSON array of company dicts (finder fields only; the
outreach columns are left blank and filled later by the connect-outreach skill).

Exits 0 and prints a summary of how many companies were added vs skipped.
"""

import argparse
import csv
import importlib.util
import json
import os
import sys
from datetime import date

_FALLBACK_MASTER = "connections.csv"


def find_project_root() -> str:
    """Locate the project root deterministically, independent of the CWD.

    This script lives at <root>/.claude/skills/<skill>/scripts/append_companies.py,
    so the project root is four directories up. We confirm by checking for schema.py
    (the project marker), then walk upward as a fallback, and finally fall back to the
    CWD. This is what lets a scheduled run write to the right tracker even when its
    working directory is not the project folder.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    if os.path.exists(os.path.join(candidate, "schema.py")):
        return candidate
    d = here
    for _ in range(6):
        if os.path.exists(os.path.join(d, "schema.py")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.getcwd()


def load_schema(csv_path: str):
    """Load schema.py sitting next to the master CSV. It is the only column authority."""
    schema_path = os.path.join(os.path.dirname(os.path.abspath(csv_path)), "schema.py")
    if not os.path.exists(schema_path):
        raise SystemExit(
            f"ERROR: schema.py not found next to {csv_path}. The column layout is defined "
            f"there and nowhere else - run this script against the real project root."
        )
    spec = importlib.util.spec_from_file_location("schema", schema_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_existing_ids(csv_path: str) -> set:
    if not os.path.exists(csv_path):
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {(row.get("company_id") or "").strip().lower()
                for row in csv.DictReader(f) if row.get("company_id")}


def load_seen_ids(cache_path: str) -> set:
    if not os.path.exists(cache_path):
        return set()
    with open(cache_path, encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip()}


def update_seen_ids(cache_path: str, new_ids: list):
    with open(cache_path, "a", encoding="utf-8") as f:
        for cid in new_ids:
            f.write(cid + "\n")


def current_week_label(d: date) -> str:
    """Week bucket used by the dashboard, mirroring the weekly outreach sheet."""
    return f"Week {d.isocalendar()[1]}"


def main():
    parser = argparse.ArgumentParser(description="Append new companies to the master tracker CSV.")
    parser.add_argument("--csv", default=os.path.join(find_project_root(), "connections.csv"),
                        help="Path to the master connections.csv (default: auto-located project root)")
    parser.add_argument("--companies", help="JSON array of company dicts")
    parser.add_argument("--print-root", action="store_true",
                        help="Print the auto-located project root and exit.")
    args = parser.parse_args()

    if args.print_root:
        print(find_project_root())
        return

    if not args.companies:
        print("ERROR: --companies is required (unless --print-root)", file=sys.stderr)
        sys.exit(1)

    schema = load_schema(args.csv)

    # Guardrail: only ever the master file.
    schema.assert_master_path(args.csv)

    try:
        companies = json.loads(args.companies)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse --companies JSON: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(companies, list):
        print("ERROR: --companies must be a JSON array", file=sys.stderr)
        sys.exit(1)

    schema.ensure_csv(args.csv)

    # The existing header is the authoritative write order (always full width).
    header = schema.read_header(args.csv) or list(schema.CANONICAL_COLUMNS)

    cache_path = os.path.join(os.path.dirname(os.path.abspath(args.csv)), "seen_companies.txt")
    seen_ids = load_seen_ids(cache_path)
    existing_ids = load_existing_ids(args.csv)
    today = date.today()
    today_iso = today.isoformat()
    week = current_week_label(today)

    added = 0
    skipped = 0
    ids_to_cache = []
    batch_seen = set()

    with open(args.csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        for comp in companies:
            cid = str(comp.get("company_id", "")).strip().lower()
            if not cid:
                print(f"  WARNING: skipping company with no company_id: "
                      f"{comp.get('company_name', '?')}")
                skipped += 1
                continue
            if cid in seen_ids or cid in existing_ids or cid in batch_seen:
                skipped += 1
                batch_seen.add(cid)
                continue

            row = {col: comp.get(col, "") for col in header}
            row["company_id"] = cid
            if not row.get("date_added"):
                row["date_added"] = today_iso
            if not row.get("week"):
                row["week"] = week
            for col, default in schema.DEFAULTS.items():
                if col in row and not row[col]:
                    row[col] = default

            writer.writerow(row)
            existing_ids.add(cid)
            batch_seen.add(cid)
            ids_to_cache.append(cid)
            added += 1

    if ids_to_cache:
        update_seen_ids(cache_path, ids_to_cache)

    print(f"Done. Added: {added} | Skipped (duplicates): {skipped} | "
          f"Week: {week} | CSV: {args.csv}")


if __name__ == "__main__":
    main()
