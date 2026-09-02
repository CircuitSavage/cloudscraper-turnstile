"""Cloudflare challenge detection and field extraction.

Pure functions, no requests/session dependency, so they are cheap to test.
Handles both the interactive Turnstile widget and the non-interactive 5s
"Just a moment..." interstitial.
"""

from __future__ import annotations

import re
from typing import Optional

# Markers that a response is a Cloudflare challenge page rather than real
# content. Split so we can tell a Turnstile widget apart from the 5s page.
_TURNSTILE_MARKERS = (
    "cf-turnstile",
    "challenges.cloudflare.com/turnstile",
    "turnstile.render",
    "data-sitekey",
)
_INTERSTITIAL_MARKERS = (
    "just a moment",
    "cf_chl_opt",
    "window._cf_chl_opt",
    "__cf_chl",
    "/cdn-cgi/challenge-platform",
    "cf-challenge-running",
)

# Statuses Cloudflare typically serves a challenge on. Not required (the body
# marker decides), but used to raise confidence.
CHALLENGE_STATUSES = frozenset({403, 429, 503})

# data-sitekey="0x4AAAAA..."  (the widget div attribute)
_SITEKEY_ATTR = re.compile(r"""data-sitekey\s*=\s*["']([^"']+)["']""", re.I)
# turnstile.render('#el', { sitekey: '0x4AAAAA...' })  or  sitekey: "0x..."
_SITEKEY_JS = re.compile(r"""(?:sitekey|render)\s*[:=]\s*["']([^"']+)["']""", re.I)
# data-cdata="..." / cData: "..."
_CDATA = re.compile(r"""(?:data-cdata|cdata|cData)\s*[:=]\s*["']([^"']+)["']""", re.I)
# data-action="..." / action: "..."
_ACTION = re.compile(r"""(?:data-action|action)\s*[:=]\s*["']([^"']+)["']""", re.I)
# data-pagedata / chlPageData
_PAGEDATA = re.compile(
    r"""(?:data-pagedata|pagedata|chlPageData)\s*[:=]\s*["']([^"']+)["']""", re.I
)


def is_turnstile_challenge(body_text: str, status: Optional[int] = None) -> bool:
    """Return True if the response looks like a Turnstile widget challenge."""
    if not body_text:
        return False
    lowered = body_text.lower()
    return any(marker in lowered for marker in _TURNSTILE_MARKERS)


def is_interstitial_challenge(body_text: str, status: Optional[int] = None) -> bool:
    """Return True if the response looks like the 5s "Just a moment" page."""
    if not body_text:
        return False
    lowered = body_text.lower()
    return any(marker in lowered for marker in _INTERSTITIAL_MARKERS)


def is_cloudflare_challenge(body_text: str, status: Optional[int] = None) -> bool:
    """Return True for either a Turnstile widget or the 5s interstitial."""
    return is_turnstile_challenge(body_text, status) or is_interstitial_challenge(
        body_text, status
    )


def extract_sitekey(body_text: str) -> Optional[str]:
    """Pull the Turnstile sitekey out of a challenge page, or None."""
    if not body_text:
        return None
    match = _SITEKEY_ATTR.search(body_text)
    if match:
        return match.group(1).strip()
    match = _SITEKEY_JS.search(body_text)
    if match:
        candidate = match.group(1).strip()
        # Turnstile sitekeys start with 0x (1x for the test keys); guard
        # against matching unrelated JS keys named "sitekey".
        if candidate.startswith(("0x", "1x", "2x", "3x")):
            return candidate
    return None


def _first(pattern: "re.Pattern[str]", body_text: str) -> Optional[str]:
    match = pattern.search(body_text)
    return match.group(1).strip() if match else None


def extract_turnstile_fields(body_text: str) -> dict:
    """Return {sitekey, cdata, action, pagedata} scraped from the page.

    Keys are omitted when absent so the result can be splatted into the Peak
    payload builder.
    """
    if not body_text:
        return {}
    fields = {}
    sitekey = extract_sitekey(body_text)
    if sitekey:
        fields["sitekey"] = sitekey
    cdata = _first(_CDATA, body_text)
    if cdata:
        fields["cdata"] = cdata
    action = _first(_ACTION, body_text)
    if action:
        fields["action"] = action
    pagedata = _first(_PAGEDATA, body_text)
    if pagedata:
        fields["pagedata"] = pagedata
    return fields
