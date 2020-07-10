from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveAllianceInfo, EveCharacter
from allianceauth.services.hooks import get_extension_logger

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from esi.decorators import token_required

from . import __title__
from .app_settings import (
    SR_CORPORATIONS_ENABLED,
    SR_OPERATION_MODE,
    STANDINGS_API_CHARID,
)
from .decorators import token_required_by_state
from .helpers.evecharacter import EveCharacterHelper
from .helpers.evecorporation import EveCorporation
from .helpers.eveentity import EveEntityHelper
from .helpers.view_cache import cache_get_or_set_character_standings_data
from .helpers.writers import UnicodeWriter
from .models import (
    CharacterContact,
    ContactSet,
    EveEntity,
    StandingRequest,
    StandingRevocation,
    models,
)
from .tasks import update_all
from .utils import LoggerAddTag, messages_plus

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

DEFAULT_ICON_SIZE = 32


class HttpResponseNoContent(HttpResponse):
    """
    Special HTTP response with no content, just headers.

    The content operations are ignored.
    """

    def __init__(self, content="", mimetype=None, status=None, content_type=None):
        super().__init__(status=204)

        # although we don't say a content-type, base class sets a
        # default one -- remove it, we're not returning content
        if "content-type" in self._headers:
            del self._headers["content-type"]

    def _set_content(self, value):
        pass

    def _get_content(self, value):
        pass


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def index_view(request):
    logger.debug("Start index_view request")
    context = {
        "app_title": __title__,
        "operation_mode": SR_OPERATION_MODE,
        "corporations_enabled": SR_CORPORATIONS_ENABLED,
    }
    return render(request, "standingsrequests/index.html", context)


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def partial_request_entities(request):
    logger.debug("Start partial_request_entities request")
    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        return render(
            request,
            "standingsrequests/error.html",
            {"app_title": __title__, "operation_mode": SR_OPERATION_MODE,},
        )

    eve_characters_qs = EveEntityHelper.get_characters_by_user(request.user)
    character_contacts_qs = contact_set.charactercontact_set.filter(
        contact_id__in=eve_characters_qs.values_list("character_id", flat=True)
    )
    characters_data = list()
    for character in eve_characters_qs:
        try:
            standing = character_contacts_qs.get(
                contact_id=character.character_id
            ).standing
        except CharacterContact.DoesNotExist:
            standing = None

        characters_data.append(
            {
                "character": character,
                "standing": standing,
                "pendingRequest": StandingRequest.objects.has_pending_request(
                    character.character_id
                ),
                "pendingRevocation": StandingRevocation.objects.has_pending_request(
                    character.character_id
                ),
                "requestActioned": StandingRequest.objects.has_actioned_request(
                    character.character_id
                ),
                "inOrganisation": ContactSet.is_character_in_organisation(
                    character.character_id
                ),
                "hasRequiredScopes": StandingRequest.has_required_scopes_for_request(
                    character
                ),
                "hasStanding": StandingRequest.objects.filter(
                    contact_id=character.character_id,
                    user=request.user,
                    is_effective=True,
                ).exists(),
            }
        )

    corporations_data = list()
    if SR_CORPORATIONS_ENABLED:
        corporation_ids = set(
            eve_characters_qs.exclude(
                corporation_id__in=ContactSet.corporation_ids_in_organization()
            )
            .exclude(alliance_id__in=ContactSet.alliance_ids_in_organization())
            .values_list("corporation_id", flat=True)
        )
        corporation_contacts_qs = contact_set.corporationcontact_set.filter(
            contact_id__in=corporation_ids
        )
        for corporation in EveCorporation.get_many_by_id(corporation_ids):
            if corporation and not corporation.is_npc:
                try:
                    standing = corporation_contacts_qs.get(
                        contact_id=corporation.corporation_id
                    ).standing
                except ObjectDoesNotExist:
                    standing = None

                corporations_data.append(
                    {
                        "token_count": corporation.member_tokens_count_for_user(
                            request.user
                        ),
                        "corp": corporation,
                        "standing": standing,
                        "pendingRequest": StandingRequest.objects.has_pending_request(
                            corporation.corporation_id
                        ),
                        "pendingRevocation": StandingRevocation.objects.has_pending_request(
                            corporation.corporation_id
                        ),
                        "requestActioned": StandingRequest.objects.has_actioned_request(
                            corporation.corporation_id
                        ),
                        "hasStanding": StandingRequest.objects.filter(
                            contact_id=corporation.corporation_id, is_effective=True,
                        ).exists(),
                    }
                )

        corporations_data.sort(key=lambda x: x["corp"].corporation_name)

    organization = ContactSet.standings_source_entity()
    render_items = {
        "app_title": __title__,
        "characters": characters_data,
        "corps": corporations_data,
        "operation_mode": SR_OPERATION_MODE,
        "corporations_enabled": SR_CORPORATIONS_ENABLED,
        "organization": organization,
        "organization_image_url": organization.icon_url(size=DEFAULT_ICON_SIZE),
        "authinfo": {"main_char_id": request.user.profile.main_character.character_id},
    }
    return render(
        request, "standingsrequests/partials/_request_entities.html", render_items
    )


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def request_pilot_standing(request, character_id):
    """For a user to request standings for their own pilots"""
    ok = True
    character_id = int(character_id)
    logger.debug(
        "Standings request from user %s for characterID %d", request.user, character_id
    )
    if not EveEntityHelper.is_character_owned_by_user(character_id, request.user):
        logger.warning(
            "User %s does not own Pilot ID %d, forbidden", request.user, character_id
        )
        ok = False
    elif StandingRequest.objects.has_pending_request(
        character_id
    ) or StandingRevocation.objects.has_pending_request(character_id):
        logger.warning("Contact ID %d already has a pending request", character_id)
        ok = False
    else:
        sr = StandingRequest.objects.add_request(
            user=request.user,
            contact_id=character_id,
            contact_type=StandingRequest.CHARACTER_CONTACT_TYPE,
        )
        try:
            contact_set = ContactSet.objects.latest()
        except ContactSet.DoesNotExist:
            logger.warning("Failed to get a contact set")
            ok = False
        else:
            if contact_set.character_has_satisfied_standing(character_id):
                sr.mark_standing_actioned(user=None)
                sr.mark_standing_effective()

    if not ok:
        messages_plus.warning(
            request,
            "An unexpected error occurred when trying to process "
            "your standing request for %s. Please try again."
            % EveEntity.objects.get_name(character_id),
        )

    return redirect("standingsrequests:index")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def remove_pilot_standing(request, character_id):
    """
    Handles both removing requests and removing existing standings
    """
    character_id = int(character_id)
    ok = True
    logger.debug(
        "remove_pilot_standing called by %s for character %d",
        request.user,
        character_id,
    )
    if not EveEntityHelper.is_character_owned_by_user(character_id, request.user):
        logger.warning(
            "User %s does not own Pilot ID %d, forbidden", request.user, character_id
        )
        ok = False
    elif ContactSet.is_character_in_organisation(character_id):
        logger.warning(
            "Character %d of user %s is in organization. Can not remove standing",
            character_id,
            request.user,
        )
        ok = False
    elif not StandingRevocation.objects.has_pending_request(character_id):
        if StandingRequest.objects.has_pending_request(
            character_id
        ) or StandingRequest.objects.has_actioned_request(character_id):
            logger.debug(
                "Removing standings requests for character ID %d by user %s",
                character_id,
                request.user,
            )
            StandingRequest.objects.remove_requests(character_id)
        else:
            try:
                contact_set = ContactSet.objects.latest()
            except ContactSet.DoesNotExist:
                logger.warning("Failed to get a contact set")
                ok = False
            else:
                if contact_set.character_has_satisfied_standing(character_id):
                    logger.debug(
                        "Creating standings revocation for character ID %d by user %s",
                        character_id,
                        request.user,
                    )
                    StandingRevocation.objects.add_revocation(
                        contact_id=character_id,
                        contact_type=StandingRevocation.CHARACTER_CONTACT_TYPE,
                        user=request.user,
                    )
                else:
                    logger.debug("No standings exist for characterID %d", character_id)
    else:
        logger.debug(
            "User %s already has a pending standing revocation for character %d",
            request.user,
            character_id,
        )

    if not ok:
        messages_plus.warning(
            request,
            "An unexpected error occurred when trying to process "
            "your request to revoke standing for %s. Please try again."
            % EveEntity.objects.get_name(character_id),
        )

    return redirect("standingsrequests:index")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def request_corp_standing(request, corporation_id):
    """
    For a user to request standings for their own corp
    """
    corporation_id = int(corporation_id)
    ok = True
    logger.debug(
        "Standings request from user %s for corpID %d", request.user, corporation_id
    )

    # Check the user has the required number of member keys for the corporation
    if StandingRequest.can_request_corporation_standing(corporation_id, request.user):
        if not StandingRequest.objects.has_pending_request(
            corporation_id
        ) and not StandingRevocation.objects.has_pending_request(corporation_id):
            StandingRequest.objects.add_request(
                user=request.user,
                contact_id=corporation_id,
                contact_type=StandingRequest.CORPORATION_CONTACT_TYPE,
            )
        else:
            # Pending request, not allowed
            logger.warning(
                "Contact ID %d already has a pending request", corporation_id
            )
            ok = False
    else:
        logger.warning(
            "User %s does not have enough keys for corpID %d, forbidden",
            request.user,
            corporation_id,
        )
        ok = False

    if not ok:
        messages_plus.warning(
            request,
            "An unexpected error occurred when trying to process "
            "your standing request for %s. Please try again."
            % EveEntity.objects.get_name(corporation_id),
        )

    return redirect("standingsrequests:index")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def remove_corp_standing(request, corporation_id):
    """
    Handles both removing corp requests and removing existing standings
    """
    corporation_id = int(corporation_id)
    ok = True
    logger.debug("remove_corp_standing called by %s", request.user)
    try:
        st_req = StandingRequest.objects.get(contact_id=corporation_id)
    except StandingRequest.DoesNotExist:
        ok = False
    else:
        if st_req.user == request.user:
            if (
                StandingRequest.objects.has_pending_request(corporation_id)
                or StandingRequest.objects.has_actioned_request(corporation_id)
            ) and not StandingRevocation.objects.has_pending_request(corporation_id):
                logger.debug(
                    "Removing standings requests for corpID %d by user %s",
                    corporation_id,
                    request.user,
                )
                StandingRequest.objects.remove_requests(corporation_id)
            else:
                try:
                    contact_set = ContactSet.objects.latest()
                except ContactSet.DoesNotExist:
                    logger.warning("Failed to get a contact set")
                    ok = False
                else:
                    if contact_set.corporation_has_satisfied_standing(corporation_id):
                        # Manual revocation required
                        logger.debug(
                            "Creating standings revocation for corpID %d by user %s",
                            corporation_id,
                            request.user,
                        )
                        StandingRevocation.objects.add_revocation(
                            contact_id=corporation_id,
                            contact_type=StandingRevocation.CORPORATION_CONTACT_TYPE,
                            user=request.user,
                        )
                    else:
                        logger.debug(
                            "Can remove standing - no standings exist for corpID %d",
                            corporation_id,
                        )
                        ok = False

        else:
            logger.warning(
                "User %s tried to remove standings for corpID %d but was not permitted",
                request.user,
                corporation_id,
            )
            ok = False

    if not ok:
        messages_plus.warning(
            request,
            "An unexpected error occurred when trying to process "
            "your request to revoke standing for %s. Please try again."
            % EveEntity.objects.get_name(corporation_id),
        )

    return redirect("standingsrequests:index")


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
        organization = ContactSet.standings_source_entity()
        last_update = contact_set.date if contact_set else None
        pilots_count = contact_set.charactercontact_set.count() if contact_set else None

    return render(
        request,
        "standingsrequests/view_pilots.html",
        {
            "lastUpdate": last_update,
            "app_title": __title__,
            "operation_mode": SR_OPERATION_MODE,
            "organization": organization,
            "pilots_count": pilots_count,
        },
    )


