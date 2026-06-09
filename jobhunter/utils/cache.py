"""Disk cache for fetched pages and validation fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import time


@dataclass(frozen=True)
class CacheEntry:
    key: str
    html_path: Path
    meta_path: Path


class PageCache:
    def __init__(self, root: str | Path = ".jobhunter_cache") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def entry_for(self, source: str, url: str) -> CacheEntry:
        digest = sha256(url.encode("utf-8")).hexdigest()
        directory = self.root / source
        directory.mkdir(parents=True, exist_ok=True)
        return CacheEntry(digest, directory / f"{digest}.html", directory / f"{digest}.json")

    def get(self, source: str, url: str, max_age_seconds: int | None = None) -> str | None:
        entry = self.entry_for(source, url)
        if not entry.html_path.exists() or not entry.meta_path.exists():
            return None
        if max_age_seconds is not None:
            try:
                metadata = json.loads(entry.meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
            if time.time() - float(metadata.get("fetched_at", 0)) > max_age_seconds:
                return None
        return entry.html_path.read_text(encoding="utf-8")

    def set(self, source: str, url: str, html: str, status_code: int = 200) -> CacheEntry:
        entry = self.entry_for(source, url)
        entry.html_path.write_text(html, encoding="utf-8")
        entry.meta_path.write_text(
            json.dumps({"url": url, "source": source, "status_code": status_code, "fetched_at": time.time()}, indent=2),
            encoding="utf-8",
        )
        return entry
