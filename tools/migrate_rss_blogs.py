#!/usr/bin/env python3
"""
Stage 3: Content Migration via RSS
Triggers RSS generation from TattooNOW CRM, parses the feed,
and creates blog posts in GHL via V2 Blogs API (requires PIT per location).

PIT (Private Integration Token) is fetched from Airtable task Notes metadata
(migrationMeta comment) or passed directly via --pit flag.

Usage:
  python3 tools/migrate_rss_blogs.py --domain guyaitchison.com --location-id abc123
  python3 tools/migrate_rss_blogs.py --domain guyaitchison.com --location-id abc123 --dry-run
  python3 tools/migrate_rss_blogs.py --domain guyaitchison.com --location-id abc123 --pit eyJ...
  python3 tools/migrate_rss_blogs.py --domain coverup911.com --location-id abc123 --test-content darksidetattoo.com
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

GHL_API_KEY = os.getenv('GHL_AGENCY_API_KEY', '')
GHL_V2_BASE = 'https://services.leadconnectorhq.com'
GHL_V2_VERSION = '2021-07-28'
TN_CRM_BASE = os.getenv('TN_CRM_BASE_URL', 'https://www.tattoonow.com/members/index.cfm')
TN_AUTH_PARAM = os.getenv('TN_CRM_AUTH_PARAM', 'TattooNOWAutoGeneration=1')
AIRTABLE_TOKEN = os.getenv('AIRTABLE_TOKEN', '')
AIRTABLE_BASE = 'apptbA8Mljf70CG24'
AIRTABLE_TASKS_TABLE = 'tblBP4uzRGQBcBco9'

# Domain → supertype ID mapping (same as migrate_check_domain.py)
SUPERTYPE_MAP = {
    'darksidetattoo.com': 85,
    'badtattoos.com': 103,
    'gabrielcecetattoos.com': 213,
    'vintagetattooflash.com': 266,
    'hyperspacestudios.com': 306,
    'mdtattoos.com': 357,
    'jjtattoos.com': 605,
    'forbiddenimages.com': 713,
    'stevemorristattoo.com': 867,
    'unifytattoofl.com': 872,
    '10kfoxesqueenstattoo.com': 896,
    'cattattoo.com': 961,
    'mariorosena.com': 977,
    'tattoomoney.com': 1027,
    'identitytattoo.com': 1057,
    'philrobertsontattoos.com': 1157,
    'tattoogathering.com': 1163,
    'ghostprinttattoo.com': 1230,
    'cecilporterstudios.com': 1635,
    'bobtyrrell.com': 1686,
    'tattoomachinesnow.com': 1706,
    'gaberipley.com': 1776,
    'tattooinspiration.com': 1892,
    'paradiseartistretreat.com': 2316,
    'adamlauricella.com': 2317,
    'el-dugi-art.com': 2329,
    'tattoosbygeorge.com': 2341,
    'worldwidetattooconference.com': 2474,
    'muecketattoos.com': 2643,
    'paintedtemple.com': 2680,
    'mullytattoo.com': 2688,
    'justinmarianitattoos.com': 2699,
    'deadgartattoos.com': 2735,
    'katelyncrane.com': 2811,
    'rembertattoos.com': 2828,
    'haleyadamstattoos.com': 2902,
    'bostonrogoztattoos.com': 2905,
    'larrybrogan.com': 2911,
    'michelewortman.com': 2957,
    'guyaitchison.com': 2958,
    'skinofadifferentcolor.com': 3011,
    'phippstattoo.com': 3026,
    'tattoonow.com': 3075,
    'skingallerytattoo.com': 3089,
    'patricksweeneytattoos.com': 3125,
    'soringabor.com': 3271,
    'tattoonowbusinessroundtable.com': 4318,
    'reinventingthetattoo.com': 4353,
    'artofdrewtattoo.com': 4422,
    'rudylopeztattoos.com': 4440,
    'rafaeltattoos.com': 4465,
    'venetiantattoogatering.com': 4552,
    'bodyworks-tattoo.com': 4615,
    'juicytattoo.com': 4651,
    'americantattooer.com': 4722,
    'artimmortaltattoo.com': 4793,
    'jollyoctopus.co.nz': 5931,
    'kevinbledsoe.com': 6006,
    'emeraldisletattoosession.com': 6072,
    'christianperezart.com': 7373,
    'jwheelwrighttattoos.com': 7384,
    'daddyjackstattoos.com': 7390,
}

# GEO tag extraction — US state names and abbreviations
US_STATES = {
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado', 'connecticut',
    'delaware', 'florida', 'georgia', 'hawaii', 'idaho', 'illinois', 'indiana', 'iowa',
    'kansas', 'kentucky', 'louisiana', 'maine', 'maryland', 'massachusetts', 'michigan',
    'minnesota', 'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
    'new hampshire', 'new jersey', 'new mexico', 'new york', 'north carolina',
    'north dakota', 'ohio', 'oklahoma', 'oregon', 'pennsylvania', 'rhode island',
    'south carolina', 'south dakota', 'tennessee', 'texas', 'utah', 'vermont',
    'virginia', 'washington', 'west virginia', 'wisconsin', 'wyoming',
}
STATE_ABBREVS = {
    'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga', 'hi', 'id', 'il', 'in',
    'ia', 'ks', 'ky', 'la', 'me', 'md', 'ma', 'mi', 'mn', 'ms', 'mo', 'mt', 'ne', 'nv',
    'nh', 'nj', 'nm', 'ny', 'nc', 'nd', 'oh', 'ok', 'or', 'pa', 'ri', 'sc', 'sd', 'tn',
    'tx', 'ut', 'vt', 'va', 'wa', 'wv', 'wi', 'wy',
}


def trigger_rss_generation(supertype_id):
    """Hit the CRM to generate RSS files on the server. This is slow (30-120s)."""
    url = f'{TN_CRM_BASE}?task=generaterssmigrate&super={supertype_id}&{TN_AUTH_PARAM}'
    try:
        resp = requests.get(url, timeout=120)
        return {'status': resp.status_code, 'success': resp.status_code == 200}
    except Exception as e:
        return {'status': 0, 'success': False, 'error': str(e)[:200]}


def fetch_rss_feed(domain, supertype_id):
    """Fetch the RSS feed from the client's own domain (where CRM writes them after trigger)."""
    urls_to_try = [
        f'https://www.{domain}/rss/news.xml',
        f'https://www.{domain}/rss/tattoos.xml',
        f'https://www.{domain}/rss/art.xml',
        f'https://www.{domain}/rss/artists.xml',
        f'https://www.{domain}/rss/readers_choice.xml',
        f'http://www.{domain}/rss/news.xml',
        f'http://www.{domain}/rss/tattoos.xml',
        f'http://www.{domain}/rss/art.xml',
        f'http://www.{domain}/rss/artists.xml',
        f'https://{domain}/rss/news.xml',
    ]

    for url in urls_to_try:
        try:
            resp = requests.get(url, timeout=15, allow_redirects=False,
                                headers={'User-Agent': 'TattooNOW-Migration-Bot/1.0'})
            if resp.status_code == 200 and ('<?xml' in resp.text[:100] or '<rss' in resp.text[:200]):
                return resp.text, url
        except Exception:
            continue
    return None, None


