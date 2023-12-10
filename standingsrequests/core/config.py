from django.utils.functional import classproperty
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter

from standingsrequests.app_settings import (
    SR_OPERATION_MODE,
    STANDINGS_API_CHARID,
    STR_ALLIANCE_IDS,
    STR_CORP_IDS,
)
from standingsrequests.constants import OperationMode


class BaseConfig:
    @classproperty
    def owner_character_id(cls) -> int:
        return STANDINGS_API_CHARID

    @classproperty
    def operation_mode(cls) -> OperationMode:
        """Return current operation mode."""
        return OperationMode(SR_OPERATION_MODE)

    @staticmethod
    def owner_character() -> EveCharacter:
        """returns the configured standings character"""
        try:
            return EveCharacter.objects.get(character_id=STANDINGS_API_CHARID)
        except EveCharacter.DoesNotExist:
            return EveCharacter.objects.create_character(STANDINGS_API_CHARID)

    @classmethod
    def standings_source_entity(cls) -> object:
        """returns the entity that all standings are fetched from

        returns None when in alliance mode, but character has no alliance
        """
        character = cls.owner_character()
        if cls.operation_mode is OperationMode.ALLIANCE:
            if character.alliance_id:
                entity, _ = EveEntity.objects.get_or_create_esi(
                    id=character.alliance_id
                )
            else:
                entity = None
        elif cls.operation_mode is OperationMode.CORPORATION:
            entity, _ = EveEntity.objects.get_or_create_esi(id=character.corporation_id)
        else:
            raise NotImplementedError()

        return entity


class MainOrganizations:
    """Configured main alliances and corporations from settings"""

    @classmethod
    def is_character_a_member(cls, character: EveCharacter) -> bool:
        """Return True if the character is in the organization, False otherwise."""
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
