from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from app.service.spiral_geometry import ArmObject

STARS_PER_POLITY = 20
BLACK_HOLES_PER_POLITY = 1
JUNCTIONS_PER_POLITY = 1
LEGACY_CLAIM_RADIUS = 0.034
FRONTIER_CLAIM_MIN = 0.07
FRONTIER_CLAIM_MAX = 0.17
TERRITORY_RASTER_SIZE = 1200
TERRITORY_MAP_LIMIT = 2.8
MARKER_CAPTURE_PIXELS = 4


@dataclass(frozen=True)
class FrontierPolity:
    stem: str
    name_en: str
    name_ru: str
    bloc: str
    color: str
    arm: int

    @property
    def side(self) -> int:
        return 1 if self.bloc == "miradin" else -1

    def payload(self) -> dict:
        return {
            "stem": self.stem,
            "nameEn": self.name_en,
            "nameRu": self.name_ru,
            "bloc": self.bloc,
            "kind": "vassal",
            "color": self.color,
            "label": self.name_ru,
        }


_MIRADIN = (
    ("Caldris_Compact", "Caldris Compact", "Калдрисский Компакт", "#8f4fa8"),
    ("Veyran_Accord", "Veyran Accord", "Вейранский Аккорд", "#a1478f"),
    ("Ossirian_Mandate", "Ossirian Mandate", "Оссирийский Мандат", "#7f5cc9"),
    ("Talaris_Communion", "Talaris Communion", "Таларисская Коммуния", "#b24f75"),
    ("Nivor_Protectorate", "Nivor Protectorate", "Ниворский Протекторат", "#6c69c8"),
    ("Pyralis_Directorate", "Pyralis Directorate", "Пиралисская Директория", "#9b5bb7"),
    ("Ilyr_Assembly", "Ilyr Assembly", "Илирская Ассамблея", "#7651a3"),
    ("Ceryn_League", "Ceryn League", "Церинская Лига", "#c05a9a"),
    ("Damar_Covenant", "Damar Covenant", "Дамарский Ковенант", "#6755b5"),
    ("Khelar_Union", "Khelar Union", "Хеларский Союз", "#a65d87"),
    ("Serrin_Cordon", "Serrin Cordon", "Серринский Кордон", "#805aa8"),
)

_RAIH = (
    ("Auric_Charter", "Auric Charter", "Аурикская Хартия", "#b08a36"),
    ("Dravorn_Dominion", "Dravorn Dominion", "Драворнский Доминион", "#8b9a3d"),
    ("Selqari_Synod", "Selqari Synod", "Селкарийский Синод", "#b46f32"),
    ("Vhalian_Caravanate", "Vhalian Caravanate", "Вхалийский Караванат", "#a19b45"),
    ("Kharad_March", "Kharad March", "Харадский Марш", "#768f3c"),
    (
        "Ortheon_Guild_Republic",
        "Ortheon Guild Republic",
        "Ортеонская Гильдейская Республика",
        "#c0903c",
    ),
    (
        "Yssarian_Concordat",
        "Yssarian Concordat",
        "Иссарийский Конкордат",
        "#8b7b32",
    ),
    ("Brumal_Crown", "Brumal Crown", "Брумальная Корона", "#a66f38"),
    ("Lumenar_Chamber", "Lumenar Chamber", "Люменарская Палата", "#719451"),
    ("Theros_Compact", "Theros Compact", "Теросский Компакт", "#b78646"),
)

_MIRADIN_BATCH28 = (
    ("Haldor_Compact", "Haldor Compact", "Халдорский Компакт", "#ad4c58"),
    ("Wren_Accord", "Wren Accord", "Вренский Аккорд", "#6b4cad"),
    ("Basalt_Mandate", "Basalt Mandate", "Базальтовый Мандат", "#714cad"),
    ("Grove_Communion", "Grove Communion", "Гроувская Коммуния", "#764cad"),
    ("Frost_Ward", "Frost Ward", "Фростский Дозор", "#7b4cad"),
    ("Ember_Array", "Ember Array", "Эмберский Массив", "#814cad"),
    ("Prism_Assembly", "Prism Assembly", "Призменная Ассамблея", "#864cad"),
    ("Glass_League", "Glass League", "Стеклянная Лига", "#8b4cad"),
    ("Anvil_Covenant", "Anvil Covenant", "Анвильский Ковенант", "#904cad"),
    ("Needle_Union", "Needle Union", "Игольный Союз", "#964cad"),
    ("Tide_Protectorate", "Tide Protectorate", "Приливный Протекторат", "#9b4cad"),
    ("Ash_Directorate", "Ash Directorate", "Пепельная Директория", "#a04cad"),
    ("Quiet_Chamber", "Quiet Chamber", "Тихая Палата", "#a64cad"),
    ("Span_League", "Span League", "Пролётная Лига", "#ad4c87"),
)

_RAIH_BATCH28 = (
    ("Aurin_Charter", "Aurin Charter", "Ауринская Хартия", "#c29c4e"),
    ("Cinder_Dominion", "Cinder Dominion", "Синдерский Доминион", "#c29f4e"),
    ("Choir_Synod", "Choir Synod", "Хоровой Синод", "#c2a24e"),
    ("Silt_Caravanate", "Silt Caravanate", "Силтовый Караванат", "#c2a54e"),
    ("Grit_March", "Grit March", "Гритский Марш", "#c2a74e"),
    (
        "Latch_Guild_Republic",
        "Latch Guild Republic",
        "Затворная Гильдейская Республика",
        "#c2aa4e",
    ),
    ("Bloom_Concordat", "Bloom Concordat", "Цветочный Конкордат", "#c2ad4e"),
    ("Rime_Crown", "Rime Crown", "Инеевая Корона", "#c2af4e"),
    ("Volt_Chamber", "Volt Chamber", "Вольтовая Палата", "#c2b24e"),
    ("Facet_Compact", "Facet Compact", "Гранёный Компакт", "#c2b54e"),
    (
        "Coil_Protectorate",
        "Coil Protectorate",
        "Катушечный Протекторат",
        "#c2b84e",
    ),
    ("Mirror_League", "Mirror League", "Зеркальная Лига", "#c2ba4e"),
    ("Salt_Accord", "Salt Accord", "Соляной Аккорд", "#c2bd4e"),
    ("Hex_Mandate", "Hex Mandate", "Гекс Мандат", "#c27e4e"),
)

