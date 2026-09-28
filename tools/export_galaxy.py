# -*- coding: utf-8 -*-
"""Export EfolsMiradinsPact galaxy layout into Galaxy-map JSON artifacts."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

CANON = Path(r"D:\GitHub\EfolsMiradinsPact")
OUT_DIR = Path(__file__).resolve().parents[1] / "client" / "public" / "data"
SYSTEMS_DIR = OUT_DIR / "systems"

sys.path.insert(0, str(CANON / "tools"))

# Import after path setup; reuse the exact map layout used for the PNG.
import _render_galaxy_political_map as mapmod  # noqa: E402
from _galactic_economy_data import POLITY_ROWS  # noqa: E402

TITLE_RE = re.compile(r"^#\s+(.+?)\s*/\s*(.+?)\s*$", re.M)
TOKEN_RE = re.compile(r"- Token:\s*`([^`]+)`")
STAR_TYPE_RE = re.compile(r"- Star type:\s*(.+)")
SECTOR_RE = re.compile(r"- Sector:\s*\[`([^`]+)`\]\([^)]+\)\s*\(`([^`]+)`\)")
WORLD_ROW_RE = re.compile(
    r"\|\s*\d+\s*\|\s*\[`([^`]+)`\]\([^)]+\)\s*\|\s*([^|]+)\|"
)
UNINHABITED_ROW_RE = re.compile(
    r"\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*([^|]+)\|\s*([^|]+)\|"
)
FEATURE_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*([^|\n]+)\|\s*([^|\n]+)\|"
    r"(?:\s*([^|\n]+)\|)?\s*$",
    re.M,
)
SATELLITE_ROW_RE = re.compile(
    r"\|\s*\d+\s*\|\s*`?([^|`]+)`?\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
)
PLANET_TYPE_RE = re.compile(r"- Planet type:\s*(.+)")
ROLE_RE = re.compile(r"- Role:\s*(.+)")

STAR_TYPE_KEYS = {
    "binary class g": "binary_class_g",
    "triple class g": "triple_class_g",
    "trinary class g": "triple_class_g",
    "class m giant": "class_m_giant",
    "class m": "class_m",
    "class k": "class_k",
    "class g": "class_g",
    "class f": "class_f",
    "class a": "class_a",
    "class b": "class_b",
    "pulsar": "pulsar",
    "neutron star": "neutron_star",
    "black hole": "black_hole",
    "supermassive black hole": "supermassive_black_hole",
}

PLANET_TYPE_KEYS = {
    "moon": "moon",
    "ecumenopolis": "ecumenopolis",
    "continental": "continental",
    "ocean": "ocean",
    "tropical": "tropical",
    "arid": "arid",
    "desert": "desert",
    "savanna": "savanna",
    "alpine": "alpine",
    "arctic": "arctic",
    "tundra": "tundra",
    "gaia": "gaia",
    "gas giant": "gas_giant",
    "barren": "barren",
    "frozen": "frozen",
    "molten": "molten",
    "toxic": "toxic",
}

SATELLITE_TYPES = (
    ("Moon", "moon"),
    ("Moon", "moon"),
    ("Barren", "barren"),
    ("Frozen", "frozen"),
    ("Molten", "molten"),
    ("Toxic", "toxic"),
    ("Continental", "continental"),
    ("Ocean", "ocean"),
    ("Tropical", "tropical"),
    ("Arid", "arid"),
    ("Desert", "desert"),
    ("Savanna", "savanna"),
    ("Alpine", "alpine"),
    ("Arctic", "arctic"),
    ("Tundra", "tundra"),
    ("Gaia", "gaia"),
    ("Gas Giant", "gas_giant"),
)
ROMAN_NUMERALS = ("I", "II", "III", "IV")

CAPITALS = {("Miradin_Empire", "MiradinSirius"), ("Efol_Raih", "Efol")}


def _stable_z(token: str, radius: float) -> float:
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()
    unit = (int(digest[:8], 16) / 0xFFFFFFFF) * 2.0 - 1.0
    thickness = 0.085 * max(0.15, 1.0 - radius * radius)
    return round(unit * thickness, 6)


def _type_key(raw: str | None, table: dict[str, str], fallback: str) -> str:
    if not raw:
        return fallback
    text = raw.strip().lower()
    for needle, key in sorted(table.items(), key=lambda item: -len(item[0])):
        if needle in text:
            return key
    return fallback


def _rgb_hex(color: tuple[float, float, float]) -> str:
    r, g, b = (int(round(c * 255)) for c in color)
    return f"#{r:02x}{g:02x}{b:02x}"


def _generated_satellites(parent_id: str, name_en: str, name_ru: str, parent_type: str) -> list[dict]:
    """Create a stable random-looking satellite set without changing on each export."""
    digest = hashlib.sha256(f"satellites:{parent_id}".encode("utf-8")).digest()
    # Not every planet has moons; gas giants receive them more often.
    threshold = 82 if parent_type == "gas_giant" else 58
    if digest[0] % 100 >= threshold:
        return []

    max_count = 4 if parent_type == "gas_giant" else 3
    count = 1 + digest[1] % max_count
    satellites = []
    for index in range(count):
        type_name, type_key = SATELLITE_TYPES[digest[index + 2] % len(SATELLITE_TYPES)]
        suffix = ROMAN_NUMERALS[index]
        satellites.append(
            {
                "nameEn": f"{name_en} {suffix}",
                "nameRu": f"{name_ru} {suffix}",
                "planetType": type_name,
                "planetTypeKey": type_key,
            }
        )
    return satellites


def _parse_title(text: str) -> tuple[str, str]:
    match = TITLE_RE.search(text)
    if not match:
        return "", ""
    return match.group(1).strip(), match.group(2).strip()


def _star_path(stem: str | None, token: str, kind: str) -> Path | None:
    if token == mapmod.WELL_TOKEN:
        return CANON / "UNIVERSE" / "GALAXY" / "CORE" / "AxisWell_EN.md"
    if not stem:
        return None
    if kind == "black_hole":
        return CANON / "UNIVERSE" / "GALAXY" / "BLACK_HOLES" / "EN" / stem / f"{token}.md"
    if kind == "junction":
        return CANON / "UNIVERSE" / "GALAXY" / "JUNCTIONS" / "EN" / stem / f"{token}.md"
    return CANON / "UNIVERSE" / "GALAXY" / "STARS" / "EN" / stem / "stars" / f"{token}.md"


def _world_path(stem: str, token: str) -> Path:
    return CANON / "STATES" / "EN" / stem / "worlds" / f"{token}.md"


def _parse_system_card(path: Path | None, kind: str) -> dict:
    if path is None or not path.is_file():
        fallback_type = {
            "star": "Class G",
            "well": "Supermassive Black Hole",
            "junction": "Hypercorridor Junction",
        }.get(kind, "Black Hole")
        return {
            "nameEn": "",
            "nameRu": "",
            "starType": fallback_type,
            "sectorId": "",
            "sectorNameEn": "",
            "worlds": [],
            "uninhabited": [],
            "features": [],
        }

    text = path.read_text(encoding="utf-8")
    name_en, name_ru = _parse_title(text)
    star_type = STAR_TYPE_RE.search(text)
    sector = SECTOR_RE.search(text)

    worlds = []
    for token, ru in WORLD_ROW_RE.findall(text):
        worlds.append(
            {
                "token": token,
                "nameEn": token,
                "nameRu": ru.strip(),
            }
        )

    uninhabited = []
    uninh_block = text.split("### Uninhabited planets", 1)
    if len(uninh_block) > 1:
        body = uninh_block[1].split("### System features", 1)[0]
        for name_en_u, name_ru_u, ptype in UNINHABITED_ROW_RE.findall(body):
            uninhabited.append(
                {
                    "nameEn": name_en_u,
                    "nameRu": name_ru_u.strip(),
                    "planetType": ptype.strip(),
                    "planetTypeKey": _type_key(ptype, PLANET_TYPE_KEYS, "barren"),
                }
            )

    features = []
    feat_block = text.split("### System features", 1)
    if len(feat_block) > 1:
        for name_en_f, name_ru_f, feature, placement in FEATURE_ROW_RE.findall(feat_block[1]):
            placement_text = placement.strip().lower()
            if placement_text.startswith("inner"):
                placement_key = "inner"
            elif placement_text.startswith("middle"):
                placement_key = "middle"
            else:
                placement_key = "outer"
            features.append(
                {
                    "nameEn": name_en_f,
                    "nameRu": name_ru_f.strip(),
                    "feature": feature.strip(),
                    "placement": placement_key,
                }
            )

    return {
        "nameEn": name_en,
        "nameRu": name_ru,
        "starType": (
            star_type.group(1).strip()
            if star_type
            else {
                "star": "Class G",
                "well": "Supermassive Black Hole",
                "junction": "Hypercorridor Junction",
            }.get(kind, "Black Hole")
        ),
        "sectorId": sector.group(2) if sector else "",
        "sectorNameEn": sector.group(1) if sector else "",
        "worlds": worlds,
        "uninhabited": uninhabited,
        "features": features,
    }


def _enrich_world(stem: str, world: dict) -> dict:
    path = _world_path(stem, world["token"])
    if not path.is_file():
        world["planetType"] = "Continental"
        world["planetTypeKey"] = "continental"
        world["role"] = ""
        world["satellites"] = []
        world["_satellitesRecorded"] = False
        return world
    text = path.read_text(encoding="utf-8")
    title_en, title_ru = _parse_title(text)
    if title_en:
        world["nameEn"] = title_en
    if title_ru:
        world["nameRu"] = title_ru
    ptype = PLANET_TYPE_RE.search(text)
    role = ROLE_RE.search(text)
    planet_type = ptype.group(1).strip() if ptype else "Continental"
    world["planetType"] = planet_type
    world["planetTypeKey"] = _type_key(planet_type, PLANET_TYPE_KEYS, "continental")
    world["role"] = role.group(1).strip() if role else ""
    satellites = []
    sat_block = text.split("## Natural satellites", 1)
    world["_satellitesRecorded"] = len(sat_block) > 1
    if len(sat_block) > 1:
        body = re.split(r"\n##\s+", sat_block[1], maxsplit=1)[0]
        for name_en, name_ru, satellite_type in SATELLITE_ROW_RE.findall(body):
            clean_type = satellite_type.strip()
            satellites.append(
                {
                    "nameEn": name_en.strip(),
                    "nameRu": name_ru.strip().strip("`"),
                    "planetType": clean_type,
                    "planetTypeKey": _type_key(clean_type, PLANET_TYPE_KEYS, "moon"),
                }
            )
    world["satellites"] = satellites
    return world


def build_rows() -> list[dict]:
    rows = []
    raih_i = mir_i = 0
    for stem, _ru, name_en, name_ru, bloc, kind, _arch in POLITY_ROWS:
        rec = {
            "stem": stem,
            "name_en": name_en,
            "name_ru": name_ru,
            "bloc": bloc,
            "kind": kind,
            "n": 1,
            "label": mapmod.SHORT_RU[stem],
            "idx": len(rows),
        }
        color = mapmod.polity_color(stem, bloc, kind, raih_i if bloc == "raih" else mir_i)
        rec["color"] = color
        if bloc == "raih":
            raih_i += 1
        elif bloc == "miradin":
            mir_i += 1
        rows.append(rec)
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEMS_DIR.mkdir(parents=True, exist_ok=True)

    # Reset layout RNG to the canonical seed before placement.
    mapmod.RNG = np.random.default_rng(20260909)

    rows = build_rows()
    systems, canon_edges = mapmod.load_catalog(rows)
    display_edges = mapmod.layout_systems(rows, systems, canon_edges)

    polities = []
    for rec in rows:
        polities.append(
            {
                "stem": rec["stem"],
                "nameEn": rec["name_en"],
                "nameRu": rec["name_ru"],
                "bloc": rec["bloc"],
                "kind": rec["kind"],
                "color": _rgb_hex(rec["color"]),
                "label": rec["label"].replace("\n", " "),
            }
        )

    index_systems = []
    search = []

    for key, sys in systems.items():
        xy = sys["xy"]
        x = float(xy[0])
        y = float(xy[1])
        radius = float(np.hypot(x, y))
        z = _stable_z(sys["token"], radius)
        card = _parse_system_card(_star_path(sys["stem"], sys["token"], sys["kind"]), sys["kind"])

        if sys["kind"] == "junction":
            star_type_key = "junction"
        else:
            star_type_key = _type_key(
                card["starType"],
                STAR_TYPE_KEYS,
                (
                    "class_g"
                    if sys["kind"] == "star"
                    else ("supermassive_black_hole" if sys["kind"] == "well" else "black_hole")
                ),
            )
        if sys["kind"] == "well":
            star_type_key = "supermassive_black_hole"
            card["nameEn"] = card["nameEn"] or "Axis Well"
            card["nameRu"] = card["nameRu"] or "Осевой Колодец"
            card["starType"] = "Supermassive Black Hole"
        elif sys["kind"] == "junction":
            # Junction tokens are stable graph IDs, not astronomical names.
            card["nameEn"] = "Hypercorridor junction"
            card["nameRu"] = "Стык гиперкоридоров"
            card["starType"] = "Empty hypercorridor node"
            # Some empty crossings contain a central meteorite ring. Keep the
            # choice stable across exports without inventing a proper name.
            ring_seed = int(hashlib.md5(f"junction-ring:{sys['token']}".encode()).hexdigest()[:8], 16)
            if not card["features"] and ring_seed % 4 == 0:
                card["features"] = [
                    {
                        "nameEn": "Meteorite ring",
                        "nameRu": "Метеоритное кольцо",
                        "feature": "Asteroid Belt",
                        "placement": "inner",
                    }
                ]

        capital = (sys["stem"], sys["token"]) in CAPITALS
        worlds = []
        if sys["stem"]:
            worlds = [_enrich_world(sys["stem"], dict(world)) for world in card["worlds"]]
            for world in worlds:
                recorded = world.pop("_satellitesRecorded", False)
                if not recorded:
                    world["satellites"] = _generated_satellites(
                        f"{key}:world:{world['token']}",
                        world["nameEn"],
                        world["nameRu"],
                        world["planetTypeKey"],
                    )

        uninhabited = [dict(body) for body in card["uninhabited"]]
        for body in uninhabited:
            body["satellites"] = _generated_satellites(
                f"{key}:uninhabited:{body['nameEn']}",
                body["nameEn"],
                body["nameRu"],
                body["planetTypeKey"],
            )

        detail = {
            "id": key,
            "token": sys["token"],
            "stem": sys["stem"],
            "kind": sys["kind"],
            "nameEn": card["nameEn"] or sys["token"],
            "nameRu": card["nameRu"] or sys["token"],
            "starType": card["starType"],
            "starTypeKey": star_type_key,
            "sectorId": card["sectorId"],
            "sectorNameEn": card["sectorNameEn"],
            "capital": capital,
            "x": round(x, 6),
            "y": round(y, 6),
            "z": z,
            "worlds": worlds,
            "uninhabited": uninhabited,
            "features": card["features"],
        }

        shard_name = key.replace(":", "__") + ".json"
        (SYSTEMS_DIR / shard_name).write_text(
            json.dumps(detail, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        index_systems.append(
            {
                "id": key,
                "token": sys["token"],
                "stem": sys["stem"],
                "kind": sys["kind"],
                "nameEn": detail["nameEn"],
                "nameRu": detail["nameRu"],
                "starTypeKey": star_type_key,
                "sectorId": detail["sectorId"],
                "capital": capital,
                "x": detail["x"],
                "y": detail["y"],
                "z": detail["z"],
                "worldCount": len(worlds),
                "shard": f"systems/{shard_name}",
            }
        )

        if sys["kind"] != "junction":
            search.append(
                {
                    "id": key,
                    "kind": "system",
                    "token": sys["token"],
                    "nameEn": detail["nameEn"],
                    "nameRu": detail["nameRu"],
                    "stem": sys["stem"],
                }
            )
        for world in worlds:
            search.append(
                {
                    "id": key,
                    "kind": "world",
                    "token": world["token"],
                    "nameEn": world["nameEn"],
                    "nameRu": world["nameRu"],
                    "stem": sys["stem"],
                    "planetTypeKey": world.get("planetTypeKey", "continental"),
                }
            )

    payload = {
        "meta": {
            "diskR": mapmod.DISK_R,
            "seed": 20260909,
            "source": "EfolsMiradinsPact",
            "systemCount": len(index_systems),
            "edgeCountCanon": len(canon_edges),
            "edgeCountDisplay": len(display_edges),
        },
        "polities": polities,
        "systems": index_systems,
        "edgesCanon": [{"a": a, "b": b} for a, b in canon_edges],
        "edgesDisplay": [{"a": a, "b": b} for a, b in display_edges],
        "search": search,
    }

    out_path = OUT_DIR / "galaxy-index.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        f"Wrote {out_path} with {len(index_systems)} systems, "
        f"{len(display_edges)} display edges, {len(search)} search entries"
    )


if __name__ == "__main__":
    main()
