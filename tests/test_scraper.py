"""Tests for cloudscraper-turnstile.

No network and no live Peak key: the Peak client's single HTTP method
(``PeakClient._post``) is monkeypatched, and ``requests.Session.request`` (the
transport the CloudScraper calls via ``super().request``) is replaced with a
scripted fake that returns a challenge first and the real page on retry.

Run with:

    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import cloudscraper_turnstile as cloudscraper
from cloudscraper_turnstile import (
    CloudScraper,
    PeakClient,
    create_scraper,
    resolve_api_key,
)
from cloudscraper_turnstile.detect import (
    extract_sitekey,
    extract_turnstile_fields,
    is_interstitial_challenge,
    is_turnstile_challenge,
)
from cloudscraper_turnstile.peak import build_turnstile_payload

TARGET_URL = "https://protected.example.com/checkout"
SITEKEY = "0x4AAAAAAABkMYinukE8nzYS"
TEST_TOKEN = "XXXX.TEST"
CLEAR_TOKEN = "CLEAR.TEST"

TURNSTILE_HTML = f"""
<!doctype html><html><head><title>Just a moment...</title></head>
<body>
  <form class="challenge-form" id="challenge-form"
        action="/cdn-cgi/challenge-platform/verify" method="POST">
    <input type="hidden" name="md" value="abc123">
    <div class="cf-turnstile" data-sitekey="{SITEKEY}" data-callback="onSolve"></div>
  </form>
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
</body></html>
"""

INTERSTITIAL_HTML = """
<!doctype html><html><head><title>Just a moment...</title></head>
<body>
  <div id="cf-challenge-running"></div>
  <script>window._cf_chl_opt = {cvId: '3', cType: 'managed'};</script>
  <div id="challenge-stage"></div>
</body></html>
"""

REAL_HTML = "<html><body><h1>Welcome to the shop</h1></body></html>"


class FakeResponse:
    """Enough of requests.Response for the CloudScraper logic."""

    def __init__(self, url, status, text):
        self.url = url
        self.status_code = status
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {}


def scripted_transport(*responses):
    """Return a callable standing in for requests.Session.request that yields
    the given responses in order and records each call's (method, url, kwargs)."""
    seq = iter(responses)
    calls = []

    def _request(self, method, url, *args, **kwargs):
        calls.append((method, url, kwargs))
        try:
            return next(seq)
        except StopIteration:
            return responses[-1]

    _request.calls = calls
    return _request


TURNSTILE_OK = {"success": True, "data": {"token": TEST_TOKEN}}
FIVES_OK = {
    "success": True,
    "data": {
        "cookies": {"cf_clearance": CLEAR_TOKEN},
        "user_agent": "Mozilla/5.0 (peak-test)",
        "headers": {"X-Peak": "1"},
    },
}


# ---------------------------------------------------------------------------
# (a) create_scraper returns a requests.Session subclass
# ---------------------------------------------------------------------------
class ConstructionTests(unittest.TestCase):
    def test_returns_requests_session_subclass(self):
        scraper = create_scraper()
        self.assertIsInstance(scraper, requests.Session)
        self.assertIsInstance(scraper, CloudScraper)

    def test_module_is_import_compatible(self):
        # import cloudscraper_turnstile as cloudscraper; cloudscraper.create_scraper()
        self.assertTrue(hasattr(cloudscraper, "create_scraper"))
        self.assertIsInstance(cloudscraper.create_scraper(), requests.Session)

    def test_standard_session_api_present(self):
        scraper = create_scraper(api_key="pk_test")
        for name in ("get", "post", "request", "cookies", "headers"):
            self.assertTrue(hasattr(scraper, name))


