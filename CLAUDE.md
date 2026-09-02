# LinkedIn Connect Outreach - Guide for Claude

## Read me first - house rules (Claude Code AND Cowork)

**Any agent working in this project - Claude Code or Cowork - must follow these seven rules before doing anything else.** They exist because the two tools share one folder, and inconsistency between them (re-running setup, rebuilding the plugin, making a second data file) is the main thing that breaks this project.

1. **Setup is once.** If `setup_complete.json` exists in the project root, setup is already done - do **not** re-run it.
2. **The plugin is an intentional thin launcher.** The file in `dist/` is short *by design*; it reads the project's live skills at runtime, so it is never stale. **Never "rebuild" or replace it with full skill content** - that breaks project-folder discovery.
3. **One data file, ever.** There is exactly one: `connections.csv`. Never create a second CSV, never rename it.
4. **Targeting lives in `outreach_config.json`.** To change what companies get found, who gets contacted, or how the note reads, edit `outreach_config.json` - never hard-code values into the skills. See `RETARGETING.md`.
5. **Retargeting is forward-only.** Changing the campaign never deletes or re-filters existing rows in `connections.csv` - old companies stay, and notes already sent stay exactly as sent.
6. **The two hard limits are absolute.** A connection note is at most the configured `note_char_limit` (200 by default), and at most `daily_connection_cap` requests go out per day. Both are enforced in `update_outreach.py`, which **refuses** the write rather than truncating or overshooting. Never work around either, and never work around a LinkedIn limit modal.
7. **Users speak casually - recognize settings changes.** The people using this project are not technical and did not build it. If the user says anything that sounds like they want to change *who* gets found, *who* gets contacted, or *how* the note reads, **that is a settings change** - do not run a search or send anything. Confirm in plain language, then follow `RETARGETING.md`. See **"Recognizing a settings change"** below.

Everything below expands on these. When in doubt, these seven win.

---

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere - not in connection notes, follow-ups, reports, summaries, or any other output. Always use a regular hyphen (-) instead. This rule applies across all skills and all generated text, without exception.

This is a LinkedIn connection-outreach tracker with a local web dashboard and two Claude Code skills (find companies + connect to the right person there). It ships tuned for **data teams at companies hiring analysts** but is built to be retargeted to any ICP.

## The most important rule: ONE data file

There is **exactly one** data file in this project: **`connections.csv`** in the project root.

- **Never** create a second CSV. Never write outreach data to any other filename. Never write to a template, backup, or "example" file - there is no example file.
- The column layout is defined **once** in `schema.py`. Do not invent columns or reorder them. If a column genuinely needs to change, edit `schema.py` and nothing else.
- Both skills write through helper scripts (`append_companies.py`, `update_outreach.py`) that **physically refuse** any `--csv` path whose filename is not `connections.csv`, and that always preserve the existing header.
- If `connections.csv` does not exist, create it with `python schema.py`. Do not hand-roll a CSV.

## The two safety limits (read before sending anything)

This project drives the user's **real LinkedIn account**. Two limits protect it, and both are enforced in code, not left to judgement:

| Limit | Config key | Enforced by |
|---|---|---|
| Connection note length | `outreach.note_char_limit` (200) | `update_outreach.py` **refuses** a longer note instead of truncating it |
| Requests per day | `outreach.daily_connection_cap` (15) | `update_outreach.py --cap-check` before every send, and `--mark-sent` refuses past the cap |

Additional rules the outreach skill must follow:
- **Pause `pause_between_sends_seconds` (25 to 60s) between sends.** A burst is the pattern LinkedIn flags.
- **`confirm_before_first_send` is on by default:** show the user the batch and get a yes once per run, then send the whole batch without asking again.
- **A scheduled run with nobody available to confirm drafts only.** It leaves rows at `Note drafted` and reports that they await approval. Never send unconfirmed.
- **If LinkedIn shows a weekly invite limit modal, stop the entire run.** Never dismiss and retry, never route around a platform limit.
- **Never click "Send without a note."** If the note field cannot be filled, abandon that person and record `Failed`.

## How this project is used: Claude Code + Cowork share ONE folder

