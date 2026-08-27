from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from .feed import read_existing_feed, write_feed
from .scraper import ScrapeError, enrich_items, scrape_source

LOG = logging.getLogger("rss-generator")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera un feed RSS por cada fuente configurada")
    parser.add_argument("--config", type=Path, default=Path("sources.json"))
    parser.add_argument("--output", type=Path, default=Path("site/feeds"))
    parser.add_argument("--base-url", default=os.environ.get("FEED_BASE_URL"))
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sources = json.loads(args.config.read_text(encoding="utf-8"))
    if not args.base_url:
        raise SystemExit("Indica --base-url o la variable FEED_BASE_URL")
    if args.limit < 1:
        raise SystemExit("--limit debe ser mayor que cero")

    args.output.mkdir(parents=True, exist_ok=True)
    failures = 0
    for source in sources:
        target = args.output / f"{source['id']}.xml"
        previous = read_existing_feed(target)
        try:
            current = scrape_source(source)
        except ScrapeError as error:
            if not previous:
                LOG.error("%s: %s", source["id"], error)
                failures += 1
                continue
            LOG.warning("%s: %s; se conserva el feed anterior", source["id"], error)
            current = []
        current_urls = {item.url for item in current}
        retained = [item for item in previous if item.url not in current_urls]
        summaries = [item for item in retained if not item.content]
        completed = [item for item in retained if item.content]
        if summaries and current:
            LOG.info("%s: completando %d entradas conservadas del feed anterior", source["id"], len(summaries))
            summaries = enrich_items(summaries)
        count = write_feed(source, [*current, *summaries, *completed], target, args.base_url, args.limit)
        LOG.info("%s: %d entradas escritas en %s", source["id"], count, target)
    return 1 if failures else 0
