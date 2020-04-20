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

from . import _set_logger, _generate_token, _store_as_Token
from .entity_type_ids import (
    ALLIANCE_TYPE_ID,
    CHARACTER_AMARR_TYPE_ID, 
    CHARACTER_TYPE_ID, 
    CORPORATION_TYPE_ID,
    FACTION_CALDARI_STATE_TYPE_ID,
)
from .my_test_data import (
    get_entity_names, 
    create_contacts_from_test_data, 
    create_entity,
    esi_post_characters_affiliation,
    get_my_test_data
)

from ..managers.standings import StandingsManager, ContactsWrapper
from ..models import (
    CharacterAssociation, 
    ContactSet, 
    ContactLabel,     
    PilotStanding, 
    StandingsRequest,
    StandingsRevocation, 
)

MODULE_PATH = 'standingsrequests.managers.standings'
logger = _set_logger(MODULE_PATH, __file__)


def get_test_labels() -> list:
    """returns labels from test data as list of ContactsWrapper.Label"""
    labels = list()
    for label_data in get_my_test_data()['alliance_labels']:
        labels.append(ContactsWrapper.Label(label_data))
    
    return labels


def get_test_contacts():
    """returns contacts from test data as list of ContactsWrapper.Contact"""
    labels = get_test_labels()
    
    contact_ids = [
        x['contact_id'] for x in get_my_test_data()['alliance_contacts']
    ]
    names_info = get_entity_names(contact_ids)
    contacts = list()
    for contact_data in get_my_test_data()['alliance_contacts']:
        labels.append(ContactsWrapper.Contact(contact_data, labels, names_info))

    return contacts


