import logging

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import (
    EveCorporationInfo, EveCharacter, EveAllianceInfo
)
from allianceauth.eveonline.providers import ObjectNotFound

from bravado.exception import HTTPError

from ..helpers.esi_fetch import esi_fetch
from ..utils import chunks

logger = logging.getLogger(__name__)


class EveEntityManager:
    
    @staticmethod
    def get_name(eve_entity_id):
        name = EveEntityManager.get_name_from_auth(eve_entity_id)
        if name is None:
            name = EveEntityManager.get_name_from_api(eve_entity_id)
        if name is None:
            logger.error(
                'Could not get name for eve_entity_id %s', eve_entity_id
            )
        return name

    @staticmethod
    def get_names(eve_entity_ids):
        """
        Get the names of the given entity ids from auth or if not there api
        :param eve_entity_ids: array of int entity ids who's names to fetch
        :return: dict with entity_id as key and name as value
        """        
        need_api = []
        names_info = dict()
        for entity_id in set(eve_entity_ids):
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
            alliance = EveAllianceInfo.objects.get(alliance_id=eve_entity_id)
            return alliance.alliance_name
        except EveAllianceInfo.DoesNotExist:
            # not this one either
            pass

        # Unsuccessful
        return None

    @staticmethod
    def get_names_from_api(eve_entity_ids):
        """
        Get the names of the given entity ids from the EVE API servers
        :param eve_entity_ids: array of int entity ids who's names to fetch
        :return: dict with entity_id as key and name as value
        """
        # this is to make sure there are no duplicates        
        eve_entity_ids = list(set(eve_entity_ids))

        names_info = dict()
        chunk_size = 1000
        for ids_chunk in chunks(eve_entity_ids, chunk_size):
            infos = EveEntityManager.__get_names_from_api(ids_chunk)
            for info in infos:
                names_info[info['id']] = info['name']
        
        return names_info

    @staticmethod
    def __get_names_from_api(eve_entity_ids):
        """
        Get the names of the given entity ids from the EVE API servers
        :param eve_entity_ids: array of int entity ids who's names to fetch
        :return: array of objects with keys id and name or None if unsuccessful
        """
        logger.debug(
            "Attempting to get entity name from API for ids %s", eve_entity_ids
        )
        try:
            infos = esi_fetch(
                'Universe.post_universe_names', args={'ids': eve_entity_ids}
            )
            return infos
        
        except HTTPError:
            logger.exception(
                "Error occurred while trying to query api for entity id=%s",
                eve_entity_ids
            )
            raise ObjectNotFound(eve_entity_ids, 'universe_entities')

    @staticmethod
    def get_name_from_api(eve_entity_id):
        """
        Get the name of the given entity id from the EVE API servers
        :param eve_entity_id: int entity id who's name to fetch
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
        return [
            owner_ship.character 
            for owner_ship in CharacterOwnership.objects.filter(user=user)
        ]

    @staticmethod
    def is_character_owned_by_user(character_id, user):
        try:
            CharacterOwnership.objects\
                .get(user=user, character__character_id=character_id)

            return True
        except CharacterOwnership.DoesNotExist:
            return False

    @staticmethod
    def get_state_of_character(char):
        try:
            ownership = CharacterOwnership.objects\
                .get(character__character_id=char.character_id)
            return ownership.user.profile.state.name

        except CharacterOwnership.DoesNotExist:
            return None
