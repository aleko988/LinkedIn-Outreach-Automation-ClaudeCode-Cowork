# Retargeting the campaign (change or add knobs on the fly)

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output. Use a regular hyphen (-) instead.

This guide is the **single entry point** for changing what the two skills look for and say. It works the same in **Claude Code** and **Cowork** (the Cowork plugin launchers delegate to the same `.claude/skills/` files, which read the same config this guide edits).

Use this whenever the user wants to **change** the campaign (different companies, different person, different note, different send volume) **or add** something new (a new filter, a new knob, a new captured field, a new persona tier). For a brand-new knob, jump to **"Adding a brand-new knob: the full sync checklist"**.

---

## The model: one config file is the source of truth

All the knobs live in **`outreach_config.json`** in the project root. **Both skills load it at the start of every run** - scheduled or on-demand - and use only its values for every decision. The values written inline in the skills are just labeled *defaults*; the loaded config always wins.

This is what makes retargeting a **one-way street**: change the config once, and every future run follows the new targeting. A scheduled task can never drift back to a previous ICP, because it reads the same config the user just edited. The dashboard reads the same file and shows a "Current campaign settings" panel, so the user always sees what the next run will do.

**Files:**
- `outreach_config.json` - the live, user-edited settings. **Gitignored** (personal targeting never ships).
- `outreach_config.example.json` - the shipped default. Committed. The fallback when no live config exists, and the template to copy from.

So retargeting = **edit `outreach_config.json`** (create it by copying the example if it does not exist yet).

---

## Three rules that never change when retargeting

1. **Forward-only. Never touch existing rows.** Changing the config affects **future** runs only. Companies already in `connections.csv` stay exactly as they are, and notes already sent stay exactly as sent. Do not delete, re-filter, or "clean up" old rows to match new targeting.
2. **Still exactly one data file.** `connections.csv` stays the only data file, and its filename never changes (it is the guardrail constant `MASTER_CSV_NAME` in `schema.py`).
3. **The safety limits stay enforced in code.** You may change `note_char_limit` and `daily_connection_cap` *values*, but never remove the enforcement, never let a skill write a note past the limit, and never raise the cap without telling the user the risk. Above roughly 20 requests a day, account restrictions become likely - say so plainly before making the change.

---

## Users speak casually - translate, do not ask them to learn the config

They will never say "change the `persona_tiers` key." They will say "reach the CTO instead" or "these notes sound like a robot." **Translate their plain language into the correct config key, confirm your understanding, and make the edit.**

If the user already told you what they want, do NOT ask them to pick a knob - just confirm: "I will target founders instead of Heads of Data at every company. That sound right?" Then do it.

**Which block does their request touch?**
- **What companies get found** (keywords, location, size, industry, volume) -> `finder` block
- **Who gets contacted and what the note says** (tiers, tone, limits, cap, follow-ups) -> `outreach` block
- **Change the ICP entirely** -> **both blocks** - update `campaign_label`, `finder.search_keywords`, `finder.industry_filter`, `finder.company_size_allow`, and `outreach.persona_tiers` together.

See `CLAUDE.md` -> **"Recognizing a settings change"** for a full table of example phrases.

---

## How to run a retargeting session

1. **Read the current `outreach_config.json`** so you know the starting point.
2. **Confirm your understanding** in plain language. If the request is vague, ask one short clarifying question. Do not present a list of config keys.
3. **Confirm the new values** before editing ("So: agencies with 2 to 50 people, contacting the owner, notes under 150 characters, 10 a day - correct?").
4. **Decide if the CSV is affected** using the decision rule below. Almost everything is config-only.
5. **Edit `outreach_config.json`** (create it from the example first if needed). Update `last_updated` to today. For any knob you want visible in the dashboard, set a human-readable `"<key>_label"`.
6. **Report back** what changed, confirm old rows were left untouched, and say what the next run will do.

---

## Does this change the CSV? (decision rule)

| The user wants to... | CSV change? | What to do |
|---|---|---|
| Change keywords / location / industry / size / volume | **No** | Edit `outreach_config.json` only. |
| Change persona tiers / note tone / limits / cap / follow-up timing | **No** | Edit `outreach_config.json` only. |
| Adjust an **existing** list or value (block a company, add a signal word, change tone) | **No** | Edit the relevant key. One-file change. |
| Add a **brand-new knob** (a key that does not exist yet) | **No** (usually) | Follow the sync checklist below. |
| **Capture a brand-new field** (e.g. record employee headcount growth, add a second persona per company) | **Yes** | Follow **Additive change: new captured field** below. |

