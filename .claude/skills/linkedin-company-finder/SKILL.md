---
name: linkedin-company-finder
description: Find relevant companies on LinkedIn matching your configured ideal-customer profile (ships tuned for companies hiring Data Analysts) and append them to a local CSV tracker. Use this skill when asked to find companies, build a prospect list, find leads, look for new accounts, or update the connection tracker. Also use it when a scheduled task fires for the weekly prospecting run.
---

# LinkedIn Company Finder

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output - not in connection notes, reports, summaries, or any other text. Use a regular hyphen (-) instead. This applies to every piece of text this skill generates, without exception.

Finds companies on LinkedIn matching the configured ICP (loaded in Step 0a) and appends new ones to a local CSV, deduplicating by company slug. Ships tuned for companies hiring Data Analysts, but the skill text names no industry or role - all targeting lives in the outreach config.

---

## The one-and-only data file rule (read first)

There is **exactly one** data file in this project: **`{project_root}/connections.csv`**. Never create a second CSV, never write to a differently-named file, never write to a template or example file. The `append_companies.py` script enforces this - it refuses any path whose filename is not `connections.csv` and creates the master with the correct columns automatically if it does not exist yet. The column layout is defined once in `{project_root}/schema.py`; do not invent your own columns. This is what keeps the finder, the outreach skill, and the dashboard perfectly in sync.

---

## Configuration

- **Project root**: The folder this skill lives in, **auto-located by the helper script** - it walks up from its own location (`.claude/skills/.../scripts/`) to find the project root (the folder containing `schema.py`). You do **not** need to compute or pass the project path; it works no matter what the current working directory is (important for scheduled runs).
- **Master CSV path** (the only data file): `{project_root}/connections.csv`
- **Schema (column definitions)**: `{project_root}/schema.py`
- **Cache path**: `{project_root}/seen_companies.txt`
- **Script path**: `<this skill's directory>/scripts/append_companies.py`
- **How many companies to add this run**: `{companies_per_run}` from the config (stop earlier if fewer qualify).

> Everything targeting-specific in this skill is a code-word in `{curly braces}`, resolved from the outreach config loaded in **Step 0a**. The skill text never names an industry, role, or company itself - the config is the only legend.

---

## CUSTOMIZE: targeting a different kind of company

> **STOP - is the user asking to change settings, or to run a search?** If the user said something like "look for agencies instead", "search Germany", "only companies under 200 people", "target founders", or anything about changing *what kind of company* gets found - **do not run this skill.** That is a settings change. Follow `{project_root}/RETARGETING.md` (or see `CLAUDE.md` -> "Recognizing a settings change") to update `outreach_config.json`, then confirm the change. Only run this skill when the user wants to execute a search with the current settings.

The finder code-words (all documented in `RETARGETING.md`) are: `search_keywords`, `search_mode`, `location`, `industry_filter`, `company_size_allow`, `companies_per_run`, `pages_to_scan`, `require_company_page`, `blocklist_companies`, `blocklist_phrases`, `signal_keywords`, and `skip_if_already_in_tracker`.

**Forward-only:** retargeting never touches rows already in `connections.csv` - old companies stay in the tracker even if they no longer match the new knobs.

---

## Step 0a (DO THIS FIRST, before any browser navigation) - Load the outreach config

**The outreach config is the single source of truth for what this skill looks for.** Every search and filter decision below uses these values, not the example values written inline. This applies identically to on-demand runs and scheduled runs, so a scheduled prospecting run can never drift back to a previous ICP.

```bash
python -c "
import json, os
root = os.environ.get('PROJECT_ROOT') or '{project_root}'
for name in ('outreach_config.json', 'outreach_config.example.json'):
    p = os.path.join(root, name)
    if os.path.exists(p):
        print(json.dumps(json.load(open(p))['finder'])); break
"
```

(`{project_root}` is the auto-located root - get it with `python "<this skill's dir>/scripts/append_companies.py" --print-root`.) From the returned `finder` object, bind these code-words; every step below uses them as placeholders, never literal values:

