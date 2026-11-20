"""ECM headlines from the six publications used by blocks_tracker."""

from __future__ import annotations

import datetime
import email.utils
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Same publications blocks_tracker searches, one feed each so one site cannot crowd out the rest.
SOURCES = (
    ("CNBC TV18", "cnbctv18.com"),
    ("Moneycontrol", "moneycontrol.com"),
    ("NDTV Profit", "ndtvprofit.com"),
    ("Economic Times", "economictimes.indiatimes.com"),
    ("Business Standard", "business-standard.com"),
    ("Mint", "livemint.com"),
)

QUERY = (
    '"block deal" OR "bulk deal" OR QIP OR "qualified institutional placement" '
    'OR "rights issue" OR "preferential issue" OR "preferential allotment" '
    'OR "offer for sale" OR "follow-on public" OR FPO OR IPO OR DRHP OR UDRHP '
    'OR RHP OR buyback OR "buy-back"'
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
        lines = [f"{self.kind} · {self.company}", f"{self.source} · {self.summary}"]
        if self.published:
            lines.append(self.published.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST"))
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
    if "preferential" in low:
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
    markers = (
        "crore", "₹", " rs", "sebi", "nse", "bse", "drhp", "udrhp", "rhp",
        "ipo papers", "ipo to open", "files ", "filing", "price band",
        "fresh issue", "offer for sale",
    )
    return any(marker in low for marker in markers)


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
    deals = []
    seen = set()
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=36)
    for label, domain in SOURCES:
        try:
            items = _items(_search_url(domain))
        except Exception as exc:
            print(f"feed skipped: {label}: {exc}", flush=True)
            continue
        for item in items:
            title = _text(item.find("title"))
            kind = classify_press(title)
            if not kind or not _indian_issue(title, kind):
                continue
            published = _when(item)
            if published is None or published < cutoff:
                continue
            link = direct_url(_text(item.find("link")) or _text(item.find("guid")))
            if not link or not _on_source(link, domain):
                continue
            if link in seen:
                continue
            seen.add(link)
            description = _text(item.find("description"))
            deals.append(
                Deal(
                    id="press:" + link,
                    kind=kind,
                    company=title,
                    summary=description[:300] or label,
                    source=label,
                    url=link,
                    published=published,
                )
            )
    return deals


def _search_url(domain: str) -> str:
    query = urllib.parse.quote(f"({QUERY}) site:{domain}")
    return "https://www.bing.com/news/search?q=" + query + "&format=RSS&sortbydate=1&setlang=en-IN"


def _items(url: str) -> list[ET.Element]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as response:
        root = ET.fromstring(response.read())
    return root.findall(".//item")


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return _SPACE.sub(" ", html.unescape(node.text)).strip()


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
