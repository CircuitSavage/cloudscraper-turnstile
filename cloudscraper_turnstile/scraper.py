"""Drop-in cloudscraper replacement that actually solves Turnstile.

``CloudScraper`` subclasses :class:`requests.Session`, so ``.get`` / ``.post`` /
``.request`` / ``.cookies`` / ``.headers`` all behave exactly like the real
cloudscraper object. The only added behaviour is in :meth:`CloudScraper.request`:
if a response is a Cloudflare challenge (Turnstile widget or the 5s
interstitial), it is solved through the Peak API and the request is retried
transparently, returning the final real :class:`requests.Response`.
"""

from __future__ import annotations

import os
import re
from typing import Optional
from urllib.parse import urljoin

import requests

from . import detect
from .peak import PeakClient, PeakError

__all__ = [
    "CloudScraper",
    "create_scraper",
    "resolve_api_key",
    "PeakError",
]

# Cloudflare challenge forms carry these hidden fields; we resubmit the form
# with the solved token added as cf-turnstile-response.
_FORM_RE = re.compile(r"<form[^>]*>(.*?)</form>", re.IGNORECASE | re.DOTALL)
_FORM_TAG_RE = re.compile(r"<form([^>]*)>", re.IGNORECASE)
_ACTION_RE = re.compile(r"""action\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_METHOD_RE = re.compile(r"""method\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_INPUT_RE = re.compile(r"<input\b([^>]*)>", re.IGNORECASE)
_NAME_RE = re.compile(r"""name\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_VALUE_RE = re.compile(r"""value\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


def resolve_api_key(api_key=None, captcha=None) -> Optional[str]:
    """Resolve the Peak API key. Precedence: explicit > captcha dict > env.

    Accepts cloudscraper's own captcha-provider style,
    ``captcha={'provider': 'peak', 'api_key': 'pk_...'}``, so migration is a
    no-op for users who already configured a captcha provider.
    """
    if api_key:
        return api_key
    if isinstance(captcha, dict):
        key = captcha.get("api_key") or captcha.get("key") or captcha.get("apikey")
        if key:
            return key
    return os.environ.get("PEAK_API_KEY")


def _parse_challenge_form(html: str, page_url: str):
    """Return (action_url, method, data) for the first form on the page.

    Falls back to a POST back to ``page_url`` with no hidden fields when the
    page has no parseable form.
    """
    action_url, method, data = page_url, "POST", {}
    form = _FORM_RE.search(html or "")
    if form:
        tag = _FORM_TAG_RE.search(html[: form.start() + 200])
        attrs = tag.group(1) if tag else ""
        m_action = _ACTION_RE.search(attrs)
        if m_action and m_action.group(1):
            action_url = urljoin(page_url, m_action.group(1))
        m_method = _METHOD_RE.search(attrs)
        if m_method and m_method.group(1):
            method = m_method.group(1).upper()
        for inp in _INPUT_RE.finditer(form.group(1)):
            body = inp.group(1)
            m_name = _NAME_RE.search(body)
            if not m_name:
                continue
            m_value = _VALUE_RE.search(body)
            data[m_name.group(1)] = m_value.group(1) if m_value else ""
    return action_url, method, data


class CloudScraper(requests.Session):
    """A ``requests.Session`` that solves Cloudflare challenges via Peak."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        proxy: Optional[str] = None,
        max_solve_attempts: int = 3,
        debug: bool = False,
        peak_client: Optional[PeakClient] = None,
        **kwargs,
    ) -> None:
        # requests.Session.__init__ takes no arguments; swallow every extra
        # cloudscraper kwarg (browser, delay, interpreter, allow_brotli, ...)
        # so existing create_scraper(...) calls keep working unchanged.
        super().__init__()
        self.peak_api_key = api_key
        self.peak_proxy = proxy
        self.max_solve_attempts = max_solve_attempts
        self.debug = debug
        self._peak_client = peak_client
        # Kept only for introspection / drop-in parity; not otherwise used.
        self.cloudscraper_kwargs = dict(kwargs)

    # -- Peak plumbing ----------------------------------------------------

    def _get_peak(self) -> PeakClient:
        """Build the Peak client lazily so a scraper can exist without a key
        until a challenge actually needs solving."""
        if self._peak_client is None:
            self._peak_client = PeakClient(
                api_key=self.peak_api_key, proxy=self._peak_proxy()
            )
        return self._peak_client

    def _peak_proxy(self) -> Optional[str]:
        """The proxy string forwarded to Peak so the solve matches the crawl
        IP. Explicit ``proxy`` wins; otherwise the session's configured proxy."""
        if self.peak_proxy:
            return self.peak_proxy
        proxies = getattr(self, "proxies", None) or {}
        return proxies.get("https") or proxies.get("http") or None

    def _log(self, message: str) -> None:
        if self.debug:
            print(f"[cloudscraper-turnstile] {message}")

    # -- Challenge handling ----------------------------------------------

    def _is_challenge(self, response) -> bool:
        text = response.text or ""
        status = response.status_code
        if detect.is_interstitial_challenge(text, status):
            return True
        # A Turnstile widget on a normal 200 page is a real login form, not a
        # block; only treat it as a challenge on a challenge status.
        if detect.is_turnstile_challenge(text, status) and (
            status in detect.CHALLENGE_STATUSES
        ):
            return True
        return False

    def request(self, method, url, *args, **kwargs):  # type: ignore[override]
        """Perform the request; solve and retry on a Cloudflare challenge."""
        response = super().request(method, url, *args, **kwargs)
        attempts = 0
        while attempts < self.max_solve_attempts and self._is_challenge(response):
            attempts += 1
            self._log(
                f"challenge detected (status {response.status_code}), "
                f"solve attempt {attempts}/{self.max_solve_attempts}"
            )
            solved = self._solve_and_retry(method, url, response, kwargs)
            if solved is None:
                break
            response = solved
        return response

    def _solve_and_retry(self, method, url, response, kwargs):
        text = response.text or ""
        proxy = self._peak_proxy()
        fields = detect.extract_turnstile_fields(text)
        if detect.is_turnstile_challenge(text) and fields.get("sitekey"):
            token = self._get_peak().solve_turnstile(
                sitekey=fields["sitekey"],
                url=url,
                proxy=proxy,
                cdata=fields.get("cdata"),
                action=fields.get("action"),
                pagedata=fields.get("pagedata"),
            )
            self._log("turnstile token received, resubmitting challenge form")
            return self._submit_turnstile(url, text, token)
        # No Turnstile sitekey => the 5s interstitial path.
        data = self._get_peak().solve_cloudflare5s(url, proxy=proxy)
        self._log("5s clearance received, applying cookies and re-requesting")
        self._apply_clearance(data)
        return super().request(method, url, **kwargs)

    def _submit_turnstile(self, page_url, html, token):
        """Inject the token as cf-turnstile-response and resubmit the form."""
        action_url, form_method, data = _parse_challenge_form(html, page_url)
        data["cf-turnstile-response"] = token
        # Some Cloudflare forms read the token under the g-recaptcha field too.
        data.setdefault("g-recaptcha-response", token)
        if form_method == "GET":
            return super().request("GET", action_url, params=data)
        return super().request("POST", action_url, data=data)

    def _apply_clearance(self, data: dict) -> None:
        """Persist cf_clearance cookies (and any returned headers / UA) so the
        re-request and every later request carry them."""
        cookies = data.get("cookies") or {}
        for name, value in cookies.items():
            self.cookies.set(name, value)
        clearance = data.get("cf_clearance")
        if clearance:
            self.cookies.set("cf_clearance", clearance)
        headers = data.get("headers") or {}
        if headers:
            self.headers.update(headers)
        user_agent = data.get("user_agent") or data.get("userAgent")
        if user_agent:
            self.headers["User-Agent"] = user_agent


def create_scraper(
    sess=None,
    api_key=None,
    proxy=None,
    captcha=None,
    browser=None,
    delay=None,
    interpreter=None,
    debug=False,
    max_solve_attempts=3,
    **kwargs,
):
    """Create a :class:`CloudScraper`, mirroring ``cloudscraper.create_scraper``.

    All of cloudscraper's real kwargs are accepted (``browser``, ``delay``,
    ``interpreter``, ``captcha``, ``sess``, ``allow_brotli`` via ``**kwargs``)
    and unknown kwargs never raise, so this is a true drop-in.

    The Peak API key is resolved with precedence
    explicit ``api_key`` > ``captcha`` dict > ``PEAK_API_KEY`` env.
    """
    resolved_key = resolve_api_key(api_key, captcha)
    scraper = CloudScraper(
        api_key=resolved_key,
        proxy=proxy,
        max_solve_attempts=max_solve_attempts,
        debug=debug,
        browser=browser,
        delay=delay,
        interpreter=interpreter,
        **kwargs,
    )
    if sess is not None:
        _adopt_session(scraper, sess)
    return scraper


def _adopt_session(scraper: CloudScraper, sess) -> None:
    """Carry state over from an existing requests.Session, like cloudscraper."""
    for attr in ("headers", "proxies", "params", "cookies"):
        value = getattr(sess, attr, None)
        if value:
            getattr(scraper, attr).update(value)
    for attr in ("auth", "cert", "verify", "trust_env", "max_redirects"):
        value = getattr(sess, attr, None)
        if value is not None:
            setattr(scraper, attr, value)
