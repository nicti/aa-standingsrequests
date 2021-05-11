from django.utils.functional import classproperty

from allianceauth.eveonline.models import EveCharacter

from .app_settings import STR_ALLIANCE_IDS, STR_CORP_IDS


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
