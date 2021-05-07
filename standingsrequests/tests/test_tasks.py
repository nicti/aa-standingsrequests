from datetime import timedelta
from unittest.mock import patch

from celery import Celery

from django.utils.timezone import now

from app_utils.testing import NoSocketsTestCase

from ..models import ContactSet
from ..tasks import (
    purge_stale_data,
    purge_stale_standings_data,
    standings_update,
    update_associations_api,
    update_associations_auth,
    validate_requests,
)
from .my_test_data import create_contacts_set

MODULE_PATH = "standingsrequests.tasks"

app = Celery("myauth")


@patch(MODULE_PATH + ".StandingRequest.objects.process_requests")
@patch(MODULE_PATH + ".StandingRevocation.objects.process_requests")
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


class TestOtherTasks(NoSocketsTestCase):
    @patch(MODULE_PATH + ".StandingRequest.objects.validate_requests")
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
    def test_purge_stale_data(self, mock_purge_stale_standings_data):
        app.conf.task_always_eager = True
        purge_stale_data()
        app.conf.task_always_eager = False

        self.assertTrue(mock_purge_stale_standings_data.si.called)


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
