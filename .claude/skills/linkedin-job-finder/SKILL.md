---
name: linkedin-job-finder
description: Find new LinkedIn job postings that match the user's CV (analyst roles - Data, Product, Business, BI - in the US and Europe), keep only remote jobs the user can legally take from their own country (no relocation, no sponsorship), record the job's department and its "Meet the hiring team" contacts, and append each job as a row in the local tracker. Use when asked to find jobs, find new vacancies, search for analyst roles, or when the scheduled morning job run fires.
---

# LinkedIn Job Finder

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output. Use a regular hyphen (-) instead.

Job-first outreach: instead of contacting people at companies that may not be hiring, this skill finds **specific open postings** that fit the user's CV and that the user can actually take from where they live. Each kept posting becomes one row in `connections.csv`; the `linkedin-connect-outreach` skill then finds that role's hiring manager and recruiter.

The skill text names no job title, country or skill - everything is a `{code-word}` from the `finder` block of the outreach config.

---

## The one-and-only data file rule

There is **exactly one** data file: `{project_root}/connections.csv`. This skill writes to it only through `scripts/append_jobs.py`, which refuses any other filename, de-duplicates by LinkedIn job id (`seen_jobs.txt`), skips companies that already got a job row in the last `{job_company_cooldown_days}` days (so one company's recruiters are not flooded), and stamps `date_added` / `week`.

---

## Step 0 - Load the config and what is already tracked

```bash
python -c "
import json, os
root = r'{project_root}'
for name in ('outreach_config.json', 'outreach_config.example.json'):
    p = os.path.join(root, name)
    if os.path.exists(p):
        print(json.dumps(json.load(open(p, encoding='utf-8'))['finder'])); break
"
python "<this skill's dir>/scripts/append_jobs.py" --status
```
(`{project_root}`: `python "<this skill's dir>/scripts/append_jobs.py" --print-root`.)

Bind these code-words:

| Code-word | Used in |
|---|---|
| `{job_titles}` / `{job_title_exclude}` | which titles to search, and title words that rule a posting out (Steps 1, 2) |
| `{job_markets}` | each market's `location` and `geoId` for the search URL (Step 1) |
| `{job_remote_only}` / `{job_posted_within}` | remote filter (`f_WT=2`) and recency filter (`f_TPR`) (Step 1) |
| `{jobs_per_run}` | how many new jobs to add this run, across all titles and markets (Step 5) |
| `{candidate_country}` / `{work_authorization}` | where the user lives and what they can legally accept (Step 3) |
| `{eligibility_reject_phrases}` / `{eligibility_accept_phrases}` | text in the posting that rules it out / in (Step 3) |
| `{cv_profile}` / `{min_cv_fit}` | the user's skills, years, seniority, languages, domains, and the fit bar (Step 4) |
| `{blocklist_companies}` / `{blocklist_phrases}` | staffing agencies and job aggregators to skip (Step 2) |

From `--status`, keep `seen_job_ids` and `companies_on_cooldown` - skip both **before** opening any job page.

**If `{candidate_country}` is blank or `{cv_profile}.skills` is empty, stop and tell the user** - the eligibility and CV-fit checks cannot run without them, and guessing would add jobs the user cannot take.

---

## Page-ready gate

Same as the other skills: after every navigation, poll the DOM until the target content exists (15000 ms budget on the first navigation, 8000 after), retry the navigation once on timeout, then skip. Never a fixed sleep. Predicates:
- search results: `document.querySelectorAll('[data-job-id], .job-card-container').length > 0`
- a job page: `!!document.querySelector('h1') && /about the job|job description/i.test(document.body.innerText)`

If a login page appears, stop and ask the user to log into LinkedIn.

---

## Step 1 - Search

For each market in `{job_markets}` and each title in `{job_titles}` (stop as soon as `{jobs_per_run}` jobs are kept):
```
https://www.linkedin.com/jobs/search/?keywords={title}&geoId={market.geoId}&location={market.location}&f_TPR={job_posted_within}&sortBy=DD
```
Add `&f_WT=2` when `{job_remote_only}` is true. URL-encode spaces as `%20`. Page with `&start=25`, `&start=50` (at most 3 pages per title per market).

---

## Step 2 - Read the result cards and pre-filter

```javascript
JSON.stringify(Array.from(document.querySelectorAll('[data-job-id]')).map(card => {
  const id = card.getAttribute('data-job-id');
  const title = card.querySelector('.job-card-list__title, .job-card-container__link strong, a[href*="/jobs/view/"]')?.innerText?.trim();
  const company = card.querySelector('.artdeco-entity-lockup__subtitle, .job-card-container__primary-description')?.innerText?.trim();
  const location = card.querySelector('.job-card-container__metadata-item, .artdeco-entity-lockup__caption')?.innerText?.trim();
  return { id, title, company, location };
}).filter(j => j.id && j.title))
```

Drop a card, without opening it, if: its id is in `seen_job_ids`; its title contains any `{job_title_exclude}` word (whole word, case-insensitive); the company matches `{blocklist_companies}`; or the card location names a single country that is not `{candidate_country}` **and** the title area says nothing like "worldwide" / "EMEA" / "Europe" (e.g. "United States (Remote)" is a US-only listing in practice - drop it unless the user lives in the US).

---

## Step 3 - Open the job and check location eligibility (the most important filter)

Navigate to `https://www.linkedin.com/jobs/view/{id}/`, gate, then read the full text of the posting (`get_page_text`, or the `#job-details` / `.jobs-description__content` element). Also read the top card: company name and link (`a[href*="/company/"]` -> slug), location line, workplace type (Remote / Hybrid / On-site), and "posted X ago".

Decide eligibility against `{work_authorization}`, in this order:

1. **Workplace is not Remote** (Hybrid or On-site) and `{work_authorization}` says remote only -> **reject**.
2. The text contains any `{eligibility_reject_phrases}` that restricts **where the candidate must live or what papers they need** (e.g. "must be located in the US", "authorized to work in the United States", "EU work permit required", "W2 only") and the restriction does not include `{candidate_country}` -> **reject**. Read the sentence, not just the phrase: "eligible to work in any EMEA country" may well include the user.
3. The text explicitly opens the role to the user (`{eligibility_accept_phrases}` such as "work from anywhere", "EMEA", "contractor / B2B", "Deel", or names `{candidate_country}` or its region) -> **keep**.
4. **Nothing is stated.** A listing whose location is one specific country other than `{candidate_country}` -> **reject** (in practice "Germany (Remote)" means residents of Germany). A region-wide listing (Europe, EMEA, Worldwide) -> **keep**, but write `location_eligibility` as `Region-wide remote, no residency rule stated - check before applying`.

Record `location_eligibility` as one short sentence quoting the deciding line, e.g. `"Remote across EMEA, contractors welcome" - open to Georgia`. Never mark a job eligible on a guess. When in real doubt, reject: a request about a job the user cannot take wastes a contact.

---

## Step 4 - Check the fit against the CV, and find the department

**CV fit.** Separate the posting's **must-haves** (required, "you have", minimum years) from nice-to-haves. Keep the job only if it meets `{min_cv_fit}` against `{cv_profile}`: the user has most must-have tools/skills, the required years are not far above `{cv_profile}.years_experience` (more than 2 years above = reject), the seniority matches `{cv_profile}.seniority`, and any required language is in `{cv_profile}.languages`. Write `cv_fit` as one line naming the matching must-haves and any gap, e.g. `SQL, Python, Power BI match; Looker is nice-to-have`.

**Department.** Find which team the role sits in - this is what the outreach skill uses to reach the right hiring manager and recruiter. Look, in order, at: the title ("Healthcare Data Analyst"), a "Team" / "Department" / "About the team" line, who the role reports to ("reporting to the Head of Marketing Analytics"), and the product area described. Write `job_department` as one or two plain words (`Healthcare`, `Marketing`, `Product`, `Finance`, `Operations`, `Risk`). If the posting gives no team, leave it blank - the outreach skill then uses the general data / recruiting contacts.

**Hiring team.** If the page has a **"Meet the hiring team"** section, read every person in it: name, headline, and profile link (`a[href*="/in/"]` inside that section). Put them in `notes` as `Hiring team: Name (headline) <url>; ...` - the outreach skill checks these first, since the job poster is the single most relevant person to contact.

---

## Step 5 - Save

Collect each kept job as an object and append them all at once:
```bash
python "<this skill's dir>/scripts/append_jobs.py" --jobs '<json array>'
```
Fields per job: `job_id`, `company_slug`, `company_name`, `job_title`, `job_url`, `job_location`, `job_workplace`, `job_department`, `job_posted` (YYYY-MM-DD, approximate from "posted X ago"), `location_eligibility`, `cv_fit`, `company_source` (`jobs: <title> / <market label>`), `signal` (`hiring: <job_title>`), `why_relevant` (one or two concrete sentences on the team and the work, from the posting - the outreach note quotes from this), `industry` / `company_size` / `hq_location` if shown on the job page, and `notes` (the hiring team). The script prints how many were added vs skipped (already seen, or company on cooldown).

Stop the whole search once `{jobs_per_run}` jobs are kept.

---

## Step 6 - Report

How many postings were scanned, how many dropped and why (location / work authorization, CV fit, title, already seen, cooldown), and the list of kept jobs: company, title, department, location, and the eligibility line. If the scheduled morning run called this skill, continue straight into the outreach step it asks for - do not stop here.

---

## Edge cases

- **Login wall / CAPTCHA / security checkpoint**: stop, save what was kept so far (Step 5), report.
- **Job closed** ("No longer accepting applications"): skip it.
- **Posted by a staffing agency or aggregator** (matches `{blocklist_companies}` / `{blocklist_phrases}`, or "our client"): skip - there is no reachable hiring manager.
- **Zero eligible jobs today**: that is a valid result - report it plainly. Never relax the location check to fill the quota.
