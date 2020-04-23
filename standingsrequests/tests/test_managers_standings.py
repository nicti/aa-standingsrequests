from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils.timezone import now

from esi.models import Token

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import (
    EveCharacter, EveCorporationInfo, EveAllianceInfo
)
from allianceauth.tests.auth_utils import AuthUtils

from . import (
    _generate_token, 
    _store_as_Token, 
    add_new_token, 
    add_character_to_user
)
from .entity_type_ids import (
    ALLIANCE_TYPE_ID,
    CHARACTER_AMARR_TYPE_ID, 
    CHARACTER_TYPE_ID, 
    CORPORATION_TYPE_ID,
    FACTION_CALDARI_STATE_TYPE_ID,
)
from .my_test_data import (
    get_entity_names, 
    create_contacts_set, 
    create_entity,
    esi_post_characters_affiliation,
    get_my_test_data,
    get_test_labels,
    get_test_contacts
)

from ..managers.standings import (
    StandingsManager, ContactsWrapper, StandingFactory
)
from ..models import (
    CharacterAssociation, 
    ContactSet, 
    ContactLabel,    
    PilotStanding,
    CorpStanding,
    AllianceStanding, 
    StandingsRequest,
    StandingsRevocation, 
)
from ..utils import set_test_logger, NoSocketsTestCase


MODULE_PATH = 'standingsrequests.managers.standings'
logger = set_test_logger(MODULE_PATH, __file__)


