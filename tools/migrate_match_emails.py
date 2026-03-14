#!/usr/bin/env python3
"""
Email Matching Tool: Look up contact emails from CRM and GHL for migration domains.

Checks two sources:
1. TattooNOW CRM — generalinfo endpoint extracts email from supertype profile
2. GHL V1 API — searches locations by domain name for contact info

Outputs CSV lines (client, email) suitable for dashboard Bulk Email Import.

Usage:
  python3 tools/migrate_match_emails.py                    # all domains
  python3 tools/migrate_match_emails.py --domain cattattoo.com  # single domain
  python3 tools/migrate_match_emails.py --source crm       # CRM only
  python3 tools/migrate_match_emails.py --source ghl       # GHL only
  python3 tools/migrate_match_emails.py --json              # JSON output
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

GHL_API_KEY = os.getenv('GHL_AGENCY_API_KEY', '')
GHL_COMPANY_ID = 'Wi9zjVQgZIH2Kk2lnfrg'
CRM_BASE = 'https://www.tattoonow.com/members/index.cfm'

# Full domain list from dashboard MIGRATIONS array
MIGRATIONS = [
    {"client": "Daddy Jacks Tattoos", "domain": "daddyjackstattoos.com"},
    {"client": "Jason Wheelwright Tattoos", "domain": "jwheelwrighttattoos.com"},
    {"client": "Christian Perez", "domain": "christianperezart.com"},
    {"client": "Unify Tattoo Company", "domain": "unifytattoofl.com"},
    {"client": "Emerald Isle Tattoo Sessions", "domain": "emeraldisletattoosession.com"},
    {"client": "Kevin Bledsoe", "domain": "kevinbledsoe.com"},
    {"client": "Jolly Octopus", "domain": "jollyoctopus.co.nz"},
    {"client": "Art Immortal Tattoo", "domain": "artimmortaltattoo.com"},
    {"client": "American Tattooer", "domain": "americantattooer.com"},
    {"client": "Juicy Tattoo", "domain": "juicytattoo.com"},
    {"client": "Don McDonald (Bodyworks)", "domain": "bodyworks-tattoo.com"},
    {"client": "Venetian Tattoo Gathering", "domain": "venetiantattooogathering.com"},
    {"client": "Rafael Marte Tattoos", "domain": "rafaeltattoos.com"},
    {"client": "Rudy Lopez (Mizu)", "domain": "rudylopeztattoos.com"},
    {"client": "Drew Siciliano", "domain": "artofdrewtattoo.com"},
    {"client": "Reinventing The Tattoo", "domain": "reinventingthetattoo.com"},
    {"client": "Sorin Gabor (Sugar City)", "domain": "soringabor.com"},
    {"client": "Patrick Sweeney Tattoos", "domain": "patricksweeneytattoos.com"},
    {"client": "Skin Gallery Tattoo", "domain": "skingallerytattoo.com"},
    {"client": "TattooNOW", "domain": "tattoonow.com"},
    {"client": "Steve Phipps", "domain": "phippstattoo.com"},
    {"client": "Skin of a Different Color", "domain": "skinofadifferentcolor.com"},
    {"client": "Guy Aitchison", "domain": "guyaitchison.com"},
    {"client": "Michele Wortman", "domain": "michelewortman.com"},
    {"client": "Larry Brogan (Tattoo City)", "domain": "larrybrogan.com"},
    {"client": "Boston Rogoz Tattoo", "domain": "bostonrogoztattoos.com"},
    {"client": "Haley Adams Tattoo", "domain": "haleyadamstattoos.com"},
    {"client": "Rember Tattoos", "domain": "rembertattoos.com"},
    {"client": "Katelyn Crane", "domain": "katelyncrane.com"},
    {"client": "Deadgar Tattoos", "domain": "deadgartattoos.com"},
    {"client": "Justin Mariani (Human Canvas)", "domain": "justinmarianitattoos.com"},
    {"client": "Mully (Independent Tattoo)", "domain": "mullytattoo.com"},
    {"client": "Painted Temple", "domain": "paintedtemple.com"},
    {"client": "Art of Muecke", "domain": "muecketattoos.com"},
    {"client": "Worldwide Tattoo Conference", "domain": "worldwidetattooconference.com"},
    {"client": "Tattoos by George", "domain": "tattoosbygeorge.com"},
    {"client": "Ryan El Dugi Lewis", "domain": "el-dugi-art.com"},
    {"client": "Adam Lauricella (Graceland)", "domain": "adamlauricella.com"},
    {"client": "Paradise Artist Retreat", "domain": "paradiseartistretreat.com"},
    {"client": "Tattoo Inspiration", "domain": "tattooinspiration.com"},
    {"client": "Gabe Ripley", "domain": "gaberipley.com"},
    {"client": "Tattoo-Machines NOW", "domain": "tattoomachinesnow.com"},
    {"client": "Bob Tyrrell", "domain": "bobtyrrell.com"},
    {"client": "Cecil Porter Studios", "domain": "cecilporterstudios.com"},
    {"client": "Ghostprint Gallery Tattoo", "domain": "ghostprinttattoo.com"},
    {"client": "Paradise Tattoo Gathering", "domain": "paradisetattoogathering.com"},
    {"client": "Phil Robertson (Neon Dream)", "domain": "philrobertsontattoos.com"},
    {"client": "Identity Tattoo", "domain": "identitytattoo.com"},
    {"client": "New American Tattoo Co", "domain": "tattoomoney.com"},
    {"client": "Mario Rosena (Art Junkies)", "domain": "mariorosena.com"},
    {"client": "Cat Tattoo", "domain": "cattattoo.com"},
    {"client": "10 Thousand Foxes Tattoo", "domain": "10kfoxesqueenstattoo.com"},
    {"client": "Steve Morris", "domain": "stevemorristattoo.com"},
    {"client": "Forbidden Images Tattoo", "domain": "forbiddenimages.com"},
    {"client": "Jeff Johnson Tattoo", "domain": "jjtattoos.com"},
    {"client": "Canman (Visions Tattoo)", "domain": "canmantattoos.com"},
    {"client": "Mike DeVries", "domain": "mdtattoos.com"},
    {"client": "Hyperspace Studios", "domain": "hyperspacestudios.com"},
    {"client": "Vintage Tattoo Flash", "domain": "vintagetattooflash.com"},
    {"client": "Gabriel Cece", "domain": "gabrielcecetattoos.com"},
    {"client": "BadTattoos.com", "domain": "badtattoos.com"},
    {"client": "Darkside Tattoo", "domain": "darksidetattoo.com"},
]

# Import the supertype map from migrate_check_domain.py
sys.path.insert(0, os.path.dirname(__file__))
try:
    from migrate_check_domain import SUPERTYPE_MAP
except ImportError:
    SUPERTYPE_MAP = {}


def lookup_crm_email(domain: str) -> str | None:
    """Look up contact email from CRM supertype profile."""
    entry = SUPERTYPE_MAP.get(domain.lower())
    if not entry:
        return None

    supertype_id = entry['id']
    url = f'{CRM_BASE}?task=editsuper&super={supertype_id}&TattooNOWAutoGeneration=1'

    try:
        resp = requests.get(url, timeout=10,
                            headers={'User-Agent': 'TattooNOW Migration Bot'})
        if resp.status_code != 200:
            return None

        # Extract email from the CRM page — look for email input fields or mailto links
        html = resp.text

        # Pattern 1: input field with email value
        email_input = re.search(
            r'name=["\'](?:email|contact_?email)["\'].*?value=["\']([^"\']+@[^"\']+)["\']',
            html, re.IGNORECASE | re.DOTALL
        )
        if email_input:
            return email_input.group(1).strip()

        # Pattern 2: mailto link
        mailto = re.search(r'mailto:([^\s"\'<>]+@[^\s"\'<>]+)', html)
        if mailto:
            return mailto.group(1).strip()

        # Pattern 3: plain email in text near "email" label
        email_near_label = re.search(
            r'(?:email|e-mail|contact)\s*[:=]\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            html, re.IGNORECASE
        )
        if email_near_label:
            return email_near_label.group(1).strip()

        # Pattern 4: any email address in the page (less reliable)
        all_emails = re.findall(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            html
        )
        # Filter out system emails
        filtered = [e for e in all_emails if not any(
            skip in e.lower() for skip in
            ['tattoonow.com', 'noreply', 'no-reply', 'postmaster', 'webmaster',
             'admin@', 'support@', 'example.com']
        )]
        if filtered:
            return filtered[0].strip()

    except requests.RequestException:
        pass

    return None


def lookup_ghl_email(domain: str) -> dict | None:
    """Look up contact info from GHL locations by domain."""
    if not GHL_API_KEY:
        return None

    try:
        # Search GHL locations for this domain
        resp = requests.get(
            'https://rest.gohighlevel.com/v1/locations/',
            params={'companyId': GHL_COMPANY_ID, 'limit': 100},
            headers={'Authorization': f'Bearer {GHL_API_KEY}'},
            timeout=10
        )
        if resp.status_code != 200:
            return None

        locations = resp.json().get('locations', [])
        domain_lower = domain.lower()

        for loc in locations:
            loc_domain = (loc.get('domain') or '').lower()
            loc_name = (loc.get('name') or '').lower()

            if domain_lower in loc_domain or domain_lower.split('.')[0] in loc_name:
                result = {
                    'locationId': loc.get('id'),
                    'name': loc.get('name'),
                    'email': loc.get('email'),
                    'phone': loc.get('phone'),
                }
                if result['email']:
                    return result

    except requests.RequestException:
        pass

    return None


def main():
    parser = argparse.ArgumentParser(description='Match migration domains to contact emails')
    parser.add_argument('--domain', help='Single domain to look up')
    parser.add_argument('--source', choices=['crm', 'ghl', 'all'], default='all',
                        help='Which source to check (default: all)')
    parser.add_argument('--json', action='store_true', help='Output as JSON instead of CSV')
    args = parser.parse_args()

    domains = MIGRATIONS
    if args.domain:
        domains = [m for m in MIGRATIONS if m['domain'] == args.domain.lower()]
        if not domains:
            domains = [{'client': args.domain, 'domain': args.domain.lower()}]

    results = []
    csv_lines = []

    for m in domains:
        domain = m['domain']
        client = m['client']
        email = None
        source = None
        extra = {}

        # Check CRM first (more reliable for TN clients)
        if args.source in ('crm', 'all'):
            crm_email = lookup_crm_email(domain)
            if crm_email:
                email = crm_email
                source = 'crm'

        # Check GHL if no CRM email found
        if not email and args.source in ('ghl', 'all'):
            ghl_result = lookup_ghl_email(domain)
            if ghl_result and ghl_result.get('email'):
                email = ghl_result['email']
                source = 'ghl'
                extra = {
                    'locationId': ghl_result.get('locationId'),
                    'ghlName': ghl_result.get('name'),
                    'phone': ghl_result.get('phone'),
                }

        result = {
            'client': client,
            'domain': domain,
            'email': email,
            'source': source,
            'matched': email is not None,
            **extra
        }
        results.append(result)

        if email:
            csv_lines.append(f'{client}, {email}')

    if args.json:
        output = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'total': len(results),
            'matched': len([r for r in results if r['matched']]),
            'unmatched': len([r for r in results if not r['matched']]),
            'results': results,
        }
        print(json.dumps(output, indent=2))
    else:
        # CSV output — ready for dashboard bulk import
        if csv_lines:
            print(f'# Email matches found: {len(csv_lines)}/{len(results)}')
            print(f'# Source: {args.source} | Generated: {datetime.now(timezone.utc).isoformat()}')
            print(f'# Paste below into dashboard Bulk Email Import:')
            print()
            for line in csv_lines:
                print(line)
        else:
            print(f'# No email matches found for {len(results)} domains')

        # Also print unmatched to stderr for visibility
        unmatched = [r for r in results if not r['matched']]
        if unmatched:
            print(f'\n# Unmatched ({len(unmatched)}):',  file=sys.stderr)
            for r in unmatched:
                print(f'#   {r["client"]} ({r["domain"]})', file=sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()
