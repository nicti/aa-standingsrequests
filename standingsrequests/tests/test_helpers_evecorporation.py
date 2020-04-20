from unittest.mock import patch

from django.test import TestCase

from . import _set_logger
from ..helpers.evecorporation import EveCorporation
from .my_test_data import esi_get_corporations_corporation_id

MODULE_PATH = 'standingsrequests.helpers.evecorporation'
logger = _set_logger(MODULE_PATH, __file__)


class TestEveCorporation(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.corporation = EveCorporation(
            corporation_id=2001,
            corporation_name='Wayne Technologies',
            ticker='WYT',
            member_count=3,
            alliance_id=3001
        )
    
    def test_init(self):
        self.assertEqual(self.corporation.corporation_id, 2001)
        self.assertEqual(
            self.corporation.corporation_name, 'Wayne Technologies'
        )
        self.assertEqual(self.corporation.ticker, 'WYT')
        self.assertEqual(self.corporation.member_count, 3)
        self.assertEqual(self.corporation.alliance_id, 3001)

    def test_str(self):
        expected = 'Wayne Technologies'
        self.assertEqual(str(self.corporation), expected)
    
    # case 1: corp not in cache -> get from ESI
    # case 2: corp in cache -> get from cache
    
    @patch(MODULE_PATH + '.cache')
    @patch(MODULE_PATH + '.EveCorporation.get_corp_esi')
    def test_get_corp_by_id_not_in_cache(self, mock_get_corp_esi, mock_cache):
        expected = self.corporation
        mock_cache.get.return_value = None
        mock_get_corp_esi.return_value = expected

        obj = EveCorporation.get_corp_by_id(2001)
        self.assertEqual(obj, expected)
        self.assertTrue(mock_get_corp_esi.called)
        self.assertTrue(mock_cache.set.called)

    @patch(MODULE_PATH + '.cache')
    @patch(MODULE_PATH + '.EveCorporation.get_corp_esi')
    def test_get_corp_by_id_not_in_cache_and_esi_failed(
        self, mock_get_corp_esi, mock_cache
    ):
        mock_cache.get.return_value = None
        mock_get_corp_esi.return_value = None

        obj = EveCorporation.get_corp_by_id(2001)
        self.assertIsNone(obj)
        self.assertTrue(mock_get_corp_esi.called)

    @patch(MODULE_PATH + '.cache')
    @patch(MODULE_PATH + '.EveCorporation.get_corp_esi')
    def test_get_corp_by_id_in_cache(self, mock_get_corp_esi, mock_cache):
        expected = self.corporation
        mock_cache.get.return_value = expected
        mock_get_corp_esi.return_value = expected

        obj = EveCorporation.get_corp_by_id(2001)
        self.assertEqual(obj, expected)
        self.assertFalse(mock_get_corp_esi.called)

    @patch(MODULE_PATH + '.esi_client_factory')
    def test_get_corp_esi(self, mock_esi_client_factory):
        mock_esi_client_factory.return_value.Corporation\
            .get_corporations_corporation_id.side_effect = \
            esi_get_corporations_corporation_id

        obj = EveCorporation.get_corp_esi(2102)
        self.assertEqual(obj.corporation_id, 2102)
        self.assertEqual(obj.corporation_name, 'Lexcorp')
        self.assertEqual(obj.ticker, 'LEX')
        self.assertEqual(obj.member_count, 2500)
        self.assertIsNone(obj.alliance_id)
