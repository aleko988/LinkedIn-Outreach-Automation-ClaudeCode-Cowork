#!/usr/bin/env python3
"""
LinkedIn Connect Outreach Dashboard
Run:  python dashboard/app.py   (from the project root)
Then open: http://localhost:5002

Reads the ONE data file (connections.csv) and renders it as the weekly outreach
sheet: company, profile, persona, request sent, follow-up. Never creates a second
CSV; every write goes back through the same header the file already has.
"""

import csv
import json
import os
from datetime import date, datetime

from flask import Flask, render_template_string, request, jsonify, abort

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "..", "connections.csv")
CONFIG_PATH = os.path.join(BASE_DIR, "..", "outreach_config.json")
CONFIG_EXAMPLE_PATH = os.path.join(BASE_DIR, "..", "outreach_config.example.json")


# ── config panel ───────────────────────────────────────────────────────────

def read_outreach_config():
    """Load the single source of truth for what the skills find and send.

    Prefers the live, user-edited outreach_config.json. Falls back to the shipped
    outreach_config.example.json so a fresh clone still shows settings.
    Returns (config_dict_or_None, source_label).
    """
    for path, label in ((CONFIG_PATH, "live"), (CONFIG_EXAMPLE_PATH, "default")):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f), label
            except (ValueError, OSError):
                continue
    return None, "none"


# Display spec for the "Current campaign settings" panel.
# (config_key, display label, Bootstrap icon) - order is left to right, wrapping.
# Any OTHER knob carrying a "<key>_label" companion is appended automatically in the
# same style (see _auto_label_rows), so a brand-new knob shows up with no edit here.
_FINDER_KNOBS = [
    ("search_keywords",    "Keywords",       "bi-search"),
    ("search_mode",        "Search surface", "bi-compass"),
    ("location",           "Location",       "bi-geo-alt"),
    ("company_size_allow", "Company size",   "bi-buildings"),
    ("industry_filter",    "Industries",     "bi-diagram-3"),
    ("companies_per_run",  "New per run",    "bi-plus-square"),
]
_OUTREACH_KNOBS = [
    ("persona_tiers",         "Persona priority", "bi-person-lines-fill"),
    ("personas_per_company",  "People per company", "bi-people"),
    ("note_char_limit",       "Note limit",       "bi-textarea-t"),
    ("note_monthly_limit",    "Note budget/mo",   "bi-envelope-paper"),
    ("daily_connection_cap",  "Daily cap",        "bi-speedometer2"),
    ("note_tone",             "Note tone",        "bi-chat-quote"),
    ("followup_auto_send",    "Follow-up sending", "bi-send"),
    ("followup_1_days",       "Follow-up 1",      "bi-arrow-repeat"),
    ("followup_2_days",       "Follow-up 2",      "bi-arrow-repeat"),
    ("peer_enabled",          "Peer track",       "bi-people-fill"),
    ("pitch_link",            "Pitch link",       "bi-link-45deg"),
    ("no_accept_email_days",  "Email fallback",   "bi-envelope"),
]
_CONSUMED_LABELS = {
    "search_mode_label", "company_size_label", "note_char_limit_label",
    "daily_connection_cap_label", "personas_per_company_label",
    "followup_1_label", "followup_2_label",
}


def _knob_row(block, key, label, icon):
    """Resolve one knob into a display row, or None if it has no value.

    A "<key>_label" companion (the config's display convention) wins over the raw
    value so the panel shows human-readable text. Tier lists render as chips.
    """
    if key == "persona_tiers":
        chips = [t.get("type", "") for t in block.get(key, []) if t.get("type")]
        return {"icon": icon, "label": label, "value": "", "chips": chips} if chips else None
    if key in ("industry_filter", "company_size_allow"):
        if block.get(f"{key}_label"):
            return {"icon": icon, "label": label,
                    "value": str(block[f"{key}_label"]), "chips": None}
        items = [str(x) for x in (block.get(key) or []) if str(x).strip()]
        return {"icon": icon, "label": label, "value": "", "chips": items} if items else None

    value = block.get(f"{key}_label") or block.get(key, "")
    if key in ("search_keywords",):
        value = str(value).replace("+", " ")
    if key in ("followup_1_days", "followup_2_days") and str(value).isdigit():
        value = f"day {value}"
    if isinstance(value, bool):
        value = "On" if value else "Off"
    value = str(value).strip()
    return {"icon": icon, "label": label, "value": value, "chips": None} if value else None


def _auto_label_rows(block, curated_keys):
    """Surface any NEW knob that carries a "<key>_label" companion.

    This is what makes the panel self-updating: a retarget that adds a brand-new
    knob with a human-readable "<key>_label" appears here automatically, in the same
    style, with no edit to this file. Plumbing keys (function codes, phrase lists)
    have no _label, so they correctly stay hidden.
    """
    rows = []
    for k, v in block.items():
        if not k.endswith("_label") or k in _CONSUMED_LABELS:
            continue
        base = k[: -len("_label")]
        if base in curated_keys:
            continue
        text = str(v).strip()
        if not text:
            continue
        rows.append({"icon": "bi-sliders", "label": base.replace("_", " ").capitalize(),
                     "value": text, "chips": None})
    return rows


def campaign_config_summary():
    """Flatten the outreach config into display rows for the dashboard panel."""
    cfg, source = read_outreach_config()
    if not cfg:
        return [], {"source": "none", "campaign": "No config found", "updated": "",
                    "captured_fields": []}

    f = cfg.get("finder", {})
    o = cfg.get("outreach", {})

    rows = []
    for key, label, icon in _FINDER_KNOBS:
        row = _knob_row(f, key, label, icon)
        if row:
            rows.append(row)
    rows += _auto_label_rows(f, {k for k, _, _ in _FINDER_KNOBS})

    for key, label, icon in _OUTREACH_KNOBS:
        row = _knob_row(o, key, label, icon)
        if row:
            rows.append(row)
    rows += _auto_label_rows(o, {k for k, _, _ in _OUTREACH_KNOBS})

    meta = {
        "source": source,
        "campaign": cfg.get("campaign_label", ""),
        "updated": cfg.get("last_updated", ""),
        "captured_fields": list(cfg.get("custom_fields_added") or []),
    }
    return rows, meta


