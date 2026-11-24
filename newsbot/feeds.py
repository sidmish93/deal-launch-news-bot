"""ECM headlines from the six publications' own news sitemaps.

Bing's news search only returns a short, unstable list, so a story could be
published in the morning and stay invisible until that list happened to
include it. Each paper's sitemap is the list of what it actually published.
Economic Times verticals are not on the main list; each one publishes a
48-hour sitemap. NDTV Profit and ET Auto refuse Python's HTTP client, so a
blocked list is read again with a browser TLS fingerprint.
"""

from __future__ import annotations

import dataclasses
import datetime
import email.utils
import html
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Publisher lists, not a search engine's short list. The Economic Times main
# sitemap does not include ET Auto and the other verticals, so those are read
# from each vertical's own recent-stories feed. NDTV Profit's daily sitemap is
# the list of what it published. A narrow Bing query stays as a backup.
SOURCES = (
    ("CNBC TV18", "cnbctv18.com", ("https://www.cnbctv18.com/commonfeeds/v1/cne/sitemap/google-news.xml",), False, ()),
    ("Moneycontrol", "moneycontrol.com", ("https://www.moneycontrol.com/news/news-sitemap.xml",), False, ()),
    ("NDTV Profit", "ndtvprofit.com", (), True, ()),
    (
        "Economic Times",
        "economictimes.indiatimes.com",
        (
            "https://economictimes.indiatimes.com/etstatic/sitemaps/et/news/sitemap-today.xml",
            "https://economictimes.indiatimes.com/etstatic/sitemaps/et/news/sitemap-yesterday.xml",
        ),
        True,
        (),
    ),
    ("Business Standard", "business-standard.com", ("https://www.business-standard.com/sitemap/news-sitemap.xml",), False, ()),
    (
        "Mint",
        "livemint.com",
        (
            "https://www.livemint.com/sitemap/today.xml",
            "https://www.livemint.com/sitemap/yesterday.xml",
        ),
        False,
        (),
    ),
)