_MIRADIN_BATCH29 = (
    ("Quill_Compact", "Quill Compact", "Квилльский Компакт", "#b04d5f"),
    ("Amber_Accord", "Amber Accord", "Амберский Аккорд", "#704cad"),
    ("Flint_Mandate", "Flint Mandate", "Флинтский Мандат", "#754cad"),
    ("Willow_Communion", "Willow Communion", "Виллоуская Коммуния", "#7a4cad"),
    ("Glacier_Ward", "Glacier Ward", "Глейшерский Дозор", "#804cad"),
    ("Spark_Array", "Spark Array", "Спаркский Массив", "#854cad"),
    ("Lens_Assembly", "Lens Assembly", "Ленсская Ассамблея", "#8a4cad"),
    ("Crystal_League", "Crystal League", "Кристальная Лига", "#8f4cad"),
    ("Hammer_Covenant", "Hammer Covenant", "Хаммерский Ковенант", "#944cad"),
    ("Spindle_Union", "Spindle Union", "Спиндельский Союз", "#994cad"),
    ("Harbor_Protectorate", "Harbor Protectorate", "Харборский Протекторат", "#9e4cad"),
    ("Smoke_Directorate", "Smoke Directorate", "Смоукская Директория", "#a34cad"),
    ("Archive_Chamber", "Archive Chamber", "Архивная Палата", "#a84cad"),
    ("Bridge_League", "Bridge League", "Бриджская Лига", "#ad4c7a"),
)

_RAIH_BATCH29 = (
    ("Opal_Charter", "Opal Charter", "Опаловая Хартия", "#c29d4e"),
    ("Slag_Dominion", "Slag Dominion", "Шлаковый Доминион", "#c2a04e"),
    ("Cantor_Synod", "Cantor Synod", "Канторский Синод", "#c2a34e"),
    ("Dune_Caravanate", "Dune Caravanate", "Дюнный Караванат", "#c2a64e"),
    ("Pebble_March", "Pebble March", "Пебблский Марш", "#c2a94e"),
    (
        "Hinge_Guild_Republic",
        "Hinge Guild Republic",
        "Хинджевая Гильдейская Республика",
        "#c2ac4e",
    ),
    ("Petal_Concordat", "Petal Concordat", "Петалский Конкордат", "#c2af4e"),
    ("Hail_Crown", "Hail Crown", "Хейльская Корона", "#c2b24e"),
    ("Ampere_Chamber", "Ampere Chamber", "Амперная Палата", "#c2b54e"),
    ("Gem_Compact", "Gem Compact", "Гемский Компакт", "#c2b84e"),
    (
        "Spring_Protectorate",
        "Spring Protectorate",
        "Спрингский Протекторат",
        "#c2bb4e",
    ),
    ("Reflect_League", "Reflect League", "Рефлектская Лига", "#c2be4e"),
    ("Brine_Accord", "Brine Accord", "Брайновый Аккорд", "#c2c14e"),
    ("Glyph_Mandate", "Glyph Mandate", "Глифский Мандат", "#c2804e"),
)

_MIRADIN_BATCH30 = (
    ("Arc_Array", "Arc Array", "Арковский Массив", "#b04d5f"),
    ("Cobble_Mandate", "Cobble Mandate", "Кобблский Мандат", "#704cad"),
    ("Ironbark_League", "Ironbark League", "Айронбаркская Лига", "#754cad"),
    ("Jetty_Protectorate", "Jetty Protectorate", "Джеттийский Протекторат", "#7a4cad"),
    ("Ledger_Chamber", "Ledger Chamber", "Леджерская Палата", "#804cad"),
    ("Meadow_Accord", "Meadow Accord", "Медоуский Аккорд", "#854cad"),
    ("Myrtle_Communion", "Myrtle Communion", "Миртовая Коммуния", "#8a4cad"),
    ("Parch_Compact", "Parch Compact", "Парчский Компакт", "#8f4cad"),
    ("Pin_Covenant", "Pin Covenant", "Пинский Ковенант", "#944cad"),
    ("Prismglass_Assembly", "Prismglass Assembly", "Призмгласская Ассамблея", "#994cad"),
    ("Rimefall_Ward", "Rimefall Ward", "Римфолльский Дозор", "#9e4cad"),
    ("Scroll_Union", "Scroll Union", "Скролльский Союз", "#a34cad"),
    ("Soot_Directorate", "Soot Directorate", "Сутовая Директория", "#a84cad"),
    ("Spanlink_League", "Spanlink League", "Спанлинкская Лига", "#ad4c7a"),
)

_RAIH_BATCH30 = (
    ("Alkali_Accord", "Alkali Accord", "Алкалийский Аккорд", "#c29d4e"),
    ("Blossom_Concordat", "Blossom Concordat", "Блоссомский Конкордат", "#c2a04e"),
    ("Cascade_Protectorate", "Cascade Protectorate", "Каскадный Протекторат", "#c2a34e"),
    ("Cinderfall_Dominion", "Cinderfall Dominion", "Синдерфолльский Доминион", "#c2a64e"),
    ("Drift_Caravanate", "Drift Caravanate", "Дрифтовый Караванат", "#c2a94e"),
    ("Faraday_Chamber", "Faraday Chamber", "Фарадеевская Палата", "#c2ac4e"),
    ("Hoarfrost_Crown", "Hoarfrost Crown", "Хоарфростская Корона", "#c2af4e"),
    ("Ivory_Charter", "Ivory Charter", "Айвори Хартия", "#c2b24e"),
    ("Jewel_Compact", "Jewel Compact", "Джуэльный Компакт", "#c2b54e"),
    ("Psalm_Synod", "Psalm Synod", "Псалмовый Синод", "#c2b84e"),
    (
        "Rivet_Guild_Republic",
        "Rivet Guild Republic",
        "Риветовая Гильдейская Республика",
        "#c2bb4e",
    ),
    ("Shale_March", "Shale March", "Сланцевый Марш", "#c2be4e"),
    ("Sigil_Mandate", "Sigil Mandate", "Сигильский Мандат", "#c2c14e"),
    ("Specular_League", "Specular League", "Спекулярная Лига", "#c2804e"),
)


