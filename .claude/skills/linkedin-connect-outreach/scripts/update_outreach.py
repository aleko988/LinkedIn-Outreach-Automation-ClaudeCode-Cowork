#!/usr/bin/env python3
"""
update_outreach.py - Update one company row in the ONE master tracker (connections.csv),
enforce the connection-note character limit, and enforce the daily send cap.

There is exactly one data file: connections.csv in the project root. This script refuses
to operate on any other filename and always preserves the existing header order - it only
fills in the outreach columns for the matching row, never reshapes the file.

It is also the SAFETY VALVE for the two things an agent must not get wrong:

  1. The note length. A connection_note longer than the configured limit is REFUSED,
     not truncated. The agent has to rewrite it shorter.
  2. The daily cap. --cap-check reports how many sends are still allowed today, counted
     from the CSV itself (rows whose date_sent is today). Run it BEFORE each send.

Modes:

  python update_outreach.py --cap-check
  python update_outreach.py --due-followups
  python update_outreach.py --company_id acme --data JSON_OBJECT
  python update_outreach.py --company_id acme --mark-sent
  python update_outreach.py --company_id acme --followup 1 --message TEXT
  python update_outreach.py --company_id acme --result Accepted
  python update_outreach.py --company_id acme --delete
  python update_outreach.py --print-root
"""

import argparse
import csv
import importlib.util
import json
import os
import sys
from datetime import date, datetime