class TestStandingsManager(NoSocketsTestCase):
        
    def setUp(self):
        EveCharacter.objects.all().delete()
        EveCorporationInfo.objects.all().delete()
        EveAllianceInfo.objects.all().delete()

    @patch(MODULE_PATH + '.StandingsManager.charID', 1001)    
    @patch(MODULE_PATH + '.Token')
    def test_token(self, mock_Token):
        mock_my_token = Mock(spec=Token)
        mock_Token.objects.filter.return_value\
            .require_scopes.return_value.require_valid.return_value\
            .first.return_value = mock_my_token
        
        token = StandingsManager.token()
        self.assertEqual(token, mock_my_token)
        self.assertEqual(
            mock_Token.objects.filter.call_args[1]['character_id'], 1001
        )
    
    @patch(MODULE_PATH + '.ContactsWrapper')
    @patch(MODULE_PATH + '.StandingsManager.token')
    def test_api_update_alliance_standings_normal(
        self, mock_token, mock_ContactsWrapper
    ):
        mock_contacts = Mock(spec=ContactsWrapper)
        mock_contacts.alliance = get_test_contacts()
        mock_contacts.allianceLabels = get_test_labels()
        
        mock_ContactsWrapper.return_value = mock_contacts

        x = StandingsManager.api_update_alliance_standings()
        self.assertIsInstance(x, ContactSet)

        # todo: needs more validations !!

    @patch(MODULE_PATH + '.ContactsWrapper')
    @patch(MODULE_PATH + '.StandingsManager.token')
    def test_api_update_alliance_standings_error(
        self, mock_token, mock_ContactsWrapper
    ):        
        mock_ContactsWrapper.side_effect = RuntimeError
        self.assertIsNone(StandingsManager.api_update_alliance_standings())

    def test_api_add_labels(self):
        my_set = ContactSet.objects.create(name='My Set')
        labels = get_test_labels()
        
        StandingsManager.api_add_labels(my_set, labels)        
        
        self.assertEqual(
            len(labels), 
            ContactLabel.objects.filter(set=my_set).count()
        )

        for label in labels:                    
            label_in_set = ContactLabel.objects\
                .get(set=my_set, labelID=label.id)
            self.assertEqual(label.name, label_in_set.name)

    def test_api_add_contacts(self):
        my_set = ContactSet.objects.create(name='My Set')
        StandingsManager.api_add_labels(my_set, get_test_labels())
        contacts = get_test_contacts()        
        
        StandingsManager.api_add_contacts(my_set, contacts)

        self.assertEqual(
            len(contacts), 
            PilotStanding.objects.filter(set=my_set).count()
            + CorpStanding.objects.filter(set=my_set).count()
            + AllianceStanding.objects.filter(set=my_set).count()
        )        
        for contact in contacts:
            if contact.type_id in PilotStanding.contactTypes:
                contact_in_set = \
                    PilotStanding.objects.get(set=my_set, contactID=contact.id)
            elif contact.type_id in CorpStanding.contactTypes:
                contact_in_set = \
                    CorpStanding.objects.get(set=my_set, contactID=contact.id)

            self.assertEqual(contact.name, contact_in_set.name)            
            self.assertEqual(contact.standing, contact_in_set.standing)
            self.assertSetEqual(
                set(contact.label_ids), 
                set(contact_in_set.labels.values_list('labelID', flat=True))
            )
            
    @patch(MODULE_PATH + '.STR_CORP_IDS', ['2001'])
    @patch(MODULE_PATH + '.STR_ALLIANCE_IDS', [])
    def test_pilot_in_organisation_matches_corp(self):
        create_entity(EveCharacter, 1001)
        self.assertTrue(StandingsManager.pilot_in_organisation(1001))

    @patch(MODULE_PATH + '.STR_CORP_IDS', [])
    @patch(MODULE_PATH + '.STR_ALLIANCE_IDS', ['3001'])
    def test_pilot_in_organisation_matches_alliance(self):
        create_entity(EveCharacter, 1001)
        self.assertTrue(StandingsManager.pilot_in_organisation(1001))

    @patch(MODULE_PATH + '.STR_CORP_IDS', [])
    @patch(MODULE_PATH + '.STR_ALLIANCE_IDS', [])
    def test_pilot_in_organisation_doest_not_exist(self):        
        self.assertFalse(StandingsManager.pilot_in_organisation(1999))

    @patch(MODULE_PATH + '.STR_CORP_IDS', [])
    @patch(MODULE_PATH + '.STR_ALLIANCE_IDS', [])
    def test_pilot_in_organisation_matches_none(self):        
        create_entity(EveCharacter, 1001)
        self.assertFalse(StandingsManager.pilot_in_organisation(1001))

    @patch(MODULE_PATH + '.SR_REQUIRED_SCOPES', {'Guest': ['publicData']})
    @patch(MODULE_PATH + '.EveCorporation.get_corp_by_id')
    def test_all_corp_apis_recorded_good(self, mock_get_corp_by_id):
        """user has tokens for all 3 chars of corp"""
        mock_get_corp_by_id.return_value = EveCorporationInfo(
            **get_my_test_data()['EveCorporationInfo']["2001"]
        )                
        my_user = AuthUtils.create_user('John Doe')
        for character_id, character in get_my_test_data()['EveCharacter'].items():
            if character["corporation_id"] == 2001:
                my_character = EveCharacter.objects.create(**character)
                _store_as_Token(
                    _generate_token(
                        character_id=my_character.character_id,
                        character_name=my_character.character_name,
                        scopes=['publicData']
                    ), 
                    my_user
                )               
        
        self.assertTrue(
            StandingsManager.all_corp_apis_recorded(2001, my_user)
        )

    @patch(MODULE_PATH + '.SR_REQUIRED_SCOPES', {'Guest': ['publicData']})
    @patch(MODULE_PATH + '.EveCorporation.get_corp_by_id')
    def test_all_corp_apis_recorded_incomplete(self, mock_get_corp_by_id):
        """user has tokens for only 2 / 3 chars of corp"""
        mock_get_corp_by_id.return_value = EveCorporationInfo(
            **get_my_test_data()['EveCorporationInfo']["2001"]
        )                
        my_user = AuthUtils.create_user('John Doe')
        for character_id, character in get_my_test_data()['EveCharacter'].items():
            if character_id in [1001, 1002]:
                my_character = EveCharacter.objects.create(**character)
                _store_as_Token(
                    _generate_token(
                        character_id=my_character.character_id,
                        character_name=my_character.character_name,
                        scopes=['publicData']
                    ), 
                    my_user
                )               
        
        self.assertFalse(
            StandingsManager.all_corp_apis_recorded(2001, my_user)
        )

    @patch(
        MODULE_PATH + '.SR_REQUIRED_SCOPES', 
        {'Guest': ['publicData', 'esi-mail.read_mail.v1']}
    )
    @patch(MODULE_PATH + '.EveCorporation.get_corp_by_id')
    def test_all_corp_apis_recorded_wrong_scope(self, mock_get_corp_by_id):
        """user has tokens for only 3 / 3 chars of corp, but wrong scopes"""
        mock_get_corp_by_id.return_value = EveCorporationInfo(
            **(get_my_test_data()['EveCorporationInfo']["2001"])
        )        
        my_user = AuthUtils.create_user('John Doe')        
        for character_id, character in get_my_test_data()['EveCharacter'].items():
            if character_id in [1001, 1002]:
                my_character = EveCharacter.objects.create(**character)
                _store_as_Token(
                    _generate_token(
                        character_id=my_character.character_id,
                        character_name=my_character.character_name,
                        scopes=['publicData']
                    ), 
                    my_user
                )               
        
        self.assertFalse(
            StandingsManager.all_corp_apis_recorded(2001, my_user)
        )

    @patch(MODULE_PATH + '.SR_REQUIRED_SCOPES', {'Guest': ['publicData']})
    @patch(MODULE_PATH + '.EveCorporation.get_corp_by_id')
    def test_all_corp_apis_recorded_good_another_user(self, mock_get_corp_by_id):
        """there are tokens for all 3 chars of corp, but for another user"""
        mock_get_corp_by_id.return_value = EveCorporationInfo(
            **get_my_test_data()['EveCorporationInfo']["2001"]
        )        
        user_1 = AuthUtils.create_user('John Doe')
        user_2 = AuthUtils.create_user('Mike Myers')        
        for character_id, character in get_my_test_data()['EveCharacter'].items():
            if character["corporation_id"] == 2001:
                my_character = EveCharacter.objects.create(**character)
                _store_as_Token(
                    _generate_token(
                        character_id=my_character.character_id,
                        character_name=my_character.character_name,
                        scopes=['publicData']
                    ), 
                    user_1
                )               
        
        self.assertFalse(
            StandingsManager.all_corp_apis_recorded(2001, user_2)
        )
   
    @patch(MODULE_PATH + '.StandingsRevocation.objects.all')
    @patch(MODULE_PATH + '.StandingsRequest.objects.all')
    @patch(MODULE_PATH + '.StandingsManager.process_requests')
    def test_process_pending_standings_empty(
        self, 
        mock_process_requests,
        mock_StandingsRequest_objects_all,
        mock_StandingsRevocation_objects_all
    ):
        StandingsManager.process_pending_standings()
        self.assertEqual(mock_StandingsRequest_objects_all.call_count, 1)
        self.assertEqual(mock_StandingsRevocation_objects_all.call_count, 1)
    
    @patch(MODULE_PATH + '.StandingsRevocation.objects.all')
    @patch(MODULE_PATH + '.StandingsRequest.objects.all')
    @patch(MODULE_PATH + '.StandingsManager.process_requests')
    def test_process_pending_standings_StandingsRequest(
        self, 
        mock_process_requests,
        mock_StandingsRequest_objects_all,
        mock_StandingsRevocation_objects_all
    ):
        StandingsManager.process_pending_standings(StandingsRequest)
        self.assertEqual(mock_StandingsRequest_objects_all.call_count, 1)
        self.assertEqual(mock_StandingsRevocation_objects_all.call_count, 0)

    @patch(MODULE_PATH + '.StandingsRevocation.objects.all')
    @patch(MODULE_PATH + '.StandingsRequest.objects.all')
    @patch(MODULE_PATH + '.StandingsManager.process_requests')
    def test_process_pending_standings_StandingsRevocation(
        self, 
        mock_process_requests,
        mock_StandingsRequest_objects_all,
        mock_StandingsRevocation_objects_all
    ):
        StandingsManager.process_pending_standings(StandingsRevocation)
        self.assertEqual(mock_StandingsRequest_objects_all.call_count, 0)
        self.assertEqual(mock_StandingsRevocation_objects_all.call_count, 1)


