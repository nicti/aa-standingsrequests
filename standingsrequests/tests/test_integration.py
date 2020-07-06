from datetime import timedelta
from unittest.mock import patch

from django.test import RequestFactory
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveAllianceInfo
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

MODULE_PATH = "standingsrequests.views"
logger = set_test_logger(MODULE_PATH, __file__)

TEST_SCOPE = "publicData"


@patch("standingsrequests.models.STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch("standingsrequests.managers.STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
class TestMainUseCases(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()

        create_standings_char()
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
        cls.alt_1 = EveCharacter.objects.get(character_id=1007)
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

    def setUp(self) -> None:
        ContactSet.objects.all().delete()
        self.contact_set = create_contacts_set()
        StandingsRequest.objects.all().delete()
        StandingsRevocation.objects.all().delete()

    def test_user_requests_standing_for_his_alt(self):
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

        # set standing in game
        PilotStanding.objects.create(
            contact_set=self.contact_set,
            contact_id=alt_id,
            name=self.alt_1.character_name,
            standing=10,
        )

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

        # process standing request
        with patch(
            "standingsrequests.tasks.ContactSet.objects.create_new_from_api"
        ) as mock_create_new_from_api:
            self.contact_set.refresh_from_db()
            mock_create_new_from_api.return_value = self.contact_set
            tasks.standings_update()

        # validate results
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)

    def test_user_requests_revocation_for_his_alt(self):
        # setup
        alt_id = self.alt_1.character_id
        PilotStanding.objects.create(
            contact_set=self.contact_set,
            contact_id=alt_id,
            name=self.alt_1.character_name,
            standing=10,
        )
        self.contact_set.refresh_from_db()
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contact_id=alt_id,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now() - timedelta(days=1, hours=1),
            is_effective=True,
            effective_date=now() - timedelta(days=1),
        )

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

        # remove standing in game
        PilotStanding.objects.get(
            contact_set=self.contact_set, contact_id=alt_id
        ).delete()
        self.contact_set.refresh_from_db()

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

        # process standing request
        with patch(
            "standingsrequests.tasks.ContactSet.objects.create_new_from_api"
        ) as mock_create_new_from_api:
            self.contact_set.refresh_from_db()
            mock_create_new_from_api.return_value = self.contact_set
            tasks.standings_update()

        # validate results
        my_request.refresh_from_db()
        my_revocation.refresh_from_db()
        self.assertFalse(my_request.is_effective)
        self.assertTrue(my_revocation.is_effective)