| Code-word (config key) | Substituted into |
|---|---|
| `{search_keywords}` | the `keywords=` URL param (Step 1) |
| `{search_mode}` | which LinkedIn surface to search: `jobs`, `companies`, or `posts` (Step 1) |
| `{location}` | the `location=` URL param |
| `{industry_filter}` | which industries qualify (Step 3c) |
| `{company_size_allow}` | which employee-count bands qualify (Step 3c) |
| `{companies_per_run}` | how many new companies to collect before stopping (Step 4) |
| `{pages_to_scan}` | how many result pages to page through (Step 4) |
| `{require_company_page}` | if `true`, drop any company with no LinkedIn company page (Step 3c) |
| `{blocklist_companies}` / `{blocklist_phrases}` | the aggregator/recruiter blocklist (Step 3b) |
| `{signal_keywords}` | words that mark a "why now" signal worth recording (Step 3d) |
| `{skip_if_already_in_tracker}` | if `true`, skip companies already in the CSV (Step 0) |

**Hard rule:** the steps below contain **only code-words in `{curly braces}`** for anything targeting-specific - never a literal industry, keyword, or filter value. If **neither** config file exists, stop and tell the user the outreach config is missing - do not invent values.

---

## Step 0 - Load the seen-companies cache

Before opening any LinkedIn pages, read `{project_root}/seen_companies.txt`. Load all slugs into memory as a set (one per line, lowercased, ignore blanks). This is your **seen_slugs** filter - any company slug in this set is skipped immediately in Step 2, before any browser navigation is done for it. This prevents re-processing the same companies week after week.

If the file does not exist yet, treat seen_slugs as an empty set and continue.

---

## Page-ready gate (the reliability fix - run after EVERY navigation)

LinkedIn renders results **asynchronously, after the page load event**. Reading too early is the single biggest cause of "blank page / no results": the content had simply not arrived yet. The fix is to **poll the DOM until the target content exists, then read** - never a fixed sleep.

After every `navigate` (and every in-session click), run this gate with the `javascript_tool` **before** calling `get_page_text` or extracting anything. Swap the `ready()` body for the per-step predicate given in each step. Set `budgetMs` to **15000 on the very first navigation of the run** (the cold bootstrap is the slow one) and **8000** for every navigation after that.

```javascript
await (async () => {
  const budgetMs = 15000;            // FIRST navigation of the run; use 8000 afterwards
  const t0 = performance.now();
  const ready = () => {
    // Per-step predicate - REPLACE this body (see each step).
    return document.querySelectorAll('.job-card-container, [data-job-id], .search-results__list li').length > 0;
  };
  while (performance.now() - t0 < budgetMs) {
    const spinner = document.querySelector('.artdeco-loader');
    if (ready() && !spinner) return JSON.stringify({ ready: true, ms: Math.round(performance.now() - t0) });
    await new Promise(r => setTimeout(r, 250));
  }
  return JSON.stringify({ ready: false, ms: Math.round(performance.now() - t0), reason: 'timeout' });
})()
```

**Act on the result:**
- `{"ready": true}` -> the content has rendered; read/extract immediately.
- `{"ready": false, "reason": "timeout"}` -> **one** retry: re-issue the same navigation, then run the gate again. If it still times out, only then skip this item and move on.

> This **replaces every fixed "wait N seconds"** in the steps below. Do not add fixed sleeps on top of the gate.

---

## Step 1 - Navigate to the search

Build the search URL from the code-words loaded in Step 0a. Which URL depends on `{search_mode}`:

- **`jobs`** (default - finds companies that are actively hiring, the strongest buying signal):
  `https://www.linkedin.com/jobs/search/?keywords={search_keywords}&location={location}&f_TPR=r604800`
- **`companies`** (finds companies by name/description match):
  `https://www.linkedin.com/search/results/companies/?keywords={search_keywords}`
- **`posts`** (finds companies whose people are posting about the topic right now):
  `https://www.linkedin.com/search/results/content/?keywords={search_keywords}&datePosted=%22past-week%22`

Pages use the `start` parameter (`&start=25`, `&start=50`) for jobs, or `&page=2` for search results.

Run the **page-ready gate** with the predicate matching the mode:
```javascript
// jobs mode
const ready = () => document.querySelectorAll('.job-card-container, [data-job-id]').length > 0;
// companies / posts mode
const ready = () => document.querySelectorAll('.search-results-container li, .reusable-search__result-container').length > 0;
```
If LinkedIn shows a login page instead, stop and tell the user to log in first.

---

## Step 2 - Extract candidate companies from the current page

