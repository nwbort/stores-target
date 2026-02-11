import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import time
import argparse
import re
import urllib.request
from urllib.error import URLError, HTTPError
import gzip

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

def get_store_details(url, max_retries=3):
    """Fetch a Target store page and extract details from the HTML."""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-AU,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.target.com.au/',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }

    html = None

    for attempt in range(max_retries):
        try:
            if verbose:
                retry_msg = f" (attempt {attempt + 1}/{max_retries})" if attempt > 0 else ""
                print(f"Fetching: {url}{retry_msg}", file=sys.stderr)

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
                if response.info().get('Content-Encoding') == 'gzip':
                    data = gzip.decompress(data)
                html = data.decode('utf-8', errors='ignore')
                break

        except HTTPError as e:
            if e.code == 403:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    if verbose:
                        print(f"  Got 403, waiting {wait_time}s before retry...", file=sys.stderr)
                    time.sleep(wait_time)
                else:
                    print(f"Error fetching {url}: HTTP {e.code}", file=sys.stderr)
                    return None
            else:
                print(f"Error fetching {url}: HTTP {e.code}", file=sys.stderr)
                return None
        except URLError as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                return None
    
    # If HTML was not fetched, return None
    if not html:
        return None

    try:
        # Helper function to extract text using a regular expression
        def extract_text(pattern, text, group=1, clean=True):
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                return None
            result = match.group(group).strip()
            if clean:
                result = re.sub('<[^<]+?>', '', result).strip()
                result = re.sub(r'\s+', ' ', result)
            return result

        # Extract core details
        public_name = extract_text(r'<h4 class="store-heading".*?>Target – (.*?)</h4>', html)
        phone_number = extract_text(r'<span itemprop="telephone">(.*?)</span>', html)
        latitude = extract_text(r'data-lat="([^"]+)"', html)
        longitude = extract_text(r'data-lng="([^"]+)"', html)
        
        # Extract the entire address block to search within it
        address_block_html = extract_text(r'<address itemprop="address".*?>(.*?)</address>', html, clean=False)
        
        address1, city, state, postcode = None, None, None, None
        if address_block_html:
            # The street address can contain other tags like <strong> and <br>
            street_address_html = extract_text(r'<span itemprop="streetAddress">(.*?)</span>', address_block_html, clean=False)
            address1 = extract_text(r'(.*)', street_address_html, clean=True) if street_address_html else None
            city = extract_text(r'<span itemprop="addressLocality">(.*?)</span>', address_block_html)
            state = extract_text(r'<span itemprop="addressRegion">(.*?)</span>', address_block_html)
            postcode = extract_text(r'<span itemprop="postalCode">(.*?)</span>', address_block_html)
        
        # Extract trading hours into the desired object format
        trading_hours_list = []
        hours_block_html = extract_text(r'<div class="store-hours">(.*?)</div>', html, clean=False)
        if hours_block_html:
            # Find all <dt> (day) and <dd> (hours) pairs
            hour_pairs = re.findall(r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', hours_block_html, re.DOTALL)
            for day, hours in hour_pairs:
                trading_hours_list.append({
                    "__typename": "TradingHour",
                    "hours": hours.strip(),
                    "weekDay": day.strip().upper()
                })

        location_id_match = re.search(r'/(\d+)$', url)
        location_id = location_id_match.group(1) if location_id_match else None

        if not public_name:
            return None
        
        store_data = {
            'locationId': location_id,
            'publicName': public_name,
            'phoneNumber': phone_number,
            'address1': address1,
            'address2': None,
            'address3': None,
            'city': city,
            'state': state,
            'postcode': postcode,
            'latitude': float(latitude) if latitude else None,
            'longitude': float(longitude) if longitude else None,
            'tradingHours': trading_hours_list,
            'typename': 'Location',
            'url': url
        }
        
        return store_data
    except Exception as e:
        print(f"Error processing {url}: {e}", file=sys.stderr)
        return None

def check_proxy_configuration():
    """Check if proxy is configured and warn about potential issues."""
    import os
    proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'GLOBAL_AGENT_HTTP_PROXY', 'GLOBAL_AGENT_HTTPS_PROXY']
    active_proxies = {var: os.environ.get(var) for var in proxy_vars if os.environ.get(var)}

    if active_proxies:
        print("WARNING: Proxy detected in environment. This may cause 403 errors if target.com.au is not whitelisted.", file=sys.stderr)
        if verbose:
            for var, value in active_proxies.items():
                proxy_display = value[:80] + '...' if len(value) > 80 else value
                print(f"  {var}: {proxy_display}", file=sys.stderr)
        print("  To bypass proxy issues, run this script from an environment without proxy restrictions.\n", file=sys.stderr)

def main():
    """Main function to scrape all stores and output as JSON."""
    global verbose

    parser = argparse.ArgumentParser(description='Extract Target store details from sitemap.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--check-proxy', action='store_true', help='Check proxy configuration and exit')
    args = parser.parse_args()
    verbose = args.verbose

    if args.check_proxy:
        check_proxy_configuration()
        return
    
    if not Path(SITEMAP_FILE).exists():
        print(f"Error: Sitemap file '{SITEMAP_FILE}' not found.", file=sys.stderr)
        sys.exit(1)

    # Check for proxy configuration that might cause issues
    check_proxy_configuration()

    urls = extract_urls_from_sitemap(SITEMAP_FILE)

    if verbose:
        print(f"Found {len(urls)} stores in sitemap", file=sys.stderr)

    all_stores = []
    errors = []

    for i, url in enumerate(urls, 1):
        store_data = get_store_details(url)
        if store_data:
            all_stores.append(store_data)
            if verbose:
                print(f"  [{i}/{len(urls)}] {store_data.get('publicName', 'Unknown')}", file=sys.stderr)
        else:
            errors.append((i, url))
            if verbose:
                print(f"  [{i}/{len(urls)}] Failed to extract", file=sys.stderr)

        # Add delay between requests to avoid rate limiting
        if i < len(urls):
            time.sleep(0.5)
    
    print(f"\nExtracted {len(all_stores)} stores", file=sys.stderr)
    if errors:
        print(f"Failed to extract {len(errors)} stores:", file=sys.stderr)
        for idx, url in errors:
            print(f"  [{idx}] {url}", file=sys.stderr)
    
    all_stores_sorted = sorted(all_stores, key=lambda x: x.get('locationId', ''))
    print(json.dumps(all_stores_sorted, indent=2))

if __name__ == "__main__":
    main()
