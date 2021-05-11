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
