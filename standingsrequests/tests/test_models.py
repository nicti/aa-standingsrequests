from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils

from app_utils.testing import (
    NoSocketsTestCase,
    _generate_token,
    _store_as_Token,
    add_character_to_user,
    add_new_token,
)

from ..helpers.evecorporation import EveCorporation
from ..models import (
    AbstractContact,
    AbstractStandingsRequest,
    AllianceContact,
    CharacterAssociation,
    CharacterContact,
    ContactLabel,
    ContactSet,
    CorporationContact,
    EveEntity,
    StandingRequest,
    StandingRevocation,
)
from .entity_type_ids import (
    ALLIANCE_TYPE_ID,
    CHARACTER_ACHURA_TYPE_ID,
    CHARACTER_BRUTOR_TYPE_ID,
    CHARACTER_CIVRE_TYPE_ID,
    CHARACTER_DETEIS_TYPE_ID,
    CHARACTER_DRIFTER_TYPE_ID,
    CHARACTER_GALLENTE_TYPE_ID,
    CHARACTER_INTAKI_TYPE_ID,
    CHARACTER_JIN_MEI_TYPE_ID,
    CHARACTER_KHANID_TYPE_ID,
    CHARACTER_MODIFIER_TYPE_ID,
    CHARACTER_NI_KUNNI_TYPE_ID,
    CHARACTER_SEBIESTOR_TYPE_ID,
    CHARACTER_STATIC_TYPE_ID,
    CHARACTER_TYPE_ID,
    CHARACTER_VHEROKIOR_TYPE_ID,
    CORPORATION_TYPE_ID,
)
from .my_test_data import (
    TEST_STANDINGS_ALLIANCE_ID,
    create_contacts_set,
    create_entity,
    create_standings_char,
    get_entity_name,
    get_my_test_data,
)

MODULE_PATH = "standingsrequests.models"
TEST_USER_NAME = "Peter Parker"
TEST_REQUIRED_SCOPE = "mind_reading.v1"


