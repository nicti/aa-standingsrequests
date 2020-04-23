from datetime import timedelta, datetime
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

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
    CHARACTER_DRIFTER_TYPE_ID
)
from .my_test_data import (
    create_contacts_set, get_entity_name, get_entity_names
)
from ..models import (
    AbstractStanding, 
    AllianceStanding,     
    CharacterAssociation,
    ContactSet,     
    CorpStanding, 
    EveNameCache,     
    PilotStanding,    
    StandingsRequest, 
    StandingsRevocation, 
)
from ..utils import set_test_logger


MODULE_PATH = 'standingsrequests.models'
logger = set_test_logger(MODULE_PATH, __file__)


class TestContactSet(TestCase):

    def setUp(self):
        ContactSet.objects.all().delete()       
            
    def test_str(self):
        my_set = ContactSet(name='My Set')        
        self.assertIsInstance(str(my_set), str)

    def test_get_standing_for_id_pilot(self):
        my_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        PilotStanding.objects.create(
            set=my_set,
            contactID=1001,
            name='Bruce Wayne',
            standing=5
        )
        # look for existing pilot
        obj = my_set.get_standing_for_id(1001, CHARACTER_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing pilot
        with self.assertRaises(PilotStanding.DoesNotExist):    
            my_set.get_standing_for_id(1999, CHARACTER_TYPE_ID)        

    def test_get_standing_for_id_corporation(self):
        my_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        CorpStanding.objects.create(
            set=my_set,
            contactID=2001,
            name='Dummy Corp 1',
            standing=5
        )
        # look for existing corp
        obj = my_set.get_standing_for_id(2001, CORPORATION_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing corp
        with self.assertRaises(CorpStanding.DoesNotExist):    
            my_set.get_standing_for_id(2999, CORPORATION_TYPE_ID)

    def test_get_standing_for_id_alliance(self):
        my_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        AllianceStanding.objects.create(
            set=my_set,
            contactID=3001,
            name='Dummy Alliance 1',
            standing=5
        )
        # look for existing alliance
        obj = my_set.get_standing_for_id(3001, ALLIANCE_TYPE_ID)
        self.assertEqual(obj.standing, 5)

        # look for non existing alliance
        with self.assertRaises(AllianceStanding.DoesNotExist):    
            my_set.get_standing_for_id(3999, ALLIANCE_TYPE_ID)

    def test_get_standing_for_id_other_type(self):
        my_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        AllianceStanding.objects.create(
            set=my_set,
            contactID=3001,
            name='Dummy Alliance 1',
            standing=5
        )              
        with self.assertRaises(ObjectDoesNotExist):    
            my_set.get_standing_for_id(9999, 99)


class TestAbstractStanding(TestCase):

    def test_get_contact_type(self):        
        with self.assertRaises(NotImplementedError):
            AbstractStanding.get_contact_type(42)
            

class TestPilotStanding(TestCase):

    def test_get_contact_type(self):
        self.assertEqual(PilotStanding.get_contact_type(1001), CHARACTER_TYPE_ID)

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
        self.assertEqual(CorpStanding.get_contact_type(2001), CORPORATION_TYPE_ID)

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
        self.assertEqual(AllianceStanding.get_contact_type(3001), ALLIANCE_TYPE_ID)

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
            'Mike Manager',
            'mm@example.com',
            'password'
        )
        cls.user_requestor = User.objects.create_user(
            'Roger Requestor',
            'rr@example.com',
            'password'
        )
    
    def test_check_standing_satisfied_check_only(self):
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID
        )        
        self.assertTrue(my_request.check_standing_satisfied(check_only=True))
        
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1002,
            contactType=CHARACTER_BRUTOR_TYPE_ID
        )
        self.assertTrue(my_request.check_standing_satisfied(check_only=True))

        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1003,
            contactType=CHARACTER_BRUTOR_TYPE_ID
        )
        self.assertTrue(my_request.check_standing_satisfied(check_only=True))

        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1005,
            contactType=CHARACTER_BRUTOR_TYPE_ID
        )
        self.assertFalse(my_request.check_standing_satisfied(check_only=True))

        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1009,
            contactType=CHARACTER_BRUTOR_TYPE_ID
        )
        self.assertFalse(my_request.check_standing_satisfied(check_only=True))

    def test_check_standing_satisfied_no_standing(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1999,
            contactType=CHARACTER_TYPE_ID
        )                
        self.assertFalse(
            my_request.check_standing_satisfied(check_only=True)
        )

    def test_mark_standing_effective(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID
        )        
                
        my_request.mark_standing_effective()
        my_request.refresh_from_db()
        self.assertTrue(my_request.effective)
        self.assertIsInstance(my_request.effectiveDate, datetime)

        my_date = timezone.now() - timedelta(days=5, hours=4)
        my_request.mark_standing_effective(date=my_date)
        my_request.refresh_from_db()
        self.assertTrue(my_request.effective)
        self.assertEqual(my_request.effectiveDate, my_date)

    def test_check_standing_satisfied_and_mark(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID
        )        
        self.assertTrue(my_request.check_standing_satisfied())
        my_request.refresh_from_db()
        self.assertTrue(my_request.effective)
        self.assertIsInstance(my_request.effectiveDate, datetime)
    
    def test_mark_standing_actioned(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
        )                        
        my_request.mark_standing_actioned(self.user_manager)
        my_request.refresh_from_db()
        self.assertEqual(my_request.actionBy, self.user_manager)
        self.assertIsInstance(my_request.actionDate, datetime)

    def test_check_standing_actioned_timeout_already_effective(self):
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=True
        )
        self.assertIsNone(my_request.check_standing_actioned_timeout())

    def test_check_standing_actioned_timeout_not_actioned(self):
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            effective=False
        )
        self.assertIsNone(my_request.check_standing_actioned_timeout())

    def test_check_standing_actioned_timeout_no_contact_set(self):
        ContactSet.objects.all().delete()
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=False
        )
        self.assertIsNone(my_request.check_standing_actioned_timeout())

    def test_check_standing_actioned_timeout_after_deadline(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now() - timedelta(hours=25),
            effective=False
        )
        self.assertEqual(
            my_request.check_standing_actioned_timeout(),
            self.user_manager
        )
        my_request.refresh_from_db()
        self.assertIsNone(my_request.actionBy)
        self.assertIsNone(my_request.actionDate)

    def test_check_standing_actioned_timeout_before_deadline(self):
        my_request = StandingsRequest(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=False
        )
        self.assertFalse(my_request.check_standing_actioned_timeout())

    def test_reset_to_initial(self):
        my_request = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=True,
            effectiveDate=timezone.now(),
        )
        my_request.reset_to_initial()
        my_request.refresh_from_db()
        self.assertFalse(my_request.effective)
        self.assertIsNone(my_request.effectiveDate)
        self.assertIsNone(my_request.actionBy)
        self.assertIsNone(my_request.actionDate)

    def test_pending_request(self):
        my_request_1 = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,            
            effective=False
        )        
        self.assertTrue(my_request_1.pending_request(1001))

        my_request_2 = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1002,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=True,
            effectiveDate=timezone.now(),
        )
        self.assertFalse(my_request_2.pending_request(1002))
        
    def test_actioned_request(self):
        my_request_1 = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=False
        )        
        self.assertTrue(my_request_1.actioned_request(1001))

        my_request_2 = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1002,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=True,
            effectiveDate=timezone.now(),
        )
        self.assertFalse(my_request_2.actioned_request(1002))

        my_request_3 = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1003,
            contactType=CHARACTER_TYPE_ID,            
        )
        self.assertFalse(my_request_3.actioned_request(1003))

    def test_delete_for_non_effective_dont_add_revocation(self):
        my_request_effective = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,            
            effective=False
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingsRequest.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .exists()
        )
        self.assertFalse(
            StandingsRevocation.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .exists()
        )

    def test_delete_for_effective_add_revocation(self):
        my_request_effective = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=True,
            effectiveDate=timezone.now(),
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingsRequest.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .exists()
        )
        self.assertTrue(
            StandingsRevocation.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .exists()
        )

    def test_delete_for_pending_add_revocation(self):
        my_request_effective = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=False
        )
        my_request_effective.delete()
        self.assertFalse(
            StandingsRequest.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .exists()
        )
        self.assertTrue(
            StandingsRevocation.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .exists()
        )       

    def test_delete_for_effective_dont_add_another_revocation(self):
        my_request_effective = StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,
            actionBy=self.user_manager,
            actionDate=timezone.now(),
            effective=True,
            effectiveDate=timezone.now(),
        )
        StandingsRevocation.add_revocation(1001, CHARACTER_TYPE_ID)
        my_request_effective.delete()
        self.assertFalse(
            StandingsRequest.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .exists()
        )
        self.assertEqual(
            StandingsRevocation.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .count(),
            1
        )

    def test_add_request_new(self):
        my_request = StandingsRequest.add_request(
            self.user_requestor, 
            1001, 
            CHARACTER_TYPE_ID
        )
        self.assertIsInstance(my_request, StandingsRequest)

    def test_add_request_already_exists(self):
        my_request_1 = StandingsRequest.add_request(
            self.user_requestor, 
            1001, 
            CHARACTER_TYPE_ID
        )
        my_request_2 = StandingsRequest.add_request(
            self.user_requestor, 
            1001, 
            CHARACTER_TYPE_ID
        )
        self.assertEqual(my_request_1, my_request_2)

    def test_remove_requests(self):
        StandingsRequest.objects.create(
            user=self.user_requestor,
            contactID=1001,
            contactType=CHARACTER_TYPE_ID,            
            effective=False
        )      
        StandingsRequest.remove_requests(1001)
        self.assertFalse(
            StandingsRequest.objects
            .filter(contactID=1001, contactType=CHARACTER_TYPE_ID)
            .exists()
        )


