import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
import argparse
from datetime import date, datetime, timezone

# download.sh names the file after the URL plus an extension sniffed from the
# response's MIME type, so the suffix changes if the site switches format.
SITEMAP_GLOB = "target.com.au-stores-sitemap.xml.*"
DEFAULT_OUTPUT = "stores.json"
REQUEST_DELAY = 1.0  # seconds between store page fetches, to stay polite
MAX_AGE_DAYS = 7  # refetch a store's page once its details are this old
# If at least this many pages were attempted and all failed, we're blocked or
# the layout changed. Fewer than this (e.g. one brand-new store whose page
# isn't live yet) only warns, so it doesn't hold up the daily sitemap commit.
BLOCKED_THRESHOLD = 5
verbose = False

# Fields filled in from the store page, as opposed to parsed from the URL.
DETAIL_FIELDS = ('address', 'suburb', 'postcode', 'phone', 'latitude', 'longitude', 'tradingHours')

def find_sitemap_file():
    """Locate the downloaded sitemap, whatever extension download.sh gave it."""
    matches = sorted(Path('.').glob(SITEMAP_GLOB))

    if not matches:
        print(f"Error: no sitemap file matching '{SITEMAP_GLOB}' found.", file=sys.stderr)
        sys.exit(1)

    # More than one means a stale download from a previous format is lingering,
    # and we can't tell which is current. Fail loudly rather than parse the wrong
    # one and publish stale data under a green build.
    if len(matches) > 1:
        print(f"Error: multiple sitemap files match '{SITEMAP_GLOB}':", file=sys.stderr)
        for path in matches:
            print(f"  {path}", file=sys.stderr)
        print("Delete the stale one(s) so only the current download remains.", file=sys.stderr)
        sys.exit(1)

    return matches[0]

def extract_urls_from_sitemap(filepath):
    """Extract store URLs from the sitemap, which may be XML or JSON."""
    try:
        text = Path(filepath).read_text().lstrip()

        if text.startswith('{'):
            # JSON form: {"urls": [{"location": "...", ...}, ...]}
            data = json.loads(text)
            return [entry['location'] for entry in data['urls']]

        # XML sitemap form, with the usual sitemaps.org namespace
        root = ET.fromstring(text)
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        return [elem.text for elem in root.findall('.//ns:loc', namespace)]
    except Exception as e:
        print(f"Error parsing sitemap: {e}", file=sys.stderr)
        return []

def extract_store_info_from_url(url):
    """Extract store information directly from the sitemap URL.

    URL format: https://www.target.com.au/store/{state}/{store-name}/{store-code}
    Example: https://www.target.com.au/store/act/belconnen/5123
    """
    # Pattern to match the URL structure
    pattern = r'https://www\.target\.com\.au/store/([^/]+)/([^/]+)/(\d+)$'
    match = re.match(pattern, url)

    if not match:
        if verbose:
            print(f"Warning: Could not parse URL: {url}", file=sys.stderr)
        return None

    state = match.group(1).upper()
    store_name = match.group(2).replace('-', ' ').title()
    store_code = match.group(3)

    store_data = {
        'state': state,
        'storeName': store_name,
        'storeCode': store_code,
        'url': url
    }

    return store_data

def fetch_page(url):
    """Fetch a store page with curl, the same way download.sh fetches the sitemap.

    The site has blocked Python's urllib from GitHub Actions before, while curl
    with these headers gets through, so stick with what demonstrably works.
    """
    result = subprocess.run(
        ['curl', '-s', '-L', '--fail', '--compressed', '--max-time', '30',
         '--retry', '3', '--retry-delay', '2', '--retry-all-errors',
         '-A', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
         '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
         '-H', 'Accept-Language: en-AU,en;q=0.9',
         url],
        capture_output=True,
    )
    if result.returncode != 0:
        if verbose:
            print(f"    curl exited {result.returncode} for {url}", file=sys.stderr)
        return None
    return result.stdout.decode('utf-8', errors='replace')

def clean(html):
    """Strip tags and entities, and collapse whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', unescape(text)).strip()

def search(pattern, text):
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else None

def parse_store_page(html):
    """Pull address, phone, coordinates and trading hours out of a store page.

    Returns None if the page doesn't look like a store page (e.g. a block or
    error page), so the caller can fall back to previously scraped details.
    """
    card = search(r'(<div class="store-contact-card".*?</address>)', html)
    if not card:
        return None

    # The street address may span several lines separated by <br />
    street_html = search(r'<span itemprop="streetAddress">(.*?)</span>', card) or ''
    street_lines = [clean(line) for line in re.split(r'<br\s*/?>', street_html)]
    address = ', '.join(line for line in street_lines if line)

    suburb = search(r'<span itemprop="addressLocality">(.*?)</span>', card)
    postcode = search(r'<span itemprop="postalCode">(.*?)</span>', card)
    phone = search(r'<span itemprop="telephone">(.*?)</span>', html)
    latitude = search(r'data-lat="([^"]+)"', html)
    longitude = search(r'data-lng="([^"]+)"', html)

    # The page shows this week and next, each headed by its date range
    trading_hours = []
    for title, days_html in re.findall(
            r'<h5 class="title">(.*?)</h5>\s*<dl[^>]*>(.*?)</dl>', html, re.DOTALL):
        hours = {clean(day): clean(time_range)
                 for day, time_range in re.findall(r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', days_html, re.DOTALL)}
        trading_hours.append({'week': clean(title), 'hours': hours})

    return {
        'address': address or None,
        'suburb': clean(suburb) if suburb else None,
        'postcode': clean(postcode) if postcode else None,
        'phone': clean(phone) if phone else None,
        'latitude': float(latitude) if latitude else None,
        'longitude': float(longitude) if longitude else None,
        'tradingHours': trading_hours,
    }

def load_previous(path):
    """Load the last published stores, keyed by store code, for fallback."""
    try:
        stores = json.loads(Path(path).read_text())
        return {store['storeCode']: store for store in stores}
    except (OSError, ValueError, KeyError, TypeError):
        return {}

def is_fresh(store, today, max_age_days):
    """Whether a previously scraped store's details are recent enough to reuse."""
    try:
        fetched_on = date.fromisoformat(store['detailsFetched'])
    except (KeyError, TypeError, ValueError):
        return False  # new store, or never successfully fetched
    return (today - fetched_on).days < max_age_days

