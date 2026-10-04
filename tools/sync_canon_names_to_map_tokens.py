"""Align Efols display names with map identities (= EN filenames / tokens).

Map shows DraKiln / TorWarden; uniquify left Lorsylis in H1 while files stayed DraKiln.md.
This restores card titles and star-card links to the file stem the map uses.
"""

from __future__ import annotations

import re
from pathlib import Path

CANON = Path(__file__).resolve().parents[1].parent / "EfolsMiradinsPact"
EN_WORLDS = CANON / "STATES" / "EN"
EN_STARS = CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN"
RU_STATES = CANON / "STATES" / "RU"

HOST_RE = re.compile(
    r"\[`([^`]+)`\]\(([^)]+)/stars/([^)]+)\.md\)(?:\s*\(`([^`]+)`\))?"
)
WORLD_LINK_RE = re.compile(r"\[`([^`]+)`\]\(([^)]+)/worlds/([^)]+)\.md\)")


def main() -> int:
    world_h1 = 0
    host_links = 0
    star_links = 0
    ru_h1 = 0

    for path in EN_WORLDS.rglob("worlds/*.md"):
        stem = path.stem
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or not lines[0].startswith("# "):
            continue
        h1 = lines[0][2:].strip()
        en = h1.split("/")[0].strip()
        ru = h1.split("/")[1].strip() if "/" in h1 else stem
        old_en = en
        if en != stem:
            lines[0] = f"# {stem} / {ru if ru else stem}"
            world_h1 += 1
            en = stem
        body = "\n".join(lines)

        polity = path.parts[path.parts.index("EN") + 1]
        stars_dir = EN_STARS / polity / "stars"

        def fix_host(match: re.Match[str]) -> str:
            nonlocal host_links
            label, rel, file_stem, _tok = match.group(1), match.group(2), match.group(3), match.group(4)
            compact = re.sub(r"[^A-Za-z0-9]+", "", label)
            new_stem = file_stem
            if stars_dir.is_dir():
                if (stars_dir / f"{compact}.md").is_file():
                    new_stem = compact
                elif (stars_dir / f"{file_stem}.md").is_file():
                    new_stem = file_stem
                else:
                    for f in stars_dir.glob("*.md"):
                        if f"worlds/{stem}.md" in f.read_text(encoding="utf-8", errors="replace"):
                            new_stem = f.stem
                            break
            replacement = f"[`{new_stem}`]({rel}/stars/{new_stem}.md)"
            if replacement != match.group(0).split(" (")[0] or match.group(4):
                host_links += 1
            return replacement

        body2 = HOST_RE.sub(fix_host, body)
        if old_en != stem:
            body2 = body2.replace(f"`{old_en}`", f"`{stem}`")
            body2 = body2.replace(f"[`{old_en}`]", f"[`{stem}`]")
        if body2 != text:
            path.write_text(
                body2.replace("\r\n", "\n") + ("\n" if not body2.endswith("\n") else ""),
                encoding="utf-8",
                newline="\n",
            )

    for path in EN_STARS.rglob("stars/*.md"):
        text = path.read_text(encoding="utf-8")

        def fix_world(match: re.Match[str]) -> str:
            nonlocal star_links
            disp, prefix, stem = match.group(1), match.group(2), match.group(3)
            if disp == stem:
                return match.group(0)
            star_links += 1
            return f"[`{stem}`]({prefix}/worlds/{stem}.md)"

        updated = WORLD_LINK_RE.sub(fix_world, text)
        if updated != text:
            path.write_text(updated.replace("\r\n", "\n"), encoding="utf-8", newline="\n")

    if RU_STATES.is_dir():
        for path in RU_STATES.rglob("*.md"):
            if path.parent.name not in {"миры", "worlds"}:
                continue
            stem = path.stem
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            if not lines or not lines[0].startswith("# "):
                continue
            h1 = lines[0][2:].strip()
            parts = [p.strip() for p in h1.split("/")]
            if stem in {re.sub(r"[^A-Za-z0-9]+", "", p) for p in parts}:
                continue
            ru_part = next((p for p in parts if re.search(r"[А-Яа-яЁё]", p)), parts[0] if parts else stem)
            lines[0] = f"# {ru_part} / {stem}"
            ru_h1 += 1
            path.write_text(
                "\n".join(lines).replace("\r\n", "\n") + "\n",
                encoding="utf-8",
                newline="\n",
            )

    mismatch = 0
    for path in EN_STARS.rglob("stars/*.md"):
        for disp, _prefix, stem in WORLD_LINK_RE.findall(
            path.read_text(encoding="utf-8", errors="replace")
        ):
            if disp != stem:
                mismatch += 1

    dusk = EN_STARS / "Meridian_Chamber" / "stars" / "Duskothluum.md"
    dra = EN_WORLDS / "Meridian_Chamber" / "worlds" / "DraKiln.md"
    print(f"world H1->filename: {world_h1}")
    print(f"host-star link fixes: {host_links}")
    print(f"star-card world link fixes: {star_links}")
    print(f"RU world H1 fixes: {ru_h1}")
    print(f"remaining display!=file: {mismatch}")
    if dra.is_file():
        print("DraKiln:", dra.read_text(encoding="utf-8").splitlines()[0])
        for line in dra.read_text(encoding="utf-8").splitlines():
            if "Host star" in line or "host star" in line:
                print(line)
    if dusk.is_file():
        text = dusk.read_text(encoding="utf-8")
        print("Duskothluum:", text.splitlines()[0])
        for line in text.splitlines()[:15]:
            if "worlds/" in line or line.startswith("|"):
                print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
