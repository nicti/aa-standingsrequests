from datetime import timedelta

from celery import chain, shared_task

from django.contrib.auth.models import User
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .app_settings import SR_STANDINGS_STALE_HOURS, SR_SYNC_BLUE_ALTS_ENABLED
from .models import (
    AllianceContact,
    CharacterAssociation,
    CharacterContact,
    ContactLabel,
    ContactSet,
    CorporationContact,
    StandingRequest,
    StandingRevocation,
)

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@shared_task(name="standings_requests.update_all")
def update_all(user_pk: int = None):
    """Updates standings, names cache and associations"""
    my_chain = chain(
        [
            standings_update.si(),
            update_associations_auth.si(),
            update_associations_api.si(),
            report_result_to_user.si(user_pk),
        ]
    )
    my_chain.delay()


@shared_task(name="standings_requests.report_result_to_user")
def report_result_to_user(user_pk: int = None):
    if user_pk:
        try:
            user = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            logger.warning("Can not find a user with pk %d", user_pk)
            return
        else:
            source_entity = ContactSet.standings_source_entity()
            notify(
                user,
                _("%s: Standings loaded" % __title__),
                _(
                    "Standings have been successfully loaded for %s"
                    % source_entity.name
                ),
                level="success",
            )


@shared_task(name="standings_requests.standings_update")
def standings_update():
    """Updates standings from ESI"""
    logger.info("Standings API update started")
    contact_set = ContactSet.objects.create_new_from_api()
    if not contact_set:
        logger.warn(
            "Standings API update returned None (API error probably),"
            "aborting standings update"
        )
    else:
        if SR_SYNC_BLUE_ALTS_ENABLED:
            contact_set.generate_standing_requests_for_blue_alts()
        StandingRequest.objects.process_requests()
        StandingRevocation.objects.process_requests()


@shared_task(name="standings_requests.validate_requests")
def validate_requests():
    logger.info("Validating standings request running")
    count = StandingRequest.objects.validate_requests()
    logger.info("Dealt with %d invalid standings requests", count)


@shared_task(name="standings_requests.update_associations_auth")
def update_associations_auth():
    """Update associations from local auth data (Main character, corporations)"""
    logger.info("Associations updating from Auth")
    CharacterAssociation.objects.update_from_auth()
    logger.info("Finished Associations update from Auth")


@shared_task(name="standings_requests.update_associations_api")
def update_associations_api():
    """Update character associations from the EVE API (corporations)"""
    logger.info("Associations updating from EVE API")
    CharacterAssociation.objects.update_from_api()
    logger.info("Finished associations update from EVE API")


@shared_task(name="standings_requests.purge_stale_data")
def purge_stale_data():
    """Delete all the data which is beyond its useful life.
    There is no harm in disabling this if you wish to keep everything.
    """
    my_chain = chain([purge_stale_standings_data.si()])
    my_chain.delay()


@shared_task
def purge_stale_standings_data():
    """Deletes all stale (=older than threshold hours) contact sets
    except the last remaining contact set
    """
    logger.info("Purging stale standings data")
    cutoff_date = now() - timedelta(hours=SR_STANDINGS_STALE_HOURS)
    try:
        latest_standings = ContactSet.objects.latest()
        stale_contacts_qs = ContactSet.objects.filter(date__lt=cutoff_date).exclude(
            id=latest_standings.id
        )
        if stale_contacts_qs.exists():
            logger.debug("Deleting old ContactSets")
            # we can't just do standigs.delete()
            # because with lots of them it uses lots of memory
            # lets go over them one by one and delete
            for contact_set in stale_contacts_qs:
                CharacterContact.objects.filter(contact_set=contact_set).delete()
                CorporationContact.objects.filter(contact_set=contact_set).delete()
                AllianceContact.objects.filter(contact_set=contact_set).delete()
                ContactLabel.objects.filter(contact_set=contact_set).delete()

            stale_contacts_qs.delete()
        else:
            logger.debug("No ContactSets to delete")

    except ContactSet.DoesNotExist:
        logger.warn("No ContactSets available, nothing to delete")
