
import logging
from allianceauth.eveonline.models import EveCorporationInfo, EveCharacter,\
    EveAllianceInfo
from esi.clients import esi_client_factory
from allianceauth.eveonline.providers import ObjectNotFound
from bravado.exception import HTTPNotFound, HTTPBadGateway, HTTPGatewayTimeout
from allianceauth.authentication.models import CharacterOwnership
from . import SWAGGER_SPEC_PATH
from time import sleep
from past.builtins import xrange


logger = logging.getLogger(__name__)


class EveEntityManager:

    def __init__(self):
        pass

    @staticmethod
    def get_name(eve_entity_id):
        name = EveEntityManager.get_name_from_auth(eve_entity_id)
        if name is None:
            name = EveEntityManager.get_name_from_api(eve_entity_id)
        if name is None:
            logger.error('Could not get name for eve_entity_id %s',
                         eve_entity_id)
        return name

    @staticmethod
    def get_names(eve_entity_ids):
        """
        Get the names of the given entity ids from auth or if not there api
        :param eve_entity_ids: array of int entity ids whos names to fetch
        :return: dict with entity_id as key and name as value
        """
        if not isinstance(eve_entity_ids, set):
            eve_entity_ids = set(eve_entity_ids)
        need_api = []
        names_info = {}
        for entity_id in eve_entity_ids:
            entity_id = int(entity_id)
            entity_name = EveEntityManager.get_name_from_auth(entity_id)
            if entity_name is None:
                need_api.append(entity_id)
            else:
                names_info[entity_id] = entity_name

        if len(need_api) > 0:
            api_names_info = EveEntityManager.get_names_from_api(need_api)
            names_info.update(api_names_info)

        return names_info

    @staticmethod
    def get_name_from_auth(eve_entity_id):
        """
        Attempts to get an EVE entities (pilot/corp/alliance) name from auth
        :param eve_entity_id: int id of the entity to get the name for
        :return: str name of the entity if successful or None
        """
        # Try pilots
        try:
            pilot = EveCharacter.objects.get(character_id=eve_entity_id)
            return pilot.character_name
        except EveCharacter.DoesNotExist:
            # not a known character
            pass

        # Try corps
        try:
            corp = EveCorporationInfo.objects.get(corporation_id=eve_entity_id)
            return corp.corporation_name
        except EveCorporationInfo.DoesNotExist:
            # not a known corp
            pass

        # Try alliances
        try:
            alli = EveAllianceInfo.objects.get(alliance_id=eve_entity_id)
            return alli.alliance_name
        except EveAllianceInfo.DoesNotExist:
            # not this one either
            pass

        # Unsuccessful
        return None

    @staticmethod
    def get_names_from_api(eve_entity_ids):
        """
        Get the names of the given entity ids from the EVE API servers
        :param eve_entity_ids: array of int entity ids whos names to fetch
        :return: dict with entity_id as key and name as value
        """
        # this is to make sure there is no duplicates
        if not isinstance(eve_entity_ids, set):
            eve_entity_ids = set(eve_entity_ids)
        eve_entity_ids = list(eve_entity_ids)

        chunk_size = 1000
        length = len(eve_entity_ids)
        chunks = [eve_entity_ids[x:x+chunk_size] for x in xrange(0, length, chunk_size)]
        logger.debug('Got %s chunks containing max %s each to process with a total of %s', len(chunks), chunk_size, length)

        names_info = {}
        for chunk in chunks:
            infos = EveEntityManager.__get_names_from_api(chunk)
            for info in infos:
                names_info[info['id']] = info['name']
        return names_info

    @staticmethod
    def __get_names_from_api(eve_entity_ids, count=1):
        """
        Get the names of the given entity ids from the EVE API servers
        :param eve_entity_ids: array of int entity ids whos names to fetch
        :return: array of objects with keys id and name or None if unsuccessful
        """
        logger.debug("Attempting to get entity name from API for ids {0}".format(eve_entity_ids))
        client = esi_client_factory(spec_file=SWAGGER_SPEC_PATH)
        try:
            infos = client.Universe.post_universe_names(ids=eve_entity_ids).result()
            return infos

            logger.error("Error occured while trying to query api for entity name id=%s", eve_entity_ids)

        except HTTPNotFound:
            raise ObjectNotFound(eve_entity_ids, 'universe_entitys')
        except (HTTPBadGateway, HTTPGatewayTimeout):
            if count >= 5:
                logger.exception('Failed to get entity name %s times.', count)
                return None
            else:
                sleep(count**2)
                return EveEntityManager.__get_names_from_api(eve_entity_ids,
                                                             count=count+1)

    @staticmethod
    def get_name_from_api(eve_entity_id):
        """
        Get the name of the given entity id from the EVE API servers
        :param eve_entity_id: int entity id whos name to fetch
        :return: str entity name or None if unsuccessful
        """
        eve_entity_id = int(eve_entity_id)
        infos = EveEntityManager.get_names_from_api([eve_entity_id])
        if eve_entity_id in infos:
            return infos[eve_entity_id]

        return None

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
        return [owner_ship.character for owner_ship in CharacterOwnership.objects.filter(user=user)]

    @staticmethod
    def is_character_owned_by_user(character_id, user):
        try:
            CharacterOwnership.objects.get(user=user, character__character_id=character_id)
            return True
        except CharacterOwnership.DoesNotExist:
            return False
