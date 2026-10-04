"""Align every EN star card Token + filename with compact H1 English name.

Rule: token == English star name (Corvuth Altair → CorvuthAltair, Duskothluum → Duskothluum).
Rewrites are scoped per polity so shared short stems (Duskoth) do not collide across states.
Also updates matching RU star files and frontier_polity_catalog.json when present.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT.parent / "EfolsMiradinsPact"
CATALOG_PATH = (
    ROOT
    / "server"
    / "services"
    / "catalog-service"
    / "app"
    / "data"
    / "frontier_polity_catalog.json"
)

TOKEN_RE = re.compile(r"(?m)^(- Token:\s*`)[^`]+(`)\s*$")
H1_RE = re.compile(r"(?m)^#\s+(.+)$")


def compact_token(name_en: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", name_en or "")


def h1_en(text: str) -> str:
    m = H1_RE.search(text)
    if not m:
        return ""
    return m.group(1).split("/", 1)[0].strip()


def apply_renames(text: str, renames: dict[str, str]) -> str:
    """Replace old→new tokens without substring damage (longest first)."""
    if not renames:
        return text
    updated = text
    for old, new in sorted(renames.items(), key=lambda kv: -len(kv[0])):
        if old == new:
            continue
        # Markdown / code forms first, then bare token as whole word.
        pairs = (
            (f"[`{old}`]", f"[`{new}`]"),
            (f"]({old}.md)", f"]({new}.md)"),
            (f"](stars/{old}.md)", f"](stars/{new}.md)"),
            (f"/{old}.md", f"/{new}.md"),
            (f"`{old}`", f"`{new}`"),
            (f"({old})", f"({new})"),
            (f":{old}", f":{new}"),
        )
        for a, b in pairs:
            updated = updated.replace(a, b)
        updated = re.sub(rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])", new, updated)
    return updated


def set_token_line(text: str, new_token: str) -> str:
    if TOKEN_RE.search(text):
        return TOKEN_RE.sub(rf"\g<1>{new_token}\2", text)
    # Insert under ## Status if present.
    if re.search(r"(?m)^## Status\s*$", text):
        return re.sub(
            r"(?m)^(## Status\s*\n)",
            rf"\1- Token: `{new_token}`\n",
            text,
            count=1,
        )
    return text + f"\n- Token: `{new_token}`\n"


def rename_file(old: Path, new: Path, text: str) -> None:
    new.parent.mkdir(parents=True, exist_ok=True)
    if new == old:
        old.write_text(text, encoding="utf-8")
        return
    if new.exists():
        new.write_text(text, encoding="utf-8")
        if old.exists() and old.resolve() != new.resolve():
            old.unlink()
        return
    old.write_text(text, encoding="utf-8")
    old.rename(new)


def sync_polity_stars(stars_dir: Path) -> tuple[int, int]:
    """Returns (renamed_or_rewritten_cards, reference_files_touched)."""
    files = sorted(stars_dir.glob("*.md"))
    if not files:
        return 0, 0

    plan: list[tuple[Path, str, str, str]] = []  # path, old_stem, new_token, text
    renames: dict[str, str] = {}
    used_new: dict[str, Path] = {}

    for path in files:
        text = path.read_text(encoding="utf-8")
        en = h1_en(text)
        new_token = compact_token(en)
        if not new_token:
            continue
        old_stem = path.stem
        m = re.search(r"(?m)^- Token:\s*`([^`]+)`", text)
        old_token = m.group(1) if m else old_stem
        if new_token in used_new and used_new[new_token] != path:
            raise RuntimeError(
                f"Collision in {stars_dir}: {used_new[new_token].name} and "
                f"{path.name} both want {new_token}"
            )
        used_new[new_token] = path
        if old_stem != new_token:
            renames[old_stem] = new_token
        if old_token != new_token and old_token != old_stem:
            renames[old_token] = new_token
        plan.append((path, old_stem, new_token, text))

    if not any(old != new for _p, old, new, _t in plan) and not renames:
        # Still ensure Token lines match even if filenames already ok.
        changed = 0
        for path, _old, new_token, text in plan:
            updated = set_token_line(text, new_token)
            if updated != text:
                path.write_text(updated, encoding="utf-8")
                changed += 1
        return changed, 0

    # Two-phase rename to avoid clobbering.
    temps: list[tuple[Path, Path, str]] = []  # temp, final, text
    for path, old_stem, new_token, text in plan:
        updated = set_token_line(apply_renames(text, renames), new_token)
        if old_stem == new_token:
            if updated != text:
                path.write_text(updated, encoding="utf-8")
            continue
        temp = path.with_name(f"__tmp__{new_token}__.md")
        rename_file(path, temp, updated)
        temps.append((temp, path.with_name(f"{new_token}.md"), updated))

    for temp, final, text in temps:
        rename_file(temp, final, text)

    # Rewrite references in the rest of this polity tree (EN).
    polity_dir = stars_dir.parent
    ref_touched = 0
    for path in polity_dir.rglob("*.md"):
        if path.parent == stars_dir and path.name.startswith("__tmp__"):
            continue
        text = path.read_text(encoding="utf-8")
        updated = apply_renames(text, renames)
        # Token lines inside star cards already set; still safe.
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            ref_touched += 1

    return len(plan), ref_touched


def sync_ru_stars(en_stem: str, renames: dict[str, str]) -> int:
    """Best-effort RU mirror rename using EN_TO_RU when available."""
    try:
        sys.path.insert(0, str(CANON / "tools"))
        from _gen_states_planets import EN_TO_RU  # type: ignore
    except Exception:
        return 0
    ru_stem = EN_TO_RU.get(en_stem)
    if not ru_stem or not renames:
        return 0
    ru_dir = CANON / "UNIVERSE" / "GALAXY" / "STARS" / "RU" / ru_stem / "звёзды"
    if not ru_dir.is_dir():
        # fallback ascii folder name variants
        candidates = list((CANON / "UNIVERSE" / "GALAXY" / "STARS" / "RU").glob("*"))
        ru_dir = None
        for c in candidates:
            if c.name == ru_stem:
                for sub in ("звёзды", "звезды", "stars"):
                    d = c / sub
                    if d.is_dir():
                        ru_dir = d
                        break
        if ru_dir is None:
            return 0

    touched = 0
    # Rename files first via temp
    temps = []
    for old, new in renames.items():
        old_path = ru_dir / f"{old}.md"
        if not old_path.is_file():
            continue
        text = set_token_line(apply_renames(old_path.read_text(encoding="utf-8"), renames), new)
        temp = ru_dir / f"__tmp__{new}__.md"
        rename_file(old_path, temp, text)
        temps.append((temp, ru_dir / f"{new}.md", text))
        touched += 1
    for temp, final, text in temps:
        rename_file(temp, final, text)

    polity_ru = ru_dir.parent
    for path in polity_ru.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        updated = apply_renames(text, renames)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            touched += 1
    return touched


def sync_frontier_catalog() -> int:
    if not CATALOG_PATH.is_file():
        return 0
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    changed = 0
    for _stem, entries in data.items():
        for entry in entries:
            if entry.get("kind") != "star":
                continue
            name_en = (entry.get("nameEn") or "").strip()
            new_token = compact_token(name_en)
            old = entry.get("token") or ""
            if not new_token or new_token == old:
                continue
            entry["token"] = new_token
            if entry.get("canonicalId"):
                prefix = str(entry["canonicalId"]).rsplit(":", 1)[0]
                entry["canonicalId"] = f"{prefix}:{new_token}"
            changed += 1
    if changed:
        CATALOG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def main() -> int:
    en_root = CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN"
    if not en_root.is_dir():
        raise SystemExit(f"Missing {en_root}")

    cards = 0
    refs = 0
    polities = 0
    for polity_dir in sorted(p for p in en_root.iterdir() if p.is_dir()):
        stars_dir = polity_dir / "stars"
        if not stars_dir.is_dir():
            continue
        # Capture renames for RU before mutating by re-reading plan lightly
        pre = {}
        for path in stars_dir.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            new_token = compact_token(h1_en(text))
            if new_token and path.stem != new_token:
                pre[path.stem] = new_token
            m = re.search(r"(?m)^- Token:\s*`([^`]+)`", text)
            if m and new_token and m.group(1) != new_token:
                pre[m.group(1)] = new_token

        c, r = sync_polity_stars(stars_dir)
        if c or r or pre:
            polities += 1
        cards += c
        refs += r
        refs += sync_ru_stars(polity_dir.name, pre)

    cat = sync_frontier_catalog()
    print(
        f"Polities touched: {polities}; star cards processed: {cards}; "
        f"ref updates≈{refs}; frontier catalog token fixes: {cat}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
