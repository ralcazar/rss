from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def main() -> int:
    directory = Path(sys.argv[1])
    feeds = list(directory.glob("*.xml"))
    if not feeds:
        raise SystemExit("No se generó ningún feed")
    for path in feeds:
        root = ET.parse(path).getroot()
        if root.tag != "rss" or root.get("version") != "2.0":
            raise SystemExit(f"{path} no es RSS 2.0")
        channel = root.find("channel")
        if channel is None or not channel.findall("item"):
            raise SystemExit(f"{path} no contiene noticias")
        required = ("title", "link", "description", "language", "lastBuildDate")
        missing = [name for name in required if not channel.findtext(name)]
        if missing:
            raise SystemExit(f"{path}: faltan {', '.join(missing)}")
        print(f"OK: {path} ({len(channel.findall('item'))} noticias)")
    return 0


raise SystemExit(main())
