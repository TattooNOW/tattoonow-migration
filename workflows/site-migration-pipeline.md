# Site Migration Pipeline — SOP

## Objective
Migrate legacy ColdFusion/IIS websites to GoHighLevel (GHL) with Cloudflare DNS.
Pipeline uses Python tools orchestrated by n8n, tracked via Airtable Tasks.

## Prerequisites
- `.env` loaded with: `GHL_AGENCY_API_KEY`, `CLOUDFLARE_API_TOKEN`, `AIRTABLE_TOKEN`
- Python 3.11+ with `requests`, `python-dotenv`
- Airtable project "GHL Website Migration" with 1 task per domain (checklist in Notes)

## Pipeline Stages

### Stage 1: Pre-Check (Batch)
**Tool**: `tools/migrate_check_domain.py`
**Input**: `--domain` or `--domains` (comma-separated)
**Output**: JSON with HTTP status, DNS, SSL, GHL location match, CRM supertype

```bash
python3 tools/migrate_check_domain.py --domains "domain1.com,domain2.com"
```

**Flags to watch**:
- `GHL_LOCATION_EXISTS` — domain already has a GHL sub-account
- `DNS_UNRESOLVED` — expected for dead/parked domains
- `HAS_CRM_ENTRY` — domain has content in old CRM to migrate

**Airtable**: Update "Migrate: {domain}" Notes — check off step 1, append flags.

---

### Stage 2: GHL Setup (Per-Client)
**Tool**: `tools/migrate_create_ghl.py`
**Input**: `--domain`, `--name`, optional `--email`, `--phone`
**Output**: JSON with location ID and verification

```bash
# Dry run first
python3 tools/migrate_create_ghl.py --domain example.com --name "Example Studio" --dry-run

# Create for real
python3 tools/migrate_create_ghl.py --domain example.com --name "Example Studio"
```

**Edge cases**:
- If `GHL_LOCATION_EXISTS` flagged in Stage 1, tool skips unless `--force`
- Ask Gabe: skip, overwrite, or create new?

**⚠️ MANUAL STEP — Load Snapshot**: After location is created, Gabe must manually load the TattooNOW snapshot:
- GHL Agency → Sub-Accounts → find location → Actions → "Load Snapshot" → select TattooNOW template
- The V1 API `snapshotId` parameter is silently ignored by GHL — snapshot does NOT auto-apply
- This is required before the site is usable

**⚠️ MANUAL STEP — Create Blog Author**: GHL Blog Author API is read-only (POST returns 401). Must be created in UI:
- GHL UI → [Location] → Sites → Blog → Authors → Add Author
- **Name = the location name** (e.g. "Sleeve Tattoos NOW") — one author per location
- Store the name in Airtable `migrationMeta.blogAuthorName`
- Must be done before Stage 3 — the blog migration tool matches by name
- If skipped, posts will be created without an author assigned

**Airtable**: Update "Migrate: {domain}" Notes — check off step 2, append location ID.

---

### Stage 2.5: Custom Values (Per-Client)
**Tool**: `tools/migrate_set_custom_values.py`
**Input**: `--domain`, `--location-id`, optional `--pit`
**Output**: JSON with per-field set results

Sets GHL custom values from Airtable `migrationMeta` identity data + test subdomain:
- `studio__name` — client name
- `studio__url` + `admin__navigation_base` — test subdomain URL (e.g. `sleevetattoosnow.tattooconsultations.com`)
- `01_studio_color_primary/secondary/accent` — brand colors from identity scrape
- `01_studio_logo_upload` — logo URL from identity scrape

```bash
python3 tools/migrate_set_custom_values.py --domain example.com --location-id abc123 --dry-run
python3 tools/migrate_set_custom_values.py --domain example.com --location-id abc123
```

