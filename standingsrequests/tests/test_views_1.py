from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.timezone import now
from esi.models import Token

from allianceauth.eveonline.models import (
    EveAllianceInfo,
    EveCharacter,
    EveCorporationInfo,
)
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import (
    NoSocketsTestCase,
    add_character_to_user,
    create_user_from_evecharacter,
)

from .. import views
from ..core import ContactType
from ..helpers.evecorporation import EveCorporation
from ..models import Contact, StandingRequest, StandingRevocation
from .my_test_data import (
    TEST_STANDINGS_API_CHARID,
    TEST_STANDINGS_API_CHARNAME,
    create_contacts_set,
    create_entity,
    create_eve_objects,
    create_standings_char,
    esi_get_corporations_corporation_id,
    esi_post_universe_names,
    get_my_test_data,
    load_eve_entities,
)

CORE_PATH = "standingsrequests.core"
MODELS_PATH = "standingsrequests.models"
MANAGERS_PATH = "standingsrequests.managers"
HELPERS_EVECORPORATION_PATH = "standingsrequests.helpers.evecorporation"
VIEWS_PATH = "standingsrequests.views.views_1"
TEST_SCOPE = "publicData"


@patch(CORE_PATH + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(VIEWS_PATH + ".update_all")
@patch(VIEWS_PATH + ".messages")
class TestViewAuthPage(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eve_entities()
        cls.owner_character = create_standings_char()

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

    @patch(CORE_PATH + ".SR_OPERATION_MODE", "corporation")
    def test_for_corp_when_provided_standingschar_return_success(
        self, mock_messages, mock_update_all
    ):
        # given
        user = AuthUtils.create_user(TEST_STANDINGS_API_CHARNAME)
        add_character_to_user(user, self.owner_character, is_main=True)
        # when
        response = self.make_request(user, self.owner_character)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertFalse(mock_messages.error.called)
        self.assertTrue(mock_update_all.delay.called)

    @patch(CORE_PATH + ".SR_OPERATION_MODE", "corporation")
    def test_when_not_provided_standingschar_return_error(
        self, mock_messages, mock_update_all
    ):
        create_standings_char()
        user = AuthUtils.create_user("Clark Kent")
        character = AuthUtils.add_main_character_2(user, user.username, 1002)
        response = self.make_request(user, character)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertFalse(mock_messages.success.called)
        self.assertTrue(mock_messages.error.called)
        self.assertFalse(mock_update_all.delay.called)

    @patch(CORE_PATH + ".SR_OPERATION_MODE", "alliance")
    def test_for_alliance_when_provided_standingschar_return_success(
        self, mock_messages, mock_update_all
    ):
        user = AuthUtils.create_user(TEST_STANDINGS_API_CHARNAME)
        response = self.make_request(user, self.owner_character)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertFalse(mock_messages.error.called)
        self.assertTrue(mock_update_all.delay.called)

    @patch(CORE_PATH + ".SR_OPERATION_MODE", "alliance")
    def test_for_alliance_when_provided_standingschar_not_in_alliance_return_error(
        self, mock_messages, mock_update_all
    ):
        user = AuthUtils.create_user(TEST_STANDINGS_API_CHARNAME)
        character = create_entity(EveCharacter, 1007)
        add_character_to_user(user, character)
        response = self.make_request(user, character)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:index"))
        self.assertFalse(mock_messages.success.called)
        self.assertTrue(mock_messages.error.called)
        self.assertFalse(mock_update_all.delay.called)


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
            cls.user_requestor,
            cls.main_character_1,
            is_main=True,
            scopes=[TEST_SCOPE],
        )
        cls.alt_character_1 = EveCharacter.objects.get(character_id=1007)
        add_character_to_user(
            cls.user_requestor,
            cls.alt_character_1,
            scopes=[TEST_SCOPE],
        )
        cls.alt_corporation = EveCorporationInfo.objects.get(
            corporation_id=cls.alt_character_1.corporation_id
        )
        cls.alt_character_2 = EveCharacter.objects.get(character_id=1008)
        add_character_to_user(
            cls.user_requestor,
            cls.alt_character_2,
            scopes=[TEST_SCOPE],
        )

        # Standing manager - can do everything
        cls.main_character_2 = EveCharacter.objects.get(character_id=1001)
        cls.user_manager = AuthUtils.create_member(cls.main_character_2.character_name)
        add_character_to_user(
            cls.user_manager,
            cls.main_character_2,
            is_main=True,
            scopes=[TEST_SCOPE],
        )
        cls.user_manager = AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.affect_standings", cls.user_manager
        )
        cls.user_manager = AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.view", cls.user_manager
        )
        cls.user_manager = User.objects.get(pk=cls.user_manager.pk)

        # Old user - has no main and no rights
        cls.user_former_member = AuthUtils.create_user("Lex Luthor")
        cls.alt_character_3 = EveCharacter.objects.get(character_id=1010)
        add_character_to_user(
            cls.user_former_member,
            cls.alt_character_3,
            scopes=[TEST_SCOPE],
        )

    def setUp(self):
        StandingRequest.objects.all().delete()
        StandingRevocation.objects.all().delete()

    def _create_standing_for_alt(self, alt: object) -> StandingRequest:
        if isinstance(alt, EveCharacter):
            contact_id = alt.character_id
            contact_type_id = ContactType.character_id
        elif isinstance(alt, EveCorporationInfo):
            contact_id = alt.corporation_id
            contact_type_id = ContactType.corporation_id
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
            Contact.objects.update_or_create(
                contact_set=self.contact_set,
                eve_entity_id=contact_id,
                defaults={"standing": 10},
            )
        elif isinstance(alt, EveCorporationInfo):
            contact_id = alt.corporation_id
            Contact.objects.update_or_create(
                contact_set=self.contact_set,
                eve_entity_id=contact_id,
                defaults={"standing": 10},
            )
        else:
            raise NotImplementedError()

        self.contact_set.refresh_from_db()