def parse_rss(xml_text):
    """Parse RSS XML into a list of blog post dicts using stdlib xml.etree."""
    posts = []
    try:
        # Strip XML namespace prefixes to avoid parse errors from undeclared namespaces.
        # media:thumbnail → thumbnail, content:encoded → encoded, dc:creator → creator
        cleaned = re.sub(r'<(/?)\w+:(\w+)', lambda m: f'<{m.group(1)}{m.group(2)}', xml_text)
        # Fix bare & entities (not part of &amp; &lt; etc. or &#NNN;)
        cleaned = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#)', '&amp;', cleaned)
        # Fix malformed numeric entities missing the leading & (e.g. #39; → &#39;)
        # These come from double-encoding in the TattooNOW CRM RSS output
        cleaned = re.sub(r'(?<!&)#(\d+);', r'&#\1;', cleaned)
        root = ET.fromstring(cleaned)

        channel = root.find('channel')
        if channel is not None:
            for item in channel.findall('item'):
                # Content: prefer content:encoded (stripped to 'encoded'), fallback to description
                raw_content = item.findtext('encoded') or item.findtext('description') or ''
                # Properly decode all HTML entities including numeric ones like &#39;
                content = unescape(raw_content)

                # Image: prefer media:thumbnail (stripped to 'thumbnail')
                # media:content strips to 'content' — check for url + image type attributes
                # Validate all image URLs: must end with a file extension (reject bare directory paths)
                def _valid_image_url(url):
                    return bool(url and url.startswith('http') and
                                re.search(r'\.(jpe?g|png|gif|webp)(\?[^"\']*)?$', url, re.IGNORECASE))

                image_url = ''
                thumb_el = item.find('thumbnail')
                if thumb_el is not None:
                    candidate = thumb_el.get('url', '')
                    if _valid_image_url(candidate):
                        image_url = candidate
                if not image_url:
                    content_el = item.find('content')
                    if content_el is not None and content_el.get('type', '').startswith('image'):
                        candidate = content_el.get('url', '')
                        if _valid_image_url(candidate):
                            image_url = candidate
                # Last fallback: first <img src> in HTML content with a valid image extension
                if not image_url:
                    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
                    if img_match:
                        candidate = img_match.group(1)
                        if _valid_image_url(candidate):
                            image_url = candidate

                # Description: use <description> (not encoded content) stripped of HTML, 300 chars
                desc_raw = item.findtext('description') or ''
                desc_text = re.sub(r'<[^>]+>', '', unescape(desc_raw)).strip()
                description = ' '.join(desc_text.split())[:300]

                # Keywords for category matching
                keywords = [k.strip() for k in (item.findtext('keywords') or '').split(',') if k.strip()]

                post = {
                    'title': (item.findtext('title') or '').strip(),
                    'content': content,
                    'published': item.findtext('pubDate') or '',
                    'link': item.findtext('link') or '',
                    'author': item.findtext('author') or item.findtext('creator', '') or '',
                    'imageUrl': image_url,
                    'description': description,
                    'keywords': keywords,
                }
                if post['title']:
                    posts.append(post)
        else:
            # Atom format: feed > entry
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns):
                content_el = entry.find('atom:content', ns) or entry.find('atom:summary', ns)
                post = {
                    'title': (entry.findtext('atom:title', '', ns) or '').strip(),
                    'content': unescape(content_el.text if content_el is not None and content_el.text else ''),
                    'published': entry.findtext('atom:published', '', ns) or entry.findtext('atom:updated', '', ns),
                    'link': '',
                    'author': '',
                    'imageUrl': '',
                    'description': '',
                    'keywords': [],
                }
                link_el = entry.find('atom:link', ns)
                if link_el is not None:
                    post['link'] = link_el.get('href', '')
                author_el = entry.find('atom:author', ns)
                if author_el is not None:
                    post['author'] = author_el.findtext('atom:name', '', ns)
                if post['title']:
                    posts.append(post)
    except ET.ParseError as e:
        return [], str(e)
    return posts, None


