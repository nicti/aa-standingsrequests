from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils.timezone import now
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import (
    NoSocketsTestCase,
    _generate_token,
    _store_as_Token,
    add_character_to_user,
    add_new_token,
)

from ..core import MainOrganizations
from ..helpers.evecorporation import EveCorporation
from ..models import (
    AbstractStandingsRequest,
    CharacterAffiliation,
    Contact,
    ContactLabel,
    ContactSet,
    StandingRequest,
    StandingRevocation,
)
from .entity_type_ids import CHARACTER_BRUTOR_TYPE_ID, CHARACTER_TYPE_ID
from .my_test_data import (
    TEST_STANDINGS_ALLIANCE_ID,
    create_contacts_set,
    create_entity,
    create_standings_char,
    get_my_test_data,
    load_eve_entities,
)

CORE_PATH = "standingsrequests.core"
MODELS_PATH = "standingsrequests.models"
TEST_USER_NAME = "Peter Parker"
TEST_REQUIRED_SCOPE = "mind_reading.v1"


class TestContactSet(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.character_1001 = create_entity(EveCharacter, 1001)
        load_eve_entities()

    def test_str(self):
        my_set = ContactSet(name="My Set")
        self.assertIsInstance(str(my_set), str)

    @patch(CORE_PATH + ".STR_CORP_IDS", ["2001"])
    @patch(CORE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organisation_matches_corp(self):
        self.assertTrue(MainOrganizations.is_character_a_member(self.character_1001))

    @patch(CORE_PATH + ".STR_CORP_IDS", [])
    @patch(CORE_PATH + ".STR_ALLIANCE_IDS", ["3001"])
    def test_pilot_in_organisation_matches_alliance(self):
        self.assertTrue(MainOrganizations.is_character_a_member(self.character_1001))

    @patch(CORE_PATH + ".STR_CORP_IDS", [])
    @patch(CORE_PATH + ".STR_ALLIANCE_IDS", [3101])
    def test_pilot_in_organisation_doest_not_exist(self):
        self.assertFalse(MainOrganizations.is_character_a_member(self.character_1001))

    @patch(CORE_PATH + ".STR_CORP_IDS", [])
    @patch(CORE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organisation_matches_none(self):
        self.assertFalse(MainOrganizations.is_character_a_member(self.character_1001))


class TestContactSetCreateStanding(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact_set = create_contacts_set()

    def test_can_create_pilot_standing(self):
        obj = Contact.objects.create(
            contact_set=self.contact_set, eve_entity_id=1009, standing=-10
        )
        obj.labels.add(*ContactLabel.objects.all())
        self.assertIsInstance(obj, Contact)
        self.assertEqual(obj.eve_entity_id, 1009)
        self.assertEqual(obj.standing, -10)

    def test_can_create_corp_standing(self):
        obj = Contact.objects.create(
            contact_set=self.contact_set, eve_entity_id=2102, standing=-10
        )
        obj.labels.add(*ContactLabel.objects.all())
        self.assertIsInstance(obj, Contact)
        self.assertEqual(obj.eve_entity_id, 2102)
        self.assertEqual(obj.standing, -10)

    def test_can_create_alliance_standing(self):
        obj = Contact.objects.create(
            contact_set=self.contact_set, eve_entity_id=3001, standing=5
        )
        obj.labels.add(*ContactLabel.objects.all())
        self.assertIsInstance(obj, Contact)
        self.assertEqual(obj.eve_entity_id, 3001)
        self.assertEqual(obj.standing, 5)


@patch(
    MODELS_PATH + ".SR_REQUIRED_SCOPES",
    {"Member": [TEST_REQUIRED_SCOPE], "Blue": [], "": []},
)
@patch(CORE_PATH + ".STR_ALLIANCE_IDS", [TEST_STANDINGS_ALLIANCE_ID])
class TestContactSetGenerateStandingRequestsForBlueAlts(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = AuthUtils.create_member(TEST_USER_NAME)
        create_standings_char()
        cls.contacts_set = create_contacts_set()

    def test_should_create_new_request_for_blue_alt(self):
        # given
        alt_id = 1010
        alt = create_entity(EveCharacter, alt_id)
        add_character_to_user(self.user, alt, scopes=["dummy"])
        # when
        self.contacts_set.generate_standing_requests_for_blue_alts()
        # then
        request = StandingRequest.objects.get(contact_id=alt_id)
        self.assertTrue(request.is_effective)
        self.assertEqual(request.user, self.user)
        self.assertEqual(request.contact_id, 1010)
        self.assertEqual(request.is_effective, True)
        self.assertAlmostEqual((now() - request.request_date).seconds, 0, delta=30)
        self.assertAlmostEqual((now() - request.action_date).seconds, 0, delta=30)
        self.assertAlmostEqual((now() - request.effective_date).seconds, 0, delta=30)

    def test_should_not_create_requests_for_blue_alt_if_request_already_exists(self):
        # given
        alt_id = 1010
        alt = create_entity(EveCharacter, alt_id)
        add_character_to_user(self.user, alt, scopes=["dummy"])
        req = StandingRequest.objects.get_or_create_2(
            self.user,
            alt_id,
            StandingRequest.ContactType.CHARACTER,
        )
        # when
        self.contacts_set.generate_standing_requests_for_blue_alts()
        # then
        req.refresh_from_db()
        self.assertFalse(req.is_effective)

    def test_should_not_create_requests_for_non_blue_alts(self):
        # given
        alt_id = 1009
        alt = create_entity(EveCharacter, alt_id)
        add_character_to_user(self.user, alt, scopes=["dummy"])
        # when
        self.contacts_set.generate_standing_requests_for_blue_alts()
        # then
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())

    def test_should_not_create_requests_for_alts_in_organization(self):
        # given
        alt_id = 1002
        main = create_entity(EveCharacter, alt_id)
        add_character_to_user(self.user, main, is_main=True, scopes=["dummy"])
        # when
        self.contacts_set.generate_standing_requests_for_blue_alts()
        # then
        self.assertFalse(StandingRequest.objects.filter(contact_id=alt_id).exists())


class TestAbstractStandingsRequest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ContactSet.objects.all().delete()
        create_contacts_set()
        cls.user_requestor = User.objects.create_user(
            "Roger Requestor", "rr@example.com", "password"
        )

    def test_should_say_standing_request(self):
        # given
        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        # then
        self.assertTrue(my_request.is_standing_request)
        self.assertFalse(my_request.is_standing_revocation)

    def test_should_say_standing_revocation(self):
        # given
        my_request = StandingRevocation(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        # then
        self.assertFalse(my_request.is_standing_request)
        self.assertTrue(my_request.is_standing_revocation)


class TestStandingRequest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ContactSet.objects.all().delete()
        create_contacts_set()
        cls.user_manager = User.objects.create_user(
            "Mike Manager", "mm@example.com", "password"
        )
        cls.user_requestor = User.objects.create_user(
            "Roger Requestor", "rr@example.com", "password"
        )

    def test_is_standing_satisfied(self):
        class MyStandingRequest(AbstractStandingsRequest):
            EXPECT_STANDING_LTEQ = 5.0
            EXPECT_STANDING_GTEQ = 0.0

        self.assertTrue(MyStandingRequest.is_standing_satisfied(5))
        self.assertTrue(MyStandingRequest.is_standing_satisfied(0))
        self.assertFalse(MyStandingRequest.is_standing_satisfied(-10))
        self.assertFalse(MyStandingRequest.is_standing_satisfied(10))
        self.assertFalse(MyStandingRequest.is_standing_satisfied(None))

    def test_check_standing_satisfied_check_only(self):
        my_request = StandingRequest(
            user=self.user_requestor, contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
        )
        self.assertTrue(my_request.evaluate_effective_standing(check_only=True))

        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        self.assertTrue(my_request.evaluate_effective_standing(check_only=True))

        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1003,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        self.assertTrue(my_request.evaluate_effective_standing(check_only=True))

        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1005,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        self.assertFalse(my_request.evaluate_effective_standing(check_only=True))

        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1009,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        self.assertFalse(my_request.evaluate_effective_standing(check_only=True))

    def test_check_standing_satisfied_no_standing(self):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor, contact_id=1999, contact_type_id=CHARACTER_TYPE_ID
        )
        self.assertFalse(my_request.evaluate_effective_standing(check_only=True))

    def test_mark_standing_effective_1(self):
        # given
        my_request = StandingRequest.objects.create(
            user=self.user_requestor, contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
        )
        # when
        my_request.mark_effective()
        # then
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsInstance(my_request.effective_date, datetime)

    def test_mark_standing_effective_2(self):
        # given
        my_request = StandingRequest.objects.create(
            user=self.user_requestor, contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
        )
        my_date = now() - timedelta(days=5, hours=4)
        # when
        my_request.mark_effective(date=my_date)
        # then
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertEqual(my_request.effective_date, my_date)

    def test_check_standing_satisfied_and_mark(self):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor, contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
        )
        self.assertTrue(my_request.evaluate_effective_standing())
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsInstance(my_request.effective_date, datetime)

    def test_mark_standing_actioned(self):
        # given
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
        )
        # when
        my_request.mark_actioned(self.user_manager)
        # then
        my_request.refresh_from_db()
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsInstance(my_request.action_date, datetime)
        self.assertEqual(my_request.reason, StandingRequest.Reason.NONE)

    def test_mark_standing_actioned_with_reason(self):
        # given
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
        )
        # when
        my_request.mark_actioned(
            user=self.user_manager, reason=StandingRequest.Reason.STANDING_IN_GAME
        )
        # then
        my_request.refresh_from_db()
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsInstance(my_request.action_date, datetime)
        self.assertEqual(my_request.reason, StandingRequest.Reason.STANDING_IN_GAME)

    def test_check_standing_actioned_timeout_already_effective(self):
        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
        )
        self.assertIsNone(my_request.check_actioned_timeout())

    def test_check_standing_actioned_timeout_not_actioned(self):
        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=False,
        )
        self.assertIsNone(my_request.check_actioned_timeout())

    def test_check_standing_actioned_timeout_no_contact_set(self):
        ContactSet.objects.all().delete()
        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=False,
        )
        self.assertIsNone(my_request.check_actioned_timeout())

    def test_check_standing_actioned_timeout_after_deadline(self):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now() - timedelta(hours=25),
            is_effective=False,
        )
        self.assertEqual(my_request.check_actioned_timeout(), self.user_manager)
        my_request.refresh_from_db()
        self.assertIsNone(my_request.action_by)
        self.assertIsNone(my_request.action_date)

    def test_check_standing_actioned_timeout_before_deadline(self):
        my_request = StandingRequest(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=False,
        )
        self.assertFalse(my_request.check_actioned_timeout())

    def test_reset_to_initial(self):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
            effective_date=now(),
        )
        my_request.reset_to_initial()
        my_request.refresh_from_db()
        self.assertFalse(my_request.is_effective)
        self.assertIsNone(my_request.effective_date)
        self.assertIsNone(my_request.action_by)
        self.assertIsNone(my_request.action_date)

    def test_delete_for_non_effective_dont_add_revocation(self):
        my_request_effective = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=False,
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertFalse(
            StandingRevocation.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )

    def test_delete_for_effective_add_revocation(self):
        my_request_effective = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
            effective_date=now(),
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertTrue(
            StandingRevocation.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )

    def test_delete_for_pending_add_revocation(self):
        my_request_effective = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=False,
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertTrue(
            StandingRevocation.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )

    def test_delete_for_effective_dont_add_another_revocation(self):
        my_request_effective = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
            effective_date=now(),
        )
        StandingRevocation.objects.add_revocation(
            1001, StandingRevocation.ContactType.CHARACTER
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertEqual(
            StandingRevocation.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).count(),
            1,
        )


