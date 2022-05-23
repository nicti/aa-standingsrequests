from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.html import format_html
from django.views.decorators.cache import cache_page
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from standingsrequests import __title__
from standingsrequests.app_settings import SR_PAGE_CACHE_SECONDS
from standingsrequests.core import BaseConfig
from standingsrequests.helpers.writers import UnicodeWriter
from standingsrequests.models import ContactSet, StandingRequest

from ._common import DEFAULT_ICON_SIZE, add_common_context

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@login_required
@permission_required("standingsrequests.view")
def view_pilots_standings(request):
    logger.debug("view_pilot_standings called by %s", request.user)
    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contact_set = None
    finally:
        organization = BaseConfig.standings_source_entity()
        last_update = contact_set.date if contact_set else None
        pilots_count = contact_set.contacts.count() if contact_set else None

    context = {
        "lastUpdate": last_update,
        "organization": organization,
        "pilots_count": pilots_count,
    }
    return render(
        request,
        "standingsrequests/character_standings.html",
        add_common_context(request, context),
    )


@cache_page(SR_PAGE_CACHE_SECONDS)
@login_required
@permission_required("standingsrequests.view")
def view_pilots_standings_json(request):
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()
    character_contacts_qs = (
        contacts.contacts.filter_characters()
        .select_related(
            "eve_entity",
            "eve_entity__character_affiliation",
            "eve_entity__character_affiliation__corporation",
            "eve_entity__character_affiliation__alliance",
            "eve_entity__character_affiliation__faction",
            "eve_entity__character_affiliation__eve_character",
            "eve_entity__character_affiliation__eve_character__character_ownership__user",
            "eve_entity__character_affiliation__eve_character__character_ownership__user__profile__main_character",
            "eve_entity__character_affiliation__eve_character__character_ownership__user__profile__state",
        )
        .prefetch_related("labels")
        .order_by("eve_entity__name")
    )
    characters_data = list()
    for contact in character_contacts_qs:
        character_icon_url = contact.eve_entity.icon_url(DEFAULT_ICON_SIZE)
        character_name_html = format_html(
            '<span class="text-nowrap">'
            '<img src="{}" class="img-circle" style="width:32px;height:32px"> {}'
            "</span>",
            contact.eve_entity.icon_url(),
            contact.eve_entity.name,
        )
        try:
            character = contact.eve_entity.character_affiliation.eve_character
            user = character.character_ownership.user
        except (AttributeError, ObjectDoesNotExist):
            main = None
            state = ""
            main_character_name = ""
            main_character_ticker = ""
            main_character_icon_url = ""
            main_character_html = ""
        else:
            main = user.profile.main_character
            state = user.profile.state.name if user.profile.state else ""
            main_character_name = main.character_name
            main_character_ticker = main.corporation_ticker
            main_character_icon_url = main.portrait_url(DEFAULT_ICON_SIZE)
            main_character_html = format_html(
                '<span class="text-nowrap">'
                '<img src="{}" class="img-circle" style="width:32px;height:32px">'
                " [{}] {}"
                "</span>",
                main_character_icon_url,
                main_character_ticker,
                main_character_name,
            )
        try:
            assoc = contact.eve_entity.character_affiliation
        except (AttributeError, ObjectDoesNotExist):
            corporation_id = None
            corporation_name = "?"
            alliance_id = None
            alliance_name = "?"
            faction_id = None
            faction_name = "?"
        else:
            corporation_id = assoc.corporation.id
            corporation_name = assoc.corporation.name
            alliance_id = assoc.alliance.id if assoc.alliance else None
            alliance_name = assoc.alliance.name if assoc.alliance else ""
            faction_id = assoc.faction.id if assoc.faction else None
            faction_name = assoc.faction.name if assoc.faction else ""

        labels = [label.name for label in contact.labels.all()]
        characters_data.append(
            {
                "character_id": contact.eve_entity_id,
                "character_name": contact.eve_entity.name,
                "character_icon_url": character_icon_url,
                "character_name_html": {
                    "display": character_name_html,
                    "sort": contact.eve_entity.name,
                },
                "corporation_id": corporation_id,
                "corporation_name": corporation_name,
                "alliance_id": alliance_id,
                "alliance_name": alliance_name,
                "faction_id": faction_id,
                "faction_name": faction_name,
                "state": state,
                "main_character_name": main_character_name,
                "main_character_ticker": main_character_ticker,
                "main_character_icon_url": main_character_icon_url,
                "main_character_html": {
                    "display": main_character_html,
                    "sort": main_character_name,
                },
                "standing": contact.standing if contact.standing else "",
                "labels": labels,
                "labels_str": ", ".join(labels),
            }
        )
    return JsonResponse(characters_data, safe=False)


@login_required
@permission_required("standingsrequests.download")
def download_pilot_standings(request):
    logger.info("download_pilot_standings called by %s", request.user)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="standings.csv"'
    writer = UnicodeWriter(response)
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()
    writer.writerow(
        [
            "character_id",
            "character_name",
            "corporation_id",
            "corporation_name",
            "corporation_ticker",
            "alliance_id",
            "alliance_name",
            "has_scopes",
            "state",
            "main_character_name",
            "main_character_ticker",
            "standing",
            "labels",
        ]
    )

    # lets request make sure all info is there in bulk
    character_contacts = contacts.contacts.all().order_by("eve_entity__name")
    EveEntity.objects.bulk_resolve_names([p.contact_id for p in character_contacts])

    for pilot_standing in character_contacts:
        try:
            char = EveCharacter.objects.get(character_id=pilot_standing.contact_id)
        except EveCharacter.DoesNotExist:
            char = None
        main = ""
        state = ""
        try:
            ownership = CharacterOwnership.objects.get(character=char)
        except CharacterOwnership.DoesNotExist:
            main_character_name = ""
            main = None
        else:
            state = ownership.user.profile.state.name
            main = ownership.user.profile.main_character
            if main is None:
                main_character_name = ""
            else:
                main_character_name = main.character_name
        pilot = [
            pilot_standing.eve_entity_id,
            pilot_standing.eve_entity.name,
            char.corporation_id if char else "",
            char.corporation_name if char else "",
            char.corporation_ticker if char else "",
            char.alliance_id if char else "",
            char.alliance_name if char else "",
            StandingRequest.has_required_scopes_for_request(char),
            state,
            main_character_name,
            main.corporation_ticker if main else "",
            pilot_standing.standing,
            ", ".join([label.name for label in pilot_standing.labels.all()]),
        ]
        writer.writerow([str(v) if v is not None else "" for v in pilot])
    return response
