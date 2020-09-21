from datetime import timedelta
from unittest.mock import patch, Mock
from allianceauth.notifications.models import Notification
from bravado.exception import HTTPError

from django.utils.timezone import now

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils

from . import add_character_to_user
from .entity_type_ids import (
    CHARACTER_TYPE_ID,
    CORPORATION_TYPE_ID,
)
from ..models import (
    ContactSet,
    CharacterAssociation,
    AbstractStandingsRequest,
    EveEntity,
    CharacterContact,
    StandingRequest,
    StandingRevocation,
)
from .my_test_data import (
    create_entity,
    create_contacts_set,
    create_standings_char,
    esi_post_universe_names,
    esi_get_alliances_alliance_id_contacts,
    esi_get_alliances_alliance_id_contacts_labels,
    esi_post_characters_affiliation,
    TEST_STANDINGS_API_CHARID,
    TEST_STANDINGS_API_CHARNAME,
)
from ..utils import set_test_logger, NoSocketsTestCase

MODULE_PATH = "standingsrequests.managers"
MODULE_PATH_MODELS = "standingsrequests.models"
logger = set_test_logger(MODULE_PATH, __file__)

TEST_USER_NAME = "Peter Parker"


class TestContactSetManager(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = AuthUtils.create_member(TEST_STANDINGS_API_CHARNAME)
        character = create_standings_char()
        add_character_to_user(
            cls.user, character, scopes=["esi-alliances.read_contacts.v1"]
        )

    def setUp(self):
        pass

    @patch(MODULE_PATH_MODELS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
    @patch(MODULE_PATH_MODELS + ".SR_OPERATION_MODE", "alliance")
    @patch(MODULE_PATH + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
    @patch(MODULE_PATH + ".SR_OPERATION_MODE", "alliance")
    @patch("standingsrequests.helpers.esi_fetch._esi_client")
    def test_can_create_new_from_api(self, mock_esi_client):
        mock_Contacts = mock_esi_client.return_value.Contacts
        mock_Contacts.get_alliances_alliance_id_contacts_labels.side_effect = (
            esi_get_alliances_alliance_id_contacts_labels
        )
        mock_Contacts.get_alliances_alliance_id_contacts.side_effect = (
            esi_get_alliances_alliance_id_contacts
        )

        # labels
        contact_set = ContactSet.objects.create_new_from_api()
        labels = set(contact_set.contactlabel_set.values_list("label_id", "name"))
        expected = {(1, "blue"), (2, "green"), (3, "yellow"), (4, "red")}
        self.assertSetEqual(labels, expected)

        # pilots
        pilots = set(
            contact_set.charactercontact_set.values_list("contact_id", "standing")
        )
        expected = {
            (1001, 10),
            (1002, 10),
            (1003, 5),
            (1004, 0.01),
            (1005, 0),
            (1006, 0),
            (1008, -5),
            (1009, -10),
            (1010, 5),
        }
        self.assertSetEqual(pilots, expected)

        # corporations
        corporations = set(
            contact_set.corporationcontact_set.values_list("contact_id", "standing")
        )
        expected = {
            (2003, 5.0),
            (2102, -10.0),
        }
        self.assertSetEqual(corporations, expected)

    @patch(MODULE_PATH_MODELS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
    def test_standings_character_exists(self):
        character = create_standings_char()
        self.assertEqual(ContactSet.standings_character(), character)

    @patch(MODULE_PATH_MODELS + ".STANDINGS_API_CHARID", 1002)
    @patch(MODULE_PATH_MODELS + ".EveCharacter.objects.create_character")
    def test_standings_character_not_exists(self, mock_create_character):
        character, _ = EveCharacter.objects.get_or_create(
            character_id=TEST_STANDINGS_API_CHARID,
            defaults={
                "character_name": TEST_STANDINGS_API_CHARNAME,
                "corporation_id": 2099,
                "corporation_name": "Dummy Corp",
            },
        )
        mock_create_character.return_value = character
        self.assertEqual(ContactSet.standings_character(), character)
        self.assertTrue(
            EveEntity.objects.filter(entity_id=TEST_STANDINGS_API_CHARID).exists()
        )


@patch(MODULE_PATH + ".SR_NOTIFICATIONS_ENABLED", True)
@patch(MODULE_PATH + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH_MODELS + ".STANDINGS_API_CHARID", TEST_STANDINGS_API_CHARID)
@patch(MODULE_PATH_MODELS + ".SR_STANDING_TIMEOUT_HOURS", 24)
@patch(MODULE_PATH + ".notify")
class TestAbstractStandingsRequestProcessRequests(NoSocketsTestCase):
    def setUp(self):
        self.user_manager = AuthUtils.create_user("Mike Manager")
        self.user_requestor = AuthUtils.create_user("Roger Requestor")
        ContactSet.objects.all().delete()
        self.contact_set = create_contacts_set()
        create_standings_char()

    def test_when_pilot_standing_satisfied_in_game_mark_effective_and_inform_user(
        self, mock_notify
    ):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
        )
        StandingRequest.objects.process_requests()
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsNotNone(my_request.action_date)
        self.assertEqual(mock_notify.call_count, 1)
        args, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], self.user_requestor)

    def test_dont_inform_user_when_sr_was_effective_before(self, mock_notify):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
            effective_date=now(),
        )
        StandingRequest.objects.process_requests()
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsNotNone(my_request.action_date)
        self.assertEqual(mock_notify.call_count, 0)

    def test_when_corporation_standing_satisfied_in_game_mark_effective(
        self, mock_notify
    ):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=2003,
            contact_type_id=CORPORATION_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
        )
        StandingRequest.objects.process_requests()
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsNotNone(my_request.effective_date)
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsNotNone(my_request.action_date)
        self.assertTrue(mock_notify.called)

    def test_notify_about_requests_that_are_reset_and_timed_out(self, mock_notify):
        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1008,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now() - timedelta(hours=25),
        )
        StandingRequest.objects.process_requests()
        self.assertEqual(mock_notify.call_count, 2)

    def test_dont_notify_about_requests_that_are_reset_and_not_timed_out(
        self, mock_notify
    ):
        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1008,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now() - timedelta(hours=1),
        )
        StandingRequest.objects.process_requests()
        self.assertEqual(mock_notify.call_count, 0)

    def test_no_action_when_actioned_standing_but_not_in_game_yet(self, mock_notify):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
        )
        self.contact_set.get_contact_by_id(1002, CHARACTER_TYPE_ID).delete()
        StandingRequest.objects.process_requests()
        my_request.refresh_from_db()
        self.assertFalse(my_request.is_effective)
        self.assertIsNone(my_request.effective_date)
        self.assertEqual(mock_notify.call_count, 0)

    def test_raise_exception_when_called_from_abstract_object(self, mock_notify):
        with self.assertRaises(TypeError):
            AbstractStandingsRequest.objects.process_requests()

    def test_pending_request(self, mock_notify):
        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=False,
        )
        self.assertTrue(AbstractStandingsRequest.objects.has_pending_request(1001))

        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
            effective_date=now(),
        )
        self.assertFalse(AbstractStandingsRequest.objects.has_pending_request(1002))

    def test_actioned_request(self, mock_notify):
        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=False,
        )
        self.assertTrue(AbstractStandingsRequest.objects.has_actioned_request(1001))

        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
            effective_date=now(),
        )
        self.assertFalse(AbstractStandingsRequest.objects.has_actioned_request(1002))

        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1003,
            contact_type_id=CHARACTER_TYPE_ID,
        )
        self.assertFalse(AbstractStandingsRequest.objects.has_actioned_request(1003))


