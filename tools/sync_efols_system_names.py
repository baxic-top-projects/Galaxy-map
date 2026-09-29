"""Sync unique API system names into EfolsMiradinsPact Markdown documents."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import requests


CANON = Path(r"D:\GitHub\EfolsMiradinsPact")
GALAXY_API = "http://galaxyapi.baxic.ru/api/v1/galaxy"
TITLE_RE = re.compile(r"(?m)^#\s+(.+?)\s*/\s*(.+?)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)#]+\.md)(#[^)]+)?\)")


def star_path(system: dict) -> Path | None:
    stem = system.get("canonicalStem") or system.get("stem")
    token = system.get("token")
    if not stem or not token or system.get("kind") != "star":
        return None
    return CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN" / stem / "stars" / f"{token}.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--links", action="store_true")
    args = parser.parse_args()
    galaxy = requests.get(GALAXY_API, timeout=60).json()

    desired: dict[Path, tuple[str, str]] = {}
    missing = []
    changed_titles = 0
    for system in galaxy.get("systems", []):
        path = star_path(system)
        if path is None:
            continue
        path = path.resolve()
        if not path.is_file():
            missing.append(str(path))
            continue
        text = path.read_text(encoding="utf-8")
        match = TITLE_RE.search(text)
        if not match:
            continue
        name_en = system.get("nameEn") or system["token"]
        name_ru = system.get("nameRu") or name_en
        desired[path] = (name_en, name_ru)
        if match.group(1).strip() == name_en and match.group(2).strip() == name_ru:
            continue
        changed_titles += 1
        if args.apply:
            text = text[:match.start()] + f"# {name_en} / {name_ru}" + text[match.end():]
            path.write_text(text, encoding="utf-8")

    changed_links = 0
    markdown_files = list(CANON.rglob("*.md")) if args.links else []
    for document in markdown_files:
        text = document.read_text(encoding="utf-8")

        def replace_link(match: re.Match) -> str:
            nonlocal changed_links
            raw_target = match.group(2)
            if "://" in raw_target:
                return match.group(0)
            try:
                target = (document.parent / raw_target).resolve()
            except OSError:
                return match.group(0)
            names = desired.get(target)
            if names is None:
                return match.group(0)
            old_label = match.group(1)
            wrapped = old_label.startswith("`") and old_label.endswith("`")
            new_label = f"`{names[0]}`" if wrapped else names[0]
            if new_label == old_label:
                return match.group(0)
            changed_links += 1
            return f"[{new_label}]({match.group(2)}{match.group(3) or ''})"

        updated = LINK_RE.sub(replace_link, text)
        if args.apply and updated != text:
            document.write_text(updated, encoding="utf-8")

    mode = "Updated" if args.apply else "Would update"
    print(
        f"{mode} {changed_titles} star titles and {changed_links} Markdown links; "
        f"{len(missing)} missing star cards"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