def fetch_blog_sites(location_id, pit):
    """Fetch all blog sites for a GHL location via V2 API. Returns (list of {id, name}, error)."""
    try:
        r = requests.get(
            f'{GHL_V2_BASE}/blogs/site/all',
            params={'locationId': location_id, 'limit': 20, 'skip': 0},
            headers={'Authorization': f'Bearer {pit}', 'Version': GHL_V2_VERSION},
            timeout=15,
        )
        if r.status_code == 200:
            sites = r.json().get('data', [])
            return [{'id': s['_id'], 'name': s.get('name', '')} for s in sites], None
        return [], f'HTTP {r.status_code}: {r.text[:200]}'
    except Exception as e:
        return [], str(e)[:200]


def fetch_location_blog_meta(location_id, pit):
    """Fetch categories and authors for a GHL location.
    Returns (categories_list, authors_list).
    categories_list = [{'_id': ..., 'label': ...}, ...]
    authors_list = [{'_id': ..., 'name': ...}, ...]"""
    cats_r = requests.get(
        f'{GHL_V2_BASE}/blogs/categories',
        params={'locationId': location_id, 'limit': 10, 'offset': 0},
        headers={'Authorization': f'Bearer {pit}', 'Version': GHL_V2_VERSION},
        timeout=15,
    )
    cats = cats_r.json().get('categories', []) if cats_r.status_code == 200 else []

    auth_r = requests.get(
        f'{GHL_V2_BASE}/blogs/authors',
        params={'locationId': location_id, 'limit': 10, 'offset': 0},
        headers={'Authorization': f'Bearer {pit}', 'Version': GHL_V2_VERSION},
        timeout=15,
    )
    authors = auth_r.json().get('authors', []) if auth_r.status_code == 200 else []
    return cats, authors


