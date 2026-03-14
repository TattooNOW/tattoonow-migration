# TattooNOW Migration Pipeline

Welcome James. This repo has everything you need to run the TattooNOW site migration pipeline.

---

## Step 1 — Install Claude Code Skills

Download `james-claude-skills.zip` from this repo and run:

```bash
unzip james-claude-skills.zip
mkdir -p ~/.claude/skills
cp -r Users/tattoonow/.claude/skills/ghl-api ~/.claude/skills/
cp Users/tattoonow/.claude/skills/airtable-best-practices.md ~/.claude/skills/
cp -r Users/tattoonow/.claude/skills/n8n-code-javascript ~/.claude/skills/
cp -r Users/tattoonow/.claude/skills/n8n-workflow-patterns ~/.claude/skills/
```

## Step 2 — Clone the Repo

```bash
git clone https://github.com/TattooNOW/tattoonow-migration.git
cd tattoonow-migration
```

## Step 3 — Set Up .env

```bash
cp .env.example .env
# Fill in the values Gabe shares via iMessage
```

## Step 4 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

## Step 5 — Test Your Setup

```bash
python3 tools/migrate_check_domain.py --domain ghostinthetattoomachine.com --dry-run
```

---

## How to Run a Migration Session

1. Read `MIGRATION-HANDOFF.md` — pipeline state, pilot domains, what's done, what's next
2. Copy the opening prompt from `MIGRATION-PROMPT.md` into Claude Code, replace `[DOMAIN]` with the domain you're working on
3. Claude will tell you exactly what to do in GHL and what it will handle automatically

---

## Files in This Repo

| File / Folder | Purpose |
|---------------|---------|
| `README.md` | This file — start here |
| `MIGRATION-HANDOFF.md` | Current pipeline state, pilot status, manual steps |
| `MIGRATION-PROMPT.md` | Opening prompt to paste into Claude Code each session |
| `CLAUDE.md` | Full technical context (Claude reads this automatically) |
| `.env.example` | API key template — copy to `.env` and fill in |
| `requirements.txt` | Python dependencies |
| `tools/` | Migration scripts — Claude runs these, not you |
| `workflows/` | SOPs and n8n workflow JSONs |
| `james-claude-skills.zip` | Claude Code skills (install once, Step 1 above) |
