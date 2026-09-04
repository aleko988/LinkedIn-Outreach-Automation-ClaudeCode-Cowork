# LinkedIn Connect Outreach

A local, agent-run outreach tracker. Two Claude skills find the right companies, find the right person at each one, write a connection note of **200 characters or less**, send the request under a **daily cap**, and track acceptances and follow-ups. A small Flask dashboard renders it all as the weekly outreach sheet.

Everything is local: one CSV, no database, no cloud, no third-party API.

```
find companies  ->  find the person  ->  write the note  ->  send  ->  follow up
   (skill 1)         (skill 2)          (<= 200 chars)     (capped)   (day 3, day 8)
```

## What you get

| | |
|---|---|
| **`/linkedin-company-finder`** | Searches LinkedIn for companies matching your ICP, qualifies them by industry and size, records a "why now" signal, and appends them to the tracker in a weekly bucket. |
| **`/linkedin-connect-outreach`** | Walks your persona tiers to find the right person at each company, writes a note under the character limit, sends the connection request with pacing and a daily cap, and records the result. Runs the daily acceptance check and follow-up pass too. |
| **`/linkedin-message-accepted`** | Messages everyone already accepted with no message yet, or due for a follow-up - on demand, without a full find-and-send cycle. |
| **Dashboard** (port 5002) | The weekly sheet - company, profile, persona, request sent, follow up - plus a ready-to-send queue, an awaiting-message queue, a follow-up-due queue, acceptance rate, and today's remaining cap. |

## Setup

Open the project folder in Claude Code and say **"set this up"**. It installs what is missing, creates the CSV, and starts the dashboard. Or do it by hand:

```bash
pip install flask
python schema.py            # creates the one data file, connections.csv
python dashboard/app.py     # http://localhost:5002
```

For Cowork, install `dist/linkedin-connect-outreach.plugin` to get all three skills in the panel.

**You must be logged into LinkedIn** in the browser Claude controls. The skills act as you.

## Everyday use

Say it in plain language - the agent works out whether you mean "run it" or "change it":

| You say | What happens |
|---|---|
| "find me 10 new companies" | Finder runs, then outreach runs on the new rows |
| "run my weekly outreach" | The full chain, ending with a batch you approve before it sends |
| "send the drafted ones" | Sends what is queued, up to the remaining daily cap |
| "who accepted?" | Checks sent invitations and updates the tracker |
| "target founders instead" | **Settings change** - edits the config, sends nothing |
| "make the notes shorter" | **Settings change** - edits `note_char_limit` |

Anything that changes *what* gets searched or *how* the note reads is a settings change, handled through `RETARGETING.md`. It never touches rows you already have.

## Runs on a schedule, not just on demand

Cowork drives your logged-in browser locally, so it can run this unattended. Company-finding, sending, checking acceptances, and following up are separate steps that can be scheduled independently:

| Schedule | What it does | Needs you? |
|---|---|---|
| **Company finding** | Finds new companies matching your ICP and adds them to the backlog. Currently run manually/on demand rather than on a timer. | Yes, you trigger it. |
| **Daily send pass** | Works through the existing backlog: finds a persona at each company, drafts the note, sends under the daily cap and monthly note quota. Also runs the acceptance check and follow-up pass at the end. | Depends on `confirm_before_first_send` - can run fully unattended if set to `false`, otherwise waits for a one-time yes on the first batch. |
| **Daily acceptance check only** | A lighter alternative to the above: just checks LinkedIn's Connections page for new acceptances (stopping the moment it reaches someone already seen) and follows up - no sending. | No - never sends a new connection request. |

These are plain scheduled-task prompts pointed at this project - see `CLAUDE.md` for the exact wording, and for the overlap to watch for if you run more than one of these on the same timer.

## The two limits that protect your account

Both are enforced in `update_outreach.py`, which **refuses the write** rather than bending:

- **Note length** - `note_char_limit`, 200 by default. Longer notes are rejected, not truncated.
- **Daily volume** - `daily_connection_cap`, 15 by default, counted from the CSV itself. Plus a 25 to 60 second random pause between sends, one confirmation before the first batch of a run, and a full stop if LinkedIn shows its weekly invite limit.

Raising the cap much above 20 a day is how accounts get restricted. `RETARGETING.md` says so, and so should you if asked.

## How it is built

- **`schema.py`** is the only place columns are defined. Helper scripts refuse any filename that is not `connections.csv`, so a second tracker cannot be created by accident.
- **`outreach_config.json`** is the only place targeting lives. The skills contain no literal company type, persona, or tone - only `{code-words}` bound from the config at the start of every run. That is why retargeting is a one-file edit and a scheduled run can never drift back to an old campaign.
- **`.claude/skills/`** is the source of truth for both Claude Code and Cowork. The Cowork plugin is a thin launcher that reads those files live, so it never goes stale.
- **The page-ready gate** - every LinkedIn navigation polls the DOM until the content exists instead of sleeping a fixed number of seconds. That is what makes the runs repeatable.

## Files

```
schema.py                      the CSV column definition (single source of truth)
connections.csv                the ONE data file
outreach_config.json           your live campaign settings
outreach_config.example.json   the shipped default
CLAUDE.md                      how the agent should work in this project
RETARGETING.md                 how to change or add a setting
.claude/skills/                the three skills (authoritative)
dashboard/app.py               the Flask dashboard, port 5002
dist/*.plugin                  the Cowork plugin (thin launchers)
```