# ---------------------------------------------------------------------------
# API-key resolution and precedence (e)
# ---------------------------------------------------------------------------
class ApiKeyResolutionTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("PEAK_API_KEY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["PEAK_API_KEY"] = self._saved
        else:
            os.environ.pop("PEAK_API_KEY", None)

    def test_explicit_api_key(self):
        self.assertEqual(resolve_api_key(api_key="pk_explicit"), "pk_explicit")

    def test_captcha_provider_dict(self):
        cap = {"provider": "peak", "api_key": "pk_from_captcha"}
        self.assertEqual(resolve_api_key(captcha=cap), "pk_from_captcha")

    def test_env_fallback(self):
        os.environ["PEAK_API_KEY"] = "pk_from_env"
        self.assertEqual(resolve_api_key(), "pk_from_env")

    def test_precedence_explicit_over_captcha_over_env(self):
        os.environ["PEAK_API_KEY"] = "pk_env"
        cap = {"provider": "peak", "api_key": "pk_cap"}
        self.assertEqual(resolve_api_key("pk_exp", cap), "pk_exp")
        self.assertEqual(resolve_api_key(None, cap), "pk_cap")
        self.assertEqual(resolve_api_key(None, None), "pk_env")

    def test_create_scraper_honors_captcha_dict(self):
        scraper = create_scraper(captcha={"provider": "peak", "api_key": "pk_cap"})
        self.assertEqual(scraper.peak_api_key, "pk_cap")


# ---------------------------------------------------------------------------
# (g) unknown cloudscraper kwargs must not raise
# ---------------------------------------------------------------------------
class DropInKwargsTests(unittest.TestCase):
    def test_cloudscraper_kwargs_accepted(self):
        scraper = create_scraper(
            api_key="pk_test",
            browser="chrome",
            delay=10,
            interpreter="nodejs",
            debug=True,
            allow_brotli=True,
            captcha={"provider": "peak", "api_key": "pk_test"},
            some_future_kwarg="whatever",
        )
        self.assertIsInstance(scraper, CloudScraper)
        self.assertEqual(scraper.cloudscraper_kwargs.get("allow_brotli"), True)

    def test_sess_state_adopted(self):
        base = requests.Session()
        base.headers.update({"X-From-Base": "yes"})
        base.cookies.set("session", "cookieval")
        scraper = create_scraper(api_key="pk_test", sess=base)
        self.assertEqual(scraper.headers.get("X-From-Base"), "yes")
        self.assertEqual(scraper.cookies.get("session"), "cookieval")


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------
class DetectionTests(unittest.TestCase):
    def test_detects_turnstile(self):
        self.assertTrue(is_turnstile_challenge(TURNSTILE_HTML, 403))

    def test_detects_interstitial(self):
        self.assertTrue(is_interstitial_challenge(INTERSTITIAL_HTML, 503))

    def test_ignores_real_page(self):
        self.assertFalse(is_turnstile_challenge(REAL_HTML, 200))
        self.assertFalse(is_interstitial_challenge(REAL_HTML, 200))

    def test_extract_sitekey(self):
        self.assertEqual(extract_sitekey(TURNSTILE_HTML), SITEKEY)

    def test_extract_fields(self):
        fields = extract_turnstile_fields(TURNSTILE_HTML)
        self.assertEqual(fields["sitekey"], SITEKEY)


# ---------------------------------------------------------------------------
# Peak payload
# ---------------------------------------------------------------------------
class PayloadTests(unittest.TestCase):
    def test_turnstile_payload_shape(self):
        payload = build_turnstile_payload(SITEKEY, TARGET_URL)
        self.assertEqual(payload["task_type"], "turnstiletask")
        self.assertEqual(payload["sitekey"], SITEKEY)
        self.assertEqual(payload["url"], TARGET_URL)
        self.assertNotIn("proxy", payload)

    def test_turnstile_payload_proxy(self):
        payload = build_turnstile_payload(SITEKEY, TARGET_URL, proxy="http://p:1")
        self.assertEqual(payload["proxy"], "http://p:1")


# ---------------------------------------------------------------------------
# (b) pass-through, (c) Turnstile solve+retry, (d) 5s path,
# (f) proxy forwarding, (h) max_solve_attempts
# ---------------------------------------------------------------------------
class RequestFlowTests(unittest.TestCase):
    def _scraper(self, **kwargs):
        kwargs.setdefault("api_key", "pk_test")
        return create_scraper(**kwargs)

    def test_non_challenge_passes_through(self):
        transport = scripted_transport(FakeResponse(TARGET_URL, 200, REAL_HTML))
        with mock.patch.object(requests.Session, "request", transport):
            with mock.patch.object(PeakClient, "_post") as mock_post:
                scraper = self._scraper()
                resp = scraper.get(TARGET_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Welcome", resp.text)
        self.assertFalse(mock_post.called)
        self.assertEqual(len(transport.calls), 1)

    def test_turnstile_solve_and_retry(self):
        transport = scripted_transport(
            FakeResponse(TARGET_URL, 403, TURNSTILE_HTML),
            FakeResponse(TARGET_URL, 200, REAL_HTML),
        )
        with mock.patch.object(requests.Session, "request", transport):
            with mock.patch.object(
                PeakClient, "_post", return_value=TURNSTILE_OK
            ) as mock_post:
                scraper = self._scraper()
                resp = scraper.get(TARGET_URL)

        # (c) Peak was called with the correct Turnstile body.
        self.assertTrue(mock_post.called)
        payload = mock_post.call_args[0][0]
        self.assertEqual(payload["task_type"], "turnstiletask")
        self.assertEqual(payload["sitekey"], SITEKEY)
        self.assertEqual(payload["url"], TARGET_URL)

        # The retry submitted the token as the cf-turnstile-response field.
        _, submit_url, submit_kwargs = transport.calls[1]
        self.assertIn("challenge-platform/verify", submit_url)
        self.assertEqual(submit_kwargs["data"]["cf-turnstile-response"], TEST_TOKEN)
        self.assertEqual(submit_kwargs["data"]["md"], "abc123")

        # And the final response is the real page.
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Welcome", resp.text)

    def test_interstitial_5s_sets_clearance_and_rerequests(self):
        transport = scripted_transport(
            FakeResponse(TARGET_URL, 503, INTERSTITIAL_HTML),
            FakeResponse(TARGET_URL, 200, REAL_HTML),
        )
        with mock.patch.object(requests.Session, "request", transport):
            with mock.patch.object(
                PeakClient, "_post", return_value=FIVES_OK
            ) as mock_post:
                scraper = self._scraper()
                resp = scraper.get(TARGET_URL)

        # (d) Peak was called with the 5s task_type (no sitekey).
        payload = mock_post.call_args[0][0]
        self.assertEqual(payload["task_type"], "cloudflare5stask")
        self.assertNotIn("sitekey", payload)

        # cf_clearance cookie + returned UA are now on the session.
        self.assertEqual(scraper.cookies.get("cf_clearance"), CLEAR_TOKEN)
        self.assertEqual(scraper.headers.get("User-Agent"), "Mozilla/5.0 (peak-test)")

        # Re-requested the original URL and returned the real page.
        self.assertEqual(transport.calls[1][1], TARGET_URL)
        self.assertIn("Welcome", resp.text)

    def test_proxy_forwarded_to_peak(self):
        transport = scripted_transport(
            FakeResponse(TARGET_URL, 403, TURNSTILE_HTML),
            FakeResponse(TARGET_URL, 200, REAL_HTML),
        )
        proxy = "http://user:pass@10.0.0.1:8080"
        with mock.patch.object(requests.Session, "request", transport):
            with mock.patch.object(
                PeakClient, "_post", return_value=TURNSTILE_OK
            ) as mock_post:
                scraper = self._scraper(proxy=proxy)
                scraper.get(TARGET_URL)
        payload = mock_post.call_args[0][0]
        self.assertEqual(payload["proxy"], proxy)

    def test_session_proxy_used_when_not_explicit(self):
        transport = scripted_transport(
            FakeResponse(TARGET_URL, 403, TURNSTILE_HTML),
            FakeResponse(TARGET_URL, 200, REAL_HTML),
        )
        with mock.patch.object(requests.Session, "request", transport):
            with mock.patch.object(
                PeakClient, "_post", return_value=TURNSTILE_OK
            ) as mock_post:
                scraper = self._scraper()
                scraper.proxies.update({"https": "http://session-proxy:3128"})
                scraper.get(TARGET_URL)
        payload = mock_post.call_args[0][0]
        self.assertEqual(payload["proxy"], "http://session-proxy:3128")

    def test_max_solve_attempts_stops_loops(self):
        # Every response is a challenge; the solver must give up after N tries.
        transport = scripted_transport(FakeResponse(TARGET_URL, 403, TURNSTILE_HTML))
        with mock.patch.object(requests.Session, "request", transport):
            with mock.patch.object(
                PeakClient, "_post", return_value=TURNSTILE_OK
            ) as mock_post:
                scraper = self._scraper(max_solve_attempts=2)
                resp = scraper.get(TARGET_URL)
        # 2 solve attempts, no infinite loop.
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
