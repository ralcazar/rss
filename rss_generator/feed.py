from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET

from .scraper import Item

ATOM = "http://www.w3.org/2005/Atom"
CONTENT = "http://purl.org/rss/1.0/modules/content/"
MEDIA = "http://search.yahoo.com/mrss/"
ET.register_namespace("atom", ATOM)
ET.register_namespace("content", CONTENT)
ET.register_namespace("media", MEDIA)


def _text(parent: ET.Element, name: str, value: str) -> ET.Element:
    element = ET.SubElement(parent, name)
    element.text = value
    return element


def read_existing_feed(path: Path) -> list[Item]:
    if not path.exists():
        return []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    result = []
    for node in root.findall("./channel/item"):
        date = node.findtext("pubDate")
        image_node = node.find(f"{{{MEDIA}}}content")
        try:
            published = parsedate_to_datetime(date) if date else None
        except (TypeError, ValueError):
            published = None
        result.append(Item(node.findtext("title", ""), node.findtext("link", ""), node.findtext("description", ""), published, image_node.get("url") if image_node is not None else None))
    return result


def write_feed(source: dict[str, str], items: list[Item], target: Path, base_url: str, limit: int) -> int:
    feed_url = urljoin(base_url.rstrip("/") + "/", f"feeds/{quote(source['id'])}.xml")
    now = datetime.now(timezone.utc)
    unique: dict[str, Item] = {}
    for item in items:
        if item.url and item.title and item.url not in unique:
            unique[item.url] = item
    ordered = sorted(unique.values(), key=lambda item: item.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:limit]

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    _text(channel, "title", source["title"])
    _text(channel, "link", source["url"])
    _text(channel, "description", source["description"])
    _text(channel, "language", source.get("language", "es-ES"))
    _text(channel, "lastBuildDate", format_datetime(now, usegmt=True))
    _text(channel, "ttl", "240")
    _text(channel, "generator", "rss-pages")
    ET.SubElement(channel, f"{{{ATOM}}}link", {"href": feed_url, "rel": "self", "type": "application/rss+xml"})
    for entry in ordered:
        node = ET.SubElement(channel, "item")
        _text(node, "title", entry.title)
        _text(node, "link", entry.url)
        guid = _text(node, "guid", entry.url)
        guid.set("isPermaLink", "true")
        if entry.description:
            _text(node, "description", entry.description)
            _text(node, f"{{{CONTENT}}}encoded", entry.description)
        if entry.published:
            date = entry.published if entry.published.tzinfo else entry.published.replace(tzinfo=timezone.utc)
            _text(node, "pubDate", format_datetime(date.astimezone(timezone.utc), usegmt=True))
        if entry.image:
            ET.SubElement(node, f"{{{MEDIA}}}content", {"url": entry.image, "medium": "image"})
    ET.indent(rss, space="  ")
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(rss).write(target, encoding="utf-8", xml_declaration=True)
    return len(ordered)
