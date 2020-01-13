from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from . import _set_logger
from ..models import EveNameCache

logger = _set_logger('standingsrequests.models', __file__)


class TestEveNameCache(TestCase):

    def setUp(self):
        EveNameCache.objects.all().delete()
    

    @patch('standingsrequests.models.EveEntityManager')
    def test_get_name_from_api_when_table_is_empty(self, mock_EveEntityManager):
        mock_EveEntityManager.get_name_from_auth.return_value = None
        mock_EveEntityManager.get_name_from_api.return_value = 'Bruce Wayne'        
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')


    @patch('standingsrequests.models.EveEntityManager')
    def test_get_name_from_auth_when_table_is_empty(self, mock_EveEntityManager):
        mock_EveEntityManager.get_name_from_auth.return_value = 'Bruce Wayne'
        mock_EveEntityManager.get_name_from_api.side_effect = RuntimeError        
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')


    @patch('standingsrequests.models.EveEntityManager')
    def test_get_name_when_exists_in_cache(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_name_from_auth.side_effect = RuntimeError
        mock_EveEntityManager.get_name_from_api.side_effect = RuntimeError

        EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )        
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')


    @patch('standingsrequests.models.EveEntityManager')
    def test_get_name_that_not_exists(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_name_from_auth.return_value = None
        mock_EveEntityManager.get_name_from_api.return_value = None
        
        self.assertEqual(EveNameCache.get_name(1999), None)


    @patch('standingsrequests.models.EveEntityManager')
    def test_get_name_when_cache_outdated(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_name_from_auth.return_value = None
        mock_EveEntityManager.get_name_from_api.return_value = 'Bruce Wayne'

        my_entity = EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )        
        my_entity.updated = timezone.now() - timedelta(days=31)
        my_entity.save()
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')
        self.assertEqual(
            mock_EveEntityManager.get_name_from_api.call_count,
            1
        )        


    @staticmethod
    def EveEntityManager_get_names(eve_entity_ids):
        entities = {
            1001: 'Bruce Wayne',
            1002: 'Peter Parker',
            1003: 'Clark Kent'
        }
        names_info = {}
        for id in eve_entity_ids:
            if id in entities:
                names_info[id] = entities[id]

        return names_info

        
    @patch('standingsrequests.models.EveEntityManager')
    def test_get_names_when_table_is_empty(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = \
            self.EveEntityManager_get_names

        entities = EveNameCache.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne',
                1002: 'Peter Parker',         
            }
        )


    @patch('standingsrequests.models.EveEntityManager')
    def test_get_names_from_cache(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = \
            self.EveEntityManager_get_names

        EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )
        EveNameCache.objects.create(
            entityID=1002,
            name='Peter Parker'
        )
        entities = EveNameCache.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne',
                1002: 'Peter Parker',         
            }
        )


    @patch('standingsrequests.models.EveEntityManager')
    def test_get_names_from_cache_and_api(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = \
            self.EveEntityManager_get_names

        EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )        
        entities = EveNameCache.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne',
                1002: 'Peter Parker',         
            }
        )


    @patch('standingsrequests.models.EveEntityManager')
    def test_get_names_that_dont_exist(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = \
            self.EveEntityManager_get_names
    
        self.assertEqual(len(EveNameCache.get_names([1999])), 0)
        

    def test_cache_timeout(self):
        my_entity = EveNameCache(
            entityID=1001,
            name='Bruce Wayne'            
        )
        # no cache timeout when added recently
        my_entity.updated = timezone.now()
        self.assertFalse(my_entity.cache_timeout())

        # cache timeout for entries older than 30 days
        my_entity.updated = timezone.now() - timedelta(days=31)
        self.assertTrue(my_entity.cache_timeout())


    def test_update_name(self):
        my_entity = EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )
        EveNameCache.update_name(1001, 'Batman')
        my_entity.refresh_from_db()
        self.assertEqual(my_entity.name, 'Batman')