_MIRADIN_BATCH31 = (
    ("Basaltpit_Mandate", "Basaltpit Mandate", "Базальтпитовый Мандат", "#704cad"),
    ("Cablearc_League", "Cablearc League", "Кейбларкская Лига", "#724cad"),
    ("Codex_Union", "Codex Union", "Кодексный Союз", "#744cad"),
    ("Copperwire_Array", "Copperwire Array", "Меднопроводный Массив", "#764cad"),
    ("Filament_Covenant", "Filament Covenant", "Филиментный Ковенант", "#784cad"),
    ("Flintquarry_Mandate", "Flintquarry Mandate", "Флинткарьерный Мандат", "#7a4cad"),
    ("Flue_Directorate", "Flue Directorate", "Флюйская Директория", "#7c4cad"),
    ("Folio_Union", "Folio Union", "Фолио Союз", "#7e4cad"),
    ("Hailvault_Ward", "Hailvault Ward", "Хейлволтский Дозор", "#804cad"),
    ("Inkpress_Compact", "Inkpress Compact", "Инкпрессный Компакт", "#824cad"),
    ("Lensforge_Assembly", "Lensforge Assembly", "Ленсфорджская Ассамблея", "#844cad"),
    ("Lichen_Communion", "Lichen Communion", "Лишайниковая Коммуния", "#864cad"),
    ("Needlehall_Covenant", "Needlehall Covenant", "Нидлхоллский Ковенант", "#884cad"),
    ("Oakiron_League", "Oakiron League", "Оакайронская Лига", "#8a4cad"),
    ("Orchard_Accord", "Orchard Accord", "Орчардский Аккорд", "#8c4cad"),
    ("Pasture_Accord", "Pasture Accord", "Пастбищный Аккорд", "#8e4cad"),
    ("Pierhead_Protectorate", "Pierhead Protectorate", "Пирхедский Протекторат", "#904cad"),
    ("Quartz_Assembly", "Quartz Assembly", "Кварцевая Ассамблея", "#924cad"),
    ("Reedweave_Communion", "Reedweave Communion", "Ридвивная Коммуния", "#944cad"),
    ("Slagforge_League", "Slagforge League", "Шлакфорджская Лига", "#964cad"),
    ("Snowlock_Ward", "Snowlock Ward", "Сноулокский Дозор", "#984cad"),
    ("Sparkgrid_Array", "Sparkgrid Array", "Спаркгридовый Массив", "#9a4cad"),
    ("Tally_Chamber", "Tally Chamber", "Таллийская Палата", "#9c4cad"),
    ("Vellum_Compact", "Vellum Compact", "Веллумский Компакт", "#9e4cad"),
    ("Wharf_Protectorate", "Wharf Protectorate", "Варфский Протекторат", "#ad4c7a"),
)

_RAIH_BATCH31 = (
    ("Ashridge_Dominion", "Ashridge Dominion", "Эшриджский Доминион", "#c29d4e"),
    ("Bloomfield_Concordat", "Bloomfield Concordat", "Блумфилдский Конкордат", "#c29e4e"),
    (
        "Bolt_Guild_Republic",
        "Bolt Guild Republic",
        "Болтовая Гильдейская Республика",
        "#c29f4e",
    ),
    ("Brinepool_Accord", "Brinepool Accord", "Брайнпуловый Аккорд", "#c2a04e"),
    ("Chant_Synod", "Chant Synod", "Чайтовый Синод", "#c2a14e"),
    ("Coral_Charter", "Coral Charter", "Коралловая Хартия", "#c2a24e"),
    ("Crag_March", "Crag March", "Крэгский Марш", "#c2a34e"),
    ("Dunespan_Caravanate", "Dunespan Caravanate", "Дюнспанский Караванат", "#c2a44e"),
    ("Emberslope_Dominion", "Emberslope Dominion", "Эмберслоупский Доминион", "#c2a54e"),
    ("Frostpeak_Crown", "Frostpeak Crown", "Фростпикская Корона", "#c2a64e"),
    (
        "Gear_Guild_Republic",
        "Gear Guild Republic",
        "Гировая Гильдейская Республика",
        "#c2a74e",
    ),
    ("Granite_March", "Granite March", "Гранитный Марш", "#c2a84e"),
    ("Icehelm_Crown", "Icehelm Crown", "Айсхельмская Корона", "#c2a94e"),
    ("Mirrorwell_League", "Mirrorwell League", "Миррорвеллская Лига", "#c2aa4e"),
    ("Mistfall_Protectorate", "Mistfall Protectorate", "Мистфолльский Протекторат", "#c2ab4e"),
    ("Ohm_Chamber", "Ohm Chamber", "Омовая Палата", "#c2ac4e"),
    ("Onyx_Compact", "Onyx Compact", "Ониксовый Компакт", "#c2ad4e"),
    ("Pearl_Charter", "Pearl Charter", "Жемчужная Хартия", "#c2ae4e"),
    ("Petalstem_Concordat", "Petalstem Concordat", "Петалстемский Конкордат", "#c2af4e"),
    ("Rapids_Protectorate", "Rapids Protectorate", "Рапидный Протекторат", "#c2b04e"),
    ("Relays_Chamber", "Relays Chamber", "Релейная Палата", "#c2b14e"),
    ("Runevault_Mandate", "Runevault Mandate", "Рунволтский Мандат", "#c2b24e"),
    ("Topaz_Compact", "Topaz Compact", "Топазовый Компакт", "#c2b34e"),
    ("Trail_Caravanate", "Trail Caravanate", "Трейловый Караванат", "#c2b44e"),
    ("Vespers_Synod", "Vespers Synod", "Весперовый Синод", "#c2804e"),
)