def match_categories(keywords, categories):
    """Match keyword list against GHL category labels. Returns list of matched category IDs."""
    label_map = {c.get('label', '').lower(): c['_id'] for c in categories}
    cat_ids = []
    for kw in keywords:
        cid = label_map.get(kw.lower())
        if cid:
            cat_ids.append(cid)
    return cat_ids


def find_author_id(author_name, authors):
    """Find GHL author ID by name (case-insensitive). Falls back to first author."""
    if not authors:
        return None
    name_lower = (author_name or '').lower().strip()
    if name_lower:
        for a in authors:
            if a.get('name', '').lower().strip() == name_lower:
                return a['_id']
    return authors[0]['_id']  # fallback to first author


def author_to_tag(author_name):
    """Slugify artist name for use as a tag (e.g. 'Guy Aitchison' → 'guy-aitchison')."""
    slug = re.sub(r'[^a-z0-9]+', '-', (author_name or '').lower().strip()).strip('-')
    return slug if slug else None


def extract_geo_tags(text):
    """Extract US state mentions from text for GEO tags. Returns up to 3 slugified state tags."""
    if not text:
        return []
    # Find word sequences (handles multi-word states like "New York")
    tokens = re.sub(r'<[^>]+>', ' ', text)  # strip HTML first
    tokens = re.sub(r'[^\w\s]', ' ', tokens)
    words = tokens.split()
    tags = []
    i = 0
    while i < len(words):
        # Try two-word match first (e.g. "New York")
        if i + 1 < len(words):
            two = (words[i] + ' ' + words[i + 1]).lower()
            if two in US_STATES:
                tags.append(two.replace(' ', '-'))
                i += 2
                continue
        one = words[i].lower()
        if one in US_STATES:
            tags.append(one)
        elif one in STATE_ABBREVS:
            tags.append(one)
        i += 1
    # Dedupe, preserve order, max 3
    seen = set()
    result = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= 3:
            break
    return result


