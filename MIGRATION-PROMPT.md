# Migration Session Opening Prompt

> **For Gabe/James**: Copy the block below and paste it to Claude Code at the start of each session.
> Replace `[DOMAIN]` with the domain you're working on.

---

```
You are helping TattooNOW migrate legacy tattoo studio websites to GoHighLevel (GHL).

Before doing anything, read these files in order:
1. `CLAUDE.md` (this repo) — system context, API keys, tool list, pipeline rules
2. `MIGRATION-HANDOFF.md` — current pipeline state and pilot domain status
3. `workflows/site-migration-pipeline.md` — full technical SOP for each stage

Skills you should have installed (check ~/.claude/skills/):
- ghl-api — GHL V1/V2 API reference
- airtable-best-practices — rate limits, Notes metadata format, batch ops
- n8n-code-javascript — n8n Code node syntax
- n8n-workflow-patterns — webhook and HTTP request patterns

Today we are working on: [DOMAIN]

Once you've read the files:
1. Pull the current Airtable task for [DOMAIN] — what stage is it at, what's checked?
2. Tell me what automated steps you can run right now (no manual input from me)
3. Tell me exactly what I need to do in GHL UI (if anything) before you can continue

Then run the automated steps. Use --dry-run on tools before the real run.
Always update the Airtable Notes after each automated step completes.
```

---

## Quick Reference — James's Manual Steps by Stage

### GHL Setup (do all 3 together in one GHL session)
1. **Load snapshot**: GHL Agency → Sub-Accounts → [location] → Actions → Load Snapshot → "TattooNOW"
2. **Create blog author**: GHL → [location] → Sites → Blog → Authors → Add Author
   - Name = studio name shown on the migration card at brain.tattoonow.com
3. **Visual review**: Open the location, confirm it looks like a real site (snapshot loaded)

### Review
- Open test subdomain link from the card (e.g. `sleevetattoosnow.tattooconsultations.com`)
- Confirm site is branded and loads correctly

### DNS Cutover
- Log into GoDaddy (or client's registrar shown on the card)
- My Products → domain → DNS → Nameservers → Change → enter Cloudflare values from the card

---

## If Something Fails

- Note the error shown on the card or in Claude's output
- Paste the exact error to Claude — it will diagnose and fix
- Do not try to run Python scripts yourself
- Do not call any APIs directly — Claude handles all automation

---

## Repo Setup (first time only)

```bash
git clone https://github.com/TattooNOW/tattoonow-migration.git
cd tattoonow-migration
cp .env.example .env   # fill in values Gabe shares via iMessage
pip install -r requirements.txt
```

Test your setup:
```bash
python3 tools/migrate_check_domain.py --domain ghostinthetattoomachine.com --dry-run
```