@patch(MODULE_PATH_MODELS + ".StandingRequest.can_request_corporation_standing")
class TestStandingsRequestValidateRequests(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_contacts_set()
        cls.user = AuthUtils.create_member("Bruce Wayne")

    def setUp(self):
        StandingRequest.objects.all().delete()

    def test_do_nothing_character_request_is_valid(
        self, mock_can_request_corporation_standing
    ):
        AuthUtils.add_permission_to_user_by_name(
            StandingRequest.REQUEST_PERMISSION_NAME, self.user
        )
        request = StandingRequest.objects.add_request(
            self.user, 1002, StandingRequest.CHARACTER_CONTACT_TYPE
        )

        StandingRequest.objects.validate_requests()
        self.assertTrue(StandingRequest.objects.filter(pk=request.pk).exists())

    def test_create_revocation_if_users_character_has_standing_but_user_no_permission(
        self, mock_can_request_corporation_standing
    ):
        StandingRequest.objects.add_request(
            self.user, 1002, StandingRequest.CHARACTER_CONTACT_TYPE
        )
        StandingRequest.objects.validate_requests()
        self.assertTrue(StandingRevocation.objects.filter(contact_id=1002).exists())

    def test_create_revocation_if_users_corporation_is_missing_apis(
        self, mock_can_request_corporation_standing
    ):
        mock_can_request_corporation_standing.return_value = False
        AuthUtils.add_permission_to_user_by_name(
            StandingRequest.REQUEST_PERMISSION_NAME, self.user
        )
        StandingRequest.objects.add_request(
            self.user, 2001, StandingRequest.CORPORATION_CONTACT_TYPE
        )

        StandingRequest.objects.validate_requests()
        self.assertTrue(StandingRevocation.objects.filter(contact_id=2001).exists())

    def test_keep_corp_standing_request_if_all_apis_recorded(
        self, mock_can_request_corporation_standing
    ):
        mock_can_request_corporation_standing.return_value = True
        AuthUtils.add_permission_to_user_by_name(
            StandingRequest.REQUEST_PERMISSION_NAME, self.user
        )
        request = StandingRequest.objects.add_request(
            self.user, 2001, StandingRequest.CORPORATION_CONTACT_TYPE
        )

        StandingRequest.objects.validate_requests()
        self.assertTrue(StandingRequest.objects.filter(pk=request.pk).exists())


class TestStandingsRequestManager(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_contacts_set()
        cls.user_requestor = AuthUtils.create_member("Bruce Wayne")
        cls.user_manager = AuthUtils.create_user("Mike Manager")

    def setUp(self):
        StandingRequest.objects.all().delete()
        Notification.objects.all().delete()

    def test_add_request_new(self):
        my_request = StandingRequest.objects.add_request(
            self.user_requestor, 1001, StandingRequest.CHARACTER_CONTACT_TYPE
        )
        self.assertIsInstance(my_request, StandingRequest)

    def test_add_request_already_exists(self):
        my_request_1 = StandingRequest.objects.add_request(
            self.user_requestor, 1001, StandingRequest.CHARACTER_CONTACT_TYPE
        )
        my_request_2 = StandingRequest.objects.add_request(
            self.user_requestor, 1001, StandingRequest.CHARACTER_CONTACT_TYPE
        )
        self.assertEqual(my_request_1, my_request_2)

    def test_remove_requests(self):
        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=False,
        )
        StandingRequest.objects.remove_requests(1001)
        self.assertFalse(
            StandingRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertFalse(Notification.objects.filter(user=self.user_requestor).exists())

    def test_pending_requests_empty(self):
        self.assertEqual(StandingRequest.objects.pending_requests().count(), 0)

    def test_pending_requests_normal(self):
        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=False,
        )
        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=True,
        )
        StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1003,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=False,
            action_date=now(),
        )
        result = StandingRequest.objects.pending_requests()
        self.assertEqual(result.count(), 1)