def fetch_meta_from_airtable(domain):
    """Fetch GHL PIT and blogId from Airtable task Notes migrationMeta comment.
    Returns (pit, blog_id, error)."""
    try:
        url = f'https://api.airtable.com/v0/{AIRTABLE_BASE}/{AIRTABLE_TASKS_TABLE}'
        params = {
            'filterByFormula': f"FIND('{domain}', {{Task}})",
            'fields[]': ['Task', 'Notes'],
            'maxRecords': 5,
        }
        resp = requests.get(url, headers={'Authorization': f'Bearer {AIRTABLE_TOKEN}'}, params=params, timeout=15)
        if resp.status_code != 200:
            return None, None, f'Airtable error {resp.status_code}'
        records = resp.json().get('records', [])
        for rec in records:
            notes = rec.get('fields', {}).get('Notes', '')
            match = re.search(r'<!--\s*migrationMeta:\s*(\{.*?\})\s*-->', notes, re.DOTALL)
            if match:
                try:
                    meta = json.loads(match.group(1))
                    pit = meta.get('ghlPit') or meta.get('pit')
                    blog_id = meta.get('ghlBlogId') or meta.get('blogId')
                    if pit:
                        return pit, blog_id, None
                except json.JSONDecodeError:
                    pass
        return None, None, 'No PIT found in Airtable migrationMeta'
    except Exception as e:
        return None, None, str(e)[:200]


def fetch_pit_from_airtable(domain):
    """Compatibility wrapper — returns (pit, error)."""
    pit, _, error = fetch_meta_from_airtable(domain)
    return pit, error