**Prerequisite**: `migrate_scrape_identity.py` must have run and stored `identityData` in Airtable `migrationMeta`.
**Test subdomain**: Create Cloudflare CNAME `{slug}.tattooconsultations.com` → `sites.leadconnectorhq.com`, store as `migrationMeta.testSubdomain`.

**Airtable**: Update Notes — check off step 2.5.

---

### Stage 3: Content Migration (Per-Client)
**Tool**: `tools/migrate_rss_blogs.py`
**Input**: `--domain`, `--location-id`, optional `--pit`, `--dry-run`, `--skip-trigger`, `--feed`, `--blog-id`, `--limit`, `--tags`
**Output**: JSON with posts found/created counts, categories matched, authors found

**Requires**: GHL Private Integration Token (PIT) per location. Gabe creates the PIT in GHL after the location is set up, then enters it via the dashboard task record (stored in Airtable `migrationMeta` Notes comment as `ghlPit`).

```bash
# Dry run — see what RSS content exists (no PIT needed)
python3 tools/migrate_rss_blogs.py --domain guyaitchison.com --dry-run

# Migrate a specific feed (news/tattoos/art)
python3 tools/migrate_rss_blogs.py --domain example.com --location-id abc123 --feed news --blog-id BLOG_ID

# Use test content from another domain (pilot testing)
python3 tools/migrate_rss_blogs.py --domain sleevetattoosnow.com --location-id abc123 \
  --test-content guyaitchison.com --skip-trigger --feed tattoos --blog-id BLOG_ID
```

**How it works**:
1. Looks up CRM supertype ID from domain (or `--test-content` override)
2. Hits `generaterssmigrate&super={id}&TattooNOWAutoGeneration=1` to trigger RSS
3. Fetches and parses RSS feed — extracts title, content, imageUrl, description, keywords, author
4. Resolves PIT from `--pit` flag or Airtable `migrationMeta` → `ghlPit` field
5. Fetches location categories + authors from GHL V2 API (once, before post loop)
6. For each post: matches keywords → category IDs; matches RSS author name → GHL author ID; builds tags (artist slug + geo)
7. Creates posts via `POST /blogs/posts` with imageUrl, description, categories, author, tags, urlSlug
8. If no PIT found → exits with `"action": "pending_pit"` (not a failure)
9. If `authors_found == 0` → logs WARNING with `blogAuthorName` from migrationMeta

**Tags rule**: `tags` = artist name slug + US state geo extracted from description. NOT keyword-derived.
**Categories rule**: `categories` = style taxonomy (Color, Blackwork, etc.) matched from RSS `<keywords>`. NOT subjects.

**Blog site IDs**: Each location has 3 blog sites (News, Tattoos, Art). IDs stored in `migrationMeta.ghlBlogSites`. Run each feed separately with `--feed` + `--blog-id`.

**No CRM entry?** Tool skips gracefully with `"action": "skipped"`. Mark task N/A.

**Airtable**: Update "Migrate: {domain}" Notes — check off step 3 (or mark N/A).

---

### Stage 4: Site Testing (Per-Client)
**Tool**: `tools/migrate_test_site.py`
**Input**: `--domain`, optional `--location-id`, `--url`
**Output**: JSON test report with pass/fail per check

```bash
python3 tools/migrate_test_site.py --domain example.com --location-id abc123
```

**Tests run**:
- Homepage returns 200 with HTML content (>500 bytes)
- SSL certificate valid
- Key pages exist (/, /about, /contact, /services, /blog)
- No broken images on homepage

**Airtable**: Update "Migrate: {domain}" Notes — check off step 4, append test summary.

---

### APPROVAL GATE (Manual — Gabe)
Gabe reviews:
- Test report JSON
- GHL site in browser (visual check)
- Any flags from earlier stages

**Decision**: Approve → Stage 5 | Reject → back to Stage 2/3 with notes.

**Airtable**: Update "Migrate: {domain}" Notes — check off step 5 (or set task Status → Blocked if rejected).

---