class TestStandingsRevocation(TestCase):
    
    def setUp(self):
        ContactSet.objects.all().delete() 
        my_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        PilotStanding.objects.create(
            set=my_set,
            contactID=1001,
            name='Bruce Wayne',
            standing=10
        )
        PilotStanding.objects.create(
            set=my_set,
            contactID=1002,
            name='James Gordon',
            standing=5
        )
        PilotStanding.objects.create(
            set=my_set,
            contactID=1003,
            name='Alfred Pennyworth',
            standing=0.01
        )
        PilotStanding.objects.create(
            set=my_set,
            contactID=1005,
            name='Clark Kent',
            standing=0
        )
        PilotStanding.objects.create(
            set=my_set,
            contactID=1008,
            name='Harvey Dent',
            standing=-5
        )
        PilotStanding.objects.create(
            set=my_set,
            contactID=1009,
            name='Lex Luthor',
            standing=-10
        )
        self.user_manager = User.objects.create_user(
            'Mike Manager',
            'mm@example.com',
            'password'
        )
        self.user_requestor = User.objects.create_user(
            'Roger Requestor',
            'rr@example.com',
            'password'
        )

    def test_add_revocation_new(self):
        my_revocation = StandingsRevocation.add_revocation(            
            1001, 
            CHARACTER_TYPE_ID
        )
        self.assertIsInstance(my_revocation, StandingsRevocation)

    def test_add_request_already_exists(self):
        StandingsRevocation.add_revocation(            
            1001, CHARACTER_TYPE_ID
        )
        my_revocation_2 = StandingsRevocation.add_revocation(            
            1001, CHARACTER_TYPE_ID
        )
        self.assertIsNone(my_revocation_2)

    def test_undo_revocation_that_exists(self):
        StandingsRevocation.add_revocation(            
            1001, CHARACTER_TYPE_ID
        )
        my_revocation = StandingsRevocation.undo_revocation(
            1001, self.user_requestor
        )
        self.assertEqual(my_revocation.user, self.user_requestor)
        self.assertEqual(my_revocation.contactID, 1001)
        self.assertEqual(my_revocation.contactType, CHARACTER_TYPE_ID)

    def test_undo_revocation_that_not_exists(self):        
        my_revocation = StandingsRevocation.undo_revocation(
            1001,            
            self.user_requestor
        )
        self.assertFalse(my_revocation)

    def test_check_standing_satisfied_but_deleted_for_neutral_check_only(self):
        my_revocation = StandingsRevocation.add_revocation(            
            1999, 
            CHARACTER_TYPE_ID
        )                
        self.assertTrue(
            my_revocation.check_standing_satisfied(check_only=True)
        )

    def test_check_standing_satisfied_but_deleted_for_neutral(self):
        my_revocation = StandingsRevocation.add_revocation(            
            1999, 
            CHARACTER_TYPE_ID
        )                
        self.assertTrue(my_revocation.check_standing_satisfied())
        self.assertTrue(my_revocation.effective)


