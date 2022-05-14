from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import NoSocketsTestCase, add_character_to_user

from ..models import StandingRequest
from .my_test_data import (
    TEST_STANDINGS_ALLIANCE_ID,
    create_contacts_set,
    create_entity,
    create_standings_char,
    load_eve_entities,
)

PACKAGE_PATH = "standingsrequests.management.commands"
TEST_USER_NAME = "Peter Parker"
TEST_REQUIRED_SCOPE = "mind_reading.v1"


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
@patch(
    "standingsrequests.core.STR_ALLIANCE_IDS",
    [str(TEST_STANDINGS_ALLIANCE_ID)],
)
@patch(
    "standingsrequests.models.SR_REQUIRED_SCOPES",
    {"Member": [TEST_REQUIRED_SCOPE], "Blue": [], "": []},
)
@patch(PACKAGE_PATH + ".standingsrequests_sync_blue_alts.get_input")
class TestSyncRequests(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = AuthUtils.create_member(TEST_USER_NAME)
        AuthUtils.add_permission_to_user_by_name(
            StandingRequest.REQUEST_PERMISSION_NAME, cls.user
        )
        load_eve_entities()

    def setUp(self):
        create_standings_char()
        self.contacts_set = create_contacts_set()
        StandingRequest.objects.all().delete()
        self.out = StringIO()

    def test_abort_if_input_is_not_y(self, mock_get_input):
        mock_get_input.return_value = "N"
        alt = create_entity(EveCharacter, 1010)
        add_character_to_user(self.user, alt, scopes=[TEST_REQUIRED_SCOPE])

        call_command("standingsrequests_sync_blue_alts", stdout=self.out)

        self.assertEqual(StandingRequest.objects.count(), 0)

    def test_creates_new_request_for_blue_alt(self, mock_get_input):
        mock_get_input.return_value = "Y"
        alt = create_entity(EveCharacter, 1010)
        add_character_to_user(self.user, alt, scopes=[TEST_REQUIRED_SCOPE])

        call_command("standingsrequests_sync_blue_alts", stdout=self.out)

        self.assertEqual(StandingRequest.objects.count(), 1)
        request = StandingRequest.objects.first()
        self.assertEqual(request.user, self.user)
        self.assertEqual(request.contact_id, 1010)
        self.assertEqual(request.is_effective, True)
        self.assertAlmostEqual((now() - request.request_date).seconds, 0, delta=30)
        self.assertAlmostEqual((now() - request.action_date).seconds, 0, delta=30)
        self.assertAlmostEqual((now() - request.effective_date).seconds, 0, delta=30)