class TestStandingRequestClassMethods(NoSocketsTestCase):
    @patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODELS_PATH + ".EveCorporation.get_by_id")
    def test_can_request_corporation_standing_good(self, mock_get_corp_by_id):
        """user has tokens for all 3 chars of corp"""
        mock_get_corp_by_id.return_value = EveCorporation(
            **get_my_test_data()["EveCorporationInfo"]["2001"]
        )
        my_user = AuthUtils.create_user("John Doe")
        for character_id, character in get_my_test_data()["EveCharacter"].items():
            if character["corporation_id"] == 2001:
                my_character = EveCharacter.objects.create(**character)
                _store_as_Token(
                    _generate_token(
                        character_id=my_character.character_id,
                        character_name=my_character.character_name,
                        scopes=["publicData"],
                    ),
                    my_user,
                )

        self.assertTrue(StandingRequest.can_request_corporation_standing(2001, my_user))

    @patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODELS_PATH + ".EveCorporation.get_by_id")
    def test_can_request_corporation_standing_incomplete(self, mock_get_corp_by_id):
        """user has tokens for only 2 / 3 chars of corp"""
        mock_get_corp_by_id.return_value = EveCorporation(
            **get_my_test_data()["EveCorporationInfo"]["2001"]
        )
        my_user = AuthUtils.create_user("John Doe")
        for character_id, character in get_my_test_data()["EveCharacter"].items():
            if character_id in [1001, 1002]:
                my_character = EveCharacter.objects.create(**character)
                _store_as_Token(
                    _generate_token(
                        character_id=my_character.character_id,
                        character_name=my_character.character_name,
                        scopes=["publicData"],
                    ),
                    my_user,
                )

        self.assertFalse(
            StandingRequest.can_request_corporation_standing(2001, my_user)
        )

    @patch(
        MODELS_PATH + ".SR_REQUIRED_SCOPES",
        {"Guest": ["publicData", "esi-mail.read_mail.v1"]},
    )
    @patch(MODELS_PATH + ".EveCorporation.get_by_id")
    def test_can_request_corporation_standing_wrong_scope(self, mock_get_corp_by_id):
        """user has tokens for only 3 / 3 chars of corp, but wrong scopes"""
        mock_get_corp_by_id.return_value = EveCorporation(
            **(get_my_test_data()["EveCorporationInfo"]["2001"])
        )
        my_user = AuthUtils.create_user("John Doe")
        for character_id, character in get_my_test_data()["EveCharacter"].items():
            if character_id in [1001, 1002]:
                my_character = EveCharacter.objects.create(**character)
                _store_as_Token(
                    _generate_token(
                        character_id=my_character.character_id,
                        character_name=my_character.character_name,
                        scopes=["publicData"],
                    ),
                    my_user,
                )

        self.assertFalse(
            StandingRequest.can_request_corporation_standing(2001, my_user)
        )

    @patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODELS_PATH + ".EveCorporation.get_by_id")
    def test_can_request_corporation_standing_good_another_user(
        self, mock_get_corp_by_id
    ):
        """there are tokens for all 3 chars of corp, but for another user"""
        mock_get_corp_by_id.return_value = EveCorporation(
            **get_my_test_data()["EveCorporationInfo"]["2001"]
        )
        user_1 = AuthUtils.create_user("John Doe")
        for character_id, character in get_my_test_data()["EveCharacter"].items():
            if character["corporation_id"] == 2001:
                my_character = EveCharacter.objects.create(**character)
                add_character_to_user(
                    user_1,
                    my_character,
                    scopes=["publicData"],
                )

        user_2 = AuthUtils.create_user("Mike Myers")
        self.assertFalse(StandingRequest.can_request_corporation_standing(2001, user_2))


