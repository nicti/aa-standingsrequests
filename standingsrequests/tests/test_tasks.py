from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils.timezone import now

from app_utils.testing import NoSocketsTestCase

from .. import tasks
from ..models import ContactSet
from .my_test_data import create_contacts_set

MODULE_PATH = "standingsrequests.tasks"


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
        tasks.standings_update()
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
        tasks.standings_update()
        self.assertTrue(mock_create_new_from_api.called)
        self.assertFalse(mock_requests_process_standings.called)
        self.assertFalse(mock_revocations_process_standings.called)


class TestOtherTasks(NoSocketsTestCase):
    @patch(MODULE_PATH + ".StandingRequest.objects.validate_requests")
    def test_validate_standings_requests(self, mock_validate_standings_requests):
        tasks.validate_requests()
        self.assertTrue(mock_validate_standings_requests.called)

    @override_settings(
        CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True
    )
    @patch(MODULE_PATH + ".CorporationDetails.objects.update_or_create_from_esi")
    @patch(MODULE_PATH + ".CharacterAffiliation.objects.update_evecharacter_relations")
    @patch(MODULE_PATH + ".CharacterAffiliation.objects.update_from_esi")
    def test_update_associations_api(
        self,
        mock_update_from_esi,
        mock_update_evecharacter_relations,
        mock_update_or_create_from_esi,
    ):
        # when
        create_contacts_set()
        tasks.update_associations_api.delay()
        # then
        self.assertTrue(mock_update_from_esi.called)
        self.assertTrue(mock_update_evecharacter_relations.called)
        self.assertTrue(mock_update_or_create_from_esi.called)


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestPurgeTasks(NoSocketsTestCase):
    @patch(MODULE_PATH + ".purge_stale_standings_data")
    def test_purge_stale_data(self, mock_purge_stale_standings_data):
        tasks.purge_stale_data.delay()
        self.assertTrue(mock_purge_stale_standings_data.si.called)


@patch(MODULE_PATH + ".SR_STANDINGS_STALE_HOURS", 48)
class TestPurgeStaleStandingData(NoSocketsTestCase):
    def setUp(self):
        ContactSet.objects.all().delete()

    def test_do_nothing_if_not_contacts_sets(self):
        tasks.purge_stale_standings_data()

    def test_one_younger_set_no_purge(self):
        set_1 = create_contacts_set()
        tasks.purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
        expected = {set_1.pk}
        self.assertSetEqual(current_pks, expected)

    def test_one_older_set_no_purge(self):
        set_1 = create_contacts_set()
        set_1.date = now() - timedelta(hours=48, seconds=1)
        set_1.save()
        tasks.purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
        expected = {set_1.pk}
        self.assertSetEqual(current_pks, expected)

    def test_two_younger_sets_no_purge(self):
        set_1 = create_contacts_set()
        set_2 = create_contacts_set()
        tasks.purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
        expected = {set_1.pk, set_2.pk}
        self.assertSetEqual(current_pks, expected)

    def test_two_sets_young_and_old_purge_older_only(self):
        set_1 = create_contacts_set()
        set_1.date = now() - timedelta(hours=48, seconds=1)
        set_1.save()
        set_2 = create_contacts_set()
        tasks.purge_stale_standings_data()
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
        tasks.purge_stale_standings_data()
        current_pks = set(ContactSet.objects.values_list("pk", flat=True))
        expected = {set_2.pk}
        self.assertSetEqual(current_pks, expected)


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestUpdateAllCorporationDetails(NoSocketsTestCase):
    def setUp(self):
        create_contacts_set()

    @patch(MODULE_PATH + ".CorporationDetails.objects.update_or_create_from_esi")
    def test_should_update_all_corporation_details(
        self, mock_update_or_create_from_esi
    ):
        # when
        tasks.update_all_corporation_details.delay()
        # then
        called_corporation_ids = {
            obj[0][0] for obj in mock_update_or_create_from_esi.call_args_list
        }
        self.assertSetEqual(called_corporation_ids, {2001, 2003, 2004, 2102})
