---
name: linkedin-message-accepted
description: Message everyone in the tracker who accepted a connection request but has not received any message yet, or is due for their next follow-up. Use this skill when asked to message people who accepted, catch up with new connections, clear the "Awaiting message" dashboard tab, or send follow-ups now - without running a full company-finding or new-connection-sending cycle.
---

# LinkedIn Message Accepted Connections

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output - not in messages, reports, or any other text. Use a regular hyphen (-) instead.

**This is a direct, on-demand entry point into Step 10 of `.claude/skills/linkedin-connect-outreach/SKILL.md`.** That file is the single source of truth for tone, character limit, the immediate-vs-scheduled distinction, and the browser mechanics for sending a LinkedIn message - none of that is repeated here, so it can never drift out of sync with the main skill. This skill exists purely so "message the people who already accepted" can be run by itself, without needing to invoke a full find-companies-and-send-requests cycle first.

---

## The one-and-only data file rule (read first)

There is **exactly one** data file in this project: **`{project_root}/connections.csv`**. This skill only ever reads from and writes to that file, through the same `update_outreach.py` script the connect-outreach skill uses - never a second file, never a hand-edited row.

---

## Step 0 - Load the outreach config

Same as `linkedin-connect-outreach/SKILL.md`'s Step 0: load `outreach_config.json` (or the example fallback) and bind `{followup_tone}`, `{followup_2_tone}`, `{job_followup_tone}`, `{job_followup_2_tone}`, `{followup_scope}`, `{cv_attachment}`, `{peer_followup_tone}`, `{pitch_link}`, `{about_me}`, `{followup_char_limit}`, `{followup_auto_send}`, `{note_must_avoid}`, `{note_signoff}`, `{pause_between_sends_seconds}`. If neither config file exists, stop and tell the user it's missing.

## Step 1 - Find who is due

```bash
python "{project_root}/.claude/skills/linkedin-connect-outreach/scripts/update_outreach.py" --due-followups
```

This returns one entry per **contact** (a company with several accepted people can produce several entries), each tagged `persona: "1"`, `"2"` or `"3"` (the peer) and `immediate_no_note: true/false`. It already includes:
- Anyone who accepted a **plain connect** (no note delivered at request time) - due immediately, `immediate_no_note: true`.
- Anyone whose scheduled follow-up window has arrived - `immediate_no_note: false`. Follow-up 1 is due `followup_1_days` after the acceptance (0 = same day), follow-up 2 is due `followup_2_days` after follow-up 1.

It never returns anyone who already replied. If the list is empty, report that and stop - there is nothing to do.

## Step 2 - Write and send each message

**Follow `linkedin-connect-outreach/SKILL.md`'s Step 10 exactly** for every entry from Step 1: the tone rules (immediate vs scheduled wording), the pitch-link and peer rules, the `--followup [1|2] --message "..." [--persona 2|3]` recording command, and - only if `{followup_auto_send}` is true - the browser mechanics for actually sending it (profile navigation, page-ready gate, Message button, compose box, Send). Pause `{pause_between_sends_seconds}` between each person, same anti-burst reasoning as sending connection requests.

If `{followup_auto_send}` is false, record the message and stop there - it shows up in the dashboard with a Copy button for the user to send by hand.

## Step 3 - Report

- How many people were messaged (split: immediate no-note catch-ups vs scheduled follow-ups)
- How many are staged in the dashboard awaiting the user (if `{followup_auto_send}` is false)
- Anyone who replied since the last check, if noticed in passing

---

## What this skill does NOT do

- **Does not check LinkedIn's Connections page for brand-new acceptances.** That is Step 8 of `linkedin-connect-outreach/SKILL.md` (the daily acceptance-check pass, Step 11) - run that first (or rely on the daily schedule) if new acceptances haven't been picked up yet. This skill only acts on acceptances already recorded in `connections.csv`.
- **Does not find new companies, find new people, or send new connection requests.** For that, use `linkedin-company-finder` and `linkedin-connect-outreach`.

## Edge cases

- **Nobody due**: report it plainly and stop - not an error.
- **The script refuses a message as too long**: rewrite it shorter, same as any other note in this project - never truncate or edit the CSV by hand.
- **Someone replied since the last check**: record `reply_status` (see `linkedin-connect-outreach/SKILL.md` Step 10) instead of sending another message, and stop that person's sequence.
- **Login wall or CAPTCHA**: stop immediately, same as every other skill in this project - never attempt to solve a CAPTCHA.
