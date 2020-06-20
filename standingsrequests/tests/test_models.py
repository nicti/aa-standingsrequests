from datetime import timedelta, datetime
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.tests.auth_utils import AuthUtils

from .entity_type_ids import (
    ALLIANCE_TYPE_ID,
    CHARACTER_TYPE_ID,
    CORPORATION_TYPE_ID,
    CHARACTER_NI_KUNNI_TYPE_ID,
    CHARACTER_CIVRE_TYPE_ID,
    CHARACTER_DETEIS_TYPE_ID,
    CHARACTER_GALLENTE_TYPE_ID,
    CHARACTER_INTAKI_TYPE_ID,
    CHARACTER_SEBIESTOR_TYPE_ID,
    CHARACTER_BRUTOR_TYPE_ID,
    CHARACTER_STATIC_TYPE_ID,
    CHARACTER_MODIFIER_TYPE_ID,
    CHARACTER_ACHURA_TYPE_ID,
    CHARACTER_JIN_MEI_TYPE_ID,
    CHARACTER_KHANID_TYPE_ID,
    CHARACTER_VHEROKIOR_TYPE_ID,
    CHARACTER_DRIFTER_TYPE_ID,
)
from . import add_new_token, _generate_token, _store_as_Token, add_character_to_user
from .my_test_data import (
    create_contacts_set,
    get_entity_name,
    create_entity,
    get_my_test_data,
    create_standings_char,
    TEST_STANDINGS_ALLIANCE_ID,
)

from ..models import (
    AbstractStanding,
    AllianceStanding,
    CharacterAssociation,
    ContactLabel,
    ContactSet,
    CorpStanding,
    EveNameCache,
    PilotStanding,
    StandingsRequest,
    StandingsRevocation,
)
from ..utils import set_test_logger, NoSocketsTestCase


MODULE_PATH = "standingsrequests.models"
logger = set_test_logger(MODULE_PATH, __file__)

TEST_USER_NAME = "Peter Parker"
TEST_REQUIRED_SCOPE = "mind_reading.v1"


