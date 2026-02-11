import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import argparse
import re

SITEMAP_FILE = "target.com.au-stores-sitemap.xml.xml"
verbose = False

def extract_urls_from_sitemap(filepath):
    """Extract store URLs from the sitemap XML file."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        # Handle the namespace
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [elem.text for elem in root.findall('.//ns:loc', namespace)]
        return urls
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

def main():
    """Main function to extract store info from sitemap URLs and output as JSON."""
    global verbose

    parser = argparse.ArgumentParser(description='Extract Target store details from sitemap URLs.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    args = parser.parse_args()
    verbose = args.verbose

    if not Path(SITEMAP_FILE).exists():
        print(f"Error: Sitemap file '{SITEMAP_FILE}' not found.", file=sys.stderr)
        sys.exit(1)

    urls = extract_urls_from_sitemap(SITEMAP_FILE)

    if verbose:
        print(f"Found {len(urls)} stores in sitemap", file=sys.stderr)

    all_stores = []
    errors = []

    for i, url in enumerate(urls, 1):
        store_data = extract_store_info_from_url(url)
        if store_data:
            all_stores.append(store_data)
            if verbose:
                print(f"  [{i}/{len(urls)}] {store_data.get('storeName', 'Unknown')} ({store_data.get('state', 'N/A')})", file=sys.stderr)
        else:
            errors.append((i, url))
            if verbose:
                print(f"  [{i}/{len(urls)}] Failed to extract", file=sys.stderr)

    print(f"\nExtracted {len(all_stores)} stores", file=sys.stderr)
    if errors:
        print(f"Failed to extract {len(errors)} stores:", file=sys.stderr)
        for idx, url in errors:
            print(f"  [{idx}] {url}", file=sys.stderr)

    # Sort by store code
    all_stores_sorted = sorted(all_stores, key=lambda x: x.get('storeCode', ''))
    print(json.dumps(all_stores_sorted, indent=2))

if __name__ == "__main__":
    main()
