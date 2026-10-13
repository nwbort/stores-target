# Target store locations (Australia)

Regularly updated store list for Target Australia.

`stores.json` lists every store in Target's stores sitemap with its state, name,
store code and URL, plus details scraped from each store page: street address,
suburb, postcode, phone, latitude/longitude and trading hours for this week and
next.

The sitemap is checked daily, but store pages are only fetched for stores that
are new to the sitemap or whose details are a week old (`detailsFetched` records
when each store was last fetched). Stores that drop out of the sitemap are
removed. If a store page can't be fetched, that store keeps its previous details
and is retried the next day. A few stores don't publish hours, so their
`tradingHours` is empty.

Run `python extract_stores.py --max-age-days 0` to refetch every store now.