@login_required
@permission_required("standingsrequests.view")
def view_pilots_standings_json(request):
    logger.debug("view_pilot_standings_json called by %s", request.user)
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()

    def get_pilots():
        characters_data = list()
        character_contacts = contacts.charactercontact_set.all().order_by("name")
        for p in character_contacts:
            character = EveCharacter.objects.get_character_by_id(p.contact_id)
            try:
                user = character.character_ownership.user
            except AttributeError:
                character = EveCharacterHelper(p.contact_id)
                main = None
                state = ""
                has_required_scopes = False
            else:
                user = character.character_ownership.user
                main = user.profile.main_character
                state = user.profile.state.name if user.profile.state else ""
                has_required_scopes = StandingRequest.has_required_scopes_for_request(
                    character
                )
            finally:
                character_icon_url = character.portrait_url(DEFAULT_ICON_SIZE)
                corporation_id = character.corporation_id if character else None
                corporation_name = character.corporation_name if character else None
                corporation_ticker = character.corporation_ticker if character else None
                alliance_id = character.alliance_id if character else None
                alliance_name = character.alliance_name if character else None
                main_character_name = main.character_name if main else None
                main_character_ticker = main.corporation_ticker if main else None
                main_character_icon_url = (
                    main.portrait_url(DEFAULT_ICON_SIZE) if main else None
                )
                labels = [label.name for label in p.labels.all()]

            characters_data.append(
                {
                    "character_id": p.contact_id,
                    "character_name": p.name,
                    "character_icon_url": character_icon_url,
                    "corporation_id": corporation_id,
                    "corporation_name": corporation_name,
                    "corporation_ticker": corporation_ticker,
                    "alliance_id": alliance_id,
                    "alliance_name": alliance_name,
                    "has_required_scopes": has_required_scopes,
                    "state": state,
                    "main_character_name": main_character_name,
                    "main_character_ticker": main_character_ticker,
                    "main_character_icon_url": main_character_icon_url,
                    "standing": p.standing,
                    "labels": labels,
                }
            )

        return characters_data

    my_characters_data = cache_get_or_set_character_standings_data(get_pilots)
    return JsonResponse(my_characters_data, safe=False)


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
    character_contacts = contacts.charactercontact_set.all().order_by("name")
    EveEntity.objects.get_names([p.contact_id for p in character_contacts])

    for pilot_standing in character_contacts:
        char = EveCharacter.objects.get_character_by_id(pilot_standing.contact_id)
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
            pilot_standing.contact_id,
            pilot_standing.name,
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
    except (ObjectDoesNotExist, ContactSet.DoesNotExist):
        contact_set = None
    finally:
        organization = ContactSet.standings_source_entity()
        last_update = contact_set.date if contact_set else None

    if contact_set:
        groups_count = (
            contact_set.corporationcontact_set.count()
            + contact_set.alliancecontact_set.count()
        )
    else:
        groups_count = None

    return render(
        request,
        "standingsrequests/view_groups.html",
        {
            "lastUpdate": last_update,
            "app_title": __title__,
            "operation_mode": SR_OPERATION_MODE,
            "organization": organization,
            "groups_count": groups_count,
        },
    )


