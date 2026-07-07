"""Site-signal enrichment worker — the zero-credit "Clay layer".

Fetches a company's website and extracts the outbound-relevant signals that
paid enrichment tools charge for:

- **PM software in use** (AppFolio, Yardi, Vantaca, Rent Manager, Buildium, ...)
  detected from portal links and vendor strings in the HTML. This is the
  "I saw you run X" integration hook.
- **24/7 / after-hours coverage** language, with the matched evidence snippet.
- **Scale claims** ("2,400 units", "85+ buildings", "3M sq ft").
- **Phone numbers** published on the site.

Implements the enrichment box in ``ARCHITECTURE.md``. Measured against Clay's
Claygent on the same firms, portal-link detection recovers the platform for
every firm whose site embeds a resident/owner portal — which is most of them.

Usage::

    python -m enrichment.site_signals example.com other.com
    python -m enrichment.site_signals --json domains.json   # ["a.com", ...]

Environment:
    ENRICH_CA_BUNDLE   optional CA bundle path (e.g. a corporate/agent proxy CA).
    Standard ``HTTPS_PROXY`` is honored automatically by urllib.

Output: one JSON object per domain on stdout (a JSON list).
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
TIMEOUT = 15
MAX_SUBPAGES = 4

# vendor -> lowercase substrings that identify it in hrefs or page text.
# Portal URLs are the strongest tell (e.g. https://xyz.appfolio.com/connect).
PLATFORM_SIGNATURES: dict[str, list[str]] = {
    "AppFolio": ["appfolio.com", "appfolio"],
    "Buildium": ["buildium.com", "buildium"],
    "Yardi": ["yardi", "rentcafe.com", "yardiasp"],
    "RealPage": ["realpage", "activebuilding"],
    "Rent Manager": ["rentmanager.com", "rent manager", "rmresident"],
    "ResMan": ["myresman", "resman"],
    "Propertyware": ["propertyware"],
    "Entrata": ["entrata"],
    "Vantaca": ["vantaca"],
    "TOPS": ["topssoft"],
    "CINC": ["cincsystems", "cincwebaxis"],
    "AppWork": ["appwork"],
    "ClickPay": ["clickpay"],
    "Zego/PayLease": ["paylease", "gozego"],
    "BuildingLink": ["buildinglink"],
    "DoorLoop": ["doorloop"],
    "TenantCloud": ["tenantcloud"],
    "FRONTSTEPS": ["frontsteps"],
}

RE_24_7 = re.compile(
    r"(24\s*[/\-x]\s*7|24\s*hours?|after[\s\-]hours?|around[\s\-]the[\s\-]clock|"
    r"emergency\s+(?:line|hotline|service|maintenance|response|call))",
    re.I,
)
RE_SCALE = re.compile(
    r"([\d][\d,.]*\+?)\s*(?:million\s+)?(units?|doors?|buildings?|properties|homes?|"
    r"residences|communities|associations|square\s*(?:feet|ft)|sq\.?\s*ft)",
    re.I,
)
RE_PHONE = re.compile(r"\(?\b\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b")
RE_HREF = re.compile(r"href=[\"']([^\"'#]+)", re.I)
SUBPAGE_HINTS = ("service", "about", "contact", "career", "job", "resident", "owner", "maintenance")


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=os.environ.get("ENRICH_CA_BUNDLE") or None)


def _fetch(url: str, ctx: ssl.SSLContext) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return resp.read(1_500_000).decode("utf-8", errors="replace")


def _homepage(domain: str, ctx: ssl.SSLContext) -> tuple[str, str]:
    last_err: Exception | None = None
    for scheme in ("https", "http"):
        for host in (domain, f"www.{domain}"):
            url = f"{scheme}://{host}/"
            try:
                return url, _fetch(url, ctx)
            except Exception as e:  # noqa: BLE001 - collect and continue
                last_err = e
    raise ConnectionError(f"unreachable: {last_err}")


def _subpage_urls(base_url: str, html: str) -> list[str]:
    seen: list[str] = []
    base_host = urllib.parse.urlparse(base_url).netloc
    for href in RE_HREF.findall(html):
        full = urllib.parse.urljoin(base_url, href)
        p = urllib.parse.urlparse(full)
        if p.netloc != base_host or p.scheme not in ("http", "https"):
            continue
        if any(h in p.path.lower() for h in SUBPAGE_HINTS) and full not in seen:
            seen.append(full)
        if len(seen) >= MAX_SUBPAGES:
            break
    return seen


def enrich_domain(domain: str) -> dict:
    """Fetch a site and return its outbound signals. Never raises."""
    out: dict = {
        "domain": domain,
        "pages_fetched": 0,
        "pm_software": [],
        "has_24_7": False,
        "evidence_24_7": None,
        "scale_claims": [],
        "phones": [],
        "error": None,
    }
    ctx = _ssl_context()
    try:
        base_url, html = _homepage(domain, ctx)
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:160]
        return out

    corpus = [html]
    out["pages_fetched"] = 1
    for sub in _subpage_urls(base_url, html):
        try:
            corpus.append(_fetch(sub, ctx))
            out["pages_fetched"] += 1
        except Exception:  # noqa: BLE001 - subpages are best-effort
            continue

    blob = "\n".join(corpus).lower()
    out["pm_software"] = sorted(
        {name for name, sigs in PLATFORM_SIGNATURES.items() if any(s in blob for s in sigs)}
    )
    m = RE_24_7.search("\n".join(corpus))
    if m:
        out["has_24_7"] = True
        start = max(0, m.start() - 60)
        out["evidence_24_7"] = re.sub(r"\s+", " ", "\n".join(corpus)[start : m.end() + 60]).strip()
    out["scale_claims"] = [
        f"{num} {unit}" for num, unit in RE_SCALE.findall("\n".join(corpus))[:5]
    ]
    out["phones"] = list(dict.fromkeys(RE_PHONE.findall("\n".join(corpus))))[:3]
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] == "--json":
        domains = json.load(open(argv[1]))
    else:
        domains = argv
    results = [enrich_domain(d.strip().lower()) for d in domains]
    json.dump(results, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
