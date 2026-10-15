#!/usr/bin/env python3
"""
append_jobs.py - Deduplicates and appends new JOB rows to the ONE master tracker.

There is exactly one data file: connections.csv in the project root. This script will
refuse to write to any other filename, always creates the master with the full
canonical header if it is missing, and always writes rows that match the existing
header exactly.

A job row is one specific posting (job-first outreach): its company_id is
"<company-slug>--<job_id>", so the same company can appear again later for a different
role, while the job itself is never added twice (seen_jobs.txt + existing rows).

To avoid flooding one company's recruiters with requests for every analyst opening, a
company that already got a job row within the last `job_company_cooldown_days` (config,
default 30) is skipped.

Usage:
    python append_jobs.py --status
        Prints {"seen_job_ids": [...], "companies_on_cooldown": [...]} so the finder can
        skip those before opening any job page.
    python append_jobs.py --jobs '[{"job_id": "4012345678", "company_slug": "acme", ...}, ...]'
        Each job dict carries the finder columns (job_title, job_url, company_name, ...)
        plus company_slug. Outreach columns are left blank for the outreach skill.
    python append_jobs.py --print-root
"""

import argparse
import csv
import importlib.util
import json
import os
import sys
from datetime import date, datetime


def find_project_root() -> str:
    """Same discovery as the other helper scripts: four levels up, confirmed by schema.py."""
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
    schema_path = os.path.join(os.path.dirname(os.path.abspath(csv_path)), "schema.py")
    if not os.path.exists(schema_path):
        raise SystemExit(f"ERROR: schema.py not found next to {csv_path}.")
    spec = importlib.util.spec_from_file_location("schema", schema_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_config(root: str) -> dict:
    for name in ("outreach_config.json", "outreach_config.example.json"):
        p = os.path.join(root, name)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (ValueError, OSError):
                continue
    return {}


def read_rows(csv_path: str):
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_seen(cache_path: str) -> set:
    if not os.path.exists(cache_path):
        return set()
    with open(cache_path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def company_slug(row) -> str:
    url = (row.get("linkedin_company_url") or "").lower()
    if "/company/" in url:
        return url.split("/company/")[1].split("/")[0]
    return (row.get("company_id") or "").split("--")[0].lower()


def companies_on_cooldown(rows, days: int) -> set:
    """Company slugs that already got a job row within the cooldown window."""
    out = set()
    today = date.today()
    for r in rows:
        if not (r.get("job_id") or "").strip():
            continue
        try:
            added = datetime.strptime((r.get("date_added") or "").strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        if (today - added).days < days:
            out.add(company_slug(r))
    return out


def main():
    root = find_project_root()
    parser = argparse.ArgumentParser(description="Append new job rows to the master tracker CSV.")
    parser.add_argument("--csv", default=os.path.join(root, "connections.csv"))
    parser.add_argument("--jobs", help="JSON array of job dicts")
    parser.add_argument("--status", action="store_true",
                        help="Print seen job ids and companies on cooldown, then exit.")
    parser.add_argument("--print-root", action="store_true")
    args = parser.parse_args()

    if args.print_root:
        print(root)
        return

    schema = load_schema(args.csv)
    schema.assert_master_path(args.csv)
    cooldown = int(load_config(root).get("finder", {}).get("job_company_cooldown_days", 30))
    cache_path = os.path.join(os.path.dirname(os.path.abspath(args.csv)), "seen_jobs.txt")

    rows = read_rows(args.csv)
    seen = load_seen(cache_path) | {(r.get("job_id") or "").strip() for r in rows if r.get("job_id")}
    cooling = companies_on_cooldown(rows, cooldown)

    if args.status:
        print(json.dumps({"seen_job_ids": sorted(seen), "companies_on_cooldown": sorted(cooling),
                          "cooldown_days": cooldown}))
        return

    if not args.jobs:
        print("ERROR: --jobs is required (unless --status / --print-root)", file=sys.stderr)
        sys.exit(1)
    try:
        jobs = json.loads(args.jobs)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse --jobs JSON: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(jobs, list):
        print("ERROR: --jobs must be a JSON array", file=sys.stderr)
        sys.exit(1)

    schema.ensure_csv(args.csv)
    header = schema.read_header(args.csv) or list(schema.CANONICAL_COLUMNS)
    missing = [c for c in ("job_id", "job_title", "job_url") if c not in header]
    if missing:
        raise SystemExit(f"ERROR: connections.csv has no {missing} columns yet - migrate it to the "
                         f"current schema first (RETARGETING.md, 'Additive change').")

    today = date.today()
    added, skipped_seen, skipped_cooldown, skipped_bad = 0, 0, 0, 0
    new_ids = []
    with open(args.csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        for job in jobs:
            jid = str(job.get("job_id", "")).strip()
            slug = str(job.get("company_slug", "")).strip().lower()
            if not jid or not slug:
                print(f"  WARNING: skipping job with no job_id/company_slug: {job.get('job_title', '?')}")
                skipped_bad += 1
                continue
            if jid in seen:
                skipped_seen += 1
                continue
            if slug in cooling:
                skipped_cooldown += 1
                continue
            row = {col: job.get(col, "") for col in header}
            row["company_id"] = f"{slug}--{jid}"
            row["job_id"] = jid
            row["job_url"] = row.get("job_url") or f"https://www.linkedin.com/jobs/view/{jid}/"
            row["linkedin_company_url"] = row.get("linkedin_company_url") or \
                f"https://www.linkedin.com/company/{slug}/"
            row["date_added"] = row.get("date_added") or today.isoformat()
            row["week"] = row.get("week") or f"Week {today.isocalendar()[1]}"
            for col, default in schema.DEFAULTS.items():
                if col in row and not row[col]:
                    row[col] = default
            writer.writerow(row)
            seen.add(jid)
            cooling.add(slug)  # one job per company per run, too
            new_ids.append(jid)
            added += 1

    if new_ids:
        with open(cache_path, "a", encoding="utf-8") as f:
            for jid in new_ids:
                f.write(jid + "\n")

    print(f"Done. Added: {added} | Skipped (already seen): {skipped_seen} | "
          f"Skipped (company on {cooldown}-day cooldown): {skipped_cooldown} | "
          f"Skipped (missing id): {skipped_bad} | CSV: {args.csv}")


if __name__ == "__main__":
    main()
