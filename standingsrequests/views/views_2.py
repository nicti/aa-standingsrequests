from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_page
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag
from app_utils.views import HttpResponseNoContent

from .. import __title__
from ..app_settings import SR_NOTIFICATIONS_ENABLED, SR_PAGE_CACHE_SECONDS
from ..core import BaseConfig, ContactType
from ..helpers.evecharacter import EveCharacterHelper
from ..helpers.evecorporation import EveCorporation
from ..helpers.writers import UnicodeWriter
from ..models import ContactSet, StandingRequest, StandingRevocation
from .helpers import DEFAULT_ICON_SIZE, add_common_context

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


###########################
# Views character and groups #
###########################
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
        "standingsrequests/view_pilots.html",
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
        try:
            character = contact.eve_entity.character_affiliation.eve_character
            user = character.character_ownership.user
        except (AttributeError, ObjectDoesNotExist):
            main = None
            state = ""
            main_character_name = None
            main_character_ticker = None
            main_character_icon_url = None
        else:
            main = user.profile.main_character
            state = user.profile.state.name if user.profile.state else ""
            main_character_name = main.character_name
            main_character_ticker = main.corporation_ticker
            main_character_icon_url = main.portrait_url(DEFAULT_ICON_SIZE)
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
            faction_name = assoc.faction.name if assoc.faction else None

        labels = [label.name for label in contact.labels.all()]
        characters_data.append(
            {
                "character_id": contact.eve_entity_id,
                "character_name": contact.eve_entity.name,
                "character_icon_url": contact.eve_entity.icon_url(DEFAULT_ICON_SIZE),
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
                "standing": contact.standing,
                "labels": labels,
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
            state = ownership.user.profile.state.name
            main = ownership.user.profile.main_character
            if main is None:
                main_character_name = ""
            else:
                main_character_name = main.character_name
        except CharacterOwnership.DoesNotExist:
            main_character_name = ""
            main = None

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
        "standingsrequests/view_groups.html",
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


###################
# Manage requests #
###################


@login_required
@permission_required("standingsrequests.affect_standings")
def manage_standings(request):
    logger.debug("manage_standings called by %s", request.user)
    context = {
        "organization": BaseConfig.standings_source_entity(),
        "requests_count": StandingRequest.objects.pending_requests().count(),
        "revocations_count": StandingRevocation.objects.pending_requests().count(),
    }
    return render(
        request, "standingsrequests/manage.html", add_common_context(request, context)
    )


@login_required
@permission_required("standingsrequests.affect_standings")
def manage_get_requests_json(request):
    logger.debug("manage_get_requests_json called by %s", request.user)
    requests_qs = StandingRequest.objects.pending_requests()
    requests_data = _compose_standing_requests_data(requests_qs)
    return JsonResponse(requests_data, safe=False)


@login_required
@permission_required("standingsrequests.affect_standings")
def manage_get_revocations_json(request):
    logger.debug("manage_get_revocations_json called by %s", request.user)
    revocations_qs = StandingRevocation.objects.pending_requests()
    requests_data = _compose_standing_requests_data(revocations_qs)
    return JsonResponse(requests_data, safe=False)


def _compose_standing_requests_data(
    requests_qs: models.QuerySet, quick_check: bool = False
) -> list:
    """composes list of standings requests or revocations based on queryset
    and returns it
    """
    requests_qs = requests_qs.select_related(
        "user", "user__profile__state", "user__profile__main_character"
    )
    # preload data in bulk
    eve_characters = {
        character.character_id: character
        for character in EveCharacter.objects.filter(
            character_id__in=(
                requests_qs.exclude(
                    contact_type_id=ContactType.corporation_id
                ).values_list("contact_id", flat=True)
            )
        )
    }
    # TODO: remove EveCorporation usage
    eve_corporations = {
        corporation.corporation_id: corporation
        for corporation in EveCorporation.get_many_by_id(
            requests_qs.filter(contact_type_id=ContactType.corporation_id).values_list(
                "contact_id", flat=True
            )
        )
    }
    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = dict()
    else:
        all_contact_ids = set(eve_characters.keys()) | set(eve_corporations.keys())
        contacts = {
            obj.eve_entity_id: obj
            for obj in contact_set.contacts.prefetch_related("labels").filter(
                eve_entity_id__in=all_contact_ids
            )
        }
    requests_data = list()
    for req in requests_qs:
        main_character_name = ""
        main_character_ticker = ""
        main_character_icon_url = ""
        if req.user:
            state_name = req.user.profile.state.name
            main = req.user.profile.main_character
            if main:
                main_character_name = main.character_name
                main_character_ticker = main.corporation_ticker
                main_character_icon_url = main.portrait_url(DEFAULT_ICON_SIZE)
        else:
            state_name = "(no user)"

        if req.is_character:
            if req.contact_id in eve_characters:
                character = eve_characters[req.contact_id]
            else:
                # TODO: remove EveCharacterHelper usage
                character = EveCharacterHelper(req.contact_id)

            contact_name = character.character_name
            contact_icon_url = character.portrait_url(DEFAULT_ICON_SIZE)
            corporation_id = character.corporation_id
            corporation_name = (
                character.corporation_name if character.corporation_name else ""
            )
            corporation_ticker = (
                character.corporation_ticker if character.corporation_ticker else ""
            )
            alliance_id = character.alliance_id
            alliance_name = character.alliance_name if character.alliance_name else ""
            has_scopes = StandingRequest.has_required_scopes_for_request(
                character=character, user=req.user, quick_check=quick_check
            )

        elif req.is_corporation and req.contact_id in eve_corporations:
            corporation = eve_corporations[req.contact_id]
            contact_icon_url = corporation.logo_url(DEFAULT_ICON_SIZE)
            contact_name = corporation.corporation_name
            corporation_id = corporation.corporation_id
            corporation_name = corporation.corporation_name
            corporation_ticker = corporation.ticker
            alliance_id = None
            alliance_name = ""
            has_scopes = (
                not corporation.is_npc
                and corporation.user_has_all_member_tokens(
                    user=req.user, quick_check=quick_check
                )
            )

        else:
            contact_name = ""
            contact_icon_url = ""
            corporation_id = None
            corporation_name = ""
            corporation_ticker = ""
            alliance_id = None
            alliance_name = ""
            has_scopes = False

        if req.is_standing_revocation:
            reason = req.get_reason_display()
        else:
            reason = None
        try:
            my_contact = contacts[req.contact_id]
        except KeyError:
            labels = []
        else:
            labels = [obj.name for obj in my_contact.labels.all()]

        requests_data.append(
            {
                "contact_id": req.contact_id,
                "contact_name": contact_name,
                "contact_icon_url": contact_icon_url,
                "corporation_id": corporation_id,
                "corporation_name": corporation_name,
                "corporation_ticker": corporation_ticker,
                "alliance_id": alliance_id,
                "alliance_name": alliance_name,
                "request_date": req.request_date.isoformat(),
                "action_date": req.action_date.isoformat() if req.action_date else None,
                "has_scopes": has_scopes,
                "state": state_name,
                "reason": reason,
                "labels": sorted(labels),
                "main_character_name": main_character_name,
                "main_character_ticker": main_character_ticker,
                "main_character_icon_url": main_character_icon_url,
                "actioned": req.is_actioned,
                "is_effective": req.is_effective,
                "is_corporation": req.is_corporation,
                "is_character": req.is_character,
                "action_by": req.action_by.username if req.action_by else "(System)",
            }
        )

    return requests_data


@login_required
@permission_required("standingsrequests.affect_standings")
def manage_requests_write(request, contact_id):
    contact_id = int(contact_id)
    logger.debug("manage_requests_write called by %s", request.user)
    if request.method == "PUT":
        actioned = 0
        for r in StandingRequest.objects.filter(contact_id=contact_id):
            r.mark_actioned(request.user)
            actioned += 1
        if actioned > 0:
            return HttpResponseNoContent()
        return Http404()
    elif request.method == "DELETE":
        try:
            standing_request = StandingRequest.objects.get(contact_id=contact_id)
        except StandingRequest.DoesNotExist:
            return Http404()
        standing_request.delete()
        if SR_NOTIFICATIONS_ENABLED:
            entity_name = EveEntity.objects.resolve_name(contact_id)
            title = _("Standing request for %s rejected" % entity_name)
            message = _(
                "Your standing request for '%s' has been rejected by %s."
                % (entity_name, request.user)
            )
            notify(user=standing_request.user, title=title, message=message)

        return HttpResponseNoContent()
    return Http404()


@login_required
@permission_required("standingsrequests.affect_standings")
def manage_revocations_write(request, contact_id):
    contact_id = int(contact_id)
    logger.debug(
        "manage_revocations_write called by %s for contact_id %d",
        request.user,
        contact_id,
    )
    if request.method == "PUT":
        actioned = 0
        for r in StandingRevocation.objects.filter(contact_id=contact_id):
            r.mark_actioned(request.user)
            actioned += 1
        if actioned > 0:
            return HttpResponseNoContent()
        else:
            return Http404
    elif request.method == "DELETE":
        try:
            standing_revocation = StandingRevocation.objects.get(contact_id=contact_id)
        except StandingRevocation.DoesNotExist:
            return Http404()
        else:
            StandingRevocation.objects.filter(contact_id=contact_id).delete()
            if SR_NOTIFICATIONS_ENABLED and standing_revocation.user:
                entity_name = EveEntity.objects.resolve_name(contact_id)
                title = _("Standing revocation for %s rejected" % entity_name)
                message = _(
                    "Your standing revocation for '%s' "
                    "has been rejected by %s." % (entity_name, request.user)
                )
                notify(user=standing_revocation.user, title=title, message=message)

            return HttpResponseNoContent()

    else:
        return Http404()


###################
# View requests #
###################


@login_required
@permission_required("standingsrequests.affect_standings")
def view_active_requests(request):
    context = {
        "organization": BaseConfig.standings_source_entity(),
        "requests_count": _standing_requests_to_view().count(),
    }
    return render(
        request, "standingsrequests/requests.html", add_common_context(request, context)
    )


@login_required
@permission_required("standingsrequests.affect_standings")
def view_requests_json(request):

    response_data = _compose_standing_requests_data(
        _standing_requests_to_view(), quick_check=True
    )
    return JsonResponse(response_data, safe=False)


def _standing_requests_to_view() -> models.QuerySet:
    return (
        StandingRequest.objects.filter(is_effective=True)
        .select_related("user__profile")
        .order_by("-request_date")
    )