def config_limits():
    cfg, _ = read_outreach_config()
    o = (cfg or {}).get("outreach", {})
    return {
        "note_char_limit": int(o.get("note_char_limit", 200)),
        "daily_cap": int(o.get("daily_connection_cap", 15)),
        "note_monthly_cap": int(o.get("note_monthly_limit", 5)),
        "followup_1_days": int(o.get("followup_1_days", 0)),
        "followup_2_days": int(o.get("followup_2_days", 4)),
        "followup_auto_send": bool(o.get("followup_auto_send", False)),
        "no_accept_email_days": int(o.get("no_accept_email_days", 5)),
        "job_rows_only": str(o.get("followup_scope", "all")).strip() == "job_rows",
    }


# ── data ───────────────────────────────────────────────────────────────────

STATUSES = ["Not started", "Note drafted", "Request sent", "Accepted", "Replied", "Archived"]
RESULTS = ["", "Sent", "Pending", "Accepted", "Ignored", "Withdrawn", "Failed", "Emailed"]
REPLIES = ["No reply", "Replied", "Positive", "Not interested"]

STATUS_COLORS = {
    "Not started":  "#6c757d",
    "Note drafted": "#b8860b",
    "Request sent": "#0d6efd",
    "Accepted":     "#198754",
    "Replied":      "#6610f2",
    "Archived":     "#adb5bd",
}


def read_rows():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(rows):
    """Write back through the file's existing header - never reshape the CSV."""
    if not rows:
        return
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        fieldnames = list(csv.DictReader(f).fieldnames or [])
    if not fieldnames:
        fieldnames = list(rows[0].keys())
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(rows)


def days_since(value):
    v = (value or "").strip()
    if not v:
        return None
    try:
        return (date.today() - datetime.strptime(v, "%Y-%m-%d").date()).days
    except ValueError:
        return None


# Contact slots: (slot, display label). Slot 1 = primary persona_*/connection_* columns,
# slot 2 = persona2_*, slot 3 = the peer (persona3_*). Mirrors schema.persona_field.
CONTACT_SLOTS = (("1", "Primary contact"), ("2", "Second contact"), ("3", "Peer"))


def pf(slot, key):
    if slot == "1":
        if key in ("name", "title", "linkedin", "tier"):
            return f"persona_{key}"
        return "connection_note" if key == "note" else key
    return f"persona{slot}_{key}"