Run this JavaScript to pull every company reference off the results page:

```javascript
const out = [];
// Company links appear as /company/<slug> hrefs across all three search modes.
document.querySelectorAll('a[href*="/company/"]').forEach(a => {
  const m = a.href.match(/\/company\/([^\/?#]+)/);
  if (!m) return;
  const slug = m[1].toLowerCase();
  const text = (a.textContent || '').trim().split('\n')[0].trim();
  out.push({ slug, text });
});
// Jobs mode: the card subtitle carries the company name even when the link text is empty.
document.querySelectorAll('.job-card-container').forEach(card => {
  const nameEl = card.querySelector('.artdeco-entity-lockup__subtitle, .job-card-container__primary-description');
  const link = card.querySelector('a[href*="/company/"]');
  const m = link && link.href.match(/\/company\/([^\/?#]+)/);
  if (m) out.push({ slug: m[1].toLowerCase(), text: (nameEl?.textContent || '').trim() });
});
const seen = new Set();
const deduped = out.filter(o => {
  if (!o.slug || seen.has(o.slug)) return false;
  seen.add(o.slug);
  return true;
});
JSON.stringify({ total: deduped.length, companies: deduped });
```

**Immediately filter out any slug already in `seen_slugs`** (loaded in Step 0) when `{skip_if_already_in_tracker}` is true. Do not navigate to those companies at all.

---

## Step 3 - Qualify each candidate company

For each remaining slug, in order, until you have `{companies_per_run}` qualified companies.

### Pacing between companies

Before navigating to each company (except the first), wait a **random 2-4 seconds**. That keeps the cadence human. The page-ready gate then waits however long the page actually needs - do not stack long fixed sleeps on top of it.

### 3a - Load the company page

Navigate to `https://www.linkedin.com/company/{slug}/`, then run the **page-ready gate** with this predicate:
```javascript
const ready = () => !!document.querySelector('h1') &&
  (document.querySelectorAll('.org-top-card-summary-info-list__info-item').length > 0 ||
   /employees/i.test(document.body.innerText));
```
On a gate timeout after one retry, skip this company and move on (it is likely a redirect or a deleted page).

### 3b - Check the blocklist

Read the company name (the `h1`) and the About/tagline text. Skip the company entirely - create no row - if:
- the name matches any entry in `{blocklist_companies}` (case-insensitive), or
- the page text contains any phrase in `{blocklist_phrases}` (these mark staffing agencies and aggregators that hide the real employer).

### 3c - Extract the company fields and apply the ICP filters

First try `get_page_text`. A loaded company page returns a header block like:
```
Acme Data
The analytics layer for logistics
Software Development  Berlin, Germany  12K followers  51-200 employees
```

Parse from that:

| Field | How to extract |
|---|---|
| `company_id` | the `{slug}` (lowercased) - this is the de-dup key |
| `company_name` | the `h1` heading |
| `company_tagline` | the line immediately after the company name |
| `industry` | first segment of the third line, before the city |
| `hq_location` | city plus country on the third line |
| `company_size` | the "X-Y employees" pattern on the third line |
| `linkedin_company_url` | `https://www.linkedin.com/company/{slug}/` |
| `company_source` | the `{search_mode}` you used plus the keyword, e.g. `jobs: Data Analyst` |
| `date_added` / `week` | leave blank - the helper script fills both |

If `get_page_text` returns a pinned post instead of the header block, fall back to:
```javascript
const name = document.querySelector('h1')?.textContent?.trim();
const tagline = document.querySelector('.org-top-card-summary__tagline')?.textContent?.trim();
const infoItems = Array.from(document.querySelectorAll('.org-top-card-summary-info-list__info-item'))
  .map(el => el.textContent.trim());
JSON.stringify({ name, tagline, infoItems });
```

**Now apply the ICP filters. Drop the company (no row) if any fails:**
- `industry` is not in `{industry_filter}` - unless `{industry_filter}` is empty, which means any industry qualifies. Match loosely: a listed "Software Development" also matches "Software Development and IT".
- `company_size` is not in `{company_size_allow}` - unless the list is empty. If size is not shown, keep the company and leave the field blank.
- `{require_company_page}` is true and there is no real company page (a 404 or a redirect to a personal profile).

### 3d - Record the "why now" signal and why it is relevant

