#!/usr/bin/env python3
"""
Stage 1: Domain Pre-Check Tool
Checks domain health, DNS, GHL status, and CRM supertype mapping.
Returns JSON to stdout for n8n consumption.

Usage:
  python3 tools/migrate_check_domain.py --domain darksidetattoo.com
  python3 tools/migrate_check_domain.py --domains ghostinthetattoomachine.com,backtattoosnow.com
"""

import argparse
import json
import os
import socket
import ssl
import sys
from datetime import datetime
from urllib.parse import urlparse

import requests

# Load env vars
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

GHL_API_KEY = os.getenv('GHL_AGENCY_API_KEY', '')
GHL_API_BASE = os.getenv('GHL_API_BASE_URL', 'https://rest.gohighlevel.com/v1')
GHL_COMPANY_ID = os.getenv('GHL_COMPANY_ID', 'Wi9zjVQgZIH2Kk2lnfrg')

# CRM Supertype Map — extracted from TattooNOW admin page
SUPERTYPE_MAP = {
    'darksidetattoo.com': {'id': 85, 'name': 'Darkside Tattoo'},
    'badtattoos.com': {'id': 103, 'name': 'BadTattoos.com'},
    'gabrielcecetattoos.com': {'id': 213, 'name': 'gabriel cece dot com'},
    'vintagetattooflash.com': {'id': 266, 'name': 'Vintage Tattoo Flash'},
    'hyperspacestudios.com': {'id': 306, 'name': 'Hyperspace Studios'},
    'mdtattoos.com': {'id': 357, 'name': 'Mike DeVries'},
    'jjtattoos.com': {'id': 605, 'name': 'Jeff Johnson Tattoo'},
    'forbiddenimages.com': {'id': 713, 'name': 'Forbidden Images Tattoo Art Studio'},
    'stevemorristattoo.com': {'id': 867, 'name': 'Steve Morris'},
    'unifytattoofl.com': {'id': 872, 'name': 'Unify Tattoo Company'},
    '10kfoxesqueenstattoo.com': {'id': 896, 'name': '10 Thousand Foxes Tattoo'},
    'cattattoo.com': {'id': 961, 'name': 'Cat Tattoo'},
    'mariorosena.com': {'id': 977, 'name': 'Mario at Art Junkies'},
    'tattoomoney.com': {'id': 1027, 'name': '@newamericantattooco'},
    'identitytattoo.com': {'id': 1057, 'name': 'Identity Tattoo'},
    'philrobertsontattoos.com': {'id': 1157, 'name': 'Neon Dream'},
    'tattoogathering.com': {'id': 1163, 'name': 'Paradise Tattoo Gathering'},
    'ghostprinttattoo.com': {'id': 1230, 'name': 'Ghostprint Gallery Tattoo'},
    'cecilporterstudios.com': {'id': 1635, 'name': 'Cecil Porter Studios'},
    'bobtyrrell.com': {'id': 1686, 'name': 'Bob Tyrrells Night Gallery'},
    'tattoomachinesnow.com': {'id': 1706, 'name': 'Tattoo-Machines NOW'},
    'gaberipley.com': {'id': 1776, 'name': 'Gabe Ripley'},
    'tattooinspiration.com': {'id': 1892, 'name': 'Tattoo Inspiration'},
    'paradiseartistretreat.com': {'id': 2316, 'name': 'Paradise Artist Retreat'},
    'adamlauricella.com': {'id': 2317, 'name': 'Adam @ Graceland Tattoo'},
    'el-dugi-art.com': {'id': 2329, 'name': 'Ryan El Dugi Lewis'},
    'tattoosbygeorge.com': {'id': 2341, 'name': 'Tattoos by George'},
    'worldwidetattooconference.com': {'id': 2474, 'name': 'Worldwide Tattoo Conference'},
    'muecketattoos.com': {'id': 2643, 'name': 'Art of Muecke'},
    'paintedtemple.com': {'id': 2680, 'name': 'Painted Temple'},
    'mullytattoo.com': {'id': 2688, 'name': 'Independent Tattoo Company'},
    'justinmarianitattoos.com': {'id': 2699, 'name': 'Human Canvas Tattoo'},
    'deadgartattoos.com': {'id': 2735, 'name': 'Deadgar Tattoos'},
    'katelyncrane.com': {'id': 2811, 'name': 'Tattoos by Katelyn Crane'},
    'rembertattoos.com': {'id': 2828, 'name': 'Rember Tattoos'},
    'haleyadamstattoos.com': {'id': 2902, 'name': 'Haley Adams Tattoo'},
    'bostonrogoztattoos.com': {'id': 2905, 'name': 'Boston Rogoz Tattoo'},
    'larrybrogan.com': {'id': 2911, 'name': 'Tattoo City Skin Art Studio'},
    'michelewortman.com': {'id': 2957, 'name': 'Michele Wortman'},
    'guyaitchison.com': {'id': 2958, 'name': 'Guy Aitchison'},
    'skinofadifferentcolor.com': {'id': 3011, 'name': 'Skin of a Different Color'},
    'phippstattoo.com': {'id': 3026, 'name': 'Steve Phipps'},
    'tattoonow.com': {'id': 3075, 'name': 'TattooNOW'},
    'skingallerytattoo.com': {'id': 3089, 'name': 'Skin Gallery Tattoo'},
    'patricksweeneytattoos.com': {'id': 3125, 'name': 'Patrick Sweeney Tattoos'},
    'soringabor.com': {'id': 3271, 'name': 'Sorin Gabor at Sugar City Tattoo'},
    'tattoonowbusinessroundtable.com': {'id': 4318, 'name': 'TattooNOW Business Roundtable'},
    'reinventingthetattoo.com': {'id': 4353, 'name': 'Reinventing The Tattoo'},
    'artofdrewtattoo.com': {'id': 4422, 'name': 'Drew Siciliano'},
    'rudylopeztattoos.com': {'id': 4440, 'name': 'Mizu'},
    'rafaeltattoos.com': {'id': 4465, 'name': 'Rafael Marte Tattoos'},
    'venetiantattoogatering.com': {'id': 4552, 'name': 'Venetian Tattoo Gathering'},
    'bodyworks-tattoo.com': {'id': 4615, 'name': 'Tattoos by Don McDonald'},
    'juicytattoo.com': {'id': 4651, 'name': 'Juicy Tattoo'},
    'americantattooer.com': {'id': 4722, 'name': 'American Tattooer'},
    'artimmortaltattoo.com': {'id': 4793, 'name': 'Art Immortal Tattoo'},
    'jollyoctopus.co.nz': {'id': 5931, 'name': 'Jolly Octopus'},
    'kevinbledsoe.com': {'id': 6006, 'name': 'Kevin Bledsoe'},
    'emeraldisletattoosession.com': {'id': 6072, 'name': 'Emerald Isle Tattoo Sessions'},
    'christianperezart.com': {'id': 7373, 'name': 'Christian Perez'},
    'jwheelwrighttattoos.com': {'id': 7384, 'name': 'Jason Wheelwright Tattoos'},
    'daddyjackstattoos.com': {'id': 7390, 'name': 'Daddy Jacks Tattoos'},
}


