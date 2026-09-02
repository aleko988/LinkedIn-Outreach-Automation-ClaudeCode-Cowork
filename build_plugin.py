#!/usr/bin/env python3
"""
build_plugin.py - (re)build the Cowork plugin as THIN LAUNCHERS.

Design (read this before "fixing" the plugin):
------------------------------------------------
There is ONE source of truth for the skills: .claude/skills/<name>/SKILL.md in the
project. The Cowork plugin does NOT copy that content. Each plugin skill is a thin
launcher that (1) discovers the shared project folder on the user's machine and
(2) reads and follows the project's live SKILL.md.

Why thin and not full content:
- The live SKILL.md is always current, so the plugin never goes stale and NEVER needs
  rebuilding when skills or knobs change. Knob changes live in outreach_config.json,
  which the project's SKILL.md loads live at runtime.
- Bundling a full copy of the skill text would (a) re-introduce drift and (b) break
  path discovery (the project's scripts auto-locate the project root from their own
  location; a copy inside the plugin install dir would not find connections.csv).

You normally never need to run this. Only re-run it if you change the LAUNCHER shape
itself (Step 0/Step 1 wording, plugin.json, or the descriptions):

    python build_plugin.py
"""

import json
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "dist", "linkedin-connect-outreach.plugin")

SKILLS = {
    "linkedin-company-finder": {
        "title": "LinkedIn Company Finder",
        "description": "Find companies on LinkedIn matching your configured ideal-customer profile and save them to the local tracker. Use when asked to find companies, build a prospect list, find leads, look for new accounts, or when a scheduled prospecting run fires.",
        "script": "append_companies.py",
        "script_step": "the CSV-save step",
    },
    "linkedin-connect-outreach": {
        "title": "LinkedIn Connect Outreach",
        "description": "Find the right person at each tracked company, write a connection note of 200 characters or less, send the request under a daily cap, and record the result. Also handles follow-ups. Use when asked to find people, send connection requests, add people on LinkedIn, or write outreach notes.",
        "script": "update_outreach.py",
        "script_step": "the note-validation, send-cap and CSV-update steps",
    },
}

PLUGIN_JSON = {
    "name": "linkedin-connect-outreach",
    "version": "0.1.0",
    "description": "Thin-launcher plugin: adds the LinkedIn company finder + connect outreach skills to Cowork. Delegates to the project's live skills and outreach_config.json, so targeting changes need no reinstall or rebuild.",
    "keywords": ["linkedin", "outreach", "prospecting", "crm", "connections"],
}

PLUGIN_README = """# LinkedIn Connect Outreach - Cowork plugin (thin launchers)

This plugin adds the **company finder** and **connect outreach** skills to the Cowork panel.

**It deliberately contains no copy of the skill logic.** Each skill here is a thin
launcher that finds your shared project folder (`Projects/linkedin-connect-outreach`)
and runs the project's live `SKILL.md`. That means:

- Targeting (companies, personas, note tone, daily cap) is driven by
  `outreach_config.json` in the project, loaded live on every run. **Changing knobs
  never requires reinstalling or rebuilding this plugin.**
- Skill edits in the project are picked up automatically. **This plugin never goes
  stale and should not be rebuilt into a full-content copy** - doing so breaks the
  project-folder discovery these launchers rely on.

The safety limits (200-character notes, a daily send cap, pacing between sends) are
enforced by the project's helper script, not by this plugin.
"""

DO_NOT_REBUILD = """> **THIS IS AN INTENTIONAL THIN LAUNCHER - DO NOT "UPDATE", "REBUILD", OR REPLACE IT WITH FULL SKILL CONTENT.**
> It is deliberately short. The real, full skill lives in the project at
> `.claude/skills/{name}/SKILL.md` and is read **live at runtime** in Step 1 below, so
> it is ALWAYS current - including every knob change and skill edit. It is **not** stale
> or incomplete. Copying the full skill text in here would BREAK project-folder discovery
> (the run would lose track of the shared `connections.csv` and `outreach_config.json`).
> Leave it thin."""


def launcher(name: str, meta: dict) -> str:
    return f"""---
name: {name}
description: {meta['description']}
---

# {meta['title']} (Cowork launcher)

{DO_NOT_REBUILD.format(name=name)}

> **FORMATTING RULE - NO EM DASHES:** Never use em dashes anywhere in any output. Use a regular hyphen (-) instead.

This skill is a thin launcher. It discovers the project root on this machine, then reads and follows the authoritative skill instructions from the project itself. All targeting (companies, personas, note tone, send cap) lives in the project's `outreach_config.json` and is loaded live - **changing knobs never requires touching or rebuilding this plugin.**

---

## Step 0 - Discover the project root

Read the Cowork desktop config to find the shared files folder:

**macOS:**
```bash
python3 -c "import json,os; p=os.path.expanduser('~/Library/Application Support/Claude/claude_desktop_config.json'); print(json.load(open(p)).get('coworkUserFilesPath',''))"
```
**Windows** (use `python`): same, but read `os.path.join(os.environ['APPDATA'],'Claude','claude_desktop_config.json')`.

Set `PROJECT_ROOT = {{coworkUserFilesPath}}/Projects/linkedin-connect-outreach`. Verify it exists:
```bash
python -c "import os; print('FOUND' if os.path.exists(os.path.join(r'{{PROJECT_ROOT}}','schema.py')) else 'MISSING')"
```
If the config is missing or the project is MISSING, stop and tell the user to open or clone
the project into their Cowork Projects folder.

---

## Step 1 - Load and follow the authoritative skill

Read the full instructions from:
```
{{PROJECT_ROOT}}/.claude/skills/{name}/SKILL.md
```

Follow every step in that file exactly. Use `{{PROJECT_ROOT}}` wherever the instructions
reference `{{project_root}}`. The helper-script path for {meta['script_step']} is:
```
{{PROJECT_ROOT}}/.claude/skills/{name}/scripts/{meta['script']}
```
That script loads `{{PROJECT_ROOT}}/outreach_config.json` (the current knobs) at the start
of the run, so whatever the user last set is what gets used - no rebuild needed. It also
enforces the note character limit and the daily send cap, and **refuses** any write that
would break either.
"""


def build():
    if os.path.exists(OUT):
        os.remove(OUT)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(".claude-plugin/plugin.json", json.dumps(PLUGIN_JSON, indent=2) + "\n")
        z.writestr("README.md", PLUGIN_README)
        for name, meta in SKILLS.items():
            z.writestr(f"skills/{name}/SKILL.md", launcher(name, meta))
    print(f"Built {OUT} (thin launchers, no skill-content copy, no scripts bundled)")


if __name__ == "__main__":
    build()
