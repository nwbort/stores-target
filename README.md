# Target store locations (Australia)

Regularly updated store list for Target Australia.

## Files

- `extract_stores.py` - Main scraper script
- `target.com.au-stores-sitemap.xml.xml` - Sitemap containing all store URLs
- `stores.json` - Output file with extracted store data

## Usage

```bash
python extract_stores.py > stores.json
```

Options:
- `-v, --verbose` - Enable verbose output to see progress
- `--check-proxy` - Check proxy configuration and exit

## Requirements

- Python 3.x
- `requests` library

Install dependencies:
```bash
pip install requests
```

## Known Issues: Proxy Restrictions

### Problem

This script requires direct internet access to `www.target.com.au`. If you're running it in an environment with a corporate proxy or restricted network that doesn't whitelist `target.com.au`, you'll encounter errors like:

```
ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))
```

or

```
HTTP Error 403: Forbidden
```

### Solution

Run the script from an environment that either:

1. Has no proxy configured, OR
2. Has a proxy that allows access to `target.com.au`

To check if you have proxy issues:
```bash
python extract_stores.py --check-proxy
```

### Running Without Proxy Restrictions

If you're in a restricted environment, you may need to:

1. Run the script from your local machine instead
2. Use a different network with unrestricted internet access
3. Request that `target.com.au` and `*.target.com.au` be added to your proxy's whitelist

## Script Features

- Automatically extracts store URLs from sitemap XML
- Parses store details including name, phone, address, coordinates, and trading hours
- Includes retry logic with exponential backoff for transient failures
- Modern browser headers to avoid bot detection
- Rate limiting (0.5s delay between requests)
- Session management for efficient connection pooling

## Output Format

The script outputs a JSON array of store objects with details like locationId, publicName, phoneNumber, address, coordinates, and tradingHours.