class TestStandingRequestGetRequiredScopesForState(NoSocketsTestCase):
    @patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_scopes_if_defined_for_state(self):
        expected = ["abc"]
        self.assertListEqual(
            StandingRequest.get_required_scopes_for_state("member"), expected
        )

    @patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_empty_list_if_not_defined_for_state(self):
        expected = []
        self.assertListEqual(
            StandingRequest.get_required_scopes_for_state("guest"), expected
        )

    @patch(MODELS_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_empty_list_if_state_is_note(self):
        expected = []
        self.assertListEqual(
            StandingRequest.get_required_scopes_for_state(None), expected
        )


@patch(MODELS_PATH + ".StandingRequest.get_required_scopes_for_state")
class TestStandingsManagerHasRequiredScopesForRequest(NoSocketsTestCase):
    def test_true_when_user_has_required_scopes(
        self, mock_get_required_scopes_for_state
    ):
        mock_get_required_scopes_for_state.return_value = ["abc"]
        user = AuthUtils.create_member("Bruce Wayne")
        character = AuthUtils.add_main_character_2(
            user=user,
            name="Batman",
            character_id=2099,
            corp_id=2001,
            corp_name="Wayne Tech",
        )
        add_new_token(user, character, ["abc"])
        self.assertTrue(StandingRequest.has_required_scopes_for_request(character))

    def test_false_when_user_does_not_have_required_scopes(
        self, mock_get_required_scopes_for_state
    ):
        mock_get_required_scopes_for_state.return_value = ["xyz"]
        user = AuthUtils.create_member("Bruce Wayne")
        character = AuthUtils.add_main_character_2(
            user=user,
            name="Batman",
            character_id=2099,
            corp_id=2001,
            corp_name="Wayne Tech",
        )
        add_new_token(user, character, ["abc"])
        self.assertFalse(StandingRequest.has_required_scopes_for_request(character))

    def test_false_when_user_state_can_not_be_determinded(
        self, mock_get_required_scopes_for_state
    ):
        mock_get_required_scopes_for_state.return_value = ["abc"]
        character = create_entity(EveCharacter, 1002)
        self.assertFalse(StandingRequest.has_required_scopes_for_request(character))


class TestCharacterAffiliation(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eve_entities()

    def test_get_character_name_exists(self):
        my_assoc = CharacterAffiliation.objects.create(
            character_id=1002, corporation_id=2001
        )
        self.assertEqual(my_assoc.character_name, "Peter Parker")

    def test_get_character_name_not_exists(self):
        character = EveEntity.objects.create(id=1999)
        my_assoc = CharacterAffiliation.objects.create(
            character=character, corporation_id=2001
        )
        self.assertIsNone(my_assoc.character_name)
