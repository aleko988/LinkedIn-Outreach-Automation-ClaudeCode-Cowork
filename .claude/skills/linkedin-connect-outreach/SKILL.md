---
name: linkedin-connect-outreach
description: For each company in the tracker, find the right person (tiers set by your outreach config; ships tuned for data leaders and founders), write a connection note of 200 characters or less, send the connection request with that note under a daily cap, and record the result. Also handles follow-up messages after a request is accepted. Use this skill when asked to find people, send connection requests, add people on LinkedIn, write outreach notes, or follow up with accepted connections.
---

# LinkedIn Connect Outreach

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output - not in connection notes, follow-ups, reports, or any other text. Use a regular hyphen (-) instead. This applies to every piece of text this skill generates, without exception.

For each company row in the tracker that has no persona yet, find the right person per the configured tiers, write a note of **at most `{note_char_limit}` characters**, send the connection request with that note, and record it. Ships tuned for data leaders and founders, but the skill text names no title - all targeting lives in the outreach config (loaded in Step 0).

---

## The one-and-only data file rule (read first)

There is **exactly one** data file in this project: **`{project_root}/connections.csv`**. This skill only ever reads from and writes to that file. The `update_outreach.py` script enforces this (it refuses any path whose filename is not `connections.csv`) and always preserves the file's existing column order, defined once in `{project_root}/schema.py`. Update rows **in place**; never rewrite or reshape the file yourself.

---

## The two hard limits this skill must never break

These are enforced in code by `update_outreach.py`, not left to judgement:

1. **The note is at most `{note_char_limit}` characters.** The script **refuses** a longer note instead of truncating it. If it refuses, rewrite the note shorter and try again. Never paste a note into LinkedIn that the script has not accepted.
2. **At most `{daily_connection_cap}` connection requests per day.** Run `--cap-check` **before every single send**. When `remaining` hits 0, stop sending, record the rest as drafted-not-sent, and report back.

Breaking either one is the failure mode that gets a LinkedIn account restricted. Treat both as absolute.

---

## Configuration

- **Project root**: auto-located by the helper script - it walks up from its own location to find the folder containing `schema.py`. Get it with `python "<this skill's dir>/scripts/update_outreach.py" --print-root`.
- **Master CSV path** (the only data file): `{project_root}/connections.csv`
- **Schema (column definitions)**: `{project_root}/schema.py`
- **Script path**: `<this skill's directory>/scripts/update_outreach.py`
- **Process rows where**: `persona_name` is blank - regardless of `outreach_status` or how long ago the company was added. This is keyed on the data, not the date: a company added weeks ago that never got a persona is still picked up. **Always process anything not yet processed.**

---

## CUSTOMIZE: targeting a different person or changing the note

> **STOP - is the user asking to change settings, or to run outreach?** If the user said something like "target founders instead", "make the notes shorter", "less salesy", "send more per day", "add a follow-up", or anything about changing *who* gets contacted or *how* the note reads - **do not run this skill.** That is a settings change. Follow `{project_root}/RETARGETING.md` (or see `CLAUDE.md` -> "Recognizing a settings change") to update `outreach_config.json`, then confirm the change. Only run this skill when the user wants to execute outreach with the current settings.

The outreach code-words (all documented in `RETARGETING.md`) are: `persona_tiers`, `personas_per_company`, `function_code`, `small_company_threshold`, `small_company_tier_override`, `prefer_second_degree`, `prefer_same_location`, `skip_if_no_persona`, `note_char_limit`, `note_tone`, `note_must_include`, `note_must_avoid`, `note_ask`, `note_signoff`, `daily_connection_cap`, `pause_between_sends_seconds`, `confirm_before_first_send`, `stop_on_weekly_invite_limit`, `followup_enabled`, `followup_1_days`, `followup_2_days`, `followup_char_limit`, and `followup_tone`.

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
| `{persona_tiers}` | who to look for, in priority order (each has `type`, `who`, `keywords`) - Step 3 |
| `{personas_per_company}` | how many people to contact per company - Step 3 |
| `{function_code}` | `facetCurrentFunction=` on the People tab - Step 3 |
| `{small_company_threshold}` / `{small_company_tier_override}` | at companies under N employees, jump straight to this tier - Step 3 |
| `{prefer_second_degree}` / `{prefer_same_location}` | tie-breakers when several people match - Step 4 |
| `{skip_if_no_persona}` | `keep` or `delete` a company where nobody matched - Step 9 |
| `{note_char_limit}` | the hard note length limit - Step 5 |
| `{note_tone}` / `{note_must_include}` / `{note_must_avoid}` / `{note_ask}` / `{note_signoff}` | how the note reads - Step 5 |
| `{daily_connection_cap}` / `{pause_between_sends_seconds}` | send pacing - Steps 6 and 7 |
| `{confirm_before_first_send}` | ask the user once before the first send of the run - Step 6 |
| `{stop_on_weekly_invite_limit}` | stop the run if LinkedIn shows the weekly invite limit - Step 7 |
| `{followup_enabled}` / `{followup_1_days}` / `{followup_2_days}` / `{followup_char_limit}` / `{followup_tone}` | the follow-up pass - Step 10 |

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
https://www.linkedin.com/company/{slug}/people/?keywords={tier.keywords}&facetCurrentFunction={function_code}
```
If a tier returns 0 results, retry once **without** `facetCurrentFunction` before moving to the next tier - the function filter is the most common cause of a false empty.

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
4. **Never pick someone already in the tracker** with a different company row, and never pick a 1st-degree connection - you are already connected to them.

Record: `persona_name`, `persona_title` (their headline), `persona_linkedin` (`https://www.linkedin.com` + path), `persona_tier` (the tier `type` that matched), `persona_location`, `persona_mutuals` (shared-connections count if the profile shows one).