The only thing that changes the CSV is **adding a new captured field** (a new column). Even then it is **additive** - it appends a blank column and never deletes existing rows.

---

## Config Reference (every knob, by config key)

### `finder` block - job-first search (`linkedin-job-finder`)
| Config key | Controls | Shipped default |
|---|---|---|
| `job_titles` / `job_title_exclude` | titles to search, and title words that rule a posting out (seniority, internships) | analyst titles / Principal, Director, Manager... |
| `job_markets` | list of `{label, location, geoId}` searched one after another | United States, European Union |
| `job_remote_only` / `job_posted_within` | remote filter (`f_WT=2`) and recency (`r86400` = 24h) | `true` / `r86400` |
| `jobs_per_run` | new jobs kept per run | `10` |
| `job_company_cooldown_days` | skip a company that got a job row this recently, so its recruiters are not flooded | `30` |
| `candidate_country` / `work_authorization` | where the user lives and what they can legally accept - drives the location-eligibility check | blank / remote only, no sponsorship |
| `eligibility_reject_phrases` / `eligibility_accept_phrases` | posting text that rules a job out (residency, work-permit, W2) or in (worldwide, EMEA, contractor) | see config |
| `cv_profile` / `min_cv_fit` | the user's skills, years, seniority, languages, domains, and the fit bar | blank - filled from the CV |

### `finder` block - company search (`linkedin-company-finder`, legacy)
| Config key | Controls | Shipped default |
|---|---|---|
| `search_keywords` | the `keywords=` param (URL-encoded, `+` between words) - a single string, or a **list** of role queries run one after another in the same pass | `Data+Analyst` |
| `search_mode` | which LinkedIn surface to search: `jobs` (companies hiring - strongest signal), `companies`, or `posts` | `jobs` |
| `location` | the `location=` param | `Worldwide` |
| `industry_filter` | which industries qualify; empty list means any | see config |
| `company_size_allow` | which employee bands qualify; empty list means any | 11 to 5K |
| `companies_per_run` | how many NEW companies to add per run, across all keywords combined | `10` |
| `pages_to_scan` | how many result pages to page through, per keyword | `2` |
| `remote_only` | add LinkedIn's remote-jobs filter (`f_WT=2`) to the search | `false` |
| `hq_location_filter` | which company HQ locations qualify (loose text match against the extracted `hq_location`); empty means any | `[]` |
| `require_company_page` | drop anything with no real LinkedIn company page | `true` |
| `blocklist_companies` | staffing agencies and aggregators to skip | see config |
| `blocklist_phrases` | hidden-employer phrases to skip | see config |
| `signal_keywords` | words that mark a "why now" signal worth recording | see config |
| `skip_if_already_in_tracker` | skip slugs already in `seen_companies.txt` | `true` |

