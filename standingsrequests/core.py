from enum import IntEnum

from django.utils.functional import classproperty
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter

from .app_settings import (
    SR_OPERATION_MODE,
    STANDINGS_API_CHARID,
    STR_ALLIANCE_IDS,
    STR_CORP_IDS,
)


class MainOrganizations:
    """Configured main alliances and corporations from settings"""

    @classmethod
    def is_character_a_member(cls, character: EveCharacter) -> bool:
        """Check if the Pilot is in the auth instances organisation

        character: EveCharacter

        returns True if the character is in the organisation, False otherwise
        """
        return (
            character.corporation_id in cls.corporation_ids
            or character.alliance_id in cls.alliance_ids
        )

    @classproperty
    def corporation_ids(cls) -> set:
        return {int(org_id) for org_id in list(STR_CORP_IDS)}

    @classproperty
    def alliance_ids(cls) -> set:
        return {int(org_id) for org_id in list(STR_ALLIANCE_IDS)}


class BaseConfig:
    @classproperty
    def standings_character_id(cls) -> int:
        return STANDINGS_API_CHARID

    @classproperty
    def operation_mode(cls) -> str:
        return SR_OPERATION_MODE

    @staticmethod
    def standings_character() -> EveCharacter:
        """returns the configured standings character"""
        try:
            character = EveCharacter.objects.get(character_id=STANDINGS_API_CHARID)
        except EveCharacter.DoesNotExist:
            character = EveCharacter.objects.create_character(STANDINGS_API_CHARID)
            EveEntity.objects.get_or_create(
                id=character.character_id,
                defaults={
                    "name": character.character_name,
                    "category": EveEntity.CATEGORY_CHARACTER,
                },
            )

        return character

    @classmethod
    def standings_source_entity(cls) -> object:
        """returns the entity that all standings are fetched from

        returns None when in alliance mode, but character has no alliance
        """
        character = cls.standings_character()
        if cls.operation_mode == "alliance":
            if character.alliance_id:
                entity, _ = EveEntity.objects.get_or_create(
                    id=character.alliance_id,
                    defaults={
                        "name": character.alliance_name,
                        "category": EveEntity.CATEGORY_ALLIANCE,
                    },
                )
            else:
                entity = None
        elif cls.operation_mode == "corporation":
            entity, _ = EveEntity.objects.get_or_create(
                id=character.corporation_id,
                defaults={
                    "name": character.corporation_name,
                    "category": EveEntity.CATEGORY_CORPORATION,
                },
            )
        else:
            raise NotImplementedError()

        return entity


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
