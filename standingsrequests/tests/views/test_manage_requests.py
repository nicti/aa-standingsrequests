from unittest.mock import patch

from django.urls import reverse

from allianceauth.eveonline.models import EveCharacter

from standingsrequests.models import StandingRequest, StandingRevocation

from ..my_test_data import (
    TestViewPagesBase,
    esi_get_corporations_corporation_id,
    esi_post_universe_names,
)

HELPERS_EVECORPORATION_PATH = "standingsrequests.helpers.evecorporation"


@patch(HELPERS_EVECORPORATION_PATH + ".cache")
@patch(HELPERS_EVECORPORATION_PATH + ".esi")
class TestViewManageRequests(TestViewPagesBase):
    def test_request_character(self, mock_esi, mock_cache):
        # given
        mock_Corporation = mock_esi.client.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi.client.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        mock_cache.get.return_value = None

        alt_id = self.alt_character_1.character_id
        standing_request = StandingRequest.objects.get_or_create_2(
            self.user_requestor,
            alt_id,
            StandingRequest.ContactType.CHARACTER,
        )
        self.client.force_login(self.user_manager)

        # when
        response = self.client.get(reverse("standingsrequests:manage_requests_list"))

        # then
        self.assertEqual(response.status_code, 200)
        data = {obj["contact_id"]: obj for obj in response.context.dicts[3]["requests"]}
        expected = {alt_id}
        self.assertSetEqual(set(data.keys()), expected)
        self.maxDiff = None

        data_alt_1 = data[self.alt_character_1.character_id]
        expected_alt_1 = {
            "contact_id": 1007,
            "contact_name": "James Gordon",
            "contact_icon_url": "https://images.evetech.net/characters/1007/portrait?size=32",
            "corporation_id": 2004,
            "corporation_name": "Metro Police",
            "corporation_ticker": "MP",
            "alliance_id": None,
            "alliance_name": "",
            "has_scopes": True,
            "request_date": standing_request.request_date,
            "action_date": None,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "actioned": False,
            "is_effective": False,
            "is_corporation": False,
            "is_character": True,
            "action_by": "(System)",
            "reason": None,
            "labels": [],
        }
        self.assertPartialDictEqual(data_alt_1, expected_alt_1)

    def test_request_corporation(self, mock_esi, mock_cache):
        # given
        mock_Corporation = mock_esi.client.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi.client.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        mock_cache.get.return_value = None
        alt_id = self.alt_character_1.corporation_id
        standing_request = StandingRequest.objects.get_or_create_2(
            self.user_requestor,
            alt_id,
            StandingRequest.ContactType.CORPORATION,
        )
        self.client.force_login(self.user_manager)

        # when
        response = self.client.get(reverse("standingsrequests:manage_requests_list"))

        # then
        self.assertEqual(response.status_code, 200)
        data = {obj["contact_id"]: obj for obj in response.context.dicts[3]["requests"]}
        expected = {alt_id}
        self.assertSetEqual(set(data.keys()), expected)
        self.maxDiff = None

        expected_alt_1 = {
            "contact_id": 2004,
            "contact_name": "Metro Police",
            "contact_icon_url": "https://images.evetech.net/corporations/2004/logo?size=32",
            "corporation_id": 2004,
            "corporation_name": "Metro Police",
            "corporation_ticker": "MP",
            "alliance_id": None,
            "alliance_name": "",
            "has_scopes": True,
            "request_date": standing_request.request_date,
            "action_date": None,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "actioned": False,
            "is_effective": False,
            "is_corporation": True,
            "is_character": False,
            "action_by": "(System)",
            "reason": None,
            "labels": [],
        }
        self.assertPartialDictEqual(data[alt_id], expected_alt_1)