# Same paper, separate sites. The 48-hour sitemap is the list; recentstories
# is only the newest page and drops a story once twenty newer ones exist.
ET_VERTICALS = (
    "auto", "chemicals", "energy", "bfsi", "cfo", "ciso", "realty", "pharma",
    "infra", "telecom", "manufacturing", "government", "legal", "health",
    "cio", "retail", "hospitality", "travel", "agriculture", "electronics",
    "sustainability",
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
    if _is_stake(low):
        return "Stake"
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
    if re.search(r"\bipos?\b", low):
        return "IPO"
    return None


def _is_stake(low: str) -> bool:
    """A stake sale, or a purchase of a stake that names the price or the offer."""
    if re.search(r"\bstake sale\b", low):
        return True
    if not re.search(r"\b(?:acquir\w*|buys?|buying|offloads?|sells?|selling)\b.{0,50}\bstake\b", low):
        return False
    return bool(
        "crore" in low
        or "₹" in low
        or re.search(r"\brs\.?\s*\d", low)
        or "open offer" in low
        or "share purchase" in low
    )


def _price_reaction(low: str) -> bool:
    """The share price is the story, and the deal is only the reason it moved."""
    return re.search(
        r"\b(?:shares?|stocks?)\b.{0,60}\b(?:fall|falls|fell|plunge|plunges|plunged|tank|tanks|tanked|slide|slides|slid|tumble|tumbles|crash|crashes|jump|jumps|jumped|surge|surges|rise|rises|rose|drop|drops|dropped|sink|sinks|sank)\b"
        r"|\bpares? losses\b"
        r"|\btrad(?:e|es|ing) flat\b"
        r"|\bsharpest (?:fall|drop|decline|slide)\b"
        r"|\bshare price in focus\b",
        low,
    ) is not None


def _is_roundup(low: str) -> bool:
    """A diary of several corporate actions, not one issue."""
    if re.search(r"\brecord dates\b", low):
        return True
    if re.search(r"\brecord date\b", low):
        actions = sum(
            phrase in low
            for phrase in ("dividend", "buyback", "buy-back", "buy back", "rights issue", "stock split", "bonus")
        )
        if actions >= 2:
            return True
    if re.search(r"\binvits\b", low) and re.search(r"\b(?:expected|likely) to\b|\bup to \d", low):
        return True
    return "alert" in low and re.search(r"\bdividends?\b.{0,40}\bbuy-?backs?\b", low) is not None


def _blocks_issue(title: str, kind: str | None = None) -> bool:
    """Price moves, foreign listings, grey-market notes, and roundups are not a deal."""
    low = (title or "").lower()
    if any(skip in low for skip in PRESS_SKIP):
        return True
    if re.search(r"\b(nasdaq|nyse)\b", low) or "wall street" in low:
        return True
    if "securities and exchange commission" in low and "sebi" not in low:
        return True
    # A dollar amount with no rupee figure is a foreign offer. "Stake sale" is
    # the Indian phrase, and the valuation beside it is often written in dollars.
    indian_money = "crore" in low or "₹" in low or re.search(r"\brs\.?\s*\d", low)
    stake = kind == "Stake" or "stake sale" in low
    if not stake and "$" in (title or "") and not indian_money:
        return True
    if _price_reaction(low) or _is_roundup(low):
        return True
    if re.search(r"\bshould you buy\b|\bgood stock to bet\b|\bwhat (?:market )?experts say\b", low):
        return True
    if stake and re.search(r"\b(strike|protest|scam)\b", low):
        return True
    return False


def _indian_issue(title: str, kind: str) -> bool:
    """The headline has to be the Indian issue itself, whichever deal word it uses."""
    if _blocks_issue(title, kind):
        return False
    low = (title or "").lower()
    if kind != "IPO":
        return True
    # The sitemap is the whole paper. Mentioning an IPO is not the same as
    # the company filing, pricing, opening, or moving that offer.
    return any(re.search(pattern, low) for pattern in (
        r"\bfiles\b", r"\bfiling\b", r"\bfiled\b", r"ipo papers",
        r"\bto launch\b", r"\blaunches\b", r"\bto raise\b",
        r"\braises\b.{0,40}(?:₹|\brs\b|\d)", r"\braising\b.{0,40}(?:₹|\brs\b|\d|funds|capital)",
        r"fresh issue", r"offer for sale", r"price band", r"\bto open\b", r"\bopens\b",
        r"ipo size", r"\btrims\b", r"\bhalves\b", r"\bcuts\b",
        r"\bto float\b", r"\bapproves\b", r"\bnod\b",
        r"\beyes\b", r"\beyeing\b", r"\bweighs\b", r"\bweighing\b",
        r"\bdefers\b", r"\bdeferred\b", r"\bdeferring\b",
        r"\bdelays\b", r"\bdelayed\b", r"\bpostpones\b", r"\bpostponed\b",
        r"\bplans?\b", r"\bplanning\b", r"\bslips?\b", r"\bslipped\b",
    ))


# Verbs a headline uses when the strict list above does not. Kept next to the
# offer word so "investors mull the impact of an IPO" does not qualify.
_OFFER_ACTION = re.compile(
    r"\b(?:mulls?|mulling|considers?|considering|explores?|exploring|seeks?|seeking|"
    r"lines up|lining up|gears up|gearing up|targets?|targeting|looks to|looking to|"
    r"set to|readies|readying|revives?|reviving|pushes back|pushed back|"
    r"prepares|preparing|in talks)\b.{0,50}\b"
    r"(?:ipos?|drhp|udrhp|rhp|qip|fpo|stake sale|offer for sale|preferential issue|"
    r"rights issue|buy-?back|block deal|bulk deal)\b"
    r"|\b(?:ipos?|drhp|udrhp|rhp|qip|fpo)\b.{0,40}\b"
    r"(?:mulls?|mulling|considers?|considering|explores?|exploring|seeks?|seeking|"
    r"lines up|lining up|gears up|gearing up|readies|readying|revives?|reviving)\b",
    re.I,
)


def offer_status(title: str) -> str:
    """firm: send from the headline. maybe: the offer is named, the verb is not. no: drop."""
    kind = classify_press(title)
    if not kind or _blocks_issue(title, kind):
        return "no"
    if _indian_issue(title, kind):
        return "firm"
    return "maybe"


def confirm_offer(headline: str, description: str = "") -> str | None:
    """Send when the headline or the article says the company is doing the offer."""
    blob = _SPACE.sub(" ", f"{headline} {description}").strip()
    kind = classify_press(headline) or classify_press(blob)
    if not kind:
        return None
    if _blocks_issue(blob, kind) or _blocks_issue(headline, kind):
        return None
    if _indian_issue(headline, kind) or _indian_issue(blob, kind):
        return kind
    low = blob.lower()
    if re.match(r"(investors|analysts|brokerages|markets|the market|dalal street)\b", low):
        return None
    if kind == "IPO" and _offer_action(blob):
        return "IPO"
    return None


def _offer_action(text: str) -> bool:
    """The verb has to act on the offer, not sit near a passing mention of one."""
    match = _OFFER_ACTION.search(text or "")
    if not match:
        return False
    gap = match.group(0).lower()
    return "ahead of" not in gap and "growth" not in gap


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


def press_deals(
    skip_urls: set[str] | None = None,
    held_titles: dict[str, str] | None = None,
) -> tuple[list[Deal], list[tuple[str, str]]]:
    """Firm deals, plus headlines that name an offer once the article confirms it.

    The second list is urls judged and not sent, with the title that was judged.
    A later poll retries a url when the paper changes that title. skip_urls are
    already delivered. The article clock is not a reason to drop a url: the
    caller sends a story when it first appears on a list.
    """
    socket.setdefaulttimeout(15)
    skip_urls = skip_urls or set()
    held_titles = held_titles or {}
    sources = list(SOURCES)
    for name in ET_VERTICALS:
        feeds = (f"https://{name}.economictimes.indiatimes.com/rss/recentstories",)
        if name == "auto":
            feeds = feeds + (_site_feed("auto.economictimes.indiatimes.com"),)
        sources.append((
            "Economic Times",
            "economictimes.indiatimes.com",
            (f"https://{name}.economictimes.indiatimes.com/jcms-sitemaps/{name}/48hours/sitemap-48hours.xml",),
            False,
            feeds,
        ))
    found: list[tuple[list[Deal], list[Deal]]] = []
    pool = ThreadPoolExecutor(max_workers=12)
    try:
        futures = [
            pool.submit(_source_deals, source, skip_urls, held_titles) for source in sources
        ]
        for future in futures:
            try:
                found.append(future.result(timeout=40))
            except Exception as exc:
                print(f"feed skipped: {exc}", flush=True)
                found.append(([], []))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    firms: list[Deal] = []
    maybes: list[Deal] = []
    seen = set()
    for firm_batch, maybe_batch in found:
        for deal in firm_batch + maybe_batch:
            if deal.url in seen:
                continue
            seen.add(deal.url)
            if deal in firm_batch:
                firms.append(deal)
            else:
                maybes.append(deal)
    ready, rejected = _promote_maybes(maybes)
    return firms + ready, rejected


def _promote_maybes(maybes: list[Deal]) -> tuple[list[Deal], list[tuple[str, str]]]:
    """A named offer with no clear verb is checked against the article, once."""
    ready: list[Deal] = []
    needs_page: list[Deal] = []
    rejected: list[tuple[str, str]] = []
    for deal in maybes:
        kind = confirm_offer(deal.company, "")
        if kind:
            ready.append(dataclasses.replace(deal, kind=kind))
        else:
            needs_page.append(deal)
    if not needs_page:
        return ready, rejected
    pool = ThreadPoolExecutor(max_workers=8)
    try:
        futures = {pool.submit(_judge_page, deal): deal for deal in needs_page[:20]}
        for future, deal in futures.items():
            try:
                judged = future.result(timeout=8)
            except Exception:
                continue
            if judged is None:
                rejected.append((deal.url, deal.company))
            else:
                ready.append(judged)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return ready, rejected


def _judge_page(deal: Deal) -> Deal | None:
    found = _article_blurb(deal.url)
    if found is None:
        raise TimeoutError(deal.url)
    title, description = found
    use = title or deal.company
    kind = confirm_offer(use, description)
    if not kind:
        return None
    return dataclasses.replace(
        deal,
        kind=kind,
        company=use,
        summary=(description or deal.summary)[:300],
    )


def _article_blurb(url: str) -> tuple[str, str] | None:
    """The article headline and description. None means the page did not load."""
    try:
        page = _fetch(url)[:250_000].decode("utf-8", "replace")
    except Exception:
        return None
    title = _meta(page, "og:title") or _meta(page, "twitter:title")
    description = _meta(page, "og:description") or _meta(page, "description")
    if title:
        title = re.sub(
            r"\s+[|\-–—]\s+(?:NDTV Profit|Moneycontrol|Mint|Business Standard|"
            r"Economic Times|ET|CNBC TV18)\s*$",
            "",
            title,
            flags=re.I,
        ).strip()
    return title, description


def _source_deals(
    source: tuple,
    skip_urls: set[str],
    held_titles: dict[str, str],
) -> tuple[list[Deal], list[Deal]]:
    label, domain, sitemaps, use_bing, feeds = source
    firms: list[Deal] = []
    maybes: list[Deal] = []
    seen = set()
    if domain == "ndtvprofit.com":
        # The news sitemap carries the headline. The daily files are the backup
        # for a story that has already rotated off that shorter list.
        sitemaps = ("https://www.ndtvprofit.com/news_sitemap.xml",) + _ndtv_daily_sitemaps()
        feeds = tuple(feeds) + (_site_feed("ndtvprofit.com"),)
    for url in sitemaps:
        parser = _listed_entries if "sitemap-daily-" in url else _sitemap_entries
        try:
            entries = parser(_fetch(url))
        except Exception as exc:
            print(f"feed skipped: {label}: {exc}", flush=True)
            continue
        for title, link, published in entries:
            _add_deal(
                firms, maybes, seen, skip_urls, held_titles,
                label, domain, title, link, published, "",
            )
    for url in feeds:
        try:
            items = _items(url)
        except Exception as exc:
            print(f"feed skipped: {label}: {exc}", flush=True)
            continue
        for item in items:
            title = _text(item.find("title"))
            link = direct_url(_text(item.find("link")) or _text(item.find("guid")))
            _add_deal(
                firms, maybes, seen, skip_urls, held_titles,
                label, domain, title, link, _when(item), _text(item.find("description")),
            )
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
                _add_deal(
                    firms, maybes, seen, skip_urls, held_titles,
                    label, domain, title, link, published, description,
                )
    return firms, maybes


def _add_deal(
    firms,
    maybes,
    seen,
    skip_urls,
    held_titles,
    label,
    domain,
    title,
    link,
    published,
    description,
) -> None:
    if not link or not _on_source(link, domain) or link in seen or link in skip_urls:
        return
    if held_titles.get(link) == title:
        return
    status = offer_status(title)
    if status == "no":
        return
    # A list with no clock cannot be told from a stale sitemap entry.
    if published is None:
        return
    seen.add(link)
    kind = classify_press(title) or "IPO"
    deal = Deal(
        id="press:" + link,
        kind=kind,
        company=title,
        summary=(description or label)[:300],
        source=label,
        url=link,
        published=published,
    )
    if status == "firm":
        firms.append(deal)
    else:
        confirmed = confirm_offer(title, description)
        if confirmed:
            firms.append(dataclasses.replace(deal, kind=confirmed))
        else:
            maybes.append(deal)


def _ndtv_daily_sitemaps() -> tuple[str, ...]:
    now = datetime.datetime.now(IST)
    urls = []
    for shift in (0, 1):
        day = (now - datetime.timedelta(days=shift)).date()
        urls.append(f"https://www.ndtvprofit.com/sitemap/sitemap-daily-{day.isoformat()}.xml")
    return tuple(urls)


def _title_from_slug(url: str) -> str:
    slug = (url or "").rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"-\d{5,}$", "", slug)
    text = re.sub(r"\s+", " ", slug.replace("-", " ")).strip()
    text = re.sub(r"\brs\b", "Rs", text)
    text = re.sub(r"\bcr\b", "crore", text)
    if not text:
        return url
    return text[0].upper() + text[1:]


