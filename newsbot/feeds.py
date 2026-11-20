"""ECM headlines from the six publications' own news sitemaps.

Bing's news search only returns a short, unstable list, so a story could be
published in the morning and stay invisible until that list happened to
include it. Each paper's sitemap is the list of what it actually published.
"""

from __future__ import annotations

import datetime
import email.utils
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Publisher sitemaps, not a search engine's short list. Economic Times verticals
# such as ET Auto are not in the main sitemap, and NDTV Profit blocks its own
# sitemap, so those two also use a narrow Bing query per deal type.
SOURCES = (
    ("CNBC TV18", "cnbctv18.com", ("https://www.cnbctv18.com/commonfeeds/v1/cne/sitemap/google-news.xml",), False),
    ("Moneycontrol", "moneycontrol.com", ("https://www.moneycontrol.com/news/news-sitemap.xml",), False),
    ("NDTV Profit", "ndtvprofit.com", (), True),
    (
        "Economic Times",
        "economictimes.indiatimes.com",
        (
            "https://economictimes.indiatimes.com/etstatic/sitemaps/et/news/sitemap-today.xml",
            "https://economictimes.indiatimes.com/etstatic/sitemaps/et/news/sitemap-yesterday.xml",
        ),
        True,
    ),
    ("Business Standard", "business-standard.com", ("https://www.business-standard.com/sitemap/news-sitemap.xml",), False),
    (
        "Mint",
        "livemint.com",
        (
            "https://www.livemint.com/sitemap/today.xml",
            "https://www.livemint.com/sitemap/yesterday.xml",
        ),
        False,
    ),
)

BING_QUERIES = (
    'IPO OR DRHP OR UDRHP OR RHP OR FPO OR "initial public offer"',
    'QIP OR "qualified institutional placement"',
    '"preferential issue" OR "preferential allotment" OR "rights issue" OR buyback OR "buy-back"',
    '"block deal" OR "bulk deal" OR "offer for sale"',
)

PRESS_SKIP = (
    "grey market",
    "gmp",
    "subscription status",
    "subscribed",
    "lists at",
    "listing gain",
    "listing loss",
    "debuts at",
    "allotment status",
)

_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Deal:
    id: str
    kind: str
    company: str
    summary: str
    source: str
    url: str
    published: datetime.datetime | None

    def format(self, include_url: bool = True) -> str:
        lines = [self.company]
        if self.published:
            when = self.published.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
            lines.append(f"{self.source} | {when}")
        else:
            lines.append(self.source)
        if include_url and self.url:
            lines.append(self.url)
        return "\n".join(lines)


def prospectus_kind(text: str) -> str | None:
    """DRHP, UDRHP, and RHP. Longer forms are tested first so DRHP is not read as RHP."""
    low = _SPACE.sub(" ", text or "").lower()
    if "udrhp" in low or "updated draft red herring" in low:
        return "UDRHP"
    if "drhp" in low or "draft red herring" in low:
        return "DRHP"
    if re.search(r"(?<![a-z])rhp\b", low) or "red herring prospectus" in low:
        return "RHP"
    return None


def classify(text: str) -> str | None:
    """Return a deal label, or None when the text is not an ECM launch."""
    low = " " + _SPACE.sub(" ", text or "").lower() + " "
    if "net asset value" in low or " per unit " in low or "ipo etf" in low:
        return None
    prospectus = prospectus_kind(low)
    if prospectus:
        return prospectus
    if re.search(r"\bqip\b", low) or "qualified institutional placement" in low:
        return "QIP"
    if "block deal" in low or "bulk deal" in low:
        return "Block"
    if "offer for sale" in low:
        return "OFS"
    if "rights issue" in low or "right issue" in low:
        return "Rights"
    if "preferential issue" in low or "preferential allotment" in low or "preferential basis" in low:
        return "Preferential"
    if "buy-back" in low or "buyback" in low or "buy back" in low:
        return "Buyback"
    if (
        "initial public offer" in low
        or "public issue" in low
        or re.search(r"\bfpo\b", low)
        or "follow-on public" in low
        or "follow on public" in low
    ):
        return "IPO"
    return None


def classify_press(title: str) -> str | None:
    low = (title or "").lower()
    if any(skip in low for skip in PRESS_SKIP):
        return None
    kind = classify(title)
    if kind:
        return kind
    if re.search(r"\bipo\b", low):
        return "IPO"
    return None


