from django.contrib.auth.decorators import login_required, permission_required
from django.db import models
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_page
from esi.decorators import token_required

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveAllianceInfo, EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag
from app_utils.messages import messages_plus

from . import __title__
from .app_settings import (
    SR_CORPORATIONS_ENABLED,
    SR_NOTIFICATIONS_ENABLED,
    SR_OPERATION_MODE,
    STANDINGS_API_CHARID,
)
from .decorators import token_required_by_state
from .helpers.evecharacter import EveCharacterHelper
from .helpers.evecorporation import EveCorporation
from .helpers.eveentity import EveEntityHelper
from .helpers.writers import UnicodeWriter
from .models import (
    ContactSet,
    CorporationContact,
    EveEntity,
    StandingRequest,
    StandingRevocation,
)
from .tasks import update_all

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

DEFAULT_ICON_SIZE = 32
CACHED_PAGES_MINUTES = 10


def add_common_context(request, context: dict) -> dict:
    """adds the common context used by all view"""
    new_context = {
        **{
            "app_title": __title__,
            "operation_mode": SR_OPERATION_MODE,
            "pending_total_count": (
                StandingRequest.objects.pending_requests().count()
                + StandingRevocation.objects.pending_requests().count()
            ),
        },
        **context,
    }
    return new_context