If **no** person is found at any tier, follow `{skip_if_no_persona}`: `keep` leaves the row with a blank persona (it will be retried next run); `delete` removes the row via the script's `--delete` mode.

---

## Step 5 - Write the connection note (at most `{note_char_limit}` characters)

This is the whole product. A generic note is worse than no note.

**Rules, in priority order:**

1. **Hard limit: `{note_char_limit}` characters, counted including spaces and punctuation.** Count before you save. The helper script refuses anything longer - it will not truncate for you.
2. **Include every item in `{note_must_include}`** - by default their first name and one concrete detail about their company or team, taken from `signal` or `why_relevant`. The detail must be something you actually read on their company page, never a guess.
3. **Avoid every phrase in `{note_must_avoid}`.** No "I hope this finds you well", no "quick question", no buzzwords, no em dashes.
4. **Tone: `{note_tone}`.** Write like a person, not a template. Contractions are fine.
5. **The ask is `{note_ask}`** - by default just a connect. No meeting request, no link, no pitch in the first note.
6. **Signoff: `{note_signoff}`.** Default `none` - at this length a signoff wastes characters.

**Shape that works at this length:** greeting with first name, one line naming the specific thing you noticed, one line on why you personally care, then the connect ask. Three short sentences, roughly 140 to 190 characters.

Good (152 chars):
```
Hi Lena, saw Acme is building out its first analytics team in Berlin. I work on the same messy-data problems daily and would like to follow what you ship.
```

Bad, and why:
```
Hi Lena! I hope this message finds you well. I came across your profile and was really impressed by your background. I would love to connect and explore potential synergies.
```
Nothing specific, three banned phrases, says nothing only this person would receive.

Save the note with:
```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --data '{"persona_name": "...", "persona_title": "...", "persona_linkedin": "...", "persona_tier": "...", "persona_location": "...", "persona_mutuals": "...", "connection_note": "..."}'
```
The script validates the length, writes `note_char_count`, and sets `outreach_status` to `Note drafted`. **If it refuses, rewrite the note shorter - do not truncate it mid-sentence and do not edit the CSV by hand.**

---

## Step 6 - Confirm before the first send of the run

If `{confirm_before_first_send}` is true, **before the first send only**, show the user the queue you are about to send: each company, the person, their title, and the exact note. Then ask one plain question, for example: "That is 8 connection requests, 8 of your 15 daily cap. Send them now?"

- Wait for a yes. On any hesitation or edit request, apply the edit and re-confirm.
- Once confirmed, send the whole batch without asking again this run.
- If `{confirm_before_first_send}` is false, skip this step and send directly.

A scheduled run with `confirm_before_first_send` true and nobody available to answer should **draft only**: leave the rows at `Note drafted` and report that they are waiting for approval. Never send unconfirmed when the setting asks for confirmation.

---

## Step 7 - Send the connection request

For each queued person, in order:

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

### 7c - Add the note and send

Wait for the invite modal with a gate whose predicate is `document.querySelector('.artdeco-modal')`, then:

```javascript
await (async () => {
  const modal = document.querySelector('.artdeco-modal');
  if (!modal) return JSON.stringify({ ok: false, reason: 'no-modal' });
  const btnByText = (t) => Array.from(modal.querySelectorAll('button'))
    .find(b => (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase().includes(t));
  const addNote = btnByText('add a note');
  if (addNote) { addNote.click(); await new Promise(r => setTimeout(r, 500)); }
  const ta = modal.querySelector('textarea#custom-message, textarea[name="message"], textarea');
  if (!ta) return JSON.stringify({ ok: false, reason: 'no-note-field' });
  return JSON.stringify({ ok: true, limit: ta.getAttribute('maxlength') });
})()
```

Type the note into that textarea using the `type_text` / `fill` tool rather than setting `.value` in JS - LinkedIn listens for real input events and will otherwise send an empty note. Then click the send button:

