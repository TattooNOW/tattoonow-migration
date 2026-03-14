#!/usr/bin/env python3
"""
Stage 2: GHL Sub-Account Setup
Creates a GoHighLevel location from snapshot for a domain.
Returns JSON to stdout for n8n consumption.

Usage:
  python3 tools/migrate_create_ghl.py --domain darksidetattoo.com --name "Darkside Tattoo"
  python3 tools/migrate_create_ghl.py --domain darksidetattoo.com --name "Darkside Tattoo" --dry-run
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

GHL_API_KEY = os.getenv('GHL_AGENCY_API_KEY', '')
GHL_API_BASE = os.getenv('GHL_API_BASE_URL', 'https://rest.gohighlevel.com/v1')
GHL_COMPANY_ID = os.getenv('GHL_COMPANY_ID', 'Wi9zjVQgZIH2Kk2lnfrg')
GHL_SNAPSHOT_ID = os.getenv('GHL_SNAPSHOT_ID', 'kwq6O3LdhQrLdJGozmZ4')

HEADERS = {'Authorization': f'Bearer {GHL_API_KEY}'}


def find_existing_location(domain):
    """Check if a GHL location already exists for this domain."""
    try:
        resp = requests.get(
            f'{GHL_API_BASE}/locations/',
            params={'companyId': GHL_COMPANY_ID, 'limit': 100},
            headers=HEADERS,
            timeout=15
        )
        if resp.status_code == 200:
            domain_lower = domain.lower().replace('www.', '')
            for loc in resp.json().get('locations', []):
                for field in ['domain', 'website']:
                    val = (loc.get(field, '') or '').lower()
                    val = val.replace('http://', '').replace('https://', '').replace('www.', '').rstrip('/')
                    if val and len(val) > 3 and (domain_lower == val or domain_lower == val.split('/')[0]):
                        return loc
    except Exception:
        pass
    return None


def create_location(domain, name, email=None, phone=None):
    """Create a new GHL sub-account/location with snapshot."""
    payload = {
        'companyId': GHL_COMPANY_ID,
        'name': name,
        'businessName': name,
        'domain': domain,
        'address': '',
        'city': '',
        'state': '',
        'country': 'US',
        'postalCode': '',
        'website': f'https://{domain}',
        'timezone': 'America/New_York',
        'snapshotId': GHL_SNAPSHOT_ID,
    }
    if email:
        payload['email'] = email
    if phone:
        payload['phone'] = phone

    resp = requests.post(
        f'{GHL_API_BASE}/locations/',
        json=payload,
        headers=HEADERS,
        timeout=30
    )
    return resp.status_code, resp.json()


def verify_location(location_id, max_retries=3):
    """Verify location exists and snapshot was applied."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(
                f'{GHL_API_BASE}/locations/{location_id}',
                headers=HEADERS,
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                loc = data.get('location', data)
                return {
                    'verified': True,
                    'id': loc.get('id'),
                    'name': loc.get('name'),
                    'domain': loc.get('domain'),
                    'website': loc.get('website'),
                }
        except Exception:
            pass
        if attempt < max_retries - 1:
            time.sleep(2)
    return {'verified': False}


def main():
    parser = argparse.ArgumentParser(description='Stage 2: GHL Sub-Account Setup')
    parser.add_argument('--domain', required=True, help='Domain name')
    parser.add_argument('--name', required=True, help='Business/location name')
    parser.add_argument('--email', help='Contact email (optional)')
    parser.add_argument('--phone', help='Contact phone (optional)')
    parser.add_argument('--dry-run', action='store_true', help='Check only, do not create')
    parser.add_argument('--force', action='store_true', help='Create even if location exists')
    args = parser.parse_args()

    domain = args.domain.lower().strip().replace('www.', '')
    result = {
        'domain': domain,
        'stage': 'ghl_setup',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'action': None,
        'success': False,
    }

    # Check for existing location
    existing = find_existing_location(domain)
    if existing:
        result['existing_location'] = {
            'id': existing.get('id'),
            'name': existing.get('name'),
        }
        if not args.force:
            result['action'] = 'skipped'
            result['reason'] = 'GHL location already exists. Use --force to create anyway.'
            result['success'] = True
            print(json.dumps(result, indent=2))
            return

    if args.dry_run:
        result['action'] = 'dry_run'
        result['success'] = True
        result['would_create'] = {
            'name': args.name,
            'domain': domain,
            'snapshot_id': GHL_SNAPSHOT_ID,
        }
        print(json.dumps(result, indent=2))
        return

    # Create location
    status_code, resp_data = create_location(domain, args.name, args.email, args.phone)

    if status_code in (200, 201):
        location_id = resp_data.get('id') or resp_data.get('locationId') or resp_data.get('location', {}).get('id')
        result['action'] = 'created'
        result['location_id'] = location_id
        result['success'] = True

        # Verify after short delay (snapshot takes a moment)
        if location_id:
            time.sleep(3)
            verification = verify_location(location_id)
            result['verification'] = verification
    else:
        result['action'] = 'failed'
        result['error'] = resp_data
        result['http_status'] = status_code

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
