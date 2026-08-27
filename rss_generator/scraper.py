from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, Tag

LOG = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (compatible; rss-pages/1.0; +https://github.com/)"


class ScrapeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Item:
    title: str
    url: str
    description: str = ""
    published: datetime | None = None
    image: str | None = None


def canonical_url(url: str, base: str) -> str:
    absolute = urljoin(base, url)
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", "", ""))


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    clean = value.strip()
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(clean)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_nodes(value: Any):
    if isinstance(value, list):
        for child in value:
            yield from _json_nodes(child)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from _json_nodes(value["@graph"])


def _from_json_ld(soup: BeautifulSoup, base: str) -> list[Item]:
    items: list[Item] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _json_nodes(data):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if not set(types) & {"NewsArticle", "Article", "BlogPosting"}:
                continue
            title = node.get("headline") or node.get("name")
            url = node.get("url") or node.get("mainEntityOfPage")
            if isinstance(url, dict):
                url = url.get("@id")
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url") or image.get("@id")
            if title and url:
                items.append(Item(str(title).strip(), canonical_url(str(url), base), str(node.get("description", "")).strip(), parse_date(node.get("datePublished")), urljoin(base, image) if image else None))
    return items


def _first_text(node: Tag, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        found = node.select_one(selector)
        if found and found.get_text(" ", strip=True):
            return found.get_text(" ", strip=True)
    return ""


def _from_html(soup: BeautifulSoup, base: str) -> list[Item]:
    containers = soup.select("article, .views-row, .noticia, .news-item, .card")
    if not containers:
        containers = [a.parent for a in soup.select('a[href*="/noticias/"]') if isinstance(a.parent, Tag)]
    items: list[Item] = []
    for node in containers:
        link = node.select_one('h1 a[href], h2 a[href], h3 a[href], a[href*="/noticias/"]')
        if not link or not link.get("href"):
            continue
        title = link.get_text(" ", strip=True) or link.get("title", "").strip()
        if not title:
            continue
        time = node.select_one("time")
        date_value = (time.get("datetime") if time else None) or _first_text(node, (".date", ".fecha", ".field--name-field-fecha"))
        image_node = node.select_one("img[src], img[data-src]")
        image = (image_node.get("src") or image_node.get("data-src")) if image_node else None
        description = _first_text(node, (".summary", ".entradilla", ".field--name-body", "p"))
        items.append(Item(title, canonical_url(str(link["href"]), base), description, parse_date(date_value), urljoin(base, image) if image else None))
    return items


def scrape_source(source: dict[str, str]) -> list[Item]:
    try:
        response = requests.get(source["url"], headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}, timeout=(10, 30))
        response.raise_for_status()
    except requests.RequestException as error:
        raise ScrapeError(f"no se pudo descargar {source['url']}: {error}") from error
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = [*_from_json_ld(soup, source["url"]), *_from_html(soup, source["url"])]
    unique = {item.url: item for item in candidates}
    if not unique:
        raise ScrapeError("la página no contiene noticias reconocibles")
    return list(unique.values())
