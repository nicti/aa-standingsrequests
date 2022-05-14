from unittest.mock import patch

from django.urls import reverse

from ..my_test_data import (
    TestViewPagesBase,
    esi_get_corporations_corporation_id,
    esi_post_universe_names,
)

HELPERS_EVECORPORATION_PATH = "standingsrequests.helpers.evecorporation"


@patch(HELPERS_EVECORPORATION_PATH + ".cache")
@patch(HELPERS_EVECORPORATION_PATH + ".esi")
class TestViewActiveRequestsJson(TestViewPagesBase):
    def test_request_character(self, mock_esi, mock_cache):
        # given
        alt_id = self.alt_character_1.character_id
        standing_request = self._create_standing_for_alt(self.alt_character_1)
        self.client.force_login(self.user_manager)

        # when
        response = self.client.get(reverse("standingsrequests:effective_requests_list"))

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
            "action_date": standing_request.action_date,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "actioned": False,
            "is_effective": True,
            "is_corporation": False,
            "is_character": True,
            "action_by": self.user_manager.username,
            "reason": None,
            "labels": [],
        }
        self.assertDictEqual(data_alt_1, expected_alt_1)

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
        alt_id = self.alt_corporation.corporation_id
        standing_request = self._create_standing_for_alt(self.alt_corporation)
        self.client.force_login(self.user_manager)

        # when
        response = self.client.get(reverse("standingsrequests:effective_requests_list"))

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
            "action_date": standing_request.action_date,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "actioned": False,
            "is_effective": True,
            "is_corporation": True,
            "is_character": False,
            "action_by": self.user_manager.username,
            "reason": None,
            "labels": [],
        }
        self.assertDictEqual(data[alt_id], expected_alt_1)
