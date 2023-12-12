from enum import IntEnum
from typing import Set


class ContactTypeId(IntEnum):
    CHARACTER_AMARR = 1373
    CHARACTER_KUNNI = 1374
    CHARACTER_CIVRE = 1375
    CHARACTER_DETEIS = 1376
    CHARACTER_GALLENTE = 1377
    CHARACTER_INTAKI = 1378
    CHARACTER_SEBIESTOR = 1379
    CHARACTER_BRUTOR = 1380
    CHARACTER_STATIC = 1381
    CHARACTER_MODIFIER = 1382
    CHARACTER_ACHURA = 1383
    CHARACTER_JIN_MEI = 1384
    CHARACTER_KHANID = 1385
    CHARACTER_VHEROKIOR = 1386
    CHARACTER_DRIFTER = 34574
    CORPORATION = 2

    @property
    def is_character(self) -> bool:
        return self.value in self.character_ids()

    @property
    def is_corporation(self) -> bool:
        return self.value in self.corporation_ids()

    @classmethod
    def character_id(cls) -> int:
        return cls.CHARACTER_AMARR

    @classmethod
    def character_ids(cls) -> Set[int]:
        return {
            cls.CHARACTER_AMARR,
            cls.CHARACTER_KUNNI,
            cls.CHARACTER_CIVRE,
            cls.CHARACTER_DETEIS,
            cls.CHARACTER_GALLENTE,
            cls.CHARACTER_INTAKI,
            cls.CHARACTER_SEBIESTOR,
            cls.CHARACTER_BRUTOR,
            cls.CHARACTER_STATIC,
            cls.CHARACTER_MODIFIER,
            cls.CHARACTER_ACHURA,
            cls.CHARACTER_JIN_MEI,
            cls.CHARACTER_KHANID,
            cls.CHARACTER_VHEROKIOR,
            cls.CHARACTER_DRIFTER,
        }

    @classmethod
    def corporation_ids(cls) -> Set[int]:
        return {cls.CORPORATION}
