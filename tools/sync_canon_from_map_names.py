"""Sync EfolsMiradinsPact file names + titles from live map names.

Rules:
- Map token / compact(nameEn) = English name without spaces = filename
- Card H1 = nameEn / nameRu from the map
- Canon cards have no Token/Токен lines
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT.parent / "EfolsMiradinsPact"
SNAPSHOT = Path(__import__("os").environ.get("TEMP", str(ROOT / "tools"))) / "map_galaxy_snapshot.json"
CATALOG = (
    ROOT
    / "server"
    / "services"
    / "catalog-service"
    / "app"
    / "data"
    / "frontier_polity_catalog.json"
)

EN_STARS = CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN"
EN_WORLDS = CANON / "STATES" / "EN"
RU_WORLDS_ROOT = CANON / "STATES" / "RU"

TOKEN_LINE_RE = re.compile(r"(?m)^-\s*(?:Token|Токен)\s*:\s*.+\n?")
HOST_RE = re.compile(
    r"(- Host star:\s*)\[`[^`]+`\]\([^)]+/stars/[^)]+\.md\)(?:\s*\(`[^`]+`\))?"
)


def compact(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", name or "")


def load_map() -> dict:
    if SNAPSHOT.is_file():
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    import urllib.request

    req = urllib.request.Request(
        "http://galaxyapi.baxic.ru/api/v1/galaxy",
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.load(resp)
    SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def polity_folder(entry: dict) -> str:
    stem = entry.get("canonicalStem") or entry.get("stem") or ""
    eid = entry.get("id") or ""
    if eid.startswith("frontier:"):
        return stem
    return eid.split(":", 1)[0] or stem


def strip_tokens_tree(root: Path) -> int:
    n = 0
    if not root.is_dir():
        return 0
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        updated = TOKEN_LINE_RE.sub("", text)
        if updated != text:
            path.write_text(updated.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
            n += 1
    return n


def rename_md(old: Path, new: Path, text: str) -> None:
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


def set_h1(text: str, name_en: str, name_ru: str) -> str:
    lines = text.splitlines()
    title = f"# {name_en} / {name_ru}".rstrip(" /")
    if lines and lines[0].lstrip("\ufeff").startswith("# "):
        lines[0] = title
    else:
        lines.insert(0, title)
    return "\n".join(lines) + ("\n" if text.endswith("\n") or not text else "\n")


def find_star_file(polity: str, token: str, want: str) -> Path | None:
    stars = EN_STARS / polity / "stars"
    if not stars.is_dir():
        return None
    for name in (want, token):
        if name and (stars / f"{name}.md").is_file():
            return stars / f"{name}.md"
    # fuzzy: any file whose stem equals want/token ignoring case
    for path in stars.glob("*.md"):
        if path.stem in {want, token}:
            return path
    return None


def sync_systems(systems: list[dict]) -> tuple[int, int, dict[str, str]]:
    """Returns (updated, created, renames old->new keyed by polity:old)."""
    updated = created = 0
    renames: dict[str, str] = {}
    for entry in systems:
        polity = polity_folder(entry)
        if not polity:
            continue
        token = entry.get("token") or ""
        name_en = (entry.get("nameEn") or token).strip()
        name_ru = (entry.get("nameRu") or name_en).strip()
        want = compact(name_en) or token
        if not want:
            continue
        stars = EN_STARS / polity / "stars"
        stars.mkdir(parents=True, exist_ok=True)
        src = find_star_file(polity, token, want)
        dest = stars / f"{want}.md"
        if src is None:
            body = (
                f"# {name_en} / {name_ru}\n\n"
                f"## Planet\n\n"
                f"## Status\n"
                f"- Role: host star\n"
                f"- Layer: material galaxy (`Universe/GALAXY`)\n"
            )
            dest.write_text(body, encoding="utf-8", newline="\n")
            created += 1
            if token and token != want:
                renames[f"{polity}:{token}"] = want
            continue
        text = set_h1(src.read_text(encoding="utf-8-sig"), name_en, name_ru)
        text = TOKEN_LINE_RE.sub("", text)
        if src.resolve() != dest.resolve():
            renames[f"{polity}:{src.stem}"] = want
            if token and token != src.stem:
                renames[f"{polity}:{token}"] = want
            rename_md(src, dest, text)
        else:
            if text != src.read_text(encoding="utf-8-sig"):
                dest.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        updated += 1
    return updated, created, renames


def find_world_file(polity: str, token: str) -> Path | None:
    for folder in {polity}:
        path = EN_WORLDS / folder / "worlds" / f"{token}.md"
        if path.is_file():
            return path
    # scan all polities for this token (rare duplicates share token)
    matches = list(EN_WORLDS.glob(f"*/worlds/{token}.md"))
    if len(matches) == 1:
        return matches[0]
    for match in matches:
        if match.parts[match.parts.index("EN") + 1] == polity:
            return match
    return matches[0] if matches else None


def minimal_world_card(
    *,
    name_en: str,
    name_ru: str,
    polity: str,
    token: str,
    planet_type: str,
    host_star: str,
) -> str:
    polity_title = polity.replace("_", " ")
    star_link = ""
    if host_star:
        star_link = (
            f"- Host star: [`{host_star}`]("
            f"../../../../UNIVERSE/GALAXY/STARS/EN/{polity}/stars/{host_star}.md)\n"
        )
    return (
        f"# {name_en} / {name_ru}\n"
        f"## Status\n"
        f"- Polity: [{polity_title} — Draft Profile](../{polity}.md)\n"
        f"- Role: world\n"
        f"- Planet type: {planet_type or 'Unknown'}\n"
        f"{star_link}"
    )


def sync_worlds(worlds: list[dict], systems_by_id: dict[str, dict]) -> tuple[int, int]:
    updated = created = 0
    for entry in worlds:
        polity = polity_folder(entry)
        token = entry.get("token") or ""
        if not polity or not token:
            continue
        name_en = (entry.get("nameEn") or token).strip()
        name_ru = (entry.get("nameRu") or name_en).strip()
        # Filename = map token (English id; may include hyphens)
        want_name = token
        # If token has spaces (shouldn't), compact it
        if " " in want_name:
            want_name = compact(want_name)

        host = ""
        system = systems_by_id.get(entry.get("id") or "")
        if system:
            host = compact(system.get("nameEn") or "") or (system.get("token") or "")

        dest_dir = EN_WORLDS / polity / "worlds"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{want_name}.md"
        src = find_world_file(polity, token)
        if src is None and want_name != token:
            src = find_world_file(polity, want_name)

        planet_type = entry.get("planetTypeKey") or ""
        if src is None:
            dest.write_text(
                minimal_world_card(
                    name_en=name_en,
                    name_ru=name_ru,
                    polity=polity,
                    token=want_name,
                    planet_type=planet_type,
                    host_star=host,
                ),
                encoding="utf-8",
                newline="\n",
            )
            created += 1
            continue

        text = src.read_text(encoding="utf-8-sig")
        text = set_h1(text, name_en, name_ru)
        text = TOKEN_LINE_RE.sub("", text)
        if host:

            def _host(match: re.Match[str]) -> str:
                return (
                    f"{match.group(1)}[`{host}`]("
                    f"../../../../UNIVERSE/GALAXY/STARS/EN/{polity}/stars/{host}.md)"
                )

            if HOST_RE.search(text):
                text = HOST_RE.sub(_host, text)
        if src.resolve() != dest.resolve():
            rename_md(src, dest, text)
        else:
            dest.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        updated += 1
    return updated, created


def rewrite_star_world_links(renames: dict[str, str]) -> int:
    """Ensure star cards link worlds by filename/token display = file stem."""
    touched = 0
    link_re = re.compile(r"\[`([^`]+)`\]\(([^)]+)/worlds/([^)]+)\.md\)")
    for path in EN_STARS.rglob("stars/*.md"):
        text = path.read_text(encoding="utf-8")
        polity = path.parts[path.parts.index("EN") + 1]

        def fix(match: re.Match[str]) -> str:
            _disp, prefix, stem = match.group(1), match.group(2), match.group(3)
            return f"[`{stem}`]({prefix}/worlds/{stem}.md)"

        updated = link_re.sub(fix, text)
        # apply star renames in links within this polity
        local = {
            old.split(":", 1)[1]: new
            for old, new in renames.items()
            if old.startswith(polity + ":")
        }
        if local:
            for old, new in sorted(local.items(), key=lambda kv: -len(kv[0])):
                updated = updated.replace(f"]({old}.md)", f"]({new}.md)")
                updated = updated.replace(f"](stars/{old}.md)", f"](stars/{new}.md)")
                updated = updated.replace(f"`{old}`", f"`{new}`")
        updated = TOKEN_LINE_RE.sub("", updated)
        if updated != text:
            path.write_text(updated.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
            touched += 1
    return touched


def sync_frontier_catalog_from_map(systems: list[dict], worlds: list[dict]) -> int:
    if not CATALOG.is_file():
        return 0
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    by_key: dict[tuple[str, str], dict] = {}
    for entry in systems:
        if entry.get("kind") != "system":
            continue
        polity = entry.get("stem") or polity_folder(entry)
        # match catalog by current token or compact name
        by_key[(polity, entry.get("token") or "")] = entry
        by_key[(polity, compact(entry.get("nameEn") or ""))] = entry

    changed = 0
    worlds_by_system: dict[str, list[dict]] = {}
    for world in worlds:
        worlds_by_system.setdefault(world.get("id") or "", []).append(world)

    for polity, entries in data.items():
        for entry in entries:
            if entry.get("kind") != "star":
                continue
            tok = entry.get("token") or ""
            mapped = by_key.get((polity, tok)) or by_key.get((polity, compact(entry.get("nameEn") or "")))
            if not mapped:
                continue
            new_token = compact(mapped.get("nameEn") or "") or (mapped.get("token") or "")
            name_en = (mapped.get("nameEn") or "").strip()
            name_ru = (mapped.get("nameRu") or "").strip()
            before = (entry.get("token"), entry.get("nameEn"), entry.get("nameRu"))
            entry["token"] = new_token
            entry["nameEn"] = name_en
            entry["nameRu"] = name_ru
            if entry.get("canonicalId"):
                prefix = str(entry["canonicalId"]).rsplit(":", 1)[0]
                entry["canonicalId"] = f"{prefix}:{new_token}"
            # worlds under this system id if present
            sid = mapped.get("id") or ""
            if sid in worlds_by_system and entry.get("worlds") is not None:
                entry["worlds"] = [
                    {
                        "token": w.get("token") or "",
                        "nameEn": w.get("nameEn") or w.get("token") or "",
                        "nameRu": w.get("nameRu") or "",
                        "planetTypeKey": w.get("planetTypeKey") or "",
                    }
                    for w in worlds_by_system[sid]
                ]
            after = (entry.get("token"), entry.get("nameEn"), entry.get("nameRu"))
            if before != after:
                changed += 1

    if changed:
        CATALOG.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def main() -> int:
    if not CANON.is_dir():
        raise SystemExit(f"Canon not found: {CANON}")
    data = load_map()
    search = data.get("search") or []
    systems = [x for x in search if x.get("kind") == "system"]
    worlds = [x for x in search if x.get("kind") == "world"]
    systems_by_id = {s.get("id"): s for s in systems if s.get("id")}

    sys_u, sys_c, renames = sync_systems(systems)
    world_u, world_c = sync_worlds(worlds, systems_by_id)
    link_t = rewrite_star_world_links(renames)
    stripped = strip_tokens_tree(CANON / "UNIVERSE") + strip_tokens_tree(CANON / "STATES")
    cat = sync_frontier_catalog_from_map(systems, worlds)

    # verify samples
    dusk = EN_STARS / "Meridian_Chamber" / "stars" / "Duskothluum.md"
    dra = EN_WORLDS / "Meridian_Chamber" / "worlds" / "DraKiln.md"
    print(f"systems updated={sys_u} created={sys_c} renames={len(renames)}")
    print(f"worlds updated={world_u} created={world_c}")
    print(f"star cards link rewrites={link_t}")
    print(f"token lines stripped files={stripped}")
    print(f"frontier catalog stars synced={cat}")
    if dusk.is_file():
        print("Duskothluum:", dusk.read_text(encoding="utf-8").splitlines()[0])
    if dra.is_file():
        print("DraKiln:", dra.read_text(encoding="utf-8").splitlines()[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