def _listed_entries(payload: bytes) -> list[tuple[str, str, datetime.datetime | None]]:
    """Article link and time from a sitemap that has no headline, only the URL."""
    root = ET.fromstring(payload)
    entries = []
    for node in root.iter():
        if not node.tag.endswith("url"):
            continue
        link = ""
        published = None
        for child in list(node):
            name = child.tag.rsplit("}", 1)[-1]
            text = _text_value(child.text)
            if name == "loc" and text.startswith("http") and not link:
                link = text.split("?")[0]
            elif name == "lastmod" and text and published is None:
                published = _iso_when(text)
        if link:
            entries.append((_title_from_slug(link), link, published))
    return entries


def polish_headline(deal: Deal) -> Deal | None:
    """Open an NDTV article for its real headline. None means the page is not a deal."""
    if deal.source != "NDTV Profit":
        return deal
    found = _article_blurb(deal.url)
    if found is None:
        return deal
    title, description = found
    headline = title or deal.company
    kind = confirm_offer(headline, description)
    if not kind:
        return None
    return dataclasses.replace(
        deal,
        kind=kind,
        company=headline,
        summary=(description or deal.summary)[:300],
    )


def _meta(page: str, prop: str) -> str:
    patterns = (
        rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"',
        rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{re.escape(prop)}"',
    )
    for pattern in patterns:
        match = re.search(pattern, page, re.IGNORECASE)
        if match:
            return _text_value(match.group(1))
    return ""


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
            if name == "loc" and _is_article_url(text) and not link:
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


def _site_feed(host: str) -> str:
    """Newest stories on one site, with no keyword filter to crowd a deal out."""
    quoted = urllib.parse.quote(f"site:{host}")
    return "https://www.bing.com/news/search?q=" + quoted + "&format=RSS&sortbydate=1&setlang=en-IN&count=40"


def _is_article_url(url: str) -> bool:
    path = (url or "").lower().split("?", 1)[0]
    return path.startswith("http") and not path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"))


def _fetch(url: str) -> bytes:
    """Read a publisher list. Akamai answers Python with 403 and a browser with the file."""
    try:
        return _urlopen(url)
    except urllib.error.HTTPError as exc:
        if exc.code != 403:
            raise
        try:
            return _fetch_as_browser(url)
        except Exception:
            raise exc


def _urlopen(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def _fetch_as_browser(url: str) -> bytes:
    from curl_cffi import requests

    response = requests.get(url, impersonate="chrome", timeout=20)
    if response.status_code != 200:
        raise urllib.error.URLError(f"HTTP Error {response.status_code}")
    return response.content


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
