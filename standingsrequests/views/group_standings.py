from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from standingsrequests import __title__
from standingsrequests.app_settings import SR_PAGE_CACHE_SECONDS
from standingsrequests.core import BaseConfig
from standingsrequests.models import ContactSet, ContactType, StandingRequest

from ._common import DEFAULT_ICON_SIZE, add_common_context

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@login_required
@permission_required("standingsrequests.view")
def view_groups_standings(request):
    logger.debug("view_group_standings called by %s", request.user)
    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contact_set = None
    finally:
        organization = BaseConfig.standings_source_entity()
        last_update = contact_set.date if contact_set else None

    if contact_set:
        groups_count = (
            contact_set.contacts.filter_corporations()
            | contact_set.contacts.filter_alliances()
        ).count()

    else:
        groups_count = None
    context = {
        "lastUpdate": last_update,
        "organization": organization,
        "groups_count": groups_count,
    }
    return render(
        request,
        "standingsrequests/group_standings.html",
        add_common_context(request, context),
    )


@cache_page(SR_PAGE_CACHE_SECONDS)
@login_required
@permission_required("standingsrequests.view")
def view_groups_standings_json(request):
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()
    corporations_qs = (
        contacts.contacts.filter_corporations()
        .select_related(
            "eve_entity",
            "eve_entity__corporation_details",
            "eve_entity__corporation_details__alliance",
            "eve_entity__corporation_details__faction",
        )
        .prefetch_related("labels")
        .order_by("eve_entity__name")
    )
    corporations_data = list()
    standings_requests = {
        obj.contact_id: obj
        for obj in (
            StandingRequest.objects.filter(
                contact_type_id=ContactType.corporation_id
            ).filter(
                contact_id__in=list(
                    corporations_qs.values_list("eve_entity_id", flat=True)
                )
            )
        )
    }
    for contact in corporations_qs:
        try:
            corporation_details = contact.eve_entity.corporation_details
        except (ObjectDoesNotExist, AttributeError):
            alliance_id = None
            alliance_name = "?"
            faction_id = None
            faction_name = "?"
        else:
            alliance = corporation_details.alliance
            if alliance:
                alliance_id = alliance.id
                alliance_name = alliance.name
            else:
                alliance_id = None
                alliance_name = ""
            faction = corporation_details.faction
            if faction:
                faction_id = faction.id
                faction_name = faction.name
            else:
                faction_id = None
                faction_name = ""
        try:
            standing_request = standings_requests[contact.eve_entity_id]
            user = standing_request.user
            main = user.profile.main_character
        except (KeyError, AttributeError, ObjectDoesNotExist):
            main_character_name = ""
            main_character_ticker = ""
            main_character_icon_url = ""
            state_name = ""
        else:
            main_character_name = main.character_name if main else ""
            main_character_ticker = main.corporation_ticker if main else ""
            main_character_icon_url = (
                main.portrait_url(DEFAULT_ICON_SIZE) if main else ""
            )
            state_name = user.profile.state.name

        labels = [label.name for label in contact.labels.all()]
        corporations_data.append(
            {
                "corporation_id": contact.eve_entity_id,
                "corporation_name": contact.eve_entity.name,
                "corporation_icon_url": contact.eve_entity.icon_url(DEFAULT_ICON_SIZE),
                "alliance_id": alliance_id,
                "alliance_name": alliance_name,
                "faction_id": faction_id,
                "faction_name": faction_name,
                "standing": contact.standing,
                "labels": labels,
                "state": state_name,
                "main_character_name": main_character_name,
                "main_character_ticker": main_character_ticker,
                "main_character_icon_url": main_character_icon_url,
            }
        )
    alliances_data = list()
    for contact in (
        contacts.contacts.filter_alliances()
        .select_related("eve_entity")
        .prefetch_related("labels")
        .order_by("eve_entity__name")
    ):
        alliances_data.append(
            {
                "alliance_id": contact.eve_entity_id,
                "alliance_name": contact.eve_entity.name,
                "alliance_icon_url": contact.eve_entity.icon_url(DEFAULT_ICON_SIZE),
                "standing": contact.standing,
                "labels": [label.name for label in contact.labels.all()],
            }
        )
    my_groups_data = {"corps": corporations_data, "alliances": alliances_data}
    return JsonResponse(my_groups_data, safe=False)
