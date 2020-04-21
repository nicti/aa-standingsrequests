import logging
import datetime

from celery import shared_task, chain

from django.utils import timezone

from . import __title__
from .app_settings import SR_STANDINGS_STALE_HOURS, SR_REVOCATIONS_STALE_DAYS
from .managers.standings import StandingsManager
from .models import ContactSet, StandingsRevocation
from .models import PilotStanding, CorpStanding, AllianceStanding, ContactLabel
from .utils import LoggerAddTag

logger = LoggerAddTag(logging.getLogger(__name__), __title__)


@shared_task(name="standings_requests.standings_update")
def standings_update():    
    logger.info("Standings API update started")
    try:
        st = StandingsManager.api_update_alliance_standings()
        if st is None:
            logger.warn(
                'Standings API update returned None (API error probably),'
                'aborting standings update'
            )
        else:
            StandingsManager.process_pending_standings()
    
    except Exception as ex:
        logger.exception('Failed to execute standings_update', ex)


@shared_task(name="standings_requests.validate_standings_requests")
def validate_standings_requests():
    logger.info("Validating standings request running")
    count = StandingsManager.validate_standings_requests()
    logger.info("Deleted {0} standings requests".format(count))


@shared_task(name="standings_requests.update_associations_auth")
def update_associations_auth():
    """
    Update associations from local auth data (Main character, corporations)
    """
    logger.info("Associations updating from Auth")
    StandingsManager.update_character_associations_auth()
    logger.info("Finished Associations update from Auth")


@shared_task(name="standings_requests.update_associations_api")
def update_associations_api():
    """
    Update character associations from the EVE API (corporations)
    """
    logger.info("Associations updating from EVE API")
    StandingsManager.update_character_associations_api()
    logger.info("Finished associations update from EVE API")


@shared_task(name="standings_requests.purge_stale_data")
def purge_stale_data():
    """
    Delete all the data which is beyond its useful life. 
    There is no harm in disabling this if you wish to keep everything.
    """
    my_chain = chain([
        purge_stale_standings_data.si(),
        purge_stale_revocations.si(),
    ])
    my_chain.delay()


@shared_task
def purge_stale_standings_data():
    """Deletes all stale (=older than threshold hours) contact sets 
    except the last remaining contact set
    """
    logger.info("Purging stale standings data")
    cutoff_date = \
        timezone.now() - datetime.timedelta(hours=SR_STANDINGS_STALE_HOURS)
    try:
        latest_standings = ContactSet.objects.latest()    
        standings_qs = ContactSet.objects\
            .filter(date__lt=cutoff_date)\
            .exclude(id=latest_standings.id)
        if standings_qs.exists():
            logger.debug("Deleting old ContactSets")
            # we can't just do standigs.delete() 
            # because with lots of them it uses lots of memory
            # lets go over them one by one and delete
            for contact_set in standings_qs:                
                PilotStanding.objects.filter(set=contact_set).delete()
                CorpStanding.objects.filter(set=contact_set).delete()
                AllianceStanding.objects.filter(set=contact_set).delete()
                ContactLabel.objects.filter(set=contact_set).delete()

            standings_qs.delete()
        else:
            logger.debug("No ContactSets to delete")
    
    except ContactSet.DoesNotExist:
        logger.warn("No ContactSets available, nothing to delete")


@shared_task
def purge_stale_revocations():
    """removes revocations older than threshold"""
    logger.info("Purging stale revocations data")
    cutoff_date = \
        timezone.now() - datetime.timedelta(days=SR_REVOCATIONS_STALE_DAYS)
    revocations_qs = StandingsRevocation.objects\
        .exclude(effective=False)\
        .filter(effectiveDate__lt=cutoff_date)
    count = revocations_qs.count()
    revocations_qs.delete()
    logger.debug("Deleted %d standings revocations", count)
