import random
from unittest.mock import Mock, patch

from bravado.exception import HTTPNotFound

from django.test import TestCase

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models \
    import EveCharacter, EveCorporationInfo, EveAllianceInfo
from allianceauth.eveonline.providers import ObjectNotFound
from allianceauth.tests.auth_utils import AuthUtils

from . import _get_random_string
from .my_test_data import get_entity_name, get_entity_names
from ..managers.eveentity import EveEntityManager
from ..utils import set_test_logger


MODULE_PATH = 'standingsrequests.managers.eveentity'
logger = set_test_logger(MODULE_PATH, __file__)


def get_entity_name_auth(entity_id):
    """this one returns a subset"""
    entities = {
        1001: 'Bruce Wayne',
        1002: 'Peter Parker',        
    }
    if entity_id in entities:
        return entities[entity_id]
    else:
        return None


def get_names_from_api(entity_ids, count=1):
    """returns list of found entities in ESI format"""
    return [
        {'id': key, 'name': value} 
        for key, value in get_entity_names(entity_ids).items()
    ]


class TestEveEntityManager(TestCase):
    
    def setUp(self):
        EveCharacter.objects.all().delete()
        EveCorporationInfo.objects.all().delete()
        EveAllianceInfo.objects.all().delete()

    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_api')
    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_auth')   
    def test_get_name_from_auth(
        self, mock_get_name_from_auth, 
        mock_get_name_from_api
    ):
        mock_get_name_from_auth.side_effect = get_entity_name_auth
        mock_get_name_from_api.side_effect = get_entity_name

        name = EveEntityManager.get_name(1001)
        self.assertEqual(name, 'Bruce Wayne')

    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_api')
    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_auth')
    def test_get_name_from_api(
        self, mock_get_name_from_auth, 
        mock_get_name_from_api
    ):
        mock_get_name_from_auth.side_effect = get_entity_name_auth
        mock_get_name_from_api.side_effect = get_entity_name

        name = EveEntityManager.get_name(1003)
        self.assertEqual(name, 'Clark Kent')

    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_api')
    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_auth')
    def test_get_name_fails(
        self, mock_get_name_from_auth, 
        mock_get_name_from_api
    ):
        mock_get_name_from_auth.side_effect = get_entity_name_auth
        mock_get_name_from_api.side_effect = get_entity_name

        self.assertIsNone(EveEntityManager.get_name(1999))  

    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_api')
    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_auth')
    def test_get_names_from_auth(
        self, mock_get_name_from_auth, 
        mock_get_name_from_api
    ):
        mock_get_name_from_auth.side_effect = get_entity_name_auth
        mock_get_name_from_api.side_effect = get_entity_name

        names = EveEntityManager.get_names([1001, 1002])
        self.assertDictEqual(
            names, 
            {1001: 'Bruce Wayne', 1002: 'Peter Parker'}
        )

    @patch(MODULE_PATH + '.EveEntityManager.get_names_from_api')
    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_auth')
    def test_get_names_from_auth_and_api(
        self, mock_get_name_from_auth, 
        mock_get_names_from_api
    ):
        mock_get_name_from_auth.side_effect = get_entity_name_auth
        mock_get_names_from_api.side_effect = get_entity_names

        names = EveEntityManager.get_names([1001, 1003])
        self.assertDictEqual(
            names, 
            {1001: 'Bruce Wayne', 1003: 'Clark Kent'}
        )

    @patch(MODULE_PATH + '.EveEntityManager.get_names_from_api')
    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_auth')
    def test_get_names_from_auth_and_api_not_found(
        self, mock_get_name_from_auth, 
        mock_get_names_from_api
    ):
        mock_get_name_from_auth.side_effect = get_entity_name_auth
        mock_get_names_from_api.side_effect = get_entity_names

        names = EveEntityManager.get_names([1998, 1999])
        self.assertDictEqual(
            names, 
            dict()
        )

    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_api')
    @patch(MODULE_PATH + '.EveEntityManager.get_name_from_auth')
    def test_get_names_from_auth_w_set(
        self, mock_get_name_from_auth, mock_get_name_from_api
    ):
        mock_get_name_from_auth.side_effect = get_entity_name_auth
        mock_get_name_from_api.side_effect = get_entity_name

        names = EveEntityManager.get_names({1001, 1002})
        self.assertDictEqual(
            names, 
            {1001: 'Bruce Wayne', 1002: 'Peter Parker'}
        )
    
    def test_get_name_from_auth_none_exists(self):    
        self.assertIsNone(EveEntityManager.get_name_from_auth(1999))

    def test_get_name_from_auth_character(self):
        EveCharacter.objects.create(
            character_id=1001,
            character_name='Bruce Wayne',
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1'
        )
        self.assertEqual(
            EveEntityManager.get_name_from_auth(1001),
            'Bruce Wayne'
        )

    def test_get_name_from_auth_corporation(self):
        EveCorporationInfo.objects.create(            
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1',
            member_count=42
        )
        self.assertEqual(
            EveEntityManager.get_name_from_auth(2001),
            'Dummy Corp 1'
        )

    def test_get_name_from_auth_alliance(self):
        EveAllianceInfo.objects.create(            
            alliance_id=3001,
            alliance_name='Dummy Alliance 1',
            alliance_ticker='DA1',
            executor_corp_id=2001
        )
        self.assertEqual(
            EveEntityManager.get_name_from_auth(3001),
            'Dummy Alliance 1'
        )

    @patch(
        MODULE_PATH + '.EveEntityManager._EveEntityManager__get_names_from_api'
    )
    def test_get_names_from_api_normal(self, mock__get_names_from_api):
        mock__get_names_from_api.side_effect = get_names_from_api

        names = EveEntityManager.get_names_from_api([1001, 1003])
        self.assertDictEqual(
            names, 
            {1001: 'Bruce Wayne', 1003: 'Clark Kent'}
        )

    @patch(
        MODULE_PATH + '.EveEntityManager._EveEntityManager__get_names_from_api'
    )
    def test_get_names_from_api_chunks(self, mock__get_names_from_api):
                
        def get_names_from_api_randoms(eve_entity_ids):
            return [
                {'id': id, 'name': _get_random_string(16)}
                for id in eve_entity_ids
            ]
        
        mock__get_names_from_api.side_effect = get_names_from_api_randoms

        ids = {random.randrange(10000, 20000) for x in range(2000)}

        names = EveEntityManager.get_names_from_api(ids)
        self.assertEqual(len(names), len(ids))

    @patch('standingsrequests.helpers.esi_fetch._esi_client')
    def test__get_names_from_api_normal(self, mock_esi_client):
        ids = [1001, 1002, 1003]
        infos_expected = get_names_from_api(ids)
        mock_esi_client.return_value.Universe.post_universe_names.return_value\
            .result.return_value = infos_expected

        infos = EveEntityManager._EveEntityManager__get_names_from_api(ids)
        self.assertListEqual(infos, infos_expected)

    @patch('standingsrequests.helpers.esi_fetch._esi_client')
    def test__get_names_from_api_not_found(self, mock_esi_client):
        ids = [1001, 1002, 1003]
        get_names_from_api(ids)
        mock_esi_client.return_value.Universe.post_universe_names.return_value\
            .result.side_effect = HTTPNotFound(Mock(), message='TestException')

        with self.assertRaises(ObjectNotFound):
            EveEntityManager._EveEntityManager__get_names_from_api(ids)
               
    @patch(MODULE_PATH + '.EveEntityManager.get_names_from_api')
    def test_get_name_from_api_exists(self, mock_get_names_from_api):        
        mock_get_names_from_api.side_effect = get_entity_names
        
        name = EveEntityManager.get_name_from_api(1003)
        self.assertEqual(name, 'Clark Kent')

    @patch(MODULE_PATH + '.EveEntityManager.get_names_from_api')
    def test_get_name_from_api_exists_not(self, mock_get_names_from_api):        
        mock_get_names_from_api.side_effect = get_entity_names
        
        name = EveEntityManager.get_name_from_api(1999)
        self.assertIsNone(name)

    def test_get_owner_from_character_id_normal(self):        
        my_user = AuthUtils.create_user('Mike Manager')
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name='Bruce Wayne',
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1'
        )
        CharacterOwnership.objects.create(
            character=my_character,
            owner_hash='abc',
            user=my_user
        )
        self.assertEqual(
            EveEntityManager.get_owner_from_character_id(1001),
            my_user
        )

    def test_get_owner_from_character_id_no_owner(self):        
        EveCharacter.objects.create(
            character_id=1001,
            character_name='Bruce Wayne',
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1'
        )        
        self.assertIsNone(EveEntityManager.get_owner_from_character_id(1001))

    def test_get_owner_from_character_id_no_char(self):                
        self.assertIsNone(EveEntityManager.get_owner_from_character_id(1001))

    def test_get_character_by_user(self):      
        my_user = AuthUtils.create_user('Mike Manager')
        my_character_1 = EveCharacter.objects.create(
            character_id=1001,
            character_name='Bruce Wayne',
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1'
        )
        CharacterOwnership.objects.create(
            character=my_character_1,
            owner_hash='abc1',
            user=my_user
        )
        my_character_2 = EveCharacter.objects.create(
            character_id=1002,
            character_name='Peter Parker',
            corporation_id=2002,
            corporation_name='Dummy Corp 2',
            corporation_ticker='DC2'
        )
        CharacterOwnership.objects.create(
            character=my_character_2,
            owner_hash='abc2',
            user=my_user
        )
        characters = EveEntityManager.get_characters_by_user(my_user)
        self.assertSetEqual(
            set(characters),
            {my_character_1, my_character_2}
        )
        
    def test_is_character_owned_by_user_match(self):        
        my_user = AuthUtils.create_user('Mike Manager')
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name='Bruce Wayne',
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1'
        )
        CharacterOwnership.objects.create(
            character=my_character,
            owner_hash='abc',
            user=my_user
        )
        self.assertTrue(
            EveEntityManager.is_character_owned_by_user(1001, my_user)
        )

    def test_is_character_owned_by_user_no_match(self):        
        my_user = AuthUtils.create_user('Mike Manager')
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name='Bruce Wayne',
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1'
        )
        CharacterOwnership.objects.create(
            character=my_character,
            owner_hash='abc',
            user=my_user
        )
        self.assertFalse(
            EveEntityManager.is_character_owned_by_user(1002, my_user)
        )

    def test_get_state_of_character_match(self):        
        my_user = AuthUtils.create_user('Mike Manager')
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name='Bruce Wayne',
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1'
        )
        CharacterOwnership.objects.create(
            character=my_character,
            owner_hash='abc',
            user=my_user
        )                
        self.assertEqual(
            EveEntityManager.get_state_of_character(my_character),
            'Guest'
        )
        
    def test_get_state_of_character_no_match(self):
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name='Bruce Wayne',
            corporation_id=2001,
            corporation_name='Dummy Corp 1',
            corporation_ticker='DC1'
        )
        self.assertIsNone(
            EveEntityManager.get_state_of_character(my_character)
        )