class TestStandingsRevocationManager(NoSocketsTestCase):
    def setUp(self):
        ContactSet.objects.all().delete()
        my_set = ContactSet.objects.create(name="Dummy Set")
        CharacterContact.objects.create(
            contact_set=my_set, contact_id=1001, name="Bruce Wayne", standing=10
        )
        CharacterContact.objects.create(
            contact_set=my_set, contact_id=1002, name="James Gordon", standing=5
        )
        CharacterContact.objects.create(
            contact_set=my_set, contact_id=1003, name="Alfred Pennyworth", standing=0.01
        )
        CharacterContact.objects.create(
            contact_set=my_set, contact_id=1005, name="Clark Kent", standing=0
        )
        CharacterContact.objects.create(
            contact_set=my_set, contact_id=1008, name="Harvey Dent", standing=-5
        )
        CharacterContact.objects.create(
            contact_set=my_set, contact_id=1009, name="Lex Luthor", standing=-10
        )
        self.user_manager = AuthUtils.create_user("Mike Manager")
        self.user_requestor = AuthUtils.create_user("Roger Requestor")

    def test_add_revocation_new(self):
        my_revocation = StandingRevocation.objects.add_revocation(
            1001, StandingRevocation.CHARACTER_CONTACT_TYPE, user=self.user_requestor
        )
        self.assertIsInstance(my_revocation, StandingRevocation)

    def test_add_request_already_exists(self):
        StandingRevocation.objects.add_revocation(
            1001, StandingRevocation.CHARACTER_CONTACT_TYPE
        )
        my_revocation_2 = StandingRevocation.objects.add_revocation(
            1001, StandingRevocation.CHARACTER_CONTACT_TYPE
        )
        self.assertIsNone(my_revocation_2)

    def test_check_standing_satisfied_but_deleted_for_neutral_check_only(self):
        my_revocation = StandingRevocation.objects.add_revocation(
            1999, StandingRevocation.CHARACTER_CONTACT_TYPE
        )
        self.assertTrue(my_revocation.evaluate_effective_standing(check_only=True))

    def test_check_standing_satisfied_but_deleted_for_neutral(self):
        my_revocation = StandingRevocation.objects.add_revocation(
            1999, StandingRevocation.CHARACTER_CONTACT_TYPE
        )
        self.assertTrue(my_revocation.evaluate_effective_standing())
        self.assertTrue(my_revocation.is_effective)


