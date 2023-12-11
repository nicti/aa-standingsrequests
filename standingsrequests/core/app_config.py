"""API for current configuration from settings."""

from typing import Optional, Set

from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter

from standingsrequests.app_settings import (
    SR_OPERATION_MODE,
    STANDINGS_API_CHARID,
    STR_ALLIANCE_IDS,
    STR_CORP_IDS,
)
from standingsrequests.constants import OperationMode


def operation_mode() -> OperationMode:
    """Return current operation mode."""
    return OperationMode(SR_OPERATION_MODE)


def owner_character() -> EveCharacter:
    """Return the configured standings character."""
    try:
        return EveCharacter.objects.get(character_id=STANDINGS_API_CHARID)
    except EveCharacter.DoesNotExist:
        return EveCharacter.objects.create_character(STANDINGS_API_CHARID)


def standings_source_entity() -> Optional[EveEntity]:
    """Returns the entity that all standings are fetched from.

    When in alliance mode and character has no alliance, then return None
    """
    character = owner_character()
    if operation_mode() is OperationMode.ALLIANCE:
        if character.alliance_id:
            obj, _ = EveEntity.objects.get_or_create_esi(id=character.alliance_id)
            return obj

        return None

    if operation_mode() is OperationMode.CORPORATION:
        obj, _ = EveEntity.objects.get_or_create_esi(id=character.corporation_id)
        return obj

    raise NotImplementedError()


def is_character_a_member(character: EveCharacter) -> bool:
    """Return True if the character is in the organization, False otherwise."""
    return (
        character.corporation_id in corporation_ids()
        or character.alliance_id in alliance_ids()
    )


def corporation_ids() -> Set[int]:
    """Return corporation IDs, which belong the configured organization."""
    result = {int(org_id) for org_id in list(STR_CORP_IDS)}
    return result


def alliance_ids() -> Set[int]:
    """Return alliance IDs, which belong to the configured organization."""
    result = {int(org_id) for org_id in list(STR_ALLIANCE_IDS)}
    return result
