---
name: linkedin-night-run
description: The scheduled NIGHT run of the job search - check which connection requests were accepted today, and send each new connection a short message (who the user is, the specific role they are reaching out about, their CV attached as a PDF, and a request for feedback); also sends the reminder when one is due. Use when the night schedule fires, or when the user asks to "check who accepted and message them".
---

# LinkedIn Night Run (check acceptances -> message them)

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output. Use a regular hyphen (-) instead.

This skill is an **orchestrator only**. All logic lives in `{project_root}/engine/OUTREACH_STEPS.md` (the outreach engine); this file only says which of its steps to run, in which order. It never finds jobs and never sends new connection requests.

(`{project_root}`: the folder containing `schema.py`; `python "{project_root}/engine/update_outreach.py" --print-root` prints it.)

---

## Step 1 - Record today's acceptances

Run outreach **Step 8** in full (8a to 8d): read LinkedIn's Connections page (sorted "Recently added") only down to the last-checked cutoff, match new connections against `persona_linkedin` / `persona2_linkedin` / `persona3_linkedin`, record each with `--persona N --result Accepted` (this stamps `accepted_date`), then advance the cutoff with `--mark-checked`.

## Step 2 - Message who is due

Run outreach **Step 10**. With the current config, `--due-followups` returns:
- everyone who **accepted today** (follow-up 1 is due the same day), and
- anyone whose first message went out `followup_2_days` ago with no reply (the reminder).

For job rows, write follow-up 1 in `job_followup_tone`: thanks for connecting, who the user is, the exact role (with the job link), the CV **attached as the PDF in `cv_attachment`** (Step 10's "Attaching the CV" - falls back to `pitch_link` only if attaching fails), and a request for feedback. Respect `followup_char_limit`, run it through `humanizer` if available, record it with `--followup 1 --message "..." --persona N`, and, if `followup_auto_send` is true, send it with the Message button exactly as Step 10 describes, pausing between messages.

`followup_scope` keeps legacy company-only rows out of this list - never message them by hand.

## Step 3 - Fallback email drafts

Run outreach **Step 12** (drafts only - this never sends email).

## Step 4 - Report

New acceptances today (who, which job), messages sent vs only drafted, reminders sent, anyone who replied (record `reply_status` so their sequence stops), and fallback emails drafted.

---

## Hard stops

Login wall, CAPTCHA or security checkpoint: stop, keep what is already recorded, report. If the Message button is missing for someone recorded as Accepted, do not send a connection request or InMail instead - note it in the report.
