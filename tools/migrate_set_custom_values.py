#!/usr/bin/env python3
"""
Stage 2.5: Set GHL Location Custom Values
Populates GHL custom values (studio name, URL, colors, logo, etc.)
from Airtable migrationMeta identityData + testSubdomain fields.

Run after GHL location creation (Stage 2) and before blog migration (Stage 3).

Usage:
  python3 tools/migrate_set_custom_values.py --domain sleevetattoosnow.com --location-id sWu6C0JeGO3XgINZaTTB
  python3 tools/migrate_set_custom_values.py --domain sleevetattoosnow.com --location-id sWu6C0JeGO3XgINZaTTB --dry-run
"""

import argparse
import json
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

GHL_V2_BASE = 'https://services.leadconnectorhq.com'
GHL_V2_VERSION = '2021-07-28'
AIRTABLE_TOKEN = os.getenv('AIRTABLE_TOKEN', '')
AIRTABLE_BASE = 'apptbA8Mljf70CG24'
AIRTABLE_TASKS_TABLE = 'tblBP4uzRGQBcBco9'


def fetch_migration_meta(domain):
    """Fetch migrationMeta from Airtable task Notes. Returns (meta_dict, error)."""
    try:
        url = f'https://api.airtable.com/v0/{AIRTABLE_BASE}/{AIRTABLE_TASKS_TABLE}'
        params = {
            'filterByFormula': f"FIND('{domain}', {{Task}})",
            'fields[]': ['Task', 'Notes'],
            'maxRecords': 5,
        }
        resp = requests.get(url, headers={'Authorization': f'Bearer {AIRTABLE_TOKEN}'}, params=params, timeout=15)
        if resp.status_code != 200:
            return None, f'Airtable error {resp.status_code}'
        records = resp.json().get('records', [])
        for rec in records:
            notes = rec.get('fields', {}).get('Notes', '')
            match = re.search(r'<!--\s*migrationMeta:\s*(\{.*?\})\s*-->', notes, re.DOTALL)
            if match:
                try:
                    meta = json.loads(match.group(1))
                    return meta, None
                except json.JSONDecodeError as e:
                    return None, f'migrationMeta JSON parse error: {e}'
        return None, 'No migrationMeta found in Airtable task Notes'
    except Exception as e:
        return None, str(e)[:200]


def fetch_custom_value_definitions(location_id, pit):
    """Fetch all custom value field definitions. Returns ({fieldKey: id}, error)."""
    try:
        r = requests.get(
            f'{GHL_V2_BASE}/locations/{location_id}/customValues',
            headers={'Authorization': f'Bearer {pit}', 'Version': GHL_V2_VERSION},
            timeout=15,
        )
        if r.status_code != 200:
            return {}, f'HTTP {r.status_code}: {r.text[:200]}'
        defs = r.json().get('customValues', [])
        return {d['fieldKey']: d['id'] for d in defs}, None
    except Exception as e:
        return {}, str(e)[:200]


def set_custom_value(location_id, cv_id, value, pit):
    """Set a single custom value by ID. Returns (success, error)."""
    try:
        r = requests.put(
            f'{GHL_V2_BASE}/locations/{location_id}/customValues/{cv_id}',
            json={'value': value},
            headers={
                'Authorization': f'Bearer {pit}',
                'Version': GHL_V2_VERSION,
                'Content-Type': 'application/json',
            },
            timeout=15,
        )
        if r.status_code in (200, 201):
            return True, None
        return False, f'HTTP {r.status_code}: {r.text[:200]}'
    except Exception as e:
        return False, str(e)[:200]


def build_values_from_meta(meta, domain):
    """Build fieldKey → value dict from migrationMeta and identity data."""
    values = {}
    client_name = meta.get('client', '')
    test_subdomain = meta.get('testSubdomain', '')
    identity = meta.get('identityData', {})

    # Studio name
    if client_name:
        values['studio__name'] = client_name

    # Studio URL — prefer test subdomain, fallback to original domain
    studio_url = test_subdomain or f'https://{domain}'
    values['studio__url'] = studio_url

    # Navigation base — the test/live domain used for internal links
    if test_subdomain:
        values['admin__navigation_base'] = test_subdomain

    # From scrape identity data (migrate_scrape_identity.py output stored in identityData)
    if identity.get('logoUrl'):
        values['01_studio_logo_upload'] = identity['logoUrl']
    if identity.get('primaryColor'):
        values['01_studio_color_primary'] = identity['primaryColor']
    if identity.get('secondaryColor'):
        values['01_studio_color_secondary'] = identity['secondaryColor']
    if identity.get('accentColor'):
        values['01_studio_color_accent'] = identity['accentColor']
    if identity.get('instagram'):
        values['01_studio_instagram'] = identity['instagram']
    if identity.get('email'):
        values['studio__from_email'] = identity['email']

    return values


def main():
    parser = argparse.ArgumentParser(description='Stage 2.5: Set GHL Location Custom Values')
    parser.add_argument('--domain', required=True, help='Domain name')
    parser.add_argument('--location-id', required=True, help='GHL location ID')
    parser.add_argument('--pit', help='GHL Private Integration Token (fetched from Airtable if not provided)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be set without making changes')
    args = parser.parse_args()

    domain = args.domain.lower().strip().replace('www.', '')

    # Fetch migrationMeta from Airtable
    meta, meta_error = fetch_migration_meta(domain)
    if not meta:
        print(json.dumps({'success': False, 'error': f'Could not load migrationMeta: {meta_error}'}, indent=2))
        return

    # Resolve PIT
    pit = args.pit or meta.get('ghlPit') or meta.get('pit')
    if not pit:
        print(json.dumps({'success': False, 'error': 'No PIT found. Pass --pit or add ghlPit to Airtable migrationMeta.'}, indent=2))
        return

    # Build values to set
    values = build_values_from_meta(meta, domain)
    if not values:
        print(json.dumps({'success': True, 'action': 'nothing_to_set', 'reason': 'No custom values derived from migrationMeta'}, indent=2))
        return

    if args.dry_run:
        print(json.dumps({'success': True, 'action': 'dry_run', 'would_set': values}, indent=2))
        return

    # Fetch field definitions to map fieldKey → ID
    key_to_id, defs_error = fetch_custom_value_definitions(args.location_id, pit)
    if defs_error:
        print(json.dumps({'success': False, 'error': f'Could not fetch custom value definitions: {defs_error}'}, indent=2))
        return

    # Set each value
    results = {}
    for field_key, value in values.items():
        cv_id = key_to_id.get(field_key)
        if not cv_id:
            results[field_key] = 'not_found'
            continue
        ok, err = set_custom_value(args.location_id, cv_id, value, pit)
        results[field_key] = 'ok' if ok else f'error: {err}'

    success = all(v == 'ok' for v in results.values() if v != 'not_found')
    print(json.dumps({
        'success': success,
        'action': 'set_custom_values',
        'domain': domain,
        'location_id': args.location_id,
        'results': results,
    }, indent=2))


if __name__ == '__main__':
    main()
