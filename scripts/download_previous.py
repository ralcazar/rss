from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for source in json.loads(args.config.read_text(encoding="utf-8")):
        url = f"{args.base_url.rstrip('/')}/feeds/{source['id']}.xml"
        try:
            with urlopen(Request(url, headers={"User-Agent": "rss-pages/1.0"}), timeout=20) as response:
                data = response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            print(f"No se recuperó {url}: {error}")
            continue
        (args.output / f"{source['id']}.xml").write_bytes(data)
    return 0


raise SystemExit(main())