### Stage 5: DNS Setup + Cutover (Per-Client)
**Tool**: `tools/migrate_dns_cloudflare.py`
**Input**: `--domain`, optional `--dry-run`, `--verify-only`
**Output**: JSON with zone ID, nameservers, DNS records, GoDaddy instructions

```bash
# Dry run
python3 tools/migrate_dns_cloudflare.py --domain example.com --dry-run

# Create zone + records
python3 tools/migrate_dns_cloudflare.py --domain example.com

# Verify after nameserver change (24h later)
python3 tools/migrate_dns_cloudflare.py --domain example.com --verify-only
```

**What it does**:
1. Creates Cloudflare zone (or uses existing)
2. Adds CNAME records: `domain` + `www.domain` → `sites.leadconnectorhq.com`
3. Generates GoDaddy nameserver change instructions (printed in output)

**MANUAL STEP**: Nameserver change at GoDaddy. This is intentionally manual — same process clients will follow. Gabe tests it first on pilot domains.

**Airtable**: Update "Migrate: {domain}" Notes — check off step 6. Set task Status → Blocked (waiting for manual NS change at step 7).

---

### Stage 6: Post-Migration (Ongoing)
After nameserver change + 24h propagation:
1. Run `migrate_dns_cloudflare.py --verify-only` to confirm propagation
2. Run `migrate_test_site.py` again to confirm live site health
3. Monitor daily for 7 days
4. Gabe confirms final signoff

**Airtable**: Update "Migrate: {domain}" Notes — check off steps 7+8. Set task Status → Done after 7-day soak.

---

## Quick Reference

| Stage | Tool | Automated? | Bottleneck |
|-------|------|-----------|------------|
| 1. Pre-Check | migrate_check_domain.py | ✅ Yes (batch) | None |
| 2. GHL Setup | migrate_create_ghl.py | ✅ Yes (per-client) | Existing GHL location? |
| 2. ⚠️ Load Snapshot | GHL UI (manual) | ❌ NO | Gabe |
| 2. ⚠️ Create Blog Author | GHL UI (manual) | ❌ NO — API read-only | Gabe — name = location name |
| 2.5 Custom Values | migrate_set_custom_values.py | ✅ Yes (per-client) | identityData must exist |
| 3. Content (News) | migrate_rss_blogs.py --feed news | ✅ Yes (per-client) | No CRM entry → N/A |
| 3. Content (Tattoos) | migrate_rss_blogs.py --feed tattoos | ✅ Yes (per-client) | No CRM entry → N/A |
| 3. Content (Art) | migrate_rss_blogs.py --feed art | ✅ Yes (per-client) | No CRM entry → N/A |
| 4. Testing | migrate_test_site.py | ✅ Yes (per-client) | None |
| 4. ⚠️ Visual QA | Browser (manual) | ❌ NO | Gabe |
| 5a. DNS Setup | migrate_dns_cloudflare.py | ✅ Yes (per-client) | None |
| 5b. DNS Cutover | Manual (GoDaddy) | ❌ NO | Gabe/client |
| 6. Monitor | migrate_dns_cloudflare.py --verify | ✅ Yes | 7-day soak |

## 5 Pilot Domains

| Domain | CRM Supertype | Notes |
|--------|--------------|-------|
| ghostinthetattoomachine.com | None | No CRM content |
| backtattoosnow.com | None | No CRM content |
| tattoonowbusinessroundtable.com | 4318 | Has CRM entry |
| coverup911.com | None | No CRM content |
| sleevetattoosnow.com | None | No CRM content |

## Error Recovery

- **GHL API 429 (rate limit)**: Wait 60s, retry. Max 3 retries.
- **Cloudflare zone exists**: Tool reuses existing zone, adds records.
- **RSS feed empty**: Tool marks as N/A, not a failure.
- **GHL blog API not available**: Tool logs for manual import.
- **DNS not propagated after 48h**: Check nameservers were actually changed at registrar.