`signal` and `why_relevant` are what make the connection note in the outreach skill land. Do not skip them and do not write filler.

- **`signal`**: scan the company page (About, recent posts, the Jobs tab count) for any `{signal_keywords}` match, and write it as a short phrase: `hiring 3 analysts`, `raised Series A`, `opened a Berlin office`. If the company came from `jobs` mode, the open role itself is the signal - write it as `hiring: <exact job title>`. If nothing concrete is found, leave blank rather than inventing one.
- **`why_relevant`**: one or two sentences, in your own words, on what this company does and why it fits the ICP. Concrete only - name the product, the market, or the team being built. This is the raw material the outreach skill quotes from, so a vague sentence here produces a vague note later.

### 3e - Get the company website

Use the `find` tool with the query: `"Visit website or Learn more external link"`. This returns the `href` without navigating. Strip UTM parameters and subpaths - keep only the root domain. If `find` returns nothing, leave `company_website` blank and continue.

---

## Step 4 - Paginate

Continue through up to `{pages_to_scan}` pages using the `start` / `page` parameter, until you have `{companies_per_run}` qualified companies or you run out of results. Stop early if a page yields zero new slugs after the seen filter.

---

## Step 5 - Save to CSV

Build a JSON array of every qualified company object and run:

```bash
python "<this skill's dir>/scripts/append_companies.py" --companies '<json_array>'
```

Use the actual absolute path to `scripts/append_companies.py` inside this skill's directory. **You do not need to pass `--csv`** - the script auto-locates `connections.csv` in the project root from its own location, so it works regardless of the current working directory (this is what makes scheduled runs reliable). The script:
- Refuses to run if `--csv` is not the master `connections.csv` (single-file guardrail)
- Creates the master with the full canonical header (from `schema.py`) if it does not exist yet
- Loads `seen_companies.txt` and pre-filters any slugs already there
- Deduplicates by `company_id` against existing rows
- Stamps `date_added` and the `week` bucket automatically
- Writes full-width rows matching the existing header exactly (outreach columns left blank)
- Appends the new slugs to `seen_companies.txt`
- Prints: `Done. Added: N | Skipped (duplicates): N | Week: Week NN | CSV: /path`

---

## Step 6 - Report finder results (this is NOT the end - outreach follows immediately)

Give a brief summary. **Do NOT end your turn here - Step 7 is mandatory and must happen in the same response.** This is a mid-flow status update, not a stopping point.

Tell the user: how many pages were scanned, how many companies were found, how many were dropped by the blocklist and by the ICP filters (and why), and how many were added vs skipped as already-tracked.

Example: "Scanned 2 pages. Found 23 companies. Dropped 6 (3 staffing agencies, 3 outside the size range). Added 10 new companies to Week 36, 7 already in your tracker. Now finding the right person at each and drafting connection notes..."

**Then immediately continue to Step 7. Do not wait for user input.**

## Step 7 - Automatically run the outreach skill (MANDATORY - DO NOT STOP HERE)

**CRITICAL: Do NOT stop, pause, wait for user input, or end your turn after reporting finder results. You MUST immediately proceed to outreach in the same response - no exceptions. This applies to on-demand runs, scheduled runs, and every other context. Stopping here breaks the scheduled workflow.**

After Step 6, continue directly in the same response to run the outreach skill (`/linkedin-connect-outreach` in Claude Code, or follow `.claude/skills/linkedin-connect-outreach/SKILL.md` in Cowork) for every row that has no persona yet. The finder and the outreach skill are designed to run as one uninterrupted flow.

> The one legitimate pause is inside the outreach skill itself: if `confirm_before_first_send` is on, it asks the user once before the first batch of connection requests. That confirmation belongs to that skill, not to this one.

---

## Edge cases

- **Login page**: Stop immediately and tell the user to log into LinkedIn in Chrome first.
- **Company page never loads** (gate times out twice): skip that company and continue.
- **Slug redirects to a different company** (acquisition or rebrand): use the slug the browser ended on, so the de-dup key matches what a future run will see.
- **Company page shows no employee count**: keep the company, leave `company_size` blank; the size filter only drops a company when a size is shown and it is outside the allowed bands.
- **No website found**: leave `company_website` blank, continue - do not guess a URL.
- **CAPTCHA appears**: stop, save whatever companies have been collected so far by running the CSV script, then report to the user.