@patch(CORE_PATH + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MANAGERS_PATH + ".SR_NOTIFICATIONS_ENABLED", True)
@patch(HELPERS_EVECORPORATION_PATH + ".esi")
class TestViewsBasics(TestViewPagesBase):
    def _setup_mocks(self, mock_esi):
        mock_Corporation = mock_esi.client.Corporation
        mock_Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi.client.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )

    def test_should_redirect_to_create_requests_page_for_requestor_1(self, mock_esi):
        # given
        request = self.factory.get(reverse("standingsrequests:index"))
        request.user = self.user_requestor
        # when
        response = views.index_view(request)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

    def test_should_redirect_to_create_requests_page_for_requestor_2(self, mock_esi):
        # given
        request = self.factory.get(reverse("standingsrequests:index"))
        request.user = self.user_requestor
        StandingRequest.objects.get_or_create_2(
            self.user_requestor,
            self.alt_character_1.character_id,
            StandingRequest.ContactType.CHARACTER,
        )
        # when
        response = views.index_view(request)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

    def test_should_redirect_to_create_requests_page_for_manger(self, mock_esi):
        # given
        request = self.factory.get(reverse("standingsrequests:index"))
        request.user = self.user_requestor
        # when
        response = views.index_view(request)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

    def test_should_redirect_to_manage_requests_page_1(self, mock_esi):
        # given
        request = self.factory.get(reverse("standingsrequests:index"))
        request.user = self.user_manager
        StandingRequest.objects.get_or_create_2(
            self.user_requestor,
            self.alt_character_1.character_id,
            StandingRequest.ContactType.CHARACTER,
        )
        # when
        response = views.index_view(request)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:manage"))

    def test_should_redirect_to_manage_requests_page_2(self, mock_esi):
        # given
        request = self.factory.get(reverse("standingsrequests:index"))
        request.user = self.user_manager
        self._create_standing_for_alt(self.alt_character_1)
        StandingRevocation.objects.add_revocation(
            self.alt_character_1.character_id,
            StandingRevocation.ContactType.CHARACTER,
            user=self.user_requestor,
        )
        # when
        response = views.index_view(request)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:manage"))

    def test_user_can_open_create_requests_page(self, mock_esi):
        request = self.factory.get(reverse("standingsrequests:create_requests"))
        request.user = self.user_requestor
        response = views.create_requests(request)
        self.assertEqual(response.status_code, 200)

    def test_user_can_open_pilots_standing(self, mock_esi):
        request = self.factory.get(reverse("standingsrequests:view_pilots"))
        request.user = self.user_manager
        response = views.view_pilots_standings(request)
        self.assertEqual(response.status_code, 200)

    def test_user_can_open_groups_standing(self, mock_esi):
        request = self.factory.get(reverse("standingsrequests:view_groups"))
        request.user = self.user_manager
        response = views.view_groups_standings(request)
        self.assertEqual(response.status_code, 200)

    def test_user_can_open_manage_requests(self, mock_esi):
        request = self.factory.get(reverse("standingsrequests:manage"))
        request.user = self.user_manager
        response = views.manage_standings(request)
        self.assertEqual(response.status_code, 200)

    def test_user_can_open_accepted_requests(self, mock_esi):
        request = self.factory.get(reverse("standingsrequests:view_requests"))
        request.user = self.user_manager
        response = views.view_active_requests(request)
        self.assertEqual(response.status_code, 200)


@patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
class TestRequestCharacterStanding(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        create_contacts_set()
        create_entity(EveCharacter, 1001)
        cls.user, _ = create_user_from_evecharacter(
            1001, permissions=["standingsrequests.request_standings"]
        )

    def view_request_pilot_standing(self, character_id: int) -> bool:
        request = self.factory.get(
            reverse(
                "standingsrequests:request_character_standing",
                args=[character_id],
            )
        )
        request.user = self.user
        with patch(VIEWS_PATH + ".messages.error") as mock_message:
            response = views.request_character_standing(request, character_id)
            success = not mock_message.called
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))
        return success

    def test_should_create_new_request(self):
        # when
        alt_character = create_entity(EveCharacter, 1008)
        add_character_to_user(self.user, alt_character, scopes=["publicData"])
        result = self.view_request_pilot_standing(alt_character.character_id)
        # then
        self.assertTrue(result)
        obj = StandingRequest.objects.get(contact_id=alt_character.character_id)
        self.assertFalse(obj.is_actioned)
        self.assertFalse(obj.is_effective)

    def test_should_not_create_new_request_if_character_has_pending_request(self):
        # given
        alt_character = create_entity(EveCharacter, 1110)
        add_character_to_user(self.user, alt_character, scopes=["publicData"])
        StandingRequest.objects.create(
            contact_id=alt_character.character_id,
            contact_type_id=ContactType.character_id,
            user=self.user,
        )
        # when
        result = self.view_request_pilot_standing(alt_character.character_id)
        # then
        self.assertFalse(result)

    def test_should_not_create_new_request_if_character_has_pending_revocation(self):
        # given
        alt_character = create_entity(EveCharacter, 1110)
        add_character_to_user(self.user, alt_character, scopes=["publicData"])
        StandingRevocation.objects.create(
            contact_id=alt_character.character_id,
            contact_type_id=ContactType.character_id,
            user=self.user,
        )
        # when
        result = self.view_request_pilot_standing(alt_character.character_id)
        # then
        self.assertFalse(result)

    def test_should_not_create_new_request_if_character_is_missing_scopes(self):
        # given
        alt_character = create_entity(EveCharacter, 1009)
        add_character_to_user(self.user, alt_character)
        # when
        result = self.view_request_pilot_standing(alt_character.character_id)
        # then
        self.assertFalse(result)

    def test_should_not_create_new_request_if_character_is_not_owned_by_anyone(self):
        # given
        random_character = create_entity(EveCharacter, 1007)
        # when
        result = self.view_request_pilot_standing(random_character.character_id)
        # then
        self.assertFalse(result)

    def test_should_not_create_new_request_if_character_is_owned_by_sombody_else(self):
        # given
        user = AuthUtils.create_member("Peter Parker")
        other_character = create_entity(EveCharacter, 1006)
        add_character_to_user(user, other_character, scopes=["publicData"])
        # when
        result = self.view_request_pilot_standing(other_character.character_id)
        # then
        self.assertFalse(result)

    def test_should_auto_confirm_new_request_if_standing_is_satisfied(self):
        # given
        alt_character = create_entity(EveCharacter, 1110)
        add_character_to_user(self.user, alt_character, scopes=["publicData"])
        # when
        result = self.view_request_pilot_standing(alt_character.character_id)
        # then
        self.assertTrue(result)
        obj = StandingRequest.objects.get(contact_id=alt_character.character_id)
        self.assertTrue(obj.is_effective)


