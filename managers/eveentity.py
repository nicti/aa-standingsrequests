from eveonline.managers import EveManager
import evelink
import logging

logger = logging.getLogger(__name__)


class EveEntityManager:

    def __init__(self):
        pass

    @staticmethod
    def get_name_from_auth(eve_entity_id):
        """
        Attempts to get an EVE entities (pilot/corp/alliance) name from auth
        :param eve_entity_id: int id of the entity to get the name for
        :return: str name of the entity if successful or None
        """
        # Try pilots
        pilot = EveManager.get_character_by_id(eve_entity_id)
        if pilot is not None:
            return pilot.character_name
        # Try corps
        corp = EveManager.get_corporation_info_by_id(eve_entity_id)
        if corp is not None:
            return corp.corporation_name

        # Try alliances
        alli = EveManager.get_alliance_info_by_id(eve_entity_id)
        if alli is not None:
            return alli.alliance_name

        # Unsuccessful
        return None

    @staticmethod
    def get_name_from_api(eve_entity_id):
        """
        Get the name of the given entity id from the EVE API servers
        :param eve_entity_id: int entity id whos name to fetch
        :return: str entity name or None if unsuccessful
        """
        logger.debug("Attempting to get entity name from API for id {0}".format(eve_entity_id))
        try:
            eve = evelink.eve.EVE()
            response = eve.character_name_from_id(int(eve_entity_id))
            return response.result
        except evelink.api.APIError as error:
            logger.debug("APIError occured while trying to query api server. Entity may not exist or API error")
            return None

    @staticmethod
    def get_owner_from_character_id(character_id):
        """
        Attempt to get the character owner from the given character_id
        :param character_id: int character ID to get the owner for
        :return: User (django) or None
        """
        char = EveManager.get_character_by_id(character_id)
        if char is not None:
            return char.user
        else:
            return None