@patch(MODULE_PATH + '.StandingsManager.get_required_scopes_for_state')
class TestStandingsManagerHasRequiredScopesForRequest(TestCase):
   
    def test_true_when_user_has_required_scopes(
        self, mock_get_required_scopes_for_state
    ):
        mock_get_required_scopes_for_state.return_value = ['abc']
        user = AuthUtils.create_member('Bruce Wayne')
        character = AuthUtils.add_main_character_2(
            user=user, 
            name='Batman', 
            character_id=2099, 
            corp_id=2001, 
            corp_name='Wayne Tech'
        )
        add_new_token(user, character, ['abc'])
        self.assertTrue(
            StandingsManager.has_required_scopes_for_request(character)
        )

    def test_false_when_user_does_not_have_required_scopes(
        self, mock_get_required_scopes_for_state
    ):
        mock_get_required_scopes_for_state.return_value = ['xyz']
        user = AuthUtils.create_member('Bruce Wayne')
        character = AuthUtils.add_main_character_2(
            user=user, 
            name='Batman', 
            character_id=2099, 
            corp_id=2001, 
            corp_name='Wayne Tech'
        )
        add_new_token(user, character, ['abc'])
        self.assertFalse(
            StandingsManager.has_required_scopes_for_request(character)
        )

    def test_false_when_user_state_can_not_be_determinded(
        self, mock_get_required_scopes_for_state
    ):
        mock_get_required_scopes_for_state.return_value = ['abc']                
        character = create_entity(EveCharacter, 1002)        
        self.assertFalse(
            StandingsManager.has_required_scopes_for_request(character)
        )


