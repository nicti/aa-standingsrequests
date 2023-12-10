from enum import IntEnum

from django.utils.functional import classproperty


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
    ALLIANCE_TYPE_ID = 16159
    CORPORATION_TYPE_ID = 2

    @classproperty
    def character_id(cls):
        return cls.CHARACTER_AMARR_TYPE_ID

    @classproperty
    def character_ids(cls):
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

    @classproperty
    def corporation_ids(cls):
        return {cls.CORPORATION_TYPE_ID}

    @classproperty
    def corporation_id(cls):
        return cls.CORPORATION_TYPE_ID

    @classproperty
    def alliance_ids(cls):
        return {cls.ALLIANCE_TYPE_ID}

    @classproperty
    def alliance_id(cls):
        return cls.ALLIANCE_TYPE_ID

    @classmethod
    def is_character(cls, type_id):
        return type_id in cls.character_ids

    @classmethod
    def is_corporation(cls, type_id):
        return type_id in cls.corporation_ids

    @classmethod
    def is_alliance(cls, type_id):
        return type_id in cls.alliance_ids