def create_ghl_blog_post(location_id, post, pit, blog_id=None, category_ids=None, author_id=None, extra_tags=None):
    """Create a blog post in GHL via V2 Blogs API using PIT auth."""
    # Generate URL slug: slugified title + timestamp suffix for uniqueness
    slug_base = re.sub(r'[^a-z0-9]+', '-', post['title'].lower()).strip('-')[:60]
    url_slug = f"{slug_base}-{int(time.time()) % 100000}"

    payload = {
        'locationId': location_id,
        'title': post['title'],
        'rawHTML': post['content'][:50000],
        'status': 'PUBLISHED',
        'urlSlug': url_slug,
    }
    if blog_id:
        payload['blogId'] = blog_id
    if post.get('published'):
        payload['publishedAt'] = post['published']
    if post.get('imageUrl'):
        payload['imageUrl'] = post['imageUrl']
        payload['imageAltText'] = post['title']
    if post.get('description'):
        payload['description'] = post['description']
    if category_ids:
        payload['categories'] = category_ids
    if author_id:
        payload['author'] = author_id

    # Tags = artist name slug + GEO tags + any extra tags passed in
    tags = list(post.get('tags', []))
    if extra_tags:
        tags = list(dict.fromkeys(tags + extra_tags))  # merge, dedupe, preserve order
    if tags:
        payload['tags'] = [t for t in tags if t]  # filter empty strings

    resp = requests.post(
        f'{GHL_V2_BASE}/blogs/posts',
        json=payload,
        headers={
            'Authorization': f'Bearer {pit}',
            'Version': GHL_V2_VERSION,
            'Content-Type': 'application/json',
        },
        timeout=15,
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        return {'success': True, 'id': data.get('id') or data.get('_id')}

    return {
        'success': False,
        'http_status': resp.status_code,
        'error': resp.text[:300],
    }


def main():
    parser = argparse.ArgumentParser(description='Stage 3: Content Migration via RSS')
    parser.add_argument('--domain', required=True, help='Domain name')
    parser.add_argument('--location-id', help='GHL location ID (for blog creation)')
    parser.add_argument('--pit', help='GHL Private Integration Token (fetched from Airtable if not provided)')
    parser.add_argument('--dry-run', action='store_true', help='Fetch and parse RSS only, do not create posts')
    parser.add_argument('--skip-trigger', action='store_true', help='Skip RSS generation trigger')
    parser.add_argument('--test-content', metavar='DOMAIN', help='Use another domain\'s CRM content (e.g. darksidetattoo.com)')
    parser.add_argument('--limit', type=int, default=0, help='Max posts to create (0 = all)')
    parser.add_argument('--blog-id', help='GHL Blog site ID (fetched from Airtable migrationMeta if not provided)')
    parser.add_argument('--feed', choices=['news', 'tattoos', 'art', 'artists', 'readers_choice'], help='Which RSS feed to fetch (default: first available)')
    parser.add_argument('--tags', help='Extra tags appended to every post, comma-separated (e.g. "chicago,il")')
    args = parser.parse_args()

    domain = args.domain.lower().strip().replace('www.', '')
    result = {
        'domain': domain,
        'stage': 'content_migration',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'action': None,
        'success': False,
    }

    # Look up supertype — allow override via --test-content
    content_domain = domain
    if args.test_content:
        content_domain = args.test_content.lower().strip().replace('www.', '')
        result['test_content_source'] = content_domain

    supertype_id = SUPERTYPE_MAP.get(content_domain)
    if not supertype_id:
        result['action'] = 'skipped'
        result['reason'] = f'No CRM supertype for {content_domain} — no blog content to migrate'
        result['success'] = True
        print(json.dumps(result, indent=2))
        return

    result['supertype_id'] = supertype_id

    # Trigger RSS generation
    if not args.skip_trigger:
        trigger_result = trigger_rss_generation(supertype_id)
        result['rss_trigger'] = trigger_result
        if not trigger_result['success']:
            result['action'] = 'failed'
            result['error'] = 'RSS generation trigger failed'
            print(json.dumps(result, indent=2))
            return
        time.sleep(3)

    # Fetch RSS — use content_domain (may differ from target domain when --test-content is set)
    if args.feed:
        specific_url = f'https://www.{content_domain}/rss/{args.feed}.xml'
        try:
            r = requests.get(specific_url, timeout=15, allow_redirects=True,
                             headers={'User-Agent': 'TattooNOW-Migration-Bot/1.0'})
            if r.status_code == 200 and ('<?xml' in r.text[:100] or '<rss' in r.text[:200]):
                xml_text, feed_url = r.text, specific_url
            else:
                xml_text, feed_url = None, None
        except Exception:
            xml_text, feed_url = None, None
    else:
        xml_text, feed_url = fetch_rss_feed(content_domain, supertype_id)

    if not xml_text:
        result['action'] = 'no_feed'
        result['reason'] = 'No RSS feed found at any expected URL'
        result['success'] = True  # Not a failure — just no content
        print(json.dumps(result, indent=2))
        return

    result['feed_url'] = feed_url

    # Parse RSS
    posts, parse_error = parse_rss(xml_text)
    if parse_error:
        result['action'] = 'parse_error'
        result['error'] = parse_error
        print(json.dumps(result, indent=2))
        return

    result['posts_found'] = len(posts)

    if not posts:
        result['action'] = 'no_posts'
        result['reason'] = 'RSS feed parsed but contained no posts'
        result['success'] = True
        print(json.dumps(result, indent=2))
        return

    if args.dry_run:
        result['action'] = 'dry_run'
        result['success'] = True
        result['posts_preview'] = [
            {
                'title': p['title'],
                'published': p['published'],
                'content_length': len(p['content']),
                'has_image': bool(p.get('imageUrl')),
                'description_preview': p.get('description', '')[:80],
                'keywords': p.get('keywords', []),
                'author': p.get('author', ''),
            }
            for p in posts[:10]
        ]
        print(json.dumps(result, indent=2))
        return

    if not args.location_id:
        result['action'] = 'failed'
        result['error'] = '--location-id required for blog creation (not dry-run)'
        print(json.dumps(result, indent=2))
        return

    # Resolve PIT + blogId — flags first, then fetch from Airtable
    pit = args.pit
    blog_id = args.blog_id
    if not pit:
        pit, airtable_blog_id, pit_error = fetch_meta_from_airtable(domain)
        if not pit:
            result['action'] = 'pending_pit'
            result['reason'] = f'No PIT available: {pit_error}. Add ghlPit to Airtable migrationMeta for this domain, then re-run.'
            result['success'] = False
            print(json.dumps(result, indent=2))
            return
        result['pit_source'] = 'airtable'
        if not blog_id and airtable_blog_id:
            blog_id = airtable_blog_id
            result['blog_id_source'] = 'airtable'
    else:
        result['pit_source'] = 'flag'

    if blog_id:
        result['blog_id'] = blog_id
    else:
        result['blog_id_warning'] = 'No blogId provided — post may fail. Add ghlBlogId to Airtable migrationMeta or use --blog-id flag.'

    # Fetch location categories and authors once before the post loop
    categories, authors = fetch_location_blog_meta(args.location_id, pit)
    result['categories_found'] = len(categories)
    result['authors_found'] = len(authors)

    if not authors:
        # Fetch blogAuthorName from Airtable migrationMeta to include in the warning
        try:
            pit_check, blog_id_check, _ = fetch_meta_from_airtable(domain)
            # Re-fetch meta for blogAuthorName
            import re as _re2
            url = f'https://api.airtable.com/v0/{AIRTABLE_BASE}/{AIRTABLE_TASKS_TABLE}'
            params = {'filterByFormula': f"FIND('{domain}', {{Task}})", 'fields[]': ['Notes'], 'maxRecords': 5}
            resp = requests.get(url, headers={'Authorization': f'Bearer {AIRTABLE_TOKEN}'}, params=params, timeout=10)
            author_name_hint = ''
            if resp.status_code == 200:
                for rec in resp.json().get('records', []):
                    notes = rec.get('fields', {}).get('Notes', '')
                    m = _re2.search(r'<!--\s*migrationMeta:\s*(\{.*?\})\s*-->', notes, _re2.DOTALL)
                    if m:
                        try:
                            author_name_hint = json.loads(m.group(1)).get('blogAuthorName', '')
                        except Exception:
                            pass
        except Exception:
            author_name_hint = ''
        hint = f' Expected name: "{author_name_hint}".' if author_name_hint else ''
        result['author_warning'] = (
            f'No blog authors found in GHL for this location. '
            f'ACTION REQUIRED: Go to GHL → Sites → Blog → Authors → Add Author (name = location name).{hint} '
            f'Then re-run to assign author to posts.'
        )

    # Parse extra tags from --tags flag
    extra_geo_tags = [t.strip() for t in (args.tags or '').split(',') if t.strip()]

    # Create blog posts in GHL via V2 API
    posts_to_create = posts[:args.limit] if args.limit > 0 else posts
    if args.limit > 0:
        result['limit'] = args.limit
    created = 0
    failed = 0
    errors = []

    for post in posts_to_create:
        # Match RSS keywords → category IDs
        cat_ids = match_categories(post.get('keywords', []), categories)

        # Find author by name, fallback to first
        author_id = find_author_id(post.get('author', ''), authors)

        # Build tags: artist name slug + GEO from description + extra geo tags
        post_tags = []
        artist_tag = author_to_tag(post.get('author', ''))
        if artist_tag:
            post_tags.append(artist_tag)
        geo_tags = extract_geo_tags(post.get('description', '') + ' ' + post.get('content', '')[:500])
        post_tags.extend(geo_tags)
        post['tags'] = list(dict.fromkeys(post_tags))  # dedupe, preserve order

        blog_result = create_ghl_blog_post(
            args.location_id, post, pit, blog_id,
            category_ids=cat_ids if cat_ids else None,
            author_id=author_id,
            extra_tags=extra_geo_tags if extra_geo_tags else None,
        )
        if blog_result['success']:
            created += 1
        else:
            failed += 1
            if len(errors) < 5:
                errors.append({'title': post['title'], 'error': blog_result.get('error', 'unknown')})
        # Rate limit respect
        time.sleep(0.5)

    result['action'] = 'migrated'
    result['posts_created'] = created
    result['posts_failed'] = failed
    result['success'] = failed == 0
    if errors:
        result['errors'] = errors

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