class TestStandingsManagerGetRequiredScopesForState(TestCase):

    @patch(MODULE_PATH + '.SR_REQUIRED_SCOPES', {'member': ['abc']})
    def test_return_scopes_if_defined_for_state(self):        
        expected = ['abc']
        self.assertListEqual(
            StandingsManager.get_required_scopes_for_state('member'),
            expected
        )

    @patch(MODULE_PATH + '.SR_REQUIRED_SCOPES', {'member': ['abc']})
    def test_return_empty_list_if_not_defined_for_state(self):
        expected = []
        self.assertListEqual(
            StandingsManager.get_required_scopes_for_state('guest'),
            expected
        )

    @patch(MODULE_PATH + '.SR_REQUIRED_SCOPES', {'member': ['abc']})
    def test_return_empty_list_if_state_is_note(self):
        expected = []
        self.assertListEqual(
            StandingsManager.get_required_scopes_for_state(None),
            expected
        )


@patch(MODULE_PATH + '.notify')
class TestStandingsManagerProcessRequests(TestCase):
    
    def setUp(self):        
        self.user_manager = AuthUtils.create_user('Mike Manager')
        self.user_requestor = AuthUtils.create_user('Roger Requestor')
        ContactSet.objects.all().delete()                 
        create_contacts_set()

    def test_no_action_for_pilot_request_when_standing_satisfied_in_game(
        self, mock_notify
    ):     
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1002,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=now(),
            effective=True,
            effectiveDate=now()
        )
        StandingsManager.process_requests([my_request])
        my_request.refresh_from_db()
        self.assertTrue(my_request.effective)
        self.assertIsNotNone(my_request.effectiveDate)
        self.assertEqual(my_request.actionBy, self.user_manager)
        self.assertIsNotNone(my_request.actionDate)

    def test_no_action_for_corp_request_when_standing_satisfied_in_game(
        self, mock_notify
    ):          
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=2004,
            contactType=CORPORATION_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=now(),
            effective=True,
            effectiveDate=now()
        )
        StandingsManager.process_requests([my_request])
        my_request.refresh_from_db()
        self.assertTrue(my_request.effective)
        self.assertIsNotNone(my_request.effectiveDate)
        self.assertEqual(my_request.actionBy, self.user_manager)
        self.assertIsNotNone(my_request.actionDate)

    def test_reset_request_with_eff_standing_not_statisfied_in_game(
        self, mock_notify
    ):     
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1008,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=now(),
            effective=True,
            effectiveDate=now()
        )
        StandingsManager.process_requests([my_request])
        my_request.refresh_from_db()
        self.assertFalse(my_request.effective)
        self.assertIsNone(my_request.effectiveDate)
        self.assertIsNone(my_request.actionBy)
        self.assertIsNone(my_request.actionDate)
    
    def test_notify_about_requests_that_are_reset_and_timed_out(
        self, mock_notify
    ):     
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1008,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=now() - timedelta(hours=25),
            effective=False
        )
        StandingsManager.process_requests([my_request])
        self.assertEqual(mock_notify.call_count, 1)
    
    def test_dont_notify_about_requests_that_are_reset_and_not_timed_out(
        self, mock_notify
    ):         
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1008,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=now() - timedelta(hours=1),
            effective=False
        )
        StandingsManager.process_requests([my_request])
        self.assertEqual(mock_notify.call_count, 0)


