from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from .. import __title__

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class EveEntityHelper:
    @staticmethod
    def get_owner_from_character_id(character_id):
        """
        Attempt to get the character owner from the given character_id
        :param character_id: int character ID to get the owner for
        :return: User (django) or None
        """
        char = EveCharacter.objects.get_character_by_id(character_id)
        if char is not None:
            try:
                ownership = CharacterOwnership.objects.get(character=char)
                return ownership.user

            except CharacterOwnership.DoesNotExist:
                return None
        else:
            return None

    @staticmethod
    def get_characters_by_user(user):
        return EveCharacter.objects.filter(
            character_ownership__user=user
        ).select_related("character_ownership__user")

    @staticmethod
    def is_character_owned_by_user(character_id, user):
        try:
            CharacterOwnership.objects.get(
                user=user, character__character_id=character_id
            )

            return True
        except CharacterOwnership.DoesNotExist:
            return False

    @staticmethod
    def get_state_of_character(char):
        try:
            ownership = CharacterOwnership.objects.get(
                character__character_id=char.character_id
            )
            return ownership.user.profile.state.name

        except CharacterOwnership.DoesNotExist:
            return None
