import json
from unittest.mock import patch, Mock

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from allianceauth.eveonline.models import EveCharacter, EveAllianceInfo
from allianceauth.tests.auth_utils import AuthUtils
from esi.models import Token

from . import add_character_to_user

from .my_test_data import (
    TEST_STANDINGS_API_CHARID,
    TEST_STANDINGS_API_CHARNAME,
    create_standings_char,
    create_contacts_set,
    create_eve_objects,
)
from ..models import EveEntity, PilotStanding, StandingsRequest, StandingsRevocation
from ..utils import set_test_logger, NoSocketsTestCase
from .. import views

MODULE_PATH = "standingsrequests.views"
MODULE_PATH_MODELS = "standingsrequests.models"
logger = set_test_logger(MODULE_PATH, __file__)

TEST_SCOPE = "publicData"


@patch(MODULE_PATH + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH_MODELS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH + ".update_all")
@patch(MODULE_PATH + ".messages_plus")
class TestViewAuthPage(NoSocketsTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        EveEntity.objects.create(
            entity_id=TEST_STANDINGS_API_CHARID, name=TEST_STANDINGS_API_CHARNAME
        )

    def make_request(self, user, character):
        token = Mock(spec=Token)
        token.character_id = character.character_id
        request = self.factory.get(reverse("standingsrequests:view_auth_page"))
        request.user = user
        request.token = token
        middleware = SessionMiddleware()
        middleware.process_request(request)
        orig_view = views.view_auth_page.__wrapped__.__wrapped__.__wrapped__
        return orig_view(request, token)

    @patch(MODULE_PATH_MODELS + ".SR_OPERATION_MODE", "corporation")
    def test_for_corp_when_provided_standingschar_return_success(
        self, mock_messages, mock_update_all
    ):
        user = AuthUtils.create_user(TEST_STANDINGS_API_CHARNAME)
        character = AuthUtils.add_main_character_2(
            user, TEST_STANDINGS_API_CHARNAME, TEST_STANDINGS_API_CHARID
        )
        response = self.make_request(user, character)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertFalse(mock_messages.error.called)
        self.assertTrue(mock_update_all.delay.called)

    @patch(MODULE_PATH_MODELS + ".SR_OPERATION_MODE", "corporation")
    def test_when_not_provided_standingschar_return_error(
        self, mock_messages, mock_update_all
    ):
        create_standings_char()
        user = AuthUtils.create_user("Clark Kent")
        character = AuthUtils.add_main_character_2(user, user.username, 1002)
        EveEntity.objects.create(
            entity_id=character.character_id, name=character.character_name
        )
        response = self.make_request(user, character)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertFalse(mock_messages.success.called)
        self.assertTrue(mock_messages.error.called)
        self.assertFalse(mock_update_all.delay.called)

    @patch(MODULE_PATH_MODELS + ".SR_OPERATION_MODE", "alliance")
    def test_for_alliance_when_provided_standingschar_return_success(
        self, mock_messages, mock_update_all
    ):
        user = AuthUtils.create_user(TEST_STANDINGS_API_CHARNAME)
        character = AuthUtils.add_main_character_2(
            user,
            TEST_STANDINGS_API_CHARNAME,
            TEST_STANDINGS_API_CHARID,
            alliance_id=3001,
            alliance_name="Dummy Alliance",
        )
        response = self.make_request(user, character)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertFalse(mock_messages.error.called)
        self.assertTrue(mock_update_all.delay.called)

    @patch(MODULE_PATH_MODELS + ".SR_OPERATION_MODE", "alliance")
    def test_for_alliance_when_provided_standingschar_not_in_alliance_return_error(
        self, mock_messages, mock_update_all
    ):
        user = AuthUtils.create_user(TEST_STANDINGS_API_CHARNAME)
        character = AuthUtils.add_main_character_2(
            user, TEST_STANDINGS_API_CHARNAME, TEST_STANDINGS_API_CHARID
        )
        response = self.make_request(user, character)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertFalse(mock_messages.success.called)
        self.assertTrue(mock_messages.error.called)
        self.assertFalse(mock_update_all.delay.called)


@patch(MODULE_PATH + ".cache")
class TestViewPilotStandingsJson(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        cls.contact_set = create_contacts_set()
        create_eve_objects()
        member_state = AuthUtils.get_member_state()
        member_state.member_alliances.add(EveAllianceInfo.objects.get(alliance_id=3001))
        cls.user = AuthUtils.create_member("John Doe")
        AuthUtils.add_permission_to_user_by_name("standingsrequests.view", cls.user)
        EveCharacter.objects.get(character_id=1009).delete()
        cls.main_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_1 = AuthUtils.create_member(cls.main_1.character_name)
        add_character_to_user(
            cls.user_1, cls.main_1, is_main=True, scopes=[TEST_SCOPE],
        )
        cls.alt_1 = EveCharacter.objects.get(character_id=1004)
        add_character_to_user(
            cls.user_1, cls.alt_1, scopes=[TEST_SCOPE],
        )

    def setUp(self):
        pass

    def test_normal(self, mock_cache):
        def my_cache_get_or_set(key, func, timeout):
            return func()

        mock_cache.get_or_set.side_effect = my_cache_get_or_set
        request = self.factory.get(reverse("standingsrequests:view_auth_page"))
        request.user = self.user
        response = views.view_pilots_standings_json(request)
        self.assertEqual(response.status_code, 200)
        data = {
            x["character_id"]: x
            for x in json.loads(response.content.decode(response.charset))
        }
        expected = {1001, 1002, 1003, 1004, 1005, 1006, 1008, 1009, 1010}
        self.assertSetEqual(set(data.keys()), expected)

        self.maxDiff = None
        data_main_1 = data[self.main_1.character_id]
        expected_main_1 = {
            "character_id": 1002,
            "character_name": "Peter Parker",
            "corporation_id": 2001,
            "corporation_name": "Wayne Technologies",
            "corporation_ticker": "WYE",
            "alliance_id": 3001,
            "alliance_name": "Wayne Enterprises",
            "has_required_scopes": True,
            "state": "Member",
            "main_character_ticker": "WYE",
            "standing": 10.0,
            "labels": ["blue", "green"],
            "main_character_name": "Peter Parker",
        }
        self.assertDictEqual(data_main_1, expected_main_1)

        data_alt_1 = data[self.alt_1.character_id]
        expected_alt_1 = {
            "character_id": 1004,
            "character_name": "Kara Danvers",
            "corporation_id": 2003,
            "corporation_name": "CatCo Worldwide Media",
            "corporation_ticker": "CC",
            "alliance_id": None,
            "alliance_name": None,
            "has_required_scopes": True,
            "state": "Member",
            "main_character_ticker": "WYE",
            "standing": 0.01,
            "labels": ["yellow"],
            "main_character_name": "Peter Parker",
        }
        self.assertDictEqual(data_alt_1, expected_alt_1)

        data_character_1009 = data[1009]
        expected_character_1009 = {
            "character_id": 1009,
            "character_name": "Lex Luthor",
            "corporation_id": 2102,
            "corporation_name": "Lexcorp",
            "corporation_ticker": None,
            "alliance_id": None,
            "alliance_name": None,
            "has_required_scopes": False,
            "state": "",
            "main_character_ticker": None,
            "standing": -10.0,
            "labels": ["red"],
            "main_character_name": None,
        }
        self.assertDictEqual(data_character_1009, expected_character_1009)

        # print(data)


@patch(MODULE_PATH + ".messages_plus")
class TestRequestStanding(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        cls.contact_set = create_contacts_set()
        create_eve_objects()

        # State is alliance, all members can add standings
        member_state = AuthUtils.get_member_state()
        member_state.member_alliances.add(EveAllianceInfo.objects.get(alliance_id=3001))
        perm = AuthUtils.get_permission_by_name("standingsrequests.request_standings")
        member_state.permissions.add(perm)

        # Requesting user
        cls.main_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_requestor = AuthUtils.create_member(cls.main_1.character_name)
        add_character_to_user(
            cls.user_requestor, cls.main_1, is_main=True, scopes=[TEST_SCOPE],
        )
        cls.alt_1 = EveCharacter.objects.get(character_id=1004)
        add_character_to_user(
            cls.user_requestor, cls.alt_1, scopes=[TEST_SCOPE],
        )

        # Standing manager
        cls.main_2 = EveCharacter.objects.get(character_id=1001)
        cls.user_manager = AuthUtils.create_member(cls.main_2.character_name)
        add_character_to_user(
            cls.user_requestor, cls.main_2, is_main=True, scopes=[TEST_SCOPE],
        )
        AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.affect_standings", cls.user_manager
        )

    def setUp(self):
        StandingsRequest.objects.all().delete()
        StandingsRevocation.objects.all().delete()

    def make_request(self, character_id):
        request = self.factory.get(
            reverse("standingsrequests:request_pilot_standing", args=[character_id],)
        )
        request.user = self.user_requestor
        response = views.request_pilot_standing(request, character_id)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        return response

    def test_when_no_pending_request_or_revocation_for_character_create_new_request(
        self, mock_messages
    ):
        character_id = self.alt_1.character_id
        self.make_request(character_id)
        self.assertEqual(
            StandingsRequest.objects.filter(contact_id=character_id).count(), 1
        )

    def test_when_pending_request_for_character_dont_create_new_request(
        self, mock_messages
    ):
        character_id = self.alt_1.character_id

        StandingsRequest.objects.add_request(
            self.user_requestor,
            character_id,
            PilotStanding.get_contact_type_id(character_id),
        )
        self.make_request(character_id)
        self.assertEqual(
            StandingsRequest.objects.filter(contact_id=character_id).count(), 1
        )

    def test_when_pending_revocation_for_character_dont_create_new_request(
        self, mock_messages
    ):
        character_id = self.alt_1.character_id

        StandingsRevocation.objects.add_revocation(
            character_id, PilotStanding.get_contact_type_id(character_id),
        )
        self.make_request(character_id)
        self.assertEqual(
            StandingsRequest.objects.filter(contact_id=character_id).count(), 0
        )


@patch(MODULE_PATH + ".messages_plus")
class TestRemovePilotStanding(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        cls.contact_set = create_contacts_set()
        create_eve_objects()

        # State is alliance, all members can add standings
        member_state = AuthUtils.get_member_state()
        member_state.member_alliances.add(EveAllianceInfo.objects.get(alliance_id=3001))
        perm = AuthUtils.get_permission_by_name("standingsrequests.request_standings")
        member_state.permissions.add(perm)

        # Requesting user
        cls.main_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_requestor = AuthUtils.create_member(cls.main_1.character_name)
        add_character_to_user(
            cls.user_requestor, cls.main_1, is_main=True, scopes=[TEST_SCOPE],
        )
        cls.alt_1 = EveCharacter.objects.get(character_id=1004)
        add_character_to_user(
            cls.user_requestor, cls.alt_1, scopes=[TEST_SCOPE],
        )

        # Standing manager
        cls.main_2 = EveCharacter.objects.get(character_id=1001)
        cls.user_manager = AuthUtils.create_member(cls.main_2.character_name)
        add_character_to_user(
            cls.user_requestor, cls.main_2, is_main=True, scopes=[TEST_SCOPE],
        )
        AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.affect_standings", cls.user_manager
        )

    def setUp(self):
        StandingsRequest.objects.all().delete()
        StandingsRevocation.objects.all().delete()

    def make_request(self, character_id):
        request = self.factory.get(
            reverse("standingsrequests:remove_pilot_standing", args=[character_id],)
        )
        request.user = self.user_requestor
        response = views.remove_pilot_standing(request, character_id)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        return response

    def test_when_effective_standing_request_exists_create_revocation(
        self, mock_messages
    ):
        character_id = self.alt_1.character_id
        sr = StandingsRequest.objects.add_request(
            self.user_requestor,
            character_id,
            PilotStanding.get_contact_type_id(character_id),
        )
        sr.mark_standing_actioned(self.user_manager)
        sr.mark_standing_effective()

        self.make_request(character_id)
        self.assertEqual(
            StandingsRequest.objects.filter(contact_id=character_id).count(), 1
        )
        self.assertEqual(
            StandingsRevocation.objects.filter(contact_id=character_id).count(), 1
        )

    def test_when_none_effective_standing_request_exists_remove_standing_request(
        self, mock_messages
    ):
        character_id = self.alt_1.character_id

        # default standing request
        StandingsRequest.objects.add_request(
            self.user_requestor,
            character_id,
            PilotStanding.get_contact_type_id(character_id),
        )
        self.make_request(character_id)
        self.assertEqual(
            StandingsRequest.objects.filter(contact_id=character_id).count(), 0
        )
        # actioned standing request
        sr = StandingsRequest.objects.add_request(
            self.user_requestor,
            character_id,
            PilotStanding.get_contact_type_id(character_id),
        )
        sr.mark_standing_actioned(self.user_manager)
        self.make_request(character_id)
        self.assertEqual(
            StandingsRequest.objects.filter(contact_id=character_id).count(), 0
        )

    def test_when_effective_standing_request_exists_and_standing_revocation_exists(
        self, mock_messages
    ):
        character_id = self.alt_1.character_id

        sr = StandingsRequest.objects.add_request(
            self.user_requestor,
            character_id,
            PilotStanding.get_contact_type_id(character_id),
        )
        sr.mark_standing_actioned(self.user_manager)
        sr.mark_standing_effective()
        StandingsRevocation.objects.add_revocation(
            character_id, PilotStanding.get_contact_type_id(character_id),
        )

        self.make_request(character_id)
        self.assertEqual(
            StandingsRequest.objects.filter(contact_id=character_id).count(), 1
        )
        self.assertEqual(
            StandingsRevocation.objects.filter(contact_id=character_id).count(), 1
        )
