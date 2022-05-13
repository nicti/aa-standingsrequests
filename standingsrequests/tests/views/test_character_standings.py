from django.test import RequestFactory
from django.urls import reverse

from allianceauth.eveonline.models import EveAllianceInfo, EveCharacter
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import (
    NoSocketsTestCase,
    add_character_to_user,
    json_response_to_dict,
)

from standingsrequests.models import CharacterAffiliation
from standingsrequests.views import character_standings

from ..my_test_data import create_contacts_set, create_eve_objects, load_eve_entities

TEST_SCOPE = "publicData"


class TestViewPilotStandingsJson(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eve_entities()
        create_eve_objects()
        cls.contact_set = create_contacts_set()
        CharacterAffiliation.objects.update_evecharacter_relations()

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

    def test_normal(self):
        # given
        self.maxDiff = None
        request = self.factory.get(reverse("standingsrequests:view_pilots_json"))
        request.user = self.user
        my_view_without_cache = (
            character_standings.view_pilots_standings_json.__wrapped__
        )
        # when
        response = my_view_without_cache(request)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response, "character_id")
        expected = {1001, 1002, 1003, 1004, 1005, 1006, 1008, 1009, 1010, 1110}
        self.assertSetEqual(set(data.keys()), expected)

        data_character_1002 = data[1002]
        expected_character_1002 = {
            "character_id": 1002,
            "character_name": "Peter Parker",
            "character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "corporation_id": 2001,
            "corporation_name": "Wayne Technologies",
            "alliance_id": 3001,
            "alliance_name": "Wayne Enterprises",
            "faction_id": None,
            "faction_name": None,
            "state": "Member",
            "main_character_ticker": "WYE",
            "standing": 10.0,
            "labels": ["blue", "green"],
            "main_character_name": "Peter Parker",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
        }
        self.assertDictEqual(data_character_1002, expected_character_1002)

        data_character_1009 = data[1009]
        expected_character_1009 = {
            "character_id": 1009,
            "character_name": "Lex Luthor",
            "character_icon_url": "https://images.evetech.net/characters/1009/portrait?size=32",
            "corporation_id": 2102,
            "corporation_name": "Lexcorp",
            "alliance_id": None,
            "alliance_name": "",
            "faction_id": None,
            "faction_name": None,
            "state": "",
            "main_character_ticker": None,
            "standing": -10.0,
            "labels": ["red"],
            "main_character_name": None,
            "main_character_icon_url": None,
        }
        self.assertDictEqual(data_character_1009, expected_character_1009)
