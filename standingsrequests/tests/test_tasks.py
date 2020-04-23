from datetime import timedelta
from unittest.mock import patch

from celery import Celery

from django.utils.timezone import now

from standingsrequests.models import ContactSet, StandingsRevocation
from standingsrequests.tasks import (
    standings_update,
    validate_standings_requests,
    update_associations_api,
    update_associations_auth,
    purge_stale_data,
    purge_stale_standings_data,
    purge_stale_revocations
)
from standingsrequests.utils import NoSocketsTestCase, set_test_logger

from .entity_type_ids import CHARACTER_TYPE_ID
from .my_test_data import create_contacts_set

MODULE_PATH = 'standingsrequests.tasks'
logger = set_test_logger(MODULE_PATH, __file__)
app = Celery('myauth')


@patch(MODULE_PATH + '.StandingsManager')
class TestStandingsUpdate(NoSocketsTestCase):
    
    def test_can_update_standings(self, mock_StandingsManager):
        standings_update()
        self.assertTrue(
            mock_StandingsManager.api_update_alliance_standings.called
        )
        self.assertTrue(
            mock_StandingsManager.process_pending_standings.called
        )

    def test_can_handle_api_error(self, mock_StandingsManager):
        mock_StandingsManager.api_update_alliance_standings.return_value = None
        standings_update()
        self.assertTrue(
            mock_StandingsManager.api_update_alliance_standings.called
        )
        self.assertFalse(
            mock_StandingsManager.process_pending_standings.called
        )

    def test_can_handle_exception(self, mock_StandingsManager):
        mock_StandingsManager.api_update_alliance_standings.side_effect = \
            RuntimeError
        standings_update()
        self.assertTrue(
            mock_StandingsManager.api_update_alliance_standings.called
        )
        self.assertFalse(
            mock_StandingsManager.process_pending_standings.called
        )


@patch(MODULE_PATH + '.StandingsManager')
class TestOtherTasks(NoSocketsTestCase):

    def test_validate_standings_requests(self, mock_StandingsManager):
        validate_standings_requests()
        self.assertTrue(
            mock_StandingsManager.validate_standings_requests.called
        )

    def test_update_associations_auth(self, mock_StandingsManager):
        update_associations_auth()
        self.assertTrue(
            mock_StandingsManager.update_character_associations_auth.called
        )
    
    def test_update_associations_api(self, mock_StandingsManager):
        update_associations_api()
        self.assertTrue(
            mock_StandingsManager.update_character_associations_api.called
        )


class TestPurgeTasks(NoSocketsTestCase):

    @patch(MODULE_PATH + '.purge_stale_standings_data')
    @patch(MODULE_PATH + '.purge_stale_revocations')
    def test_purge_stale_data(
        self, mock_purge_stale_standings_data, mock_purge_stale_revocations
    ):
        app.conf.task_always_eager = True
        purge_stale_data()
        app.conf.task_always_eager = False
                
        self.assertTrue(mock_purge_stale_standings_data.si.called)
        self.assertTrue(mock_purge_stale_revocations.si.called)

    
@patch(MODULE_PATH + '.SR_STANDINGS_STALE_HOURS', 48)
class TestPurgeStaleStandingData(NoSocketsTestCase):

    def setUp(self):
        ContactSet.objects.all().delete()

    def test_do_nothing_if_not_contacts_sets(self):
        purge_stale_standings_data()

    def test_one_younger_set_no_purge(self):
        set_1 = create_contacts_set()        
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list('pk', flat=True))
        expected = {set_1.pk}
        self.assertSetEqual(current_pks, expected)

    def test_one_older_set_no_purge(self):
        set_1 = create_contacts_set()
        set_1.date = now() - timedelta(hours=48, seconds=1)
        set_1.save()
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list('pk', flat=True))
        expected = {set_1.pk}
        self.assertSetEqual(current_pks, expected)

    def test_two_younger_sets_no_purge(self):
        set_1 = create_contacts_set()
        set_2 = create_contacts_set()        
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list('pk', flat=True))
        expected = {set_1.pk, set_2.pk}
        self.assertSetEqual(current_pks, expected)

    def test_two_sets_young_and_old_purge_older_only(self):
        set_1 = create_contacts_set()
        set_1.date = now() - timedelta(hours=48, seconds=1)
        set_1.save()
        set_2 = create_contacts_set()        
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list('pk', flat=True))
        expected = {set_2.pk}
        self.assertSetEqual(current_pks, expected)

    def test_two_older_set_purge_older_one_only(self):
        set_1 = create_contacts_set()
        set_1.date = now() - timedelta(hours=48, seconds=2)
        set_1.save()
        set_2 = create_contacts_set()
        set_1.date = now() - timedelta(hours=48, seconds=1)
        set_1.save()
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list('pk', flat=True))
        expected = {set_2.pk}
        self.assertSetEqual(current_pks, expected)


@patch(MODULE_PATH + '.SR_REVOCATIONS_STALE_DAYS', 7)
class TestPurgeStaleRevocations(NoSocketsTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_contacts_set        

    def setUp(self):
        StandingsRevocation.objects.all().delete()

    def test_no_revocation_exists_no_purge(self):
        purge_stale_revocations()

    def test_one_younger_revocation_exists_no_purge(self):
        revocation_1 = StandingsRevocation.add_revocation(            
            1001, CHARACTER_TYPE_ID
        )
        revocation_1.mark_standing_effective()
        purge_stale_revocations()
        current_pks = set(
            StandingsRevocation.objects.values_list('pk', flat=True)
        )
        expected = {revocation_1.pk}
        self.assertSetEqual(current_pks, expected)
    
    def test_one_older_revocation_is_purged(self):
        revocation_1 = StandingsRevocation.add_revocation(            
            1001, CHARACTER_TYPE_ID
        )        
        revocation_1.effectiveDate = \
            now() - timedelta(days=7, seconds=1)
        revocation_1.effective = True
        revocation_1.save()
        purge_stale_revocations()
        current_pks = set(
            StandingsRevocation.objects.values_list('pk', flat=True)
        )
        expected = set()
        self.assertSetEqual(current_pks, expected)

    def test_one_younger_one_older_revocation_purge_older_only(self):
        revocation_1 = StandingsRevocation.add_revocation(
            1001, CHARACTER_TYPE_ID
        )
        revocation_1.effectiveDate = \
            now() - timedelta(days=7, seconds=1)
        revocation_1.effective = True
        revocation_1.save()
        revocation_2 = StandingsRevocation.add_revocation(
            1002, CHARACTER_TYPE_ID
        )
        revocation_2.mark_standing_effective()
        purge_stale_revocations()
        current_pks = set(
            StandingsRevocation.objects.values_list('pk', flat=True)
        )
        expected = {revocation_2.pk}
        self.assertSetEqual(current_pks, expected)
    
    def test_two_older_revocations_are_both_purged(self):
        revocation_1 = StandingsRevocation.add_revocation(
            1001, CHARACTER_TYPE_ID
        )
        revocation_1.effectiveDate = \
            now() - timedelta(days=7, seconds=1)
        revocation_1.effective = True
        revocation_1.save()
        revocation_2 = StandingsRevocation.add_revocation(
            1002, CHARACTER_TYPE_ID
        )
        revocation_2.effectiveDate = \
            now() - timedelta(days=7, seconds=1)
        revocation_2.effective = True
        revocation_2.save()
        purge_stale_revocations()
        current_pks = set(
            StandingsRevocation.objects.values_list('pk', flat=True)
        )
        expected = set()
        self.assertSetEqual(current_pks, expected)
