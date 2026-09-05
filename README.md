<a href="https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cloudscraper-turnstile">
  <img src="https://raw.githubusercontent.com/CircuitSavage/cloudscraper-turnstile/main/assets/peak-banner.png" alt="Peak — solve Cloudflare Turnstile & the 5s challenge in ~1s" width="100%">
</a>

# cloudscraper-turnstile

**cloudscraper-turnstile** is a drop-in replacement for [cloudscraper](https://github.com/VeNoMouS/cloudscraper) that actually solves Cloudflare Turnstile and the 5s "Just a moment..." interstitial. It subclasses `requests.Session` exactly like cloudscraper does, so you change one import line and your existing scraper keeps working, except now the requests that used to return `403` come back with the real page.

```python
import cloudscraper_turnstile as cloudscraper

scraper = cloudscraper.create_scraper(api_key="pk_your_api_key")
resp = scraper.get("https://protected.example.com/")   # Turnstile solved, real page returned
```

## Why cloudscraper can't do this anymore

cloudscraper is a good tool for the challenge it was built for, but that challenge is mostly gone:

- **It only ever solved the legacy IUAM challenge.** cloudscraper works by reading Cloudflare's old "I'm Under Attack Mode" page, extracting the JavaScript math problem, and evaluating it. That is the entire mechanism.
- **It has no JS engine and no browser.** Modern Cloudflare managed challenges and Turnstile run real, obfuscated browser JavaScript and collect behavioral and fingerprint signals. There is nothing in the page for a regex-and-eval tool to solve, so the request stays on the challenge page and you get a `403`, a `503`, or an endless "Just a moment..." loop.
- **Its own "Turnstile support" is a hand-off.** cloudscraper never solved Turnstile itself. It added hooks to pass the challenge to a third-party paid CAPTCHA API and inject the returned token. Without one of those API keys configured, Turnstile support does nothing.
- **The project is effectively unmaintained.** Its last real release was in 2023. Cloudflare has shipped many detection changes since.

So on any site that switched to Turnstile or the managed 5s challenge (most of them, by now), plain cloudscraper returns the challenge HTML instead of your data. This package fills exactly that gap: it keeps cloudscraper's `create_scraper` / `requests.Session` shape and does the one thing cloudscraper cannot, by sending the challenge to a solver that runs a real browser.

## Powered by Peak

This package uses [Peak](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cloudscraper-turnstile) to solve Turnstile and the 5s challenge.

- Solve Cloudflare Turnstile & the 5s challenge in about a second
- Pay only for successful solves, from $1 / 1,000
- 1,000 free solves to start, no card.

→ [Get your free API key](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cloudscraper-turnstile) · [Docs](https://peak.fo/docs/turnstile?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cloudscraper-turnstile) · [Pricing](https://peak.fo/pricing?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cloudscraper-turnstile)

## Install

```bash
pip install cloudscraper-turnstile
```

The only dependency is `requests` (you already have it if you used cloudscraper).

## Migration guide

There is no rewrite. cloudscraper-turnstile mirrors cloudscraper's public API: `create_scraper(...)` returns a `CloudScraper` object that subclasses `requests.Session`, so `.get`, `.post`, `.request`, `.cookies`, and `.headers` all behave the same.

**Before**

```python
import cloudscraper

scraper = cloudscraper.create_scraper()
resp = scraper.get("https://protected.example.com/")   # 403 / "Just a moment..." on Turnstile sites
```

**After**

```python
import cloudscraper_turnstile as cloudscraper   # the only line that changes

scraper = cloudscraper.create_scraper()                # reads PEAK_API_KEY from env
resp = scraper.get("https://protected.example.com/")   # Turnstile solved, real page returned
```

If you were already using cloudscraper's captcha-provider style, that keeps working too, so migration is a no-op:

```python
scraper = cloudscraper.create_scraper(
    captcha={"provider": "peak", "api_key": "pk_your_api_key"},
)
```

Existing cloudscraper kwargs (`browser`, `delay`, `interpreter`, `allow_brotli`, `sess`, ...) are accepted and never raise, so you do not have to touch the rest of your `create_scraper` call.

## Quickstart

```bash
pip install cloudscraper-turnstile requests
export PEAK_API_KEY=pk_your_api_key      # Windows: setx PEAK_API_KEY pk_your_api_key
```

```python
import os
import cloudscraper_turnstile as cloudscraper

scraper = cloudscraper.create_scraper(api_key=os.environ["PEAK_API_KEY"])

# Use it exactly like requests / cloudscraper. A Turnstile or 5s challenge is
# detected, solved through Peak, and the request is retried transparently.
resp = scraper.get("https://protected.example.com/")
print(resp.status_code)   # 200
print(resp.text)          # the real page, not the challenge

# Cookies obtained during the solve (including cf_clearance) persist on the
# session for every later request.
resp2 = scraper.post(
    "https://protected.example.com/api/search",
    json={"q": "widgets"},
)
```

### Where the key comes from

The API key is resolved in this order:

1. Explicit `create_scraper(api_key="pk_...")`
2. `create_scraper(captcha={"provider": "peak", "api_key": "pk_..."})`
3. `PEAK_API_KEY` environment variable

### Using a proxy

Pass a proxy and it is forwarded to Peak, so the solve happens from the same IP as your crawl (this matters, since Cloudflare ties clearance to the requesting IP):

```python
scraper = cloudscraper.create_scraper(
    api_key="pk_your_api_key",
    proxy="http://user:pass@ip:port",
)
```

If you set `scraper.proxies` the requests way instead, that proxy is used for the solve automatically.

### Earn with your app ID

Pass your Peak app id and you earn 5% of every solve this tool makes, paid as solve credit. The `app_id` is optional and only changes who is credited, never whether or how fast a challenge is solved. Create one at [peak.fo/dashboard/developer](https://peak.fo/dashboard/developer); details at [peak.fo/earn](https://peak.fo/earn).

```python
scraper = cloudscraper.create_scraper(
    api_key="pk_your_api_key",
    app_id="app_your_app_id",   # optional; or set PEAK_APP_ID in the env
)
```

## Compatibility

| cloudscraper API | Status in cloudscraper-turnstile |
| --- | --- |
| `create_scraper(**kwargs)` | Supported. Returns a `requests.Session` subclass. |
| Returns a `requests.Session` | Yes. `CloudScraper(requests.Session)`. |
| `.get / .post / .put / .delete / .request` | Supported (inherited from `requests.Session`). |
| `.cookies`, `.headers`, `.proxies`, `.auth` | Supported (session state persists across the solve retry). |
| `sess=` (adopt an existing Session) | Supported (cookies, headers, proxies, auth carried over). |
| `captcha={"provider": ..., "api_key": ...}` | Supported. `provider: "peak"` is native; the `api_key` is read regardless. |
| `browser=`, `delay=`, `interpreter=`, `allow_brotli=`, `debug=` | Accepted, never raise. `debug=True` prints solve steps. |
| Legacy IUAM JS-math challenge | Handled by Cloudflare's own retry path; not the focus. |
| Cloudflare Turnstile | **Solved** via Peak (`turnstiletask`). |
| Cloudflare 5s "Just a moment" / managed | **Solved** via Peak (`cloudflare5stask`). |

## cloudscraper vs cloudscraper-turnstile

| Challenge / trait | cloudscraper | cloudscraper-turnstile |
| --- | --- | --- |
| Legacy IUAM JS-math | Yes | Yes |
| Cloudflare Turnstile | No (hands off to a paid API you must wire up) | **Yes** |
| 5s "Just a moment" interstitial | No (no JS engine) | **Yes** |
| Managed challenge | No | **Yes** |
| `requests.Session` drop-in | Yes | Yes |
| Actively maintained | No (last release 2023) | Yes |

## FAQ

**Why is cloudscraper not working in 2026?**
Because the site moved to Cloudflare Turnstile or the managed 5s challenge. cloudscraper only solves the old IUAM JavaScript-math page and has no JS engine, so on a modern challenge it returns the challenge HTML (usually `403`, `503`, or a "Just a moment..." page) instead of your data. Its last release was in 2023. cloudscraper-turnstile detects those challenges and solves them through Peak.

**What is a good cloudscraper alternative for Turnstile?**
cloudscraper-turnstile is built to be that alternative: same `create_scraper` API, same `requests.Session` object, but it actually solves Turnstile. Change the import, add a Peak API key, and your existing code runs.

**How do I fix cloudscraper 403 Forbidden?**
A `403` from a Cloudflare-protected site usually means you received the challenge page, not a real block. Confirm the body contains `cf-turnstile`, `Just a moment`, or `cf_chl_opt`. If so, switch to `import cloudscraper_turnstile as cloudscraper`, set `PEAK_API_KEY`, and the challenge is solved and the request retried automatically. If the proxy/IP that gets challenged is not your default one, pass `proxy=` so the solve matches.

**Does cloudscraper solve Cloudflare Turnstile?**
Not on its own. cloudscraper never solved Turnstile itself; it only added hooks to pass the token from an external paid CAPTCHA service. cloudscraper-turnstile does the solve for you through Peak and injects the `cf-turnstile-response` token, so there is nothing else to wire up.

**Do I need a real browser or Selenium?**
No. This is a pure `requests`-based client. The browser work happens on Peak's side; you send the sitekey and URL and get a token (or a `cf_clearance` cookie for the 5s challenge) back.

**Does it handle the 5s "Just a moment" page too?**
Yes. When the response is the interstitial rather than a Turnstile widget, the package calls Peak's `cloudflare5stask`, sets the returned `cf_clearance` cookie (and user-agent) on the session, and re-requests the original URL.

**Will it loop forever if a solve fails?**
No. Solving is capped by `max_solve_attempts` (default 3). After that the last response is returned as-is so you can inspect it.

## Legitimate use

Use this for automation, QA, monitoring, and scraping public data you are allowed to access. Respect each target's Terms of Service and `robots.txt`, rate-limit yourself, and do not use it for credential stuffing or to access data you have no right to. You are responsible for how you use it.

## Links

- [Peak home](https://peak.fo/?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cloudscraper-turnstile)
- [Turnstile docs](https://peak.fo/docs/turnstile?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cloudscraper-turnstile)
- [Pricing](https://peak.fo/pricing?utm_source=github&utm_medium=readme&utm_campaign=packages&utm_content=cloudscraper-turnstile)

## License

MIT. See [LICENSE](./LICENSE).