class TestCharacterAssociation(TestCase):

    def setUp(self):
        ContactSet.objects.all().delete()
        EveNameCache.objects.all().delete()
        CharacterAssociation.objects.all().delete()
    
    @patch(MODULE_PATH + '.EveNameCache')
    def test_get_character_name_exists(self, mock_EveNameCache):
        mock_EveNameCache.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(
            character_id=1002,
            main_character_id=1001
        )
        self.assertEqual(my_assoc.character_name, 'Peter Parker')

    @patch(MODULE_PATH + '.EveNameCache')
    def test_get_character_name_not_exists(self, mock_EveNameCache):
        mock_EveNameCache.get_name.side_effect = get_entity_name        
        my_assoc = CharacterAssociation(
            character_id=1999,
            main_character_id=1001
        )
        self.assertIsNone(my_assoc.character_name)

    @patch(MODULE_PATH + '.EveNameCache')
    def test_get_main_character_name_exists(self, mock_EveNameCache):
        mock_EveNameCache.get_name.side_effect = get_entity_name
        my_assoc = CharacterAssociation(
            character_id=1002,
            main_character_id=1001
        )
        self.assertEqual(my_assoc.main_character_name, 'Bruce Wayne')

    @patch(MODULE_PATH + '.EveNameCache')
    def test_get_main_character_name_not_exists(self, mock_EveNameCache):
        mock_EveNameCache.get_name.side_effect = get_entity_name        
        my_assoc = CharacterAssociation(
            character_id=1002,
            main_character_id=19999
        )
        self.assertIsNone(my_assoc.main_character_name)

    @patch(MODULE_PATH + '.EveNameCache')
    def test_get_main_character_name_not_defined(self, mock_EveNameCache):
        mock_EveNameCache.get_name.side_effect = get_entity_name        
        my_assoc = CharacterAssociation(
            character_id=1002
        )
        self.assertIsNone(my_assoc.main_character_name)

    def test_get_api_expired_items(self):
        CharacterAssociation.objects.create(
            character_id=1002,
            main_character_id=1001
        )
        my_assoc_expired_1 = CharacterAssociation.objects.create(
            character_id=1003,
            main_character_id=1001
        )
        my_assoc_expired_1.updated -= timedelta(days=4)
        my_assoc_expired_1.save()
        my_assoc_expired_2 = CharacterAssociation.objects.create(
            character_id=1004,
            main_character_id=1001
        )
        my_assoc_expired_2.updated -= timedelta(days=5)
        my_assoc_expired_2.save()

        self.assertSetEqual(
            set(CharacterAssociation.get_api_expired_items()),
            {my_assoc_expired_1, my_assoc_expired_2}
        )

    def test_get_api_expired_items_selected(self):
        CharacterAssociation.objects.create(
            character_id=1002,
            main_character_id=1001
        )
        my_assoc_expired_1 = CharacterAssociation.objects.create(
            character_id=1003,
            main_character_id=1001
        )
        my_assoc_expired_1.updated -= timedelta(days=4)
        my_assoc_expired_1.save()
        my_assoc_expired_2 = CharacterAssociation.objects.create(
            character_id=1004,
            main_character_id=1001
        )
        my_assoc_expired_2.updated -= timedelta(days=5)
        my_assoc_expired_2.save()

        self.assertSetEqual(
            set(CharacterAssociation.get_api_expired_items(items_in=[1004])),
            {my_assoc_expired_2}
        )


