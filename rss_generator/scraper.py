from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, Tag

LOG = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (compatible; rss-pages/1.0; +https://github.com/)"
SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


class ScrapeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Item:
    title: str
    url: str
    description: str = ""
    published: datetime | None = None
    image: str | None = None
    content: str = ""
    images: tuple[str, ...] = ()
    videos: tuple[str, ...] = ()


DETAIL_SELECTORS = (
    "article.template-detail-noticia",
    ".journal-content-article article",
    "[itemprop='articleBody']",
    ".article-body",
    ".entry-content",
    ".post-content",
    "main article",
)
IMAGE_URL = re.compile(r"\.(?:avif|gif|jpe?g|png|svg|webp)(?:[/?#]|$)", re.IGNORECASE)
VIDEO_URL = re.compile(r"\.(?:m3u8|m4v|mov|mp4|mpeg|ogv|webm)(?:[/?#]|$)", re.IGNORECASE)
VIDEO_PAGE = re.compile(r"(?:youtu\.be|youtube(?:-nocookie)?\.com|vimeo\.com|seneca\.tv)", re.IGNORECASE)


def canonical_url(url: str, base: str) -> str:
    absolute = urljoin(base, url)
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", "", ""))


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    clean = value.strip()
    spanish = re.fullmatch(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{2}|\d{4})", clean.casefold())
    if spanish and spanish.group(2) in SPANISH_MONTHS:
        year = int(spanish.group(3))
        if year < 100:
            year += 2000
        try:
            return datetime(year, SPANISH_MONTHS[spanish.group(2)], int(spanish.group(1)), tzinfo=timezone.utc)
        except ValueError:
            return None
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


def _absolute_url(value: str | None, base: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value or value.startswith(("data:", "javascript:", "#")):
        return None
    return urljoin(base, value)


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _normalize_article(root: Tag, base: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Make an article self-contained and return all of its media URLs."""
    for unwanted in root.select("script, style, noscript, template, form, button"):
        unwanted.decompose()

    images: list[str] = []
    videos: list[str] = []
    for tag in root.find_all(True):
        for attribute in tuple(tag.attrs):
            if attribute.casefold().startswith("on"):
                del tag.attrs[attribute]

        if tag.name == "img":
            source = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src")
            parent = tag.parent
            if isinstance(parent, Tag) and parent.name == "a" and IMAGE_URL.search(str(parent.get("href", ""))):
                source = parent.get("href")
            absolute = _absolute_url(str(source), base) if source else None
            if absolute:
                tag["src"] = absolute
                images.append(absolute)
            for lazy_attribute in ("data-src", "data-lazy-src"):
                tag.attrs.pop(lazy_attribute, None)

        is_video_source = tag.name == "source" and (
            (isinstance(tag.parent, Tag) and tag.parent.name in {"audio", "video"})
            or VIDEO_URL.search(str(tag.get("src", ""))) is not None
        )
        if tag.name in {"iframe", "video"} or is_video_source:
            source = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src")
            absolute = _absolute_url(str(source), base) if source else None
            if absolute:
                tag["src"] = absolute
                videos.append(absolute)
            tag.attrs.pop("data-src", None)
            tag.attrs.pop("data-lazy-src", None)

        poster = _absolute_url(str(tag.get("poster")), base) if tag.get("poster") else None
        if poster:
            tag["poster"] = poster
            images.append(poster)

        if tag.name == "a" and tag.get("href"):
            href = _absolute_url(str(tag["href"]), base)
            if href:
                tag["href"] = href
                if IMAGE_URL.search(href):
                    images.append(href)
                elif VIDEO_URL.search(href) or VIDEO_PAGE.search(href):
                    videos.append(href)

        if tag.get("srcset"):
            candidates = []
            for candidate in str(tag["srcset"]).split(","):
                parts = candidate.strip().split()
                absolute = _absolute_url(parts[0], base) if parts else None
                if absolute:
                    candidates.append(" ".join((absolute, *parts[1:])))
            if candidates:
                tag["srcset"] = ", ".join(candidates)

    return str(root), _unique(images), _unique(videos)


def _from_detail(soup: BeautifulSoup, base: str, item: Item) -> Item:
    root = next((soup.select_one(selector) for selector in DETAIL_SELECTORS if soup.select_one(selector)), None)
    if not isinstance(root, Tag):
        return item
    content, images, videos = _normalize_article(root, base)
    if not root.get_text(" ", strip=True):
        return item
    primary = images[0] if images else item.image
    return replace(
        item,
        image=primary,
        content=content,
        images=tuple(image for image in images if image != primary),
        videos=videos,
    )


def _from_html(soup: BeautifulSoup, base: str) -> list[Item]:
    containers = soup.select("article, .views-row, .noticia, .news-item, .card")
    if not containers:
        containers = [a.parent for a in soup.select('a[href*="/noticias/"]') if isinstance(a.parent, Tag)]
    items: list[Item] = []
    for node in containers:
        link = node.select_one("h1 a[href], h2 a[href], h3 a[href]")
        if link is None:
            link = node.select_one("a.card-title[href]")
        if link is None:
            link = node.select_one('a[href*="/noticias/"], a[href*="/-/"]')
        if not link or not link.get("href"):
            continue
        title = link.get_text(" ", strip=True) or link.get("title", "").strip()
        if not title:
            continue
        time = node.select_one("time")
        date_value = (time.get("datetime") if time else None) or _first_text(node, (".date", ".fecha", ".field--name-field-fecha"))
        image_node = node.select_one("img[src], img[data-src]")
        image = (image_node.get("src") or image_node.get("data-src")) if image_node else None
        description = _first_text(node, (".summary", ".entradilla", ".field--name-body", ".card-text", "p"))
        items.append(Item(title, canonical_url(str(link["href"]), base), description, parse_date(date_value), urljoin(base, image) if image else None))
    return items


def enrich_items(items: list[Item]) -> list[Item]:
    """Download the detail page for items that only contain a listing summary."""
    def enrich(item: Item) -> Item:
        try:
            detail = requests.get(item.url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}, timeout=(10, 30))
            detail.raise_for_status()
        except requests.RequestException as error:
            LOG.warning("no se pudo descargar el texto completo de %s: %s", item.url, error)
            return item
        return _from_detail(BeautifulSoup(detail.text, "html.parser"), item.url, item)

    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(4, len(items))) as executor:
        return list(executor.map(enrich, items))


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
    return enrich_items(list(unique.values()))