class TestContactSet(NoSocketsTestCase):
    def setUp(self):
        ContactSet.objects.all().delete()

    def test_str(self):
        my_set = ContactSet(name="My Set")
        self.assertIsInstance(str(my_set), str)

    def test_get_standing_for_id_pilot(self):
        my_set = ContactSet.objects.create(name="Dummy Set")
        PilotStanding.objects.create(
            contact_set=my_set, contact_id=1001, name="Bruce Wayne", standing=5
        )
        # look for existing pilot
        obj = my_set.get_standing_for_id(1001, CHARACTER_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing pilot
        with self.assertRaises(PilotStanding.DoesNotExist):
            my_set.get_standing_for_id(1999, CHARACTER_TYPE_ID)

    def test_get_standing_for_id_corporation(self):
        my_set = ContactSet.objects.create(name="Dummy Set")
        CorpStanding.objects.create(
            contact_set=my_set, contact_id=2001, name="Dummy Corp 1", standing=5
        )
        # look for existing corp
        obj = my_set.get_standing_for_id(2001, CORPORATION_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing corp
        with self.assertRaises(CorpStanding.DoesNotExist):
            my_set.get_standing_for_id(2999, CORPORATION_TYPE_ID)

    def test_get_standing_for_id_alliance(self):
        my_set = ContactSet.objects.create(name="Dummy Set")
        AllianceStanding.objects.create(
            contact_set=my_set, contact_id=3001, name="Dummy Alliance 1", standing=5
        )
        # look for existing alliance
        obj = my_set.get_standing_for_id(3001, ALLIANCE_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing alliance
        with self.assertRaises(AllianceStanding.DoesNotExist):
            my_set.get_standing_for_id(3999, ALLIANCE_TYPE_ID)

    def test_get_standing_for_id_other_type(self):
        my_set = ContactSet.objects.create(name="Dummy Set")
        AllianceStanding.objects.create(
            contact_set=my_set, contact_id=3001, name="Dummy Alliance 1", standing=5
        )
        with self.assertRaises(ObjectDoesNotExist):
            my_set.get_standing_for_id(9999, 99)

    @patch(MODULE_PATH + ".STR_CORP_IDS", ["2001"])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organisation_matches_corp(self):
        create_entity(EveCharacter, 1001)
        self.assertTrue(ContactSet.pilot_in_organisation(1001))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", ["3001"])
    def test_pilot_in_organisation_matches_alliance(self):
        create_entity(EveCharacter, 1001)
        self.assertTrue(ContactSet.pilot_in_organisation(1001))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organisation_doest_not_exist(self):
        self.assertFalse(ContactSet.pilot_in_organisation(1999))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organisation_matches_none(self):
        create_entity(EveCharacter, 1001)
        self.assertFalse(ContactSet.pilot_in_organisation(1001))


class TestContactSetCreateStanding(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact_set = create_contacts_set()

    def test_can_create_pilot_standing(self):
        obj = self.contact_set.create_standing(
            contact_type_id=CHARACTER_TYPE_ID,
            name="Lex Luthor",
            contact_id=1009,
            standing=-10,
            labels=ContactLabel.objects.all(),
        )
        self.assertIsInstance(obj, PilotStanding)
        self.assertEqual(obj.name, "Lex Luthor")
        self.assertEqual(obj.contact_id, 1009)
        self.assertEqual(obj.standing, -10)

    def test_can_create_corp_standing(self):
        obj = self.contact_set.create_standing(
            contact_type_id=CORPORATION_TYPE_ID,
            name="Lexcorp",
            contact_id=2102,
            standing=-10,
            labels=ContactLabel.objects.all(),
        )
        self.assertIsInstance(obj, CorpStanding)
        self.assertEqual(obj.name, "Lexcorp")
        self.assertEqual(obj.contact_id, 2102)
        self.assertEqual(obj.standing, -10)

    def test_can_create_alliance_standing(self):
        obj = self.contact_set.create_standing(
            contact_type_id=ALLIANCE_TYPE_ID,
            name="Wayne Enterprises",
            contact_id=3001,
            standing=5,
            labels=ContactLabel.objects.all(),
        )
        self.assertIsInstance(obj, AllianceStanding)
        self.assertEqual(obj.name, "Wayne Enterprises")
        self.assertEqual(obj.contact_id, 3001)
        self.assertEqual(obj.standing, 5)


@patch(
    "standingsrequests.models.STR_ALLIANCE_IDS", [str(TEST_STANDINGS_ALLIANCE_ID)],
)
@patch(
    "standingsrequests.models.SR_REQUIRED_SCOPES",
    {"Member": [TEST_REQUIRED_SCOPE], "Blue": [], "": []},
)
class TestContactSetGenerateStandingRequestsForBlueAlts(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = AuthUtils.create_member(TEST_USER_NAME)

    def setUp(self):
        create_standings_char()
        self.contacts_set = create_contacts_set()
        StandingsRequest.objects.all().delete()

    def test_creates_new_request_for_blue_alt(self):
        alt = create_entity(EveCharacter, 1010)
        add_character_to_user(self.user, alt, scopes=[TEST_REQUIRED_SCOPE])

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertEqual(StandingsRequest.objects.count(), 1)
        request = StandingsRequest.objects.first()
        self.assertEqual(request.user, self.user)
        self.assertEqual(request.contact_id, 1010)
        self.assertEqual(request.is_effective, True)
        self.assertAlmostEqual((now() - request.request_date).seconds, 0, delta=30)
        self.assertAlmostEqual((now() - request.action_date).seconds, 0, delta=30)
        self.assertAlmostEqual((now() - request.effective_date).seconds, 0, delta=30)

    def test_does_not_create_requests_for_blue_alt_if_request_already_exists(self):
        alt = create_entity(EveCharacter, 1010)
        add_character_to_user(self.user, alt, scopes=[TEST_REQUIRED_SCOPE])
        StandingsRequest.objects.add_request(
            self.user,
            alt.character_id,
            PilotStanding.get_contact_type_id(alt.character_id),
        )

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertEqual(StandingsRequest.objects.count(), 1)

    def test_does_not_create_requests_for_non_blue_alts(self):
        alt = create_entity(EveCharacter, 1009)
        add_character_to_user(self.user, alt, scopes=[TEST_REQUIRED_SCOPE])

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertEqual(StandingsRequest.objects.count(), 0)

    def test_does_not_create_requests_for_alts_in_organization(self):
        main = create_entity(EveCharacter, 1002)
        add_character_to_user(
            self.user, main, is_main=True, scopes=[TEST_REQUIRED_SCOPE]
        )

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertEqual(StandingsRequest.objects.count(), 0)

    def test_does_not_create_requests_for_alts_without_matching_scopes(self):
        user = AuthUtils.create_member("John Doe")
        alt = create_entity(EveCharacter, 1010)
        add_character_to_user(user, alt)

        self.contacts_set.generate_standing_requests_for_blue_alts()

        self.assertEqual(StandingsRequest.objects.count(), 0)


class TestAbstractStanding(TestCase):
    def test_get_contact_type(self):
        with self.assertRaises(NotImplementedError):
            AbstractStanding.get_contact_type_id(42)


class TestPilotStanding(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(PilotStanding.get_contact_type_id(1001), CHARACTER_TYPE_ID)

    def test_is_pilot(self):
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_NI_KUNNI_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_CIVRE_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_DETEIS_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_GALLENTE_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_INTAKI_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_SEBIESTOR_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_BRUTOR_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_STATIC_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_MODIFIER_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_ACHURA_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_JIN_MEI_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_KHANID_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_VHEROKIOR_TYPE_ID))
        self.assertTrue(PilotStanding.is_pilot(CHARACTER_DRIFTER_TYPE_ID))

        self.assertFalse(PilotStanding.is_pilot(CORPORATION_TYPE_ID))
        self.assertFalse(PilotStanding.is_pilot(ALLIANCE_TYPE_ID))
        self.assertFalse(PilotStanding.is_pilot(1))
        self.assertFalse(PilotStanding.is_pilot(None))
        self.assertFalse(PilotStanding.is_pilot(-1))
        self.assertFalse(PilotStanding.is_pilot(0))


class TestCorpStanding(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(CorpStanding.get_contact_type_id(2001), CORPORATION_TYPE_ID)

    def test_is_pilot(self):
        self.assertTrue(CorpStanding.is_corp(CORPORATION_TYPE_ID))
        self.assertFalse(CorpStanding.is_corp(CHARACTER_TYPE_ID))
        self.assertFalse(CorpStanding.is_corp(ALLIANCE_TYPE_ID))
        self.assertFalse(CorpStanding.is_corp(1))
        self.assertFalse(CorpStanding.is_corp(None))
        self.assertFalse(CorpStanding.is_corp(-1))
        self.assertFalse(CorpStanding.is_corp(0))


class TestAllianceStanding(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(AllianceStanding.get_contact_type_id(3001), ALLIANCE_TYPE_ID)

    def test_is_pilot(self):
        self.assertTrue(AllianceStanding.is_alliance(ALLIANCE_TYPE_ID))
        self.assertFalse(AllianceStanding.is_alliance(CHARACTER_TYPE_ID))
        self.assertFalse(AllianceStanding.is_alliance(CORPORATION_TYPE_ID))
        self.assertFalse(AllianceStanding.is_alliance(1))
        self.assertFalse(AllianceStanding.is_alliance(None))
        self.assertFalse(AllianceStanding.is_alliance(-1))
        self.assertFalse(AllianceStanding.is_alliance(0))


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

    def test_check_standing_satisfied_check_only(self):
        my_request = StandingsRequest(
            user=self.user_requestor, contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
        )
        self.assertTrue(my_request.process_standing(check_only=True))

        my_request = StandingsRequest(
            user=self.user_requestor,
            contact_id=1002,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        self.assertTrue(my_request.process_standing(check_only=True))

        my_request = StandingsRequest(
            user=self.user_requestor,
            contact_id=1003,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        self.assertTrue(my_request.process_standing(check_only=True))

        my_request = StandingsRequest(
            user=self.user_requestor,
            contact_id=1005,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        self.assertFalse(my_request.process_standing(check_only=True))

        my_request = StandingsRequest(
            user=self.user_requestor,
            contact_id=1009,
            contact_type_id=CHARACTER_BRUTOR_TYPE_ID,
        )
        self.assertFalse(my_request.process_standing(check_only=True))

    def test_check_standing_satisfied_no_standing(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor, contact_id=1999, contact_type_id=CHARACTER_TYPE_ID
        )
        self.assertFalse(my_request.process_standing(check_only=True))

    def test_mark_standing_effective(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor, contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
        )

        my_request.mark_standing_effective()
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsInstance(my_request.effective_date, datetime)

        my_date = now() - timedelta(days=5, hours=4)
        my_request.mark_standing_effective(date=my_date)
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertEqual(my_request.effective_date, my_date)

    def test_check_standing_satisfied_and_mark(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor, contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
        )
        self.assertTrue(my_request.process_standing())
        my_request.refresh_from_db()
        self.assertTrue(my_request.is_effective)
        self.assertIsInstance(my_request.effective_date, datetime)

    def test_mark_standing_actioned(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
        )
        my_request.mark_standing_actioned(self.user_manager)
        my_request.refresh_from_db()
        self.assertEqual(my_request.action_by, self.user_manager)
        self.assertIsInstance(my_request.action_date, datetime)

    def test_check_standing_actioned_timeout_already_effective(self):
        my_request = StandingsRequest(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
        )
        self.assertIsNone(my_request.check_standing_actioned_timeout())

    def test_check_standing_actioned_timeout_not_actioned(self):
        my_request = StandingsRequest(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=False,
        )
        self.assertIsNone(my_request.check_standing_actioned_timeout())

    def test_check_standing_actioned_timeout_no_contact_set(self):
        ContactSet.objects.all().delete()
        my_request = StandingsRequest(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=False,
        )
        self.assertIsNone(my_request.check_standing_actioned_timeout())

    def test_check_standing_actioned_timeout_after_deadline(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now() - timedelta(hours=25),
            is_effective=False,
        )
        self.assertEqual(
            my_request.check_standing_actioned_timeout(), self.user_manager
        )
        my_request.refresh_from_db()
        self.assertIsNone(my_request.action_by)
        self.assertIsNone(my_request.action_date)

    def test_check_standing_actioned_timeout_before_deadline(self):
        my_request = StandingsRequest(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=False,
        )
        self.assertFalse(my_request.check_standing_actioned_timeout())

    def test_reset_to_initial(self):
        my_request = StandingsRequest.objects.create(
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
        my_request_effective = StandingsRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            is_effective=False,
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingsRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertFalse(
            StandingsRevocation.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )

    def test_delete_for_effective_add_revocation(self):
        my_request_effective = StandingsRequest.objects.create(
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
            StandingsRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertTrue(
            StandingsRevocation.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )

    def test_delete_for_pending_add_revocation(self):
        my_request_effective = StandingsRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=False,
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingsRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertTrue(
            StandingsRevocation.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )

    def test_delete_for_effective_dont_add_another_revocation(self):
        my_request_effective = StandingsRequest.objects.create(
            user=self.user_requestor,
            contact_id=1001,
            contact_type_id=CHARACTER_TYPE_ID,
            action_by=self.user_manager,
            action_date=now(),
            is_effective=True,
            effective_date=now(),
        )
        StandingsRevocation.objects.add_revocation(1001, CHARACTER_TYPE_ID)
        my_request_effective.delete()
        self.assertFalse(
            StandingsRequest.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).exists()
        )
        self.assertEqual(
            StandingsRevocation.objects.filter(
                contact_id=1001, contact_type_id=CHARACTER_TYPE_ID
            ).count(),
            1,
        )


class TestStandingsRequestClassMethods(NoSocketsTestCase):
    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODULE_PATH + ".EveCorporation.get_corp_by_id")
    def test_all_corp_apis_recorded_good(self, mock_get_corp_by_id):
        """user has tokens for all 3 chars of corp"""
        mock_get_corp_by_id.return_value = EveCorporationInfo(
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

        self.assertTrue(StandingsRequest.all_corp_apis_recorded(2001, my_user))

    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODULE_PATH + ".EveCorporation.get_corp_by_id")
    def test_all_corp_apis_recorded_incomplete(self, mock_get_corp_by_id):
        """user has tokens for only 2 / 3 chars of corp"""
        mock_get_corp_by_id.return_value = EveCorporationInfo(
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

        self.assertFalse(StandingsRequest.all_corp_apis_recorded(2001, my_user))

    @patch(
        MODULE_PATH + ".SR_REQUIRED_SCOPES",
        {"Guest": ["publicData", "esi-mail.read_mail.v1"]},
    )
    @patch(MODULE_PATH + ".EveCorporation.get_corp_by_id")
    def test_all_corp_apis_recorded_wrong_scope(self, mock_get_corp_by_id):
        """user has tokens for only 3 / 3 chars of corp, but wrong scopes"""
        mock_get_corp_by_id.return_value = EveCorporationInfo(
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

        self.assertFalse(StandingsRequest.all_corp_apis_recorded(2001, my_user))

    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"Guest": ["publicData"]})
    @patch(MODULE_PATH + ".EveCorporation.get_corp_by_id")
    def test_all_corp_apis_recorded_good_another_user(self, mock_get_corp_by_id):
        """there are tokens for all 3 chars of corp, but for another user"""
        mock_get_corp_by_id.return_value = EveCorporationInfo(
            **get_my_test_data()["EveCorporationInfo"]["2001"]
        )
        user_1 = AuthUtils.create_user("John Doe")
        user_2 = AuthUtils.create_user("Mike Myers")
        for character_id, character in get_my_test_data()["EveCharacter"].items():
            if character["corporation_id"] == 2001:
                my_character = EveCharacter.objects.create(**character)
                _store_as_Token(
                    _generate_token(
                        character_id=my_character.character_id,
                        character_name=my_character.character_name,
                        scopes=["publicData"],
                    ),
                    user_1,
                )

        self.assertFalse(StandingsRequest.all_corp_apis_recorded(2001, user_2))


class TestStandingsRequestGetRequiredScopesForState(NoSocketsTestCase):
    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_scopes_if_defined_for_state(self):
        expected = ["abc"]
        self.assertListEqual(
            StandingsRequest.get_required_scopes_for_state("member"), expected
        )

    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_empty_list_if_not_defined_for_state(self):
        expected = []
        self.assertListEqual(
            StandingsRequest.get_required_scopes_for_state("guest"), expected
        )

    @patch(MODULE_PATH + ".SR_REQUIRED_SCOPES", {"member": ["abc"]})
    def test_return_empty_list_if_state_is_note(self):
        expected = []
        self.assertListEqual(
            StandingsRequest.get_required_scopes_for_state(None), expected
        )


@patch(MODULE_PATH + ".StandingsRequest.get_required_scopes_for_state")
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
        self.assertTrue(StandingsRequest.has_required_scopes_for_request(character))

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
        self.assertFalse(StandingsRequest.has_required_scopes_for_request(character))

    def test_false_when_user_state_can_not_be_determinded(
        self, mock_get_required_scopes_for_state
    ):
        mock_get_required_scopes_for_state.return_value = ["abc"]
        character = create_entity(EveCharacter, 1002)
        self.assertFalse(StandingsRequest.has_required_scopes_for_request(character))


class TestCharacterAssociation(TestCase):
    def setUp(self):
        ContactSet.objects.all().delete()
        EveNameCache.objects.all().delete()
        CharacterAssociation.objects.all().delete()

    @patch(MODULE_PATH + ".EveNameCache")
    def test_get_character_name_exists(self, mock_EveNameCache):
        mock_EveNameCache.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1002, main_character_id=1001)
        self.assertEqual(my_assoc.character_name, "Peter Parker")

    @patch(MODULE_PATH + ".EveNameCache")
    def test_get_character_name_not_exists(self, mock_EveNameCache):
        mock_EveNameCache.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1999, main_character_id=1001)
        self.assertIsNone(my_assoc.character_name)

    @patch(MODULE_PATH + ".EveNameCache")
    def test_get_main_character_name_exists(self, mock_EveNameCache):
        mock_EveNameCache.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1002, main_character_id=1001)
        self.assertEqual(my_assoc.main_character_name, "Bruce Wayne")

    @patch(MODULE_PATH + ".EveNameCache")
    def test_get_main_character_name_not_exists(self, mock_EveNameCache):
        mock_EveNameCache.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1002, main_character_id=19999)
        self.assertIsNone(my_assoc.main_character_name)

    @patch(MODULE_PATH + ".EveNameCache")
    def test_get_main_character_name_not_defined(self, mock_EveNameCache):
        mock_EveNameCache.objects.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(character_id=1002)
        self.assertIsNone(my_assoc.main_character_name)


class TestEveNameCache(TestCase):
    def setUp(self):
        ContactSet.objects.all().delete()
        EveNameCache.objects.all().delete()

    """
    @patch(MODULE_PATH + '.EveEntityHelper')
    def test_get_names_from_contacts(self, mock_EveEntityHelper):        
        mock_EveEntityHelper.get_names.side_effect = \
            get_entity_names

        contact_set = ContactSet.objects.create(
            name='Dummy Pilots Set'
        )
        PilotStanding.objects.create(
            contact_set=contact_set
            contact_id=1001,
            name='Bruce Wayne',
            standing=0
        )                
        entities = EveNameCache.objects.get_names([1001])
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

    def test_cache_timeout(self):
        my_entity = EveNameCache(entity_id=1001, name="Bruce Wayne")
        # no cache timeout when added recently
        my_entity.updated = now()
        self.assertFalse(my_entity.cache_timeout())

        # cache timeout for entries older than 30 days
        my_entity.updated = now() - timedelta(days=31)
        self.assertTrue(my_entity.cache_timeout())
