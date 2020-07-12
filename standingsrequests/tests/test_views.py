from datetime import timedelta
import json
from unittest.mock import patch, Mock

from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.eveonline.models import (
    EveCharacter,
    EveAllianceInfo,
    EveCorporationInfo,
)
from allianceauth.tests.auth_utils import AuthUtils
from esi.models import Token

from . import add_character_to_user

from .my_test_data import (
    TEST_STANDINGS_API_CHARID,
    TEST_STANDINGS_API_CHARNAME,
    create_standings_char,
    create_contacts_set,
    create_eve_objects,
    esi_get_corporations_corporation_id,
    esi_post_universe_names,
)
from ..models import (
    CharacterContact,
    CorporationContact,
    EveEntity,
    StandingRequest,
    StandingRevocation,
)
from ..utils import set_test_logger, NoSocketsTestCase
from .. import views

MODULE_PATH = "standingsrequests.views"
MODULE_PATH_MODELS = "standingsrequests.models"
MODULE_PATH_MANAGERS = "standingsrequests.managers"
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
            entity_id=character.character_id,
            name=character.character_name,
            category=EveEntity.CATEGORY_CHARACTER,
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


@patch(MODULE_PATH + ".cache_view_pilots_json.get_or_set")
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
        cls.main_character_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_1 = AuthUtils.create_member(cls.main_character_1.character_name)
        add_character_to_user(
            cls.user_1, cls.main_character_1, is_main=True, scopes=[TEST_SCOPE],
        )
        cls.alt_character_1 = EveCharacter.objects.get(character_id=1007)
        add_character_to_user(
            cls.user_1, cls.alt_character_1, scopes=[TEST_SCOPE],
        )

    def setUp(self):
        pass

    def test_normal(self, mock_cache_get_or_set_character_standings_data):
        def my_cache_get_or_set(func):
            return func()

        mock_cache_get_or_set_character_standings_data.side_effect = my_cache_get_or_set
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
        data_character_1002 = data[1002]
        expected_character_1002 = {
            "character_id": 1002,
            "character_name": "Peter Parker",
            "character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
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
            "corporation_ticker": None,
            "alliance_id": None,
            "alliance_name": None,
            "has_required_scopes": None,
            "state": "",
            "main_character_ticker": None,
            "standing": -10.0,
            "labels": ["red"],
            "main_character_name": None,
            "main_character_icon_url": None,
        }
        self.assertDictEqual(data_character_1009, expected_character_1009)

        # print(data)