### `outreach` block
| Config key | Controls | Shipped default |
|---|---|---|
| `persona_tiers` | who to contact, in priority order (`type`, `who`, `keywords`, and optionally a per-tier `function_code`) | Recruiter/TA / Data-Analytics Hiring Manager / Founder or CTO |
| `personas_per_company` | how many people per company - `1` or `2` (the CSV has two contact slots; see "Adding a new persona tier" below) | `1` |
| `function_code` | fallback `facetCurrentFunction=` on the People tab when a tier has no `function_code` of its own | `25` |
| `small_company_threshold` / `small_company_tier_override` | below N employees, jump straight to this tier (a 20-person company has no Head of Data) | `50` / tier `4` |
| `prefer_second_degree` / `prefer_same_location` | tie-breakers when several people match | `true` / `false` |
| `skip_if_no_persona` | `keep` or `delete` a company where nobody matched | `keep` |
| **`note_char_limit`** | **hard limit on the connection note - enforced in code** | `200` |
| `note_tone` | how the note reads | warm, direct, peer-to-peer |
| `note_must_include` | things every note must contain | first name + one concrete detail |
| `note_must_avoid` | banned phrases | "hope this finds you well", buzzwords, em dashes |
| `note_ask` | what the note asks for | just connect, no meeting, no link |
| `note_signoff` | signoff style | `none` |
| `note_example` | a worked reference note matching the current shape and length - the skill copies its structure, never its literal words | see config |
| **`note_monthly_limit`** | **max connection requests per calendar month that may include a note - enforced in code, for accounts without LinkedIn Premium** | `5` |
| **`daily_connection_cap`** | **max requests per day - enforced in code** | `15` |
| `pause_between_sends_seconds` | random pause range between sends | `[25, 60]` |
| `confirm_before_first_send` | ask the user once per run before the first send | `true` |
| `stop_on_weekly_invite_limit` | stop the whole run when LinkedIn caps the week | `true` |
| `followup_enabled` | run the follow-up pass at all | `true` |
| `followup_auto_send` | `true` = the skill sends the follow-up itself (LinkedIn messages to existing connections aren't quota-limited, unlike connection notes); `false` = draft and stage it in the dashboard only, for the user to send by hand | `false` |
| `followup_1_days` / `followup_2_days` | follow-up 1 is due this many days after the **acceptance** (`accepted_date`; 0 = same day), follow-up 2 this many days after **follow-up 1**. Someone who accepted a *plain* connect (no note) is always due for follow-up 1 right away (`immediate_no_note: true`) | `0` / `4` |
| `followup_char_limit` | max length of a follow-up message | `400` |
| `followup_tone` | how follow-ups read | short, useful, one clear ask |
| `candidates_to_inspect` | how many matching profiles to open per track before picking one | `4` |
| `recruiter_focus_keywords` | words in a recruiter's headline / About / recent posts that show they hire for your field | data, analytics, BI, tech... |
| `peer_enabled` | also connect with one peer per company (slot 3, `persona3_*`) | `true` |
| `peer_tier` | who counts as a peer (`type`, `who`, `keywords`, `function_code`) | Data Analyst / BI Analyst / Analytics Engineer |
| `peer_common_ground` | the user's `university`, `background`, `past_companies`, `home_country` - used to find peers with a shared link. Blank fields are skipped | all blank |
| `peer_ask` / `peer_note_example` / `peer_followup_tone` | what the peer note asks (a 15-minute chat), its reference shape, and how the post-accept messages read (call, then the referral loop) | see config |
| `pitch_link` | CV / video pitch URL (e.g. Reslink) put in the first post-accept message to recruiters and hiring managers - never in a note, never to peers | blank |
| `job_contacts` | for job rows: per slot, the `role`, `department_keywords` (with a `{job_department}` placeholder) and `general_keywords` fallback | slot 1 Hiring Manager, slot 2 Recruiter |
| `job_note_example` / `job_followup_tone` / `job_followup_2_tone` | the note and the post-accept messages for job rows (who you are, the role, CV link, ask for feedback) | see config |
| `cv_attachment` | absolute path to the CV PDF attached to the first message after acceptance on job rows (falls back to `pitch_link` if the upload fails) | blank |
| `followup_scope` | `job_rows` = only rows with a `job_id` get follow-ups and fallback emails; `all` = every row | `all` |
| `no_accept_email_days` / `emails_per_run` / `email_tone` | after this many days unaccepted, draft a fallback email (at most N per run) for the user to send themselves | `5` / `10` |

### Top level
| Config key | Controls |
|---|---|
| `campaign_label` | friendly name shown in the dashboard panel |
| `last_updated` | date of the last retarget (set this on every edit) |
| `custom_fields_added` | list of any new CSV columns added |

### LinkedIn function codes (for `function_code`)
`25` Research/Analytics cluster · `13` Engineering · `12` HR/Recruiting · `15` IT · `17` Marketing · `4` Business Development · `10` Finance · `20` Product Management. If unsure, omit the function filter and rely on `keywords` - the search still works, just less precisely.

---

### `about_me` and `followup_2_tone` (outreach block)

| Key | What it does | Default if absent |
|---|---|---|
| `about_me` | One first-person line naming what the user actually does. Injected into the connection note (Step 5, compressed) and the post-acceptance message (Step 10, in full). Without it every message is about the company only, and the reader has nothing to reply to. | Empty - the skill writes as if the knob did not exist and never invents a background. |
| `followup_2_tone` | How the day-8 follow-up reads, separately from follow-up 1. | Falls back to `followup_tone`. |

---

## Adding a brand-new knob: the full sync checklist

A knob is only "wired" when **every** place that needs to know about it has been updated. Touch these in order; skipping one is how drift happens.

| # | File | What to add | Why it is required |
|---|---|---|---|
| 1 | **`outreach_config.example.json`** | The new key, **plus a `"<key>_label"` companion** if it should show in the dashboard. Put it under the right block (`finder` or `outreach`). Add a note to `_README` if the behavior is non-obvious. | This is the committed default **and** the fallback a fresh clone uses. |
| 2 | **`.claude/skills/<skill>/SKILL.md`** | (a) add the key to the **Step 0 "bind these code-words" table**; (b) reference it only as a `{code-word}` in the step that uses it - never inline a literal; (c) state the **default-if-absent** behavior. | The skill only sees config keys it binds in Step 0. A key the skill never binds is dead config. This is the step most often forgotten. |
| 3 | **`RETARGETING.md`** (this file) | A row in the Config Reference for the new key. | So the next retarget knows the knob exists. |
| 4 | **`dashboard/app.py`** -> `campaign_config_summary()` *(usually automatic)* | If the knob has a `"<key>_label"`, the panel **auto-displays it** - nothing to edit. Only touch this file for a custom icon, a fixed position, or special formatting (chips): add it to `_FINDER_KNOBS` / `_OUTREACH_KNOBS`. | The panel is how the user confirms what the next run will do. |
| 5 | *(only if the knob enforces a limit)* **`update_outreach.py`** | Read it in `load_config()` and enforce it there. | A limit that lives only in a SKILL.md is advice, not a guardrail. Anything protecting the user's account belongs in the script. |
| 6 | *(only if the knob captures new per-company data)* **`schema.py` + migration** | A new CSV column. | Follow **Additive change: new captured field** below. |

### The drift traps (read these every time)

- **The live config is gitignored and per-user.** `outreach_config.json` already exists on the user's machine and will **not** automatically gain your new key. So (a) the skill and scripts must read the key with a safe default (`cfg.get("the_key", <default>)`) so existing configs keep working, **and** (b) when the user actually asks for the knob, write it into their live `outreach_config.json` too.
- **Never inline a value in a skill.** Anything targeting-specific stays a `{code-word}` resolved from config.
- **Never rebuild the Cowork plugin for a knob.** The launchers read the live `.claude/skills/` files at runtime, so a knob is picked up automatically. Rebuilding re-introduces drift.
- **Forward-only and one data file still hold.**

### Verify the wiring before reporting done

1. **Config loads:** `python -c "import json; print(json.load(open('outreach_config.json'))['outreach'])"` prints the new key.
2. **Skill binds it:** the `{code-word}` appears in both the Step 0 table and the step that uses it.
3. **Panel shows it:** load the dashboard and confirm the row renders. A knob with a `"<key>_label"` appears automatically.
4. **(If it is a limit)** try to violate it and confirm the script refuses.
5. **(If a column was added)** confirm `python schema.py` reports the new count and a test append lands the value in the right column.

---

## A note on raising the daily cap (read before doing it)

`daily_connection_cap` is the one knob where the user's request and their interest can diverge. If they ask for 50 or 100 a day:

1. **Say plainly what happens.** LinkedIn restricts accounts that send at that rate, and a restricted account cannot be un-restricted on request. The weekly invite ceiling for most accounts sits near 100 to 200 total.
2. **Offer the better lever.** Acceptance rate is what actually moves results, and it comes from a sharper ICP and a more specific note, not more volume. Suggest tightening `industry_filter` or `persona_tiers` instead.
3. **If they still want it, make the change** - it is their account - but set it to the number they asked for, tell them what you set, and note the risk once. Do not argue twice, and do not quietly set a different number than they asked for.

Never raise the cap on your own initiative, and never bypass the enforcement in `update_outreach.py` as a shortcut.

---

## Additive change: new captured field (the only CSV-touching case)

If the user wants to **start capturing a field that does not exist yet** (e.g. "also record their mutual connections", or add a second persona `persona2_*`):

1. **Add the column to `schema.py`** - insert the field into `CANONICAL_COLUMNS` (and into `FINDER_COLUMNS` or `OUTREACH_COLUMNS` as appropriate). This is the only file where columns are defined.
2. **Migrate the existing `connections.csv` in place - never with `--force`.** `python schema.py --force` DELETES all rows. Instead:
   ```bash
   python -c "
   import csv
   from schema import CANONICAL_COLUMNS
   path = 'connections.csv'
   with open(path, newline='', encoding='utf-8') as f:
       rows = list(csv.DictReader(f))
   with open(path, 'w', newline='', encoding='utf-8') as f:
       w = csv.DictWriter(f, fieldnames=CANONICAL_COLUMNS)
       w.writeheader()
       for r in rows:
           w.writerow({c: r.get(c, '') for c in CANONICAL_COLUMNS})
   print('Migrated. Existing rows preserved, new column added blank.')
   "
   ```
   Run from the project root. Existing rows get the new column blank; no row is lost.
3. **Teach the relevant skill to fill it** - add an extraction step and include it in the helper script payload.
4. **Surface it in the dashboard** if the user wants to see it.
5. **Record it in `outreach_config.json`** under `custom_fields_added`.

> Renaming or removing a column is riskier (it can orphan dashboard logic). Only on explicit request, and migrate the same in-place way - never `--force` a populated file.

## Adding a new persona tier

- **Swapping who a tier is** (e.g. tier 1 becomes "VP Marketing") is **config-only** - edit `persona_tiers`. No CSV change.
- **Adding a 5th tier** is also config-only - the skill walks the list in order, whatever its length.
- **The peer track** uses its own third slot (`persona3_*`) and is switched with `peer_enabled` - it does not count toward `personas_per_company`, which only covers the hiring-manager / recruiter slots.
- **Contacting more than one person per company**: set `personas_per_company: 2` in the config. This is now fully wired end to end (built via the additive-change procedure above) - here is what exists, for reference:

### The second-contact columns and the `--persona` flag

The CSV has **three** contact slots per company row: the primary persona, the second contact (below), and the peer (`persona3_*` - same columns as `persona2_*`, plus `persona3_common_ground`). Every slot also has an `accepted_date` and an `email_draft` column (`accepted_date` / `persona2_accepted_date` / `persona3_accepted_date`, and so on). The first two slots:

| Primary persona column | Second-contact equivalent |
|---|---|
| `persona_name`, `persona_title`, `persona_linkedin`, `persona_tier` | `persona2_name`, `persona2_title`, `persona2_linkedin`, `persona2_tier` |
| *(no equivalent - see below)* | `persona2_note` (no `persona2_location`/`persona2_mutuals` column) |
| `connection_note`, `note_char_count` | `persona2_note` doubles as both - not auto length-checked by `--data` the way `connection_note` is, so the skill counts it itself before saving |
| `connection_sent`, `date_sent`, `connection_result`, `note_sent_with_request`, `last_action_date` | `persona2_connection_sent`, `persona2_date_sent`, `persona2_connection_result`, `persona2_note_sent_with_request`, `persona2_last_action_date` |
| `followup_1_message`, `followup_1_date`, `followup_2_message`, `followup_2_date`, `reply_status` | `persona2_followup_1_message`, `persona2_followup_1_date`, `persona2_followup_2_message`, `persona2_followup_2_date`, `persona2_reply_status` |
| `outreach_status` | *(shared - no per-persona status column; it only ever reflects the primary persona)* |

`update_outreach.py --mark-sent`, `--result` and `--followup` all take a `--persona 1` (default), `--persona 2` or `--persona 3` flag to pick which set of columns they write to (`--data` does not - it is field-name-driven, so address `persona2_reply_status` etc. directly). **The second contact is a fully separate connection request against the exact same `daily_connection_cap` and `note_monthly_limit`** - `--cap-check` and `--note-cap-check` already sum both personas' sends together (a company where both were messaged today counts as 2 toward the daily cap), so nothing needs tracking by hand. `--due-followups` also checks both contacts independently and returns one entry per contact, tagged `"persona": "1"` or `"2"`.

**Going past 3 contacts per company** would need a fourth set of columns (`persona4_*`) added the same way - extend `PERSONAS` in `update_outreach.py`, `CONTACT_SLOTS` in `dashboard/app.py`, and follow the additive-change procedure above.
