from unittest.mock import patch

from django.urls import reverse

from standingsrequests.views.effective_requests import effective_requests_data

from ..my_test_data import (
    TestViewPagesBase,
    esi_get_corporations_corporation_id,
    esi_post_universe_names,
)
from ..utils import json_response_to_dict_2

HELPERS_EVECORPORATION_PATH = "standingsrequests.helpers.evecorporation"


@patch(HELPERS_EVECORPORATION_PATH + ".cache")
@patch(HELPERS_EVECORPORATION_PATH + ".esi")
class TestEffectiveRequestsData(TestViewPagesBase):
    def test_request_character(self, mock_esi, mock_cache):
        # given
        alt_id = self.alt_character_1.character_id
        self._create_standing_for_alt(self.alt_character_1)
        request = self.factory.get(reverse("standingsrequests:effective_requests_data"))
        request.user = self.user_manager
        my_view_without_cache = effective_requests_data.__wrapped__

        # when
        response = my_view_without_cache(request)

        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict_2(response, "contact_id")
        expected = {alt_id}
        self.assertSetEqual(set(data.keys()), expected)
        self.maxDiff = None

        data_alt_1 = data[self.alt_character_1.character_id]
        expected_alt_1 = {
            "contact_id": 1007,
            "contact_name": "James Gordon",
            "corporation_name": "Metro Police",
            "corporation_ticker": "MP",
            "alliance_name": "",
            "has_scopes": True,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "action_by": self.user_manager.username,
            "labels_str": "",
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
        alt_id = self.alt_corporation.corporation_id
        self._create_standing_for_alt(self.alt_corporation)
        request = self.factory.get(reverse("standingsrequests:effective_requests_data"))
        request.user = self.user_manager
        my_view_without_cache = effective_requests_data.__wrapped__

        # when
        response = my_view_without_cache(request)

        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict_2(response, "contact_id")
        expected = {alt_id}
        self.assertSetEqual(set(data.keys()), expected)
        self.maxDiff = None

        expected_alt_1 = {
            "contact_id": 2004,
            "contact_name": "Metro Police",
            "corporation_name": "Metro Police",
            "corporation_ticker": "MP",
            "alliance_name": "",
            "has_scopes": True,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "action_by": self.user_manager.username,
            "labels_str": "",
        }
        self.assertPartialDictEqual(data[alt_id], expected_alt_1)
