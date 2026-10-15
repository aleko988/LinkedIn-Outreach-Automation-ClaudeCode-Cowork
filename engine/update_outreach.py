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
  3. The monthly note quota (no LinkedIn Premium = a limited number of connection
     requests per month may include a personalized note). --note-cap-check reports how
     many note-sends remain this calendar month, counted from the CSV itself (rows with
     note_sent_with_request=Yes whose date_sent is this month). --mark-sent REFUSES a
     note-send once the quota is used - the row must go out as a plain connect instead
     (--note-used no).

It also tracks the **acceptance-check cutoff**: the date the daily acceptance-check pass
last ran. --acceptance-check-status prints that cutoff (so the pass only reads LinkedIn's
Connections page down to that date, sorted "Recently added", instead of scanning the
user's entire connections list every day). --mark-checked advances it after a pass
finishes. This state lives in last_acceptance_check.json next to connections.csv - it is
bookkeeping, not outreach data, same category as seen_companies.txt.

It also maintains blocked_personas.txt: profiles that hit a wall this project cannot work
around (e.g. LinkedIn's "verify this member knows you" email gate) get remembered there via
--block-persona, so they are never picked as a candidate again.

A company has up to THREE contacts: the primary persona (persona_*/connection_* columns),
a second contact (persona2_*, used when personas_per_company > 1), and a peer on the team
(persona3_*, used when peer_enabled is true). --persona 2|3 on --mark-sent, --result and
--followup writes to that contact's columns instead of the primary ones - each is a fully
separate connection request against the SAME daily cap and monthly note quota, so
--cap-check and --note-cap-check count every contact's sends together.

Follow-up timing (--due-followups): follow-up 1 is due followup_1_days after the acceptance
was recorded (accepted_date; 0 = the same day), follow-up 2 is due followup_2_days after
follow-up 1 went out. --due-emails lists contacts whose request has sat unaccepted for
no_accept_email_days, so the skill can draft a fallback email for the user to send.

Modes:

  python update_outreach.py --cap-check
  python update_outreach.py --note-cap-check
  python update_outreach.py --due-followups
  python update_outreach.py --acceptance-check-status
  python update_outreach.py --mark-checked [--as-of YYYY-MM-DD]
  python update_outreach.py --block-persona PROFILE_URL
  python update_outreach.py --company_id acme --block-persona PROFILE_URL --data '{"persona_name": "", ...}'
  python update_outreach.py --due-emails
  python update_outreach.py --company_id acme --persona 2 --mark-sent [--note-used yes|no]
  python update_outreach.py --company_id acme --persona 3 --result Accepted
  python update_outreach.py --company_id acme --data JSON_OBJECT
  python update_outreach.py --company_id acme --mark-sent [--note-used yes|no]
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

    This script lives at <root>/engine/update_outreach.py. We first try four directories
    up (its old .claude/skills/<skill>/scripts/ home), then walk upward until we find
    schema.py (the project marker), and finally fall back to the CWD. This
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


PERSONAS = ("1", "2", "3")


def pf(persona: str, key: str) -> str:
    """Column name for a contact slot - mirrors schema.persona_field (kept local so the
    helpers below work before the schema module is loaded)."""
    if persona == "1":
        if key in ("name", "title", "linkedin", "tier"):
            return f"persona_{key}"
        return "connection_note" if key == "note" else key
    return f"persona{persona}_{key}"


def sent_today(rows) -> int:
    """Count sends today against the daily cap - every contact at a company (primary,
    second, peer) is its own connection request against the same LinkedIn account limit."""
    today = date.today().isoformat()
    return sum(1 for r in rows for p in PERSONAS
               if (r.get(pf(p, "date_sent")) or "").strip() == today)


def blocked_personas_path(root: str) -> str:
    return os.path.join(root, "blocked_personas.txt")


def normalize_profile_path(url: str) -> str:
    """Reduce a LinkedIn profile URL to its /in/<slug> path, lowercased, so the
    blocklist matches regardless of query params or https/www variations."""
    u = (url or "").strip().lower()
    idx = u.find("/in/")
    if idx == -1:
        return u
    rest = u[idx:]
    return rest.split("?")[0].rstrip("/")


def block_persona(root: str, profile_url: str) -> None:
    """Remember a profile that hit a wall this project cannot work around (e.g. LinkedIn's
    'verify this member knows you' email gate), so it is never picked as a candidate again.
    Bookkeeping only, like seen_companies.txt - not outreach data.
    """
    path = normalize_profile_path(profile_url)
    if not path:
        return
    existing = set()
    p = blocked_personas_path(root)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            existing = {line.strip() for line in f if line.strip()}
    if path not in existing:
        with open(p, "a", encoding="utf-8") as f:
            f.write(path + "\n")


def acceptance_check_state_path(root: str) -> str:
    return os.path.join(root, "last_acceptance_check.json")


def read_last_checked_date(root: str, rows) -> str:
    """The cutoff date for the daily acceptance-check pass: everyone on the Connections
    page dated on or before this can be skipped, since they were already seen last time.

    Falls back to the earliest date_sent in the tracker (never miss the very first batch
    ever sent) or, if nothing has been sent yet, to today.
    """
    state_path = acceptance_check_state_path(root)
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                data = json.load(f)
            v = (data.get("last_checked_date") or "").strip()
            if v:
                return v
        except (ValueError, OSError):
            pass
    all_dates = [(r.get(pf(p, "date_sent")) or "").strip() for r in rows for p in PERSONAS]
    sent_dates = sorted(d for d in all_dates if d)
    return sent_dates[0] if sent_dates else date.today().isoformat()


def write_last_checked_date(root: str, as_of: str) -> None:
    with open(acceptance_check_state_path(root), "w", encoding="utf-8") as f:
        json.dump({"last_checked_date": as_of}, f)


def notes_sent_this_month(rows) -> int:
    """Count connection requests actually sent WITH a personalized note this
    calendar month - this is what LinkedIn's free-plan monthly note quota limits.
    A drafted-but-unsent note, or a note sent as part of a plain (no-note) connect,
    does not count. Checked for every contact slot - each is its own connection
    request against the same monthly quota.
    """
    ym = date.today().strftime("%Y-%m")
    return sum(1 for r in rows for p in PERSONAS
               if (r.get(pf(p, "note_sent_with_request")) or "").strip() == "Yes"
               and (r.get(pf(p, "date_sent")) or "").strip().startswith(ym))


def parse_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


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
    parser.add_argument("--persona", choices=list(PERSONAS), default="1",
                        help="Which contact at this company --mark-sent / --result / --followup "
                             "apply to (default: 1, the primary persona_* fields). '2' writes to "
                             "the persona2_* fields (second contact), '3' to persona3_* (the peer).")
    parser.add_argument("--note-used", choices=["yes", "no"],
                        help="With --mark-sent: whether the drafted note was actually included in "
                             "the sent invite (counts against the monthly note quota) or it went out "
                             "as a plain connect. Defaults to 'yes' if a connection_note is present, "
                             "'no' otherwise - pass explicitly to send a plain connect despite having "
                             "a drafted note on file.")
    parser.add_argument("--result",
                        help="Set connection_result (Sent/Pending/Accepted/Ignored/Withdrawn/Failed/"
                             "Emailed) for the --persona contact. Accepted also stamps accepted_date.")
    parser.add_argument("--followup", type=int, choices=[1, 2], help="Record follow-up 1 or 2")
    parser.add_argument("--message", help="The follow-up message text (use with --followup)")
    parser.add_argument("--delete", action="store_true", help="Delete this row")
    parser.add_argument("--block-persona",
                        help="Profile URL of a person who should never be picked as a candidate "
                             "again (e.g. hit LinkedIn's email-verification wall). Appends to "
                             "blocked_personas.txt. Can be combined with --data to also clear "
                             "this row's persona fields so the company gets retried with someone "
                             "else on the next run.")
    parser.add_argument("--cap-check", action="store_true",
                        help="Print how many more requests may be sent today, then exit.")
    parser.add_argument("--note-cap-check", action="store_true",
                        help="Print how many personalized-note sends remain this month, then exit.")
    parser.add_argument("--due-followups", action="store_true",
                        help="List accepted connections whose follow-up is due, then exit.")
    parser.add_argument("--due-emails", action="store_true",
                        help="List contacts whose request has sat unaccepted for "
                             "no_accept_email_days with no fallback email drafted yet, then exit.")
    parser.add_argument("--acceptance-check-status", action="store_true",
                        help="Print the cutoff date for the daily acceptance-check pass, then exit.")
    parser.add_argument("--mark-checked", action="store_true",
                        help="Advance the acceptance-check cutoff (default: today), then exit.")
    parser.add_argument("--as-of", help="With --mark-checked: the date to set as the new cutoff "
                                         "(default: today). Format YYYY-MM-DD.")
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
    note_cap = int(cfg.get("note_monthly_limit", 5))

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

    # ---------- NOTE CAP CHECK (monthly) ----------
    if args.note_cap_check:
        used = notes_sent_this_month(rows)
        remaining = max(0, note_cap - used)
        print(json.dumps({"note_cap": note_cap, "notes_used_this_month": used,
                           "notes_remaining": remaining}))
        if remaining == 0:
            print("Monthly note quota used up. Draft the note as usual for the record, but "
                  "send this and every remaining request as a PLAIN connect (no note) until "
                  "next month - pass --note-used no with --mark-sent.", file=sys.stderr)
        return

    # ---------- DUE FOLLOW-UPS ----------
    # followup_scope "job_rows": only rows that came from a specific job posting (job_id set)
    # get follow-ups and fallback emails - legacy company-only rows are left alone.
    job_rows_only = str(cfg.get("followup_scope", "all")).strip() == "job_rows"

    def in_scope(r):
        return not job_rows_only or bool((r.get("job_id") or "").strip())

    if args.due_followups:
        d1 = int(cfg.get("followup_1_days", 0))
        d2 = int(cfg.get("followup_2_days", 4))

        def due_for_persona(r, p):
            """Checks one contact slot's own acceptance/reply/followup state independently.

            Follow-up 1 is anchored on the ACCEPTANCE (accepted_date), not the send - the
            best time to message is right after they accept. Rows accepted before
            accepted_date existed fall back to date_sent. Follow-up 2 is anchored on
            follow-up 1, so it always lands followup_2_days after the first message.
            """
            if not in_scope(r) or not (r.get(pf(p, "name")) or "").strip():
                return None
            if (r.get(pf(p, "connection_result")) or "").strip() != "Accepted":
                return None
            if (r.get(pf(p, "reply_status")) or "").strip() in ("Replied", "Positive", "Not interested"):
                return None
            anchor = parse_date(r.get(pf(p, "accepted_date"))) or parse_date(r.get(pf(p, "date_sent")))
            if not anchor:
                return None
            today_d = date.today()
            f1 = parse_date(r.get(pf(p, "followup_1_date")))
            has_f1 = bool((r.get(pf(p, "followup_1_date")) or "").strip())
            has_f2 = bool((r.get(pf(p, "followup_2_date")) or "").strip())
            note_was_used = (r.get(pf(p, "note_sent_with_request")) or "").strip() == "Yes"
            which = None
            if not has_f1:
                # A plain connect (no note delivered at request time) is always due now -
                # they never got the personalized content at all.
                if (today_d - anchor).days >= d1 or not note_was_used:
                    which = 1
            elif not has_f2 and (today_d - (f1 or anchor)).days >= d2:
                which = 2
            if not which:
                return None
            return {"company_id": r.get("company_id"), "company_name": r.get("company_name"),
                    "job_title": r.get("job_title"), "job_url": r.get("job_url"),
                    "persona": p, "persona_name": r.get(pf(p, "name")),
                    "persona_tier": r.get(pf(p, "tier")),
                    "persona_linkedin": r.get(pf(p, "linkedin")), "followup": which,
                    "days_since_accepted": (today_d - anchor).days,
                    "immediate_no_note": which == 1 and not note_was_used}

        due = [e for r in rows for p in PERSONAS for e in [due_for_persona(r, p)] if e]
        print(json.dumps(due, indent=2))
        return

    # ---------- DUE FALLBACK EMAILS ----------
    if args.due_emails:
        n_days = int(cfg.get("no_accept_email_days", 5))
        due = []
        for r in rows:
            if not in_scope(r):
                continue
            for p in PERSONAS:
                if not (r.get(pf(p, "name")) or "").strip():
                    continue
                if (r.get(pf(p, "connection_sent")) or "").strip() != "Yes":
                    continue
                if (r.get(pf(p, "connection_result")) or "").strip() not in ("Sent", "Pending", ""):
                    continue
                if (r.get(pf(p, "email_draft")) or "").strip():
                    continue
                sent_d = parse_date(r.get(pf(p, "date_sent")))
                if not sent_d or (date.today() - sent_d).days < n_days:
                    continue
                due.append({"company_id": r.get("company_id"), "company_name": r.get("company_name"),
                            "company_website": r.get("company_website"),
                            "job_title": r.get("job_title"), "job_url": r.get("job_url"),
                            "persona": p, "persona_name": r.get(pf(p, "name")),
                            "persona_title": r.get(pf(p, "title")),
                            "persona_tier": r.get(pf(p, "tier")),
                            "days_since_sent": (date.today() - sent_d).days,
                            "email_field": pf(p, "email_draft")})
        # Freshest first - a request sent 6 days ago is a better email target than one
        # that has sat for two months. The skill drafts at most emails_per_run of these.
        due.sort(key=lambda e: e["days_since_sent"])
        print(json.dumps(due, indent=2))
        return

    # ---------- ACCEPTANCE-CHECK CUTOFF (read) ----------
    if args.acceptance_check_status:
        cutoff = read_last_checked_date(root, rows)
        print(json.dumps({"last_checked_date": cutoff}))
        print(f"Read the Connections page sorted by 'Recently added' and stop as soon as you "
              f"reach someone connected on or before {cutoff} - everyone above that on the "
              f"page is new since the last check.", file=sys.stderr)
        return

    # ---------- ACCEPTANCE-CHECK CUTOFF (advance) ----------
    if args.mark_checked:
        as_of = args.as_of or today
        write_last_checked_date(root, as_of)
        print(f"Done. Acceptance-check cutoff advanced to {as_of}.")
        return

    # ---------- BLOCK A PERSONA (standalone, or combined with --company_id/--data below) ----------
    if args.block_persona:
        block_persona(root, args.block_persona)
        if not args.company_id:
            print(f"Done. Blocked persona: {normalize_profile_path(args.block_persona)}")
            return
        # else: fall through - the caller is also clearing this row's persona fields via --data

    if not args.company_id:
        print("Error: --company_id is required (unless --cap-check / --note-cap-check / "
              "--due-followups / --due-emails / --acceptance-check-status / --mark-checked / --block-persona / "
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

    # The second-contact and peer notes get the same hard length check as connection_note.
    for p in ("2", "3"):
        f = pf(p, "note")
        if f in updates and str(updates[f]).strip():
            check_note(str(updates[f]), note_limit, f)

    # ---------- FOLLOW-UP (primary or persona2) ----------
    if args.followup:
        if not args.message:
            print("Error: --followup requires --message", file=sys.stderr)
            sys.exit(1)
        fu_msg_field = pf(args.persona, f"followup_{args.followup}_message")
        fu_date_field = pf(args.persona, f"followup_{args.followup}_date")
        check_note(args.message, followup_limit, fu_msg_field)
        updates[fu_msg_field] = args.message
        updates[fu_date_field] = today
        updates[pf(args.persona, "last_action_date")] = today

    # ---------- NOTE LENGTH GUARDRAIL ----------
    if "connection_note" in updates:
        n = check_note(str(updates["connection_note"]), note_limit, "connection_note")
        updates["note_char_count"] = str(n)
        if (target.get("outreach_status") or "").strip() not in ("Request sent", "Accepted", "Replied"):
            updates.setdefault("outreach_status", "Note drafted")

    # ---------- MARK SENT (daily-cap and monthly-note-cap enforced, any contact slot) ----------
    if args.mark_sent:
        is_primary = args.persona == "1"
        note_field = pf(args.persona, "note")
        sent_field = pf(args.persona, "connection_sent")
        date_field = pf(args.persona, "date_sent")
        result_field = pf(args.persona, "connection_result")
        note_used_field = pf(args.persona, "note_sent_with_request")
        last_action_field = pf(args.persona, "last_action_date")

        # A connection may go out as a plain connect (no note) once the monthly note
        # quota is used up - a drafted note staying on file for the record is fine,
        # it just was not the thing actually sent. --note-used decides which happened;
        # if omitted, infer it from whether a note is present.
        note = str(updates.get(note_field) or target.get(note_field) or "").strip()
        if note:
            check_note(note, note_limit, note_field)
        note_used = args.note_used if args.note_used else ("yes" if note else "no")
        if note_used == "yes" and not note:
            print(f"Error: --note-used yes but this row has no {note_field} to send.",
                  file=sys.stderr)
            sys.exit(1)

        used = sent_today(rows)
        already_today = (target.get(date_field) or "").strip() == today
        if not already_today and used >= cap:
            print(f"REFUSING: daily cap of {cap} requests already reached ({used} sent today). "
                  f"Stop sending and report back to the user.", file=sys.stderr)
            sys.exit(2)

        if note_used == "yes":
            already_counted_this_send = (target.get(note_used_field) or "").strip() == "Yes" and already_today
            notes_used = notes_sent_this_month(rows)
            if not already_counted_this_send and notes_used >= note_cap:
                print(f"REFUSING: monthly note quota of {note_cap} already reached "
                      f"({notes_used} sent this month). Send this one as a plain connect instead: "
                      f"re-run with --note-used no.", file=sys.stderr)
                sys.exit(2)

        updates[sent_field] = "Yes"
        updates[date_field] = today
        updates[result_field] = args.result or "Sent"
        updates[note_used_field] = "Yes" if note_used == "yes" else "No"
        updates[last_action_field] = today
        if is_primary:
            # No per-persona outreach_status column exists for the other contacts - the
            # shared outreach_status only reflects the primary persona's progress.
            updates["outreach_status"] = "Request sent"
    elif args.result:
        updates[pf(args.persona, "connection_result")] = args.result
        updates[pf(args.persona, "last_action_date")] = today
        if args.result == "Accepted":
            # Stamp the acceptance once - it anchors follow-up 1. A re-run never moves it.
            if not (target.get(pf(args.persona, "accepted_date")) or "").strip():
                updates[pf(args.persona, "accepted_date")] = today
            if args.persona == "1":
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
        tail = f" | Sent today: {sent_today(rows)}/{cap} | Notes this month: {notes_sent_this_month(rows)}/{note_cap}"
    print(f"Done. Updated company_id={company_id} | Fields: {', '.join(updates.keys())}{tail} "
          f"| CSV: {args.csv}")


if __name__ == "__main__":
    main()