- **Claude Code** does the one-time setup and the on-demand work ("find me 10 new companies", "open the dashboard"). It auto-loads the skills from `.claude/skills/` whenever the project folder is open.
- **Cowork** runs the recurring weekly prospecting run locally (it drives the user's logged-in browser and writes to the same `connections.csv`), using the plugin in `dist/linkedin-connect-outreach.plugin`. The plugin skills are thin launchers that discover the project root and delegate to the authoritative `SKILL.md` files in `.claude/skills/`.

The `.claude/skills/<name>/` folders are the **single source of truth**. The plugin in `dist/` is a thin wrapper - it does not duplicate skill logic.

> **Do NOT "rebuild" the plugin into a full-content copy of the skills.** The plugin SKILL.md files are intentionally short launchers; their brevity is by design, not staleness. They read the project's live `SKILL.md` at runtime, so they are always current - including every knob change and skill edit - and **never need rebuilding**. The only time `build_plugin.py` is re-run is if the launcher *shape* itself changes.

## "Set this up" trigger

If the user says anything like "set this up", "get me started", "initialize this", or "install this" - run the setup steps below in order.

## FIRST: check if setup is already complete

**Before running ANY setup step, check for a `setup_complete.json` file in the project root.**

- **If it exists** -> setup is already done on this machine. Do NOT re-run setup. Tell the user who set it up and when, then go straight to next actions: find companies, run outreach, or open the dashboard (http://localhost:5002). **If you are running in Cowork, still present `dist/linkedin-connect-outreach.plugin` for installation** - Claude Code does not install the Cowork plugin.
- **If it does NOT exist** -> fresh setup. Run the steps below in order. Every step is idempotent, so a re-run is safe.
- **Write the marker only at the very END of a fully successful setup**, with `set_up_by`, `timestamp`, `install_path`, and `steps_completed`.

## When a new user opens this project

### 0. Confirm the install location (so Cowork and Claude Code share it)

This project should live inside the user's **Cowork files location**, under `Projects/`. That location is user-configurable, so **discover it - never hardcode it.** Read `coworkUserFilesPath` from the Cowork desktop config:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\\Claude\\claude_desktop_config.json`

Ideal location is `<coworkUserFilesPath>/Projects/linkedin-connect-outreach`. If the project is elsewhere and that path exists, offer to move it. If the config or key does not exist, the current location is fine.

### 1. Check prerequisites (run the checks yourself - install what is missing)

Detect the OS with `uname -s 2>/dev/null || echo "Windows"`.

- **Windows**: check `git --version`, `python --version`, `pip --version`, `pip show flask`. Install missing pieces with `winget install Git.Git` / `winget install Python.Python.3.12` / `python -m ensurepip --upgrade` / `pip install flask`. If `winget` is unavailable, give the user a download link and ask them to say "continue" when done.
- **macOS/Linux**: check `xcode-select -p`, `which brew`, `python3 --version`, `pip3 --version`, `pip3 show flask`. Install with `xcode-select --install`, the Homebrew installer, `brew install python3`, `python3 -m ensurepip --upgrade`, `pip3 install flask`.

Only involve the user when a step needs their physical action (a dialog to click, a password to type).

### 2. Create their one data file
```bash
python schema.py
```
This creates an empty `connections.csv` with the correct columns. It will not overwrite an existing file.

### 3. Skills

**Claude Code:** the two skills in `.claude/skills/` auto-load. The user already has:
- `/linkedin-company-finder` - finds new companies matching the ICP
- `/linkedin-connect-outreach` - finds the right person, writes the note, sends the request

**Cowork:** present `dist/linkedin-connect-outreach.plugin` with `present_files` so the user can click Install.

**Prerequisite to flag:** the skills drive a browser as the user, so they must be **logged into LinkedIn** in the browser Claude controls. If a login wall appears, stop and ask them to log in.

### 4. Start the dashboard
```bash
python dashboard/app.py      # any OS
bash dashboard/run.sh        # macOS/Linux
dashboard\\run.bat            # Windows
```
Then tell the user to open **http://localhost:5002**.

### 5. Confirm the send settings out loud

Before the first outreach run, tell the user in plain language what will happen: "I will send up to 15 connection requests a day, each with a note of 200 characters or less, and I will show you the batch before the first send." Get their agreement. If they want different numbers, that is a settings change - follow `RETARGETING.md`.

### 6. Write the setup-complete marker (LAST, only after every step above succeeded)

## How the two skills work together

1. **Company finder** searches LinkedIn for companies matching the ICP and **appends** them as new rows to `connections.csv` (finder columns filled, outreach columns blank). It de-dups by company slug using `seen_companies.txt` and stamps a `week` bucket.
2. **Connect outreach** scans `connections.csv` for **any row where `persona_name` is blank** - regardless of `outreach_status` or how long ago it was added - finds the right person per the configured tiers, writes a note of 200 characters or less, sends the request under the daily cap, and records the result.
3. The outreach skill also runs the **follow-up pass**: accepted connections with no reply get follow-up 1 on day 3 and follow-up 2 on day 8 (both configurable).
4. The **dashboard** reads `connections.csv` and renders it as the weekly sheet: company, profile, persona, request sent, follow up.

## Scheduling (the weekly prospecting run)

A scheduled run needs a **logged-in LinkedIn browser** and the **local** `connections.csv`, so it must run **on the user's machine**, not as a cloud agent.

- **Cowork scheduled task (runs locally).** Example task prompt: *"Use the LinkedIn Company Finder skill to find new companies. When that finishes, use the LinkedIn Connect Outreach skill to find the right person at each and draft notes. Give a short combined summary."*
- **On-demand in Claude Code.** The user opens the project and says *"run my weekly outreach"*.

**Ordering:** the finder must finish before outreach starts. A single chained task guarantees this. Outreach is idempotent and only touches rows without a persona.

**Always required:** a logged-in LinkedIn session, the machine awake, and - while `confirm_before_first_send` is on - someone available to approve the batch. Without that approval a scheduled run correctly stops at drafts.

## Recognizing a settings change (read this - users speak casually)

**The people using this project did not build it and do not know the config structure.** Recognize these as settings changes, confirm what they mean, and follow `RETARGETING.md`. Do not run a search or send anything when the user is asking for a settings change.

- **Settings change** = the user wants to change *what kind of company* gets found, *who* gets contacted, *how* the note reads, or *how many* go out. **Action:** confirm in plain language, then follow `RETARGETING.md`.
- **Run request** = execute with the current settings ("find new companies", "run my weekly outreach", "send the drafted ones"). **Action:** run the relevant skill.

If unsure, ask: "Do you want me to change your settings to X, or run with your current settings?"

**Finder settings** (`finder` block):
| User says something like... | Config key |
|---|---|
| "Look for agencies instead" / "find fintech companies" | `search_keywords` + `industry_filter` |
| "Search Germany" / "only companies in London" | `location` |
| "Only companies under 200 people" / "bigger companies" | `company_size_allow` |
| "Find more per run" / "just 5 a week" | `companies_per_run` |
| "Skip this company" / "block that agency" | `blocklist_companies` |
| "Search posts instead of jobs" | `search_mode` |

**Outreach settings** (`outreach` block):
| User says something like... | Config key |
|---|---|
| "Target founders" / "reach the CTO instead" / "not recruiters" | `persona_tiers` |
| "Contact two people per company" | `personas_per_company` |
| "Make the notes shorter" / "150 characters max" | `note_char_limit` |
| "Less salesy" / "more casual" / "stop sounding like a template" | `note_tone` + `note_must_avoid` |
| "Send more per day" / "slow down" | `daily_connection_cap` |
| "Stop asking me before sending" | `confirm_before_first_send` |
| "Follow up sooner" / "no follow-ups" | `followup_1_days` / `followup_enabled` |

**Full ICP change** (e.g. "target marketing agencies, reach the owner"): update `campaign_label`, `finder.search_keywords`, `finder.industry_filter`, `finder.company_size_allow`, and `outreach.persona_tiers` together. See `RETARGETING.md`.

## Notes for Claude

- **"Start the dashboard" / "open localhost":** run `python dashboard/app.py`, then tell the user to open http://localhost:5002.
- **Port:** 5002, so it can run alongside the job-search dashboard on 5001. Change it with the `PORT` env var.
- **OS detection:** Windows -> `python` + `pip`. macOS/Linux -> `python3` + `pip3`.
- All data stays local - no cloud, no database, no third-party API. Everything is in `connections.csv`.
- The skills always write to `connections.csv` in the project root (one level above `dashboard/`).

## File structure

```
.
├── schema.py                   <- single source of truth for CSV columns
├── connections.csv             <- the ONE data file (gitignored; create via schema.py)
├── RETARGETING.md              <- how to change/add campaign knobs
├── outreach_config.example.json <- shipped default knobs (committed; the fallback)
├── outreach_config.json        <- live user settings (gitignored; skills load this)
├── seen_companies.txt          <- finder de-dup cache (gitignored)
├── setup_complete.json         <- per-machine setup marker (gitignored)
├── .claude/skills/             <- AUTHORITATIVE skills (auto-load in Claude Code)
│   ├── linkedin-company-finder/   (SKILL.md + scripts/append_companies.py)
│   └── linkedin-connect-outreach/ (SKILL.md + scripts/update_outreach.py)
├── dist/
│   └── linkedin-connect-outreach.plugin  <- Cowork plugin (present for install)
└── dashboard/
    ├── app.py                  <- Flask dashboard (port 5002)
    └── run.sh / run.bat        <- launchers
```

## CSV columns (defined in schema.py)

| Group | Columns |
|---|---|
| Finder | company_id, date_added, week, company_name, linkedin_company_url, company_tagline, industry, company_size, hq_location, company_website, signal, why_relevant, company_source, outreach_status |
| Outreach | persona_name, persona_title, persona_linkedin, persona_tier, persona_location, persona_mutuals, connection_note, note_char_count, connection_sent, date_sent, connection_result, followup_1_message, followup_1_date, followup_2_message, followup_2_date, reply_status |
| Dashboard | last_action_date, notes |
