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
        media_nodes = node.findall(f"{{{MEDIA}}}content")
        images = [media.get("url", "") for media in media_nodes if media.get("medium") == "image" and media.get("url")]
        videos = [media.get("url", "") for media in media_nodes if media.get("medium") == "video" and media.get("url")]
        description = node.findtext("description", "")
        content = node.findtext(f"{{{CONTENT}}}encoded", "")
        # Older feeds used content:encoded for the plain listing summary too.
        # Detail content is HTML, so keeping only HTML here lets the CLI migrate
        # old summaries once without re-downloading completed articles forever.
        stored_content = content if "<" in content and ">" in content else ""
        try:
            published = parsedate_to_datetime(date) if date else None
        except (TypeError, ValueError):
            published = None
        result.append(
            Item(
                node.findtext("title", ""),
                node.findtext("link", ""),
                description,
                published,
                images[0] if images else None,
                stored_content,
                tuple(images[1:]),
                tuple(videos),
            )
        )
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
        full_content = entry.content or entry.description
        if full_content:
            # Some clients only render description, while others prefer content:encoded.
            # Publishing the complete HTML in both prevents either client from truncating it.
            _text(node, "description", full_content)
            _text(node, f"{{{CONTENT}}}encoded", full_content)
        if entry.published:
            date = entry.published if entry.published.tzinfo else entry.published.replace(tzinfo=timezone.utc)
            _text(node, "pubDate", format_datetime(date.astimezone(timezone.utc), usegmt=True))
        for image in dict.fromkeys(filter(None, (entry.image, *entry.images))):
            ET.SubElement(node, f"{{{MEDIA}}}content", {"url": image, "medium": "image"})
        for video in dict.fromkeys(entry.videos):
            media = ET.SubElement(node, f"{{{MEDIA}}}content", {"url": video, "medium": "video"})
            ET.SubElement(media, f"{{{MEDIA}}}player", {"url": video})
    ET.indent(rss, space="  ")
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(rss).write(target, encoding="utf-8", xml_declaration=True)
    return len(ordered)
