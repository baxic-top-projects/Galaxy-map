# -*- coding: utf-8 -*-
"""Ensure every system has a globally unique display name (no shared base names)."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "server" / "data"
INDEX_PATH = DATA / "galaxy-index.json"

PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")

# Compact fantasy syllables for deterministic renames.
EN_A = ("Ae", "Al", "Ash", "Bel", "Cael", "Cor", "Dra", "Esh", "Fae", "Gor", "Hel", "Kael", "Lor", "Mir", "Nex", "Or", "Pyr", "Quel", "Rav", "Sel", "Thal", "Ul", "Vor", "Wyn", "Xan", "Yl", "Zor")
EN_B = ("a", "ae", "an", "ar", "el", "en", "eth", "ia", "iel", "ion", "ir", "is", "or", "oth", "une", "yn", "yx")
EN_C = ("a", "e", "is", "on", "um", "us", "ia", "or", "ith", "yn")

RU_A = ("Аш", "Бел", "Вор", "Гор", "Дра", "Каэл", "Лор", "Мир", "Некс", "Ор", "Пир", "Рав", "Сел", "Тал", "Ул", "Хел", "Эш", "Ял")
RU_B = ("а", "ан", "ар", "ел", "ен", "ет", "ия", "ион", "ир", "ор", "ун", "ин")
RU_C = ("а", "ис", "он", "ум", "ус", "ия", "ор", "ит", "ин")


def _strip_paren(value: str) -> str:
    return PAREN_RE.sub("", (value or "").strip()).strip()


def _digest(system_id: str) -> bytes:
    return hashlib.sha256(system_id.encode("utf-8")).digest()


def _mint_en(system_id: str, used: set[str]) -> str:
    raw = _digest(system_id)
    for attempt in range(64):
        b = _digest(f"{system_id}:{attempt}") if attempt else raw
        name = f"{EN_A[b[0] % len(EN_A)]}{EN_B[b[1] % len(EN_B)]}{EN_C[b[2] % len(EN_C)]}"
        if name not in used:
            return name
    return f"Star{abs(int.from_bytes(raw[:4], 'big'))}"


def _mint_ru(system_id: str, used: set[str]) -> str:
    raw = _digest(f"ru:{system_id}")
    for attempt in range(64):
        b = _digest(f"ru:{system_id}:{attempt}") if attempt else raw
        name = f"{RU_A[b[0] % len(RU_A)]}{RU_B[b[1] % len(RU_B)]}{RU_C[b[2] % len(RU_C)]}"
        if name not in used:
            return name
    return f"Звезда{abs(int.from_bytes(raw[:4], 'big'))}"


def uniquify() -> dict:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    systems = index.get("systems") or []

    # Normalize away previous "(Polity)" suffixes.
    for system in systems:
        system["nameEn"] = _strip_paren(system.get("nameEn") or "")
        system["nameRu"] = _strip_paren(system.get("nameRu") or "")

    # Junctions: always token-based unique labels (token may still collide across stems).
    junction_groups: dict[str, list[dict]] = defaultdict(list)
    for system in systems:
        if system.get("kind") != "junction":
            continue
        token = system.get("token") or system.get("id", "").split(":")[-1]
        junction_groups[token].append(system)

    used_en: set[str] = set()
    used_ru: set[str] = set()
    renamed = 0

    for token, rows in junction_groups.items():
        rows_sorted = sorted(rows, key=lambda row: row.get("id") or "")
        for index_row, system in enumerate(rows_sorted):
            if index_row == 0:
                candidate_en = f"{token} Junction"
                candidate_ru = f"Стык {token}"
            else:
                candidate_en = _mint_en(system["id"] + ":junction", used_en) + " Junction"
                candidate_ru = "Стык " + _mint_ru(system["id"] + ":junction", used_ru)
            # Guarantee uniqueness against already assigned.
            while candidate_en in used_en:
                candidate_en = _mint_en(system["id"] + f":junction:{candidate_en}", used_en) + " Junction"
            while candidate_ru in used_ru:
                candidate_ru = "Стык " + _mint_ru(system["id"] + f":junction:{candidate_ru}", used_ru)
            if system.get("nameEn") != candidate_en or system.get("nameRu") != candidate_ru:
                renamed += 1
            system["nameEn"] = candidate_en
            system["nameRu"] = candidate_ru
            used_en.add(candidate_en)
            used_ru.add(candidate_ru)

    # Non-junctions: first keeper of a base name keeps it; later clones get minted names.
    by_base_en: dict[str, list[dict]] = defaultdict(list)
    for system in systems:
        if system.get("kind") == "junction":
            continue
        base = system.get("nameEn") or system.get("token") or system["id"]
        by_base_en[base].append(system)

    for base, rows in by_base_en.items():
        rows_sorted = sorted(rows, key=lambda row: row.get("id") or "")
        for index_row, system in enumerate(rows_sorted):
            if index_row == 0:
                candidate_en = base
                candidate_ru = system.get("nameRu") or base
                # If somehow already taken (junction overlap etc.), mint.
                if candidate_en in used_en:
                    candidate_en = _mint_en(system["id"], used_en)
                if candidate_ru in used_ru:
                    candidate_ru = _mint_ru(system["id"], used_ru)
            else:
                candidate_en = _mint_en(system["id"], used_en)
                candidate_ru = _mint_ru(system["id"], used_ru)
                renamed += 1
            while candidate_en in used_en:
                candidate_en = _mint_en(system["id"] + candidate_en, used_en)
            while candidate_ru in used_ru:
                candidate_ru = _mint_ru(system["id"] + candidate_ru, used_ru)
            system["nameEn"] = candidate_en
            system["nameRu"] = candidate_ru
            used_en.add(candidate_en)
            used_ru.add(candidate_ru)

    # Search entries follow system labels.
    by_id = {system["id"]: system for system in systems}
    for entry in index.get("search") or []:
        if entry.get("kind") != "system":
            continue
        system = by_id.get(entry.get("id"))
        if not system:
            continue
        entry["nameEn"] = system["nameEn"]
        entry["nameRu"] = system["nameRu"]

    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    shard_updates = 0
    for system in systems:
        shard = system.get("shard") or ""
        if not shard:
            continue
        path = DATA / shard
        if not path.is_file():
            continue
        detail = json.loads(path.read_text(encoding="utf-8"))
        if detail.get("nameEn") == system["nameEn"] and detail.get("nameRu") == system["nameRu"]:
            continue
        detail["nameEn"] = system["nameEn"]
        detail["nameRu"] = system["nameRu"]
        path.write_text(json.dumps(detail, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        shard_updates += 1

    return {
        "systems": len(systems),
        "renamed": renamed,
        "uniqueNameEn": len({s["nameEn"] for s in systems}),
        "uniqueNameRu": len({s["nameRu"] for s in systems}),
        "shardsUpdated": shard_updates,
        "hasParenNames": sum(1 for s in systems if "(" in s["nameEn"]),
    }


if __name__ == "__main__":
    print(uniquify())