@patch(CORE_PATH + ".STR_ALLIANCE_IDS", [3001])
@patch(CORE_PATH + ".SR_OPERATION_MODE", "alliance")
class TestRemoveCharacterStanding(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        create_contacts_set()
        create_entity(EveCharacter, 1001)
        cls.user, _ = create_user_from_evecharacter(
            1001, permissions=["standingsrequests.request_standings"]
        )

    def view_request_pilot_standing(self, character_id: int) -> bool:
        request = self.factory.get(
            reverse("standingsrequests:remove_character_standing", args=[character_id])
        )
        request.user = self.user
        with patch(VIEWS_PATH + ".messages.warning") as mock_message:
            response = views.remove_character_standing(request, character_id)
            success = not mock_message.called
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))
        return success

    def test_should_remove_valid_request(self):
        # given
        alt_character = create_entity(EveCharacter, 1110)
        add_character_to_user(self.user, alt_character, scopes=["publicData"])
        StandingRequest.objects.get_or_create_2(
            user=self.user,
            contact_id=alt_character.character_id,
            contact_type=StandingRequest.ContactType.CHARACTER,
        )
        # when
        result = self.view_request_pilot_standing(alt_character.character_id)
        # then
        self.assertTrue(result)
        self.assertFalse(
            StandingRequest.objects.filter(
                contact_id=alt_character.character_id
            ).exists()
        )

    def test_should_not_remove_request_if_character_not_owned_by_anyone(self):
        # given
        random_character = create_entity(EveCharacter, 1007)
        # when
        result = self.view_request_pilot_standing(random_character.character_id)
        # then
        self.assertFalse(result)

    def test_should_not_remove_request_if_character_is_owned_by_sombody_else(self):
        # given
        user = AuthUtils.create_member("Peter Parker")
        other_character = create_entity(EveCharacter, 1006)
        add_character_to_user(user, other_character, scopes=["publicData"])
        # when
        result = self.view_request_pilot_standing(other_character.character_id)
        # then
        self.assertFalse(result)

    def test_should_return_false_if_character_in_organization(self):
        # given
        alt_character = create_entity(EveCharacter, 1002)
        add_character_to_user(self.user, alt_character, scopes=["publicData"])
        # when
        result = self.view_request_pilot_standing(alt_character.character_id)
        # then
        self.assertFalse(result)

    # I believe we do not need this requirement
    # def test_should_create_revocation_if_character_has_satisfied_standing(self):
    #     # given
    #     alt_character = create_entity(EveCharacter, 1110)
    #     add_character_to_user(self.user, alt_character, scopes=["publicData"])
    #     # when
    #     result = self.view_request_pilot_standing(alt_character.character_id)
    #     # then
    #     self.assertTrue(result)

    def test_should_return_false_if_character_has_no_standing_request(self):
        # given
        alt_character = create_entity(EveCharacter, 1008)
        add_character_to_user(self.user, alt_character, scopes=["publicData"])
        # when
        result = self.view_request_pilot_standing(alt_character.character_id)
        # then
        self.assertFalse(result)


@patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
class TestRequestCorporationStanding(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        create_contacts_set()
        create_entity(EveCharacter, 1001)
        cls.user, _ = create_user_from_evecharacter(
            1001, permissions=["standingsrequests.request_standings"]
        )

    def view_request_corp_standing(self, corporation_id: int) -> bool:
        request = self.factory.get(
            reverse(
                "standingsrequests:request_corp_standing",
                args=[corporation_id],
            )
        )
        request.user = self.user
        with patch(MODELS_PATH + ".EveCorporation.get_by_id") as mock_get_corp_by_id:
            mock_get_corp_by_id.return_value = EveCorporation(
                **get_my_test_data()["EveCorporationInfo"]["2102"]
            )
            with patch(VIEWS_PATH + ".messages.warning") as mock_message:
                response = views.request_corp_standing(request, corporation_id)
                success = not mock_message.called
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))
        return success

    def test_should_create_new_request_when_valid(self):
        # given
        character_1009 = create_entity(EveCharacter, 1009)
        add_character_to_user(self.user, character_1009, scopes=["publicData"])
        character_1010 = create_entity(EveCharacter, 1010)
        add_character_to_user(self.user, character_1010, scopes=["publicData"])
        # when
        result = self.view_request_corp_standing(2102)
        # then
        self.assertTrue(result)
        obj = StandingRequest.objects.get(contact_id=2102)
        self.assertFalse(obj.is_actioned)
        self.assertFalse(obj.is_effective)

    def test_should_return_false_when_not_enough_tokens(self):
        # given
        character_1009 = create_entity(EveCharacter, 1009)
        add_character_to_user(self.user, character_1009, scopes=["publicData"])
        # when
        result = self.view_request_corp_standing(2102)
        # then
        self.assertFalse(result)

    def test_should_return_false_if_pending_request(self):
        # given
        StandingRequest.objects.create(
            contact_id=2102, contact_type_id=ContactType.corporation_id, user=self.user
        )
        # when
        result = self.view_request_corp_standing(2102)
        # then
        self.assertFalse(result)

    def test_should_return_false_if_pending_revocation(self):
        # given
        StandingRevocation.objects.create(
            contact_id=2102, contact_type_id=ContactType.corporation_id, user=self.user
        )
        # when
        result = self.view_request_corp_standing(2102)
        # then
        self.assertFalse(result)