@login_required
@permission_required("standingsrequests.view")
def view_groups_standings_json(request):
    logger.debug("view_pilot_standings_json called by %s", request.user)
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()

    corporations_data = list()
    corporations_qs = contacts.corporationcontact_set.all().order_by("name")
    eve_corporations = {
        corporation.corporation_id: corporation
        for corporation in EveCorporation.get_many_by_id(
            corporations_qs.values_list("contact_id", flat=True)
        )
    }
    for contact in corporations_qs:
        if contact.contact_id in eve_corporations:
            corporation = eve_corporations[contact.contact_id]
            corporations_data.append(
                {
                    "corporation_id": corporation.corporation_id,
                    "corporation_name": corporation.corporation_name,
                    "corporation_icon_url": corporation.logo_url(DEFAULT_ICON_SIZE),
                    "alliance_id": corporation.alliance_id,
                    "alliance_name": corporation.alliance_name,
                    "standing": contact.standing,
                    "labels": [label.name for label in contact.labels.all()],
                }
            )

    alliances_data = list()
    for contact in contacts.alliancecontact_set.all().order_by("name"):
        alliances_data.append(
            {
                "alliance_id": contact.contact_id,
                "alliance_name": contact.name,
                "alliance_icon_url": EveAllianceInfo.generic_logo_url(
                    contact.contact_id, DEFAULT_ICON_SIZE
                ),
                "standing": contact.standing,
                "labels": [label.name for label in contact.labels.all()],
            }
        )

    return JsonResponse(
        {"corps": corporations_data, "alliances": alliances_data}, safe=False,
    )


