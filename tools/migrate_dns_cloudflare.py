#!/usr/bin/env python3
"""
Stage 5: DNS Setup via Cloudflare + GoDaddy Nameserver Instructions
Creates Cloudflare zone, adds DNS records pointing to GHL,
and generates step-by-step GoDaddy nameserver change instructions.
Returns JSON to stdout for n8n consumption.

Usage:
  python3 tools/migrate_dns_cloudflare.py --domain darksidetattoo.com
  python3 tools/migrate_dns_cloudflare.py --domain darksidetattoo.com --dry-run
  python3 tools/migrate_dns_cloudflare.py --domain darksidetattoo.com --verify-only
"""

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

CF_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN', '')
CF_ACCOUNT_ID = os.getenv('CLOUDFLARE_ACCOUNT_ID', '')
CF_API_BASE = 'https://api.cloudflare.com/client/v4'
CF_HEADERS = {
    'Authorization': f'Bearer {CF_API_TOKEN}',
    'Content-Type': 'application/json',
}

# GHL's CNAME target for custom domains
GHL_CNAME_TARGET = 'sites.leadconnectorhq.com'


def find_existing_zone(domain):
    """Check if a Cloudflare zone already exists for this domain."""
    try:
        resp = requests.get(
            f'{CF_API_BASE}/zones',
            params={'name': domain, 'account.id': CF_ACCOUNT_ID},
            headers=CF_HEADERS,
            timeout=15
        )
        if resp.status_code == 200:
            zones = resp.json().get('result', [])
            if zones:
                return zones[0]
    except Exception:
        pass
    return None


def create_zone(domain):
    """Create a new Cloudflare zone."""
    payload = {
        'name': domain,
        'account': {'id': CF_ACCOUNT_ID},
        'type': 'full',  # Full DNS management
    }
    resp = requests.post(
        f'{CF_API_BASE}/zones',
        json=payload,
        headers=CF_HEADERS,
        timeout=15
    )
    return resp.status_code, resp.json()


def add_dns_record(zone_id, record_type, name, content, proxied=True):
    """Add a DNS record to a Cloudflare zone."""
    payload = {
        'type': record_type,
        'name': name,
        'content': content,
        'proxied': proxied,
        'ttl': 1,  # Auto TTL when proxied
    }
    resp = requests.post(
        f'{CF_API_BASE}/zones/{zone_id}/dns_records',
        json=payload,
        headers=CF_HEADERS,
        timeout=15
    )
    return resp.status_code, resp.json()


