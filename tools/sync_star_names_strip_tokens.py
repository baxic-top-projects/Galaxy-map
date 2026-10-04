"""Efols star cards: identity = English name only (no Token field).

- Rename stars/<file>.md to compact(H1 EN) when needed (per-polity, safe refs)
- Strip `- Token:` / `- Токен:` lines from EN/RU star cards
- Align frontier_polity_catalog.json map-side token with compact(nameEn)

Map/API keeps its own token (= English compact name). Canon cards do not.
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

H1_RE = re.compile(r"(?m)^#\s+(.+)$")
TOKEN_LINE_RE = re.compile(r"(?m)^-\s*(?:Token|Токен)\s*:\s*.+\n?")


def compact_token(name_en: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", name_en or "")


def h1_en(text: str) -> str:
    m = H1_RE.search(text)
    if not m:
        return ""
    return m.group(1).split("/", 1)[0].strip()


def strip_token_lines(text: str) -> str:
    return TOKEN_LINE_RE.sub("", text)


def apply_renames(text: str, renames: dict[str, str]) -> str:
    if not renames:
        return text
    updated = text
    for old, new in sorted(renames.items(), key=lambda kv: -len(kv[0])):
        if old == new:
            continue
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
        updated = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])",
            new,
            updated,
        )
    return updated


def rename_file(old: Path, new: Path, text: str) -> None:
    new.parent.mkdir(parents=True, exist_ok=True)
    if new.resolve() == old.resolve():
        old.write_text(text, encoding="utf-8", newline="\n")
        return
    if new.exists():
        new.write_text(text, encoding="utf-8", newline="\n")
        if old.exists():
            old.unlink()
        return
    old.write_text(text, encoding="utf-8", newline="\n")
    old.rename(new)


def sync_stars_dir(stars_dir: Path) -> tuple[int, int, dict[str, str]]:
    files = sorted(stars_dir.glob("*.md"))
    if not files:
        return 0, 0, {}

    plan: list[tuple[Path, str, str, str]] = []
    renames: dict[str, str] = {}
    used: dict[str, Path] = {}

    for path in files:
        if path.name.startswith("__tmp__"):
            continue
        text = path.read_text(encoding="utf-8")
        new_name = compact_token(h1_en(text))
        if not new_name:
            # still strip tokens
            stripped = strip_token_lines(text)
            if stripped != text:
                path.write_text(stripped, encoding="utf-8", newline="\n")
            continue
        if new_name in used and used[new_name] != path:
            raise RuntimeError(
                f"Collision in {stars_dir}: {used[new_name].name} vs {path.name} → {new_name}"
            )
        used[new_name] = path
        if path.stem != new_name:
            renames[path.stem] = new_name
        plan.append((path, path.stem, new_name, text))

    rewritten = 0
    temps: list[tuple[Path, Path, str]] = []
    for path, old_stem, new_name, text in plan:
        updated = strip_token_lines(apply_renames(text, renames))
        if old_stem == new_name:
            if updated != text:
                path.write_text(updated, encoding="utf-8", newline="\n")
                rewritten += 1
            continue
        temp = path.with_name(f"__tmp__{new_name}__.md")
        rename_file(path, temp, updated)
        temps.append((temp, path.with_name(f"{new_name}.md"), updated))
        rewritten += 1

    for temp, final, text in temps:
        rename_file(temp, final, text)

    ref_touched = 0
    polity_dir = stars_dir.parent
    if renames:
        for path in polity_dir.rglob("*.md"):
            if "__tmp__" in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            updated = apply_renames(text, renames)
            if path.parent == stars_dir:
                updated = strip_token_lines(updated)
            if updated != text:
                path.write_text(updated, encoding="utf-8", newline="\n")
                ref_touched += 1

    return rewritten, ref_touched, renames


def sync_ru_for_polity(en_stem: str, renames: dict[str, str]) -> int:
    try:
        sys.path.insert(0, str(CANON / "tools"))
        from _gen_states_planets import EN_TO_RU  # type: ignore
    except Exception:
        return 0
    ru_stem = EN_TO_RU.get(en_stem)
    if not ru_stem:
        return 0
    ru_root = CANON / "UNIVERSE" / "GALAXY" / "STARS" / "RU" / ru_stem
    if not ru_root.is_dir():
        return 0
    stars_dir = None
    for sub in ("звёзды", "звезды", "stars"):
        d = ru_root / sub
        if d.is_dir():
            stars_dir = d
            break
    if stars_dir is None:
        return 0

    touched = 0
    # Strip token lines on all RU star cards; rename when mapping known
    temps = []
    for path in sorted(stars_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        new_name = renames.get(path.stem)
        updated = strip_token_lines(apply_renames(text, renames) if renames else text)
        if new_name and new_name != path.stem:
            temp = stars_dir / f"__tmp__{new_name}__.md"
            rename_file(path, temp, updated)
            temps.append((temp, stars_dir / f"{new_name}.md", updated))
            touched += 1
        elif updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
            touched += 1
    for temp, final, text in temps:
        rename_file(temp, final, text)

    if renames:
        for path in ru_root.rglob("*.md"):
            if path.parent == stars_dir:
                continue
            text = path.read_text(encoding="utf-8")
            updated = apply_renames(text, renames)
            if updated != text:
                path.write_text(updated, encoding="utf-8", newline="\n")
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

    cards = refs = ru = 0
    for polity_dir in sorted(p for p in en_root.iterdir() if p.is_dir()):
        stars_dir = polity_dir / "stars"
        if not stars_dir.is_dir():
            continue
        c, r, renames = sync_stars_dir(stars_dir)
        cards += c
        refs += r
        ru += sync_ru_for_polity(polity_dir.name, renames)

    # Final pass: strip any remaining Token lines in all star cards
    stripped = 0
    for path in en_root.rglob("stars/*.md"):
        text = path.read_text(encoding="utf-8")
        updated = strip_token_lines(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
            stripped += 1
    ru_root = CANON / "UNIVERSE" / "GALAXY" / "STARS" / "RU"
    if ru_root.is_dir():
        for path in ru_root.rglob("*.md"):
            if path.parent.name not in {"звёзды", "звезды", "stars"}:
                continue
            text = path.read_text(encoding="utf-8")
            updated = strip_token_lines(text)
            if updated != text:
                path.write_text(updated, encoding="utf-8", newline="\n")
                stripped += 1

    cat = sync_frontier_catalog()
    print(
        f"EN cards rewritten/renamed: {cards}; polity refs: {refs}; "
        f"RU touches: {ru}; token lines stripped: {stripped}; "
        f"frontier catalog fixes: {cat}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
