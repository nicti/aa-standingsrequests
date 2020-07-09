from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.notifications.models import Notification
from allianceauth.tests.auth_utils import AuthUtils

from . import add_character_to_user
from .my_test_data import (
    TEST_STANDINGS_API_CHARID,
    create_standings_char,
    create_contacts_set,
    create_eve_objects,
    esi_get_corporations_corporation_id,
    esi_post_universe_names,
)
from ..models import (
    ContactSet,
    StandingRequest,
    StandingRevocation,
    CharacterContact,
    CorporationContact,
)
from .. import views
from .. import tasks
from ..utils import set_test_logger

MODULE_PATH_MODELS = "standingsrequests.models"
MODULE_PATH_MANAGERS = "standingsrequests.managers"
MODULE_PATH_TASKS = "standingsrequests.tasks"
logger = set_test_logger(MODULE_PATH_MANAGERS, __file__)

TEST_SCOPE = "publicData"


@patch(MODULE_PATH_MODELS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH_MANAGERS + ".SR_NOTIFICATIONS_ENABLED", True)
@patch(MODULE_PATH_MANAGERS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
class TestMainUseCases(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()

        create_standings_char()
        create_eve_objects()

        # State is alliance, all members can add standings
        cls.member_state = AuthUtils.get_member_state()
        perm = AuthUtils.get_permission_by_name(StandingRequest.REQUEST_PERMISSION_NAME)
        cls.member_state.permissions.add(perm)

        # Requesting user
        cls.main_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_requestor = AuthUtils.create_user(cls.main_1.character_name)
        add_character_to_user(
            cls.user_requestor, cls.main_1, is_main=True, scopes=[TEST_SCOPE],
        )
        cls.alt_1 = EveCharacter.objects.get(character_id=1007)
        add_character_to_user(
            cls.user_requestor, cls.alt_1, scopes=[TEST_SCOPE],
        )
        cls.alt_corporation = EveCorporationInfo.objects.get(
            corporation_id=cls.alt_1.corporation_id
        )
        cls.alt_2 = EveCharacter.objects.get(character_id=1008)

        # Standing manager
        cls.main_2 = EveCharacter.objects.get(character_id=1001)
        cls.user_manager = AuthUtils.create_user(cls.main_2.character_name)
        add_character_to_user(
            cls.user_manager, cls.main_2, is_main=True, scopes=[TEST_SCOPE],
        )
        AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.affect_standings", cls.user_manager
        )
        cls.member_state.member_characters.add(cls.main_2)
        cls.user_manager = User.objects.get(pk=cls.user_manager.pk)

    @patch(MODULE_PATH_TASKS + ".ContactSet.objects.create_new_from_api")
    def _process_standing_requests(self, mock_create_new_from_api):
        mock_create_new_from_api.return_value = self.contact_set
        tasks.standings_update()

    def _set_standing_for_alt_in_game(self, alt: object) -> None:
        if isinstance(alt, EveCharacter):
            contact_id = alt.character_id
            contact_name = alt.character_name
        elif isinstance(alt, EveCorporationInfo):
            contact_id = alt.corporation_id
            contact_name = alt.corporation_name
        else:
            raise NotImplementedError()

        CharacterContact.objects.create(
            contact_set=self.contact_set,
            contact_id=contact_id,
            name=contact_name,
            standing=10,
        )
        self.contact_set.refresh_from_db()

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

    def _remove_standing_for_alt_in_game(self, alt: object) -> None:
        if isinstance(alt, EveCharacter):
            CharacterContact.objects.get(
                contact_set=self.contact_set, contact_id=alt.character_id
            ).delete()
        elif isinstance(alt, EveCorporationInfo):
            CorporationContact.objects.get(
                contact_set=self.contact_set, contact_id=alt.corporation_id
            ).delete()
        else:
            raise NotImplementedError()

        self.contact_set.refresh_from_db()

    def _setup_mocks(self, mock_esi_client):
        mock_Corporation = mock_esi_client.return_value.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )

    def setUp(self) -> None:
        cache.clear()
        ContactSet.objects.all().delete()
        self.contact_set = create_contacts_set()
        StandingRequest.objects.all().delete()
        StandingRevocation.objects.all().delete()
        Notification.objects.all().delete()
        self.member_state.member_characters.add(self.main_1)
        self.user_requestor = User.objects.get(pk=self.user_requestor.pk)

    @patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
    @patch("standingsrequests.helpers.esi_fetch._esi_client")
    def test_user_requests_standing_for_his_alt_character(self, mock_esi_client):
        """
        given user has permission and user's alt has no standing
        when user requests standing and request is actioned by manager
        then alt has standing and user gets change notification
        """
        # setup
        self._setup_mocks(mock_esi_client)
        alt_id = self.alt_1.character_id

        # user opens create requests page
        request = self.factory.get(reverse("standingsrequests:request_entities"))
        request.user = self.user_requestor
        response = views.partial_request_entities(request)
        self.assertEqual(response.status_code, 200)

        # make sure link for requesting standing is shown to user
        request_standing_url = reverse(
            "standingsrequests:request_pilot_standing", args=[alt_id],
        )
        self.assertIn(request_standing_url, response.content.decode("utf8"))

        # user requests standing for alt
        request = self.factory.get(request_standing_url)
        request.user = self.user_requestor
        response = views.request_pilot_standing(request, alt_id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StandingRequest.objects.filter(contact_id=alt_id).exists())
        my_request = StandingRequest.objects.get(contact_id=alt_id)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)

        # set standing in game and mark as actioned
        self._set_standing_for_alt_in_game(self.alt_1)
        request = self.factory.put(
            reverse("standingsrequests:manage_requests_write", args=[alt_id],)
        )
        request.user = self.user_manager
        response = views.manage_requests_write(request, alt_id)
        self.assertEqual(response.status_code, 204)
        my_request.refresh_from_db()
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsNotNone(my_request.action_date)
        self.assertFalse(my_request.is_effective)

        self._process_standing_requests()

        # validate results
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    @patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
    @patch("standingsrequests.helpers.esi_fetch._esi_client")
    def test_user_requests_revocation_for_his_alt_character(self, mock_esi_client):
        """
        given user's alt has standing and user has permission
        when user requests revocation and request is actioned by manager
        then alt's standing is removed and user gets change notification
        """

        # setup
        self._setup_mocks(mock_esi_client)
        alt_id = self.alt_1.character_id
        self._set_standing_for_alt_in_game(self.alt_1)
        my_request = self._create_standing_for_alt(self.alt_1)

        # user opens create requests page
        request = self.factory.get(reverse("standingsrequests:request_entities"))
        request.user = self.user_requestor
        response = views.partial_request_entities(request)
        self.assertEqual(response.status_code, 200)

        # make sure link for revoking standing is shown to user
        revoke_standing_url = reverse(
            "standingsrequests:remove_pilot_standing", args=[alt_id],
        )
        self.assertIn(revoke_standing_url, response.content.decode("utf8"))

        # user requests revocation for alt
        request = self.factory.get(revoke_standing_url)
        request.user = self.user_requestor
        response = views.remove_pilot_standing(request, alt_id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)
        my_revocation = StandingRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)

        # remove standing for alt in game and mark as actioned
        self._remove_standing_for_alt_in_game(self.alt_1)

        request = self.factory.put(
            reverse("standingsrequests:manage_revocations_write", args=[alt_id],)
        )
        request.user = self.user_manager
        response = views.manage_revocations_write(request, alt_id)
        self.assertEqual(response.status_code, 204)
        my_revocation.refresh_from_db()
        self.assertEqual(my_revocation.action_by, self.user_manager)
        self.assertIsNotNone(my_revocation.action_date)
        self.assertFalse(my_revocation.is_effective)

        self._process_standing_requests()

        # validate results
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    @patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
    @patch("standingsrequests.helpers.esi_fetch._esi_client")
    def test_user_requests_standing_for_his_alt_corporation(self, mock_esi_client):
        """
        given user has permission and user's alt has no standing
        and all corporation members have tokens
        when user requests standing and request is actioned by manager
        then alt has standing and user gets change notification
        """

        # setup
        self._setup_mocks(mock_esi_client)
        alt_id = self.alt_corporation.corporation_id
        add_character_to_user(
            self.user_requestor, self.alt_2, scopes=[TEST_SCOPE],
        )

        # user opens create requests page
        request = self.factory.get(reverse("standingsrequests:request_entities"))
        request.user = self.user_requestor
        response = views.partial_request_entities(request)
        self.assertEqual(response.status_code, 200)

        # make sure link for requesting standing is shown to user
        request_standing_url = reverse(
            "standingsrequests:request_corp_standing", args=[alt_id],
        )
        self.assertIn(request_standing_url, response.content.decode("utf8"))

        # user requests standing for alt
        request = self.factory.get(request_standing_url)
        request.user = self.user_requestor
        response = views.request_corp_standing(request, alt_id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StandingRequest.objects.filter(contact_id=alt_id).exists())
        my_request = StandingRequest.objects.get(contact_id=alt_id)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)

        # set standing in game and mark as actioned
        self._set_standing_for_alt_in_game(self.alt_corporation)
        request = self.factory.put(
            reverse("standingsrequests:manage_requests_write", args=[alt_id],)
        )
        request.user = self.user_manager
        response = views.manage_requests_write(request, alt_id)
        self.assertEqual(response.status_code, 204)
        my_request.refresh_from_db()
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsNotNone(my_request.action_date)
        self.assertFalse(my_request.is_effective)

        self._process_standing_requests()

        # validate results
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    @patch("standingsrequests.helpers.evecorporation._esi_client", lambda: None)
    @patch("standingsrequests.helpers.esi_fetch._esi_client")
    def test_user_requests_revocation_for_his_alt_corporation(self, mock_esi_client):
        """
        given user's alt has standing and user has permission
        when user requests revocation and request is actioned by manager
        then alt's standing is removed and user gets change notification
        """

        # setup
        self._setup_mocks(mock_esi_client)
        alt_id = self.alt_corporation.corporation_id
        self._set_standing_for_alt_in_game(self.alt_corporation)
        my_request = self._create_standing_for_alt(self.alt_corporation)

        # user opens create requests page
        request = self.factory.get(reverse("standingsrequests:request_entities"))
        request.user = self.user_requestor
        response = views.partial_request_entities(request)
        self.assertEqual(response.status_code, 200)

        # make sure link for revoking standing is shown to user
        revoke_standing_url = reverse(
            "standingsrequests:remove_corp_standing", args=[alt_id],
        )
        self.assertIn(revoke_standing_url, response.content.decode("utf8"))

        # user requests revocation for alt
        request = self.factory.get(revoke_standing_url)
        request.user = self.user_requestor
        response = views.remove_corp_standing(request, alt_id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)
        my_revocation = StandingRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)

        # remove standing for alt in game and mark as actioned
        self._remove_standing_for_alt_in_game(self.alt_corporation)
        request = self.factory.put(
            reverse("standingsrequests:manage_revocations_write", args=[alt_id],)
        )
        request.user = self.user_manager
        response = views.manage_revocations_write(request, alt_id)
        self.assertEqual(response.status_code, 204)
        my_revocation.refresh_from_db()
        self.assertEqual(my_revocation.action_by, self.user_manager)
        self.assertIsNotNone(my_revocation.action_date)
        self.assertFalse(my_revocation.is_effective)

        self._process_standing_requests()

        # validate results
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    def test_automatic_standing_revocation_when_standing_is_reset_in_game(self):
        """
        given user's alt has standing and user has permission
        when alt's standing is reset in-game
        then alt's standing is removed and user gets change notification
        """

        # setup
        alt_id = self.alt_1.character_id
        self._create_standing_for_alt(self.alt_1)

        # run task
        self._process_standing_requests()

        # validate
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    def test_automatically_create_standing_revocation_for_invalid_alts(self):
        """
        given user's alt has standing
        when user has lost permission
        then standing revocation is automatically created
        and standing is removed after actioned by manager
        and user is notified
        """

        # setup
        alt_id = self.alt_1.character_id
        self._set_standing_for_alt_in_game(self.alt_1)
        my_request = self._create_standing_for_alt(self.alt_1)
        self.member_state.member_characters.remove(self.main_1)
        self.user_requestor = User.objects.get(pk=self.user_requestor.pk)
        self.assertFalse(
            self.user_requestor.has_perm(StandingRequest.REQUEST_PERMISSION_NAME)
        )

        # run task
        tasks.validate_requests()

        # validate
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        my_revocation = StandingRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)

    @patch(MODULE_PATH_TASKS + ".SR_SYNC_BLUE_ALTS_ENABLED", True)
    def test_automatically_create_standing_requests_for_valid_alts(self):
        """
        given user's alt has no standing record
        when regular standing update is run
        then standing record is automatically created for this alt
        """

        # setup
        self._set_standing_for_alt_in_game(self.alt_1)

        # run task
        self._process_standing_requests()

        # validate
        my_request = StandingRequest.objects.get(contact_id=self.alt_1.character_id)
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