def list_dns_records(zone_id):
    """List existing DNS records for a zone."""
    try:
        resp = requests.get(
            f'{CF_API_BASE}/zones/{zone_id}/dns_records',
            params={'per_page': 100},
            headers=CF_HEADERS,
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json().get('result', [])
    except Exception:
        pass
    return []


def setup_ghl_dns(zone_id, domain):
    """Add required DNS records for GHL hosting."""
    records_to_add = [
        # Root domain CNAME (Cloudflare supports CNAME flattening at root)
        {'type': 'CNAME', 'name': domain, 'content': GHL_CNAME_TARGET, 'proxied': True},
        # www subdomain CNAME
        {'type': 'CNAME', 'name': f'www.{domain}', 'content': GHL_CNAME_TARGET, 'proxied': True},
    ]

    results = []
    for rec in records_to_add:
        status, resp = add_dns_record(zone_id, rec['type'], rec['name'], rec['content'], rec['proxied'])
        results.append({
            'record': f"{rec['type']} {rec['name']} → {rec['content']}",
            'status': status,
            'success': status in (200, 201),
            'id': resp.get('result', {}).get('id') if status in (200, 201) else None,
            'error': resp.get('errors', [{}])[0].get('message') if status not in (200, 201) else None,
        })
        time.sleep(0.3)

    return results


TATTOOCONSULTATIONS_ZONE = 'tattooconsultations.com'


def domain_to_slug(domain):
    """Convert domain to a clean slug for test subdomain. e.g. sleevetattoosnow.com → sleevetattoosnow"""
    return domain.replace('.com', '').replace('.net', '').replace('.org', '').replace('.co.nz', '') \
        .replace('.', '-').replace('_', '-').lower().strip('-')


def create_test_subdomain(domain, dry_run=False):
    """
    Create {slug}.tattooconsultations.com CNAME → sites.leadconnectorhq.com
    in the tattooconsultations.com Cloudflare zone.
    Returns dict with url and result info.
    """
    slug = domain_to_slug(domain)
    subdomain_name = f'{slug}.{TATTOOCONSULTATIONS_ZONE}'

    if dry_run:
        return {
            'action': 'dry_run',
            'subdomain': subdomain_name,
            'cname_target': GHL_CNAME_TARGET,
            'url': f'https://{subdomain_name}',
        }

    # Find tattooconsultations.com zone
    try:
        resp = requests.get(
            f'{CF_API_BASE}/zones',
            params={'name': TATTOOCONSULTATIONS_ZONE, 'account.id': CF_ACCOUNT_ID},
            headers=CF_HEADERS,
            timeout=15
        )
        zones = resp.json().get('result', []) if resp.status_code == 200 else []
        if not zones:
            return {'action': 'error', 'error': f'Zone not found for {TATTOOCONSULTATIONS_ZONE}', 'subdomain': subdomain_name}
        zone_id = zones[0]['id']
    except Exception as e:
        return {'action': 'error', 'error': str(e), 'subdomain': subdomain_name}

    # Check if CNAME already exists
    try:
        existing_resp = requests.get(
            f'{CF_API_BASE}/zones/{zone_id}/dns_records',
            params={'type': 'CNAME', 'name': subdomain_name},
            headers=CF_HEADERS,
            timeout=15
        )
        existing = existing_resp.json().get('result', []) if existing_resp.status_code == 200 else []
        if existing:
            return {
                'action': 'exists',
                'subdomain': subdomain_name,
                'url': f'https://{subdomain_name}',
                'record_id': existing[0].get('id'),
            }
    except Exception:
        pass

    # Create the CNAME record
    status, result = add_dns_record(zone_id, 'CNAME', subdomain_name, GHL_CNAME_TARGET, proxied=True)
    if status in (200, 201):
        return {
            'action': 'created',
            'subdomain': subdomain_name,
            'url': f'https://{subdomain_name}',
            'record_id': result.get('result', {}).get('id'),
            'cname_target': GHL_CNAME_TARGET,
        }
    else:
        return {
            'action': 'error',
            'subdomain': subdomain_name,
            'error': result.get('errors', [{}])[0].get('message', 'Unknown error'),
        }


def lookup_registrar(domain):
    """Look up domain registrar via WHOIS."""
    try:
        import whois
        w = whois.whois(domain)
        registrar = (w.registrar or '').strip()
        return registrar
    except Exception as e:
        return f'WHOIS_ERROR: {str(e)[:100]}'


# Per-registrar instruction templates
REGISTRAR_INSTRUCTIONS = {
    'godaddy': {
        'name': 'GoDaddy',
        'login_url': 'https://dcc.godaddy.com/manage/{domain}/dns',
        'steps': [
            'Login to GoDaddy: https://dcc.godaddy.com/manage/{domain}/dns',
            'Scroll to "Nameservers" section',
            'Click "Change Nameservers"',
            'Select "I\'ll use my own nameservers"',
            'Enter: {ns1} and {ns2}',
            'Click "Save"',
        ],
    },
    'namecheap': {
        'name': 'Namecheap',
        'login_url': 'https://ap.www.namecheap.com/domains/domaincontrolpanel/{domain}/domain',
        'steps': [
            'Login to Namecheap: https://ap.www.namecheap.com/',
            'Go to Domain List → click "Manage" next to {domain}',
            'Under "Nameservers", select "Custom DNS"',
            'Enter: {ns1} and {ns2}',
            'Click the green checkmark to save',
        ],
    },
    'networksolutions': {
        'name': 'Network Solutions',
        'login_url': 'https://www.networksolutions.com/manage-it/index.jsp',
        'steps': [
            'Login to Network Solutions: https://www.networksolutions.com/manage-it/',
            'Click "Manage Account" → "My Domain Names"',
            'Click on {domain} → "Manage" → "Change Where Domain Points"',
            'Select "DNS" tab → "Advanced DNS"',
            'Under Nameservers, click "Move DNS"',
            'Enter: {ns1} and {ns2}',
            'Click "Move DNS" to save',
        ],
    },
    'google': {
        'name': 'Google Domains / Squarespace',
        'login_url': 'https://domains.squarespace.com/domains/{domain}/dns',
        'steps': [
            'Login: https://domains.squarespace.com/ (Google Domains migrated here)',
            'Select {domain} → "DNS" tab',
            'Scroll to "Custom nameservers" and click "Manage"',
            'Add: {ns1} and {ns2}',
            'Click "Save" then activate custom nameservers',
        ],
    },
    'cloudflare': {
        'name': 'Cloudflare (Already Here)',
        'login_url': 'https://dash.cloudflare.com/',
        'steps': [
            'Domain is already registered at Cloudflare — no nameserver change needed.',
            'Just ensure DNS records point to GHL (CNAME → preview.leadconnectorhq.com).',
        ],
    },
    'name.com': {
        'name': 'Name.com',
        'login_url': 'https://www.name.com/account/domain/details/{domain}#dns',
        'steps': [
            'Login to Name.com: https://www.name.com/account/',
            'Click "My Domains" → select {domain}',
            'Click "Nameservers" tab',
            'Switch to "Custom nameservers"',
            'Enter: {ns1} and {ns2}',
            'Click "Apply"',
        ],
    },
    'ionos': {
        'name': '1&1 IONOS',
        'login_url': 'https://my.ionos.com/domain-details/{domain}',
        'steps': [
            'Login to IONOS: https://my.ionos.com/',
            'Go to "Domains & SSL" → select {domain}',
            'Click "DNS" → "Nameserver Settings"',
            'Select "Use custom nameservers"',
            'Enter: {ns1} and {ns2}',
            'Click "Save"',
        ],
    },
}


def match_registrar(registrar_string):
    """Match WHOIS registrar string to our known registrar templates."""
    if not registrar_string or registrar_string.startswith('WHOIS_ERROR'):
        return None
    r = registrar_string.lower()
    if 'godaddy' in r or 'go daddy' in r:
        return 'godaddy'
    if 'namecheap' in r:
        return 'namecheap'
    if 'network solutions' in r or 'networksolutions' in r:
        return 'networksolutions'
    if 'google' in r or 'squarespace' in r:
        return 'google'
    if 'cloudflare' in r:
        return 'cloudflare'
    if 'name.com' in r:
        return 'name.com'
    if 'ionos' in r or '1&1' in r or 'united internet' in r:
        return 'ionos'
    return None


def generate_dns_instructions(domain, nameservers, registrar_raw=None):
    """Generate registrar-specific nameserver change instructions."""
    ns1 = nameservers[0] if len(nameservers) > 0 else 'ns1.cloudflare.com'
    ns2 = nameservers[1] if len(nameservers) > 1 else 'ns2.cloudflare.com'

    registrar_key = match_registrar(registrar_raw) if registrar_raw else None
    reg = REGISTRAR_INSTRUCTIONS.get(registrar_key) if registrar_key else None

    # Header
    registrar_label = reg['name'] if reg else (registrar_raw or 'Unknown Registrar')
    steps_block = ''
    if reg:
        for i, step in enumerate(reg['steps'], 1):
            formatted = step.format(domain=domain, ns1=ns1, ns2=ns2)
            steps_block += f'   Step {i}: {formatted}\n'
    else:
        steps_block = f"""   Step 1: Find your registrar's login page
   Registrar detected: {registrar_raw or 'UNKNOWN — check WHOIS manually'}
   Step 2: Navigate to DNS or Nameserver settings for {domain}
   Step 3: Switch to "Custom nameservers"
   Step 4: Enter:
      Nameserver 1: {ns1}
      Nameserver 2: {ns2}
   Step 5: Save changes
"""

    instructions = f"""
==========================================================
  DNS Cutover Instructions for {domain}
  Registrar: {registrar_label}
==========================================================

IMPORTANT: This is a MANUAL step. Do not skip.

{steps_block}
After saving:
   - Allow 24-48 hours for full DNS propagation
   - Verify: python3 tools/migrate_dns_cloudflare.py --domain {domain} --verify-only

==========================================================
  After cutover, Cloudflare handles:
  - SSL certificate (auto-provisioned, ~15 min)
  - CDN caching
  - DDoS protection
  - DNS management
==========================================================
""".strip()
    return instructions


def verify_dns_propagation(domain):
    """Check if DNS has propagated to Cloudflare."""
    result = {'propagated': False, 'checks': []}
    try:
        # Check if domain resolves
        addrs = socket.getaddrinfo(domain, 443, socket.AF_INET, socket.SOCK_STREAM)
        ips = list(set(addr[4][0] for addr in addrs))
        result['checks'].append({'type': 'A_RECORD', 'values': ips, 'resolved': True})
    except socket.gaierror:
        result['checks'].append({'type': 'A_RECORD', 'values': [], 'resolved': False})
        return result

    # Check if it's pointing to Cloudflare (CF IPs are in 104.x.x.x, 172.x.x.x, etc.)
    try:
        resp = requests.get(
            f'https://{domain}',
            timeout=10,
            headers={'User-Agent': 'TattooNOW-Migration-Bot/1.0'},
            allow_redirects=True
        )
        server = resp.headers.get('server', '').lower()
        cf_ray = resp.headers.get('cf-ray', '')
        result['checks'].append({
            'type': 'CLOUDFLARE_PROXY',
            'server': resp.headers.get('server', ''),
            'cf_ray': cf_ray,
            'is_cloudflare': 'cloudflare' in server or bool(cf_ray),
        })
        result['propagated'] = 'cloudflare' in server or bool(cf_ray)
    except Exception as e:
        result['checks'].append({'type': 'HTTPS_CHECK', 'error': str(e)[:200]})

    return result


def main():
    parser = argparse.ArgumentParser(description='Stage 5: DNS Setup + Registrar-Specific Instructions')
    parser.add_argument('--domain', required=True, help='Domain name')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be created')
    parser.add_argument('--verify-only', action='store_true', help='Only check DNS propagation')
    parser.add_argument('--skip-dns-records', action='store_true', help='Create zone only, skip DNS records')
    parser.add_argument('--whois-only', action='store_true', help='Only look up registrar, do not touch DNS')
    parser.add_argument('--test-subdomain', action='store_true', help='Create {slug}.tattooconsultations.com CNAME only')
    args = parser.parse_args()

    domain = args.domain.lower().strip().replace('www.', '')
    result = {
        'domain': domain,
        'stage': 'dns_setup',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'action': None,
        'success': False,
    }

    # Test subdomain mode — create {slug}.tattooconsultations.com CNAME only
    if args.test_subdomain:
        sub_result = create_test_subdomain(domain, dry_run=args.dry_run)
        result.update({
            'stage': 'test_subdomain',
            'action': sub_result.get('action'),
            'success': sub_result.get('action') in ('created', 'exists', 'dry_run'),
            'testSubdomain': sub_result,
        })
        print(json.dumps(result, indent=2))
        sys.exit(0)

    # WHOIS registrar lookup (always run)
    registrar_raw = lookup_registrar(domain)
    registrar_key = match_registrar(registrar_raw)
    result['registrar'] = registrar_raw
    result['registrar_key'] = registrar_key or 'unknown'

    # WHOIS-only mode — just return registrar info
    if args.whois_only:
        result['action'] = 'whois_lookup'
        result['success'] = not registrar_raw.startswith('WHOIS_ERROR')
        result['instructions_available'] = registrar_key is not None
        if registrar_key:
            result['registrar_name'] = REGISTRAR_INSTRUCTIONS[registrar_key]['name']
        print(json.dumps(result, indent=2))
        return

    # Verify-only mode
    if args.verify_only:
        result['action'] = 'verify'
        verification = verify_dns_propagation(domain)
        result['verification'] = verification
        result['success'] = verification['propagated']
        result['status'] = 'PROPAGATED' if verification['propagated'] else 'NOT_PROPAGATED'
        print(json.dumps(result, indent=2))
        return

    # Check for existing zone
    existing = find_existing_zone(domain)
    if existing:
        result['existing_zone'] = {
            'id': existing.get('id'),
            'status': existing.get('status'),
            'name_servers': existing.get('name_servers', []),
        }

    if args.dry_run:
        result['action'] = 'dry_run'
        result['success'] = True
        result['would_create'] = {
            'zone': domain,
            'records': [
                f'CNAME {domain} → {GHL_CNAME_TARGET}',
                f'CNAME www.{domain} → {GHL_CNAME_TARGET}',
            ],
        }
        if existing:
            result['would_create']['note'] = 'Zone already exists, would add DNS records only'
        result['dns_instructions'] = generate_dns_instructions(domain, existing.get('name_servers', []) if existing else [], registrar_raw)
        print(json.dumps(result, indent=2))
        return

    # Create zone if it doesn't exist
    zone_id = None
    nameservers = []

    if existing:
        zone_id = existing['id']
        nameservers = existing.get('name_servers', [])
        result['zone_action'] = 'existing'
    else:
        status, resp = create_zone(domain)
        if status in (200, 201) and resp.get('success'):
            zone_data = resp.get('result', {})
            zone_id = zone_data.get('id')
            nameservers = zone_data.get('name_servers', [])
            result['zone_action'] = 'created'
            result['zone_id'] = zone_id
        else:
            result['action'] = 'failed'
            result['error'] = resp.get('errors', [{}])[0].get('message', 'Unknown error')
            print(json.dumps(result, indent=2))
            return

    result['nameservers'] = nameservers

    # Add DNS records
    if not args.skip_dns_records and zone_id:
        dns_results = setup_ghl_dns(zone_id, domain)
        result['dns_records'] = dns_results
        all_success = all(r['success'] for r in dns_results)
        if not all_success:
            for r in dns_results:
                if not r['success'] and r.get('error') and 'already exists' in r.get('error', '').lower():
                    r['success'] = True
            all_success = all(r['success'] for r in dns_results)
        result['dns_all_success'] = all_success

    # Generate registrar-specific instructions
    result['dns_instructions'] = generate_dns_instructions(domain, nameservers, registrar_raw)
    result['action'] = 'zone_ready'
    result['success'] = True
    result['next_step'] = f'MANUAL: Change nameservers at {result["registrar_key"]} (see instructions)'

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
