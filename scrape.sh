#!/bin/bash
set -e

# download.sh names its output after the URL plus an extension sniffed from the
# response MIME type, and this endpoint flip-flops between XML and JSON. Clear
# previous downloads first so a format change replaces the sitemap rather than
# leaving a stale copy beside the new one for extract_stores.py to pick up.
rm -f target.com.au-stores-sitemap.xml.*

./download.sh 'https://www.target.com.au/stores-sitemap.xml'
