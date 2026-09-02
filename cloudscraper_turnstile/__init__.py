"""cloudscraper-turnstile: a cloudscraper drop-in that solves Cloudflare
Turnstile and the 5s interstitial through the Peak API.

Swap two lines and existing code keeps working::

    import cloudscraper_turnstile as cloudscraper

    scraper = cloudscraper.create_scraper(api_key="pk_your_api_key")
    r = scraper.get("https://protected.example.com/")
    print(r.status_code, r.text)
"""

from __future__ import annotations

from .detect import (
    extract_sitekey,
    extract_turnstile_fields,
    is_cloudflare_challenge,
    is_interstitial_challenge,
    is_turnstile_challenge,
)
from .peak import (
    PeakClient,
    PeakError,
    build_cloudflare5s_payload,
    build_turnstile_payload,
)
from .scraper import CloudScraper, create_scraper, resolve_api_key

__version__ = "0.1.0"

__all__ = [
    "create_scraper",
    "CloudScraper",
    "resolve_api_key",
    "PeakClient",
    "PeakError",
    "build_turnstile_payload",
    "build_cloudflare5s_payload",
    "is_cloudflare_challenge",
    "is_turnstile_challenge",
    "is_interstitial_challenge",
    "extract_sitekey",
    "extract_turnstile_fields",
    "__version__",
]
