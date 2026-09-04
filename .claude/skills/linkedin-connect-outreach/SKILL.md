---
name: linkedin-connect-outreach
description: For each company in the tracker, find the right person (tiers set by your outreach config), write a connection note of 200 characters or less, send the connection request under a daily cap and a monthly note-budget (for accounts without LinkedIn Premium), and record the result. Also handles follow-up messages after a request is accepted (auto-send or draft-only, per config) and a lightweight daily pass to catch new acceptances. Use this skill when asked to find people, send connection requests, add people on LinkedIn, write outreach notes, check who accepted, or follow up with accepted connections.
---

# LinkedIn Connect Outreach

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output - not in connection notes, follow-ups, reports, or any other text. Use a regular hyphen (-) instead. This applies to every piece of text this skill generates, without exception.

For each company row in the tracker that has no persona yet, find the right person per the configured tiers, write a note of **at most `{note_char_limit}` characters**, send the connection request with that note, and record it. Ships tuned for data leaders and founders, but the skill text names no title - all targeting lives in the outreach config (loaded in Step 0).

---

## The one-and-only data file rule (read first)

There is **exactly one** data file in this project: **`{project_root}/connections.csv`**. This skill only ever reads from and writes to that file. The `update_outreach.py` script enforces this (it refuses any path whose filename is not `connections.csv`) and always preserves the file's existing column order, defined once in `{project_root}/schema.py`. Update rows **in place**; never rewrite or reshape the file yourself.

---

## The three hard limits this skill must never break

These are enforced in code by `update_outreach.py`, not left to judgement:

1. **The note is at most `{note_char_limit}` characters.** The script **refuses** a longer note instead of truncating it. If it refuses, rewrite the note shorter and try again. Never paste a note into LinkedIn that the script has not accepted.
2. **At most `{daily_connection_cap}` connection requests per day.** Run `--cap-check` **before every single send**. When `remaining` hits 0, stop sending, record the rest as drafted-not-sent, and report back.
3. **At most `{note_monthly_limit}` connection requests WITH a personalized note per calendar month** (this account has no LinkedIn Premium, which is what removes this limit). Run `--note-cap-check` before deciding whether to include a note. Once the monthly quota is used, keep drafting notes as usual (they are still useful, and get saved for the record) but **send every further request that period as a plain connect** (`--mark-sent --note-used no`) - never skip a company just because the note budget ran out.

Breaking any of these is the failure mode that gets a LinkedIn account restricted. Treat all three as absolute.

---

## Configuration

- **Project root**: auto-located by the helper script - it walks up from its own location to find the folder containing `schema.py`. Get it with `python "<this skill's dir>/scripts/update_outreach.py" --print-root`.
- **Master CSV path** (the only data file): `{project_root}/connections.csv`
- **Schema (column definitions)**: `{project_root}/schema.py`
- **Script path**: `<this skill's directory>/scripts/update_outreach.py`
- **Process rows where**: `persona_name` is blank - regardless of `outreach_status` or how long ago the company was added. This is keyed on the data, not the date: a company added weeks ago that never got a persona is still picked up. **Always process anything not yet processed.**
- **Blocked-personas cache**: `{project_root}/blocked_personas.txt` - profiles that hit a wall this project cannot work around (see Step 7c) and must never be picked as a candidate again. Load it before Step 3, same as the finder loads `seen_companies.txt`.

---

## CUSTOMIZE: targeting a different person or changing the note

> **STOP - is the user asking to change settings, or to run outreach?** If the user said something like "target founders instead", "make the notes shorter", "less salesy", "send more per day", "add a follow-up", or anything about changing *who* gets contacted or *how* the note reads - **do not run this skill.** That is a settings change. Follow `{project_root}/RETARGETING.md` (or see `CLAUDE.md` -> "Recognizing a settings change") to update `outreach_config.json`, then confirm the change. Only run this skill when the user wants to execute outreach with the current settings.

The outreach code-words (all documented in `RETARGETING.md`) are: `persona_tiers` (each with its own optional `function_code`), `personas_per_company`, `function_code`, `small_company_threshold`, `small_company_tier_override`, `prefer_second_degree`, `prefer_same_location`, `skip_if_no_persona`, `note_char_limit`, `note_tone`, `note_must_include`, `note_must_avoid`, `note_ask`, `note_signoff`, `note_example`, `note_monthly_limit`, `daily_connection_cap`, `pause_between_sends_seconds`, `confirm_before_first_send`, `stop_on_weekly_invite_limit`, `followup_enabled`, `followup_auto_send`, `followup_1_days`, `followup_2_days`, `followup_char_limit`, and `followup_tone`.

