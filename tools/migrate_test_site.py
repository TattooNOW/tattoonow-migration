#!/usr/bin/env python3
"""
Stage 4: Post-Build Site Testing
Checks GHL site health: homepage, SSL, page load, broken links.
Returns JSON test report for n8n consumption.

Usage:
  python3 tools/migrate_test_site.py --domain darksidetattoo.com --location-id abc123
  python3 tools/migrate_test_site.py --domain darksidetattoo.com
"""

import argparse
import json
import os
import re
import socket
import ssl
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

GHL_API_KEY = os.getenv('GHL_AGENCY_API_KEY', '')
GHL_API_BASE = os.getenv('GHL_API_BASE_URL', 'https://rest.gohighlevel.com/v1')


def check_homepage(url, timeout=15):
    """Check homepage returns 200 and has content."""
    try:
        resp = requests.get(url, timeout=timeout, headers={'User-Agent': 'TattooNOW-Migration-Bot/1.0'}, allow_redirects=True)
        body_length = len(resp.text)
        has_html = '<html' in resp.text[:500].lower() or '<!doctype' in resp.text[:500].lower()
        return {
            'url': url,
            'final_url': resp.url,
            'status': resp.status_code,
            'body_length': body_length,
            'has_html': has_html,
            'server': resp.headers.get('server', ''),
            'pass': resp.status_code == 200 and body_length > 500 and has_html,
        }
    except Exception as e:
        return {'url': url, 'status': 0, 'error': str(e)[:200], 'pass': False}


def check_ssl_cert(domain):
    """Check SSL certificate validity."""
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.settimeout(5)
            s.connect((domain, 443))
            cert = s.getpeercert()
            issuer = dict(x[0] for x in cert.get('issuer', [()])).get('organizationName', 'Unknown')
            not_after = cert.get('notAfter', '')
            return {
                'valid': True,
                'issuer': issuer,
                'expiry': not_after,
                'pass': True,
            }
    except Exception as e:
        return {'valid': False, 'error': str(e)[:200], 'pass': False}


def check_key_pages(base_url):
    """Check common pages exist (non-404)."""
    pages = ['/', '/about', '/contact', '/services', '/blog']
    results = []
    for page in pages:
        url = base_url.rstrip('/') + page
        try:
            resp = requests.get(url, timeout=10, headers={'User-Agent': 'TattooNOW-Migration-Bot/1.0'}, allow_redirects=True)
            results.append({
                'page': page,
                'status': resp.status_code,
                'exists': resp.status_code < 400,
            })
        except Exception:
            results.append({'page': page, 'status': 0, 'exists': False})
        time.sleep(0.3)
    return results


def check_broken_images(url):
    """Scan homepage for broken image references."""
    broken = []
    try:
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'TattooNOW-Migration-Bot/1.0'})
        if resp.status_code != 200:
            return {'checked': False, 'reason': f'Homepage returned {resp.status_code}'}

        # Extract img src attributes
        img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', resp.text, re.IGNORECASE)
        checked = 0
        for src in img_srcs[:20]:  # Check first 20 images max
            if src.startswith('data:'):
                continue
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = url.rstrip('/') + src
            elif not src.startswith('http'):
                src = url.rstrip('/') + '/' + src
            try:
                img_resp = requests.head(src, timeout=5, allow_redirects=True)
                if img_resp.status_code >= 400:
                    broken.append({'src': src[:200], 'status': img_resp.status_code})
                checked += 1
            except Exception:
                broken.append({'src': src[:200], 'status': 0})
                checked += 1
            time.sleep(0.2)
        return {'checked': True, 'images_found': len(img_srcs), 'images_checked': checked, 'broken': broken}
    except Exception as e:
        return {'checked': False, 'reason': str(e)[:200]}


def check_ghl_location(location_id):
    """Verify GHL location data is populated."""
    if not location_id:
        return {'checked': False, 'reason': 'No location ID provided'}
    try:
        resp = requests.get(
            f'{GHL_API_BASE}/locations/{location_id}',
            headers={'Authorization': f'Bearer {GHL_API_KEY}'},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            loc = data.get('location', data)
            return {
                'checked': True,
                'name': loc.get('name'),
                'domain': loc.get('domain'),
                'website': loc.get('website'),
                'pass': bool(loc.get('name')),
            }
        return {'checked': False, 'reason': f'API returned {resp.status_code}'}
    except Exception as e:
        return {'checked': False, 'reason': str(e)[:200]}


def main():
    parser = argparse.ArgumentParser(description='Stage 4: Post-Build Site Testing')
    parser.add_argument('--domain', required=True, help='Domain name to test')
    parser.add_argument('--location-id', help='GHL location ID')
    parser.add_argument('--url', help='Override test URL (default: https://{domain})')
    args = parser.parse_args()

    domain = args.domain.lower().strip().replace('www.', '')
    base_url = args.url or f'https://{domain}'

    result = {
        'domain': domain,
        'stage': 'site_testing',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'base_url': base_url,
        'tests': {},
        'overall_pass': False,
    }

    # Run all tests
    result['tests']['homepage'] = check_homepage(base_url)
    result['tests']['ssl'] = check_ssl_cert(domain)
    result['tests']['pages'] = check_key_pages(base_url)
    result['tests']['images'] = check_broken_images(base_url)

    if args.location_id:
        result['tests']['ghl_location'] = check_ghl_location(args.location_id)

    # Calculate overall pass/fail
    critical_pass = (
        result['tests']['homepage'].get('pass', False) and
        result['tests']['ssl'].get('pass', False)
    )
    broken_images = len(result['tests']['images'].get('broken', []))

    result['overall_pass'] = critical_pass and broken_images == 0
    result['summary'] = {
        'homepage': 'PASS' if result['tests']['homepage'].get('pass') else 'FAIL',
        'ssl': 'PASS' if result['tests']['ssl'].get('pass') else 'FAIL',
        'pages_found': sum(1 for p in result['tests']['pages'] if p.get('exists')),
        'pages_total': len(result['tests']['pages']),
        'broken_images': broken_images,
    }

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