def find_project_root() -> str:
    """Locate the project root deterministically, independent of the CWD.

    This script lives at <root>/.claude/skills/<skill>/scripts/update_outreach.py, so
    the project root is four directories up. We confirm with schema.py (the project
    marker), then walk upward as a fallback, and finally fall back to the CWD. This
    lets a scheduled run update the right tracker from any working directory.
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


def load_config(root: str) -> dict:
    """Load the live outreach config, falling back to the shipped example.

    Only the limits this script enforces are read here (note length, daily cap,
    follow-up timing). Everything else about tone and targeting is the skill's job.
    """
    for name in ("outreach_config.json", "outreach_config.example.json"):
        p = os.path.join(root, name)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f).get("outreach", {}) or {}
            except (ValueError, OSError):
                continue
    return {}


def read_rows(csv_path: str):
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_rows(csv_path: str, fieldnames, rows):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            for col in fieldnames:
                row.setdefault(col, "")
            writer.writerow(row)


def sent_today(rows) -> int:
    today = date.today().isoformat()
    return sum(1 for r in rows if (r.get("date_sent") or "").strip() == today)


def check_note(note: str, limit: int, field: str) -> int:
    """Refuse an over-long note instead of silently truncating it."""
    n = len(note)
    if n > limit:
        raise SystemExit(
            f"REFUSING TO WRITE: {field} is {n} characters, the limit is {limit}.\n"
            f"Rewrite it shorter - do not truncate mid-sentence. The text was:\n{note}"
        )
    return n


def main():
    root = find_project_root()
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=os.path.join(root, "connections.csv"),
                        help="Path to the master connections.csv (default: auto-located root)")
    parser.add_argument("--company_id", help="company_id of the row to update")
    parser.add_argument("--data", help="JSON object of outreach fields to update")
    parser.add_argument("--note", help="Shorthand for setting connection_note only")
    parser.add_argument("--mark-sent", action="store_true",
                        help="Record that the connection request was actually sent now.")
    parser.add_argument("--result",
                        help="Set connection_result (Sent/Pending/Accepted/Ignored/Withdrawn/Failed)")
    parser.add_argument("--followup", type=int, choices=[1, 2], help="Record follow-up 1 or 2")
    parser.add_argument("--message", help="The follow-up message text (use with --followup)")
    parser.add_argument("--delete", action="store_true", help="Delete this row")
    parser.add_argument("--cap-check", action="store_true",
                        help="Print how many more requests may be sent today, then exit.")
    parser.add_argument("--due-followups", action="store_true",
                        help="List accepted connections whose follow-up is due, then exit.")
    parser.add_argument("--print-root", action="store_true",
                        help="Print the auto-located project root and exit.")
    args = parser.parse_args()

    if args.print_root:
        print(root)
        return

    schema = load_schema(args.csv)
    schema.assert_master_path(args.csv)
    cfg = load_config(root)
    note_limit = int(cfg.get("note_char_limit", getattr(schema, "NOTE_CHAR_LIMIT", 200)))
    followup_limit = int(cfg.get("followup_char_limit", 400))
    cap = int(cfg.get("daily_connection_cap", 15))

    if not os.path.exists(args.csv):
        print(f"Error: master CSV not found at {args.csv}", file=sys.stderr)
        sys.exit(1)

    fieldnames, rows = read_rows(args.csv)
    today = date.today().isoformat()

    # ---------- CAP CHECK ----------
    if args.cap_check:
        used = sent_today(rows)
        remaining = max(0, cap - used)
        print(json.dumps({"cap": cap, "sent_today": used, "remaining": remaining}))
        if remaining == 0:
            print("Daily cap reached. Stop sending and report back to the user.",
                  file=sys.stderr)
        return

    # ---------- DUE FOLLOW-UPS ----------
    if args.due_followups:
        d1 = int(cfg.get("followup_1_days", 3))
        d2 = int(cfg.get("followup_2_days", 8))
        due = []
        for r in rows:
            if (r.get("connection_result") or "").strip() != "Accepted":
                continue
            if (r.get("reply_status") or "").strip() in ("Replied", "Positive", "Not interested"):
                continue
            sent = (r.get("date_sent") or "").strip()
            if not sent:
                continue
            try:
                sent_d = datetime.strptime(sent, "%Y-%m-%d").date()
            except ValueError:
                continue
            age = (date.today() - sent_d).days
            has_f1 = bool((r.get("followup_1_date") or "").strip())
            has_f2 = bool((r.get("followup_2_date") or "").strip())
            which = None
            if not has_f1 and age >= d1:
                which = 1
            elif has_f1 and not has_f2 and age >= d2:
                which = 2
            if which:
                due.append({"company_id": r.get("company_id"),
                            "company_name": r.get("company_name"),
                            "persona_name": r.get("persona_name"),
                            "persona_linkedin": r.get("persona_linkedin"),
                            "followup": which,
                            "days_since_sent": age})
        print(json.dumps(due, indent=2))
        return

    if not args.company_id:
        print("Error: --company_id is required (unless --cap-check / --due-followups / "
              "--print-root)", file=sys.stderr)
        sys.exit(1)

    company_id = str(args.company_id).strip().lower()

    # ---------- DELETE ----------
    if args.delete:
        before = len(rows)
        rows = [r for r in rows if (r.get("company_id") or "").strip().lower() != company_id]
        if len(rows) == before:
            print(f"Error: company_id '{company_id}' not found in CSV", file=sys.stderr)
            sys.exit(1)
        write_rows(args.csv, fieldnames, rows)
        print(f"Done. Deleted company_id={company_id} (left in seen_companies.txt so it "
              f"will not be re-added) | CSV: {args.csv}")
        return

    # Ensure all outreach columns exist (in case of an older or partial header).
    for col in schema.OUTREACH_COLUMNS:
        if col not in fieldnames:
            fieldnames.append(col)

    target = next((r for r in rows
                   if (r.get("company_id") or "").strip().lower() == company_id), None)
    if target is None:
        print(f"Error: company_id '{company_id}' not found in CSV", file=sys.stderr)
        sys.exit(1)

    updates = {}
    if args.data:
        try:
            updates = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Error: --data is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
    if args.note:
        updates["connection_note"] = args.note

    # ---------- FOLLOW-UP ----------
    if args.followup:
        if not args.message:
            print("Error: --followup requires --message", file=sys.stderr)
            sys.exit(1)
        check_note(args.message, followup_limit, f"followup_{args.followup}_message")
        updates[f"followup_{args.followup}_message"] = args.message
        updates[f"followup_{args.followup}_date"] = today
        updates["last_action_date"] = today

    # ---------- NOTE LENGTH GUARDRAIL ----------
    if "connection_note" in updates:
        n = check_note(str(updates["connection_note"]), note_limit, "connection_note")
        updates["note_char_count"] = str(n)
        if (target.get("outreach_status") or "").strip() not in ("Request sent", "Accepted", "Replied"):
            updates.setdefault("outreach_status", "Note drafted")

    # ---------- MARK SENT (cap-enforced) ----------
    if args.mark_sent:
        note = str(updates.get("connection_note") or target.get("connection_note") or "").strip()
        if not note:
            print("Error: cannot mark sent - this row has no connection_note yet.",
                  file=sys.stderr)
            sys.exit(1)
        check_note(note, note_limit, "connection_note")
        used = sent_today(rows)
        already_today = (target.get("date_sent") or "").strip() == today
        if not already_today and used >= cap:
            print(f"REFUSING: daily cap of {cap} requests already reached ({used} sent today). "
                  f"Stop sending and report back to the user.", file=sys.stderr)
            sys.exit(2)
        updates["connection_sent"] = "Yes"
        updates["date_sent"] = today
        updates["connection_result"] = args.result or "Sent"
        updates["outreach_status"] = "Request sent"
        updates["last_action_date"] = today
    elif args.result:
        updates["connection_result"] = args.result
        updates["last_action_date"] = today
        if args.result == "Accepted":
            updates["outreach_status"] = "Accepted"

    if not updates:
        print("Error: nothing to update. Pass --data, --note, --mark-sent, --result or "
              "--followup.", file=sys.stderr)
        sys.exit(1)

    for key, val in updates.items():
        if key in fieldnames:
            target[key] = val

    write_rows(args.csv, fieldnames, rows)

    tail = ""
    if args.mark_sent:
        tail = f" | Sent today: {sent_today(rows)}/{cap}"
    print(f"Done. Updated company_id={company_id} | Fields: {', '.join(updates.keys())}{tail} "
          f"| CSV: {args.csv}")


if __name__ == "__main__":
    main()