def _indian_issue(title: str, kind: str) -> bool:
    """A bare IPO headline has to be an Indian issue. QIP, blocks, and rights already are."""
    if kind != "IPO":
        return True
    low = (title or "").lower()
    if re.search(r"\b(nasdaq|nyse)\b", low) or "wall street" in low:
        return False
    indian_money = "crore" in low or "₹" in low or re.search(r"\brs\.?\s*\d", low)
    if "$" in (title or "") and not indian_money:
        return False
    if "securities and exchange commission" in low and "sebi" not in low:
        return False
    # The sitemap is the whole paper, so a rupee figure or the letters "nse"
    # inside "Sensex" is not enough. The headline has to be the issue itself.
    return any(re.search(pattern, low) for pattern in (
        r"\bfiles\b", r"\bfiling\b", r"\bfiled\b", r"ipo papers",
        r"\bto launch\b", r"\blaunches\b", r"\bto raise\b", r"\braises\b", r"\braising\b",
        r"fresh issue", r"offer for sale", r"price band", r"\bto open\b", r"\bopens\b",
        r"ipo size", r"\btrims\b", r"\bhalves\b", r"\bcuts\b",
    ))


def direct_url(link: str) -> str:
    """Bing wraps the article in a click tracker. The publisher URL is in the query."""
    parsed = urllib.parse.urlparse(link or "")
    if "bing.com" not in parsed.netloc.lower():
        return link
    target = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
    return target or link


def _on_source(url: str, domain: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == domain or host.endswith("." + domain)


def press_deals() -> list[Deal]:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=36)
    found: list[list[Deal]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_source_deals, source, cutoff) for source in SOURCES]
        for future in futures:
            found.append(future.result())
    deals = []
    seen = set()
    for batch in found:
        for deal in batch:
            if deal.url in seen:
                continue
            seen.add(deal.url)
            deals.append(deal)
    return deals


def _source_deals(source: tuple, cutoff: datetime.datetime) -> list[Deal]:
    label, domain, sitemaps, use_bing = source
    deals = []
    seen = set()
    for url in sitemaps:
        try:
            entries = _sitemap_entries(_fetch(url))
        except Exception as exc:
            print(f"feed skipped: {label}: {exc}", flush=True)
            continue
        for title, link, published in entries:
            _add_deal(deals, seen, label, domain, title, link, published, "", cutoff)
    if use_bing:
        for query in BING_QUERIES:
            try:
                items = _items(_search_url(domain, query))
            except Exception as exc:
                print(f"feed skipped: {label}: {exc}", flush=True)
                continue
            for item in items:
                title = _text(item.find("title"))
                link = direct_url(_text(item.find("link")) or _text(item.find("guid")))
                published = _when(item)
                description = _text(item.find("description"))
                _add_deal(deals, seen, label, domain, title, link, published, description, cutoff)
    return deals


def _add_deal(deals, seen, label, domain, title, link, published, description, cutoff) -> None:
    kind = classify_press(title)
    if not kind or not _indian_issue(title, kind):
        return
    if published is None or published < cutoff:
        return
    if not link or not _on_source(link, domain):
        return
    if link in seen:
        return
    seen.add(link)
    deals.append(
        Deal(
            id="press:" + link,
            kind=kind,
            company=title,
            summary=(description or label)[:300],
            source=label,
            url=link,
            published=published,
        )
    )


def _sitemap_entries(payload: bytes) -> list[tuple[str, str, datetime.datetime | None]]:
    """Article title, link, and publication time from a Google news sitemap."""
    root = ET.fromstring(payload)
    entries = []
    for node in root.iter():
        if not node.tag.endswith("url"):
            continue
        link = ""
        title = ""
        published = None
        for child in node.iter():
            name = child.tag.rsplit("}", 1)[-1]
            text = _text_value(child.text)
            if name == "loc" and text.startswith("http") and not link:
                link = text
            elif name == "title" and text and not title:
                title = text
            elif name == "publication_date" and text and published is None:
                published = _iso_when(text)
        if link and title:
            entries.append((title, link, published))
    return entries


def _search_url(domain: str, query: str) -> str:
    quoted = urllib.parse.quote(f"({query}) site:{domain}")
    return "https://www.bing.com/news/search?q=" + quoted + "&format=RSS&sortbydate=1&setlang=en-IN&count=40"


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def _items(url: str) -> list[ET.Element]:
    root = ET.fromstring(_fetch(url))
    return root.findall(".//item")


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return _text_value(node.text)


def _text_value(value: str | None) -> str:
    if not value:
        return ""
    return _SPACE.sub(" ", html.unescape(value)).strip()


def _iso_when(raw: str) -> datetime.datetime | None:
    try:
        parsed = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _when(item: ET.Element) -> datetime.datetime | None:
    raw = _text(item.find("pubDate"))
    if not raw:
        return None
    parsed = None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
            try:
                parsed = datetime.datetime.strptime(raw, fmt).replace(tzinfo=IST)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed
