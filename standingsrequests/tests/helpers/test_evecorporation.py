from unittest.mock import patch

from django.test import TestCase
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import (
    NoSocketsTestCase,
    add_character_to_user,
    create_user_from_evecharacter,
)

from standingsrequests.helpers.evecorporation import EveCorporation
from standingsrequests.tests.testdata.my_test_data import (
    create_eve_objects,
    esi_get_corporations_corporation_id,
    get_my_test_data,
)

EVECORPORATION_PATH = "standingsrequests.helpers.evecorporation"
MODELS_PATH = "standingsrequests.models"


@patch(EVECORPORATION_PATH + ".cache")
@patch(EVECORPORATION_PATH + ".esi")
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


class TestMemberTokensCountForUser(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        create_eve_objects()

    def test_should_count_valid_characters_only(self):
        # given
        user, _ = create_user_from_evecharacter(1001, scopes=["special-scope"])
        add_character_to_user(
            user, EveCharacter.objects.get(character_id=1002), scopes=["special-scope"]
        )  # same corp and valid scope
        add_character_to_user(
            user, EveCharacter.objects.get(character_id=1003)
        )  # same corp, but invalid scope
        add_character_to_user(
            user, EveCharacter.objects.get(character_id=1006)
        )  # different corp
        obj = EveCorporation(corporation_id=2001)

        # when
        with patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"Guest": {"special-scope"}}):
            result = obj.member_tokens_count_for_user(user)

        # then
        self.assertEqual(result, 2)


class TestGetManyById(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        create_eve_objects()
        cls.corporations: dict = get_my_test_data()["EveCorporationInfo"]

    def test_should_return_corporations(self):
        def my_get_by_id(corporation_id, *args, **kwargs):
            try:
                obj = self.corporations[str(corporation_id)]
            except KeyError:
                return None

            return EveCorporation(**obj)

        # when
        with patch(
            EVECORPORATION_PATH + ".EveCorporation.get_by_id", new=my_get_by_id
        ), patch(EVECORPORATION_PATH + ".esi") as _:
            result = EveCorporation.get_many_by_id([2001, 2002, 2987])

        # then
        corporations = {obj.corporation_id: obj for obj in result}
        self.assertSetEqual(set(corporations.keys()), {2001, 2002})
