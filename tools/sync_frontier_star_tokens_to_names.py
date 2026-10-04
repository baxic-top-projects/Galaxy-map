"""Align frontier star tokens with their display names (Corvuth Altair → CorvuthAltair).

Updates frontier_polity_catalog.json and renames/rewrites EfolsMiradinsPact star cards
so the HUD signature matches the title pair (like NoxAbyss / Бездна Нокс).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVICE = ROOT / "server" / "services" / "catalog-service"
CANON = ROOT.parent / "EfolsMiradinsPact"

sys.path.insert(0, str(CANON / "tools"))

from _gen_states_planets import EN_TO_RU  # noqa: E402

CATALOG_PATH = CATALOG_SERVICE / "app" / "data" / "frontier_polity_catalog.json"


def compact_token(name_en: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", name_en or "")


def _rewrite_text(text: str, renames: dict[str, tuple[str, str, str]]) -> str:
    updated = text
    for old_token, (new_token, name_en, name_ru) in sorted(
        renames.items(),
        key=lambda item: -len(item[0]),
    ):
        pairs = (
            (f"[`{old_token}`]", f"[`{name_en}`]"),
            (f"# {old_token}", f"# {name_en}"),
            (f"`{old_token}`", f"`{new_token}`"),
            (f"/{old_token}.md", f"/{new_token}.md"),
            (f"({old_token})", f"({new_token})"),
            (f":{old_token}", f":{new_token}"),
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
        new_path.write_text(text, encoding="utf-8")
        old_path.unlink()
        return True
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(text, encoding="utf-8")
    old_path.unlink()
    return True


def main() -> int:
    if not CANON.is_dir():
        raise SystemExit(f"Canon repo not found: {CANON}")
    raw_catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    renames: dict[str, tuple[str, str, str]] = {}
    by_stem: dict[str, list[str]] = {}
    used = {
        entry.get("token") or ""
        for entries in raw_catalog.values()
        for entry in entries
    }

    for stem, entries in raw_catalog.items():
        for entry in entries:
            if entry.get("kind") != "star":
                continue
            old_token = entry.get("token") or ""
            name_en = (entry.get("nameEn") or "").strip()
            name_ru = (entry.get("nameRu") or "").strip()
            if not old_token or not name_en:
                continue
            new_token = compact_token(name_en)
            if not new_token or new_token == old_token:
                continue
            if new_token in used and new_token != old_token:
                raise RuntimeError(
                    f"Token collision: {old_token} → {new_token} already used"
                )
            used.discard(old_token)
            used.add(new_token)
            renames[old_token] = (new_token, name_en, name_ru)
            by_stem.setdefault(stem, []).append(old_token)
            entry["token"] = new_token
            if entry.get("canonicalId"):
                prefix = str(entry["canonicalId"]).rsplit(":", 1)[0]
                entry["canonicalId"] = f"{prefix}:{new_token}"

    CATALOG_PATH.write_text(
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
                # Keep Status Token line explicit.
                text = re.sub(
                    r"(?m)^(- Token:\s*`).*?(`)\s*$",
                    rf"\g<1>{new_token}\2",
                    text,
                )
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
                text = re.sub(
                    r"(?m)^(- Token:\s*`).*?(`)\s*$",
                    rf"\g<1>{new_token}\2",
                    text,
                )
                if _rename_card(ru_old, ru_new, text):
                    renamed_files += 1

    rewritten_files = 0
    for path in CANON.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not any(old in text for old in renames):
            continue
        updated = _rewrite_text(text, renames)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            rewritten_files += 1

    sample = renames.get("OssiZephith0c3")
    print(
        f"Renamed {len(renames)} star tokens; "
        f"{renamed_files} star cards; {rewritten_files} markdown references; "
        f"catalog updated"
    )
    if sample:
        print(f"Sample: OssiZephith0c3 → {sample[0]} ({sample[1]} / {sample[2]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