@patch(HELPERS_EVECORPORATION_PATH + ".cache")
@patch(HELPERS_EVECORPORATION_PATH + ".esi")
class TestViewManageRevocations(TestViewPagesBase):
    def test_should_show_character_revocation(self, mock_esi, mock_cache):
        # given
        alt_character = EveCharacter.objects.get(character_id=1110)
        alt_id = alt_character.character_id
        self._create_standing_for_alt(alt_character)
        standing_request = StandingRevocation.objects.add_revocation(
            alt_id,
            StandingRevocation.ContactType.CHARACTER,
            user=self.user_requestor,
            reason=StandingRevocation.Reason.LOST_PERMISSION,
        )
        self.client.force_login(self.user_manager)

        # when
        response = self.client.get(reverse("standingsrequests:manage_revocations_list"))

        # then
        self.assertEqual(response.status_code, 200)
        data = {
            obj["contact_id"]: obj for obj in response.context.dicts[3]["revocations"]
        }
        expected = {alt_id}
        self.assertSetEqual(set(data.keys()), expected)
        self.maxDiff = None

        data_alt_1 = data[alt_id]
        expected_alt_1 = {
            "contact_id": 1110,
            "contact_name": "Phil Coulson",
            "contact_icon_url": "https://images.evetech.net/characters/1110/portrait?size=32",
            "corporation_id": 2110,
            "corporation_name": "Shield",
            "corporation_ticker": "SH",
            "alliance_id": None,
            "alliance_name": "",
            "has_scopes": False,
            "request_date": standing_request.request_date,
            "action_date": None,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "actioned": False,
            "is_effective": False,
            "is_corporation": False,
            "is_character": True,
            "action_by": "(System)",
            "reason": "Character owner has lost permission",
            "labels": ["red", "yellow"],
        }
        self.assertPartialDictEqual(data_alt_1, expected_alt_1)

    def test_revoke_corporation(self, mock_esi, mock_cache):
        # given
        mock_Corporation = mock_esi.client.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi.client.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        mock_cache.get.return_value = None
        alt_id = self.alt_corporation.corporation_id
        self._create_standing_for_alt(self.alt_corporation)
        standing_request = StandingRevocation.objects.add_revocation(
            alt_id,
            StandingRevocation.ContactType.CORPORATION,
            user=self.user_requestor,
        )
        self.client.force_login(self.user_manager)

        # when
        response = self.client.get(reverse("standingsrequests:manage_revocations_list"))

        # then
        self.assertEqual(response.status_code, 200)
        data = {
            obj["contact_id"]: obj for obj in response.context.dicts[3]["revocations"]
        }
        expected = {alt_id}
        self.assertSetEqual(set(data.keys()), expected)
        self.maxDiff = None

        expected_alt_1 = {
            "contact_id": 2004,
            "contact_name": "Metro Police",
            "contact_icon_url": "https://images.evetech.net/corporations/2004/logo?size=32",
            "corporation_id": 2004,
            "corporation_name": "Metro Police",
            "corporation_ticker": "MP",
            "alliance_id": None,
            "alliance_name": "",
            "has_scopes": True,
            "request_date": standing_request.request_date,
            "action_date": None,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "actioned": False,
            "is_effective": False,
            "is_corporation": True,
            "is_character": False,
            "action_by": "(System)",
            "reason": "None recorded",
            "labels": [],
        }
        self.assertPartialDictEqual(data[alt_id], expected_alt_1)

    def test_can_show_user_without_main(self, mock_esi, mock_cache):
        # given
        alt_id = self.alt_character_3.character_id
        self._create_standing_for_alt(self.alt_character_3)
        standing_request = StandingRevocation.objects.add_revocation(
            alt_id,
            StandingRevocation.ContactType.CHARACTER,
            user=self.user_former_member,
        )
        self.client.force_login(self.user_manager)

        # when
        response = self.client.get(reverse("standingsrequests:manage_revocations_list"))

        # then
        self.assertEqual(response.status_code, 200)
        data = {
            obj["contact_id"]: obj for obj in response.context.dicts[3]["revocations"]
        }
        expected = {alt_id}
        self.assertSetEqual(set(data.keys()), expected)
        self.maxDiff = None

        data_alt_1 = data[alt_id]
        expected_alt_1 = {
            "contact_id": 1010,
            "contact_name": "Natasha Romanoff",
            "contact_icon_url": "https://images.evetech.net/characters/1010/portrait?size=32",
            "corporation_id": 2102,
            "corporation_name": "Lexcorp",
            "corporation_ticker": "LEX",
            "alliance_id": None,
            "alliance_name": "",
            "has_scopes": False,
            "request_date": standing_request.request_date,
            "action_date": None,
            "state": "Guest",
            "main_character_name": "-",
            "main_character_ticker": "-",
            "main_character_icon_url": "-",
            "actioned": False,
            "is_effective": False,
            "is_corporation": False,
            "is_character": True,
            "action_by": "(System)",
            "reason": "None recorded",
            "labels": ["red"],
        }
        self.assertPartialDictEqual(data_alt_1, expected_alt_1)

    def test_can_handle_requests_without_user(self, mock_esi, mock_cache):
        # setup
        alt_id = 1006
        my_alt = EveCharacter.objects.get(character_id=alt_id)
        self._create_standing_for_alt(my_alt)
        standing_request = StandingRevocation.objects.add_revocation(
            alt_id, StandingRevocation.ContactType.CHARACTER
        )
        self.client.force_login(self.user_manager)

        # when
        response = self.client.get(reverse("standingsrequests:manage_revocations_list"))

        # then
        self.assertEqual(response.status_code, 200)
        data = {
            obj["contact_id"]: obj for obj in response.context.dicts[3]["revocations"]
        }
        expected = {alt_id}
        self.assertSetEqual(set(data.keys()), expected)
        self.maxDiff = None

        data_alt_1 = data[alt_id]
        expected_alt_1 = {
            "contact_id": alt_id,
            "contact_name": "Steven Roger",
            "contact_icon_url": f"https://images.evetech.net/characters/{alt_id}/portrait?size=32",
            "corporation_id": 2003,
            "corporation_name": "CatCo Worldwide Media",
            "corporation_ticker": "CC",
            "alliance_id": None,
            "alliance_name": "",
            "has_scopes": False,
            "request_date": standing_request.request_date,
            "action_date": None,
            "state": "-",
            "main_character_name": "-",
            "main_character_ticker": "-",
            "main_character_icon_url": "-",
            "actioned": False,
            "is_effective": False,
            "is_corporation": False,
            "is_character": True,
            "action_by": "(System)",
            "reason": "None recorded",
            "labels": ["yellow"],
        }
        self.assertPartialDictEqual(data_alt_1, expected_alt_1)