class TestEveNameCache(TestCase):

    def setUp(self):
        ContactSet.objects.all().delete()
        EveNameCache.objects.all().delete()

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_name_from_api_when_table_is_empty(self, mock_EveEntityManager):
        mock_EveEntityManager.get_name_from_auth.return_value = None
        mock_EveEntityManager.get_name_from_api.return_value = 'Bruce Wayne'        
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_name_from_auth_when_table_is_empty(self, mock_EveEntityManager):
        mock_EveEntityManager.get_name_from_auth.return_value = 'Bruce Wayne'
        mock_EveEntityManager.get_name_from_api.side_effect = RuntimeError        
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_name_when_exists_in_cache(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_name_from_auth.side_effect = RuntimeError
        mock_EveEntityManager.get_name_from_api.side_effect = RuntimeError

        EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )        
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_name_that_not_exists(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_name_from_auth.return_value = None
        mock_EveEntityManager.get_name_from_api.return_value = None
        
        self.assertEqual(EveNameCache.get_name(1999), None)

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_name_when_cache_outdated(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_name_from_auth.return_value = None
        mock_EveEntityManager.get_name_from_api.return_value = 'Bruce Wayne'

        contact_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        AllianceStanding.objects.create(
            set=contact_set,
            contactID=3001,
            name='Dummy Alliance 1',
            standing=0
        )
        my_entity = EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )        
        my_entity.updated = timezone.now() - timedelta(days=31)
        my_entity.save()
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')
        self.assertEqual(
            mock_EveEntityManager.get_name_from_api.call_count,
            1
        )    

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_from_pilot_contacts(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_name_from_auth.side_effect = RuntimeError
        mock_EveEntityManager.get_name_from_api.side_effect = RuntimeError

        contact_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        PilotStanding.objects.create(
            set=contact_set,
            contactID=1001,
            name='Bruce Wayne',
            standing=0
        )                        
        self.assertEqual(EveNameCache.get_name(1001), 'Bruce Wayne')

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_from_corporation_contacts(self, mock_EveEntityManager):
        mock_EveEntityManager.get_name_from_auth.side_effect = RuntimeError
        mock_EveEntityManager.get_name_from_api.side_effect = RuntimeError

        contact_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        CorpStanding.objects.create(
            set=contact_set,
            contactID=2001,
            name='Dummy Corp 1',
            standing=0
        )                        
        self.assertEqual(EveNameCache.get_name(2001), 'Dummy Corp 1')

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_from_alliance_contacts(self, mock_EveEntityManager):
        mock_EveEntityManager.get_name_from_auth.side_effect = RuntimeError
        mock_EveEntityManager.get_name_from_api.side_effect = RuntimeError

        contact_set = ContactSet.objects.create(
            name='Dummy Set'
        )
        AllianceStanding.objects.create(
            set=contact_set,
            contactID=3001,
            name='Dummy Alliance 1',
            standing=0
        )                        
        self.assertEqual(EveNameCache.get_name(3001), 'Dummy Alliance 1')
        
    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_when_table_is_empty(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = get_entity_names

        entities = EveNameCache.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne',
                1002: 'Peter Parker',         
            }
        )
        self.assertListEqual(
            mock_EveEntityManager.get_names.call_args[0][0],
            [1001, 1002]
        )

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_from_cache(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = get_entity_names

        EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )
        EveNameCache.objects.create(
            entityID=1002,
            name='Peter Parker'
        )
        entities = EveNameCache.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne',
                1002: 'Peter Parker',         
            }
        )
        self.assertListEqual(
            mock_EveEntityManager.get_names.call_args[0][0],
            []
        )

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_from_cache_and_api(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = \
            get_entity_names

        EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )        
        entities = EveNameCache.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne',
                1002: 'Peter Parker',         
            }
        )
        self.assertListEqual(
            mock_EveEntityManager.get_names.call_args[0][0],
            [1002]
        )

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_from_expired_cache_and_api(self, mock_EveEntityManager):
        mock_EveEntityManager.get_names.side_effect = \
            get_entity_names

        my_entity = EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )        
        my_entity.updated = timezone.now() - timedelta(days=31)
        my_entity.save()
        entities = EveNameCache.get_names([1001, 1002])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne',
                1002: 'Peter Parker',         
            }
        )
        self.assertListEqual(
            mock_EveEntityManager.get_names.call_args[0][0],
            [1001, 1002]
        )

    """
    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_from_contacts(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = \
            get_entity_names

        contact_set = ContactSet.objects.create(
            name='Dummy Pilots Set'
        )
        PilotStanding.objects.create(
            set=contact_set
            contactID=1001,
            name='Bruce Wayne',
            standing=0
        )                
        entities = EveNameCache.get_names([1001])
        self.assertDictEqual(
            entities,
            {
                1001: 'Bruce Wayne'
            }
        ) 
        self.assertListEqual(
            mock_EveEntityManager.get_names.call_args[0][0],
            []
        )       
    """

    @patch(MODULE_PATH + '.EveEntityManager')
    def test_get_names_that_dont_exist(self, mock_EveEntityManager):        
        mock_EveEntityManager.get_names.side_effect = \
            get_entity_names
    
        self.assertEqual(len(EveNameCache.get_names([1999])), 0)
        
    def test_cache_timeout(self):
        my_entity = EveNameCache(
            entityID=1001,
            name='Bruce Wayne'            
        )
        # no cache timeout when added recently
        my_entity.updated = timezone.now()
        self.assertFalse(my_entity.cache_timeout())

        # cache timeout for entries older than 30 days
        my_entity.updated = timezone.now() - timedelta(days=31)
        self.assertTrue(my_entity.cache_timeout())

    def test_update_name(self):
        my_entity = EveNameCache.objects.create(
            entityID=1001,
            name='Bruce Wayne'
        )
        EveNameCache.update_name(1001, 'Batman')
        my_entity.refresh_from_db()
        self.assertEqual(my_entity.name, 'Batman')