_MIRADIN_BATCH32 = (
    ("Anviloak_League", "Anviloak League", "Наковальнедубовая Лига", "#704cad"),
    ("Arcgrid_Array", "Arcgrid Array", "Аркгридовый Массив", "#724cad"),
    ("Busbar_Array", "Busbar Array", "Шинный Массив", "#744cad"),
    ("Cinderforge_League", "Cinderforge League", "Зольнокузнечная Лига", "#764cad"),
    ("Daybook_Chamber", "Daybook Chamber", "Дейбукская Палата", "#784cad"),
    ("Glacelock_Ward", "Glacelock Ward", "Глейслокский Дозор", "#7a4cad"),
    ("Grove_Accord", "Grove Accord", "Рощевой Аккорд", "#7c4cad"),
    ("Kelpweave_Communion", "Kelpweave Communion", "Келпвивная Коммуния", "#7e4cad"),
    ("Leyfield_Accord", "Leyfield Accord", "Лейфилдовый Аккорд", "#804cad"),
    ("Marblepit_Mandate", "Marblepit Mandate", "Мраморный Мандат", "#824cad"),
    ("Mole_Protectorate", "Mole Protectorate", "Мольный Протекторат", "#844cad"),
    ("Moss_Communion", "Moss Communion", "Моховая Коммуния", "#864cad"),
    ("Palimpsest_Union", "Palimpsest Union", "Палимпсестный Союз", "#884cad"),
    ("Parchment_Compact", "Parchment Compact", "Пергаментный Компакт", "#8a4cad"),
    ("Pinpoint_Covenant", "Pinpoint Covenant", "Пинпойнтский Ковенант", "#8c4cad"),
    ("Prismforge_Assembly", "Prismforge Assembly", "Призмфорджская Ассамблея", "#8e4cad"),
    ("Quarto_Union", "Quarto Union", "Кварто Союз", "#904cad"),
    ("Quaystep_Protectorate", "Quaystep Protectorate", "Кейстепский Протекторат", "#924cad"),
    ("Rimevault_Ward", "Rimevault Ward", "Раймволтский Дозор", "#944cad"),
    ("Shalequarry_Mandate", "Shalequarry Mandate", "Сланцекарьерный Мандат", "#964cad"),
    ("Spanbridge_League", "Spanbridge League", "Спанбриджская Лига", "#984cad"),
    ("Spireglass_Assembly", "Spireglass Assembly", "Шпилегассская Ассамблея", "#9a4cad"),
    ("Stack_Directorate", "Stack Directorate", "Дымоходная Директория", "#9c4cad"),
    ("Threadhall_Covenant", "Threadhall Covenant", "Тредхоллский Ковенант", "#9e4cad"),
    ("Typeset_Compact", "Typeset Compact", "Наборный Компакт", "#a04cad"),
)

_RAIH_BATCH32 = (
    ("Amber_Charter", "Amber Charter", "Янтарная Хартия", "#c29d4e"),
    ("Antiphon_Synod", "Antiphon Synod", "Антифонный Синод", "#c29e4e"),
    ("Basalt_March", "Basalt March", "Базальтовый Марш", "#c29f4e"),
    ("Bloomstem_Concordat", "Bloomstem Concordat", "Блумстемский Конкордат", "#c2a04e"),
    ("Cinderhill_Dominion", "Cinderhill Dominion", "Зольнохолмский Доминион", "#c2a14e"),
    ("Cog_Guild_Republic", "Cog Guild Republic", "Шестерёночная Гильдейская Республика", "#c2a24e"),
    ("Coulomb_Chamber", "Coulomb Chamber", "Кулоновая Палата", "#c2a34e"),
    ("Dewfall_Protectorate", "Dewfall Protectorate", "Дьюфолльский Протекторат", "#c2a44e"),
    ("Dunehaul_Caravanate", "Dunehaul Caravanate", "Дюнхоловый Караванат", "#c2a54e"),
    ("Eddy_Protectorate", "Eddy Protectorate", "Эдди Протекторат", "#c2a64e"),
    ("Glasswell_League", "Glasswell League", "Глассвеллская Лига", "#c2a74e"),
    ("Glyphvault_Mandate", "Glyphvault Mandate", "Глифволтский Мандат", "#c2a84e"),
    ("Jade_Compact", "Jade Compact", "Нефритовый Компакт", "#c2a94e"),
    ("Loamhaul_Caravanate", "Loamhaul Caravanate", "Лоумхоловый Караванат", "#c2aa4e"),
    ("Matins_Synod", "Matins Synod", "Заутренний Синод", "#c2ab4e"),
    ("Nacre_Charter", "Nacre Charter", "Перламутровая Хартия", "#c2ac4e"),
    ("Obsidian_Compact", "Obsidian Compact", "Обсидиановый Компакт", "#c2ad4e"),
    ("Petalfold_Concordat", "Petalfold Concordat", "Петалфолдский Конкордат", "#c2ae4e"),
    ("Ratchet_Guild_Republic", "Ratchet Guild Republic", "Трещоточная Гильдейская Республика", "#c2af4e"),
    ("Ridge_March", "Ridge March", "Хребтовый Марш", "#c2b04e"),
    ("Rimehelm_Crown", "Rimehelm Crown", "Раймхельмская Корона", "#c2b14e"),
    ("Rimepeak_Crown", "Rimepeak Crown", "Раймпикская Корона", "#c2b24e"),
    ("Saltern_Accord", "Saltern Accord", "Солеварный Аккорд", "#c2b34e"),
    ("Scoriater_Dominion", "Scoriater Dominion", "Скориатеррасный Доминион", "#c2b44e"),
    ("Switch_Chamber", "Switch Chamber", "Коммутаторная Палата", "#c2b54e"),
)


def _miradin_polities(
    rows: tuple[tuple[str, str, str, str], ...],
    *,
    first_arm_count: int,
) -> tuple[FrontierPolity, ...]:
    return tuple(
        FrontierPolity(
            row[0],
            row[1],
            row[2],
            "miradin",
            row[3],
            arm=1 if index < first_arm_count else 4,
        )
        for index, row in enumerate(rows)
    )


def _raih_polities(
    rows: tuple[tuple[str, str, str, str], ...],
    *,
    first_arm_count: int,
) -> tuple[FrontierPolity, ...]:
    return tuple(
        FrontierPolity(
            row[0],
            row[1],
            row[2],
            "raih",
            row[3],
            arm=2 if index < first_arm_count else 3,
        )
        for index, row in enumerate(rows)
    )


