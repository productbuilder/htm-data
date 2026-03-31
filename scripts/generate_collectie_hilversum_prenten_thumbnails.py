#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PRENTEN_DIR = ROOT / "dev" / "org" / "collectie-hilversum" / "prenten"
MANIFEST_PATH = PRENTEN_DIR / "collection.json"
THUMB_BASE_URL = (
    "https://raw.githubusercontent.com/productbuilder/htm-data/main/"
    "dev/org/collectie-hilversum/prenten/"
)
MAX_DIMENSION = 200
JPEG_QUALITY = 82


def is_source_image(path: Path) -> bool:
    lower = path.name.lower()
    return path.is_file() and lower.endswith((".jpg", ".jpeg")) and not lower.endswith(".thumb.jpg")


def is_valid_thumbnail(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with Image.open(path) as img:
            w, h = img.size
            return img.format == "JPEG" and max(w, h) <= MAX_DIMENSION
    except Exception:
        return False


def create_thumbnail(source: Path, target: Path) -> None:
    with Image.open(source) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)


def generate_thumbnails(prenten_dir: Path) -> Tuple[int, int, int]:
    created = 0
    skipped_valid = 0
    regenerated = 0

    for source in sorted(p for p in prenten_dir.iterdir() if is_source_image(p)):
        target = source.with_name(f"{source.stem}.thumb.jpg")
        if is_valid_thumbnail(target):
            skipped_valid += 1
            continue

        existed = target.exists()
        create_thumbnail(source, target)
        if existed:
            regenerated += 1
        else:
            created += 1

    return created, regenerated, skipped_valid


def url_basename(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    return Path(path).name


def update_manifest(manifest_path: Path, prenten_dir: Path) -> Tuple[int, int, List[Dict[str, str]]]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = data.get("items", [])

    files_by_lower: Dict[str, List[str]] = {}
    for p in prenten_dir.iterdir():
        if is_source_image(p):
            files_by_lower.setdefault(p.name.lower(), []).append(p.name)

    updated = 0
    unchanged = 0
    unmatched: List[Dict[str, str]] = []

    for item in items:
        media = item.get("media")
        if not isinstance(media, dict):
            unmatched.append({"id": item.get("id", ""), "reason": "missing media"})
            continue

        source_url = media.get("url")
        if not isinstance(source_url, str) or not source_url:
            unmatched.append({"id": item.get("id", ""), "reason": "missing media.url"})
            continue

        basename = url_basename(source_url)
        if not basename:
            unmatched.append({"id": item.get("id", ""), "reason": "media.url has no filename"})
            continue

        matches = files_by_lower.get(basename.lower(), [])
        if len(matches) != 1:
            reason = "source image not found" if len(matches) == 0 else "ambiguous source filename"
            unmatched.append(
                {
                    "id": item.get("id", ""),
                    "source": basename,
                    "reason": reason,
                }
            )
            continue

        source_name = matches[0]
        stem = Path(source_name).stem
        target_thumb_url = f"{THUMB_BASE_URL}{stem}.thumb.jpg"

        if media.get("thumbnailUrl") != target_thumb_url:
            media["thumbnailUrl"] = target_thumb_url
            updated += 1
        else:
            unchanged += 1

    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return updated, unchanged, unmatched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate .thumb.jpg files for Collectie Hilversum prenten and update manifest thumbnailUrl values."
    )
    parser.add_argument(
        "--prenten-dir",
        type=Path,
        default=PRENTEN_DIR,
        help=f"Path to prenten directory (default: {PRENTEN_DIR})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help=f"Path to collection manifest (default: {MANIFEST_PATH})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prenten_dir = args.prenten_dir.resolve()
    manifest_path = args.manifest.resolve()

    created, regenerated, skipped_valid = generate_thumbnails(prenten_dir)
    updated, unchanged, unmatched = update_manifest(manifest_path, prenten_dir)

    print(f"prenten_dir: {prenten_dir}")
    print(f"manifest: {manifest_path}")
    print(f"thumbnails_created: {created}")
    print(f"thumbnails_regenerated: {regenerated}")
    print(f"thumbnails_skipped_valid: {skipped_valid}")
    print(f"manifest_items_updated: {updated}")
    print(f"manifest_items_unchanged: {unchanged}")
    print(f"manifest_items_unmatched: {len(unmatched)}")
    if unmatched:
        print("unmatched_items:")
        for entry in unmatched:
            source = entry.get("source", "")
            source_part = f" source={source}" if source else ""
            print(f"- id={entry.get('id', '')}{source_part} reason={entry.get('reason', '')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