class TestStandingsManager(TestCase):
        
    def setUp(self):
        EveCharacter.objects.all().delete()
        EveCorporationInfo.objects.all().delete()
        EveAllianceInfo.objects.all().delete()

    @patch(MODULE_PATH + '.StandingsManager.charID', 1001)
    @patch(MODULE_PATH + '.esi_client_factory')
    @patch(MODULE_PATH + '.Token')
    def test_api_get_instance(
        self, mock_Token, mock_esi_client_factory
    ):
        mock_Token.objects.filter.return_value\
            .require_scopes.return_value.require_valid.return_value = \
            [Mock(spec=Token)]
        mock_esi_client_factory.return_value = 'my ESI client'

        response = StandingsManager.api_get_instance()
        self.assertEqual(response, 'my ESI client')
        self.assertEqual(
            mock_Token.objects.filter.call_args[1]['character_id'], 1001
        )
    
    @patch(MODULE_PATH + '.ContactsWrapper')
    @patch(MODULE_PATH + '.StandingsManager.api_get_instance')
    def test_api_update_alliance_standings_normal(
        self, mock_api_get_instance, mock_ContactsWrapper
    ):
        mock_api_get_instance.return_value = Mock()

        mock_contacts = Mock(spec=ContactsWrapper)
        mock_contacts.alliance = get_test_contacts()
        mock_contacts.allianceLabels = get_test_labels()
        
        mock_ContactsWrapper.return_value = mock_contacts

        x = StandingsManager.api_update_alliance_standings()
        self.assertIsInstance(x, ContactSet)

        # todo: needs more validations !!

    @patch(MODULE_PATH + '.ContactsWrapper')
    @patch(MODULE_PATH + '.StandingsManager.api_get_instance')
    def test_api_update_alliance_standings_error(
        self, mock_api_get_instance, mock_ContactsWrapper
    ):
        mock_api_get_instance.return_value = Mock()
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
        contacts = get_test_contacts()
        
        StandingsManager.api_add_contacts(my_set, contacts)

        self.assertEqual(
            len(contacts), 
            PilotStanding.objects.filter(set=my_set).count()
        )
        
        for contact in contacts:
            contact_in_set = PilotStanding.objects\
                .get(set=my_set, contactID=contact.id)
            self.assertEqual(contact.name, contact_in_set.name)
            self.assertEqual(contact.type_id, contact_in_set.contact_type)
            self.assertEqual(contact.standing, contact_in_set.standing)
            self.assertSetEqual(
                set(contact.label_ids), 
                set(contact_in_set.labels)
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
    def test_pilot_in_organisation_matches_none(self):        
        self.assertFalse(StandingsManager.pilot_in_organisation(1999))

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


class TestStandingsManagerProcessRequests(TestCase):
    
    def setUp(self):        
        self.user_manager = AuthUtils.create_user('Mike Manager')
        self.user_requestor = AuthUtils.create_user('Roger Requestor')
        ContactSet.objects.all().delete()         
        my_set = ContactSet.objects.create(name='Dummy Set')
        create_contacts_from_test_data(my_set)

    def test_process_requests_1(self):                
        """do nothing for pilot requests with standing satisfied in game"""
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

    def test_process_requests_1a(self):                
        """do nothing for corp requests with standing satisfied in game"""
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

    def test_process_requests_2(self):                
        """reset request w/ effective standing that is not satisfied in game"""
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

    @patch(MODULE_PATH + '.notify')
    def test_process_requests_3(self, mock_notify): 
        """notify about requests that have been reset and timed out"""
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

    @patch(MODULE_PATH + '.notify')
    def test_process_requests_4(self, mock_notify): 
        """dont notify about requests that have been reset and not timed out"""
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


class TestStandingsUpdateCharacterAssociations(TestCase):
    
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

    @patch(MODULE_PATH + '.EveNameCache')    
    def test_update_character_associations_auth(self, mock_EveNameCache):
        my_character = create_entity(EveCharacter, 1001)
        _store_as_Token(
            _generate_token(
                character_id=my_character.character_id,
                character_name=my_character.character_name,
                scopes=['publicData']
            ), 
            self.user_requestor
        )
        self.user_requestor.profile.main_character = my_character
        self.user_requestor.profile.save()

        StandingsManager.update_character_associations_auth()
        self.assertEqual(CharacterAssociation.objects.count(), 1)
        assoc = CharacterAssociation.objects.first()
        self.assertEqual(assoc.character_id, 1001)
        self.assertEqual(assoc.corporation_id, 2001)
        self.assertEqual(assoc.main_character_id, 1001)        
        self.assertEqual(assoc.alliance_id, 3001)

    # todo: test more variations


class TestStandingsUpdateCharacterAssociationsApi(TestCase):
    
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

    @patch(MODULE_PATH + '.StandingsManager.api_get_instance')  
    def test_do_nothing_if_not_set_available(self, mock_api_get_instance):
        StandingsManager.update_character_associations_api()
        self.assertFalse(
            mock_api_get_instance.return_value
            .Character.post_characters_affiliation.called
        )

    @patch(MODULE_PATH + '.StandingsManager.api_get_instance')  
    def test_dont_update_when_not_needed(self, mock_api_get_instance):
        create_contacts_from_test_data()
        StandingsManager.update_character_associations_api()        
        self.assertFalse(
            mock_api_get_instance.return_value
            .Character.post_characters_affiliation.called
        )

    @patch(MODULE_PATH + '.StandingsManager.api_get_instance')  
    def test_updates_all_contacts_with_expired_cache(self, mock_api_get_instance):
        mock_api_get_instance.return_value\
            .Character.post_characters_affiliation.side_effect = \
            esi_post_characters_affiliation

        create_contacts_from_test_data()
        expected = [1001, 1002, 1003]
        for x in CharacterAssociation.objects.filter(character_id__in=expected):
            x.updated = now() - timedelta(days=3, hours=1)
            x.save()
        StandingsManager.update_character_associations_api()        
        self.assertTrue(
            mock_api_get_instance.return_value
            .Character.post_characters_affiliation.called
        )
        args, kwargs = mock_api_get_instance.return_value\
            .Character.post_characters_affiliation.call_args        
        self.assertSetEqual(set(kwargs['characters']), set(expected))        
        self.assertTrue(
            CharacterAssociation.objects
            .filter(
                character_id__in=expected, 
                updated__gt=now() - timedelta(hours=1)
            ).exists()
        )

    @patch(MODULE_PATH + '.StandingsManager.api_get_instance')  
    def test_updates_all_unknown_contacts(self, mock_api_get_instance):
        mock_api_get_instance.return_value\
            .Character.post_characters_affiliation.side_effect = \
            esi_post_characters_affiliation
        
        create_contacts_from_test_data()
        expected = [1001, 1002, 1003]
        CharacterAssociation.objects.filter(character_id__in=expected).delete()
        StandingsManager.update_character_associations_api()        
        self.assertTrue(
            mock_api_get_instance.return_value
            .Character.post_characters_affiliation.called
        )
        args, kwargs = mock_api_get_instance.return_value\
            .Character.post_characters_affiliation.call_args        
        self.assertSetEqual(set(kwargs['characters']), set(expected))
        self.assertTrue(
            CharacterAssociation.objects
            .filter(character_id__in=expected).exists()
        )


class TestStandingsFactory(TestCase):
    pass


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
        
    @patch(MODULE_PATH + '.EveNameCache')
    def test_init(self, mock_EveNameCache):
        mock_EveNameCache.get_names.side_effect = get_entity_names
    
        mock_client = Mock()
        mock_client.Contacts\
            .get_alliances_alliance_id_contacts_labels.return_value\
            .result.return_value = get_my_test_data()['alliance_labels']

        mock_response = Mock()
        mock_response.headers = dict()
        mock_client.Contacts\
            .get_alliances_alliance_id_contacts.return_value\
            .result.return_value = (
                get_my_test_data()['alliance_contacts'], 
                mock_response
            )
        
        create_entity(EveCharacter, 1001)

        x = ContactsWrapper(mock_client, 1001)
        self.assertEqual(len(x.alliance), len(
            get_my_test_data()['alliance_contacts'])
        )