**Forward-only:** retargeting never touches rows already in `connections.csv`. Notes already sent stay exactly as they were sent.

---

## Step 0 (DO THIS FIRST) - Load the outreach config

**The outreach config is the single source of truth for who this skill contacts and what the note says.**

```bash
python -c "
import json, os
root = os.environ.get('PROJECT_ROOT') or '{project_root}'
for name in ('outreach_config.json', 'outreach_config.example.json'):
    p = os.path.join(root, name)
    if os.path.exists(p):
        print(json.dumps(json.load(open(p))['outreach'])); break
"
```

Bind these code-words; every step below uses them as placeholders, never literal values:

| Code-word (config key) | Substituted into |
|---|---|
| `{persona_tiers}` | who to look for, in priority order (each has `type`, `who`, `keywords`, and optionally its own `function_code`) - Step 3 |
| `{personas_per_company}` | how many people to contact per company - Step 3 |
| `{function_code}` | fallback `facetCurrentFunction=` on the People tab when a tier has no `function_code` of its own - Step 3 |
| `{small_company_threshold}` / `{small_company_tier_override}` | at companies under N employees, jump straight to this tier - Step 3 |
| `{prefer_second_degree}` / `{prefer_same_location}` | tie-breakers when several people match - Step 4 |
| `{skip_if_no_persona}` | `keep` or `delete` a company where nobody matched - Step 9 |
| `{note_char_limit}` | the hard note length limit - Step 5 |
| `{note_tone}` / `{note_must_include}` / `{note_must_avoid}` / `{note_ask}` / `{note_signoff}` | how the note reads - Step 5 |
| `{note_example}` | a reference note matching the current campaign's shape and length - copy its structure, never its literal words - Step 5 |
| `{note_monthly_limit}` | how many connects may include a personalized note this calendar month (no Premium = LinkedIn's own cap) - Step 2b and Step 7c |
| `{daily_connection_cap}` / `{pause_between_sends_seconds}` | send pacing - Steps 6 and 7 |
| `{confirm_before_first_send}` | ask the user once before the first send of the run - Step 6 |
| `{stop_on_weekly_invite_limit}` | stop the run if LinkedIn shows the weekly invite limit - Step 7 |
| `{followup_enabled}` / `{followup_1_days}` / `{followup_2_days}` / `{followup_char_limit}` / `{followup_tone}` | the follow-up pass - Step 10 |
| `{followup_auto_send}` | if `false` (the default for this campaign), a follow-up is drafted and staged in the dashboard only - never sent by the skill. If `true`, the skill sends it itself via the Message button - Step 10 |

**Hard rule:** the steps below contain **only code-words in `{curly braces}`** for anything targeting-specific. If **neither** config file exists, stop and tell the user the outreach config is missing - do not invent values.

---

## Step 1 - Read the unprocessed rows

Read `{project_root}/connections.csv`. Select every row where `persona_name` is blank. Do not filter by `outreach_status`. If every row already has a persona, say so and skip to Step 10 (follow-ups).

For each selected row, take: `company_id`, `company_name`, `linkedin_company_url`, `company_size`, `industry`, `hq_location`, `signal`, `why_relevant`. The last two are what make the note personal - if both are blank, the note will be generic, so lean on `industry` and `company_tagline` instead.

---

## Step 2 - Check the daily cap before doing any work

```bash
python "<this skill's dir>/scripts/update_outreach.py" --cap-check
```

This prints `{"cap": N, "sent_today": N, "remaining": N}`. If `remaining` is 0, do **not** start a sending run: tell the user the cap is already used up today, and offer to draft notes without sending (Steps 3 to 5, then stop before Step 6). Otherwise you may process at most `remaining` companies through to a send this run.

---

## Step 2b - Check the monthly note budget before doing any work

```bash
python "<this skill's dir>/scripts/update_outreach.py" --note-cap-check
```

This prints `{"note_cap": N, "notes_used_this_month": N, "notes_remaining": N}`. Remember `notes_remaining` for this run - it is how many of the sends below may include a personalized note. **This never blocks the run.** Once `notes_remaining` hits 0, every further company in this run still gets a note drafted (Step 5, for the record and in case you want to send it by hand) but is sent as a **plain connect** in Step 7c. Decrement your own running count of `notes_remaining` by 1 each time you actually send with a note, so you do not overshoot before the script's own check catches it in Step 7c.

---

## Page-ready gate (run after EVERY navigation in Steps 3 to 7)

LinkedIn renders People-tab results and profile pages **asynchronously, after the page load event**. Reading too early is the main cause of empty results and stuck panels. **Poll the DOM until the target content exists, then read** - never a fixed sleep.

Use `budgetMs` = **15000 on the first navigation of the run**, **8000** afterwards.

```javascript
await (async () => {
  const budgetMs = 15000;            // FIRST navigation of the run; use 8000 afterwards
  const t0 = performance.now();
  const ready = () => document.querySelectorAll('.org-people-profile-card__profile-info').length > 0;  // People tab
  while (performance.now() - t0 < budgetMs) {
    const spinner = document.querySelector('.artdeco-loader');
    if (ready() && !spinner) return JSON.stringify({ ready: true, ms: Math.round(performance.now() - t0) });
    await new Promise(r => setTimeout(r, 250));
  }
  return JSON.stringify({ ready: false, ms: Math.round(performance.now() - t0), reason: 'timeout' });
})()
```

For a **person's profile page**, swap the predicate for:
```javascript
const ready = () => !!document.querySelector('h1') && /experience|about|activity/i.test(document.body.innerText);
```

**Act on the result:** `ready: true` -> extract immediately. `timeout` -> retry the navigation once, gate again; if it still times out, treat that tier as 0 results and move to the next tier.

---

## Step 3 - Find the persona at this company

Extract the company slug from `linkedin_company_url` (`https://www.linkedin.com/company/<slug>/`). The People tab is:
```
https://www.linkedin.com/company/{slug}/people/
```

**Which tier to try first.** Read `company_size`. If the company has fewer than `{small_company_threshold}` employees, start at tier `{small_company_tier_override}` (at a 20-person company there is no Head of Data - the founder is the right person). Otherwise start at tier 1 and walk down the `{persona_tiers}` list in order until you find someone.

For each tier, navigate to:
```
https://www.linkedin.com/company/{slug}/people/?keywords={tier.keywords}&facetCurrentFunction={tier.function_code or function_code}
```
Use the tier's own `function_code` when it has one (e.g. Recruiter/TA tiers use the HR/Recruiting function, Data tiers use the Research/Analytics function - see `RETARGETING.md`'s function-code table); fall back to the top-level `{function_code}` only if the tier does not specify its own. If a tier returns 0 results, retry once **without** `facetCurrentFunction` before moving to the next tier - the function filter is the most common cause of a false empty.