def check_http(domain):
    """Check HTTP status and server headers."""
    result = {
        'http_status': None,
        'server': None,
        'redirect_chain': [],
        'ghl_detected': False,
        'final_url': None,
    }
    try:
        resp = requests.get(
            f'http://{domain}',
            timeout=10,
            allow_redirects=True,
            headers={'User-Agent': 'TattooNOW-Migration-Bot/1.0'}
        )
        result['http_status'] = resp.status_code
        result['server'] = resp.headers.get('server', '')
        result['final_url'] = resp.url
        if resp.history:
            result['redirect_chain'] = [r.url for r in resp.history]
        # Detect GHL by /lander redirect or leadconnectorhq in response
        if '/lander' in resp.url or 'leadconnectorhq' in resp.text[:5000]:
            result['ghl_detected'] = True
    except requests.exceptions.ConnectionError:
        result['http_status'] = 0
        result['server'] = 'CONNECTION_REFUSED'
    except requests.exceptions.Timeout:
        result['http_status'] = 0
        result['server'] = 'TIMEOUT'
    except Exception as e:
        result['http_status'] = 0
        result['server'] = f'ERROR: {str(e)[:100]}'
    return result


def check_dns(domain):
    """Check DNS resolution."""
    result = {'a_records': [], 'resolved': False}
    try:
        addrs = socket.getaddrinfo(domain, 80, socket.AF_INET, socket.SOCK_STREAM)
        result['a_records'] = list(set(addr[4][0] for addr in addrs))
        result['resolved'] = len(result['a_records']) > 0
    except socket.gaierror:
        result['resolved'] = False
    return result