###################
# Manage requests #
###################


@login_required
@permission_required("standingsrequests.affect_standings")
def manage_standings(request):
    logger.debug("manage_standings called by %s", request.user)
    context = {
        "app_title": __title__,
        "operation_mode": SR_OPERATION_MODE,
        "organization": ContactSet.standings_source_entity(),
        "requests_count": _standing_requests_to_manage().count(),
        "revocations_count": _revocations_to_manage().count(),
    }
    return render(request, "standingsrequests/manage.html", context,)


@login_required
@permission_required("standingsrequests.affect_standings")
def manage_get_requests_json(request):
    logger.debug("manage_get_requests_json called by %s", request.user)
    requests_qs = _standing_requests_to_manage()
    requests_data = _compose_standing_requests_data(requests_qs)
    return JsonResponse(requests_data, safe=False)


@login_required
@permission_required("standingsrequests.affect_standings")
def manage_get_revocations_json(request):
    logger.debug("manage_get_revocations_json called by %s", request.user)
    revocations_qs = _revocations_to_manage()
    requests_data = _compose_standing_requests_data(revocations_qs)
    return JsonResponse(requests_data, safe=False)


def _standing_requests_to_manage() -> models.QuerySet:
    return (
        StandingRequest.objects.filter(action_date__isnull=True, is_effective=False)
        .select_related("user__profile__main_character")
        .order_by("request_date")
    )


