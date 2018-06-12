from __future__ import unicode_literals

from django.utils import timezone

from .managers.standings import StandingsManager
from .models import ContactSet, StandingsRevocation
from celery import task
import logging
import datetime
from builtins import Exception

logger = logging.getLogger(__name__)


@task(name="standings_requests.standings_update")
def standings_update():
    logger.info("Standings API update running")

    # Run standings update first
    try:
        st = StandingsManager.api_update_alliance_standings()
        if st is None:
            logger.warn("Standings API update returned None (API error probably), aborting standings update")
            return

        StandingsManager.process_pending_standings()
    except Exception as e:
        logger.exception('Failed to executre standings_update')


@task(name="standings_requests.validate_standings_requests")
def validate_standings_requests():
    logger.info("Validating standings request running")
    count = StandingsManager.validate_standings_requests()
    logger.info("Deleted {0} standings requests".format(count))


@task(name="standings_requests.update_associations_auth")
def update_associations_auth():
    """
    Update associations from local auth data (Main character, corporations)
    """
    logger.info("Associations updating from Auth")
    StandingsManager.update_character_associations_auth()
    logger.info("Finished Associations update from Auth")


@task(name="standings_requests.update_associations_api")
def update_associations_api():
    """
    Update character associations from the EVE API (corporations)
    """
    logger.info("Associations updating from EVE API")
    StandingsManager.update_character_associations_api()
    logger.info("Finished associations update from EVE API")


@task(name="standings_requests.purge_stale_data")
def purge_stale_data():
    """
    Delete all the data which is beyond its useful life. There is no harm in disabling this
    if you wish to keep everything.
    """
    purge_stale_standings_data()
    purge_stale_revocations()


def purge_stale_standings_data():
    # Standings Data
    # Keep only the last 48 hours and at least one record (even if its stale)
    logger.info("Purging stale standings data")
    cutoff_date = timezone.now() - datetime.timedelta(hours=48)
    latest_standings = ContactSet.objects.latest()
    if latest_standings is not None:
        standings = ContactSet.objects.filter(date__lt=cutoff_date).exclude(id=latest_standings.id)

        if len(standings):
            logger.debug("Deleting Standings {0}".format(standings))
            standings.delete()
        else:
            logger.debug("No Standings to delete")
    else:
        logger.warn("No standings available, nothing to delete")


def purge_stale_revocations():
    logger.info("Purging stale revocations data")
    cutoff_date = timezone.now() - datetime.timedelta(days=7)
    revocs = StandingsRevocation.objects.exclude(effective=False).filter(effectiveDate__lt=cutoff_date)
    count = len(revocs)
    revocs.delete()
    logger.debug("Deleted {0} standings revocations".format(count))
