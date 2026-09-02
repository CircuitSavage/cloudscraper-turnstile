"""Basic usage: solve Cloudflare Turnstile transparently.

Set your key first (get a free one at https://peak.fo):

    export PEAK_API_KEY=pk_your_api_key      # Windows: setx PEAK_API_KEY pk_your_api_key

Then run:

    python examples/basic.py
"""

import os

import cloudscraper_turnstile as cloudscraper

API_KEY = os.environ.get("PEAK_API_KEY", "pk_your_api_key")


def main():
    # create_scraper mirrors cloudscraper's signature. The key can also come
    # from the PEAK_API_KEY env var, so create_scraper() alone is enough.
    scraper = cloudscraper.create_scraper(api_key=API_KEY)

    # Use it exactly like a requests.Session. If the page is a Cloudflare
    # Turnstile or 5s challenge, it is solved through Peak and retried; you
    # get the final real response back.
    resp = scraper.get("https://protected.example.com/")
    print("status:", resp.status_code)
    print("bytes:", len(resp.content))

    # Cookies (including any cf_clearance obtained during the solve) persist
    # on the session for every later request.
    resp2 = scraper.get("https://protected.example.com/account")
    print("second request status:", resp2.status_code)


if __name__ == "__main__":
    main()
