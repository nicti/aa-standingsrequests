from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_webtest import WebTest

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.notifications.models import Notification
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import add_character_to_user

from .. import tasks
from ..core import ContactType
from ..models import (
    Contact,
    ContactSet,
    RequestLogEntry,
    StandingRequest,
    StandingRevocation,
)
from .my_test_data import (
    TEST_STANDINGS_ALLIANCE_ID,
    TEST_STANDINGS_API_CHARID,
    create_contacts_set,
    create_eve_objects,
    create_standings_char,
    esi_get_corporations_corporation_id,
    esi_post_characters_affiliation,
    esi_post_universe_names,
    load_eve_entities,
)

CORE_PATH = "standingsrequests.core"
MODELS_PATH = "standingsrequests.models"
MANAGERS_PATH = "standingsrequests.managers"
TASKS_PATH = "standingsrequests.tasks"
TEST_REQUIRED_SCOPE = "publicData"
HELPERS_EVECORPORATION_PATH = "standingsrequests.helpers.evecorporation"


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
@patch(
    MODELS_PATH + ".SR_REQUIRED_SCOPES",
    {"Member": [TEST_REQUIRED_SCOPE], "Blue": [], "": []},
)
@patch(CORE_PATH + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MANAGERS_PATH + ".SR_NOTIFICATIONS_ENABLED", True)
@patch(CORE_PATH + ".STR_ALLIANCE_IDS", [TEST_STANDINGS_ALLIANCE_ID])
class TestMainUseCases(WebTest):
    csrf_checks = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_standings_char()
        create_eve_objects()
        load_eve_entities()
        # State is alliance, all members can add standings
        cls.member_state = AuthUtils.get_member_state()
        perm = AuthUtils.get_permission_by_name(StandingRequest.REQUEST_PERMISSION_NAME)
        cls.member_state.permissions.add(perm)
        # Requesting user
        cls.main_character_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_requestor = AuthUtils.create_user(cls.main_character_1.character_name)
        add_character_to_user(
            cls.user_requestor,
            cls.main_character_1,
            is_main=True,
            scopes=[
                TEST_REQUIRED_SCOPE,
            ],
        )
        cls.member_state.member_characters.add(cls.main_character_1)
        cls.alt_character_1 = EveCharacter.objects.get(character_id=1007)
        add_character_to_user(
            cls.user_requestor,
            cls.alt_character_1,
            scopes=[
                TEST_REQUIRED_SCOPE,
            ],
        )
        cls.alt_corporation = EveCorporationInfo.objects.get(
            corporation_id=cls.alt_character_1.corporation_id
        )
        cls.alt_character_2 = EveCharacter.objects.get(character_id=1008)
        add_character_to_user(
            cls.user_requestor,
            cls.alt_character_2,
            scopes=[
                TEST_REQUIRED_SCOPE,
            ],
        )
        # Standing manager
        cls.main_character_2 = EveCharacter.objects.get(character_id=1001)
        cls.user_manager = AuthUtils.create_user(cls.main_character_2.character_name)
        add_character_to_user(
            cls.user_manager,
            cls.main_character_2,
            is_main=True,
            scopes=[
                TEST_REQUIRED_SCOPE,
            ],
        )
        cls.member_state.member_characters.add(cls.main_character_2)
        cls.user_manager = AuthUtils.add_permission_to_user_by_name(
            StandingRequest.REQUEST_PERMISSION_NAME, cls.user_manager
        )
        cls.user_manager = AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.affect_standings", cls.user_manager
        )

    @patch(TASKS_PATH + ".ContactSet.objects.create_new_from_api")
    def _process_standing_requests(self, mock_create_new_from_api):
        mock_create_new_from_api.return_value = self.contact_set
        tasks.standings_update()

    def _set_standing_for_alt_in_game(self, alt: object) -> None:
        if isinstance(alt, EveCharacter):
            Contact.objects.update_or_create(
                contact_set=self.contact_set,
                eve_entity_id=alt.character_id,
                defaults={"standing": 10},
            )
        elif isinstance(alt, EveCorporationInfo):
            Contact.objects.update_or_create(
                contact_set=self.contact_set,
                eve_entity_id=alt.corporation_id,
                defaults={"standing": 10},
            )
        else:
            raise NotImplementedError()

        self.contact_set.refresh_from_db()

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

    def _remove_standing_for_alt_in_game(self, alt: object) -> None:
        if isinstance(alt, EveCharacter):
            Contact.objects.get(
                contact_set=self.contact_set, eve_entity_id=alt.character_id
            ).delete()
        elif isinstance(alt, EveCorporationInfo):
            Contact.objects.get(
                contact_set=self.contact_set, eve_entity_id=alt.corporation_id
            ).delete()
        else:
            raise NotImplementedError()

        self.contact_set.refresh_from_db()

    def _parse_contacts_data(self, response, key: str):
        return {row["contact_id"]: row for row in response.context.dicts[3][key]}

    def _setup_mocks(self, mock_esi, mock_esi_manager):
        mock_esi.client.Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_manager.client.Corporation.get_corporations_corporation_id.side_effect = (
            esi_get_corporations_corporation_id
        )
        mock_esi_manager.client.Character.post_characters_affiliation.side_effect = (
            esi_post_characters_affiliation
        )
        mock_esi.client.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )

    def setUp(self) -> None:
        cache.clear()
        ContactSet.objects.all().delete()
        self.contact_set = create_contacts_set()
        StandingRequest.objects.all().delete()
        StandingRevocation.objects.all().delete()
        Notification.objects.all().delete()

        # requestor as permission
        self.user_requestor = AuthUtils.add_permission_to_user_by_name(
            StandingRequest.REQUEST_PERMISSION_NAME, self.user_requestor
        )

    @patch(MANAGERS_PATH + ".esi")
    @patch(HELPERS_EVECORPORATION_PATH + ".esi")
    def test_user_requests_standing_for_his_alt_character(
        self, mock_esi, mock_esi_manager
    ):
        """
        given user has permission and user's alt has no standing
        when user requests standing and request is actioned by manager
        then alt has standing and user gets change notification
        """
        # setup
        self._setup_mocks(mock_esi, mock_esi_manager)
        alt_id = self.alt_character_1.character_id

        # user opens create requests page
        self.app.set_user(self.user_requestor)
        create_page_1 = self.app.get(reverse("standingsrequests:create_requests"))
        self.assertEqual(create_page_1.status_code, 200)
        create_page_2 = self.app.get(reverse("standingsrequests:request_characters"))
        self.assertEqual(create_page_2.status_code, 200)

        # user requests standing for alt
        request_standing_url = reverse(
            "standingsrequests:request_character_standing", args=[alt_id]
        )
        response = create_page_2.click(href=request_standing_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

        # validate new state
        self.assertTrue(StandingRequest.objects.filter(contact_id=alt_id).exists())
        my_request = StandingRequest.objects.get(contact_id=alt_id)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(reverse("standingsrequests:manage_requests_list"))
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, "requests")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # set standing in game and mark as actioned
        self._set_standing_for_alt_in_game(self.alt_character_1)
        response = self.app.put(
            reverse("standingsrequests:manage_requests_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate new state
        my_request.refresh_from_db()
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsNotNone(my_request.action_date)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(
            RequestLogEntry.objects.filter(
                action_by__user=self.user_manager,
                requested_for__character_id=alt_id,
                requested_by__user=self.user_requestor,
                request_type=RequestLogEntry.RequestType.REQUEST,
                action=RequestLogEntry.Action.CONFIRMED,
            ).count(),
            1,
        )

        # run process standing results task
        self._process_standing_requests()

        # validate final state
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    @patch(MANAGERS_PATH + ".esi")
    @patch(HELPERS_EVECORPORATION_PATH + ".esi")
    def test_user_requests_revocation_for_his_alt_character(
        self, mock_esi, mock_esi_manager
    ):
        """
        given user's alt has standing and user has permission
        when user requests revocation and request is actioned by manager
        then alt's standing is removed and user gets change notification
        """
        # setup
        self._setup_mocks(mock_esi, mock_esi_manager)
        alt_id = self.alt_character_1.character_id
        self._set_standing_for_alt_in_game(self.alt_character_1)
        my_request = self._create_standing_for_alt(self.alt_character_1)

        # user opens create requests page
        self.app.set_user(self.user_requestor)
        create_page_1 = self.app.get(reverse("standingsrequests:create_requests"))
        self.assertEqual(create_page_1.status_code, 200)
        create_page_2 = self.app.get(reverse("standingsrequests:request_characters"))
        self.assertEqual(create_page_2.status_code, 200)

        # user requests standing for alt
        request_standing_url = reverse(
            "standingsrequests:remove_character_standing", args=[alt_id]
        )
        response = create_page_2.click(href=request_standing_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

        # validate new state
        self.assertTrue(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)
        my_revocation = StandingRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)
        self.assertEqual(my_revocation.reason, StandingRevocation.Reason.OWNER_REQUEST)

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(
            reverse("standingsrequests:manage_revocations_list")
        )
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, "revocations")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # remove standing for alt in game and mark as actioned
        self._remove_standing_for_alt_in_game(self.alt_character_1)
        response = self.app.put(
            reverse("standingsrequests:manage_revocations_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate new state
        my_revocation.refresh_from_db()
        self.assertEqual(my_revocation.action_by, self.user_manager)
        self.assertIsNotNone(my_revocation.action_date)
        self.assertFalse(my_revocation.is_effective)
        self.assertEqual(
            RequestLogEntry.objects.filter(
                action_by__user=self.user_manager,
                requested_for__character_id=alt_id,
                requested_by__user=self.user_requestor,
                request_type=RequestLogEntry.RequestType.REVOCATION,
                action=RequestLogEntry.Action.CONFIRMED,
                reason=StandingRevocation.Reason.OWNER_REQUEST,
            ).count(),
            1,
        )

        # run process standing results task
        self._process_standing_requests()

        # validate final state
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    @patch(MANAGERS_PATH + ".esi")
    @patch(HELPERS_EVECORPORATION_PATH + ".esi")
    def test_user_requests_standing_for_his_alt_corporation(
        self, mock_esi, mock_esi_manager
    ):
        """
        given user has permission and user's alt has no standing
        and all corporation members have tokens
        when user requests standing and request is actioned by manager
        then alt has standing and user gets change notification
        """
        # setup
        self._setup_mocks(mock_esi, mock_esi_manager)
        alt_id = self.alt_corporation.corporation_id

        # user opens create requests page
        self.app.set_user(self.user_requestor)
        create_page_1 = self.app.get(reverse("standingsrequests:create_requests"))
        self.assertEqual(create_page_1.status_code, 200)
        create_page_2 = self.app.get(reverse("standingsrequests:request_corporations"))
        self.assertEqual(create_page_2.status_code, 200)

        # user requests standing for alt
        request_standing_url = reverse(
            "standingsrequests:request_corp_standing", args=[alt_id]
        )
        response = create_page_2.click(href=request_standing_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

        # validate new state
        self.assertTrue(StandingRequest.objects.filter(contact_id=alt_id).exists())
        my_request = StandingRequest.objects.get(contact_id=alt_id)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(reverse("standingsrequests:manage_requests_list"))
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, "requests")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # set standing in game and mark as actioned
        self._set_standing_for_alt_in_game(self.alt_corporation)
        response = self.app.put(
            reverse("standingsrequests:manage_requests_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate new state
        my_request.refresh_from_db()
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsNotNone(my_request.action_date)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(
            RequestLogEntry.objects.filter(
                action_by__user=self.user_manager,
                requested_for__corporation_id=alt_id,
                requested_by__user=self.user_requestor,
                request_type=RequestLogEntry.RequestType.REQUEST,
                action=RequestLogEntry.Action.CONFIRMED,
            ).count(),
            1,
        )

        # run process standing results task
        self._process_standing_requests()

        # validate final state
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    @patch(MANAGERS_PATH + ".esi")
    @patch(HELPERS_EVECORPORATION_PATH + ".esi")
    def test_user_requests_revocation_for_his_alt_corporation(
        self, mock_esi, mock_esi_manager
    ):
        """
        given user's alt has standing and user has permission
        when user requests revocation and request is actioned by manager
        then alt's standing is removed and user gets change notification
        """
        # setup
        self._setup_mocks(mock_esi, mock_esi_manager)
        alt_id = self.alt_corporation.corporation_id
        self._set_standing_for_alt_in_game(self.alt_corporation)
        my_request = self._create_standing_for_alt(self.alt_corporation)

        # user opens create requests page
        self.app.set_user(self.user_requestor)
        create_page_1 = self.app.get(reverse("standingsrequests:create_requests"))
        self.assertEqual(create_page_1.status_code, 200)
        create_page_2 = self.app.get(reverse("standingsrequests:request_corporations"))
        self.assertEqual(create_page_2.status_code, 200)

        # user requests standing for alt
        request_standing_url = reverse(
            "standingsrequests:remove_corp_standing", args=[alt_id]
        )
        response = create_page_2.click(href=request_standing_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

        # validate new state
        self.assertTrue(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)
        my_revocation = StandingRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(
            reverse("standingsrequests:manage_revocations_list")
        )
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, "revocations")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # remove standing for alt in game and mark as actioned
        self._remove_standing_for_alt_in_game(self.alt_corporation)
        response = self.app.put(
            reverse("standingsrequests:manage_revocations_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate new state
        my_revocation.refresh_from_db()
        self.assertEqual(my_revocation.action_by, self.user_manager)
        self.assertIsNotNone(my_revocation.action_date)
        self.assertFalse(my_revocation.is_effective)
        self.assertEqual(
            RequestLogEntry.objects.filter(
                action_by__user=self.user_manager,
                requested_for__corporation_id=alt_id,
                requested_by__user=self.user_requestor,
                request_type=RequestLogEntry.RequestType.REVOCATION,
                action=RequestLogEntry.Action.CONFIRMED,
            ).count(),
            1,
        )

        # run process standing results task
        self._process_standing_requests()

        # validate final state
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    @patch(MANAGERS_PATH + ".esi")
    @patch(HELPERS_EVECORPORATION_PATH + ".esi")
    def test_user_requests_standing_for_his_alt_character_but_refused(
        self, mock_esi, mock_esi_manager
    ):
        """
        given user has permission and user's alt has no standing
        when user requests standing and request is refused by manager
        then request is reset, alt has no standing and user gets notification
        """
        # setup
        self._setup_mocks(mock_esi, mock_esi_manager)
        alt_id = self.alt_character_1.character_id

        # user opens create requests page
        self.app.set_user(self.user_requestor)
        create_page_1 = self.app.get(reverse("standingsrequests:create_requests"))
        self.assertEqual(create_page_1.status_code, 200)
        create_page_2 = self.app.get(reverse("standingsrequests:request_characters"))
        self.assertEqual(create_page_2.status_code, 200)

        # user requests standing for alt
        request_standing_url = reverse(
            "standingsrequests:request_character_standing", args=[alt_id]
        )
        response = create_page_2.click(href=request_standing_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

        # validate new state
        self.assertTrue(StandingRequest.objects.filter(contact_id=alt_id).exists())
        my_request = StandingRequest.objects.get(contact_id=alt_id)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(reverse("standingsrequests:manage_requests_list"))
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, "requests")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # Manage refused request
        response = self.app.delete(
            reverse("standingsrequests:manage_requests_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate final state
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())
        self.assertEqual(
            RequestLogEntry.objects.filter(
                action_by__user=self.user_manager,
                requested_for__character_id=alt_id,
                requested_by__user=self.user_requestor,
                request_type=RequestLogEntry.RequestType.REQUEST,
                action=RequestLogEntry.Action.REJECTED,
            ).count(),
            1,
        )

    @patch(MANAGERS_PATH + ".esi")
    @patch(HELPERS_EVECORPORATION_PATH + ".esi")
    def test_user_requests_standing_for_his_alt_corporation_but_refused(
        self, mock_esi, mock_esi_manager
    ):
        """
        given user has permission and user's alt has no standing
        and all corporation members have tokens
        when user requests standing and request is actioned by manager
        then alt has standing and user gets change notification
        """
        # setup
        self._setup_mocks(mock_esi, mock_esi_manager)
        alt_id = self.alt_corporation.corporation_id

        # user opens create requests page
        self.app.set_user(self.user_requestor)
        create_page_1 = self.app.get(reverse("standingsrequests:create_requests"))
        self.assertEqual(create_page_1.status_code, 200)
        create_page_2 = self.app.get(reverse("standingsrequests:request_corporations"))
        self.assertEqual(create_page_2.status_code, 200)

        # user requests standing for alt
        request_standing_url = reverse(
            "standingsrequests:request_corp_standing", args=[alt_id]
        )
        response = create_page_2.click(href=request_standing_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

        # validate new state
        self.assertTrue(StandingRequest.objects.filter(contact_id=alt_id).exists())
        my_request = StandingRequest.objects.get(contact_id=alt_id)
        self.assertFalse(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(reverse("standingsrequests:manage_requests_list"))
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, "requests")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # Manage refused request
        response = self.app.delete(
            reverse("standingsrequests:manage_requests_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate final state
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())
        self.assertEqual(
            RequestLogEntry.objects.filter(
                action_by__user=self.user_manager,
                requested_for__corporation_id=alt_id,
                requested_by__user=self.user_requestor,
                request_type=RequestLogEntry.RequestType.REQUEST,
                action=RequestLogEntry.Action.REJECTED,
            ).count(),
            1,
        )

    @patch(MANAGERS_PATH + ".esi")
    @patch(HELPERS_EVECORPORATION_PATH + ".esi")
    def test_user_requests_revocation_for_his_alt_character_but_refused(
        self, mock_esi, mock_esi_manager
    ):
        """
        given user's alt has standing and user has permission
        when user requests revocation and request is actioned by manager
        then alt's standing is removed and user gets change notification
        """
        # setup
        self._setup_mocks(mock_esi, mock_esi_manager)
        alt_id = self.alt_character_1.character_id
        self._set_standing_for_alt_in_game(self.alt_character_1)
        my_request = self._create_standing_for_alt(self.alt_character_1)

        # user opens create requests page
        self.app.set_user(self.user_requestor)
        create_page_1 = self.app.get(reverse("standingsrequests:create_requests"))
        self.assertEqual(create_page_1.status_code, 200)
        create_page_2 = self.app.get(reverse("standingsrequests:request_characters"))
        self.assertEqual(create_page_2.status_code, 200)

        # user requests standing for alt
        request_standing_url = reverse(
            "standingsrequests:remove_character_standing", args=[alt_id]
        )
        response = create_page_2.click(href=request_standing_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingsrequests:create_requests"))

        # validate new state
        self.assertTrue(my_request.is_effective)
        self.assertEqual(my_request.user, self.user_requestor)
        my_revocation = StandingRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)
        self.assertEqual(my_revocation.reason, StandingRevocation.Reason.OWNER_REQUEST)

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(
            reverse("standingsrequests:manage_revocations_list")
        )
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, "revocations")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # Manage refused request
        response = self.app.delete(
            reverse("standingsrequests:manage_revocations_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate final state
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())
        self.assertEqual(
            RequestLogEntry.objects.filter(
                action_by__user=self.user_manager,
                requested_for__character_id=alt_id,
                requested_by__user=self.user_requestor,
                request_type=RequestLogEntry.RequestType.REVOCATION,
                action=RequestLogEntry.Action.REJECTED,
                reason=StandingRevocation.Reason.OWNER_REQUEST,
            ).count(),
            1,
        )

    def test_automatic_standing_revocation_when_standing_is_reset_in_game(self):
        """
        given user's alt has standing and user has permission
        when alt's standing is reset in-game
        then alt's standing is removed and user gets change notification
        """

        # setup
        alt_id = self.alt_character_1.character_id
        self._create_standing_for_alt(self.alt_character_1)

        # run task
        self._process_standing_requests()

        # validate
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    def test_automatically_create_standing_revocation_for_invalid_alts(self):
        """
        given user's alt has standing record
        when user has lost permission
        then standing revocation is automatically created
        and standing is removed after actioned by manager
        and user is notified
        """

        # setup
        alt_id = self.alt_character_1.character_id
        self._set_standing_for_alt_in_game(self.alt_character_1)
        my_request = self._create_standing_for_alt(self.alt_character_1)
        self.member_state.member_characters.remove(self.main_character_1)
        permission = AuthUtils.get_permission_by_name(
            StandingRequest.REQUEST_PERMISSION_NAME
        )
        self.user_requestor.user_permissions.remove(permission)
        self.user_requestor = User.objects.get(pk=self.user_requestor.pk)
        self.assertFalse(
            self.user_requestor.has_perm(StandingRequest.REQUEST_PERMISSION_NAME)
        )

        # run task
        tasks.validate_requests()

        # validate new state
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        my_revocation = StandingRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)
        self.assertEqual(
            my_revocation.reason, StandingRevocation.Reason.LOST_PERMISSION
        )

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(
            reverse("standingsrequests:manage_revocations_list")
        )
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, "revocations")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # remove standing for alt in game and mark as actioned
        self._remove_standing_for_alt_in_game(self.alt_character_1)
        response = self.app.put(
            reverse("standingsrequests:manage_revocations_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate new state
        my_revocation.refresh_from_db()
        self.assertEqual(my_revocation.action_by, self.user_manager)
        self.assertIsNotNone(my_revocation.action_date)
        self.assertFalse(my_revocation.is_effective)

        # run process standing results task
        self._process_standing_requests()

        # validate final state
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())

    @patch(TASKS_PATH + ".SR_SYNC_BLUE_ALTS_ENABLED", True)
    def test_automatically_create_standing_requests_for_valid_alts(self):
        """
        given user's alt has no standing record
        when regular standing update is run
        then standing record is automatically created for this alt
        """

        # setup
        self._set_standing_for_alt_in_game(self.alt_character_1)

        # run task
        self._process_standing_requests()

        # validate
        my_request = StandingRequest.objects.get(
            contact_id=self.alt_character_1.character_id
        )
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
        self.assertEqual(
            RequestLogEntry.objects.filter(
                action_by__isnull=True,
                requested_for__character_id=self.alt_character_1.character_id,
                requested_by__user=self.user_requestor,
                request_type=RequestLogEntry.RequestType.REQUEST,
                action=RequestLogEntry.Action.CONFIRMED,
            ).count(),
            1,
        )

    @patch(TASKS_PATH + ".SR_SYNC_BLUE_ALTS_ENABLED", True)
    def test_automatically_create_standing_revocation_for_invalid_alts_2(self):
        """
        given user's alt has no standing record
        and alt has standing in game
        when user has no permission
        then standing revocation is automatically created
        and standing is removed after actioned by manager
        and user is notified
        """

        # setup
        alt_id = self.alt_character_1.character_id
        self._set_standing_for_alt_in_game(self.alt_character_1)
        self.member_state.member_characters.remove(self.main_character_1)
        permission = AuthUtils.get_permission_by_name(
            StandingRequest.REQUEST_PERMISSION_NAME
        )
        self.user_requestor.user_permissions.remove(permission)
        self.user_requestor = User.objects.get(pk=self.user_requestor.pk)
        self.assertFalse(
            self.user_requestor.has_perm(StandingRequest.REQUEST_PERMISSION_NAME)
        )

        # run tasks
        self._process_standing_requests()
        tasks.validate_requests()

        # validate new state
        req = StandingRequest.objects.get(contact_id=alt_id)
        self.assertTrue(req.is_effective)
        my_revocation = StandingRevocation.objects.get(contact_id=alt_id)
        self.assertFalse(my_revocation.is_effective)
        self.assertEqual(
            my_revocation.reason, StandingRevocation.Reason.LOST_PERMISSION
        )

        # manager opens manage page
        self.app.set_user(self.user_manager)
        manage_page_1 = self.app.get(reverse("standingsrequests:manage"))
        self.assertEqual(manage_page_1.status_code, 200)
        manage_page_2 = self.app.get(
            reverse("standingsrequests:manage_revocations_list")
        )
        self.assertEqual(manage_page_2.status_code, 200)

        # make sure standing request is visible to manager
        data = self._parse_contacts_data(manage_page_2, key="revocations")
        self.assertSetEqual(set(data.keys()), {alt_id})

        # remove standing for alt in game and mark as actioned
        self._remove_standing_for_alt_in_game(self.alt_character_1)
        response = self.app.put(
            reverse("standingsrequests:manage_revocations_write", args=[alt_id])
        )
        self.assertEqual(response.status_code, 200)

        # validate new state
        my_revocation.refresh_from_db()
        self.assertEqual(my_revocation.action_by, self.user_manager)
        self.assertIsNotNone(my_revocation.action_date)
        self.assertFalse(my_revocation.is_effective)

        # run process standing results task
        self._process_standing_requests()

        # validate final state
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())
        self.assertFalse(StandingRevocation.objects.filter(contact_id=alt_id).exists())
        self.assertTrue(Notification.objects.filter(user=self.user_requestor).exists())
