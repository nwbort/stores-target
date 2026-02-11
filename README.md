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
- `--limit N` - Process only first N stores (useful for testing)

## Requirements

- Python 3.x
- `requests` library (>=2.31.0)
- `urllib3` library (>=2.0.0)

Install dependencies:
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install requests urllib3
```

## Troubleshooting

### Testing the Script

Before running a full scrape, test with a limited number of stores:

```bash
python extract_stores.py --limit 5 -v > test.json
```

This will process only the first 5 stores with verbose output, helping you identify issues quickly.

### 403 Forbidden Errors

If you're getting 403 errors, there are two main causes:

#### 1. Proxy Restrictions

This script requires direct internet access to `www.target.com.au`. If you're running it in an environment with a corporate proxy or restricted network that doesn't whitelist `target.com.au`, you'll encounter errors like:

```
ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))
```

**Solution**: Run from an environment that either:
- Has no proxy configured, OR
- Has a proxy that allows access to `target.com.au`

Check for proxy issues:
```bash
python extract_stores.py --check-proxy
```

#### 2. Bot Detection / Rate Limiting

Target.com.au may be detecting automated requests and blocking them. This can happen if:
- Requests are too frequent (the script has 1.5s delays to mitigate this)
- The IP address is flagged (GitHub Actions IPs, VPN IPs, datacenter IPs)
- Multiple scrapes run in short succession

**What the script does to avoid this:**
- Establishes a session by visiting the main site first (gets cookies)
- Uses realistic browser headers (Chrome 120 on Windows)
- Includes Sec-Fetch-* headers that real browsers send
- Delays 1.5 seconds between requests
- Reuses the same session/connection

**If you still get 403 errors:**
1. Try running from a residential IP address (not datacenter/VPN/GitHub)
2. Increase the delay between requests (edit line 250: `time.sleep(1.5)` → `time.sleep(3)`)
3. Test with `--limit 5` first to verify it works at all
4. Wait some time (hours/days) before retrying if you've been rate-limited
5. Consider using a headless browser solution (Selenium/Playwright) for full browser emulation

## Script Features

- Automatically extracts store URLs from sitemap XML
- Parses store details including name, phone, address, coordinates, and trading hours
- **Session establishment**: Visits main site first to obtain cookies (mimics real browser)
- **Advanced retry logic** with exponential backoff for transient failures
- **Modern browser headers** including Sec-Fetch-* headers to avoid bot detection
- **Rate limiting**: 1.5 second delay between requests to be respectful
- **Connection pooling**: Reuses connections for better performance
- **Automatic retry strategy** for server errors (429, 500, 502, 503, 504)
- **Testing mode**: Use `--limit` flag to test with subset of stores first

## Output Format

The script outputs a JSON array of store objects with details like locationId, publicName, phoneNumber, address, coordinates, and tradingHours.