def _revocations_to_manage() -> models.QuerySet:
    return (
        StandingRevocation.objects.filter(action_date__isnull=True, is_effective=False)
        .select_related("user__profile__main_character")
        .order_by("request_date")
    )


def _compose_standing_requests_data(requests_qs: models.QuerySet) -> list:
    """composes list of standings requests or revocations based on queryset 
    and returns it
    """
    requests_data = list()
    eve_corporations = {
        corporation.corporation_id: corporation
        for corporation in EveCorporation.get_many_by_id(
            [r.contact_id for r in requests_qs if r.is_corporation]
        )
    }
    for r in requests_qs:
        try:
            main = r.user.profile.main_character
            state_name = r.user.profile.state.name
        except AttributeError:
            main = None
            state_name = ""
            main_character_name = ""
            main_character_ticker = ""
            main_character_icon_url = ""
        else:
            main_character_name = main.character_name
            main_character_ticker = main.corporation_ticker
            main_character_icon_url = main.portrait_url(DEFAULT_ICON_SIZE)

        if r.is_character:
            character = EveCharacter.objects.get_character_by_id(r.contact_id)
            if not character:
                character = EveCharacterHelper(r.contact_id)

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
            has_scopes = StandingRequest.has_required_scopes_for_request(character)

        elif r.is_corporation and r.contact_id in eve_corporations:
            corporation = eve_corporations[r.contact_id]
            contact_icon_url = corporation.logo_url(DEFAULT_ICON_SIZE)
            contact_name = corporation.corporation_name
            corporation_id = corporation.corporation_id
            corporation_name = corporation.corporation_name
            corporation_ticker = corporation.ticker
            alliance_id = None
            alliance_name = ""
            has_scopes = StandingRequest.can_request_corporation_standing(
                corporation.corporation_id, r.user
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

        requests_data.append(
            {
                "contact_id": r.contact_id,
                "contact_name": contact_name,
                "contact_icon_url": contact_icon_url,
                "corporation_id": corporation_id,
                "corporation_name": corporation_name,
                "corporation_ticker": corporation_ticker,
                "alliance_id": alliance_id,
                "alliance_name": alliance_name,
                "request_date": r.request_date.isoformat(),
                "action_date": r.action_date.isoformat() if r.action_date else None,
                "has_scopes": has_scopes,
                "state": state_name,
                "main_character_name": main_character_name,
                "main_character_ticker": main_character_ticker,
                "main_character_icon_url": main_character_icon_url,
                "actioned": r.is_actioned,
                "is_effective": r.is_effective,
                "is_corporation": r.is_corporation,
                "is_character": r.is_character,
                "action_by": r.action_by.username if r.action_by else "",
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
            r.mark_standing_actioned(request.user)
            actioned += 1
        if actioned > 0:
            return HttpResponseNoContent()
        else:
            return Http404
    elif request.method == "DELETE":
        StandingRequest.objects.remove_requests(contact_id, request.user)
        # TODO: Error handling
        return HttpResponseNoContent()
    else:
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
            r.mark_standing_actioned(request.user)
            actioned += 1
        if actioned > 0:
            return HttpResponseNoContent()
        else:
            return Http404
    elif request.method == "DELETE":
        StandingRevocation.objects.filter(contact_id=contact_id).delete()
        # TODO: Error handling
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
        "app_title": __title__,
        "operation_mode": SR_OPERATION_MODE,
        "organization": ContactSet.standings_source_entity(),
        "requests_count": _standing_requests_to_view().count(),
    }
    return render(request, "standingsrequests/requests.html", context)


@login_required
@permission_required("standingsrequests.affect_standings")
def view_requests_json(request):

    response_data = _compose_standing_requests_data(_standing_requests_to_view())
    return JsonResponse(response_data, safe=False)


def _standing_requests_to_view() -> models.QuerySet:
    return (
        StandingRequest.objects.filter(is_effective=True)
        .select_related("user__profile__main_character")
        .order_by("request_date")
    )


@login_required
@permission_required("standingsrequests.affect_standings")
@token_required(new=False, scopes=ContactSet.required_esi_scope())
def view_auth_page(request, token):
    source_entity = ContactSet.standings_source_entity()
    char_name = EveEntity.objects.get_name(STANDINGS_API_CHARID)
    if not source_entity:
        messages_plus.error(
            request,
            format_html(
                _(
                    "The configured character <strong>%s</strong> does not belong "
                    "to an alliance and can therefore not be used "
                    "to setup alliance standings. "
                    "Please configure a character that has an alliance."
                )
                % char_name,
            ),
        )
    elif token.character_id == STANDINGS_API_CHARID:
        update_all.delay(user_pk=request.user.pk)
        messages_plus.success(
            request,
            format_html(
                _(
                    "Token for character <strong>%s</strong> has been setup "
                    "successfully and the app has started pulling standings "
                    "from <strong>%s</strong>."
                )
                % (char_name, source_entity.name),
            ),
        )
    else:
        messages_plus.error(
            request,
            _(
                "Failed to setup token for configured character "
                "%(char_name)s (id:%(standings_api_char_id)s). "
                "Instead got token for different character: "
                "%(token_char_name)s (id:%(token_char_id)s)"
            )
            % {
                "char_name": char_name,
                "standings_api_char_id": STANDINGS_API_CHARID,
                "token_char_name": EveEntity.objects.get_name(token.character_id),
                "token_char_id": token.character_id,
            },
        )
    return redirect("standingsrequests:index")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
@token_required_by_state(new=False)
def view_requester_add_scopes(request, token):
    messages_plus.success(
        request,
        _("Successfully added token with required scopes for %(char_name)s")
        % {"char_name": EveEntity.objects.get_name(token.character_id)},
    )
    return redirect("standingsrequests:index")