class TestContactSet(NoSocketsTestCase):
    def setUp(self):
        ContactSet.objects.all().delete()

    def test_str(self):
        my_set = ContactSet(name="My Set")
        self.assertIsInstance(str(my_set), str)

    def test_get_contact_by_id_pilot(self):
        my_set = ContactSet.objects.create(name="Dummy Set")
        CharacterContact.objects.create(
            contact_set=my_set, contact_id=1001, name="Bruce Wayne", standing=5
        )
        # look for existing pilot
        obj = my_set.get_contact_by_id(1001, CHARACTER_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing pilot
        with self.assertRaises(CharacterContact.DoesNotExist):
            my_set.get_contact_by_id(1999, CHARACTER_TYPE_ID)

    def test_get_contact_by_id_corporation(self):
        my_set = ContactSet.objects.create(name="Dummy Set")
        CorporationContact.objects.create(
            contact_set=my_set, contact_id=2001, name="Dummy Corp 1", standing=5
        )
        # look for existing corp
        obj = my_set.get_contact_by_id(2001, CORPORATION_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing corp
        with self.assertRaises(CorporationContact.DoesNotExist):
            my_set.get_contact_by_id(2999, CORPORATION_TYPE_ID)

    def test_get_contact_by_id_alliance(self):
        my_set = ContactSet.objects.create(name="Dummy Set")
        AllianceContact.objects.create(
            contact_set=my_set, contact_id=3001, name="Dummy Alliance 1", standing=5
        )
        # look for existing alliance
        obj = my_set.get_contact_by_id(3001, ALLIANCE_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing alliance
        with self.assertRaises(AllianceContact.DoesNotExist):
            my_set.get_contact_by_id(3999, ALLIANCE_TYPE_ID)

    def test_get_contact_by_id_other_type(self):
        my_set = ContactSet.objects.create(name="Dummy Set")
        AllianceContact.objects.create(
            contact_set=my_set, contact_id=3001, name="Dummy Alliance 1", standing=5
        )
        with self.assertRaises(ObjectDoesNotExist):
            my_set.get_contact_by_id(9999, 99)

    @patch(MODULE_PATH + ".STR_CORP_IDS", ["2001"])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organisation_matches_corp(self):
        character = create_entity(EveCharacter, 1001)
        self.assertTrue(ContactSet.is_character_in_organisation(character))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", ["3001"])
    def test_pilot_in_organisation_matches_alliance(self):
        character = create_entity(EveCharacter, 1001)
        self.assertTrue(ContactSet.is_character_in_organisation(character))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [3001])
    def test_pilot_in_organisation_doest_not_exist(self):
        character = create_entity(EveCharacter, 1007)
        self.assertFalse(ContactSet.is_character_in_organisation(character))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organisation_matches_none(self):
        character = create_entity(EveCharacter, 1001)
        self.assertFalse(ContactSet.is_character_in_organisation(character))


class TestContactSetCreateStanding(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact_set = create_contacts_set()

    def test_can_create_pilot_standing(self):
        obj = self.contact_set.create_contact(
            contact_type_id=CHARACTER_TYPE_ID,
            name="Lex Luthor",
            contact_id=1009,
            standing=-10,
            labels=ContactLabel.objects.all(),
        )
        self.assertIsInstance(obj, CharacterContact)
        self.assertEqual(obj.name, "Lex Luthor")
        self.assertEqual(obj.contact_id, 1009)
        self.assertEqual(obj.standing, -10)

    def test_can_create_corp_standing(self):
        obj = self.contact_set.create_contact(
            contact_type_id=CORPORATION_TYPE_ID,
            name="Lexcorp",
            contact_id=2102,
            standing=-10,
            labels=ContactLabel.objects.all(),
        )
        self.assertIsInstance(obj, CorporationContact)
        self.assertEqual(obj.name, "Lexcorp")
        self.assertEqual(obj.contact_id, 2102)
        self.assertEqual(obj.standing, -10)

    def test_can_create_alliance_standing(self):
        obj = self.contact_set.create_contact(
            contact_type_id=ALLIANCE_TYPE_ID,
            name="Wayne Enterprises",
            contact_id=3001,
            standing=5,
            labels=ContactLabel.objects.all(),
        )
        self.assertIsInstance(obj, AllianceContact)
        self.assertEqual(obj.name, "Wayne Enterprises")
        self.assertEqual(obj.contact_id, 3001)
        self.assertEqual(obj.standing, 5)


@patch(
    MODULE_PATH + ".SR_REQUIRED_SCOPES",
    {"Member": [TEST_REQUIRED_SCOPE], "Blue": [], "": []},
)
@patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [TEST_STANDINGS_ALLIANCE_ID])
class TestContactSetGenerateStandingRequestsForBlueAlts(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = AuthUtils.create_member(TEST_USER_NAME)

    def setUp(self):
        create_standings_char()
        self.contacts_set = create_contacts_set()
        StandingRequest.objects.all().delete()

    def test_creates_new_request_for_blue_alt(self):
        alt_id = 1010
        alt = create_entity(EveCharacter, alt_id)
        add_character_to_user(self.user, alt, scopes=["dummy"])

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertTrue(StandingRequest.objects.has_effective_request(alt_id))
        request = StandingRequest.objects.first()
        self.assertEqual(request.user, self.user)
        self.assertEqual(request.contact_id, 1010)
        self.assertEqual(request.is_effective, True)
        self.assertAlmostEqual((now() - request.request_date).seconds, 0, delta=30)
        self.assertAlmostEqual((now() - request.action_date).seconds, 0, delta=30)
        self.assertAlmostEqual((now() - request.effective_date).seconds, 0, delta=30)

    def test_does_not_create_requests_for_blue_alt_if_request_already_exists(self):
        alt_id = 1010
        alt = create_entity(EveCharacter, alt_id)
        add_character_to_user(self.user, alt, scopes=["dummy"])
        StandingRequest.objects.add_request(
            self.user,
            alt_id,
            StandingRequest.CHARACTER_CONTACT_TYPE,
        )

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertFalse(StandingRequest.objects.has_effective_request(alt_id))

    def test_does_not_create_requests_for_non_blue_alts(self):
        alt_id = 1009
        alt = create_entity(EveCharacter, alt_id)
        add_character_to_user(self.user, alt, scopes=["dummy"])

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertFalse(StandingRequest.objects.has_effective_request(alt_id))

    def test_does_not_create_requests_for_alts_in_organization(self):
        alt_id = 1002
        main = create_entity(EveCharacter, alt_id)
        add_character_to_user(self.user, main, is_main=True, scopes=["dummy"])

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertFalse(StandingRequest.objects.has_effective_request(alt_id))


class TestAbstractStanding(TestCase):
    def test_get_contact_type(self):
        with self.assertRaises(NotImplementedError):
            AbstractContact.get_contact_type_id()


class TestPilotStanding(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(CharacterContact.get_contact_type_id(), CHARACTER_TYPE_ID)

    def test_is_pilot(self):
        self.assertTrue(CharacterContact.is_character(CHARACTER_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_NI_KUNNI_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_CIVRE_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_DETEIS_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_GALLENTE_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_INTAKI_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_SEBIESTOR_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_BRUTOR_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_STATIC_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_MODIFIER_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_ACHURA_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_JIN_MEI_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_KHANID_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_VHEROKIOR_TYPE_ID))
        self.assertTrue(CharacterContact.is_character(CHARACTER_DRIFTER_TYPE_ID))

        self.assertFalse(CharacterContact.is_character(CORPORATION_TYPE_ID))
        self.assertFalse(CharacterContact.is_character(ALLIANCE_TYPE_ID))
        self.assertFalse(CharacterContact.is_character(1))
        self.assertFalse(CharacterContact.is_character(None))
        self.assertFalse(CharacterContact.is_character(-1))
        self.assertFalse(CharacterContact.is_character(0))


class TestCorpStanding(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(CorporationContact.get_contact_type_id(), CORPORATION_TYPE_ID)

    def test_is_pilot(self):
        self.assertTrue(CorporationContact.is_corporation(CORPORATION_TYPE_ID))
        self.assertFalse(CorporationContact.is_corporation(CHARACTER_TYPE_ID))
        self.assertFalse(CorporationContact.is_corporation(ALLIANCE_TYPE_ID))
        self.assertFalse(CorporationContact.is_corporation(1))
        self.assertFalse(CorporationContact.is_corporation(None))
        self.assertFalse(CorporationContact.is_corporation(-1))
        self.assertFalse(CorporationContact.is_corporation(0))


class TestAllianceStanding(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(AllianceContact.get_contact_type_id(), ALLIANCE_TYPE_ID)

    def test_is_pilot(self):
        self.assertTrue(AllianceContact.is_alliance(ALLIANCE_TYPE_ID))
        self.assertFalse(AllianceContact.is_alliance(CHARACTER_TYPE_ID))
        self.assertFalse(AllianceContact.is_alliance(CORPORATION_TYPE_ID))
        self.assertFalse(AllianceContact.is_alliance(1))
        self.assertFalse(AllianceContact.is_alliance(None))
        self.assertFalse(AllianceContact.is_alliance(-1))
        self.assertFalse(AllianceContact.is_alliance(0))


class TestStandingsRequest(TestCase):
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

    def test_mark_standing_effective(self):
        my_request = StandingRequest.objects.create(
            user=self.user_requestor, contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
        )

        my_request.mark_effective()
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsInstance(my_request.effective_date, datetime)

        my_date = now() - timedelta(days=5, hours=4)
        my_request.mark_effective(date=my_date)
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
        my_request = StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
        )
        my_request.mark_actioned(self.user_manager)
        my_request.refresh_from_db()
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsInstance(my_request.action_date, datetime)

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
            1001, StandingRevocation.CHARACTER_CONTACT_TYPE
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


class TestStandingsRequestClassMethods(NoSocketsTestCase):
    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODULE_PATH + ".EveCorporation.get_by_id")
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

    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODULE_PATH + ".EveCorporation.get_by_id")
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
        MODULE_PATH + ".SR_REQUIRED_SCOPES",
        {"Guest": ["publicData", "esi-mail.read_mail.v1"]},
    )
    @patch(MODULE_PATH + ".EveCorporation.get_by_id")
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

    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODULE_PATH + ".EveCorporation.get_by_id")
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


class TestStandingsRequestGetRequiredScopesForState(NoSocketsTestCase):
    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_scopes_if_defined_for_state(self):
        expected = ["abc"]
        self.assertListEqual(
            StandingRequest.get_required_scopes_for_state("member"), expected
        )

    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_empty_list_if_not_defined_for_state(self):
        expected = []
        self.assertListEqual(
            StandingRequest.get_required_scopes_for_state("guest"), expected
        )

    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_empty_list_if_state_is_note(self):
        expected = []
        self.assertListEqual(
            StandingRequest.get_required_scopes_for_state(None), expected
        )


@patch(MODULE_PATH + ".StandingRequest.get_required_scopes_for_state")
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


class TestCharacterAssociation(TestCase):
    def setUp(self):
        ContactSet.objects.all().delete()
        EveEntity.objects.all().delete()
        CharacterAssociation.objects.all().delete()

    @patch(MODULE_PATH + ".EveEntity")
    def test_get_character_name_exists(self, mock_EveEntity):
        mock_EveEntity.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1002, main_character_id=1001)
        self.assertEqual(my_assoc.character_name, "Peter Parker")

    @patch(MODULE_PATH + ".EveEntity")
    def test_get_character_name_not_exists(self, mock_EveEntity):
        mock_EveEntity.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1999, main_character_id=1001)
        self.assertIsNone(my_assoc.character_name)

    @patch(MODULE_PATH + ".EveEntity")
    def test_get_main_character_name_exists(self, mock_EveEntity):
        mock_EveEntity.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1002, main_character_id=1001)
        self.assertEqual(my_assoc.main_character_name, "Bruce Wayne")

    @patch(MODULE_PATH + ".EveEntity")
    def test_get_main_character_name_not_exists(self, mock_EveEntity):
        mock_EveEntity.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1002, main_character_id=19999)
        self.assertIsNone(my_assoc.main_character_name)

    @patch(MODULE_PATH + ".EveEntity")
    def test_get_main_character_name_not_defined(self, mock_EveEntity):
        mock_EveEntity.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1002)
        self.assertIsNone(my_assoc.main_character_name)


class TestEveEntity(TestCase):
    def setUp(self):
        ContactSet.objects.all().delete()
        EveEntity.objects.all().delete()

    """
    @patch(MODULE_PATH + '.EveEntityHelper')
    def test_get_names_from_contacts(self, mock_EveEntityHelper):
        mock_EveEntityHelper.get_names.side_effect = \
            get_entity_names

        contact_set = ContactSet.objects.create(
            name='Dummy Pilots Set'
        )
        CharacterContact.objects.create(
            contact_set=contact_set
            contact_id=1001,
            name='Bruce Wayne',
            standing=0
        )
        entities = EveEntity.objects.get_names([1001])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne'
            }
        )
        self.assertListEqual(
            mock_EveEntityHelper.get_names.call_args[0][0],
            []
        )
    """
