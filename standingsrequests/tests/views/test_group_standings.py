from django.test import RequestFactory
from django.urls import reverse

from allianceauth.eveonline.models import EveAllianceInfo, EveCharacter
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import add_character_to_user, json_response_to_python

from standingsrequests.views import group_standings

from ..my_test_data import (
    create_contacts_set,
    create_eve_objects,
    load_corporation_details,
    load_eve_entities,
)
from ..utils import NoSocketsTestCasePlus

TEST_SCOPE = "publicData"


class TestGroupStandingsJson(NoSocketsTestCasePlus):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        cls.contact_set = create_contacts_set()
        load_eve_entities()
        create_eve_objects()
        load_corporation_details()
        member_state = AuthUtils.get_member_state()
        member_state.member_alliances.add(EveAllianceInfo.objects.get(alliance_id=3001))
        cls.user = AuthUtils.create_member("John Doe")
        AuthUtils.add_permission_to_user_by_name("standingsrequests.view", cls.user)
        EveCharacter.objects.get(character_id=1009).delete()
        cls.main_character_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_1 = AuthUtils.create_member(cls.main_character_1.character_name)
        add_character_to_user(
            cls.user_1,
            cls.main_character_1,
            is_main=True,
            scopes=[TEST_SCOPE],
        )
        cls.alt_character_1 = EveCharacter.objects.get(character_id=1007)
        add_character_to_user(
            cls.user_1,
            cls.alt_character_1,
            scopes=[TEST_SCOPE],
        )

    def test_corporations_data(self):
        # given
        self.maxDiff = None
        request = self.factory.get(
            reverse("standingsrequests:view_corporation_standings_json")
        )
        request.user = self.user
        my_view_without_cache = (
            group_standings.view_corporation_standings_json.__wrapped__
        )
        # when
        response = my_view_without_cache(request)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_python(response)
        corporations = {obj["corporation_id"]: obj for obj in data}
        self.assertSetEqual(set(corporations.keys()), {2001, 2003, 2102})
        obj = corporations[2001]
        expected = {
            "corporation_id": 2001,
            "alliance_id": 3001,
            "alliance_name": "Wayne Enterprises",
            "faction_id": None,
            "faction_name": "",
            "standing": 10.0,
            "state": "",
            "main_character_name": "",
        }
        self.assertPartialDictEqual(obj, expected)
        obj = corporations[2003]
        self.assertPartialDictEqual(
            obj,
            {
                "corporation_id": 2003,
                "alliance_id": None,
                "alliance_name": "",
                "faction_id": None,
                "faction_name": "",
                "standing": 5.0,
                "state": "",
                "main_character_name": "",
            },
        )

    def test_alliances_data(self):
        # given
        self.maxDiff = None
        request = self.factory.get(
            reverse("standingsrequests:view_alliance_standings_json")
        )
        request.user = self.user
        my_view_without_cache = group_standings.view_alliance_standings_json.__wrapped__
        # when
        response = my_view_without_cache(request)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_python(response)

        alliances = {obj["alliance_id"]: obj for obj in data}
        self.assertSetEqual(set(alliances.keys()), {3010})
        obj = alliances[3010]
        self.assertPartialDictEqual(obj, {"alliance_id": 3010, "standing": -10.0})
