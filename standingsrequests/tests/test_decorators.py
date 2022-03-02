from unittest.mock import Mock, patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from esi.models import CallbackRedirect, Token

from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import _generate_token, _store_as_Token, generate_invalid_pk

from ..decorators import token_required_by_state
from .my_test_data import create_eve_objects

MODULE_PATH = "standingsrequests.decorators"
PATH_MODELS = "standingsrequests.models"


@patch(PATH_MODELS + ".StandingRequest.get_required_scopes_for_state")
@patch(MODULE_PATH + ".select_token", spec=True)
@patch(MODULE_PATH + ".sso_redirect", spec=True)
@patch(MODULE_PATH + "._check_callback")
class TestTokenRequiredByState(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_eve_objects()
        cls.user = AuthUtils.create_member("Bruce Wayne")
        cls.token = _store_as_Token(
            _generate_token(
                character_id=1002, character_name=cls.user.username, scopes=["abc"]
            ),
            cls.user,
        )
        cls.factory = RequestFactory()

    def setUp(self):
        CallbackRedirect.objects.all().delete()

    def generate_get_request(self):
        request = self.factory.get("https://www.example.com/my_view/")
        request.user = self.user
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        request.session.save()
        return request

    def generate_post_request(self, data=dict(), user=None):
        request = self.factory.post("https://www.example.com/my_view/", data)
        request.user = self.user if not user else user
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        request.session.save()
        return request

    def test_can_present_user_with_token_choices_when_token_matches(
        self,
        mock_check_callback,
        mock_sso_redirect,
        mock_select_token,
        mock_get_required_scopes_for_state,
    ):
        @token_required_by_state(new=False)
        def my_view(request, tokens):
            return tokens

        mock_check_callback.return_value = None
        mock_get_required_scopes_for_state.return_value = ["abc"]

        response = my_view(self.generate_get_request())
        self.assertTrue(response, mock_select_token())

    def test_prompt_user_to_add_new_token_when_token_matches_not(
        self,
        mock_check_callback,
        mock_sso_redirect,
        mock_select_token,
        mock_get_required_scopes_for_state,
    ):
        @token_required_by_state(new=False)
        def my_view(request, tokens):
            return tokens

        mock_check_callback.return_value = None
        mock_get_required_scopes_for_state.return_value = ["xyz"]

        response = my_view(self.generate_get_request())
        self.assertTrue(response, mock_sso_redirect())

    def test_proceeds_to_view_when_token_is_received(
        self,
        mock_check_callback,
        mock_sso_redirect,
        mock_select_token,
        mock_get_required_scopes_for_state,
    ):
        @token_required_by_state(new=True)
        def my_view(request, token):
            return token

        mock_check_callback.return_value = self.token
        mock_get_required_scopes_for_state.return_value = ["abc"]

        response = my_view(self.generate_get_request())
        self.assertEqual(response, self.token)

    def test_user_has_selected_to_add_new_token(
        self,
        mock_check_callback,
        mock_sso_redirect,
        mock_select_token,
        mock_get_required_scopes_for_state,
    ):
        @token_required_by_state(new=True)
        def my_view(request, token):
            return token

        mock_check_callback.return_value = None
        mock_get_required_scopes_for_state.return_value = ["abc"]

        data = {"_add": True}
        response = my_view(self.generate_post_request(data))

        self.assertEqual(response, mock_sso_redirect())

    def test_user_has_provided_a_new_token(
        self,
        mock_check_callback,
        mock_sso_redirect,
        mock_select_token,
        mock_get_required_scopes_for_state,
    ):
        @token_required_by_state(new=True)
        def my_view(request, token):
            return token

        mock_check_callback.return_value = None
        mock_get_required_scopes_for_state.return_value = ["abc"]

        data = {"_token": self.token.pk}
        response = my_view(self.generate_post_request(data))

        self.assertEqual(response, self.token)

    def test_return_to_selection_if_provided_token_from_user_has_vanished(
        self,
        mock_check_callback,
        mock_sso_redirect,
        mock_select_token,
        mock_get_required_scopes_for_state,
    ):
        @token_required_by_state(new=True)
        def my_view(request, token):
            return token

        mock_check_callback.return_value = None
        mock_get_required_scopes_for_state.return_value = ["abc"]

        data = {"_token": generate_invalid_pk(Token)}
        response = my_view(self.generate_post_request(data))

        self.assertEqual(response, mock_sso_redirect())

    def test_prompt_user_to_add_new_token_if_provided_has_wrong_scope(
        self,
        mock_check_callback,
        mock_sso_redirect,
        mock_select_token,
        mock_get_required_scopes_for_state,
    ):
        @token_required_by_state(new=True)
        def my_view(request, token):
            return token

        mock_check_callback.return_value = None
        mock_get_required_scopes_for_state.return_value = ["xyz"]

        data = {"_token": self.token.pk}
        response = my_view(self.generate_post_request(data))

        self.assertEqual(response, mock_sso_redirect())

    def test_prompt_user_to_add_new_token_if_token_provided_with_wrong_user(
        self,
        mock_check_callback,
        mock_sso_redirect,
        mock_select_token,
        mock_get_required_scopes_for_state,
    ):
        @token_required_by_state(new=True)
        def my_view(request, token):
            return token

        mock_check_callback.return_value = None
        mock_get_required_scopes_for_state.return_value = ["xyz"]

        data = {"_token": self.token.pk}
        other_user = AuthUtils.create_user("Lex Luther")
        response = my_view(self.generate_post_request(data, user=other_user))

        self.assertEqual(response, mock_sso_redirect())