class TestCharacterAssociationsManagerAuth(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = AuthUtils.create_user("Bruce Wayne")

    def setUp(self):
        EveCharacter.objects.all().delete()
        CharacterOwnership.objects.all().delete()
        CharacterAssociation.objects.all().delete()
        EveEntity.objects.all().delete()

    def test_can_update_from_one_character(self):
        my_character = create_entity(EveCharacter, 1001)
        add_character_to_user(self.user, my_character, is_main=True)

        CharacterAssociation.objects.update_from_auth()
        self.assertEqual(CharacterAssociation.objects.count(), 1)
        assoc = CharacterAssociation.objects.first()
        self.assertEqual(assoc.character_id, 1001)
        self.assertEqual(assoc.corporation_id, 2001)
        self.assertEqual(assoc.main_character_id, 1001)
        self.assertEqual(assoc.alliance_id, 3001)
        self.assertEqual(
            EveEntity.objects.get(entity_id=1001).name, my_character.character_name
        )

    def test_can_handle_no_main(self):
        my_character = create_entity(EveCharacter, 1001)
        add_character_to_user(self.user, my_character)

        CharacterAssociation.objects.update_from_auth()
        self.assertEqual(CharacterAssociation.objects.count(), 1)
        assoc = CharacterAssociation.objects.first()
        self.assertEqual(assoc.character_id, 1001)
        self.assertEqual(assoc.corporation_id, 2001)
        self.assertIsNone(assoc.main_character_id)
        self.assertEqual(assoc.alliance_id, 3001)
        self.assertEqual(
            EveEntity.objects.get(entity_id=1001).name, my_character.character_name
        )

    def test_can_handle_no_character_without_alliance(self):
        my_character = create_entity(EveCharacter, 1004)
        add_character_to_user(self.user, my_character)

        CharacterAssociation.objects.update_from_auth()
        self.assertEqual(CharacterAssociation.objects.count(), 1)
        assoc = CharacterAssociation.objects.first()
        self.assertEqual(assoc.character_id, 1004)
        self.assertEqual(assoc.corporation_id, 2003)
        self.assertIsNone(assoc.main_character_id)
        self.assertIsNone(assoc.alliance_id)
        self.assertEqual(
            EveEntity.objects.get(entity_id=1004).name, my_character.character_name
        )


@patch("standingsrequests.helpers.esi_fetch._esi_client")
class TestCharacterAssociationsManagerApi(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_requestor = AuthUtils.create_user("Roger Requestor")
        cls.user_manager = AuthUtils.create_user("Mike Manager")

    def setUp(self):
        EveCharacter.objects.all().delete()
        CharacterOwnership.objects.all().delete()
        CharacterAssociation.objects.all().delete()
        ContactSet.objects.all().delete()

    def test_do_nothing_if_not_set_available(self, mock_esi_client):
        CharacterAssociation.objects.update_from_api()
        self.assertFalse(
            mock_esi_client.return_value.Character.post_characters_affiliation.called
        )

    def test_dont_update_when_not_needed(self, mock_esi_client):
        create_contacts_set()
        CharacterAssociation.objects.update_from_api()
        self.assertFalse(
            mock_esi_client.return_value.Character.post_characters_affiliation.called
        )

    def test_updates_all_contacts_with_expired_cache(self, mock_esi_client):
        mock_esi_client.return_value.Character.post_characters_affiliation.side_effect = (
            esi_post_characters_affiliation
        )

        create_contacts_set()
        expected = [1001, 1002, 1003]
        for x in CharacterAssociation.objects.filter(character_id__in=expected):
            x.updated = now() - timedelta(days=3, hours=1)
            x.save()
        CharacterAssociation.objects.update_from_api()
        self.assertTrue(
            mock_esi_client.return_value.Character.post_characters_affiliation.called
        )
        (
            args,
            kwargs,
        ) = mock_esi_client.return_value.Character.post_characters_affiliation.call_args
        self.assertSetEqual(set(kwargs["characters"]), set(expected))
        self.assertTrue(
            CharacterAssociation.objects.filter(
                character_id__in=expected, updated__gt=now() - timedelta(hours=1)
            ).exists()
        )

    def test_updates_all_unknown_contacts(self, mock_esi_client):
        mock_esi_client.return_value.Character.post_characters_affiliation.side_effect = (
            esi_post_characters_affiliation
        )

        create_contacts_set()
        expected = [1001, 1002, 1003]
        CharacterAssociation.objects.filter(character_id__in=expected).delete()
        CharacterAssociation.objects.update_from_api()
        self.assertTrue(
            mock_esi_client.return_value.Character.post_characters_affiliation.called
        )
        (
            args,
            kwargs,
        ) = mock_esi_client.return_value.Character.post_characters_affiliation.call_args
        self.assertSetEqual(set(kwargs["characters"]), set(expected))
        self.assertTrue(
            CharacterAssociation.objects.filter(character_id__in=expected).exists()
        )

    def test_handle_exception_from_api(self, mock_esi_client):
        mock_esi_client.return_value.Character.post_characters_affiliation.side_effect = HTTPError(
            Mock()
        )

        create_contacts_set()
        expected = [1001, 1002, 1003]
        CharacterAssociation.objects.filter(character_id__in=expected).delete()
        CharacterAssociation.objects.update_from_api()
        self.assertFalse(
            CharacterAssociation.objects.filter(character_id__in=expected).exists()
        )


class TestCharacterAssociationManager(NoSocketsTestCase):
    def setUp(self):
        CharacterAssociation.objects.all().delete()

    def test_get_api_expired_items(self):
        CharacterAssociation.objects.create(character_id=1002, main_character_id=1001)
        my_assoc_expired_1 = CharacterAssociation.objects.create(
            character_id=1003, main_character_id=1001
        )
        my_assoc_expired_1.updated -= timedelta(days=4)
        my_assoc_expired_1.save()
        my_assoc_expired_2 = CharacterAssociation.objects.create(
            character_id=1004, main_character_id=1001
        )
        my_assoc_expired_2.updated -= timedelta(days=5)
        my_assoc_expired_2.save()

        self.assertSetEqual(
            set(CharacterAssociation.objects.get_api_expired_items()),
            {my_assoc_expired_1, my_assoc_expired_2},
        )

    def test_get_api_expired_items_selected(self):
        CharacterAssociation.objects.create(character_id=1002, main_character_id=1001)
        my_assoc_expired_1 = CharacterAssociation.objects.create(
            character_id=1003, main_character_id=1001
        )
        my_assoc_expired_1.updated -= timedelta(days=4)
        my_assoc_expired_1.save()
        my_assoc_expired_2 = CharacterAssociation.objects.create(
            character_id=1004, main_character_id=1001
        )
        my_assoc_expired_2.updated -= timedelta(days=5)
        my_assoc_expired_2.save()

        self.assertSetEqual(
            set(CharacterAssociation.objects.get_api_expired_items(items_in=[1004])),
            {my_assoc_expired_2},
        )


@patch("standingsrequests.helpers.esi_fetch._esi_client")
class TestEveEntityManagerGetName(NoSocketsTestCase):
    def setUp(self):
        ContactSet.objects.all().delete()
        EveEntity.objects.all().delete()

    def test_get_name_from_api_when_table_is_empty(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        self.assertEqual(EveEntity.objects.get_name(1001), "Bruce Wayne")

    def test_get_name_when_exists_in_cache(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        EveEntity.objects.create(entity_id=1001, name="Bruce Wayne")
        self.assertEqual(EveEntity.objects.get_name(1001), "Bruce Wayne")

    def test_get_name_that_not_exists(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        self.assertEqual(EveEntity.objects.get_name(1999), None)

    def test_get_name_when_cache_outdated(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        my_entity = EveEntity.objects.create(entity_id=1001, name="Bruce Wayne")
        my_entity.updated = now() - timedelta(days=31)
        my_entity.save()
        self.assertEqual(EveEntity.objects.get_name(1001), "Bruce Wayne")


@patch("standingsrequests.helpers.esi_fetch._esi_client")
class TestEveEntityManagerGetNames(NoSocketsTestCase):
    def setUp(self):
        EveEntity.objects.all().delete()

    def test_get_names_when_table_is_empty(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        entities = EveEntity.objects.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: "Bruce Wayne",
                1002: "Peter Parker",
            },
        )

    def test_get_names_from_cache(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        EveEntity.objects.create(entity_id=1001, name="Bruce Wayne")
        EveEntity.objects.create(entity_id=1002, name="Peter Parker")
        entities = EveEntity.objects.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: "Bruce Wayne",
                1002: "Peter Parker",
            },
        )

    def test_get_names_from_cache_and_api(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        EveEntity.objects.create(entity_id=1001, name="Bruce Wayne")
        entities = EveEntity.objects.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: "Bruce Wayne",
                1002: "Peter Parker",
            },
        )

    def test_get_names_from_expired_cache_and_api(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        EveEntity.objects.create(entity_id=1001, name="Bruce Wayne")
        EveEntity.objects.filter(entity_id=1001).update(
            updated=now() - timedelta(days=31)
        )
        entities = EveEntity.objects.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: "Bruce Wayne",
                1002: "Peter Parker",
            },
        )

    def test_get_names_that_dont_exist(self, mock_esi_client):
        mock_esi_client.return_value.Universe.post_universe_names.side_effect = (
            esi_post_universe_names
        )
        entities = EveEntity.objects.get_names([1999])
        self.assertDictEqual(entities, dict())


class TestEveEntityManager(NoSocketsTestCase):
    def setUp(self):
        ContactSet.objects.all().delete()
        EveEntity.objects.all().delete()

    def test_update_name(self):
        my_entity = EveEntity.objects.create(entity_id=1001, name="Bruce Wayne")
        EveEntity.objects.update_name(1001, "Batman", EveEntity.CATEGORY_CHARACTER)
        my_entity.refresh_from_db()
        self.assertEqual(my_entity.name, "Batman")
        self.assertEqual(my_entity.category, EveEntity.CATEGORY_CHARACTER)
