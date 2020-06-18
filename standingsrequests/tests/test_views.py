from unittest.mock import patch, Mock

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from allianceauth.tests.auth_utils import AuthUtils
from esi.models import Token

from .my_test_data import (
    TEST_STANDINGS_API_CHARID,
    TEST_STANDINGS_API_CHARNAME,
    create_standings_char,
)
from ..models import EveNameCache
from ..utils import set_test_logger, NoSocketsTestCase
from .. import views

MODULE_PATH = "standingsrequests.views"
MODELS_MODULE_PATH = "standingsrequests.models"
logger = set_test_logger(MODULE_PATH, __file__)


@patch(MODULE_PATH + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODELS_MODULE_PATH + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH + ".update_all")
@patch(MODULE_PATH + ".messages_plus")
class TestViewAuthPage(NoSocketsTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        EveNameCache.objects.create(
            entityID=TEST_STANDINGS_API_CHARID, name=TEST_STANDINGS_API_CHARNAME
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

    @patch(MODELS_MODULE_PATH + ".SR_OPERATION_MODE", "corporation")
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

    @patch(MODELS_MODULE_PATH + ".SR_OPERATION_MODE", "corporation")
    def test_when_not_provided_standingschar_return_error(
        self, mock_messages, mock_update_all
    ):
        create_standings_char()
        user = AuthUtils.create_user("Clark Kent")
        character = AuthUtils.add_main_character_2(user, user.username, 1002)
        EveNameCache.objects.create(
            entityID=character.character_id, name=character.character_name
        )
        response = self.make_request(user, character)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertFalse(mock_messages.success.called)
        self.assertTrue(mock_messages.error.called)
        self.assertFalse(mock_update_all.delay.called)

    @patch(MODELS_MODULE_PATH + ".SR_OPERATION_MODE", "alliance")
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

    @patch(MODELS_MODULE_PATH + ".SR_OPERATION_MODE", "alliance")
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
