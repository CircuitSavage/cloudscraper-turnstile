# Testing

The suite uses only the Python standard library (`unittest` + `unittest.mock`).
It requires **no live Peak key and no network**:

- The Peak client's single HTTP method (`PeakClient._post`) is monkeypatched to
  return `{"success": true, "data": {"token": "XXXX.TEST"}}` for Turnstile and a
  `{"success": true, "data": {"cookies": {"cf_clearance": "CLEAR.TEST"}, ...}}`
  shape for the 5s task.
- `requests.Session.request` (the transport the `CloudScraper` calls via
  `super().request`) is replaced with a scripted fake that returns a challenge
  first and the real page on retry.

The only real dependency is `requests` (a hard dependency of the package, since
a cloudscraper drop-in always has it):

```bash
pip install requests
```

## What is asserted

`tests/test_scraper.py` covers the full drop-in contract:

- **(a) Type contract** - `create_scraper()` returns a `requests.Session`
  subclass (`CloudScraper`); `import cloudscraper_turnstile as cloudscraper` then
  `cloudscraper.create_scraper()` works; `.get/.post/.request/.cookies/.headers`
  are present.
- **(b) Pass-through** - a non-challenge 200 response is returned unchanged and
  Peak is never called.
- **(c) Turnstile solve + retry** - a 403 Turnstile page triggers a Peak call
  with the correct body (`task_type=turnstiletask`, extracted `sitekey`, `url`),
  the token is injected as the `cf-turnstile-response` form field, the challenge
  form is resubmitted, and the final real page is returned.
- **(d) 5s interstitial** - a 503 "Just a moment" page triggers a
  `cloudflare5stask` call (no sitekey), the returned `cf_clearance` cookie and
  user-agent are set on the session, and the original URL is re-requested.
- **(e) API-key precedence** - explicit `api_key=` > `captcha={'provider':'peak',
  'api_key':...}` > `PEAK_API_KEY` env, each honored.
- **(f) Proxy forwarding** - an explicit `proxy=` and, failing that, the
  session's configured proxy are forwarded to Peak so the solve matches the
  crawl IP.
- **(g) Drop-in kwargs** - unknown cloudscraper kwargs (`browser`, `delay`,
  `interpreter`, `allow_brotli`, future kwargs) do not raise; `sess=` state is
  adopted.
- **(h) Loop guard** - when every response is a challenge, the solver stops
  after `max_solve_attempts` instead of looping forever.

## Run

```bash
cd cloudscraper-turnstile
pip install requests
python -m unittest discover -s tests -v
```

Python used: 3.12

## Observed output (PASS)

```
test_captcha_provider_dict (test_scraper.ApiKeyResolutionTests.test_captcha_provider_dict) ... ok
test_create_scraper_honors_captcha_dict (test_scraper.ApiKeyResolutionTests.test_create_scraper_honors_captcha_dict) ... ok
test_env_fallback (test_scraper.ApiKeyResolutionTests.test_env_fallback) ... ok
test_explicit_api_key (test_scraper.ApiKeyResolutionTests.test_explicit_api_key) ... ok
test_precedence_explicit_over_captcha_over_env (test_scraper.ApiKeyResolutionTests.test_precedence_explicit_over_captcha_over_env) ... ok
test_module_is_import_compatible (test_scraper.ConstructionTests.test_module_is_import_compatible) ... ok
test_returns_requests_session_subclass (test_scraper.ConstructionTests.test_returns_requests_session_subclass) ... ok
test_standard_session_api_present (test_scraper.ConstructionTests.test_standard_session_api_present) ... ok
test_detects_interstitial (test_scraper.DetectionTests.test_detects_interstitial) ... ok
test_detects_turnstile (test_scraper.DetectionTests.test_detects_turnstile) ... ok
test_extract_fields (test_scraper.DetectionTests.test_extract_fields) ... ok
test_extract_sitekey (test_scraper.DetectionTests.test_extract_sitekey) ... ok
test_ignores_real_page (test_scraper.DetectionTests.test_ignores_real_page) ... ok
test_cloudscraper_kwargs_accepted (test_scraper.DropInKwargsTests.test_cloudscraper_kwargs_accepted) ... ok
test_sess_state_adopted (test_scraper.DropInKwargsTests.test_sess_state_adopted) ... ok
test_turnstile_payload_proxy (test_scraper.PayloadTests.test_turnstile_payload_proxy) ... ok
test_turnstile_payload_shape (test_scraper.PayloadTests.test_turnstile_payload_shape) ... ok
test_interstitial_5s_sets_clearance_and_rerequests (test_scraper.RequestFlowTests.test_interstitial_5s_sets_clearance_and_rerequests) ... ok
test_max_solve_attempts_stops_loops (test_scraper.RequestFlowTests.test_max_solve_attempts_stops_loops) ... ok
test_non_challenge_passes_through (test_scraper.RequestFlowTests.test_non_challenge_passes_through) ... ok
test_proxy_forwarded_to_peak (test_scraper.RequestFlowTests.test_proxy_forwarded_to_peak) ... ok
test_session_proxy_used_when_not_explicit (test_scraper.RequestFlowTests.test_session_proxy_used_when_not_explicit) ... ok
test_turnstile_solve_and_retry (test_scraper.RequestFlowTests.test_turnstile_solve_and_retry) ... ok

----------------------------------------------------------------------
Ran 23 tests in 0.003s

OK
```
