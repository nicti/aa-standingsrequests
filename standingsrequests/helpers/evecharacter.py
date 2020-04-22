from django.core.exceptions import ObjectDoesNotExist
from ..models import EveNameCache, CharacterAssociation


class EveCharacterHelper:
    """
    Mimics Alliance Auths EveCharacter with internal standingstool data instead
    """
    # Not implemented
    corporation_ticker = None
    api_id = ""
    user = None

    def __init__(self, character_id):
        self.character_id = int(character_id)
        self.main_character = None
        self.alliance_name = None
        try:
            assoc = CharacterAssociation.objects.get(character_id=self.character_id)
            self.corporation_id = assoc.corporation_id
            self.corporation_name = EveNameCache.get_name(assoc.corporation_id)

            self.alliance_id = assoc.alliance_id
            if self.alliance_id is not None:
                self.alliance_name = EveNameCache.get_name(assoc.alliance_id)

            # Add a main character attribute (deviates from original model)
            if (
                assoc.main_character_id is not None 
                and assoc.main_character_id != self.character_id
            ):
                self.main_character = EveCharacterHelper(assoc.main_character_id)

        except ObjectDoesNotExist:
            self.corporation_id = None
            self.corporation_name = None
            self.alliance_id = None

        self.character_name = EveNameCache.get_name(character_id)
