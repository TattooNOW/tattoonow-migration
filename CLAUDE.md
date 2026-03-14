# TattooNOW Migration Pipeline — Claude Code Context

> This file is for the `tattoonow-migration` repo — James's working environment.
> Full ops context lives in `tattoonow-ops/CLAUDE.md` (Gabe's repo).

## Identity

You are the migration co-pilot for **TattooNOW LLC**, owned by **Gabe Ripley** (gabe@tattoonow.com).

Your job in this repo: migrate legacy tattoo studio websites to GoHighLevel (GHL).
The assistant (James) handles manual GHL UI steps. You handle all automation.

## Skills to Load First

Before any migration work, confirm these skills are available:

| Skill | Use for |
|-------|---------|
| `ghl-api` | GHL V1/V2 API, PIT auth, blog endpoints |
| `airtable-best-practices` | Rate limits, batch ops, Notes metadata format |
| `n8n-workflow-patterns` | Webhook patterns, HTTP request nodes |
| `n8n-code-javascript` | Code node syntax for n8n |

Load them by referencing: `~/.claude/skills/` (they're already installed if Claude Code is set up correctly).

## Connected Systems

### Airtable
- **Base**: TattooNOW - Business Hub (`apptbA8Mljf70CG24`)
- **Token**: in `.env` as `AIRTABLE_TOKEN`
- **Migration tasks**: Tasks table (`tblBP4uzRGQBcBco9`) filtered by `Project = 'GHL Website Migration'`
- **Rate limit warning**: Free tier = 1,000 calls/month. Never call Airtable directly from Claude Code — use n8n webhooks as the API layer.

### n8n
- **Instance**: https://tn.reinventingai.com
- **API Key**: in `.env` as `N8N_API_KEY`
- **Migration webhook**: `GET https://tn.reinventingai.com/webhook/tn-ops-migrations` — returns all 71 migration records
- **Stage update**: `POST https://tn.reinventingai.com/webhook/tn-ops-migration-update`
- **Dashboard**: https://brain.tattoonow.com/#migrations

### GoHighLevel (GHL)
- **Agency API Key**: in `.env` as `GHL_AGENCY_API_KEY`
- **Company ID**: `Wi9zjVQgZIH2Kk2lnfrg`
- **V1 API** (location creation only): `https://rest.gohighlevel.com/v1/`
- **V2 API** (everything else): `https://services.leadconnectorhq.com` with PIT per location
- **PITs**: stored per-domain in Airtable `migrationMeta.ghlPit` (Notes field HTML comment)

### Cloudflare
- **API Token**: in `.env` as `CLOUDFLARE_API_TOKEN`
- **Account ID**: `d44a192b4520deb383a974546e135baf`
- **Used for**: Creating `{slug}.tattooconsultations.com` test subdomains + production DNS zones

## Tools (in `tools/`)

| Tool | Stage | Usage |
|------|-------|-------|
| `migrate_check_domain.py` | 2. Pre-Check | `--domain example.com` |
| `migrate_create_ghl.py` | 3. GHL Setup | `--domain example.com --name "Studio Name"` |
| `migrate_scrape_identity.py` | 3. GHL Setup | `--domain example.com` |
| `migrate_set_custom_values.py` | 3. GHL Setup | `--domain example.com --location-id LOC_ID` |
| `migrate_dns_cloudflare.py` | 3. GHL Setup + 5. DNS | `--domain example.com --test-subdomain` |
| `migrate_rss_blogs.py` | 3. GHL Setup | `--domain example.com --location-id LOC_ID --feed news --blog-id BLOG_ID` |
| `migrate_create_authors.py` | 3. GHL Setup | `--location-id LOC_ID` |
| `migrate_test_site.py` | 4. Review | `--domain example.com` |
| `migrate_match_emails.py` | Utility | `--domain example.com` |

All tools support `--dry-run`. Always run dry-run first.

## Pipeline (6 Stages)

| Stage | Who | Trigger |
|-------|-----|---------|
| 1. Queued | — | Domain added to Airtable |
| 2. Pre-Check | Claude (auto) | Claude runs migrate_check_domain.py |
| 3. GHL Setup | Claude + James | Claude creates location → James does 3 GHL UI steps → Claude runs automation block |
| 4. Review | James | James reviews test subdomain, checks card |
| 5. DNS Cutover | Claude + James | Claude creates Cloudflare zone → James changes nameservers → Claude verifies |
| 6. Live | Claude (auto) | DNS verified, live tests pass |

### Stage 3 Automation Block (runs after James's 3 manual checkboxes)
1. `migrate_scrape_identity.py` — logo + colors from old site
2. `migrate_set_custom_values.py` — set name, URL, colors, logo in GHL
3. `migrate_dns_cloudflare.py --test-subdomain` — create `{slug}.tattooconsultations.com` CNAME
4. `migrate_rss_blogs.py` — migrate blog content (news + tattoos + art feeds)
5. `migrate_test_site.py` — automated site health checks

## Pilot Domains (as of 2026-03-14)

All at **GHL Setup** — waiting on James's 3 manual steps.

| Domain | GHL Location ID | Studio Name |
|--------|----------------|-------------|
| ghostinthetattoomachine.com | `XiUPFeURoAVRM7DU62AI` | Ghost in the Tattoo Machine |
| backtattoosnow.com | `ps2Q1poeZnTGkr5aYI4F` | Back Tattoos NOW |
| tattoonowbusinessroundtable.com | `hot7lLhkD36rvrKilvCD` | TattooNOW Business Roundtable |
| coverup911.com | `W8M6JXAFznfW6t0fFspc` | Cover Up 911 |
| sleevetattoosnow.com | `sWu6C0JeGO3XgINZaTTB` | Sleeve Tattoos NOW |

## Airtable Notes Metadata Format

Migration state is stored as HTML comments in the Notes field of each task:

```
<!-- pipelineStage: GHL Setup -->
<!-- stageData: {"ghlLocationId":"XiUPFeURoAVRM7DU62AI","testSubdomain":"..."} -->
<!-- migrationMeta: {"client":"Ghost in the Tattoo Machine","pilot":true,"ghlPit":"..."} -->
```

**When updating Notes**: Always read first, patch only the comment you're changing, write back the full Notes. Never blank the whole field.

## GHL API Rules

- **V2 for everything except location creation** — use `services.leadconnectorhq.com`
- **V1 only for**: `POST /v1/locations/` (sub-account creation)
- **Auth**: V2 uses PIT (`Authorization: Bearer {PIT}`), V1 uses agency key
- **snapshotId param is silently ignored** — snapshot must be loaded manually in GHL UI
- **Blog Author POST is 401** — authors must be created in GHL UI (never via API)

## .env Keys Required

```
GHL_AGENCY_API_KEY=
GHL_COMPANY_ID=Wi9zjVQgZIH2Kk2lnfrg
GHL_SNAPSHOT_ID=kwq6O3LdhQrLdJGozmZ4
AIRTABLE_TOKEN=
N8N_API_KEY=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=d44a192b4520deb383a974546e135baf
```

Gabe provides `.env` values via iMessage. Never commit `.env` to git.

## Gotchas

- GHL V1 `snapshotId` param silently ignored — snapshot MUST be loaded manually
- GHL Blog Author `POST /blogs/authors` returns 401 — UI only
- RSS namespace `media:content` strips to `content`, `content:encoded` strips to `encoded` — no collision
- `migrate_rss_blogs.py` needs PIT stored in Airtable `migrationMeta.ghlPit` before running
- Blog site IDs (News/Tattoos/Art) stored in `migrationMeta.ghlBlogSites` — fetched once per location
- tattooconsultations.com Cloudflare zone exists — `create_test_subdomain()` in `migrate_dns_cloudflare.py` adds CNAME to it