class TestViewPagesBase(TestCase):
    """Base TestClass for all tests that deal with standing requests
    
    Defines common test data
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()

        create_standings_char()
        create_eve_objects()

        cls.contact_set = create_contacts_set()

        # State is alliance, all members can add standings
        member_state = AuthUtils.get_member_state()
        member_state.member_alliances.add(EveAllianceInfo.objects.get(alliance_id=3001))
        perm = AuthUtils.get_permission_by_name(StandingRequest.REQUEST_PERMISSION_NAME)
        member_state.permissions.add(perm)

        # Requesting user - can only make requests
        cls.main_character_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_requestor = AuthUtils.create_member(
            cls.main_character_1.character_name
        )
        add_character_to_user(
            cls.user_requestor, cls.main_character_1, is_main=True, scopes=[TEST_SCOPE],
        )
        cls.alt_character_1 = EveCharacter.objects.get(character_id=1007)
        add_character_to_user(
            cls.user_requestor, cls.alt_character_1, scopes=[TEST_SCOPE],
        )
        cls.alt_corporation = EveCorporationInfo.objects.get(
            corporation_id=cls.alt_character_1.corporation_id
        )
        cls.alt_character_2 = EveCharacter.objects.get(character_id=1008)
        add_character_to_user(
            cls.user_requestor, cls.alt_character_2, scopes=[TEST_SCOPE],
        )

        # Standing manager - can do everything
        cls.main_character_2 = EveCharacter.objects.get(character_id=1001)
        cls.user_manager = AuthUtils.create_member(cls.main_character_2.character_name)
        add_character_to_user(
            cls.user_manager, cls.main_character_2, is_main=True, scopes=[TEST_SCOPE],
        )
        AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.affect_standings", cls.user_manager
        )
        AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.view", cls.user_manager
        )
        cls.user_manager = User.objects.get(pk=cls.user_manager.pk)

    def setUp(self):
        StandingRequest.objects.all().delete()
        StandingRevocation.objects.all().delete()

    def _create_standing_for_alt(self, alt: object) -> StandingRequest:
        if isinstance(alt, EveCharacter):
            contact_id = alt.character_id
            contact_type_id = CharacterContact.get_contact_type_id()
        elif isinstance(alt, EveCorporationInfo):
            contact_id = alt.corporation_id
            contact_type_id = CorporationContact.get_contact_type_id()
        else:
            raise NotImplementedError()

        return StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=contact_id,
            contact_type_id=contact_type_id,
            action_by=self.user_manager,
            action_date=now() - timedelta(days=1, hours=1),
            is_effective=True,
            effective_date=now() - timedelta(days=1),
        )

    def _set_standing_for_alt_in_game(self, alt: object) -> None:
        if isinstance(alt, EveCharacter):
            contact_id = alt.character_id
            contact_name = alt.character_name
            CharacterContact.objects.update_or_create(
                contact_set=self.contact_set,
                contact_id=contact_id,
                defaults={"name": contact_name, "standing": 10,},
            )
        elif isinstance(alt, EveCorporationInfo):
            contact_id = alt.corporation_id
            contact_name = alt.corporation_name
            CorporationContact.objects.update_or_create(
                contact_set=self.contact_set,
                contact_id=contact_id,
                defaults={"name": contact_name, "standing": 10,},
            )
        else:
            raise NotImplementedError()

        self.contact_set.refresh_from_db()


@patch(MODULE_PATH_MODELS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH_MANAGERS + ".SR_NOTIFICATIONS_ENABLED", True)
@patch(MODULE_PATH_MANAGERS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
@patch("standingsrequests.helpers.esi_fetch._esi_client")
class TestViewsBasics(TestViewPagesBase):
    def _setup_mocks(self, mock_esi_client):
        mock_Corporation = mock_esi_client.return_value.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )

    def test_user_can_open_index(self, mock_esi_client):
        request = self.factory.get(reverse("standingsrequests:index"))
        request.user = self.user_requestor
        response = views.index_view(request)
        self.assertEqual(response.status_code, 200)

    def test_user_can_open_pilots_standing(self, mock_esi_client):
        request = self.factory.get(reverse("standingsrequests:view_pilots"))
        request.user = self.user_manager
        response = views.view_pilots_standings(request)
        self.assertEqual(response.status_code, 200)

    def test_user_can_open_groups_standing(self, mock_esi_client):
        request = self.factory.get(reverse("standingsrequests:view_groups"))
        request.user = self.user_manager
        response = views.view_groups_standings(request)
        self.assertEqual(response.status_code, 200)

    def test_user_can_open_manage_requests(self, mock_esi_client):
        request = self.factory.get(reverse("standingsrequests:manage"))
        request.user = self.user_manager
        response = views.manage_standings(request)
        self.assertEqual(response.status_code, 200)

    def test_user_can_open_accepted_requests(self, mock_esi_client):
        request = self.factory.get(reverse("standingsrequests:view_requests"))
        request.user = self.user_manager
        response = views.view_active_requests(request)
        self.assertEqual(response.status_code, 200)


@patch(MODULE_PATH + ".messages_plus")
class TestRequestStanding(TestViewPagesBase):
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
        character_id = self.alt_character_1.character_id
        self.make_request(character_id)
        self.assertEqual(
            StandingRequest.objects.filter(contact_id=character_id).count(), 1
        )

    def test_when_pending_request_for_character_dont_create_new_request(
        self, mock_messages
    ):
        character_id = self.alt_character_1.character_id

        StandingRequest.objects.add_request(
            self.user_requestor, character_id, StandingRequest.CHARACTER_CONTACT_TYPE,
        )
        self.make_request(character_id)
        self.assertEqual(
            StandingRequest.objects.filter(contact_id=character_id).count(), 1
        )

    def test_when_pending_revocation_for_character_dont_create_new_request(
        self, mock_messages
    ):
        character_id = self.alt_character_1.character_id

        StandingRevocation.objects.add_revocation(
            character_id,
            StandingRequest.CHARACTER_CONTACT_TYPE,
            user=self.user_requestor,
        )
        self.make_request(character_id)
        self.assertEqual(
            StandingRequest.objects.filter(contact_id=character_id).count(), 0
        )


@patch(MODULE_PATH + ".messages_plus")
class TestRemovePilotStanding(TestViewPagesBase):
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
        character_id = self.alt_character_1.character_id
        self._set_standing_for_alt_in_game(self.alt_character_1)
        sr = StandingRequest.objects.add_request(
            self.user_requestor, character_id, StandingRequest.CHARACTER_CONTACT_TYPE,
        )
        sr.mark_actioned(self.user_manager)
        sr.mark_effective()

        self.make_request(character_id)
        self.assertEqual(
            StandingRequest.objects.filter(contact_id=character_id).count(), 1
        )
        self.assertEqual(
            StandingRevocation.objects.filter(contact_id=character_id).count(), 1
        )

    def test_when_none_effective_standing_request_exists_remove_standing_request(
        self, mock_messages
    ):
        character_id = self.alt_character_1.character_id

        # default standing request
        StandingRequest.objects.add_request(
            self.user_requestor, character_id, StandingRequest.CHARACTER_CONTACT_TYPE,
        )
        self.make_request(character_id)
        self.assertEqual(
            StandingRequest.objects.filter(contact_id=character_id).count(), 0
        )
        # actioned standing request
        sr = StandingRequest.objects.add_request(
            self.user_requestor, character_id, StandingRequest.CHARACTER_CONTACT_TYPE,
        )
        sr.mark_actioned(self.user_manager)
        self.make_request(character_id)
        self.assertEqual(
            StandingRequest.objects.filter(contact_id=character_id).count(), 0
        )

    def test_when_effective_standing_request_exists_and_standing_revocation_exists(
        self, mock_messages
    ):
        character_id = self.alt_character_1.character_id

        sr = StandingRequest.objects.add_request(
            self.user_requestor, character_id, StandingRequest.CHARACTER_CONTACT_TYPE,
        )
        sr.mark_actioned(self.user_manager)
        sr.mark_effective()
        StandingRevocation.objects.add_revocation(
            character_id,
            StandingRequest.CHARACTER_CONTACT_TYPE,
            user=self.user_requestor,
        )

        self.make_request(character_id)
        self.assertEqual(
            StandingRequest.objects.filter(contact_id=character_id).count(), 1
        )
        self.assertEqual(
            StandingRevocation.objects.filter(contact_id=character_id).count(), 1
        )


@patch("standingsrequests.helpers.evecorporation.cache")
@patch("standingsrequests.helpers.esi_fetch._esi_client")
@patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
class TestViewManageRequestsJson(TestViewPagesBase):
    def test_request_character(self, mock_esi_client, mock_cache):
        # setup
        mock_Corporation = mock_esi_client.return_value.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        mock_cache.get.return_value = None

        alt_id = self.alt_character_1.character_id
        standing_request = StandingRequest.objects.add_request(
            self.user_requestor, alt_id, StandingRequest.CHARACTER_CONTACT_TYPE,
        )

        # make request
        request = self.factory.get(
            reverse("standingsrequests:manage_get_requests_json")
        )
        request.user = self.user_manager
        response = views.manage_get_requests_json(request)

        # validate
        self.assertEqual(response.status_code, 200)
        data = {
            x["contact_id"]: x
            for x in json.loads(response.content.decode(response.charset))
        }
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
            "request_date": standing_request.request_date.isoformat(),
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
        }
        self.assertDictEqual(data_alt_1, expected_alt_1)

    def test_request_corporation(self, mock_esi_client, mock_cache):
        # setup
        mock_Corporation = mock_esi_client.return_value.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        mock_cache.get.return_value = None
        alt_id = self.alt_character_1.corporation_id
        standing_request = StandingRequest.objects.add_request(
            self.user_requestor, alt_id, StandingRequest.CORPORATION_CONTACT_TYPE,
        )

        # make request
        request = self.factory.get(
            reverse("standingsrequests:manage_get_requests_json")
        )
        request.user = self.user_manager
        response = views.manage_get_requests_json(request)

        # validate
        self.assertEqual(response.status_code, 200)
        data = {
            x["contact_id"]: x
            for x in json.loads(response.content.decode(response.charset))
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
            "request_date": standing_request.request_date.isoformat(),
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
        }
        self.assertDictEqual(data[alt_id], expected_alt_1)


@patch("standingsrequests.helpers.evecorporation.cache")
@patch("standingsrequests.helpers.esi_fetch._esi_client")
@patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
class TestViewManageRevocationsJson(TestViewPagesBase):
    def test_revoke_character(self, mock_esi_client, mock_cache):
        # setup
        alt_id = self.alt_character_1.character_id
        self._create_standing_for_alt(self.alt_character_1)
        standing_request = StandingRevocation.objects.add_revocation(
            alt_id, StandingRevocation.CHARACTER_CONTACT_TYPE, user=self.user_requestor
        )

        # make request
        request = self.factory.get(
            reverse("standingsrequests:manage_get_revocations_json")
        )
        request.user = self.user_manager
        response = views.manage_get_revocations_json(request)

        # validate
        self.assertEqual(response.status_code, 200)
        data = {
            x["contact_id"]: x
            for x in json.loads(response.content.decode(response.charset))
        }
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
            "request_date": standing_request.request_date.isoformat(),
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
        }
        self.assertDictEqual(data_alt_1, expected_alt_1)

    def test_revoke_corporation(self, mock_esi_client, mock_cache):
        # setup
        mock_Corporation = mock_esi_client.return_value.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        mock_cache.get.return_value = None

        alt_id = self.alt_corporation.corporation_id
        self._create_standing_for_alt(self.alt_corporation)
        standing_request = StandingRevocation.objects.add_revocation(
            alt_id,
            StandingRevocation.CORPORATION_CONTACT_TYPE,
            user=self.user_requestor,
        )

        # make request
        request = self.factory.get(
            reverse("standingsrequests:manage_get_revocations_json")
        )
        request.user = self.user_manager
        response = views.manage_get_revocations_json(request)

        # validate
        self.assertEqual(response.status_code, 200)
        data = {
            x["contact_id"]: x
            for x in json.loads(response.content.decode(response.charset))
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
            "request_date": standing_request.request_date.isoformat(),
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
        }
        self.assertDictEqual(data[alt_id], expected_alt_1)


@patch("standingsrequests.helpers.evecorporation.cache")
@patch("standingsrequests.helpers.esi_fetch._esi_client")
@patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
class TestViewActiveRequestsJson(TestViewPagesBase):
    def test_request_character(self, mock_esi_client, mock_cache):
        # setup
        alt_id = self.alt_character_1.character_id
        standing_request = self._create_standing_for_alt(self.alt_character_1)

        # make request
        request = self.factory.get(reverse("standingsrequests:view_requests_json"))
        request.user = self.user_manager
        response = views.view_requests_json(request)

        # validate
        self.assertEqual(response.status_code, 200)
        data = {
            x["contact_id"]: x
            for x in json.loads(response.content.decode(response.charset))
        }
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
            "request_date": standing_request.request_date.isoformat(),
            "action_date": standing_request.action_date.isoformat(),
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "actioned": False,
            "is_effective": True,
            "is_corporation": False,
            "is_character": True,
            "action_by": self.user_manager.username,
        }
        self.assertDictEqual(data_alt_1, expected_alt_1)

    def test_request_corporation(self, mock_esi_client, mock_cache):
        # setup
        mock_Corporation = mock_esi_client.return_value.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        mock_cache.get.return_value = None
        alt_id = self.alt_corporation.corporation_id
        standing_request = self._create_standing_for_alt(self.alt_corporation)

        # make request
        request = self.factory.get(reverse("standingsrequests:view_requests_json"))
        request.user = self.user_manager
        response = views.view_requests_json(request)

        # validate
        self.assertEqual(response.status_code, 200)
        data = {
            x["contact_id"]: x
            for x in json.loads(response.content.decode(response.charset))
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
            "request_date": standing_request.request_date.isoformat(),
            "action_date": standing_request.action_date.isoformat(),
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
            "actioned": False,
            "is_effective": True,
            "is_corporation": True,
            "is_character": False,
            "action_by": self.user_manager.username,
        }
        self.assertDictEqual(data[alt_id], expected_alt_1)


@patch(MODULE_PATH + ".cache_view_groups_json.get_or_set")
@patch("standingsrequests.helpers.esi_fetch._esi_client")
@patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
class TestGroupsStandings(TestViewPagesBase):
    def test_view(
        self, mock_esi_client, mock_cache_get_or_set_character_standings_data
    ):
        def my_cache_get_or_set(func):
            return func()

        # setup
        mock_Corporation = mock_esi_client.return_value.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        mock_cache_get_or_set_character_standings_data.side_effect = my_cache_get_or_set
        self._create_standing_for_alt(self.alt_corporation)
        self._set_standing_for_alt_in_game(self.alt_corporation)

        # make request
        request = self.factory.get(reverse("standingsrequests:view_groups_json"))
        request.user = self.user_manager
        response = views.view_groups_standings_json(request)

        # validate
        self.maxDiff = None
        self.assertEqual(response.status_code, 200)
        data_json = json.loads(response.content.decode(response.charset))
        corporations = {row["corporation_id"]: row for row in data_json["corps"]}
        expected = {2003, 2004, 2102}
        self.assertSetEqual(set(corporations.keys()), expected)

        corporation_2003_expected = {
            "corporation_id": 2003,
            "corporation_name": "CatCo Worldwide Media",
            "corporation_icon_url": "https://images.evetech.net/corporations/2003/logo?size=32",
            "alliance_id": None,
            "alliance_name": None,
            "standing": 5.0,
            "labels": [],
            "has_required_scopes": None,
            "state": "",
            "main_character_name": "",
            "main_character_ticker": "",
            "main_character_icon_url": "",
        }
        self.assertDictEqual(corporations[2003], corporation_2003_expected)

        corporation_2004_expected = {
            "corporation_id": 2004,
            "corporation_name": "Metro Police",
            "corporation_icon_url": "https://images.evetech.net/corporations/2004/logo?size=32",
            "alliance_id": None,
            "alliance_name": None,
            "standing": 10.0,
            "labels": [],
            "has_required_scopes": True,
            "state": "Member",
            "main_character_name": "Peter Parker",
            "main_character_ticker": "WYE",
            "main_character_icon_url": "https://images.evetech.net/characters/1002/portrait?size=32",
        }
        self.assertDictEqual(corporations[2004], corporation_2004_expected)

        alliances = {row["alliance_id"]: row for row in data_json["alliances"]}
        expected = {3010}
        self.assertSetEqual(set(alliances.keys()), expected)