from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from rss_generator.feed import ATOM, MEDIA, read_existing_feed, write_feed
from rss_generator.scraper import Item


SOURCE = {"id": "municipio", "title": "Noticias", "description": "Actualidad", "url": "https://example.es/noticias", "language": "es-ES"}


def test_writes_feedly_compatible_rss_and_reads_it_back(tmp_path):
    path = tmp_path / "feeds" / "municipio.xml"
    item = Item("Titular", "https://example.es/noticias/1", "Resumen", datetime(2026, 8, 25, tzinfo=timezone.utc), "https://example.es/1.jpg")
    assert write_feed(SOURCE, [item, item], path, "https://owner.github.io/repo", 50) == 1
    root = ET.parse(path).getroot()
    channel = root.find("channel")
    assert channel.find(f"{{{ATOM}}}link").get("href") == "https://owner.github.io/repo/feeds/municipio.xml"
    assert channel.find("item/guid").get("isPermaLink") == "true"
    assert channel.find(f"item/{{{MEDIA}}}content").get("medium") == "image"
    assert read_existing_feed(path) == [item]


def test_limits_and_orders_entries(tmp_path):
    old = Item("Antigua", "https://example.es/old", published=datetime(2025, 1, 1, tzinfo=timezone.utc))
    new = Item("Nueva", "https://example.es/new", published=datetime(2026, 1, 1, tzinfo=timezone.utc))
    path = tmp_path / "feed.xml"
    write_feed(SOURCE, [old, new], path, "https://example.test", 1)
    assert ET.parse(path).findtext("./channel/item/title") == "Nueva"