class TestRemoveCorporationStanding(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        create_contacts_set()
        create_entity(EveCharacter, 1001)
        cls.user, _ = create_user_from_evecharacter(
            1001, permissions=["standingsrequests.request_standings"]
        )

    def view_remove_corp_standing(self, corporation_id: int) -> bool:
        request = self.factory.get(
            reverse(
                "standingsrequests:remove_corp_standing",
                args=[corporation_id],
            )
        )
        request.user = self.user
        with patch(VIEWS_PATH + ".messages.warning") as mock_message:
            response = views.remove_corp_standing(request, corporation_id)
            success = not mock_message.called
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))
        return success

    def test_should_remove_valid_pending_request(self):
        # given
        character_1009 = create_entity(EveCharacter, 1009)
        add_character_to_user(self.user, character_1009, scopes=["publicData"])
        StandingRequest.objects.get_or_create_2(
            user=self.user,
            contact_id=2102,
            contact_type=StandingRequest.ContactType.CORPORATION,
        )
        # when
        success = self.view_remove_corp_standing(2102)
        # then
        self.assertTrue(success)
        self.assertFalse(StandingRequest.objects.filter(contact_id=2102).exists())

    def test_should_remove_valid_effective_request(self):
        # given
        character_1004 = create_entity(EveCharacter, 1004)
        add_character_to_user(self.user, character_1004, scopes=["publicData"])
        req = StandingRequest.objects.get_or_create_2(
            user=self.user,
            contact_id=2003,
            contact_type=StandingRequest.ContactType.CORPORATION,
        )
        req.mark_actioned(user=None)
        req.mark_effective()
        # when
        success = self.view_remove_corp_standing(2003)
        # then
        self.assertTrue(success)
        self.assertTrue(StandingRequest.objects.filter(contact_id=2003).exists())
        self.assertTrue(StandingRevocation.objects.filter(contact_id=2003).exists())

    def test_should_return_false_if_standing_requests_from_another_user(self):
        # given
        user = AuthUtils.create_member("Peter Parker")
        character_1009 = create_entity(EveCharacter, 1009)
        add_character_to_user(self.user, character_1009, scopes=["publicData"])
        StandingRequest.objects.get_or_create_2(
            user=user,
            contact_id=2102,
            contact_type=StandingRequest.ContactType.CORPORATION,
        )
        # when
        success = self.view_remove_corp_standing(2102)
        # then
        self.assertFalse(success)

    def test_should_return_false_if_no_standing_request_exists(self):
        # given
        character_1009 = create_entity(EveCharacter, 1009)
        add_character_to_user(self.user, character_1009, scopes=["publicData"])
        # when
        success = self.view_remove_corp_standing(2102)
        # then
        self.assertFalse(success)

    def test_should_return_false_if_standing_not_fully_effective(self):
        # given
        character = create_entity(EveCharacter, 1008)
        add_character_to_user(self.user, character, scopes=["publicData"])
        req = StandingRequest.objects.get_or_create_2(
            user=self.user,
            contact_id=2102,
            contact_type=StandingRequest.ContactType.CORPORATION,
        )
        req.mark_actioned(user=None)
        req.mark_effective()
        # when
        success = self.view_remove_corp_standing(2102)
        # then
        self.assertFalse(success)
