---
name: linkedin-morning-run
description: The scheduled MORNING run of the job search - find today's new analyst job postings that fit the CV and that the user can take from their country, then find each job's department hiring manager and recruiter and send them connection requests under the daily cap. Use when the morning schedule fires, or when the user asks to "run the morning job search", "find today's jobs and send requests".
---

# LinkedIn Morning Run (find jobs -> send connection requests)

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output. Use a regular hyphen (-) instead.

This skill is an **orchestrator only**. It contains no search, note or send logic of its own - it runs the job-finder skill and then the outreach engine, in order, so nothing here can drift out of sync with them:

- `{project_root}/.claude/skills/linkedin-job-finder/SKILL.md`
- `{project_root}/engine/OUTREACH_STEPS.md` (the outreach engine)

(`{project_root}`: `python "{project_root}/engine/update_outreach.py" --print-root`, or the folder containing `schema.py`.)

It runs unattended on a timer. `confirm_before_first_send` in `outreach_config.json` decides whether it may send without asking; if that is `true` and nobody is there to answer, it **drafts only** (outreach Step 6) - never send unconfirmed.

---

## Step 1 - Find today's jobs

Follow `linkedin-job-finder/SKILL.md` in full (Steps 0 to 6). It stops at `jobs_per_run` kept jobs and refuses to run if the CV profile or the user's country is missing from the config - if it stops for that reason, report it and end the run (there is nothing to send).

## Step 2 - Contact each job's hiring manager and recruiter

Follow `engine/OUTREACH_STEPS.md` **Steps 0 to 9** for the rows without a persona yet - job rows first (Step 1 there orders them), using **Step 3j** to find the department hiring manager and recruiter for each job. Every hard limit there applies unchanged: the note character limit, the daily cap (`--cap-check` before every send), the monthly note quota (plain connects once it is spent), the pause between sends, and stopping on a weekly-invite-limit modal.

**Do not** run Step 3b (peers) unless `peer_enabled` is true, and do not run the follow-up pass here - messaging people who accepted is the night run's job (`linkedin-night-run`).

## Step 3 - Report

One short report: jobs found (and how many were rejected for location/eligibility vs CV fit), then per job - company, title, department, who was contacted (tier label shows whether it was the job poster, a department contact, or a general fallback), sent with a note or plain - and the remaining daily cap and monthly note quota.

---

## Hard stops

Login wall, CAPTCHA, security checkpoint, or LinkedIn's weekly invitation limit: stop the whole run immediately, keep everything already recorded, and say so in the report. Never work around them.
