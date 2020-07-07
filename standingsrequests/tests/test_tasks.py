from datetime import timedelta
from unittest.mock import patch

from celery import Celery

from django.utils.timezone import now

from standingsrequests.models import ContactSet, StandingsRevocation
from standingsrequests.tasks import (
    standings_update,
    validate_requests,
    update_associations_api,
    update_associations_auth,
    purge_stale_data,
    purge_stale_standings_data,
    purge_stale_revocations,
)
from standingsrequests.utils import NoSocketsTestCase, set_test_logger

from .entity_type_ids import CHARACTER_TYPE_ID
from .my_test_data import create_contacts_set

MODULE_PATH = "standingsrequests.tasks"
logger = set_test_logger(MODULE_PATH, __file__)
app = Celery("myauth")


@patch(MODULE_PATH + ".StandingsRequest.objects.process_requests")
@patch(MODULE_PATH + ".StandingsRevocation.objects.process_requests")
@patch(MODULE_PATH + ".ContactSet.objects.create_new_from_api")
class TestStandingsUpdate(NoSocketsTestCase):
    def test_can_update_standings(
        self,
        mock_create_new_from_api,
        mock_requests_process_standings,
        mock_revocations_process_standings,
    ):
        standings_update()
        self.assertTrue(mock_create_new_from_api.called)
        self.assertTrue(mock_requests_process_standings.called)
        self.assertTrue(mock_revocations_process_standings.called)

    def test_can_handle_api_error(
        self,
        mock_create_new_from_api,
        mock_requests_process_standings,
        mock_revocations_process_standings,
    ):
        mock_create_new_from_api.return_value = None
        standings_update()
        self.assertTrue(mock_create_new_from_api.called)
        self.assertFalse(mock_requests_process_standings.called)
        self.assertFalse(mock_revocations_process_standings.called)

    def test_can_handle_exception(
        self,
        mock_create_new_from_api,
        mock_requests_process_standings,
        mock_revocations_process_standings,
    ):
        mock_create_new_from_api.side_effect = RuntimeError
        standings_update()
        self.assertTrue(mock_create_new_from_api.called)
        self.assertFalse(mock_requests_process_standings.called)
        self.assertFalse(mock_revocations_process_standings.called)


class TestOtherTasks(NoSocketsTestCase):
    @patch(MODULE_PATH + ".StandingsRequest.objects.validate_requests")
    def test_validate_standings_requests(self, mock_validate_standings_requests):
        validate_requests()
        self.assertTrue(mock_validate_standings_requests.called)

    @patch(MODULE_PATH + ".CharacterAssociation.objects.update_from_auth")
    def test_update_associations_auth(self, mock_update_character_associations_auth):
        update_associations_auth()
        self.assertTrue(mock_update_character_associations_auth.called)

    @patch(MODULE_PATH + ".CharacterAssociation.objects.update_from_api")
    def test_update_associations_api(self, mock_update_character_associations_api):
        update_associations_api()
        self.assertTrue(mock_update_character_associations_api.called)


class TestPurgeTasks(NoSocketsTestCase):
    @patch(MODULE_PATH + ".purge_stale_standings_data")
    @patch(MODULE_PATH + ".purge_stale_revocations")
    def test_purge_stale_data(
        self, mock_purge_stale_standings_data, mock_purge_stale_revocations
    ):
        app.conf.task_always_eager = True
        purge_stale_data()
        app.conf.task_always_eager = False

        self.assertTrue(mock_purge_stale_standings_data.si.called)
        self.assertTrue(mock_purge_stale_revocations.si.called)


@patch(MODULE_PATH + ".SR_STANDINGS_STALE_HOURS", 48)
class TestPurgeStaleStandingData(NoSocketsTestCase):
    def setUp(self):
        ContactSet.objects.all().delete()

    def test_do_nothing_if_not_contacts_sets(self):
        purge_stale_standings_data()

    def test_one_younger_set_no_purge(self):
        set_1 = create_contacts_set()
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
        expected = {set_1.pk}
        self.assertSetEqual(current_pks, expected)

    def test_one_older_set_no_purge(self):
        set_1 = create_contacts_set()
        set_1.date = now() - timedelta(hours=48, seconds=1)
        set_1.save()
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
        expected = {set_1.pk}
        self.assertSetEqual(current_pks, expected)

    def test_two_younger_sets_no_purge(self):
        set_1 = create_contacts_set()
        set_2 = create_contacts_set()
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
        expected = {set_1.pk, set_2.pk}
        self.assertSetEqual(current_pks, expected)

    def test_two_sets_young_and_old_purge_older_only(self):
        set_1 = create_contacts_set()
        set_1.date = now() - timedelta(hours=48, seconds=1)
        set_1.save()
        set_2 = create_contacts_set()
        purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
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
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
        expected = {set_2.pk}
        self.assertSetEqual(current_pks, expected)


@patch(MODULE_PATH + ".SR_REVOCATIONS_STALE_DAYS", 7)
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
        revocation_1 = StandingsRevocation.objects.add_revocation(
            1001, CHARACTER_TYPE_ID
        )
        revocation_1.mark_standing_effective()
        purge_stale_revocations()
        current_pks = set(StandingsRevocation.objects.values_list("pk", flat=True))
        expected = {revocation_1.pk}
        self.assertSetEqual(current_pks, expected)

    def test_one_older_revocation_is_purged(self):
        revocation_1 = StandingsRevocation.objects.add_revocation(
            1001, CHARACTER_TYPE_ID
        )
        revocation_1.effective_date = now() - timedelta(days=7, seconds=1)
        revocation_1.is_effective = True
        revocation_1.save()
        purge_stale_revocations()
        current_pks = set(StandingsRevocation.objects.values_list("pk", flat=True))
        expected = set()
        self.assertSetEqual(current_pks, expected)

    def test_one_younger_one_older_revocation_purge_older_only(self):
        revocation_1 = StandingsRevocation.objects.add_revocation(
            1001, CHARACTER_TYPE_ID
        )
        revocation_1.effective_date = now() - timedelta(days=7, seconds=1)
        revocation_1.is_effective = True
        revocation_1.save()
        revocation_2 = StandingsRevocation.objects.add_revocation(
            1002, CHARACTER_TYPE_ID
        )
        revocation_2.mark_standing_effective()
        purge_stale_revocations()
        current_pks = set(StandingsRevocation.objects.values_list("pk", flat=True))
        expected = {revocation_2.pk}
        self.assertSetEqual(current_pks, expected)

    def test_two_older_revocations_are_both_purged(self):
        revocation_1 = StandingsRevocation.objects.add_revocation(
            1001, CHARACTER_TYPE_ID
        )
        revocation_1.effective_date = now() - timedelta(days=7, seconds=1)
        revocation_1.is_effective = True
        revocation_1.save()
        revocation_2 = StandingsRevocation.objects.add_revocation(
            1002, CHARACTER_TYPE_ID
        )
        revocation_2.effective_date = now() - timedelta(days=7, seconds=1)
        revocation_2.is_effective = True
        revocation_2.save()
        purge_stale_revocations()
        current_pks = set(StandingsRevocation.objects.values_list("pk", flat=True))
        expected = set()
        self.assertSetEqual(current_pks, expected)