@patch(MODULE_PATH + '.EveNameCache')
class TestStandingsUpdateCharacterAssociationsAuth(TestCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = AuthUtils.create_user('Bruce Wayne')
        
    def setUp(self):        
        EveCharacter.objects.all().delete()
        CharacterOwnership.objects.all().delete()
        CharacterAssociation.objects.all().delete()
        ContactSet.objects.all().delete()

    def test_can_update_from_one_character(self, mock_EveNameCache):
        my_character = create_entity(EveCharacter, 1001)        
        add_character_to_user(self.user, my_character, is_main=True)

        StandingsManager.update_character_associations_auth()
        self.assertEqual(CharacterAssociation.objects.count(), 1)
        assoc = CharacterAssociation.objects.first()
        self.assertEqual(assoc.character_id, 1001)
        self.assertEqual(assoc.corporation_id, 2001)
        self.assertEqual(assoc.main_character_id, 1001)        
        self.assertEqual(assoc.alliance_id, 3001)
    
    def test_can_handle_no_main(self, mock_EveNameCache):
        my_character = create_entity(EveCharacter, 1001)        
        add_character_to_user(self.user, my_character)

        StandingsManager.update_character_associations_auth()
        self.assertEqual(CharacterAssociation.objects.count(), 1)
        assoc = CharacterAssociation.objects.first()
        self.assertEqual(assoc.character_id, 1001)
        self.assertEqual(assoc.corporation_id, 2001)
        self.assertIsNone(assoc.main_character_id)
        self.assertEqual(assoc.alliance_id, 3001)

    def test_can_handle_no_character_without_alliance(self, mock_EveNameCache):
        my_character = create_entity(EveCharacter, 1004)        
        add_character_to_user(self.user, my_character)

        StandingsManager.update_character_associations_auth()
        self.assertEqual(CharacterAssociation.objects.count(), 1)
        assoc = CharacterAssociation.objects.first()
        self.assertEqual(assoc.character_id, 1004)
        self.assertEqual(assoc.corporation_id, 2003)
        self.assertIsNone(assoc.main_character_id)
        self.assertIsNone(assoc.alliance_id)

  
@patch('standingsrequests.helpers.esi_fetch._esi_client')
class TestStandingsUpdateCharacterAssociationsApi(NoSocketsTestCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_requestor = AuthUtils.create_user('Roger Requestor')
        cls.user_manager = AuthUtils.create_user('Mike Manager')
        
    def setUp(self):        
        EveCharacter.objects.all().delete()
        CharacterOwnership.objects.all().delete()
        CharacterAssociation.objects.all().delete()
        ContactSet.objects.all().delete()
 
    def test_do_nothing_if_not_set_available(self, mock_esi_client):
        StandingsManager.update_character_associations_api()
        self.assertFalse(
            mock_esi_client.return_value
            .Character.post_characters_affiliation.called
        )

    def test_dont_update_when_not_needed(self, mock_esi_client):
        create_contacts_set()
        StandingsManager.update_character_associations_api()        
        self.assertFalse(
            mock_esi_client.return_value
            .Character.post_characters_affiliation.called
        )

    def test_updates_all_contacts_with_expired_cache(self, mock_esi_client):
        mock_esi_client.return_value\
            .Character.post_characters_affiliation.side_effect = \
            esi_post_characters_affiliation

        create_contacts_set()
        expected = [1001, 1002, 1003]
        for x in CharacterAssociation.objects.filter(character_id__in=expected):
            x.updated = now() - timedelta(days=3, hours=1)
            x.save()
        StandingsManager.update_character_associations_api()        
        self.assertTrue(
            mock_esi_client.return_value
            .Character.post_characters_affiliation.called
        )
        args, kwargs = mock_esi_client.return_value\
            .Character.post_characters_affiliation.call_args        
        self.assertSetEqual(set(kwargs['characters']), set(expected))        
        self.assertTrue(
            CharacterAssociation.objects
            .filter(
                character_id__in=expected, 
                updated__gt=now() - timedelta(hours=1)
            ).exists()
        )
    
    def test_updates_all_unknown_contacts(self, mock_esi_client):
        mock_esi_client.return_value\
            .Character.post_characters_affiliation.side_effect = \
            esi_post_characters_affiliation
        
        create_contacts_set()
        expected = [1001, 1002, 1003]
        CharacterAssociation.objects.filter(character_id__in=expected).delete()
        StandingsManager.update_character_associations_api()        
        self.assertTrue(
            mock_esi_client.return_value
            .Character.post_characters_affiliation.called
        )
        args, kwargs = mock_esi_client.return_value\
            .Character.post_characters_affiliation.call_args        
        self.assertSetEqual(set(kwargs['characters']), set(expected))
        self.assertTrue(
            CharacterAssociation.objects
            .filter(character_id__in=expected).exists()
        )

    def test_handle_exception_from_api(self, mock_esi_client):
        mock_esi_client.return_value\
            .Character.post_characters_affiliation.side_effect = \
            RuntimeError
        
        create_contacts_set()
        expected = [1001, 1002, 1003]
        CharacterAssociation.objects.filter(character_id__in=expected).delete()
        StandingsManager.update_character_associations_api()
        self.assertFalse(
            CharacterAssociation.objects
            .filter(character_id__in=expected).exists()
        )
        

class TestStandingFactory(TestCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact_set = create_contacts_set()
        
    def test_can_create_pilot_standing(self):
        obj = StandingFactory.create_standing(
            contact_set=self.contact_set,
            contact_type=CHARACTER_TYPE_ID,
            name='Lex Luthor',
            contact_id=1009,
            standing=-10,
            labels=ContactLabel.objects.all()
        )
        self.assertIsInstance(obj, PilotStanding)
        self.assertEqual(obj.name, 'Lex Luthor')
        self.assertEqual(obj.contactID, 1009)
        self.assertEqual(obj.standing, -10)        
    
    def test_can_create_corp_standing(self):
        obj = StandingFactory.create_standing(
            contact_set=self.contact_set,
            contact_type=CORPORATION_TYPE_ID,
            name='Lexcorp',
            contact_id=2102,
            standing=-10,
            labels=ContactLabel.objects.all()
        )
        self.assertIsInstance(obj, CorpStanding)
        self.assertEqual(obj.name, 'Lexcorp')
        self.assertEqual(obj.contactID, 2102)
        self.assertEqual(obj.standing, -10)   

    def test_can_create_alliance_standing(self):
        obj = StandingFactory.create_standing(
            contact_set=self.contact_set,
            contact_type=ALLIANCE_TYPE_ID,
            name='Wayne Enterprises',
            contact_id=3001,
            standing=5,
            labels=ContactLabel.objects.all()
        )
        self.assertIsInstance(obj, AllianceStanding)
        self.assertEqual(obj.name, 'Wayne Enterprises')
        self.assertEqual(obj.contactID, 3001)
        self.assertEqual(obj.standing, 5)   


class TestContactsWrapperLabel(TestCase):
        
    def test_all(self):
        json = {
            'label_id': 3,
            'label_name': 'Dummy Label 3'
        }
        x = ContactsWrapper.Label(json)
        self.assertEqual(int(x.id), 3)
        self.assertEqual(x.name, 'Dummy Label 3')
        self.assertEqual(str(x), 'Dummy Label 3')
        self.assertEqual(repr(x), 'Dummy Label 3')


class TestContactsWrapperContact(TestCase):
    
    def test_all(self):
        json = {
            'contact_id': 1001,
            'contact_type': 'character',
            'label_ids': [3, 7],
            'standing': 5,            
        }
        label_3 = ContactsWrapper.Label({
            'label_id': 3,
            'label_name': 'Dummy Label 3'
        })
        label_4 = ContactsWrapper.Label({
            'label_id': 4,
            'label_name': 'Dummy Label 4'
        })
        label_7 = ContactsWrapper.Label({
            'label_id': 7,
            'label_name': 'Dummy Label 7'
        })
        labels = [label_3, label_4, label_7]
        names_info = {
            1001: 'Bruce Wayne'
        }
        x = ContactsWrapper.Contact(json, labels, names_info)
        self.assertEqual(int(x.id), 1001)
        self.assertEqual(x.name, 'Bruce Wayne')
        self.assertEqual(int(x.standing), 5)
        self.assertIsNone(x.in_watchlist)
        self.assertListEqual(x.label_ids, [3, 7])
        self.assertListEqual(x.labels, [label_3, label_7])

        self.assertEqual(str(x), 'Bruce Wayne')
        self.assertEqual(repr(x), 'Bruce Wayne')

    def test_get_type_id_from_name(self):
        self.assertEqual(
            ContactsWrapper.Contact.get_type_id_from_name('character'),
            CHARACTER_AMARR_TYPE_ID
        )
        self.assertEqual(
            ContactsWrapper.Contact.get_type_id_from_name('alliance'),
            ALLIANCE_TYPE_ID
        )
        self.assertEqual(
            ContactsWrapper.Contact.get_type_id_from_name('faction'),
            FACTION_CALDARI_STATE_TYPE_ID
        )
        self.assertEqual(
            ContactsWrapper.Contact.get_type_id_from_name('corporation'),
            CORPORATION_TYPE_ID
        )
        with self.assertRaises(NotImplementedError):
            ContactsWrapper.Contact.get_type_id_from_name('not supported')


class TestContactsWrapper(TestCase):
        
    @patch('standingsrequests.helpers.esi_fetch._esi_client')
    @patch(MODULE_PATH + '.EveNameCache')
    def test_init(self, mock_EveNameCache, mock_esi_client):
        mock_EveNameCache.get_names.side_effect = get_entity_names
            
        mock_esi_client.return_value.Contacts\
            .get_alliances_alliance_id_contacts_labels.return_value\
            .result.return_value = get_my_test_data()['alliance_labels']

        mock_response = Mock()
        mock_response.headers = dict()
        mock_esi_client.return_value.Contacts\
            .get_alliances_alliance_id_contacts.return_value\
            .result.return_value = (
                get_my_test_data()['alliance_contacts'], 
                mock_response
            )
        
        create_entity(EveCharacter, 1001)

        contacts = ContactsWrapper(Mock(spec=Token), 1001)
        self.assertEqual(len(contacts.alliance), len(
            get_my_test_data()['alliance_contacts'])
        )


@patch(MODULE_PATH + '.StandingsManager.all_corp_apis_recorded')
class TestValidateStandingRequest(NoSocketsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_contacts_set()
        cls.user = AuthUtils.create_member('Bruce Wayne')
    
    def setUp(self):
        StandingsRequest.objects.all().delete()

    def test_do_nothing_character_request_is_valid(
        self, mock_all_corp_apis_recorded
    ):
        AuthUtils.add_permission_to_user_by_name(
            'standingsrequests.request_standings', self.user
        )
        request = StandingsRequest.add_request(
            self.user, 1002, CHARACTER_TYPE_ID
        )

        StandingsManager.validate_standings_requests()
        self.assertTrue(
            StandingsRequest.objects.filter(pk=request.pk).exists()
        )

    def test_remove_character_standing_request_if_user_has_no_permission(
        self, mock_all_corp_apis_recorded
    ):
        request = StandingsRequest.add_request(
            self.user, 1002, CHARACTER_TYPE_ID
        )

        StandingsManager.validate_standings_requests()
        self.assertFalse(
            StandingsRequest.objects.filter(pk=request.pk).exists()
        )
    
    def test_remove_corp_standing_request_if_not_all_apis_recorded(
        self, mock_all_corp_apis_recorded
    ):
        mock_all_corp_apis_recorded.return_value = False
        AuthUtils.add_permission_to_user_by_name(
            'standingsrequests.request_standings', self.user
        )
        request = StandingsRequest.add_request(
            self.user, 2001, CORPORATION_TYPE_ID
        )

        StandingsManager.validate_standings_requests()
        self.assertFalse(
            StandingsRequest.objects.filter(pk=request.pk).exists()
        )
    
    def test_keep_corp_standing_request_if_all_apis_recorded(
        self, mock_all_corp_apis_recorded
    ):
        mock_all_corp_apis_recorded.return_value = True
        AuthUtils.add_permission_to_user_by_name(
            'standingsrequests.request_standings', self.user
        )
        request = StandingsRequest.add_request(
            self.user, 2001, CORPORATION_TYPE_ID
        )

        StandingsManager.validate_standings_requests()
        self.assertTrue(
            StandingsRequest.objects.filter(pk=request.pk).exists()
        )