def parse_day(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _in_scope(row, limits):
    """followup_scope "job_rows": legacy company-only rows (no job_id) get no follow-ups."""
    return not limits.get("job_rows_only") or bool((row.get("job_id") or "").strip())


def followup_due_for(row, limits, slot):
    """Which follow-up (1, 2 or None) this contact is waiting on - same rules as
    update_outreach.py --due-followups: follow-up 1 followup_1_days after acceptance
    (immediately for a plain connect), follow-up 2 followup_2_days after follow-up 1."""
    if not _in_scope(row, limits) or not (row.get(pf(slot, "name")) or "").strip():
        return None
    if (row.get(pf(slot, "connection_result")) or "").strip() != "Accepted":
        return None
    if (row.get(pf(slot, "reply_status")) or "No reply").strip() not in ("No reply", ""):
        return None
    anchor = parse_day(row.get(pf(slot, "accepted_date"))) or parse_day(row.get(pf(slot, "date_sent")))
    if not anchor:
        return None
    today = date.today()
    has_f1 = bool((row.get(pf(slot, "followup_1_date")) or "").strip())
    has_f2 = bool((row.get(pf(slot, "followup_2_date")) or "").strip())
    note_was_used = (row.get(pf(slot, "note_sent_with_request")) or "").strip() == "Yes"
    if not has_f1 and ((today - anchor).days >= limits["followup_1_days"] or not note_was_used):
        return 1
    f1 = parse_day(row.get(pf(slot, "followup_1_date"))) or anchor
    if has_f1 and not has_f2 and (today - f1).days >= limits["followup_2_days"]:
        return 2
    return None


def email_due_for(row, limits, slot):
    """True when this contact's request has sat unaccepted for no_accept_email_days -
    time to try email instead (drafted by the skill, sent by the user)."""
    if not _in_scope(row, limits):
        return False
    if (row.get(pf(slot, "connection_sent")) or "").strip() != "Yes":
        return False
    if (row.get(pf(slot, "connection_result")) or "").strip() not in ("Sent", "Pending", ""):
        return False
    age = days_since(row.get(pf(slot, "date_sent")))
    return age is not None and age >= limits["no_accept_email_days"]


def contacts(row, limits):
    """Every filled contact slot on this row, flattened to the same keys so the
    templates can loop instead of repeating a block per slot."""
    out = []
    for slot, label in CONTACT_SLOTS:
        name = (row.get(pf(slot, "name")) or "").strip()
        if not name:
            continue
        g = lambda k: (row.get(pf(slot, k)) or "").strip()
        out.append({
            "slot": slot, "label": label, "name": name, "title": g("title"),
            "linkedin": g("linkedin"), "tier": g("tier"),
            "location": g("persona_location") if slot == "1" else "",
            "common_ground": g("common_ground") if slot == "3" else "",
            "note": g("note"), "note_len": len(g("note")),
            "sent": g("connection_sent") == "Yes", "date_sent": g("date_sent"),
            "result": g("connection_result"), "accepted_date": g("accepted_date"),
            "note_used": g("note_sent_with_request") == "Yes",
            "f1_msg": g("followup_1_message"), "f1_date": g("followup_1_date"),
            "f2_msg": g("followup_2_message"), "f2_date": g("followup_2_date"),
            "reply": g("reply_status") or "No reply", "email_draft": g("email_draft"),
            "due": followup_due_for(row, limits, slot),
            "email_due": email_due_for(row, limits, slot),
            "age": days_since(g("date_sent")),
            "result_field": pf(slot, "connection_result"), "reply_field": pf(slot, "reply_status"),
        })
    return out


def followup_due(row, limits):
    """First due follow-up across all contacts (kept for /api/stats)."""
    return next((d for s, _ in CONTACT_SLOTS for d in [followup_due_for(row, limits, s)] if d), None)


def sent_today_count(rows):
    """Counts each contact's send separately, matching update_outreach.py's daily-cap
    accounting - three contacts messaged at one company today count as 3."""
    today = date.today().isoformat()
    return sum(1 for r in rows for s, _ in CONTACT_SLOTS
               if (r.get(pf(s, "date_sent")) or "").strip() == today)


def notes_sent_this_month_count(rows):
    ym = date.today().strftime("%Y-%m")
    return sum(1 for r in rows for s, _ in CONTACT_SLOTS
               if (r.get(pf(s, "note_sent_with_request")) or "").strip() == "Yes"
               and (r.get(pf(s, "date_sent")) or "").strip().startswith(ym))


def row_matches(row, query):
    q = query.lower()
    fields = [row.get(k, "") for k in
              ("company_name", "job_title", "job_department", "persona_name", "persona_title", "persona2_name",
             "persona3_name", "industry",
               "hq_location", "signal", "why_relevant", "week")]
    return any(q in (f or "").lower() for f in fields)


def week_sort_key(label):
    """Sort 'Week 36' style buckets numerically, newest first; blanks last."""
    digits = "".join(c for c in (label or "") if c.isdigit())
    return (-int(digits) if digits else 1, label or "zzz")


# ── templates ──────────────────────────────────────────────────────────────

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LinkedIn Connect Outreach</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>
    :root {
      --bg: #f6f7f9; --surface: #ffffff; --line: #ebedf0;
      --ink: #131720; --ink-soft: #5b6472; --ink-faint: #9aa1ad;
      --brand: #3b5bdb; --brand-bg: #eef2ff;
      --ok: #198754; --ok-bg: #e6f9ee; --warn: #8a6400; --warn-bg: #fff8e1;
    }
    body { background: var(--bg); font-size: .92rem; color: var(--ink);
           -webkit-font-smoothing: antialiased; }
    .navbar { background: var(--ink) !important; padding: .7rem 1.5rem; }
    .navbar-brand { color: #fff !important; font-weight: 700; font-size: 1rem; letter-spacing: -.01em; }
    .search-wrap input { font-size: .85rem; border-radius: 8px; padding: .4rem .9rem; border: none; }
    .search-wrap button { border-radius: 8px; font-size: .82rem; }

    .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
                  margin-right: 6px; vertical-align: middle; }
    .status-text { font-size: .76rem; font-weight: 500; color: var(--ink-soft); vertical-align: middle; }

    /* Stat strip */
    .stat-strip { background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
                  display: flex; overflow: hidden; }
    .stat-cell { flex: 1; padding: 16px 18px; text-align: center; border-left: 1px solid var(--line); }
    .stat-cell:first-child { border-left: none; }
    .stat-cell.stat-highlight { background: var(--brand-bg); }
    .stat-value { font-size: 1.7rem; font-weight: 700; line-height: 1.05; letter-spacing: -.02em; }
    .stat-cell.stat-highlight .stat-value { color: var(--brand); }
    .stat-label { font-size: .7rem; text-transform: uppercase; letter-spacing: .6px;
                  color: var(--ink-soft); font-weight: 600; margin-top: 4px; }
    .stat-sub { font-size: .73rem; color: var(--ink-faint); margin-top: 2px; }

    /* Tab cards */
    .tabnav { display: flex; gap: 10px; }
    .tab-card { flex: 1; text-decoration: none; color: inherit; text-align: center;
                background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
                padding: 14px 12px; transition: border-color .15s, box-shadow .15s, background .15s; }
    .tab-card:hover { border-color: #d7dbe0; box-shadow: 0 4px 14px rgba(19,23,32,.06); color: inherit; }
    .tab-card.active { border-color: var(--brand); background: var(--brand-bg); }
    .tab-num { font-size: 1.5rem; font-weight: 700; line-height: 1.05; letter-spacing: -.02em; }
    .tab-card.active .tab-num { color: var(--brand); }
    .tab-name { font-size: .7rem; text-transform: uppercase; letter-spacing: .5px;
                color: var(--ink-soft); font-weight: 600; margin-top: 4px; }
    .tab-card.active .tab-name { color: var(--brand); }

    /* Weekly sheet table */
    .week-block { background: var(--surface); border: 1px solid var(--line);
                  border-radius: 12px; overflow: hidden; margin-bottom: 18px; }
    .week-head { padding: 12px 18px; font-weight: 700; font-size: .85rem;
                 border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 10px; }
    .week-count { font-size: .72rem; font-weight: 600; color: var(--ink-faint); }
    .sheet { width: 100%; margin: 0; font-size: .85rem; }
    .sheet th { font-size: .66rem; text-transform: uppercase; letter-spacing: .5px;
                color: var(--ink-faint); font-weight: 700; padding: 10px 18px;
                border-bottom: 1px solid var(--line); white-space: nowrap; }
    .sheet td { padding: 12px 18px; border-bottom: 1px solid var(--line); vertical-align: top; }
    .sheet tr:last-child td { border-bottom: none; }
    .sheet tr:hover td { background: #fafbfc; }
    .c-company { font-weight: 600; color: var(--ink); text-decoration: none; }
    .c-company:hover { color: var(--brand); }
    .c-sub { font-size: .76rem; color: var(--ink-faint); }
    .c-persona { color: var(--ink); }
    .c-tier { font-size: .66rem; font-weight: 700; text-transform: uppercase; letter-spacing: .4px;
              background: var(--brand-bg); color: var(--brand); padding: 2px 8px; border-radius: 20px; }
    .yes-pill { font-size: .72rem; font-weight: 700; padding: 2px 9px; border-radius: 20px;
                background: var(--ok-bg); color: var(--ok); }
    .no-pill  { font-size: .72rem; font-weight: 600; padding: 2px 9px; border-radius: 20px;
                background: #eef1f4; color: var(--ink-soft); }
    .due-pill { font-size: .72rem; font-weight: 700; padding: 2px 9px; border-radius: 20px;
                background: var(--warn-bg); color: var(--warn); }
    .note-cell { color: var(--ink-soft); font-size: .8rem; line-height: 1.45; max-width: 380px; }
    .empty { padding: 40px; text-align: center; color: var(--ink-faint); }

    /* Detail page */
    .panel { border: 1px solid var(--line); border-radius: 12px; background: var(--surface); padding: 20px; }
    .panel-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .5px;
                   color: var(--ink-faint); font-weight: 600; margin-bottom: 1px; }
    .panel-val { font-size: .9rem; color: var(--ink); }
    .note-box { font-size: .92rem; line-height: 1.6; padding-left: 12px;
                border-left: 2px solid var(--line); white-space: pre-wrap; }
    .char-count { font-size: .74rem; color: var(--ink-faint); }
    .char-count.over { color: #b91c1c; font-weight: 700; }
    .copy-btn { font-size: .76rem; padding: .25em .6em; border-radius: 6px; color: var(--ink-soft);
                border: 1px solid transparent; background: transparent; cursor: pointer; }
    .copy-btn:hover { background: var(--bg); color: var(--ink); }
    .copy-btn.copied { color: #1f9d55; }
    .section-title { font-size: .95rem; font-weight: 700; margin-bottom: 14px; letter-spacing: -.01em; }

    /* Campaign settings panel */
    .settings { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; }
    .settings > summary { list-style: none; cursor: pointer; padding: 13px 18px; font-size: .82rem;
        font-weight: 600; display: flex; align-items: center; gap: 8px; }
    .settings > summary::-webkit-details-marker { display: none; }
    .settings > summary::after { content: "\\F282"; font-family: "bootstrap-icons"; margin-left: auto;
        color: var(--ink-faint); font-weight: 400; transition: transform .15s; }
    .settings[open] > summary::after { transform: rotate(180deg); }
    .ss-role { font-weight: 500; color: var(--ink-soft); }
    .ss-badge { font-size: .66rem; text-transform: uppercase; letter-spacing: .4px; font-weight: 700;
        padding: 2px 7px; border-radius: 20px; }
    .ss-default { background: #eef1f4; color: var(--ink-soft); }
    .ss-live { background: var(--brand-bg); color: var(--brand); }
    .ss-updated { font-size: .7rem; color: var(--ink-faint); font-weight: 500; }
    .ss-body { padding: 4px 18px 16px; }
    .ss-note { font-size: .76rem; color: var(--ink-soft); margin-bottom: 12px; }
    .ss-note code { background: #eef1f4; padding: 1px 5px; border-radius: 4px; font-size: .72rem; }
    .ss-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
        gap: 1px; background: var(--line); border: 1px solid var(--line);
        border-radius: 8px; overflow: hidden; }
    .ss-item { background: var(--surface); padding: 11px 14px; display: flex; gap: 10px; align-items: flex-start; }
    .ss-item > i { color: var(--ink-faint); font-size: .95rem; width: 16px; text-align: center; flex: none; margin-top: 1px; }
    .ss-key { display: block; font-size: .65rem; text-transform: uppercase; letter-spacing: .4px;
        color: var(--ink-faint); font-weight: 700; margin-bottom: 3px; }
    .ss-val { font-size: .84rem; line-height: 1.35; font-weight: 500; overflow-wrap: anywhere; }
    .ss-chips { display: flex; flex-wrap: wrap; gap: 5px; }
    .ss-chip { font-size: .72rem; font-weight: 600; background: var(--brand-bg); color: var(--brand);
        padding: 2px 9px; border-radius: 20px; }
    .ss-captured { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 12px;
        font-size: .76rem; color: var(--ink-soft); }
  </style>
</head>
<body>
<nav class="navbar navbar-dark mb-3">
  <div class="container-fluid">
    <a class="navbar-brand" href="/"><i class="bi bi-person-plus me-2"></i>Connect Outreach</a>
    <form class="d-flex search-wrap gap-2" method="get" action="/">
      <input class="form-control form-control-sm" type="search" name="q"
             placeholder="Search companies, people, signals..."
             value="{{ request.args.get('q','') }}" style="width:260px">
      <button class="btn btn-outline-light btn-sm" type="submit">Search</button>
    </form>
  </div>
</nav>
<div class="container-fluid px-4">
  {% block content %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
function flashCopied(btn) {
  const old = btn.innerHTML;
  btn.innerHTML = '<i class="bi bi-check2"></i> Copied';
  btn.classList.add('copied');
  setTimeout(() => { btn.innerHTML = old; btn.classList.remove('copied'); }, 1800);
}
function copyText(text, btn) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => flashCopied(btn)).catch(() => legacyCopy(text, btn));
  } else { legacyCopy(text, btn); }
}
function legacyCopy(text, btn) {
  const ta = document.createElement('textarea');
  ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta); ta.focus(); ta.select();
  try { document.execCommand('copy'); } catch (e) {}
  document.body.removeChild(ta); flashCopied(btn);
}
</script>
</body>
</html>
"""

SETTINGS_PANEL = """
<details class="settings mb-4">
  <summary>
    <i class="bi bi-sliders"></i>
    Current campaign settings
    <span class="ss-role">{{ cfg_meta.campaign }}</span>
    {% if cfg_meta.source == 'live' %}<span class="ss-badge ss-live">live</span>
    {% elif cfg_meta.source == 'default' %}<span class="ss-badge ss-default">shipped default</span>{% endif %}
    {% if cfg_meta.updated %}<span class="ss-updated">updated {{ cfg_meta.updated }}</span>{% endif %}
  </summary>
  <div class="ss-body">
    <div class="ss-note">This is what the next run will do. To change it, just say what you want in plain
      language (for example "target founders" or "search Germany") and the agent edits
      <code>outreach_config.json</code> for you. Existing rows are never re-filtered.</div>
    {% if cfg_rows %}
    <div class="ss-grid">
      {% for r in cfg_rows %}
      <div class="ss-item">
        <i class="bi {{ r.icon }}"></i>
        <div class="ss-cell">
          <span class="ss-key">{{ r.label }}</span>
          {% if r.chips %}
            <div class="ss-chips">{% for c in r.chips %}<span class="ss-chip">{{ c }}</span>{% endfor %}</div>
          {% else %}
            <div class="ss-val">{{ r.value }}</div>
          {% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
    {% else %}<div class="ss-note">No config file found.</div>{% endif %}
    {% if cfg_meta.captured_fields %}
    <div class="ss-captured"><span>Also captured per company:</span>
      {% for f in cfg_meta.captured_fields %}<span class="ss-chip">{{ f }}</span>{% endfor %}
    </div>{% endif %}
  </div>
</details>
"""

INDEX_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
{% block content %}

<div class="stat-strip mb-3">
  <div class="stat-cell"><div class="stat-value">{{ stats.companies }}</div>
    <div class="stat-label">Companies</div><div class="stat-sub">in the tracker</div></div>
  <div class="stat-cell"><div class="stat-value">{{ stats.sent }}</div>
    <div class="stat-label">Requests sent</div><div class="stat-sub">all time</div></div>
  <div class="stat-cell"><div class="stat-value">{{ stats.accepted }}</div>
    <div class="stat-label">Accepted</div><div class="stat-sub">{{ stats.accept_rate }} acceptance</div></div>
  <div class="stat-cell"><div class="stat-value">{{ stats.replied }}</div>
    <div class="stat-label">Replied</div><div class="stat-sub">conversations started</div></div>
  <div class="stat-cell stat-highlight"><div class="stat-value">{{ stats.remaining }}</div>
    <div class="stat-label">Left today</div><div class="stat-sub">{{ stats.sent_today }} of {{ stats.cap }} used</div></div>
  <div class="stat-cell"><div class="stat-value">{{ stats.notes_remaining }}</div>
    <div class="stat-label">Notes left</div><div class="stat-sub">{{ stats.notes_used_month }} of {{ stats.note_cap }} this month</div></div>
</div>

<div class="tabnav mb-4">
  {% for tab in tabs %}
  <a class="tab-card {% if active_tab == tab.name %}active{% endif %}"
     href="/?tab={{ tab.name|urlencode }}&q={{ q }}">
    <div class="tab-num">{{ tab.count }}</div>
    <div class="tab-name">{{ tab.name }}</div>
  </a>
  {% endfor %}
</div>

""" + SETTINGS_PANEL + """

{% if not weeks %}
  <div class="week-block"><div class="empty">
    <i class="bi bi-inbox" style="font-size:1.6rem"></i>
    <div class="mt-2">Nothing here yet. Ask the agent to find companies to start a week.</div>
  </div></div>
{% endif %}

{% for wk in weeks %}
<div class="week-block">
  <div class="week-head"><i class="bi bi-calendar3"></i>{{ wk.label }}
    <span class="week-count">{{ wk.rows|length }} compan{{ 'y' if wk.rows|length == 1 else 'ies' }}</span></div>
  <table class="sheet">
    <thead><tr>
      <th style="width:22%">Company name</th>
      <th style="width:16%">LinkedIn profile</th>
      <th style="width:20%">Ideal persona</th>
      <th style="width:13%">Request sent</th>
      <th style="width:29%">Follow up</th>
    </tr></thead>
    <tbody>
    {% for r in wk.rows %}
      <tr>
        <td>
          <a class="c-company" href="/company/{{ r.company_id }}">{{ r.company_name or r.company_id }}</a>
          <div class="c-sub">
            <span class="status-dot" style="background:{{ status_colors.get(r.outreach_status, '#6c757d') }}"></span>
            <span class="status-text">{{ r.outreach_status or 'Not started' }}</span>
          </div>
          {% if r.job_title %}<div class="c-sub"><i class="bi bi-briefcase"></i>
            <a href="{{ r.job_url }}" target="_blank" class="text-decoration-none">{{ r.job_title }}</a>
            {% if r.job_department %} - {{ r.job_department }}{% endif %}</div>
            {% if r.job_location %}<div class="c-sub"><i class="bi bi-geo-alt"></i> {{ r.job_location }}</div>{% endif %}
          {% elif r.signal %}<div class="c-sub"><i class="bi bi-lightning-charge"></i> {{ r.signal }}</div>{% endif %}
        </td>
        <td>
          {% for c in r._contacts %}{% if not loop.first %}<hr class="my-1">{% endif %}
            {% if c.linkedin %}<a href="{{ c.linkedin }}" target="_blank" class="text-decoration-none">
              <i class="bi bi-linkedin"></i> Profile</a>{% else %}<span class="c-sub">-</span>{% endif %}
          {% else %}
            {% if r.linkedin_company_url %}<a href="{{ r.linkedin_company_url }}" target="_blank"
              class="text-decoration-none c-sub"><i class="bi bi-building"></i> Company</a>
            {% else %}<span class="c-sub">-</span>{% endif %}
          {% endfor %}
        </td>
        <td>
          {% for c in r._contacts %}{% if not loop.first %}<hr class="my-1">{% endif %}
            <div class="c-persona">{{ c.name }}</div>
            <div class="c-sub">{{ c.title }}</div>
            {% if c.tier %}<span class="c-tier">{{ c.tier }}</span>{% endif %}
          {% else %}<span class="c-sub">not found yet</span>{% endfor %}
        </td>
        <td>
          {% for c in r._contacts %}{% if not loop.first %}<hr class="my-1">{% endif %}
            {% if c.sent %}
              <span class="yes-pill">Yes</span>
              <div class="c-sub mt-1">{{ c.date_sent }}</div>
              {% if c.result and c.result != 'Sent' %}<div class="c-sub">{{ c.result }}</div>{% endif %}
            {% elif c.note %}<span class="no-pill">Drafted</span>
            {% elif c.result %}<span class="c-sub">{{ c.result }}</span>
            {% else %}<span class="no-pill">No</span>{% endif %}
          {% else %}<span class="no-pill">No</span>{% endfor %}
        </td>
        <td>
          {% for c in r._contacts %}{% if not loop.first %}<hr class="my-1">{% endif %}
            {% if c.due %}
              <span class="due-pill">Follow-up {{ c.due }} due</span>
              <div class="c-sub mt-1">{{ c.age }} days since sent</div>
            {% elif c.email_due %}
              <span class="due-pill">Try email</span>
              <div class="c-sub mt-1">{{ c.age }} days, not accepted{% if c.email_draft %} - draft ready{% endif %}</div>
            {% elif c.reply != 'No reply' %}<span class="yes-pill">{{ c.reply }}</span>
            {% elif c.f2_date %}<div class="c-sub">2 sent, last {{ c.f2_date }}</div>
            {% elif c.f1_date %}<div class="c-sub">1 sent {{ c.f1_date }}</div>
            {% elif c.note %}<div class="note-cell">{{ c.note }}</div>
            {% else %}<span class="c-sub">-</span>{% endif %}
          {% else %}<span class="c-sub">-</span>{% endfor %}
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</div>
{% endfor %}
<div class="mb-5"></div>
{% endblock %}
""")

DETAIL_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
{% block content %}
<a href="/" class="text-decoration-none c-sub"><i class="bi bi-arrow-left"></i> Back to all weeks</a>

<div class="row g-3 mt-1 mb-5">
  <div class="col-lg-8">
    <div class="panel mb-3">
      <div class="d-flex justify-content-between align-items-start">
        <div>
          <div class="section-title mb-1">{{ r.company_name }}</div>
          <div class="c-sub">{{ r.company_tagline }}</div>
        </div>
        <div class="text-end">
          <span class="status-dot" style="background:{{ status_colors.get(r.outreach_status, '#6c757d') }}"></span>
          <span class="status-text">{{ r.outreach_status }}</span>
        </div>
      </div>
      <hr>
      <div class="row g-3">
        <div class="col-sm-4"><div class="panel-label">Industry</div><div class="panel-val">{{ r.industry or '-' }}</div></div>
        <div class="col-sm-4"><div class="panel-label">Size</div><div class="panel-val">{{ r.company_size or '-' }}</div></div>
        <div class="col-sm-4"><div class="panel-label">HQ</div><div class="panel-val">{{ r.hq_location or '-' }}</div></div>
        <div class="col-sm-4"><div class="panel-label">Week</div><div class="panel-val">{{ r.week or '-' }}</div></div>
        <div class="col-sm-4"><div class="panel-label">Added</div><div class="panel-val">{{ r.date_added or '-' }}</div></div>
        <div class="col-sm-4"><div class="panel-label">Source</div><div class="panel-val">{{ r.company_source or '-' }}</div></div>
      </div>
      {% if r.job_title %}<hr>
        <div class="panel-label">Job</div>
        <div class="panel-val"><a href="{{ r.job_url }}" target="_blank" class="text-decoration-none">{{ r.job_title }}</a>
          {% if r.job_department %}<span class="c-tier ms-2">{{ r.job_department }}</span>{% endif %}</div>
        <div class="row g-3 mt-1">
          <div class="col-sm-4"><div class="panel-label">Location</div><div class="panel-val">{{ r.job_location or '-' }}</div></div>
          <div class="col-sm-4"><div class="panel-label">Workplace</div><div class="panel-val">{{ r.job_workplace or '-' }}</div></div>
          <div class="col-sm-4"><div class="panel-label">Posted</div><div class="panel-val">{{ r.job_posted or '-' }}</div></div>
        </div>
        {% if r.location_eligibility %}<div class="panel-label mt-3">Why you can apply from your location</div><div class="panel-val">{{ r.location_eligibility }}</div>{% endif %}
        {% if r.cv_fit %}<div class="panel-label mt-3">CV fit</div><div class="panel-val">{{ r.cv_fit }}</div>{% endif %}
      {% endif %}
      {% if r.signal %}<hr><div class="panel-label">Signal</div><div class="panel-val">{{ r.signal }}</div>{% endif %}
      {% if r.why_relevant %}<div class="panel-label mt-3">Why relevant</div><div class="panel-val">{{ r.why_relevant }}</div>{% endif %}
      <hr>
      <div class="d-flex gap-3 flex-wrap">
        {% if r.linkedin_company_url %}<a href="{{ r.linkedin_company_url }}" target="_blank"
          class="text-decoration-none"><i class="bi bi-linkedin"></i> Company page</a>{% endif %}
        {% if r.company_website %}<a href="{{ r.company_website }}" target="_blank"
          class="text-decoration-none"><i class="bi bi-globe2"></i> Website</a>{% endif %}
      </div>
    </div>

    <div class="panel">
      <div class="section-title">Contacts</div>
      {% for c in contacts %}
        {% if not loop.first %}<hr>{% endif %}
        <div class="mb-2">
          <div class="panel-label">{{ c.label }}</div>
          <span class="c-persona fw-semibold">{{ c.name }}</span>
          {% if c.tier %}<span class="c-tier ms-2">{{ c.tier }}</span>{% endif %}
          <div class="c-sub">{{ c.title }}{% if c.location %} - {{ c.location }}{% endif %}</div>
          {% if c.common_ground %}<div class="c-sub"><i class="bi bi-link"></i> Common ground: {{ c.common_ground }}</div>{% endif %}
          {% if c.linkedin %}<a href="{{ c.linkedin }}" target="_blank"
            class="text-decoration-none c-sub"><i class="bi bi-linkedin"></i> Open profile</a>{% endif %}
          {% if c.accepted_date %}<div class="c-sub">Accepted {{ c.accepted_date }}</div>{% endif %}
        </div>
        {% if c.note %}
          <div class="note-box my-3">{{ c.note }}</div>
          <div class="d-flex align-items-center gap-3">
            <span class="char-count {% if c.note_len > limits.note_char_limit %}over{% endif %}">
              {{ c.note_len }} / {{ limits.note_char_limit }} characters</span>
            {% if c.sent %}
              {% if c.note_used %}<span class="yes-pill">Sent with this note</span>
              {% else %}<span class="no-pill">Sent as plain connect (note not used)</span>{% endif %}
            {% else %}
              <button class="copy-btn" onclick="copyText({{ c.note|tojson }}, this)">
                <i class="bi bi-clipboard"></i> Copy</button>
            {% endif %}
          </div>
        {% else %}<div class="c-sub my-3">No note drafted.</div>{% endif %}
        {% for n, msg, d in ((1, c.f1_msg, c.f1_date), (2, c.f2_msg, c.f2_date)) if msg %}
          <div class="panel-label mt-3">Follow-up {{ n }} - {{ d }}</div>
          <div class="note-box mt-2">{{ msg }}</div>
          <div class="d-flex align-items-center gap-3 mt-2">
            {% if limits.followup_auto_send %}<span class="yes-pill">Sent automatically</span>
            {% else %}<span class="c-sub">Ready to send yourself</span>
            <button class="copy-btn" onclick="copyText({{ msg|tojson }}, this)">
              <i class="bi bi-clipboard"></i> Copy</button>{% endif %}
          </div>
        {% endfor %}
        {% if c.email_draft %}
          <div class="panel-label mt-3">Fallback email (not accepted after {{ limits.no_accept_email_days }} days)</div>
          <div class="note-box mt-2">{{ c.email_draft }}</div>
          <div class="d-flex align-items-center gap-3 mt-2">
            <span class="c-sub">Find their address and send it yourself, then set the result to Emailed</span>
            <button class="copy-btn" onclick="copyText({{ c.email_draft|tojson }}, this)">
              <i class="bi bi-clipboard"></i> Copy</button>
          </div>
        {% endif %}
      {% else %}
        <div class="c-sub">No persona found yet. The outreach skill picks this up on the next run.</div>
      {% endfor %}
    </div>
  </div>

  <div class="col-lg-4">
    <div class="panel">
      <div class="section-title">Update</div>
      <div class="panel-label">Outreach status</div>
      <select class="form-select form-select-sm mb-3" id="statusSel">
        {% for s in statuses %}<option {% if r.outreach_status == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
      </select>
      {% for c in contacts %}
        <div class="panel-label">{{ c.name }} - request result</div>
        <select class="form-select form-select-sm mb-2 js-field" data-field="{{ c.result_field }}">
          {% for s in results %}<option value="{{ s }}" {% if c.result == s %}selected{% endif %}>{{ s or '-' }}</option>{% endfor %}
        </select>
        <div class="panel-label">{{ c.name }} - reply</div>
        <select class="form-select form-select-sm mb-3 js-field" data-field="{{ c.reply_field }}">
          {% for s in replies %}<option {% if c.reply == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
        </select>
      {% endfor %}
      <div class="panel-label">Notes</div>
      <textarea class="form-control form-control-sm mb-3" id="notesBox" rows="3">{{ r.notes }}</textarea>
      <button class="btn btn-primary btn-sm w-100" onclick="save(this)">Save</button>
      <div class="c-sub mt-2" id="saveMsg"></div>
      {% for c in contacts if c.due or c.email_due %}
        <hr><span class="due-pill">{{ c.name }} - {% if c.due %}Follow-up {{ c.due }} due{% else %}Try email{% endif %}</span>
        <div class="c-sub mt-2">Sent {{ c.age }} days ago{% if c.due %}, no reply yet{% else %}, still not accepted{% endif %}.</div>
      {% endfor %}
    </div>
  </div>
</div>

<script>
function save(btn) {
  btn.disabled = true;
  fetch('/api/update', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(Object.assign({
      company_id: {{ r.company_id|tojson }},
      outreach_status: document.getElementById('statusSel').value,
      notes: document.getElementById('notesBox').value
    }, Object.fromEntries(Array.from(document.querySelectorAll('.js-field'))
         .map(el => [el.dataset.field, el.value]))))
  }).then(r => r.json()).then(d => {
    btn.disabled = false;
    document.getElementById('saveMsg').textContent = d.ok ? 'Saved.' : ('Error: ' + (d.error || 'unknown'));
    if (d.ok) setTimeout(() => location.reload(), 500);
  }).catch(e => { btn.disabled = false; document.getElementById('saveMsg').textContent = 'Error: ' + e; });
}
</script>
{% endblock %}
""")


# ── routes ─────────────────────────────────────────────────────────────────

def _has_persona(r):
    return bool((r.get("persona_name") or "").strip())


def _sent(r):
    return (r.get("connection_sent") or "").strip() == "Yes"


def _slots(r):
    return [s for s, _ in CONTACT_SLOTS if (r.get(pf(s, "name")) or "").strip()]


def _accepted_slots(r):
    return [s for s in _slots(r) if (r.get(pf(s, "connection_result")) or "").strip() == "Accepted"]


def _has_message(r, slot):
    return bool((r.get(pf(slot, "followup_1_message")) or "").strip())


def _replied(r, slot):
    return (r.get(pf(slot, "reply_status")) or "No reply").strip() not in ("No reply", "")


TAB_FILTERS = {
    "Needs a person":      lambda r, l: not _has_persona(r),
    "Ready to send":       lambda r, l: any((r.get(pf(s, "note")) or "").strip()
                                            and (r.get(pf(s, "connection_sent")) or "").strip() != "Yes"
                                            and not (r.get(pf(s, "connection_result")) or "").strip()
                                            for s in _slots(r)),
    "Sent":                lambda r, l: _sent(r) and (r.get("connection_result") or "") in ("Sent", "Pending", ""),
    "Accepted":            lambda r, l: bool(_accepted_slots(r)),
    "Awaiting message":    lambda r, l: any(not _has_message(r, s) for s in _accepted_slots(r)),
    "Messaged":            lambda r, l: any(_has_message(r, s) for s in _accepted_slots(r)),
    "Follow up due":       lambda r, l: any(followup_due_for(r, l, s) for s in _slots(r)),
    "Try email":           lambda r, l: any(email_due_for(r, l, s) for s in _slots(r)),
    "Replied":             lambda r, l: any(_replied(r, s) for s in _slots(r)),
    "All":                 lambda r, l: True,
}


@app.route("/")
def index():
    limits = config_limits()
    all_rows = read_rows()
    q = request.args.get("q", "").strip()
    active_tab = request.args.get("tab", "Ready to send").strip()
    if active_tab not in TAB_FILTERS:
        active_tab = "Ready to send"

    tabs = [{"name": name, "count": sum(1 for r in all_rows if pred(r, limits))}
            for name, pred in TAB_FILTERS.items()]

    rows = [r for r in all_rows if TAB_FILTERS[active_tab](r, limits)]
    if q:
        rows = [r for r in rows if row_matches(r, q)]

    for r in rows:
        r["_contacts"] = contacts(r, limits)

    buckets = {}
    for r in rows:
        buckets.setdefault((r.get("week") or "No week").strip() or "No week", []).append(r)
    weeks = [{"label": k, "rows": v}
             for k, v in sorted(buckets.items(), key=lambda kv: week_sort_key(kv[0]))]

    # Counted per contact (primary, second, peer) - each is its own request.
    sent = sum(1 for r in all_rows for s in _slots(r)
               if (r.get(pf(s, "connection_sent")) or "").strip() == "Yes")
    accepted = sum(len(_accepted_slots(r)) for r in all_rows)
    replied = sum(1 for r in all_rows for s in _slots(r) if _replied(r, s))
    used = sent_today_count(all_rows)
    notes_used = notes_sent_this_month_count(all_rows)
    stats = {
        "companies": len(all_rows),
        "sent": sent,
        "accepted": accepted,
        "accept_rate": f"{round(100 * accepted / sent)}%" if sent else "-",
        "replied": replied,
        "cap": limits["daily_cap"],
        "sent_today": used,
        "remaining": max(0, limits["daily_cap"] - used),
        "note_cap": limits["note_monthly_cap"],
        "notes_used_month": notes_used,
        "notes_remaining": max(0, limits["note_monthly_cap"] - notes_used),
    }

    cfg_rows, cfg_meta = campaign_config_summary()
    return render_template_string(INDEX_HTML, weeks=weeks, tabs=tabs, active_tab=active_tab,
                                  q=q, stats=stats, status_colors=STATUS_COLORS,
                                  cfg_rows=cfg_rows, cfg_meta=cfg_meta, request=request)


@app.route("/company/<company_id>")
def company_detail(company_id):
    limits = config_limits()
    rows = read_rows()
    r = next((x for x in rows
              if (x.get("company_id") or "").strip().lower() == company_id.strip().lower()), None)
    if not r:
        abort(404)
    return render_template_string(DETAIL_HTML, r=r, limits=limits, contacts=contacts(r, limits),
                                  statuses=STATUSES, results=RESULTS, replies=REPLIES,
                                  status_colors=STATUS_COLORS, request=request)


@app.route("/api/update", methods=["POST"])
def api_update():
    """Manual status edits from the dashboard.

    Deliberately narrow: it can only touch the tracking fields (status, notes, and each
    contact's request result and reply). The note itself
    is written by the skill through update_outreach.py, which enforces the character
    limit - so there is no path here that can save an over-length note.
    """
    data = request.get_json() or {}
    company_id = (data.get("company_id") or "").strip().lower()
    if not company_id:
        return jsonify({"error": "missing company_id"}), 400

    result_fields = {pf(s, "connection_result") for s, _ in CONTACT_SLOTS}
    reply_fields = {pf(s, "reply_status") for s, _ in CONTACT_SLOTS}
    allowed = {"outreach_status", "notes"} | result_fields | reply_fields
    updates = {k: v for k, v in data.items() if k in allowed}
    if data.get("outreach_status") and data["outreach_status"] not in STATUSES:
        return jsonify({"error": "invalid status"}), 400
    for k, v in updates.items():
        if k in result_fields and v not in RESULTS:
            return jsonify({"error": "invalid result"}), 400
        if k in reply_fields and v not in REPLIES:
            return jsonify({"error": "invalid reply status"}), 400

    rows = read_rows()
    target = next((r for r in rows
                   if (r.get("company_id") or "").strip().lower() == company_id), None)
    if not target:
        return jsonify({"error": "not found"}), 404
    for k, v in updates.items():
        # Recording an acceptance by hand stamps accepted_date, same as the script does.
        if k in result_fields and v == "Accepted" and (target.get(k) or "") != "Accepted":
            slot = next(s for s, _ in CONTACT_SLOTS if pf(s, "connection_result") == k)
            if not (target.get(pf(slot, "accepted_date")) or "").strip():
                target[pf(slot, "accepted_date")] = date.today().isoformat()
        target[k] = v
    target["last_action_date"] = date.today().isoformat()
    write_rows(rows)
    return jsonify({"ok": True})


@app.route("/api/stats")
def api_stats():
    """Machine-readable snapshot - handy for a scheduled run to check the cap."""
    limits = config_limits()
    rows = read_rows()
    used = sent_today_count(rows)
    return jsonify({"companies": len(rows), "sent_today": used, "cap": limits["daily_cap"],
                    "remaining": max(0, limits["daily_cap"] - used),
                    "followups_due": sum(1 for r in rows if followup_due(r, limits))})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    print(f"\nDashboard running at http://localhost:{port}")
    print(f"    CSV: {os.path.abspath(CSV_PATH)}\n")
    app.run(debug=False, port=port)