class HttpResponseNoContent(HttpResponse):
    """Special HTTP response with no content, just headers.

    The content operations are ignored.
    """

    def __init__(self, content="", mimetype=None, status=None, content_type=None):
        super().__init__(status=204)

        # although we don't define a content-type, base class sets a
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
    """index page is used as dispatcher"""
    app_count = (
        StandingRequest.objects.pending_requests().count()
        + StandingRevocation.objects.pending_requests().count()
    )
    if app_count > 0 and request.user.has_perm("standingsrequests.affect_standings"):
        return redirect("standingsrequests:manage")
    else:
        return redirect("standingsrequests:create_requests")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def create_requests(request):
    organization = ContactSet.standings_source_entity()
    context = {
        "corporations_enabled": SR_CORPORATIONS_ENABLED,
        "organization": organization,
        "organization_image_url": organization.icon_url(size=DEFAULT_ICON_SIZE),
        "authinfo": {"main_char_id": request.user.profile.main_character.character_id},
    }
    return render(
        request,
        "standingsrequests/create_requests.html",
        add_common_context(request, context),
    )


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def request_characters(request):
    logger.debug("Start request_characters request")
    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        return render(
            request, "standingsrequests/error.html", add_common_context(request, {})
        )

    eve_characters_qs = EveEntityHelper.get_characters_by_user(request.user)
    eve_characters = {obj.character_id: obj for obj in eve_characters_qs}
    characters_with_standing = {
        contact["contact_id"]: contact["standing"]
        for contact in (
            contact_set.charactercontact_set.filter(
                contact_id__in=list(eve_characters.keys())
            ).values("contact_id", "standing")
        )
    }
    characters_standings_requests = {
        obj.contact_id: obj
        for obj in (
            StandingRequest.objects.select_related("user")
            .filter(contact_id__in=eve_characters.keys())
            .annotate_is_pending()
            .annotate_is_actioned()
        )
    }
    characters_standing_revocation = {
        obj.contact_id: obj
        for obj in (
            StandingRevocation.objects.filter(
                contact_id__in=eve_characters.keys()
            ).annotate_is_pending()
        )
    }
    characters_data = list()
    for character in eve_characters.values():
        character_id = character.character_id
        standing = characters_with_standing.get(character_id)
        has_pending_request = (
            character_id in characters_standings_requests
            and characters_standings_requests[character_id].is_pending_annotated
        )
        has_pending_revocation = (
            character_id in characters_standing_revocation
            and characters_standing_revocation[character_id].is_pending_annotated
        )
        has_actioned_request = (
            character_id in characters_standings_requests
            and characters_standings_requests[character_id].is_actioned_annotated
        )
        has_standing = (
            character_id in characters_standings_requests
            and characters_standings_requests[character_id].is_effective
            and characters_standings_requests[character_id].user == request.user
        )
        characters_data.append(
            {
                "character": character,
                "standing": standing,
                "pendingRequest": has_pending_request,
                "pendingRevocation": has_pending_revocation,
                "requestActioned": has_actioned_request,
                "inOrganisation": ContactSet.is_character_in_organisation(character),
                "hasRequiredScopes": StandingRequest.has_required_scopes_for_request(
                    character, user=request.user, quick_check=True
                ),
                "hasStanding": has_standing,
            }
        )

    context = {"characters": characters_data}
    return render(
        request,
        "standingsrequests/partials/_request_characters.html",
        add_common_context(request, context),
    )


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def request_corporations(request):
    logger.debug("Start request_characters request")
    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        return render(
            request, "standingsrequests/error.html", add_common_context(request, {})
        )

    eve_characters_qs = EveEntityHelper.get_characters_by_user(request.user)
    corporation_ids = set(
        eve_characters_qs.exclude(
            corporation_id__in=ContactSet.corporation_ids_in_organization()
        )
        .exclude(alliance_id__in=ContactSet.alliance_ids_in_organization())
        .values_list("corporation_id", flat=True)
    )
    corporations_standing_requests = {
        obj.contact_id: obj
        for obj in (
            StandingRequest.objects.select_related("user")
            .filter(contact_id__in=corporation_ids)
            .annotate_is_pending()
            .annotate_is_actioned()
        )
    }
    corporations_revocation_requests = {
        obj.contact_id: obj
        for obj in (
            StandingRevocation.objects.filter(contact_id__in=corporation_ids)
            .annotate_is_pending()
            .annotate_is_actioned()
        )
    }
    corporation_contacts = {
        obj.contact_id: obj
        for obj in (
            contact_set.corporationcontact_set.filter(contact_id__in=corporation_ids)
        )
    }
    corporations_data = list()
    for corporation in EveCorporation.get_many_by_id(corporation_ids):
        if corporation and not corporation.is_npc:
            corporation_id = corporation.corporation_id
            try:
                standing = corporation_contacts[corporation_id].standing
            except KeyError:
                standing = None
            has_pending_request = (
                corporation_id in corporations_standing_requests
                and corporations_standing_requests[corporation_id].is_pending_annotated
            )
            has_pending_revocation = (
                corporation_id in corporations_revocation_requests
                and corporations_revocation_requests[
                    corporation_id
                ].is_pending_annotated
            )
            has_actioned_request = (
                corporation_id in corporations_standing_requests
                and corporations_standing_requests[corporation_id].is_actioned_annotated
            )
            has_standing = (
                corporation_id in corporations_standing_requests
                and corporations_standing_requests[corporation_id].is_effective
                and corporations_standing_requests[corporation_id].user == request.user
            )
            corporations_data.append(
                {
                    "token_count": corporation.member_tokens_count_for_user(
                        request.user, quick_check=True
                    ),
                    "corp": corporation,
                    "standing": standing,
                    "pendingRequest": has_pending_request,
                    "pendingRevocation": has_pending_revocation,
                    "requestActioned": has_actioned_request,
                    "hasStanding": has_standing,
                }
            )

    corporations_data.sort(key=lambda x: x["corp"].corporation_name)
    context = {"corps": corporations_data}
    return render(
        request,
        "standingsrequests/partials/_request_corporations.html",
        add_common_context(request, context),
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
    character = EveCharacter.objects.get_character_by_id(character_id)
    if not character or not EveEntityHelper.is_character_owned_by_user(
        character_id, request.user
    ):
        logger.warning(
            "User %s does not own Pilot ID %d, forbidden", request.user, character_id
        )
        ok = False
    elif StandingRequest.objects.has_pending_request(
        character_id
    ) or StandingRevocation.objects.has_pending_request(character_id):
        logger.warning("Contact ID %d already has a pending request", character_id)
        ok = False
    elif not StandingRequest.has_required_scopes_for_request(
        character=character, user=request.user
    ):
        ok = False
        logger.warning("Contact ID %d does not have the required scopes", character_id)
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
                sr.mark_actioned(user=None)
                sr.mark_effective()

    if not ok:
        messages_plus.warning(
            request,
            "An unexpected error occurred when trying to process "
            "your standing request for %s. Please try again."
            % EveEntity.objects.get_name(character_id),
        )

    return redirect("standingsrequests:create_requests")


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
    character = EveCharacter.objects.get_character_by_id(character_id)
    if not character or not EveEntityHelper.is_character_owned_by_user(
        character_id, request.user
    ):
        logger.warning(
            "User %s does not own Pilot ID %d, forbidden", request.user, character_id
        )
        ok = False
    elif ContactSet.is_character_in_organisation(character):
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

    return redirect("standingsrequests:create_requests")


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

    return redirect("standingsrequests:create_requests")


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

    return redirect("standingsrequests:create_requests")


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


@cache_page(60 * CACHED_PAGES_MINUTES)
@login_required
@permission_required("standingsrequests.view")
def view_pilots_standings_json(request):
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()

    character_contacts_qs = (
        contacts.charactercontact_set.all().prefetch_related("labels").order_by("name")
    )
    character_contact_ids = set(
        character_contacts_qs.values_list("contact_id", flat=True)
    )
    eve_characters = {
        obj.character_id: obj
        for obj in EveCharacter.objects.select_related(
            "character_ownership__user",
            "character_ownership__user__profile__main_character",
            "character_ownership__user__profile__state",
        ).filter(character_id__in=character_contact_ids)
    }
    characters_data = list()
    for contact in character_contacts_qs:
        character = eve_characters.get(contact.contact_id)
        try:
            user = character.character_ownership.user
        except AttributeError:
            character = EveCharacterHelper(contact.contact_id)
            main = None
            state = ""
            has_required_scopes = None
        else:
            user = character.character_ownership.user
            main = user.profile.main_character
            state = user.profile.state.name if user.profile.state else ""
            has_required_scopes = StandingRequest.has_required_scopes_for_request(
                character=character, user=user, quick_check=True
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
            labels = [label.name for label in contact.labels.all()]

        characters_data.append(
            {
                "character_id": contact.contact_id,
                "character_name": contact.name,
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
    except ContactSet.DoesNotExist:
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


@cache_page(60 * CACHED_PAGES_MINUTES)
@login_required
@permission_required("standingsrequests.view")
def view_groups_standings_json(request):
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()

    corporations_qs = (
        contacts.corporationcontact_set.all()
        .prefetch_related("labels")
        .order_by("name")
    )
    eve_corporations = {
        corporation.corporation_id: corporation
        for corporation in EveCorporation.get_many_by_id(
            corporations_qs.values_list("contact_id", flat=True)
        )
    }
    corporations_data = list()
    standing_requests_qs = StandingRequest.objects.filter(
        contact_type_id=CorporationContact.get_contact_type_id()
    )
    standings_requests = {
        obj.contact_id: obj
        for obj in standing_requests_qs.filter(contact_id__in=eve_corporations.keys())
    }
    for contact in corporations_qs:
        if contact.contact_id in eve_corporations:
            corporation = eve_corporations[contact.contact_id]
            try:
                standing_request = standings_requests[contact.contact_id]
            except KeyError:
                main = None
                has_required_scopes = None
                state_name = ""
            else:
                user = standing_request.user
                main = user.profile.main_character
                state_name = user.profile.state.name
                has_required_scopes = (
                    not corporation.is_npc
                    and corporation.user_has_all_member_tokens(
                        user=user, quick_check=True
                    )
                )
            finally:
                main_character_name = main.character_name if main else ""
                main_character_ticker = main.corporation_ticker if main else ""
                main_character_icon_url = (
                    main.portrait_url(DEFAULT_ICON_SIZE) if main else ""
                )
                labels = [label.name for label in contact.labels.all()]

            corporations_data.append(
                {
                    "corporation_id": corporation.corporation_id,
                    "corporation_name": corporation.corporation_name,
                    "corporation_icon_url": corporation.logo_url(DEFAULT_ICON_SIZE),
                    "alliance_id": corporation.alliance_id,
                    "alliance_name": corporation.alliance_name,
                    "standing": contact.standing,
                    "labels": labels,
                    "has_required_scopes": has_required_scopes,
                    "state": state_name,
                    "main_character_name": main_character_name,
                    "main_character_ticker": main_character_ticker,
                    "main_character_icon_url": main_character_icon_url,
                }
            )

    alliances_data = list()
    for contact in (
        contacts.alliancecontact_set.all().prefetch_related("labels").order_by("name")
    ):
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
        "organization": ContactSet.standings_source_entity(),
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
    # preload character ids in bulk
    eve_characters = {
        character.character_id: character
        for character in EveCharacter.objects.filter(
            character_id__in=(
                requests_qs.exclude(
                    contact_type_id=CorporationContact.get_contact_type_id()
                ).values_list("contact_id", flat=True)
            )
        )
    }
    # preload corporations in bulk
    eve_corporations = {
        corporation.corporation_id: corporation
        for corporation in EveCorporation.get_many_by_id(
            requests_qs.filter(
                contact_type_id=CorporationContact.get_contact_type_id()
            ).values_list("contact_id", flat=True)
        )
    }
    requests_data = list()
    for r in requests_qs:
        main_character_name = ""
        main_character_ticker = ""
        main_character_icon_url = ""
        if r.user:
            state_name = r.user.profile.state.name
            main = r.user.profile.main_character
            if main:
                main_character_name = main.character_name
                main_character_ticker = main.corporation_ticker
                main_character_icon_url = main.portrait_url(DEFAULT_ICON_SIZE)
        else:
            state_name = "(no user)"

        if r.is_character:
            if r.contact_id in eve_characters:
                character = eve_characters[r.contact_id]
            else:
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
            has_scopes = StandingRequest.has_required_scopes_for_request(
                character=character, user=r.user, quick_check=quick_check
            )

        elif r.is_corporation and r.contact_id in eve_corporations:
            corporation = eve_corporations[r.contact_id]
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
                    user=r.user, quick_check=quick_check
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
                "action_by": r.action_by.username if r.action_by else "(System)",
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
        else:
            return Http404()
    elif request.method == "DELETE":
        try:
            standing_request = StandingRequest.objects.get(contact_id=contact_id)
        except StandingRequest.DoesNotExist:
            return Http404()
        else:
            StandingRequest.objects.remove_requests(contact_id)
            if SR_NOTIFICATIONS_ENABLED:
                entity_name = EveEntity.objects.get_name(contact_id)
                title = _("Standing request for %s rejected" % entity_name)
                message = _(
                    "Your standing request for '%s' "
                    "has been rejected by %s." % (entity_name, request.user)
                )
                notify(user=standing_request.user, title=title, message=message)

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
                entity_name = EveEntity.objects.get_name(contact_id)
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
        "organization": ContactSet.standings_source_entity(),
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
    return redirect("standingsrequests:create_requests")
