# TattooNOW Migration Pipeline — Handoff Doc

> **Last Updated**: 2026-03-14
> **Status**: 5 pilots in progress — all at GHL Setup stage (waiting on manual GHL steps)

## Claude Code Setup — Skills Required

James's Claude Code needs these skills installed in `~/.claude/skills/`. Gabe copies them from his `~/.claude/skills/` folder:

| Skill file | Purpose |
|-----------|---------|
| `ghl-api.md` | GHL V1/V2 API, PIT auth, blog endpoints — prevents wrong API version mistakes |
| `airtable-best-practices.md` | Rate limits, Notes metadata format, batch ops — prevents quota burnout |
| `n8n-code-javascript.md` | n8n Code node syntax for any workflow modifications |
| `n8n-workflow-patterns.md` | Webhook and HTTP patterns for n8n |

Copy command (run once on James's machine after Gabe shares the files):
```bash
# Gabe shares these 4 files — copy to:
mkdir -p ~/.claude/skills
cp ghl-api.md airtable-best-practices.md n8n-code-javascript.md n8n-workflow-patterns.md ~/.claude/skills/
```

---

## What This Project Is

TattooNOW is migrating ~66 legacy ColdFusion/IIS studio websites to GoHighLevel (GHL). Pipeline is automated via Python tools in `tools/` and n8n webhooks, tracked in Airtable, visible at [brain.tattoonow.com → Migrations tab](https://brain.tattoonow.com/#migrations).

**Your job as assistant**: Do the manual steps shown on each migration card. That's it. Everything else is automated.

---

## The 6-Stage Pipeline

| Stage | Who | What Happens |
|-------|-----|-------------|
| **1 — Queued** | Auto | Domain in queue, not started |
| **2 — Pre-Check** | Auto | Claude runs domain health, DNS, SSL, CRM check |
| **3 — GHL Setup** | **You + Auto** | Claude creates GHL location → You do 3 manual steps → Claude runs automated block |
| **4 — Review** | **You** | You review test subdomain, check the box |
| **5 — DNS Cutover** | **You + Auto** | Claude creates Cloudflare zone → You change nameservers at GoDaddy → Claude verifies |
| **6 — Live** | Auto | DNS verified, live site tests pass |

### Stage 3 — GHL Setup Manual Steps (you do all 3 in one GHL session)

1. **Load TattooNOW snapshot**: GHL Agency → Sub-Accounts → find location → Actions → Load Snapshot → select "TattooNOW"
2. **Create blog author**: GHL → [Location] → Sites → Blog → Authors → Add Author → name = **studio name shown on the card**
3. **Visual review**: Open the location in GHL, confirm the snapshot loaded — site looks like a real tattoo studio page

After you check all 3 boxes on the card → automated block runs:
- Identity scrape (logo, colors)
- Set GHL custom values (name, URL, colors, logo)
- Create `{slug}.tattooconsultations.com` test subdomain in Cloudflare
- Blog content migration (3 feeds: news/tattoos/art)
- Automated site tests

### Stage 4 — Review Manual Step

- Open the test subdomain link shown on the card (e.g. `sleevetattoosnow.tattooconsultations.com`)
- Check that it looks like the studio's branded site
- Check the box on the card → advances to DNS

### Stage 5 — DNS Cutover Manual Step

The card shows Cloudflare nameserver values. Go to GoDaddy (or client's registrar):
- Log in → My Products → find domain → DNS → Nameservers → Change → enter Cloudflare values
- Check the box on the card → Claude auto-verifies propagation → advances to Live when done

---

## Pilot Domain Status (as of 2026-03-14)

All 5 pilots are at **GHL Setup** — GHL locations created, waiting on your manual steps.

| Domain | GHL Location ID | Studio Name | CRM Content? |
|--------|----------------|-------------|-------------|
| ghostinthetattoomachine.com | `XiUPFeURoAVRM7DU62AI` | Ghost in the Tattoo Machine | No |
| backtattoosnow.com | `ps2Q1poeZnTGkr5aYI4F` | Back Tattoos NOW | No |
| tattoonowbusinessroundtable.com | `hot7lLhkD36rvrKilvCD` | TattooNOW Business Roundtable | Yes |
| coverup911.com | `W8M6JXAFznfW6t0fFspc` | Cover Up 911 | No |
| sleevetattoosnow.com | `sWu6C0JeGO3XgINZaTTB` | Sleeve Tattoos NOW | No (uses Guy Aitchison test content) |

---

## Key Inventory (All ✅ Ready)

| Key | Status | Where It Lives |
|-----|--------|---------------|
| `GHL_AGENCY_API_KEY` | ✅ In .env | GHL Agency → Settings → API Keys |
| `AIRTABLE_TOKEN` | ✅ In .env | Airtable Account → API |
| `CLOUDFLARE_API_TOKEN` | ✅ In .env | Verified active 2026-03-14 |
| `N8N_API_KEY` | ✅ In .env | n8n → Settings → API Keys |
| Per-domain GHL PITs | ✅ In Airtable | Stored per task in `migrationMeta.ghlPit` |

**Getting .env**: Gabe will share via iMessage. Never commit to git.

---

## Where Things Live

- **Dashboard** (your main view): brain.tattoonow.com → Migrations tab
- **Repo**: github.com/TattooNOW/tattoonow-ops (main branch)
- **Airtable**: TattooNOW Business Hub → Tasks table (1 row per domain)
- **Tools**: `tools/migrate_*.py` — Claude runs these, not you
- **SOP**: `workflows/site-migration-pipeline.md` — full technical pipeline

---

## How a Session Works

1. Open [brain.tattoonow.com/#migrations](https://brain.tattoonow.com/#migrations)
2. Find a domain in **GHL Setup** stage
3. Click the card → read the manual step checkboxes
4. Do the steps in GHL (or GoDaddy for DNS)
5. Check the boxes as you complete each step
6. When all boxes checked → card auto-advances, automation runs
7. Move to next card

**Claude handles**: everything that's automated. You don't run Python scripts, you don't trigger n8n workflows, you just check boxes.

**If something fails**: The card will show an error state. Check in with Gabe — don't try to fix automation issues yourself.

---

## GitHub Access

Gabe will invite you at: github.com/TattooNOW/tattoonow-ops → Settings → Collaborators → Add people → `jameswilliamwisdom`

You can pull the repo to see files, but **don't push to main directly** — changes go via PR.

---

## Known Gotchas

- **GHL Blog Author API is read-only** — authors must be created in GHL UI (that's why it's a manual step)
- **GHL snapshot doesn't auto-apply via API** — must be loaded manually in GHL Agency → Sub-Accounts → Load Snapshot
- **DNS propagation takes up to 48h** — Stage 5 → 6 transition will wait for this
- **tattooconsultations.com test subdomains** — created automatically once you complete GHL Setup manual steps

---

## Learnings

- 2026-03-14: GHL V1 `snapshotId` param is silently ignored by the API — snapshot MUST be loaded manually
- 2026-03-14: GHL Blog Author `POST /blogs/authors` returns 401 — creation is UI-only
- 2026-03-14: Airtable free tier has monthly API call limit — migrations data may show amber "cached" banner. This resets automatically each month.
