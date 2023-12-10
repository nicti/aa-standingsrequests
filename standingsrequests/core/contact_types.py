from enum import IntEnum
from typing import Set


class ContactType(IntEnum):
    CHARACTER_AMARR_TYPE_ID = 1373
    CHARACTER_NI_KUNNI_TYPE_ID = 1374
    CHARACTER_CIVRE_TYPE_ID = 1375
    CHARACTER_DETEIS_TYPE_ID = 1376
    CHARACTER_GALLENTE_TYPE_ID = 1377
    CHARACTER_INTAKI_TYPE_ID = 1378
    CHARACTER_SEBIESTOR_TYPE_ID = 1379
    CHARACTER_BRUTOR_TYPE_ID = 1380
    CHARACTER_STATIC_TYPE_ID = 1381
    CHARACTER_MODIFIER_TYPE_ID = 1382
    CHARACTER_ACHURA_TYPE_ID = 1383
    CHARACTER_JIN_MEI_TYPE_ID = 1384
    CHARACTER_KHANID_TYPE_ID = 1385
    CHARACTER_VHEROKIOR_TYPE_ID = 1386
    CHARACTER_DRIFTER_TYPE_ID = 34574
    CORPORATION_TYPE_ID = 2

    @property
    def is_character(self) -> bool:
        return self.value in self.character_ids()

    @property
    def is_corporation(self) -> bool:
        return self.value in self.corporation_ids()

    @classmethod
    def character_id(cls) -> int:
        return cls.CHARACTER_AMARR_TYPE_ID

    @classmethod
    def character_ids(cls) -> Set[int]:
        return {
            cls.CHARACTER_AMARR_TYPE_ID,
            cls.CHARACTER_NI_KUNNI_TYPE_ID,
            cls.CHARACTER_CIVRE_TYPE_ID,
            cls.CHARACTER_DETEIS_TYPE_ID,
            cls.CHARACTER_GALLENTE_TYPE_ID,
            cls.CHARACTER_INTAKI_TYPE_ID,
            cls.CHARACTER_SEBIESTOR_TYPE_ID,
            cls.CHARACTER_BRUTOR_TYPE_ID,
            cls.CHARACTER_STATIC_TYPE_ID,
            cls.CHARACTER_MODIFIER_TYPE_ID,
            cls.CHARACTER_ACHURA_TYPE_ID,
            cls.CHARACTER_JIN_MEI_TYPE_ID,
            cls.CHARACTER_KHANID_TYPE_ID,
            cls.CHARACTER_VHEROKIOR_TYPE_ID,
            cls.CHARACTER_DRIFTER_TYPE_ID,
        }

    @classmethod
    def corporation_ids(cls) -> Set[int]:
        return {cls.CORPORATION_TYPE_ID}

    @classmethod
    def corporation_id(cls) -> int:
        return cls.CORPORATION_TYPE_ID