def warn(message):
    """Print a warning, as an annotation when running under GitHub Actions."""
    prefix = '::warning::' if os.environ.get('GITHUB_ACTIONS') else 'Warning: '
    print(f"{prefix}{message}", file=sys.stderr)

def main():
    """Extract store info from the sitemap and each store page, and write JSON."""
    global verbose

    parser = argparse.ArgumentParser(description='Extract Target store details from the sitemap and store pages.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT,
                        help=f'File to write (default: {DEFAULT_OUTPUT}). Its current contents '
                             'supply fallback details for any store page that fails to load.')
    parser.add_argument('--no-details', action='store_true',
                        help="Only parse the sitemap URLs; don't fetch store pages")
    parser.add_argument('--max-age-days', type=int, default=MAX_AGE_DAYS,
                        help='Refetch a store page once its details are at least this many days old '
                             f'(default: {MAX_AGE_DAYS}; 0 refetches every store). New stores are always fetched.')
    args = parser.parse_args()
    verbose = args.verbose

    sitemap_file = find_sitemap_file()

    urls = extract_urls_from_sitemap(sitemap_file)

    if verbose:
        print(f"Found {len(urls)} stores in {sitemap_file}", file=sys.stderr)

    previous = load_previous(args.output)
    today = datetime.now(timezone.utc).date()
    all_stores = []
    errors = []
    fetched = 0
    fetch_failures = []

    for i, url in enumerate(urls, 1):
        store_data = extract_store_info_from_url(url)
        if not store_data:
            errors.append((i, url))
            if verbose:
                print(f"  [{i}/{len(urls)}] Failed to extract", file=sys.stderr)
            continue

        if not args.no_details:
            old = previous.get(store_data['storeCode'], {})
            if is_fresh(old, today, args.max_age_days):
                details = {field: old.get(field) for field in DETAIL_FIELDS + ('detailsFetched',)}
            else:
                if fetched or fetch_failures:
                    time.sleep(REQUEST_DELAY)
                html = fetch_page(url)
                details = parse_store_page(html) if html else None
                if details is None:
                    fetch_failures.append(url)
                    # Keep last run's details rather than publishing a blank
                    # store. The old fetch date stays, so it's retried tomorrow.
                    details = {field: old.get(field) for field in DETAIL_FIELDS + ('detailsFetched',)}
                else:
                    fetched += 1
                    details['detailsFetched'] = today.isoformat()
            store_data.update(details)

        all_stores.append(store_data)
        if verbose:
            print(f"  [{i}/{len(urls)}] {store_data['storeName']} ({store_data['state']})", file=sys.stderr)

    print(f"\nExtracted {len(all_stores)} stores from {sitemap_file}", file=sys.stderr)

    # A sitemap that yields nothing means the download or the format changed
    # again. Exit non-zero so the workflow goes red instead of overwriting
    # the output with an empty list.
    if not all_stores:
        print("Error: no stores extracted from the sitemap.", file=sys.stderr)
        sys.exit(1)

    if errors:
        print(f"Failed to extract {len(errors)} stores:", file=sys.stderr)
        for idx, url in errors:
            print(f"  [{idx}] {url}", file=sys.stderr)

    if not args.no_details:
        print(f"Fetched details for {fetched} stores; "
              f"{len(all_stores) - fetched - len(fetch_failures)} were up to date.", file=sys.stderr)

    # Every page failing means we're blocked or the page layout changed. Go red
    # so someone notices, and leave the output untouched.
    if not fetched and len(fetch_failures) >= BLOCKED_THRESHOLD:
        print("Error: no store page could be fetched and parsed; "
              "the site may be blocking us or its layout changed.", file=sys.stderr)
        sys.exit(1)

    if fetch_failures:
        warn(f"Could not fetch details for {len(fetch_failures)} of {len(all_stores)} stores; "
             "kept their previous details.")
        for url in fetch_failures:
            print(f"  {url}", file=sys.stderr)

    # Sort by store code
    all_stores_sorted = sorted(all_stores, key=lambda x: x.get('storeCode', ''))
    Path(args.output).write_text(json.dumps(all_stores_sorted, indent=2, ensure_ascii=False) + '\n')
    print(f"Wrote {args.output}", file=sys.stderr)

if __name__ == "__main__":
    main()
