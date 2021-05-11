from allianceauth.eveonline.evelinks import eveimageserver

from ..models import CharacterAssociation


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
            assoc = CharacterAssociation.objects.select_related(
                "character", "corporation", "alliance", "main_character"
            ).get(character_id=self.character_id)
        except CharacterAssociation.DoesNotExist:
            assoc = None
            self.corporation_id = None
            self.corporation_name = None
            self.alliance_id = None
        else:
            self.corporation_id = assoc.corporation_id
            self.alliance_id = assoc.alliance_id

            # Add a main character attribute (deviates from original model)
            if (
                assoc.main_character_id is not None
                and assoc.main_character_id != self.character_id
            ):
                self.main_character = EveCharacterHelper(assoc.main_character_id)

        self.character_name = (
            assoc.character.name if assoc and assoc.character else None
        )
        self.corporation_name = (
            assoc.corporation.name if assoc and assoc.corporation else None
        )
        self.alliance_name = assoc.alliance.name if assoc and assoc.alliance else None

    def portrait_url(self, size: int = eveimageserver._DEFAULT_IMAGE_SIZE) -> str:
        return eveimageserver.character_portrait_url(self.character_id, size)
