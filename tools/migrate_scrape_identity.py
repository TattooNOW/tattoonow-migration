#!/usr/bin/env python3
"""
Content Sub-Step 1: Scrape Website Identity
Extracts logo image URL and brand colors from an existing website.
Returns JSON to stdout for n8n consumption.

Usage:
  python3 tools/migrate_scrape_identity.py --domain darksidetattoo.com
  python3 tools/migrate_scrape_identity.py --domain deadsite.com  # returns needsApproval: true
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def scrape_identity(domain: str) -> dict:
    """Scrape a website for logo and brand colors."""
    result = {
        'domain': domain,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'logoUrl': None,
        'logoFound': False,
        'colors': [],
        'colorsFound': False,
        'needsApproval': False,
        'siteReachable': False,
        'errors': []
    }

    # Try to fetch the homepage
    url = f'https://{domain}'
    html = None
    for scheme in ['https', 'http']:
        try:
            resp = requests.get(f'{scheme}://{domain}', timeout=(5, 8), allow_redirects=True,
                                headers={'User-Agent': 'Mozilla/5.0 (compatible; TattooNOW Migration Bot)'})
            if resp.status_code == 200 and len(resp.text) > 500:
                html = resp.text
                url = resp.url
                result['siteReachable'] = True
                break
        except requests.RequestException as e:
            result['errors'].append(f'{scheme}: {str(e)[:100]}')

    if not html:
        result['needsApproval'] = True
        result['errors'].append('Site unreachable or returned empty response. Manual brand input needed.')
        return result

    soup = BeautifulSoup(html, 'html.parser')

    # --- LOGO DETECTION ---
    logo_candidates = []

    # 1. Look for <img> tags with "logo" in class, id, alt, or src
    for img in soup.find_all('img'):
        attrs_text = ' '.join([
            img.get('class', [''])[0] if isinstance(img.get('class'), list) else str(img.get('class', '')),
            str(img.get('id', '')),
            str(img.get('alt', '')),
            str(img.get('src', ''))
        ]).lower()
        if 'logo' in attrs_text:
            src = img.get('src') or img.get('data-src')
            if src:
                logo_candidates.append(('img-logo', urljoin(url, src)))

    # 2. Look for <link rel="icon"> or <link rel="apple-touch-icon">
    for link in soup.find_all('link', rel=True):
        rels = [r.lower() for r in (link['rel'] if isinstance(link['rel'], list) else [link['rel']])]
        if any(r in rels for r in ['icon', 'apple-touch-icon', 'shortcut icon']):
            href = link.get('href')
            if href:
                logo_candidates.append(('favicon', urljoin(url, href)))

    # 3. Look for og:image meta tag
    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content'):
        logo_candidates.append(('og:image', urljoin(url, og_image['content'])))

    # 4. Look for <img> in <header> or <nav>
    for container in soup.find_all(['header', 'nav']):
        for img in container.find_all('img', limit=3):
            src = img.get('src') or img.get('data-src')
            if src:
                logo_candidates.append(('header-img', urljoin(url, src)))

    # Pick the best logo candidate (img-logo > header-img > og:image > favicon)
    priority = {'img-logo': 0, 'header-img': 1, 'og:image': 2, 'favicon': 3}
    logo_candidates.sort(key=lambda x: priority.get(x[0], 99))

    if logo_candidates:
        result['logoUrl'] = logo_candidates[0][1]
        result['logoFound'] = True
        result['logoSource'] = logo_candidates[0][0]
        if len(logo_candidates) > 1:
            result['logoAlternatives'] = [c[1] for c in logo_candidates[1:4]]

    # --- COLOR DETECTION ---
    colors = Counter()

    # 1. Parse inline styles and <style> blocks for hex colors
    style_text = ''
    for style_tag in soup.find_all('style'):
        if style_tag.string:
            style_text += style_tag.string

    # Also check inline styles on key elements
    for elem in soup.find_all(['body', 'header', 'nav', 'main', 'footer', 'div', 'a', 'h1', 'h2']):
        inline = elem.get('style', '')
        if inline:
            style_text += ' ' + inline

    # Extract hex colors
    hex_colors = re.findall(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', style_text)
    for c in hex_colors:
        normalized = c.upper()
        if len(normalized) == 3:
            normalized = ''.join([ch * 2 for ch in normalized])
        # Skip pure black, white, and very common grays
        if normalized not in ('000000', 'FFFFFF', 'F5F5F5', 'E5E5E5', 'CCCCCC', '333333', '666666', '999999'):
            colors[f'#{normalized}'] += 1

    # Extract rgb/rgba colors
    rgb_colors = re.findall(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', style_text)
    for r, g, b in rgb_colors:
        hex_val = f'#{int(r):02X}{int(g):02X}{int(b):02X}'
        if hex_val not in ('#000000', '#FFFFFF'):
            colors[hex_val] += 1

    # 2. Check for CSS custom properties (--primary-color, --brand-color, etc.)
    custom_props = re.findall(r'--(primary|brand|accent|main|theme)[^:]*:\s*([^;]+)', style_text, re.IGNORECASE)
    for prop_name, prop_val in custom_props:
        prop_val = prop_val.strip()
        hex_match = re.match(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', prop_val)
        if hex_match:
            c = hex_match.group(1).upper()
            if len(c) == 3:
                c = ''.join([ch * 2 for ch in c])
            colors[f'#{c}'] += 10  # Boost custom properties

    # Get top colors by frequency
    top_colors = [color for color, _ in colors.most_common(5)]
    if top_colors:
        result['colors'] = top_colors
        result['colorsFound'] = True

    # If no logo and no colors, flag for manual input
    if not result['logoFound'] and not result['colorsFound']:
        result['needsApproval'] = True

    return result


def main():
    parser = argparse.ArgumentParser(description='Scrape website identity (logo + colors)')
    parser.add_argument('--domain', required=True, help='Domain to scrape')
    args = parser.parse_args()

    domain = args.domain.strip().lower()
    if domain.startswith('http'):
        domain = domain.split('//')[1].split('/')[0]

    result = scrape_identity(domain)
    print(json.dumps(result, indent=2))

    # Exit code: 0 = success (even if needsApproval), 1 = hard error
    sys.exit(0)


if __name__ == '__main__':
    main()
