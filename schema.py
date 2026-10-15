#!/usr/bin/env python3
"""
schema.py - THE single source of truth for the connection tracker CSV.

There is exactly ONE data file in this project: connections.csv in the project root.
Its columns are defined here, in one place, and NOWHERE else. The dashboard, the
company-finder skill, and the connect-outreach skill all conform to this list. If a
column genuinely needs to change, edit it HERE and only here.

Why this file exists
--------------------
Agents kept creating second CSVs or writing rows with a different column layout than
the dashboard expected. That cannot happen here: every script creates and validates
the master file against CANONICAL_COLUMNS below, so there is never a "which CSV?" or
"why are the columns misaligned?" ambiguity.

Run this file directly to (re)create an EMPTY master tracker with the correct headers:

    python3 schema.py                    # creates ./connections.csv if missing
    python3 schema.py --force            # overwrites with an empty header-only file
    python3 schema.py --path /x/y.csv    # target a specific path (default: ./connections.csv)
"""

import argparse
import csv
import os

# The master tracker filename. Never anything else.
MASTER_CSV_NAME = "connections.csv"

# ---------------------------------------------------------------------------
# CANONICAL COLUMN ORDER - the one and only schema.
# The first block (up to outreach_status) is written by the COMPANY FINDER skill.
# The middle block is written by the CONNECT OUTREACH skill (three contact slots:
# primary persona_*, second persona2_*, peer persona3_*).
# The last two columns are written by the DASHBOARD (manual status edits).
# ---------------------------------------------------------------------------
CANONICAL_COLUMNS = [
    # --- company finder fields ---
    "company_id",             # LinkedIn company slug - the de-dup key
    "date_added",             # YYYY-MM-DD
    "week",                   # "Week 36" style bucket, mirrors the weekly sheet
    "company_name",
    "linkedin_company_url",
    "company_tagline",
    "industry",
    "company_size",
    "hq_location",
    "company_website",
    "signal",                 # why now: hiring, funding, growth, launch
    "why_relevant",           # 1-2 sentences, the personalization fuel
    "company_source",         # which search surfaced it
    "job_id",                 # LinkedIn job id - set on job-first rows (blank = legacy company-only row)
    "job_title",              # exact title of the posting
    "job_url",                # https://www.linkedin.com/jobs/view/<job_id>/
    "job_location",           # location line as posted (e.g. "Remote - EMEA", "United States (Remote)")
    "job_workplace",          # Remote / Hybrid / On-site
    "job_department",         # team/department the role sits in (e.g. Healthcare, Marketing, Product)
    "job_posted",             # YYYY-MM-DD (approximate, from "2 days ago")
    "location_eligibility",   # why the user can take it from their country (or "unstated - check")
    "cv_fit",                 # one line: which CV skills match the must-haves
    "outreach_status",        # Not started / Note drafted / Request sent / Accepted / Replied / Archived
    # --- connect outreach fields ---
    "persona_name",
    "persona_title",
    "persona_linkedin",
    "persona_tier",           # which contact tier matched (Founder, CEO, Head of X ...)
    "persona_location",
    "persona_mutuals",        # shared connections count, if visible
    "persona2_name",          # optional SECOND contact at this company (personas_per_company > 1)
    "persona2_title",
    "persona2_linkedin",
    "persona2_tier",
    "persona2_note",          # <=200 char note drafted for the second contact
    "persona2_connection_sent",        # Yes / No - second contact
    "persona2_date_sent",              # YYYY-MM-DD - also drives the daily cap counter
    "persona2_connection_result",      # Sent / Pending / Accepted / Ignored / Withdrawn / Failed / Emailed
    "persona2_accepted_date",          # YYYY-MM-DD the acceptance was recorded - anchors follow-up 1
    "persona2_note_sent_with_request", # Yes / No - whether persona2_note was actually included in
                                        # the sent invite (counts against the monthly note quota)
                                        # vs sent as a plain connect
    "persona2_last_action_date",
    "persona2_followup_1_message",
    "persona2_followup_1_date",
    "persona2_followup_2_message",
    "persona2_followup_2_date",
    "persona2_reply_status",  # No reply / Replied / Positive / Not interested - second contact
    "persona2_email_draft",   # fallback email drafted when the request sat unaccepted (user sends it)
    "persona3_name",          # PEER contact (peer_enabled) - someone on the team you would join
    "persona3_title",
    "persona3_linkedin",
    "persona3_tier",
    "persona3_common_ground", # why this peer: shared university / background / department, or 1st degree
    "persona3_note",          # <=200 char note drafted for the peer
    "persona3_connection_sent",
    "persona3_date_sent",              # also drives the daily cap counter
    "persona3_connection_result",      # Sent / Pending / Accepted / Ignored / Withdrawn / Failed / Emailed
    "persona3_accepted_date",
    "persona3_note_sent_with_request",
    "persona3_last_action_date",
    "persona3_followup_1_message",
    "persona3_followup_1_date",
    "persona3_followup_2_message",
    "persona3_followup_2_date",
    "persona3_reply_status",
    "persona3_email_draft",
    "connection_note",        # the <=200 character note drafted (may or may not be the one actually sent)
    "note_char_count",        # integer, validated by the helper script
    "note_sent_with_request", # Yes / No - whether the note above was actually included in the sent
                               # invite (counts against the monthly note quota) vs sent as a plain connect
    "connection_sent",        # Yes / No
    "date_sent",              # YYYY-MM-DD - also drives the daily cap counter
    "connection_result",      # Sent / Pending / Accepted / Ignored / Withdrawn / Failed / Emailed
    "accepted_date",          # YYYY-MM-DD the acceptance was recorded - anchors follow-up 1
    "followup_1_message",
    "followup_1_date",
    "followup_2_message",
    "followup_2_date",
    "reply_status",           # No reply / Replied / Positive / Not interested
    "email_draft",            # fallback email drafted when the request sat unaccepted (user sends it)
    # --- dashboard fields ---
    "last_action_date",
    "notes",
]