Run the **page-ready gate**, then extract:

```javascript
const cards = document.querySelectorAll('.org-people-profile-card__profile-info');
const results = Array.from(cards).slice(0, 10).map(card => {
  const nameEl = card.querySelector('.artdeco-entity-lockup__title');
  const subtitleEl = card.querySelector('.artdeco-entity-lockup__subtitle');
  const captionEl = card.querySelector('.artdeco-entity-lockup__caption');
  const link = card.querySelector('a[href*="/in/"]');
  const path = link ? new URL(link.href).pathname : null;
  const txt = card.innerText || '';
  return {
    name: nameEl?.textContent?.trim(),
    title: subtitleEl?.textContent?.trim(),
    location: captionEl?.textContent?.trim(),
    degree: (txt.match(/\b(1st|2nd|3rd)\b/) || [])[1] || '',
    path
  };
});
JSON.stringify(results.filter(r => r.name && r.path));
```

Collect `{personas_per_company}` people (default 1). If the People tab is empty or gated for every tier, fall back to a global people search:
```
https://www.linkedin.com/search/results/people/?keywords={tier.keywords}%20{company_name}
```
and verify from the headline that the person is actually at this company today.

---

## Step 4 - Pick the right person

Apply, in order:

1. **Tier order wins.** A tier-1 match beats a tier-2 match, always.
2. **Current role must be at this company.** The People tab shows LinkedIn *headlines*, not job titles - a headline can describe a past role. If there is any doubt, open the profile and check the current position before selecting.
3. **Tie-breakers:** if `{prefer_second_degree}` is true, prefer a 2nd-degree connection (they accept far more often). If `{prefer_same_location}` is true, prefer someone in the company's `hq_location`.
4. **Never pick someone already in the tracker** with a different company row, never pick a 1st-degree connection (you are already connected to them), and **never pick anyone whose profile path is in `blocked_personas.txt`** (loaded in Configuration above) - they already hit a wall this project cannot work around, and picking them again just repeats the same dead end.

