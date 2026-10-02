"""Rename Star{hex} frontier star cards in EfolsMiradinsPact to natural names."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
CANON = ROOT.parent / "EfolsMiradinsPact"

sys.path.insert(0, str(CATALOG_SERVICE))
sys.path.insert(0, str(CANON / "tools"))

from _gen_states_planets import EN_TO_RU  # noqa: E402
from app.service.frontier_naming import is_placeholder_star_label  # noqa: E402
from app.service.frontier_polities import (  # noqa: E402
    allocate_new_frontier_polities,
    load_locked_frontier_layout,
    map_canonical_frontier_catalog,
)
from app.service.spiral_geometry import generate_arm_objects  # noqa: E402

PLACEHOLDER_RE = re.compile(r"Star[0-9a-fA-F]{6,}")


def _rewrite_text(text: str, renames: dict[str, tuple[str, str, str]]) -> str:
    updated = text
    for old_token, (new_token, name_en, name_ru) in sorted(
        renames.items(),
        key=lambda item: -len(item[0]),
    ):
        old_ru = f"Звезда-{old_token}"
        pairs = (
            (f"[`{old_token}`]", f"[`{name_en}`]"),
            (f"[`{old_ru}`]", f"[`{name_ru}`]"),
            (f"# {old_token} / {old_ru}", f"# {name_en} / {name_ru}"),
            (f"# {old_ru} / {old_token}", f"# {name_ru} / {name_en}"),
            (f"# {old_token}", f"# {name_en}"),
            (f"# {old_ru}", f"# {name_ru}"),
            (f"`{old_token}`", f"`{new_token}`"),
            (f"/{old_token}.md", f"/{new_token}.md"),
            (old_ru, name_ru),
            (old_token, new_token),
        )
        for old, new in pairs:
            updated = updated.replace(old, new)
    return updated


def _rename_card(old_path: Path, new_path: Path, text: str) -> bool:
    if not old_path.is_file():
        return False
    if new_path == old_path:
        old_path.write_text(text, encoding="utf-8")
        return True
    if new_path.exists():
        old_path.unlink()
        return True
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(text, encoding="utf-8")
    old_path.unlink()
    return True


def main() -> int:
    objects = generate_arm_objects()
    _base, locked_clusters, locked_ownership = load_locked_frontier_layout(objects)
    _new_ownership, new_clusters = allocate_new_frontier_polities(
        objects,
        set(locked_ownership),
        locked_ownership,
    )
    clusters = {**locked_clusters, **new_clusters}
    catalog_path = (
        CATALOG_SERVICE / "app" / "data" / "frontier_polity_catalog.json"
    )
    raw_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    mapped = map_canonical_frontier_catalog(clusters)

    renames: dict[str, tuple[str, str, str]] = {}
    by_stem: dict[str, list[str]] = {}
    for stem, cluster in clusters.items():
        entries = sorted(
            (
                entry
                for entry in (raw_catalog.get(stem) or [])
                if entry.get("kind") == "star"
            ),
            key=lambda entry: entry.get("token") or "",
        )
        stars = sorted(
            (obj for obj in cluster if obj.kind == "star"),
            key=lambda obj: (obj.ordinal, obj.id),
        )
        for obj, entry in zip(stars, entries):
            old_token = entry.get("token") or ""
            if not is_placeholder_star_label(old_token, entry.get("nameEn")):
                continue
            mapped_entry = mapped[obj.id]
            renames[old_token] = (
                mapped_entry["token"],
                mapped_entry["nameEn"],
                mapped_entry["nameRu"],
            )
            by_stem.setdefault(stem, []).append(old_token)
            entry["token"] = mapped_entry["token"]
            entry["nameEn"] = mapped_entry["nameEn"]
            entry["nameRu"] = mapped_entry["nameRu"]

    catalog_path.write_text(
        json.dumps(raw_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    renamed_files = 0
    for stem, old_tokens in by_stem.items():
        ru_stem = EN_TO_RU[stem]
        for old_token in old_tokens:
            new_token, name_en, name_ru = renames[old_token]
            local = {old_token: (new_token, name_en, name_ru)}
            en_old = (
                CANON
                / "UNIVERSE"
                / "GALAXY"
                / "STARS"
                / "EN"
                / stem
                / "stars"
                / f"{old_token}.md"
            )
            en_new = en_old.with_name(f"{new_token}.md")
            if en_old.is_file():
                text = _rewrite_text(en_old.read_text(encoding="utf-8"), local)
                if _rename_card(en_old, en_new, text):
                    renamed_files += 1
            ru_old = (
                CANON
                / "UNIVERSE"
                / "GALAXY"
                / "STARS"
                / "RU"
                / ru_stem
                / "звёзды"
                / f"{old_token}.md"
            )
            ru_new = ru_old.with_name(f"{new_token}.md")
            if ru_old.is_file():
                text = _rewrite_text(ru_old.read_text(encoding="utf-8"), local)
                if _rename_card(ru_old, ru_new, text):
                    renamed_files += 1

    rewritten_files = 0
    for path in CANON.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not PLACEHOLDER_RE.search(text):
            continue
        updated = _rewrite_text(text, renames)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            rewritten_files += 1

    print(
        f"Renamed {len(renames)} placeholder stars; "
        f"{renamed_files} star cards; {rewritten_files} markdown references; "
        f"catalog updated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
