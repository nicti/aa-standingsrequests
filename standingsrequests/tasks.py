import datetime as dt
from typing import Optional

from celery import Task, chain, shared_task

from django.contrib.auth.models import User
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .app_settings import SR_STANDINGS_STALE_HOURS, SR_SYNC_BLUE_ALTS_ENABLED
from .core import app_config
from .models import (
    CharacterAffiliation,
    ContactSet,
    CorporationDetails,
    StandingRequest,
    StandingRevocation,
)

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

TASK_DEFAULT_PRIORITY = 6
TASK_LOW_PRIORITY = 8


@shared_task(name="standings_requests.update_all", bind=True)
def update_all(self, user_pk: int = None):
    """Update all standings and affiliations."""
    priority = _determine_task_priority(self) or TASK_DEFAULT_PRIORITY
    tasks = [
        standings_update.si().set(priority=priority),
        update_associations_api.si().set(priority=priority),
    ]
    if user_pk:
        tasks.append(report_result_to_user.si(user_pk).set(priority=priority))

    chain(tasks).delay()


@shared_task(name="standings_requests.report_result_to_user")
def report_result_to_user(user_pk: int):
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.warning("Can not find a user with pk %d", user_pk)
        return

    source_entity = app_config.standings_source_entity()
    notify(
        user,
        _("%s: Standings loaded") % __title__,
        _("Standings have been successfully loaded for %s") % source_entity.name,
        level="success",
    )


@shared_task(name="standings_requests.standings_update", bind=True)
def standings_update(self):
    """Updates standings from ESI"""
    logger.info("Standings API update started")
    contact_set: Optional[ContactSet] = ContactSet.objects.create_new_from_api()
    if not contact_set:
        raise RuntimeError(
            "Standings API update returned None (API error probably),"
            "aborting standings update"
        )

    priority = _determine_task_priority(self) or TASK_DEFAULT_PRIORITY

    tasks = []

    if SR_SYNC_BLUE_ALTS_ENABLED:
        tasks.append(
            generate_standing_requests_for_blue_alts.si(contact_set.pk).set(
                priority=priority
            )
        )

    tasks.append(process_standing_requests.si().set(priority=priority))
    tasks.append(process_standing_revocations.si().set(priority=priority))

    chain(tasks).delay()


@shared_task
def generate_standing_requests_for_blue_alts(contact_set_pk: int):
    """Generate standing requests for blue alts."""
    contact_set = ContactSet.objects.get(pk=contact_set_pk)
    contact_set.generate_standing_requests_for_blue_alts()


@shared_task
def process_standing_requests():
    """Process standings requests."""
    StandingRequest.objects.process_requests()


@shared_task
def process_standing_revocations():
    """Process standing revocations."""
    StandingRevocation.objects.process_requests()


@shared_task(name="standings_requests.validate_requests")
def validate_requests():
    """Validate standings requests."""
    count = StandingRequest.objects.validate_requests()
    logger.info("Dealt with %d invalid standings requests", count)


@shared_task(name="standings_requests.update_associations_api", bind=True)
def update_associations_api(self):
    """Update character affiliations from ESI and relations to Eve Characters"""
    priority = _determine_task_priority(self) or TASK_DEFAULT_PRIORITY
    update_character_affiliations_from_esi.apply_async(priority=priority)
    update_character_affiliations_to_auth.apply_async(priority=priority)
    update_all_corporation_details.apply_async(priority=priority)


@shared_task
def update_character_affiliations_from_esi():
    CharacterAffiliation.objects.update_from_esi()
    logger.info("Finished character affiliations from ESI.")


@shared_task
def update_character_affiliations_to_auth():
    CharacterAffiliation.objects.update_evecharacter_relations()
    logger.info("Finished updating character affiliations to Auth.")


@shared_task(bind=True)
def update_all_corporation_details(self):
    existing_corporation_ids = (
        CorporationDetails.objects.corporation_ids_from_contacts()
    )
    CorporationDetails.objects.exclude(
        corporation_id__in=existing_corporation_ids
    ).delete()

    if not existing_corporation_ids:
        logger.info("No corporations to update.")
        return

    priority = _determine_task_priority(self) or TASK_DEFAULT_PRIORITY
    for corporation_id in existing_corporation_ids:
        update_corporation_detail.apply_async(args=[corporation_id], priority=priority)

    logger.info(
        "Started updating corporation details for %d corporations.",
        len(existing_corporation_ids),
    )


@shared_task
def update_corporation_detail(corporation_id: int):
    CorporationDetails.objects.update_or_create_from_esi(corporation_id)


@shared_task(name="standings_requests.purge_stale_data", bind=True)
def purge_stale_data(self):
    """Delete all stale contact sets, but always keep the newest."""
    try:
        latest_standings = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        logger.warning("No ContactSets available, nothing to delete")
        return

    cutoff_date = now() - dt.timedelta(hours=SR_STANDINGS_STALE_HOURS)
    stale_contacts_qs = ContactSet.objects.filter(date__lt=cutoff_date).exclude(
        id=latest_standings.id
    )
    stale_objs_count = stale_contacts_qs.count()
    if not stale_objs_count:
        logger.debug("No ContactSets to delete")
        return

    logger.info("Found %d stale contact sets to purge", stale_objs_count)
    priority = _determine_task_priority(self) or TASK_LOW_PRIORITY
    tasks = [
        purge_contact_set.si(obj.pk).set(priority=priority) for obj in stale_contacts_qs
    ]
    chain(tasks).delay()


@shared_task
def purge_contact_set(contact_set_pk: int):
    obj = ContactSet.objects.filter(pk=contact_set_pk)
    obj.delete()


def _determine_task_priority(task_obj: Task) -> Optional[int]:
    """Return priority of give task or None if not defined."""
    properties = task_obj.request.get("properties") or {}
    return properties.get("priority")