# Columns the company-finder skill is responsible for populating.
FINDER_COLUMNS = CANONICAL_COLUMNS[:CANONICAL_COLUMNS.index("outreach_status") + 1]

# Columns the connect-outreach skill is responsible for populating.
OUTREACH_COLUMNS = CANONICAL_COLUMNS[CANONICAL_COLUMNS.index("persona_name"):
                                     CANONICAL_COLUMNS.index("last_action_date")]

# Column-name prefix for each contact slot. Slot 1 is the primary persona (persona_* /
# connection_* columns), slot 2 the second contact, slot 3 the peer.
PERSONA_PREFIXES = {"1": "", "2": "persona2_", "3": "persona3_"}


def persona_field(persona: str, key: str) -> str:
    """Map a contact slot + logical field to its real column name.

    persona_field("1", "name") -> "persona_name"     persona_field("3", "name") -> "persona3_name"
    persona_field("1", "note") -> "connection_note"  persona_field("2", "note") -> "persona2_note"
    persona_field("1", "date_sent") -> "date_sent"   persona_field("2", "date_sent") -> "persona2_date_sent"
    """
    persona = str(persona)
    if persona == "1":
        if key in ("name", "title", "linkedin", "tier"):
            return f"persona_{key}"
        if key == "note":
            return "connection_note"
        return key
    return f"persona{persona}_{key}"


# Hard limit on the connection-request note. LinkedIn allows 300 for a free-account
# note, but this project deliberately caps at 200: short notes get read and accepted
# at a much higher rate. The helper script REFUSES to write a longer note.
NOTE_CHAR_LIMIT = 200

# Default values applied to brand-new rows.
DEFAULTS = {
    "outreach_status": "Not started",
    "connection_sent": "No",
    "connection_result": "",
    "reply_status": "No reply",
}


def assert_master_path(csv_path: str) -> None:
    """Guardrail: refuse to operate on anything other than the master connections.csv.

    This is what makes the single-CSV rule foolproof - a script can never be pointed
    at a stray or mis-typed filename and silently create a second tracker.
    """
    base = os.path.basename(csv_path)
    if base != MASTER_CSV_NAME:
        raise SystemExit(
            f"REFUSING TO WRITE: '{base}' is not the master tracker.\n"
            f"There is exactly one data file in this project: {MASTER_CSV_NAME}.\n"
            f"Point --csv at <project_root>/{MASTER_CSV_NAME} and try again."
        )


def ensure_csv(csv_path: str) -> bool:
    """Create the master CSV with the canonical header if it does not exist.

    Returns True if a new file was created, False if it already existed.
    Never overwrites existing data.
    """
    assert_master_path(csv_path)
    if os.path.exists(csv_path):
        return False
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=CANONICAL_COLUMNS).writeheader()
    return True


def read_header(csv_path: str):
    """Return the existing header of the CSV, or None if the file does not exist."""
    if not os.path.exists(csv_path):
        return None
    with open(csv_path, newline="", encoding="utf-8") as f:
        return csv.DictReader(f).fieldnames


def main():
    parser = argparse.ArgumentParser(description="Create the empty master tracker CSV.")
    parser.add_argument("--path", default=os.path.join(os.getcwd(), MASTER_CSV_NAME),
                        help=f"Target path (default: ./{MASTER_CSV_NAME})")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite with an empty header-only file (DELETES existing rows).")
    args = parser.parse_args()

    assert_master_path(args.path)

    if args.force and os.path.exists(args.path):
        os.remove(args.path)

    created = ensure_csv(args.path)
    if created:
        print(f"Created empty master tracker: {os.path.abspath(args.path)} "
              f"({len(CANONICAL_COLUMNS)} columns)")
    else:
        print(f"Master tracker already exists (left untouched): {os.path.abspath(args.path)}")


if __name__ == "__main__":
    main()