ORIGINAL_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN,
    first_arm_count=6,
) + _raih_polities(
    _RAIH,
    first_arm_count=5,
)

PREVIOUS_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN_BATCH28,
    first_arm_count=7,
) + _raih_polities(
    _RAIH_BATCH28,
    first_arm_count=7,
)

BATCH29_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN_BATCH29,
    # Arms 1/3 are saturated after the previous wave; keep Miradin on the
    # right by placing the whole batch on arm 4.
    first_arm_count=0,
) + _raih_polities(
    _RAIH_BATCH29,
    # Keep Raih on the left by placing the whole batch on arm 2.
    first_arm_count=14,
)

BATCH30_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN_BATCH30,
    first_arm_count=4,
) + _raih_polities(
    _RAIH_BATCH30,
    first_arm_count=10,
)

BATCH31_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN_BATCH31,
    first_arm_count=12,
) + _raih_polities(
    _RAIH_BATCH31,
    first_arm_count=12,
)

LOCKED_FRONTIER_POLITIES = (
    ORIGINAL_FRONTIER_POLITIES
    + PREVIOUS_FRONTIER_POLITIES
    + BATCH29_FRONTIER_POLITIES
    + BATCH30_FRONTIER_POLITIES
    + BATCH31_FRONTIER_POLITIES
)

NEW_FRONTIER_POLITIES = _miradin_polities(
    _MIRADIN_BATCH32,
    first_arm_count=12,
) + _raih_polities(
    _RAIH_BATCH32,
    first_arm_count=12,
)

NEW_FRONTIER_STEMS = frozenset(
    polity.stem for polity in NEW_FRONTIER_POLITIES
)
NEW_FRONTIER_ARM_BY_STEM = {
    polity.stem: polity.arm for polity in NEW_FRONTIER_POLITIES
}
NEW_FRONTIER_SIDE_BY_STEM = {
    polity.stem: polity.side for polity in NEW_FRONTIER_POLITIES
}
NEW_FRONTIER_STARS_BY_STEM = {
    "Anviloak_League": 1,
    "Arcgrid_Array": 2,
    "Busbar_Array": 1,
    "Cinderforge_League": 3,
    "Daybook_Chamber": 2,
    "Glacelock_Ward": 2,
    "Grove_Accord": 2,
    "Kelpweave_Communion": 2,
    "Leyfield_Accord": 1,
    "Marblepit_Mandate": 2,
    "Mole_Protectorate": 3,
    "Moss_Communion": 1,
    "Palimpsest_Union": 1,
    "Parchment_Compact": 1,
    "Pinpoint_Covenant": 3,
    "Prismforge_Assembly": 1,
    "Quarto_Union": 3,
    "Quaystep_Protectorate": 2,
    "Rimevault_Ward": 1,
    "Shalequarry_Mandate": 1,
    "Spanbridge_League": 2,
    "Spireglass_Assembly": 3,
    "Stack_Directorate": 2,
    "Threadhall_Covenant": 1,
    "Typeset_Compact": 2,
    "Amber_Charter": 1,
    "Antiphon_Synod": 1,
    "Basalt_March": 1,
    "Bloomstem_Concordat": 1,
    "Cinderhill_Dominion": 2,
    "Cog_Guild_Republic": 1,
    "Coulomb_Chamber": 1,
    "Dewfall_Protectorate": 3,
    "Dunehaul_Caravanate": 1,
    "Eddy_Protectorate": 2,
    "Glasswell_League": 2,
    "Glyphvault_Mandate": 2,
    "Jade_Compact": 1,
    "Loamhaul_Caravanate": 2,
    "Matins_Synod": 2,
    "Nacre_Charter": 2,
    "Obsidian_Compact": 3,
    "Petalfold_Concordat": 3,
    "Ratchet_Guild_Republic": 2,
    "Ridge_March": 2,
    "Rimehelm_Crown": 3,
    "Rimepeak_Crown": 1,
    "Saltern_Accord": 2,
    "Scoriater_Dominion": 1,
    "Switch_Chamber": 3,
}
FRONTIER_POLITIES = LOCKED_FRONTIER_POLITIES + NEW_FRONTIER_POLITIES

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "frontier_polity_catalog.json"
)
_LAYOUT_LOCK_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "frontier_layout_lock.json"
)


def load_locked_frontier_layout(
    objects: list[ArmObject],
) -> tuple[
    dict[str, str],
    dict[str, tuple[ArmObject, ...]],
    dict[str, str],
]:
    """Load the immutable ownership/coordinate snapshot for current polities."""
    if not _LAYOUT_LOCK_PATH.is_file():
        raise RuntimeError(f"Missing frontier layout lock: {_LAYOUT_LOCK_PATH}")
    layout = json.loads(_LAYOUT_LOCK_PATH.read_text(encoding="utf-8"))
    expected_polities = [
        polity.stem for polity in LOCKED_FRONTIER_POLITIES
    ]
    if layout.get("polities") != expected_polities:
        raise RuntimeError(
            "Frontier polity definitions differ from the locked layout"
        )

    object_indexes = {obj.id: index for index, obj in enumerate(objects)}
    for object_id, coordinates in layout["coordinates"].items():
        index = object_indexes.get(object_id)
        if index is None:
            kind = (
                "black_hole"
                if ":black_hole" in object_id
                else "junction"
                if ":junction" in object_id
                else "star"
            )
            arm = 1
            if ":arm-" in object_id:
                try:
                    arm = int(object_id.split(":arm-", 1)[1].split(":", 1)[0])
                except ValueError:
                    arm = 1
            objects.append(
                ArmObject(
                    id=object_id,
                    arm=arm,
                    ordinal=len(objects),
                    kind=kind,
                    star_type_key=(
                        "black_hole"
                        if kind == "black_hole"
                        else "junction"
                        if kind == "junction"
                        else "class_g"
                    ),
                    x=float(coordinates[0]),
                    y=float(coordinates[1]),
                    z=float(coordinates[2]),
                )
            )
            object_indexes[object_id] = len(objects) - 1
            continue
        objects[index] = replace(
            objects[index],
            x=float(coordinates[0]),
            y=float(coordinates[1]),
            z=float(coordinates[2]),
        )

    by_id = {obj.id: obj for obj in objects}
    clusters = {
        stem: tuple(by_id[object_id] for object_id in object_ids)
        for stem, object_ids in layout["clusters"].items()
    }
    return (
        dict(layout["baseOwnership"]),
        clusters,
        dict(layout["ownership"]),
    )