```javascript
await (async () => {
  const modal = document.querySelector('.artdeco-modal');
  const send = Array.from(modal.querySelectorAll('button'))
    .find(b => /^(send|send invitation|send now)\b/i.test((b.innerText || b.getAttribute('aria-label') || '').trim()));
  if (!send || send.disabled) return JSON.stringify({ ok: false, reason: 'send-disabled' });
  send.click();
  return JSON.stringify({ ok: true });
})()
```

**Never click "Send without a note".** If the note field cannot be filled, abandon this person, record `connection_result` as `Failed`, and move on - a noteless request is worth less than not sending.

### 7d - Handle the limit modals

If a modal appears saying you have reached the **weekly invitation limit**, or offering Premium to send more:
- If `{stop_on_weekly_invite_limit}` is true (default), **stop the entire run immediately**. Do not dismiss and retry. Record the remaining rows as `Note drafted` and tell the user plainly that LinkedIn capped the week and when to resume.
- Never work around a LinkedIn limit. The cap in this project sits well below LinkedIn's own for exactly this reason.

### 7e - Record the send

```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --mark-sent
```
This sets `connection_sent = Yes`, `date_sent` to today, `connection_result = Sent`, `outreach_status = Request sent`, and re-checks the cap - it **refuses** the write if the cap is already used, which is the backstop if 7a was skipped.

### 7f - Pause

Wait a random interval within `{pause_between_sends_seconds}` (default 25 to 60 seconds) before the next person. This pacing is not optional: a burst of instant requests is the pattern LinkedIn flags.

---

## Step 8 - Record acceptances

When the user asks to check replies, or at the start of a later run, visit `https://www.linkedin.com/mynetwork/invitation-manager/sent/` and read which requests are still pending. Anyone no longer listed as pending has either accepted or declined - confirm by checking the profile for a 1st-degree badge.

```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --result Accepted
```
Valid values: `Sent`, `Pending`, `Accepted`, `Ignored`, `Withdrawn`, `Failed`. `Accepted` also moves `outreach_status` to `Accepted`, which is what puts the row into the follow-up queue.

---

## Step 9 - Report

Report:
- How many companies got a persona, and how many found nobody
- How many requests were sent, and the remaining daily cap
- Anything left at `Note drafted` and why (cap reached, awaiting confirmation, weekly limit)
- Per company: company name, person, title, tier, and the note that was sent

Example:
```
Week 36 outreach - 8 sent, 7 remaining on today's cap.

Acme Data - Lena Fischer, Head of Data (tier 1) - sent
  "Hi Lena, saw Acme is building out its first analytics team in Berlin..."
Northbeam - Tomas Silva, Founder (tier 4) - sent
  "Hi Tomas, Northbeam shipping attribution for DTC brands is..."

Drafted, not sent (daily cap): 3 companies.
No persona found: 1 company (Vela Systems - People tab is gated).
```

---

## Step 10 - Follow-ups

Only if `{followup_enabled}` is true. Ask the script who is due:

```bash
python "<this skill's dir>/scripts/update_outreach.py" --due-followups
```

This returns accepted connections with no reply yet whose `date_sent` is at least `{followup_1_days}` old (follow-up 1) or, having had follow-up 1, at least `{followup_2_days}` old (follow-up 2). It never returns anyone who already replied.

Write each follow-up in `{followup_tone}`, at most `{followup_char_limit}` characters. Follow-up 1 references the note they accepted and gives one concrete, useful thing - never "just bumping this". Follow-up 2 is shorter still and closes the loop gracefully, so the person is left with a good impression either way.

Send it as a LinkedIn message on their profile (Message button), then record it:
```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --followup 1 --message "..."
```

If someone replies, record it and stop the sequence:
```bash
python "<this skill's dir>/scripts/update_outreach.py" --company_id "{company_id}" --data '{"reply_status": "Positive"}'
```
Valid `reply_status`: `No reply`, `Replied`, `Positive`, `Not interested`. Anything other than `No reply` removes the row from the follow-up queue permanently.

---

## Edge cases

- **Login wall**: stop immediately and ask the user to log into LinkedIn in Chrome first.
- **0 results on the People tab for every tier**: retry once without `facetCurrentFunction`, then try the global people search (Step 3). Only then follow `{skip_if_no_persona}`.
- **Person is already a 1st-degree connection**: skip them and pick the next-best person at that company. If nobody else fits, record `connection_result` as `Failed` with a note in `notes` saying you are already connected.
- **Profile is out of network with no Connect button**: record `Failed` and move on. Do not use InMail.
- **The script refuses a note as too long**: rewrite it shorter. Do not edit the CSV directly and do not paste the long version into LinkedIn.
- **The script refuses `--mark-sent` on the cap**: the request may already have gone out in the browser. Tell the user exactly which person that was so the record can be fixed by hand, then stop the run.
- **CAPTCHA or a security checkpoint**: stop everything, record what has been sent so far, and tell the user. Never attempt to solve it.
- **The user asks to send more than the cap**: that is a settings change (`daily_connection_cap`). Follow `RETARGETING.md`, and say plainly that raising it above about 20 per day raises the account-restriction risk.
