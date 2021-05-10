from eveuniverse.models import EveEntity

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
            assoc = CharacterAssociation.objects.get(character_id=self.character_id)

        except CharacterAssociation.DoesNotExist:
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

        entity_ids = [
            entity_id
            for entity_id in [self.character_id, self.corporation_id, self.alliance_id]
            if entity_id is not None
        ]
        resolver = EveEntity.objects.bulk_resolve_names(entity_ids)
        self.character_name = (
            resolver.to_name(self.character_id) if self.character_id else None
        )
        self.corporation_name = (
            resolver.to_name(self.corporation_id) if self.corporation_id else None
        )
        self.alliance_name = (
            resolver.to_name(self.alliance_id) if self.alliance_id else None
        )

    def portrait_url(self, size: int = eveimageserver._DEFAULT_IMAGE_SIZE) -> str:
        return eveimageserver.character_portrait_url(self.character_id, size)
