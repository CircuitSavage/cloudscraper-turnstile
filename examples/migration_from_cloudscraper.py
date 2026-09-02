"""Migration from cloudscraper: change the import, keep everything else.

Set your key first (free at https://peak.fo):

    export PEAK_API_KEY=pk_your_api_key

Then run:

    python examples/migration_from_cloudscraper.py
"""

import os

# ---------------------------------------------------------------------------
# BEFORE (plain cloudscraper): returns 403 / a "Just a moment..." page on any
# site protected by Turnstile or the managed 5s challenge, because cloudscraper
# has no JS engine and only ever solved the legacy IUAM math challenge.
#
#     import cloudscraper
#     scraper = cloudscraper.create_scraper()
#     resp = scraper.get("https://protected.example.com/")
#
# ---------------------------------------------------------------------------
# AFTER: one import line changes. Same create_scraper, same requests.Session
# API, same calling code. Turnstile and the 5s challenge now actually solve.
# ---------------------------------------------------------------------------

import cloudscraper_turnstile as cloudscraper  # <-- the only change

API_KEY = os.environ.get("PEAK_API_KEY", "pk_your_api_key")


def main():
    # If you already used cloudscraper's captcha-provider style, it keeps
    # working too:
    #   scraper = cloudscraper.create_scraper(
    #       captcha={"provider": "peak", "api_key": API_KEY})
    scraper = cloudscraper.create_scraper(api_key=API_KEY)

    # Existing cloudscraper kwargs (browser, delay, interpreter, ...) are
    # accepted and ignored where not applicable, so nothing else has to change:
    #   scraper = cloudscraper.create_scraper(
    #       browser="chrome", delay=10, api_key=API_KEY)

    resp = scraper.get("https://protected.example.com/")
    print("status:", resp.status_code)
    print(resp.text[:500])


if __name__ == "__main__":
    main()