def check_ssl(domain):
    """Check SSL certificate."""
    result = {'ssl_valid': False, 'ssl_issuer': None, 'ssl_expiry': None}
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.settimeout(5)
            s.connect((domain, 443))
            cert = s.getpeercert()
            result['ssl_valid'] = True
            result['ssl_issuer'] = dict(x[0] for x in cert.get('issuer', [()])).get('organizationName', 'Unknown')
            not_after = cert.get('notAfter', '')
            if not_after:
                result['ssl_expiry'] = not_after
    except Exception:
        pass
    return result


def check_ghl_locations(domain):
    """Check if domain already exists as a GHL location."""
    result = {'ghl_exists': False, 'ghl_location_id': None, 'ghl_location_name': None}
    if not GHL_API_KEY:
        result['ghl_error'] = 'No GHL API key configured'
        return result
    try:
        resp = requests.get(
            f'{GHL_API_BASE}/locations/',
            params={'companyId': GHL_COMPANY_ID, 'limit': 100},
            headers={'Authorization': f'Bearer {GHL_API_KEY}'},
            timeout=15
        )
        if resp.status_code == 200:
            locations = resp.json().get('locations', [])
            domain_lower = domain.lower().replace('www.', '')
            for loc in locations:
                # Check both domain and website fields
                loc_domains = []
                for field in ['domain', 'website']:
                    val = (loc.get(field, '') or '').lower()
                    val = val.replace('http://', '').replace('https://', '').replace('www.', '').rstrip('/')
                    if val and len(val) > 3:  # Skip empty/trivial values
                        loc_domains.append(val)
                if any(domain_lower == ld or domain_lower == ld.split('/')[0] for ld in loc_domains):
                    result['ghl_exists'] = True
                    result['ghl_location_id'] = loc.get('id')
                    result['ghl_location_name'] = loc.get('name')
                    break
    except Exception as e:
        result['ghl_error'] = str(e)[:100]
    return result


def check_crm(domain):
    """Look up CRM supertype mapping."""
    domain_lower = domain.lower().replace('www.', '')
    entry = SUPERTYPE_MAP.get(domain_lower)
    if entry:
        return {'crm_supertype': entry['id'], 'crm_name': entry['name'], 'in_crm': True}
    return {'crm_supertype': None, 'crm_name': None, 'in_crm': False}


def check_domain(domain):
    """Run all checks for a single domain."""
    domain = domain.lower().strip().replace('www.', '')
    result = {
        'domain': domain,
        'checked_at': datetime.utcnow().isoformat() + 'Z',
        'flags': [],
    }

    # Run all checks
    result.update(check_http(domain))
    result.update(check_dns(domain))
    result.update(check_ssl(domain))
    result.update(check_ghl_locations(domain))
    result.update(check_crm(domain))

    # Set flags
    if result.get('ghl_exists'):
        result['flags'].append('GHL_LOCATION_EXISTS')
    if result.get('ghl_detected'):
        result['flags'].append('GHL_SITE_DETECTED')
    if not result.get('resolved'):
        result['flags'].append('DNS_UNRESOLVED')
    if result.get('http_status') == 0:
        result['flags'].append('UNREACHABLE')
    elif result.get('http_status', 0) >= 400:
        result['flags'].append('HTTP_ERROR')
    if result.get('in_crm'):
        result['flags'].append('HAS_CRM_ENTRY')
    if not result.get('ssl_valid'):
        result['flags'].append('NO_SSL')

    return result


def main():
    parser = argparse.ArgumentParser(description='Stage 1: Domain Pre-Check')
    parser.add_argument('--domain', help='Single domain to check')
    parser.add_argument('--domains', help='Comma-separated list of domains')
    args = parser.parse_args()

    if not args.domain and not args.domains:
        parser.error('Provide --domain or --domains')

    domains = []
    if args.domain:
        domains.append(args.domain)
    if args.domains:
        domains.extend(d.strip() for d in args.domains.split(',') if d.strip())

    if len(domains) == 1:
        result = check_domain(domains[0])
        print(json.dumps(result, indent=2))
    else:
        results = [check_domain(d) for d in domains]
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
