import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import time
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
        namespace = {'ns': 'https://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [elem.text for elem in root.findall('.//ns:loc', namespace)]
        return urls
    except Exception as e:
        print(f"Error parsing sitemap: {e}", file=sys.stderr)
        return []

def get_store_details(url):
    """Fetch a Target store page and extract details from the HTML."""
    try:
        if verbose:
            print(f"Fetching: {url}", file=sys.stderr)
        
        with urlopen(url, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')

        # Helper function to extract text using a regular expression
        def extract_text(pattern, text, group=1, clean=True):
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                return None
            result = match.group(group).strip()
            if clean:
                # Clean HTML tags and consolidate whitespace
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
            address1 = extract_text(r'.*', street_address_html, clean=True) if street_address_html else None
            
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

        # Assume the locationId is the number at the end of the URL
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
            'typename': 'Location',  # Updated typename
            'url': url
        }
        
        return store_data
        
    except (URLError, HTTPError) as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error processing {url}: {e}", file=sys.stderr)
        return None

def main():
    """Main function to scrape all stores and output as JSON."""
    global verbose
    
    parser = argparse.ArgumentParser(description='Extract Target store details from sitemap.')
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
        store_data = get_store_details(url)
        if store_data:
            all_stores.append(store_data)
            if verbose:
                print(f"  [{i}/{len(urls)}] {store_data.get('publicName', 'Unknown')}", file=sys.stderr)
        else:
            errors.append((i, url))
            if verbose:
                print(f"  [{i}/{len(urls)}] Failed to extract", file=sys.stderr)
        
        # Be polite to the server
        time.sleep(0.1)
    
    # Print summary
    print(f"Extracted {len(all_stores)} stores", file=sys.stderr)
    if errors:
        print(f"Failed to extract {len(errors)} stores:", file=sys.stderr)
        for idx, url in errors:
            print(f"  [{idx}] {url}", file=sys.stderr)
    
    all_stores_sorted = sorted(all_stores, key=lambda x: x.get('locationId', ''))
    print(json.dumps(all_stores_sorted, indent=2))

if __name__ == "__main__":
    main()
