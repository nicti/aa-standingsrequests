from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications.models import Notification
from allianceauth.tests.auth_utils import AuthUtils

from . import add_character_to_user
from .entity_type_ids import CHARACTER_TYPE_ID
from .my_test_data import (
    TEST_STANDINGS_API_CHARID,
    create_standings_char,
    create_contacts_set,
    create_eve_objects,
)
from ..models import (
    ContactSet,
    StandingsRequest,
    StandingsRevocation,
    PilotStanding,
)
from .. import views
from .. import tasks
from ..utils import set_test_logger, NoSocketsTestCase

MODULE_PATH_MODELS = "standingsrequests.models"
MODULE_PATH_MANAGERS = "standingsrequests.managers"
MODULE_PATH_TASKS = "standingsrequests.tasks"
logger = set_test_logger(MODULE_PATH_MANAGERS, __file__)

TEST_SCOPE = "publicData"


@patch(MODULE_PATH_MODELS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH_MANAGERS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH_MANAGERS + ".SR_NOTIFICATIONS_ENABLED", True)
class TestMainUseCases(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()

        create_standings_char()
        create_eve_objects()

        # State is alliance, all members can add standings
        cls.member_state = AuthUtils.get_member_state()
        perm = AuthUtils.get_permission_by_name(
            StandingsRequest.REQUEST_PERMISSION_NAME
        )
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

    def setUp(self) -> None:
        ContactSet.objects.all().delete()
        self.contact_set = create_contacts_set()
        StandingsRequest.objects.all().delete()
        StandingsRevocation.objects.all().delete()
        Notification.objects.all().delete()
        self.member_state.member_characters.add(self.main_1)
        self.user_requestor = User.objects.get(pk=self.user_requestor.pk)

    @patch(MODULE_PATH_TASKS + ".ContactSet.objects.create_new_from_api")
    def _process_standing_requests(self, mock_create_new_from_api):
        mock_create_new_from_api.return_value = self.contact_set
        tasks.standings_update()

    def _set_standing_for_alt_in_game(self):
        PilotStanding.objects.create(
            contact_set=self.contact_set,
            contact_id=self.alt_1.character_id,
            name=self.alt_1.character_name,
            standing=10,
        )
        self.contact_set.refresh_from_db()

    def _remove_standing_for_alt_in_game(self):
        PilotStanding.objects.get(
            contact_set=self.contact_set, contact_id=self.alt_1.character_id
        ).delete()
        self.contact_set.refresh_from_db()

    def _create_standing_for_alt(self) -> StandingsRequest:
        return StandingsRequest.objects.create(
            user=self.user_requestor,
            contact_id=self.alt_1.character_id,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now() - timedelta(days=1, hours=1),
            is_effective=True,
            effective_date=now() - timedelta(days=1),
        )

    def test_user_requests_standing_for_his_alt(self):
        # given user has permission and user's alt has no standing
        # when user requests standing and request is actioned by manager
        # then alt has standing and user gets change notification
        alt_id = self.alt_1.character_id

        # user requests standing for alt
        request = self.factory.get(
            reverse("standingsrequests:request_pilot_standing", args=[alt_id],)
        )
        request.user = self.user_requestor
        response = views.request_pilot_standing(request, alt_id)
        self.assertEqual(response.status_code, 302)
        my_request = StandingsRequest.objects.get(contact_id=alt_id)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)

        self._set_standing_for_alt_in_game()

        # mark standing as actioned
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

    def test_user_requests_revocation_for_his_alt(self):
        # given user's alt has standing and user has permission
        # when user requests revocation and request is actioned by manager
        # then alt's standing is removed and user gets change notification

        # setup
        alt_id = self.alt_1.character_id
        self._set_standing_for_alt_in_game()
        my_request = self._create_standing_for_alt()

        # user requests revocation for alt
        request = self.factory.get(
            reverse("standingsrequests:remove_pilot_standing", args=[alt_id],)
        )
        request.user = self.user_requestor
        response = views.remove_pilot_standing(request, alt_id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)
        my_revocation = StandingsRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)

        self._remove_standing_for_alt_in_game()

        # mark revocation as actioned
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
        self.assertFalse(StandingsRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingsRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    def test_automatic_standing_revocation_when_standing_is_reset_in_game(self):
        # given user's alt has standing and user has permission
        # when alt's standing is reset in-game
        # then alt's standing is removed and user gets change notification

        # Setup
        alt_id = self.alt_1.character_id
        self._create_standing_for_alt()

        # run task
        self._process_standing_requests()

        # validate
        self.assertFalse(StandingsRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingsRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    def test_create_standing_revocation_for_alts_when_user_has_lost_permission(self):
        # given user's alt has standing
        # when user has lost permission
        # then standing revocation is automatically created
        # and standing is removed after actioned by manager
        # and user is notified

        # setup
        alt_id = self.alt_1.character_id
        self._set_standing_for_alt_in_game()
        my_request = self._create_standing_for_alt()
        self.member_state.member_characters.remove(self.main_1)
        self.user_requestor = User.objects.get(pk=self.user_requestor.pk)
        self.assertFalse(
            self.user_requestor.has_perm(StandingsRequest.REQUEST_PERMISSION_NAME)
        )

        # run task
        tasks.validate_requests()

        # validate
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        my_revocation = StandingsRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)
