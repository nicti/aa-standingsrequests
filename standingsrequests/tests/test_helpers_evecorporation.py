from unittest.mock import patch

from eveuniverse.models import EveEntity

from app_utils.testing import NoSocketsTestCase

from ..helpers.evecorporation import EveCorporation
from .my_test_data import esi_get_corporations_corporation_id

MODULE_PATH = "standingsrequests.helpers.evecorporation"


@patch(MODULE_PATH + ".cache")
@patch(MODULE_PATH + ".esi")
class TestEveCorporation(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.corporation = EveCorporation(
            corporation_id=2001,
            corporation_name="Wayne Technologies",
            ticker="WYT",
            ceo_id=1003,
            member_count=3,
            alliance_id=3001,
            alliance_name="Wayne Enterprises",
        )
        EveEntity.objects.all().delete()
        EveEntity.objects.create(id=3001, name="Wayne Enterprises", category="alliance")
        cls.maxDiff = None

    def test_init(self, mock_esi, mock_cache):
        self.assertEqual(self.corporation.corporation_id, 2001)
        self.assertEqual(self.corporation.corporation_name, "Wayne Technologies")
        self.assertEqual(self.corporation.ticker, "WYT")
        self.assertEqual(self.corporation.member_count, 3)
        self.assertEqual(self.corporation.alliance_id, 3001)
        self.assertEqual(self.corporation.alliance_name, "Wayne Enterprises")

    def test_str(self, mock_esi, mock_cache):
        expected = "Wayne Technologies"
        self.assertEqual(str(self.corporation), expected)

    def test_get_corp_by_id_not_in_cache(self, mock_esi, mock_cache):
        mock_Corporation = mock_esi.client.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        expected = self.corporation
        mock_cache.get.return_value = None

        obj = EveCorporation.get_by_id(2001)
        self.assertEqual(obj, expected)
        self.assertTrue(mock_cache.set.called)

    def test_get_corp_by_id_not_in_cache_and_esi_failed(self, mock_esi, mock_cache):
        mock_Corporation = mock_esi.client.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_cache.get.return_value = None

        obj = EveCorporation.get_by_id(9876)
        self.assertIsNone(obj)

    def test_get_corp_by_id_in_cache(self, mock_esi, mock_cache):
        expected = self.corporation
        mock_cache.get.return_value = expected

        obj = EveCorporation.get_by_id(2001)
        self.assertEqual(obj, expected)

    def test_get_corp_esi(self, mock_esi, mock_cache):
        mock_esi.client.Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        obj = EveCorporation.fetch_corporation_from_api(2102)
        self.assertEqual(obj.corporation_id, 2102)
        self.assertEqual(obj.corporation_name, "Lexcorp")
        self.assertEqual(obj.ticker, "LEX")
        self.assertEqual(obj.member_count, 2)
        self.assertIsNone(obj.alliance_id)

    def test_normal_corp_is_not_npc(self, mock_esi, mock_cache):
        normal_corp = EveCorporation(
            corporation_id=98397665,
            corporation_name="Rancid Rabid Rabis",
            ticker="RANCI",
            member_count=3,
            alliance_id=99005502,
            alliance_name="Same Great Taste",
        )
        self.assertFalse(normal_corp.is_npc)

    def test_npc_corp_is_npc(self, mock_esi, mock_cache):
        normal_corp = EveCorporation(
            corporation_id=1000134,
            corporation_name="Blood Raiders",
            ticker="TBR",
            member_count=22,
        )
        self.assertTrue(normal_corp.is_npc)

    def test_corp_without_members(self, mock_esi, mock_cache):
        normal_corp = EveCorporation(
            corporation_id=98397665,
            corporation_name="Rancid Rabid Rabis",
            ticker="RANCI",
        )
        self.assertIsNone(normal_corp.alliance_name)