def allocate_frontier_polities(
    objects: list[ArmObject],
) -> tuple[dict[str, str], dict[str, tuple[ArmObject, ...]]]:
    """Allocate compact one-arm clusters next to the old disk.

    Miradin uses right-side objects in arms 1/4; Raih uses left-side objects in
    arms 2/3. Evenly spaced target points along the old disk rim keep polity
    pockets compact, distinct, and directly adjacent to existing territory.
    """

    object_indexes = {obj.id: index for index, obj in enumerate(objects)}
    available = {obj.id: obj for obj in objects}
    assignments: dict[str, str] = {}
    clusters: dict[str, tuple[ArmObject, ...]] = {}
    bloc_indexes = {"miradin": 0, "raih": 0}
    bloc_totals = {
        "miradin": sum(
            polity.bloc == "miradin"
            for polity in ORIGINAL_FRONTIER_POLITIES
        ),
        "raih": sum(
            polity.bloc == "raih"
            for polity in ORIGINAL_FRONTIER_POLITIES
        ),
    }
    def update_object(obj: ArmObject) -> None:
        objects[object_indexes[obj.id]] = obj
        available[obj.id] = obj

    for polity in ORIGINAL_FRONTIER_POLITIES:
        position = bloc_indexes[polity.bloc]
        bloc_indexes[polity.bloc] += 1
        fraction = (position + 0.5) / bloc_totals[polity.bloc]
        target_angle = (
            math.pi / 2 - fraction * math.pi
            if polity.bloc == "miradin"
            else math.pi / 2 + fraction * math.pi
        )
        target_x = math.cos(target_angle) * 1.04
        target_y = math.sin(target_angle) * 1.04

        candidates = [
            obj
            for obj in available.values()
            if obj.arm == polity.arm and obj.x * polity.side > 0
        ]
        star_candidates = sorted(
            (obj for obj in candidates if obj.kind == "star"),
            key=lambda obj: (
                math.hypot(obj.x - target_x, obj.y - target_y),
                obj.ordinal,
                obj.id,
            ),
        )
        if not star_candidates:
            raise RuntimeError(f"No stars available for {polity.stem}")
        selected_stars = star_candidates[:STARS_PER_POLITY]
        if len(selected_stars) != STARS_PER_POLITY:
            raise RuntimeError(f"Not enough stars available for {polity.stem}")

        # Keep the generator's irregular positions. Repacking onto a synthetic
        # spiral makes every polity look like an artificial star clump.
        stars = sorted(selected_stars, key=lambda obj: (obj.ordinal, obj.id))

        anchor_x = sum(obj.x for obj in stars) / len(stars)
        anchor_y = sum(obj.y for obj in stars) / len(stars)
        cluster_radius = max(
            math.hypot(obj.x - anchor_x, obj.y - anchor_y)
            for obj in stars
        )

        def take_special(kind: str, offset_index: int) -> ArmObject:
            specials = [obj for obj in candidates if obj.kind == kind]
            if not specials:
                specials = [
                    obj
                    for obj in available.values()
                    if obj.arm == polity.arm and obj.kind == kind
                ]
            if not specials:
                raise RuntimeError(f"No {kind} available for {polity.stem}")
            selected = min(
                specials,
                key=lambda obj: (
                    math.hypot(obj.x - anchor_x, obj.y - anchor_y),
                    obj.ordinal,
                    obj.id,
                ),
            )
            distance = math.hypot(selected.x - anchor_x, selected.y - anchor_y)
            if distance <= max(0.08, cluster_radius * 1.2):
                return selected

            # Reuse an unclaimed special object from this arm and place it
            # inside the new polity pocket. arm_edges() runs after allocation
            # and rebuilds local corridors around its new position.
            offset_angle = (
                (len(clusters) * 2 + offset_index) * 2.399963229728653
            )
            relocated = replace(
                selected,
                x=round(anchor_x + math.cos(offset_angle) * 0.008, 6),
                y=round(anchor_y + math.sin(offset_angle) * 0.008, 6),
                ordinal=stars[len(stars) // 2].ordinal,
            )
            update_object(relocated)
            return relocated

        black_hole = take_special("black_hole", 0)
        junction = take_special("junction", 1)

        cluster = tuple([*stars, black_hole, junction])
        for obj in cluster:
            assignments[obj.id] = polity.stem
            available.pop(obj.id)
        clusters[polity.stem] = cluster

    return assignments, clusters


def allocate_new_frontier_polities(
    objects: list[ArmObject],
    reserved_ids: Iterable[str],
    boundary_ownership: dict[str, str] | None = None,
    polities: tuple[FrontierPolity, ...] | None = None,
) -> tuple[dict[str, str], dict[str, tuple[ArmObject, ...]]]:
    """Allocate new polities on remaining neutrals.

    Prefers the polity's map half (Miradin +x / Raih -x). If that half is
    exhausted, borrows stars from the opposite half. Never mints stars.
    Star counts come from NEW_FRONTIER_STARS_BY_STEM when present.
    """
    targets = polities or NEW_FRONTIER_POLITIES
    reserved = set(reserved_ids)
    boundary = (
        set(boundary_ownership)
        if boundary_ownership is not None
        else reserved
    )
    object_indexes = {obj.id: index for index, obj in enumerate(objects)}
    available = {
        obj.id: obj
        for obj in objects
        if obj.id not in reserved and "star-extra" not in obj.id
    }
    assignments: dict[str, str] = {}
    clusters: dict[str, tuple[ArmObject, ...]] = {}
    locked_objects = [
        objects[object_indexes[object_id]]
        for object_id in boundary
        if object_id in object_indexes
    ]

    free_stars = [
        obj
        for obj in available.values()
        if obj.kind == "star" and "star-extra" not in obj.id
    ]

    def need_for(polity: FrontierPolity) -> int:
        return int(NEW_FRONTIER_STARS_BY_STEM.get(polity.stem, STARS_PER_POLITY))

    # Place larger pockets first so compact leftovers remain for 1-star vassals.
    ordered = sorted(targets, key=lambda p: (-need_for(p), p.stem))
    adjacent = list(locked_objects)

    for polity in ordered:
        need = need_for(polity)
        preferred = [
            obj for obj in free_stars if obj.x * polity.side > 0
        ]
        other = [
            obj for obj in free_stars if obj.x * polity.side <= 0
        ]
        pool = preferred + other
        if len(pool) < need:
            raise RuntimeError(
                f"Not enough free stars for {polity.stem}: need {need}, have {len(pool)}"
            )

        # Seed near existing territory when possible.
        if adjacent:
            seed = min(
                pool,
                key=lambda obj: (
                    0 if obj.x * polity.side > 0 else 1,
                    min(
                        (
                            math.hypot(obj.x - old.x, obj.y - old.y)
                            for old in adjacent
                        ),
                        default=0.0,
                    ),
                    obj.ordinal,
                    obj.id,
                ),
            )
        else:
            seed = pool[0]
        selected = sorted(
            pool,
            key=lambda obj: (
                0 if obj.x * polity.side > 0 else 1,
                math.hypot(obj.x - seed.x, obj.y - seed.y),
                obj.ordinal,
                obj.id,
            ),
        )[:need]
        selected_ids = {obj.id for obj in selected}
        free_stars = [obj for obj in free_stars if obj.id not in selected_ids]
        for object_id in selected_ids:
            available.pop(object_id, None)

        stars = sorted(selected, key=lambda obj: (obj.ordinal, obj.id))
        anchor_x = sum(obj.x for obj in stars) / len(stars)
        anchor_y = sum(obj.y for obj in stars) / len(stars)
        home_arm = Counter(obj.arm for obj in stars).most_common(1)[0][0]
        cluster_objs: list[ArmObject] = list(stars)

        def take_special(kind: str, offset_index: int) -> ArmObject | None:
            same_side = [
                obj
                for obj in available.values()
                if obj.kind == kind and obj.x * polity.side > 0
            ]
            any_free = [
                obj for obj in available.values() if obj.kind == kind
            ]
            pool_s = same_side or any_free
            if not pool_s:
                return None
            chosen = min(
                pool_s,
                key=lambda obj: (
                    math.hypot(obj.x - anchor_x, obj.y - anchor_y),
                    obj.ordinal,
                    obj.id,
                ),
            )
            distance = math.hypot(chosen.x - anchor_x, chosen.y - anchor_y)
            if chosen.x * polity.side > 0 and distance <= 0.12:
                available.pop(chosen.id, None)
                return chosen
            angle = (
                (len(LOCKED_FRONTIER_POLITIES) + len(clusters)) * 2
                + offset_index
            ) * 2.399963229728653
            radius = 0.008
            x = anchor_x + math.cos(angle) * radius
            y = anchor_y + math.sin(angle) * radius
            if x * polity.side <= 0:
                x = anchor_x + polity.side * radius
            relocated = replace(
                chosen,
                arm=home_arm,
                x=round(x, 6),
                y=round(y, 6),
                ordinal=stars[0].ordinal,
            )
            objects[object_indexes[chosen.id]] = relocated
            available.pop(chosen.id, None)
            return relocated

        for kind, offset in (("black_hole", 0), ("junction", 1)):
            special = take_special(kind, offset)
            if special is not None:
                cluster_objs.append(special)

        cluster = tuple(cluster_objs)
        for obj in cluster:
            assignments[obj.id] = polity.stem
        clusters[polity.stem] = cluster
        adjacent.extend(cluster)

    return assignments, clusters



def assign_objects_inside_territories(
    objects: list[ArmObject],
    assignments: dict[str, str],
    existing_hosts: Iterable[object],
) -> dict[str, str]:
    """Assign currently unclaimed objects already covered by polity fill.

    The calculation uses only the original polity hosts, so assigning objects
    does not recursively expand a territory and consume an entire arm.
    """
    hosts: list[tuple[float, float, str, float]] = []
    assigned_by_stem: dict[str, list[ArmObject]] = {}
    by_id = {obj.id: obj for obj in objects}
    for object_id, stem in assignments.items():
        assigned_by_stem.setdefault(stem, []).append(by_id[object_id])

    claim_by_stem: dict[str, float] = {}
    for stem, systems in assigned_by_stem.items():
        widest_nearest_gap = 0.0
        for system in systems:
            nearest_gap = min(
                (
                    math.hypot(system.x - other.x, system.y - other.y)
                    for other in systems
                    if other.id != system.id
                ),
                default=0.0,
            )
            widest_nearest_gap = max(widest_nearest_gap, nearest_gap)
        claim_by_stem[stem] = min(
            FRONTIER_CLAIM_MAX,
            max(
                FRONTIER_CLAIM_MIN,
                widest_nearest_gap * 0.58 + 0.012,
            ),
        )
        hosts.extend(
            (system.x, system.y, stem, claim_by_stem[stem])
            for system in systems
        )

    for row in existing_hosts:
        if (
            getattr(row, "id", "").startswith("frontier:")
            or not getattr(row, "stem", None)
            or getattr(row, "kind", None)
            not in {"star", "black_hole", "junction"}
        ):
            continue
        hosts.append(
            (
                float(getattr(row, "x")),
                float(getattr(row, "y")),
                str(getattr(row, "stem")),
                LEGACY_CLAIM_RADIUS,
            )
        )

    cell_size = 0.06
    cells: dict[tuple[int, int], list[tuple[float, float, str, float]]] = {}
    for host in hosts:
        key = (
            math.floor(host[0] / cell_size),
            math.floor(host[1] / cell_size),
        )
        cells.setdefault(key, []).append(host)

    additions: dict[str, str] = {}
    pixel_size = 2 * TERRITORY_MAP_LIMIT / TERRITORY_RASTER_SIZE
    marker_radius = MARKER_CAPTURE_PIXELS * pixel_size
    search_cells = math.ceil(
        (FRONTIER_CLAIM_MAX + marker_radius) / cell_size
    )
    sample_offsets = (
        (0.0, 0.0),
        (-marker_radius, 0.0),
        (marker_radius, 0.0),
        (0.0, -marker_radius),
        (0.0, marker_radius),
        (-marker_radius, -marker_radius),
        (-marker_radius, marker_radius),
        (marker_radius, -marker_radius),
        (marker_radius, marker_radius),
    )
    for obj in objects:
        if obj.id in assignments:
            continue
        cell_x = math.floor(obj.x / cell_size)
        cell_y = math.floor(obj.y / cell_size)
        candidates = [
            host
            for dx in range(-search_cells, search_cells + 1)
            for dy in range(-search_cells, search_cells + 1)
            for host in cells.get((cell_x + dx, cell_y + dy), ())
        ]
        pixel_x = math.floor(
            (obj.x + TERRITORY_MAP_LIMIT)
            / (2 * TERRITORY_MAP_LIMIT)
            * TERRITORY_RASTER_SIZE
        )
        pixel_y = math.floor(
            (TERRITORY_MAP_LIMIT - obj.y)
            / (2 * TERRITORY_MAP_LIMIT)
            * TERRITORY_RASTER_SIZE
        )
        sample_x = (
            (pixel_x + 0.5)
            / TERRITORY_RASTER_SIZE
            * 2
            * TERRITORY_MAP_LIMIT
            - TERRITORY_MAP_LIMIT
        )
        sample_y = (
            TERRITORY_MAP_LIMIT
            - (pixel_y + 0.5)
            / TERRITORY_RASTER_SIZE
            * 2
            * TERRITORY_MAP_LIMIT
        )
        coverage: dict[str, tuple[int, float]] = {}
        for offset_x, offset_y in sample_offsets:
            x = sample_x + offset_x
            y = sample_y + offset_y
            valid = [
                (math.hypot(x - host_x, y - host_y), stem)
                for host_x, host_y, stem, claim_radius in candidates
                if math.hypot(x - host_x, y - host_y) <= claim_radius
            ]
            if not valid:
                continue
            distance, stem = min(valid, key=lambda item: (item[0], item[1]))
            count, closest = coverage.get(stem, (0, math.inf))
            coverage[stem] = (count + 1, min(closest, distance))
        if coverage:
            additions[obj.id] = min(
                coverage,
                key=lambda stem: (
                    -coverage[stem][0],
                    coverage[stem][1],
                    stem,
                ),
            )

    return additions


def map_canonical_frontier_catalog(
    clusters: dict[str, tuple[ArmObject, ...]],
) -> dict[str, dict]:
    """Map Efols canonical stars/details onto the selected map objects."""
    if not _CATALOG_PATH.is_file():
        raise RuntimeError(f"Missing frontier catalog: {_CATALOG_PATH}")
    catalog = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    mapped: dict[str, dict] = {}

    from app.service.frontier_naming import (
        generated_frontier_worlds,
        is_placeholder_star_label,
        natural_frontier_black_hole_name,
        natural_frontier_junction_name,
        natural_frontier_star_name,
    )

    star_type_names = {
        "class_m": "Class M",
        "class_k": "Class K",
        "class_g": "Class G",
        "class_f": "Class F",
        "class_a": "Class A",
        "class_b": "Class B",
        "black_hole": "Black Hole",
        "junction": "Empty hypercorridor node",
    }

    for polity in FRONTIER_POLITIES:
        cluster = clusters.get(polity.stem)
        if cluster is None:
            continue
        entries = catalog.get(polity.stem) or []
        for kind in ("star", "black_hole", "junction"):
            objects_of_kind = sorted(
                (obj for obj in cluster if obj.kind == kind),
                key=lambda obj: (obj.ordinal, obj.id),
            )
            entries_of_kind = sorted(
                (entry for entry in entries if entry.get("kind") == kind),
                key=lambda entry: entry.get("token") or "",
            )
            for obj, entry in zip(objects_of_kind, entries_of_kind):
                if obj.kind == "star" and is_placeholder_star_label(
                    entry.get("token"),
                    entry.get("nameEn"),
                    entry.get("nameRu"),
                ):
                    token, name_en, name_ru = natural_frontier_star_name(obj.id)
                    worlds = entry.get("worlds") or []
                    if not worlds:
                        worlds = generated_frontier_worlds(obj.id, token)
                    mapped[obj.id] = {
                        **entry,
                        "token": token,
                        "nameEn": name_en,
                        "nameRu": name_ru,
                        "worlds": worlds,
                    }
                else:
                    mapped[obj.id] = entry
            for obj in objects_of_kind[len(entries_of_kind) :]:
                if obj.kind == "star":
                    token, name_en, name_ru = natural_frontier_star_name(obj.id)
                    worlds = generated_frontier_worlds(obj.id, token)
                elif obj.kind == "black_hole":
                    token, name_en, name_ru = (
                        natural_frontier_black_hole_name(obj.id)
                    )
                    worlds = []
                else:
                    token, name_en, name_ru = (
                        natural_frontier_junction_name(obj.id)
                    )
                    worlds = []
                mapped[obj.id] = {
                    "canonicalId": None,
                    "token": token,
                    "kind": obj.kind,
                    "nameEn": name_en,
                    "nameRu": name_ru,
                    "starType": star_type_names[obj.star_type_key],
                    "starTypeKey": obj.star_type_key,
                    "sectorId": "",
                    "sectorNameEn": "",
                    "worlds": worlds,
                    "uninhabited": [],
                    "features": [],
                    "territoryAnchor": True,
                }

        mapped_stars = sum(
            obj.id in mapped for obj in cluster if obj.kind == "star"
        )
        expected_stars = NEW_FRONTIER_STARS_BY_STEM.get(
            polity.stem, STARS_PER_POLITY
        )
        if mapped_stars != expected_stars and polity.stem in NEW_FRONTIER_STEMS:
            raise RuntimeError(
                f"{polity.stem}: mapped {mapped_stars}/{expected_stars} stars"
            )
        if (
            polity.stem not in NEW_FRONTIER_STEMS
            and mapped_stars != STARS_PER_POLITY
            and mapped_stars < 1
        ):
            raise RuntimeError(
                f"{polity.stem}: mapped {mapped_stars} stars"
            )

    return mapped