Record: `persona_name`, `persona_title` (their headline), `persona_linkedin` (`https://www.linkedin.com` + path), `persona_tier` (the tier `type` that matched), `persona_location`, `persona_mutuals` (shared-connections count if the profile shows one).

**When `{personas_per_company}` is 2**: the first (highest-tier) candidate goes in the fields above; the second candidate goes in `persona2_name`, `persona2_title`, `persona2_linkedin`, `persona2_tier` - there is no `persona2_location`/`persona2_mutuals` column, so leave those details out of `notes` unless useful. The CSV only has room for two contacts per company today - `personas_per_company` above 2 would need a new column added first (see `RETARGETING.md`'s additive-change procedure).

If **no** person is found at any tier, follow `{skip_if_no_persona}`: `keep` leaves the row with a blank persona (it will be retried next run); `delete` removes the row via the script's `--delete` mode.

---

## Step 5 - Write the connection note (at most `{note_char_limit}` characters)

This is the whole product. A generic note is worse than no note.

**Rules, in priority order:**

1. **Hard limit: `{note_char_limit}` characters, counted including spaces and punctuation.** Count before you save (`len()` on the exact string - spaces count). The helper script refuses anything longer - it will not truncate for you.
2. **Include every item in `{note_must_include}`** - by default their first name, the specific angle that made you reach out to them (their transition, project, role, or what the company/team is building - taken from `signal`, `why_relevant`, or their own profile/headline), and a brief low-pressure close. The detail must be something you actually read, never a guess.
3. **Avoid every phrase in `{note_must_avoid}`.** No "I hope this finds you well", no "quick question", no buzzwords, no em dashes.
4. **Tone: `{note_tone}`.** Proactive, not passive - name the specific thing that stood out, don't just say you're "interested in connecting." Write like a person, not a template. Contractions are fine.
5. **The ask is `{note_ask}`** - by default a connect or an open invite to hear more about their journey/team. No meeting request, no link, no pitch, no explicit job ask in the first note.
6. **Signoff: `{note_signoff}`.** Default `none` - at this length a signoff wastes characters.

**Shape that works at this length:** greeting with first name, one line naming the specific angle and that it stood out, one line inviting them to share more, then a brief low-pressure close acknowledging it's a bit of an ask. If `{note_example}` is set in the config, treat it as the reference shape - match its structure and length, not its literal words (never send the same note to everyone).

Good (151 chars) - see `{note_example}` for the current campaign's reference:
```
Hi James, your move from healthcare into data stood out to me. I'd love to hear about that journey. No worries if this is a big ask from a stranger!
```

Bad, and why:
```
Hi Lena! I hope this message finds you well. I came across your profile and was really impressed by your background. I would love to connect and explore potential synergies.
```
Passive and generic - three banned phrases, no specific angle, no low-pressure close, says nothing only this person would receive.

**If a skill named `humanizer` is available in your environment, run the drafted note through it before saving** - it strips AI-generated writing tells that survive the rules above. Humanizing can change the length, so re-count the characters afterward and trim if needed; the script below still refuses anything over `{note_char_limit}` regardless. If no such skill is available, save the note as drafted - do not treat its absence as an error.

Save the note with:
```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --data '{"persona_name": "...", "persona_title": "...", "persona_linkedin": "...", "persona_tier": "...", "persona_location": "...", "persona_mutuals": "...", "connection_note": "..."}'
```
The script validates the length, writes `note_char_count`, and sets `outreach_status` to `Note drafted`. **If it refuses, rewrite the note shorter - do not truncate it mid-sentence and do not edit the CSV by hand.**

**If there is a second contact** (`persona2_name` set from Step 4), write a separate note for them the same way - genuinely different wording, never the primary note copy-pasted - run it through `humanizer` too if available, and save it as `persona2_note` in the same `--data` call: `'{"persona2_name": "...", ..., "persona2_note": "..."}'`. It is checked against the same `{note_char_limit}`, but is not auto-validated by the script the way `connection_note` is - count it yourself before saving.

---

## Step 6 - Confirm before the first send of the run

If `{confirm_before_first_send}` is true, **before the first send only**, show the user the queue you are about to send: each company, the person, their title, and either the exact note (if this one will be sent with a note) or "plain connect, no note" (if the monthly quota is already spent for it). Then ask one plain question, for example: "That is 8 connection requests, 8 of your 15 daily cap - 3 with a note (using the last of this month's 5), 5 as plain connects. Send them now?"

- Wait for a yes. On any hesitation or edit request, apply the edit and re-confirm.
- Once confirmed, send the whole batch without asking again this run.
- If `{confirm_before_first_send}` is false, skip this step and send directly.

A scheduled run with `confirm_before_first_send` true and nobody available to answer should **draft only**: leave the rows at `Note drafted` and report that they are waiting for approval. Never send unconfirmed when the setting asks for confirmation.

---

## Step 7 - Send the connection request

For each queued person, in order. **A company with two contacts queues as two separate people** - the primary persona and the second persona each go through 7a-7f independently, in their own turn, with their own pause afterward (7f); they are two separate connection requests against the same daily cap and monthly note quota, not one combined action. The only difference for the second contact is in 7e: pass `--persona 2`.

### 7a - Check the cap first, every single time

```bash
python "<this skill's dir>/scripts/update_outreach.py" --cap-check
```
If `remaining` is 0, stop sending immediately, leave the remaining rows at `Note drafted`, and go to Step 9.

### 7b - Open the profile and click Connect

Navigate to `persona_linkedin`, run the **page-ready gate** with the profile predicate, then locate the Connect button. It is sometimes in the top card and sometimes hidden behind the **More** button:

```javascript
await (async () => {
  const findBtn = (label) => Array.from(document.querySelectorAll('button'))
    .find(b => (b.getAttribute('aria-label') || b.innerText || '').trim().toLowerCase().startsWith(label));
  let connect = findBtn('connect') || findBtn('invite');
  if (!connect) {
    const more = findBtn('more');
    if (more) { more.click(); await new Promise(r => setTimeout(r, 600)); }
    connect = findBtn('connect') || findBtn('invite');
  }
  if (!connect) return JSON.stringify({ ok: false, reason: 'no-connect-button' });
  connect.click();
  return JSON.stringify({ ok: true });
})()
```

`{"ok": false, "reason": "no-connect-button"}` means you are already connected, the profile only offers Follow, or the person has invites restricted. Record `connection_result` as `Failed`, leave `connection_sent` as `No`, and move on - this does not count against the cap.

### 7c - Decide note-or-plain, then send

**First, decide using your running `notes_remaining` count from Step 2b:**
- **`notes_remaining` > 0:** send WITH the drafted note. Decrement your running count by 1 after this send succeeds.
- **`notes_remaining` == 0:** send as a **plain connect** - the note stays drafted in the CSV for the record (and for the user to paste by hand if they choose), but do not add it to the invite. This is the intended, normal path once the monthly quota is spent, not a failure - never skip a company for this reason.

Wait for the invite modal with a gate whose predicate is `document.querySelector('.artdeco-modal')`, then:

```javascript
await (async () => {
  const modal = document.querySelector('.artdeco-modal');
  if (!modal) return JSON.stringify({ ok: false, reason: 'no-modal' });
  const text = (modal.innerText || '').toLowerCase();
  if (text.includes('enter their email') || text.includes('verify this member knows you')) {
    return JSON.stringify({ ok: false, reason: 'email-verification-required' });
  }
  const btnByText = (t) => Array.from(modal.querySelectorAll('button'))
    .find(b => (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase().includes(t));
  return JSON.stringify({
    ok: true,
    hasAddNote: !!btnByText('add a note'),
    hasSendDirect: !!btnByText('send without a note') || !!btnByText('send')
  });
})()
```

**`{"ok": false, "reason": "email-verification-required"}`**: LinkedIn is asking for *the recipient's* email to prove you know them personally - this shows up for people well outside your network. There is no legitimate way to satisfy this for a cold outreach target. **Never enter any email here - not a guess, not the user's own.** Close the modal, then:

1. **Blocklist them and clear the row** so the company gets retried with someone else next run, instead of being permanently stuck on a contact that can never be sent:
   ```bash
   python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --block-persona "{persona_linkedin}" --data '{"persona_name": "", "persona_title": "", "persona_linkedin": "", "persona_tier": "", "persona_location": "", "persona_mutuals": "", "connection_note": "", "note_char_count": "", "note_sent_with_request": "", "outreach_status": "Not started", "notes": "Skipped <name> - LinkedIn required recipient email verification; retried with a different contact."}'
   ```
   This does not count against the daily cap or the note quota, and it does not consume this company's slot in the run - if time remains, go back to Step 3 for this same company now and try the next candidate/tier (blocked_personas.txt already excludes this person); otherwise it will be picked up fresh on the next run since `persona_name` is blank again.
2. Move to the next queued person.

If this happens often, mention it in your Step 9 report - it usually means `{prefer_second_degree}` isn't finding enough 2nd-degree matches for this account and more requests are landing on distant, out-of-network people.

**If sending WITH a note:** click "Add a note", wait ~500ms, then find the textarea (`textarea#custom-message, textarea[name="message"], textarea`) and type the note into it using the `type_text` / `fill` tool rather than setting `.value` in JS - LinkedIn listens for real input events and will otherwise send an empty note. If the textarea never appears after one retry, fall back to sending plain instead (a job-search connect is still worth sending) and record `note_sent_with_request` as `No` for this send - do not abandon the company.

**If sending plain:** click "Send" (or "Send without a note") directly on the initial modal - do not click "Add a note" at all.

Either way, click the send button last:
```javascript
await (async () => {
  const modal = document.querySelector('.artdeco-modal');
  const send = Array.from(modal.querySelectorAll('button'))
    .find(b => /^(send|send invitation|send now|send without a note)\b/i.test((b.innerText || b.getAttribute('aria-label') || '').trim()));
  if (!send || send.disabled) return JSON.stringify({ ok: false, reason: 'send-disabled' });
  send.click();
  return JSON.stringify({ ok: true });
})()
```

If `send-disabled` and this was meant to be a plain send, that usually means LinkedIn requires the modal to be dismissed of the note step first - go back one step and retry. If it still fails, record `connection_result` as `Failed` and move on.

### 7d - Handle the limit modals

If a modal appears saying you have reached the **weekly invitation limit**, or offering Premium to send more:
- If `{stop_on_weekly_invite_limit}` is true (default), **stop the entire run immediately**. Do not dismiss and retry. Record the remaining rows as `Note drafted` and tell the user plainly that LinkedIn capped the week and when to resume.
- Never work around a LinkedIn limit. The cap in this project sits well below LinkedIn's own for exactly this reason.

### 7e - Record the send

```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --mark-sent --note-used yes|no
```
Pass `--note-used yes` if the invite actually went out with the note, `--note-used no` if it went out plain (including the note-textarea-failed fallback in 7c). This sets `connection_sent = Yes`, `date_sent` to today, `connection_result = Sent`, `outreach_status = Request sent`, `note_sent_with_request` accordingly, and re-checks both the daily cap and (when `--note-used yes`) the monthly note quota - it **refuses** the write if either is already used, which is the backstop if 7a or your own `notes_remaining` tracking was skipped. If it refuses on the note quota specifically, re-run with `--note-used no` - the request may already be sitting in the "sent" state in the browser regardless of the note, so do not leave the row unrecorded.

**Sending to the second contact:** add `--persona 2` to the same command:
```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --persona 2 --mark-sent --note-used yes|no
```
This writes `persona2_connection_sent`, `persona2_date_sent`, `persona2_connection_result`, `persona2_note_sent_with_request`, and `persona2_last_action_date` instead of the primary columns - it does **not** touch `outreach_status` (there is no per-persona status column; that field only ever reflects the primary persona). It counts as its own request against the **same** daily cap and monthly note quota as the primary persona - `--cap-check` and `--note-cap-check` already add both personas together, so there is nothing extra to track by hand.

### 7f - Pause

Wait a random interval within `{pause_between_sends_seconds}` (default 25 to 60 seconds) before the next person. This pacing is not optional: a burst of instant requests is the pattern LinkedIn flags.

---

## Step 8 - Record acceptances

Do this whenever the user asks to check replies, at the start of a later find-and-send run, or as the daily acceptance-check pass (Step 11). **Do not scan the user's entire connections list every time** - the account can easily have 1,000+ connections; the check below only ever reads down to where it stops mattering.

### 8a - Get the cutoff date

```bash
python "<this skill's dir>/scripts/update_outreach.py" --acceptance-check-status
```
This prints `{"last_checked_date": "YYYY-MM-DD"}` - everyone connected on or before that date was already seen on a previous check.

### 8b - Read the Connections page down to the cutoff

Navigate to `https://www.linkedin.com/mynetwork/invite-connect/connections/`. Make sure the sort is **"Recently added"** (the default; if it shows a different sort, open the sort dropdown and select it) - the list must be newest-first for the early-stop below to be valid.

Run the **page-ready gate**, then read entries from the top. Each shows a name, headline, profile link, and a "Connected on <date>" line - extract all three plus the date for each. **Stop reading (and stop paginating) the moment you reach an entry dated on or before the cutoff from 8a** - everything at or below that point was already processed on a previous check, and everything above it is new since then.

### 8c - Match new connections against the tracker

For each newly-connected entry (dated after the cutoff), look for a row in `connections.csv` where `persona_linkedin` matches this profile's URL and `connection_result` is not already `Accepted`. Match on the profile path (the `/in/<slug>` part), not the display name - names can collide.

```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --result Accepted
```
Valid values: `Sent`, `Pending`, `Accepted`, `Ignored`, `Withdrawn`, `Failed`. `Accepted` also moves `outreach_status` to `Accepted`, which is what puts the row into the follow-up queue.

A newly-connected entry that matches no row in the tracker is someone the user connected with outside this project - leave it alone, it is not this skill's concern.

### 8d - Advance the cutoff

Once every new entry from 8b has been checked against the tracker, advance the cutoff so tomorrow's check does not re-read the same names:
```bash
python "<this skill's dir>/scripts/update_outreach.py" --mark-checked
```
Only do this after 8c has actually run to completion for this pass - if the pass was interrupted partway through, leave the cutoff where it was so nothing gets skipped next time.

---

## Step 9 - Report

Report:
- How many companies got a persona, and how many found nobody
- How many requests were sent, how many with a note vs plain, and the remaining daily cap and monthly note quota
- Anything left at `Note drafted` and why (cap reached, awaiting confirmation, weekly limit)
- Per company: company name, person, title, tier, and whether it went out with a note (and what it said) or plain

Example:
```
Job-search outreach - 8 sent (3 with a note, 5 plain - monthly note quota now 0/5), 7 remaining on today's cap.

Acme Data - Lena Fischer, Recruiter / Talent Acquisition (tier 1) - sent with note
  "Hi Lena, saw Acme is building out its first analytics team in Berlin..."
Northbeam - Tomas Silva, Founder (tier 3) - sent, plain connect (note budget used up this month)

Drafted, not sent (daily cap): 3 companies.
No persona found: 1 company (Vela Systems - People tab is gated).
```

---

## Step 10 - Follow-ups

Only if `{followup_enabled}` is true. Ask the script who is due:

```bash
python "<this skill's dir>/scripts/update_outreach.py" --due-followups
```

This returns a list of `{company_id, company_name, persona, persona_name, persona_linkedin, followup, days_since_sent, immediate_no_note}` entries - one per **contact**, not per company, so a company with two accepted contacts can produce two entries. `persona` is `"1"` or `"2"`, telling you which contact's fields to use and write back to. It never returns anyone who already replied. Two ways an entry becomes due:

- **`immediate_no_note: true`** - this person accepted a **plain connect** (the monthly note quota was already spent when their request went out, so they never received your personalized note at all). This shows up **immediately**, on day 0, regardless of `{followup_1_days}` - there is no reason to make them wait for content they were always owed.
- **`immediate_no_note: false`** - a normal, scheduled touch: `date_sent` is at least `{followup_1_days}` old (follow-up 1), or, having had follow-up 1, at least `{followup_2_days}` old (follow-up 2).

**Writing the message - the two cases read differently:**
- **`immediate_no_note: true` (follow-up 1 only)**: this is effectively their *first* real personalized message, not a follow-up in tone. Do not reference "the note you accepted" - there wasn't one. Open naturally (thank them for connecting), then deliver the same specific detail and ask that would have been in the connection note (see `{note_tone}`/`{note_must_include}` for what that detail should be, pulled from `signal`/`why_relevant`), reworked into message form. Warm, no less personal for arriving this way.
- **`immediate_no_note: false`**: normal follow-up. Write in `{followup_tone}`, at most `{followup_char_limit}` characters. Follow-up 1 references the note they accepted and gives one concrete, useful thing - never "just bumping this". Follow-up 2 is shorter still and closes the loop gracefully, so the person is left with a good impression either way.

**If a skill named `humanizer` is available in your environment, run the drafted message through it before saving**, same as Step 5's notes - re-count against `{followup_char_limit}` afterward, since humanizing can change the length. If unavailable, save the message as drafted.

**Record it, using `--persona 2` for a second-contact entry:**
```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --followup 1 --message "..." [--persona 2]
```
This writes the message and `followup_1_date`/`followup_2_date` (or the `persona2_` equivalents) regardless of `{followup_auto_send}` - the CSV record of "a follow-up is due and has been written" is separate from whether it was actually sent.

**Then, if `{followup_auto_send}` is true, also send it as a real LinkedIn message**, right after recording it (recording first means the message is never lost even if the send step fails):
1. Navigate to `persona_linkedin` (or `persona2_linkedin`), run the **page-ready gate** with the profile predicate.
2. Find and click the **Message** button (same `findBtn` pattern as Step 7b, matching label `message`, not `connect`/`invite`).
3. Wait for the message compose box (gate on `document.querySelector('.msg-form__contenteditable, [contenteditable="true"]')`), then type the text using the `type_text` / `fill` tool - not `.value` in JS, same reasoning as the connection-note textarea in 7c.
4. Click the **Send** button in the compose box.
5. Pause a random interval within `{pause_between_sends_seconds}` before the next message - the same anti-burst pacing applies to messages, not just connection requests.

**If `{followup_auto_send}` is false: do not open the Message button or send anything.** The message is staged - it shows up in the dashboard at `/company/<id>` with a Copy button, ready for the user to paste and send themselves whenever they choose. Say so in your report rather than reporting it as "sent".

If someone replies, record it and stop the sequence - `--data` is field-name-driven, not `--persona`-driven, so name the field directly:
```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --data '{"reply_status": "Positive"}'
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --data '{"persona2_reply_status": "Positive"}'
```
Valid reply status: `No reply`, `Replied`, `Positive`, `Not interested`. Anything other than `No reply` removes that contact from the follow-up queue permanently - the other contact at the same company, if any, is unaffected.

---

## Step 11 - Daily acceptance-check pass (for the scheduled daily task)

This is a **lightweight subset** of this skill - Steps 8 and 10 only, run on their own once a day, without a full find-and-send cycle. Use this when the trigger is the daily schedule (see `CLAUDE.md` -> Scheduling) rather than an on-demand "run my outreach" request.

1. Run **Step 8** in full (8a to 8d) - it reads only the Connections page entries newer than the last check, matches them against the tracker, records any new `Accepted` results, and advances the cutoff. It never reads the user's full connections list.
2. Run **Step 10** to draft (and, only if `{followup_auto_send}` is true, send) the follow-up for anything now due - this is also where anyone who accepted a plain connect (`immediate_no_note: true`) gets their first real message right away, same-day, rather than waiting.
3. Report briefly: how many new acceptances, how many messages went out (split: immediate no-note catch-ups vs scheduled follow-ups) vs how many are waiting for the user in the dashboard.

Do **not** run Steps 1 to 7 (finding personas or sending new connection requests) as part of this daily pass unless the user explicitly also asked for that today - the daily schedule's job is to catch acceptances and stage follow-ups, not to send new requests.

---

## Edge cases

- **Login wall**: stop immediately and ask the user to log into LinkedIn in Chrome first.
- **0 results on the People tab for every tier**: retry once without `facetCurrentFunction`, then try the global people search (Step 3). Only then follow `{skip_if_no_persona}`.
- **Person is already a 1st-degree connection**: skip them and pick the next-best person at that company. If nobody else fits, record `connection_result` as `Failed` with a note in `notes` saying you are already connected.
- **Profile is out of network with no Connect button**: record `Failed` and move on. Do not use InMail.
- **LinkedIn asks for the recipient's email to "verify this member knows you"**: this cannot be satisfied for a cold outreach target - never guess or enter any email (not the user's own). Blocklist them and clear the row's persona fields so the company retries with someone else, per 7c - do not leave them stuck in the tracker as a dead end.
- **The script refuses a note as too long**: rewrite it shorter. Do not edit the CSV directly and do not paste the long version into LinkedIn.
- **The script refuses `--mark-sent` on the daily cap**: the request may already have gone out in the browser. Tell the user exactly which person that was so the record can be fixed by hand, then stop the run.
- **The script refuses `--mark-sent --note-used yes` on the monthly note quota**: re-run the same command with `--note-used no` - the browser may already show it sent either way, this only affects how it's recorded. Then send everyone else this run as plain connects until next month.
- **CAPTCHA or a security checkpoint**: stop everything, record what has been sent so far, and tell the user. Never attempt to solve it.
- **The user asks to send more than the cap**: that is a settings change (`daily_connection_cap`). Follow `RETARGETING.md`, and say plainly that raising it above about 20 per day raises the account-restriction risk.
- **The user asks to raise the monthly note limit above 5**: only do it if they've confirmed LinkedIn is actually letting more through on this account - the 5/month figure is LinkedIn's typical free-plan number, not this project's own choice, so raising the config value does not raise LinkedIn's real limit. If they buy Premium, ask them to say so and set `note_monthly_limit` very high (or effectively unlimited) instead.
