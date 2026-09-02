"""Peak API client for solving Cloudflare Turnstile and the 5s interstitial.

The whole Peak HTTP call is isolated in :meth:`PeakClient._post` so tests can
monkeypatch a single method and never touch the network. ``requests`` is used
for the call because it is already a hard dependency of this package (a
cloudscraper drop-in always has it).
"""

from __future__ import annotations

from typing import Optional

import requests

DEFAULT_API_URL = "https://api.peak.fo/solve"

# task_type sent to Peak for the interactive Turnstile widget challenge.
TASK_TURNSTILE = "turnstiletask"
# task_type for the non-interactive "Just a moment..." 5s interstitial.
TASK_CLOUDFLARE_5S = "cloudflare5stask"


class PeakError(RuntimeError):
    """Raised when Peak cannot solve the challenge or the call fails."""


def build_turnstile_payload(
    sitekey: str,
    url: str,
    proxy: Optional[str] = None,
    cdata: Optional[str] = None,
    action: Optional[str] = None,
    pagedata: Optional[str] = None,
) -> dict:
    """Build the JSON body for a Turnstile solve.

    ``proxy`` and the optional ``cData`` / ``action`` / ``pagedata`` fields are
    omitted entirely when not provided, per the Peak contract.
    """
    payload = {
        "task_type": TASK_TURNSTILE,
        "sitekey": sitekey,
        "url": url,
    }
    if proxy:
        payload["proxy"] = proxy
    if cdata:
        payload["cdata"] = cdata
    if action:
        payload["action"] = action
    if pagedata:
        payload["pagedata"] = pagedata
    return payload


def build_cloudflare5s_payload(url: str, proxy: Optional[str] = None) -> dict:
    """Build the JSON body for a 5s interstitial solve (no sitekey)."""
    payload = {
        "task_type": TASK_CLOUDFLARE_5S,
        "url": url,
    }
    if proxy:
        payload["proxy"] = proxy
    return payload


class PeakClient:
    """Thin client around the Peak solve endpoint."""

    def __init__(
        self,
        api_key: str,
        api_url: str = DEFAULT_API_URL,
        proxy: Optional[str] = None,
        timeout: float = 180.0,
    ) -> None:
        if not api_key:
            raise PeakError(
                "No Peak API key. Pass api_key=... , captcha={'provider':'peak',"
                " 'api_key':...}, or set PEAK_API_KEY. Get a free key at "
                "https://peak.fo."
            )
        self.api_key = api_key
        self.api_url = api_url
        self.proxy = proxy
        self.timeout = timeout

    def _post(self, payload: dict) -> dict:
        """Send the payload to Peak and return the parsed JSON response.

        Isolated so tests can monkeypatch exactly one method instead of the
        network transport.
        """
        try:
            resp = requests.post(
                self.api_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:  # pragma: no cover - network
            raise PeakError(f"Peak request failed: {exc}") from exc
        try:
            return resp.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise PeakError(
                f"Peak returned non-JSON response: {resp.text!r}"
            ) from exc

    def _check(self, result: dict) -> dict:
        if not result.get("success"):
            raise PeakError(result.get("error") or "Peak solve failed")
        data = result.get("data")
        if not data:
            raise PeakError("Peak response missing data")
        return data

    def solve_turnstile(
        self,
        sitekey: str,
        url: str,
        proxy: Optional[str] = None,
        cdata: Optional[str] = None,
        action: Optional[str] = None,
        pagedata: Optional[str] = None,
    ) -> str:
        """Solve a Turnstile challenge and return the token string.

        Raises :class:`PeakError` on failure.
        """
        payload = build_turnstile_payload(
            sitekey,
            url,
            proxy=proxy or self.proxy,
            cdata=cdata,
            action=action,
            pagedata=pagedata,
        )
        data = self._check(self._post(payload))
        token = data.get("token")
        if not token:
            raise PeakError("Peak response missing data.token")
        return token

    def solve_cloudflare5s(
        self, url: str, proxy: Optional[str] = None
    ) -> dict:
        """Solve the 5s interstitial.

        Returns the full ``data`` dict from Peak, which carries a ``cookies``
        map (with ``cf_clearance``) and optionally ``headers`` / ``user_agent``
        to reuse on the crawl session.
        """
        payload = build_cloudflare5s_payload(url, proxy=proxy or self.proxy)
        return self._check(self._post(payload))
