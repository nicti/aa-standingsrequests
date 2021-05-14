from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from esi.decorators import token_required
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag
from app_utils.messages import messages_plus

from .. import __title__
from ..app_settings import SR_CORPORATIONS_ENABLED
from ..core import BaseConfig, MainOrganizations
from ..decorators import token_required_by_state
from ..helpers.evecorporation import EveCorporation
from ..helpers.eveentity import EveEntityHelper
from ..models import ContactSet, StandingRequest, StandingRevocation
from ..tasks import update_all
from .helpers import DEFAULT_ICON_SIZE, add_common_context

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


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
    organization = BaseConfig.standings_source_entity()
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
        contact["eve_entity_id"]: contact["standing"]
        for contact in (
            contact_set.contacts.filter(
                eve_entity_id__in=list(eve_characters.keys())
            ).values("eve_entity_id", "standing")
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
                "inOrganisation": MainOrganizations.is_character_a_member(character),
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
        eve_characters_qs.exclude(corporation_id__in=MainOrganizations.corporation_ids)
        .exclude(alliance_id__in=MainOrganizations.alliance_ids)
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
        obj.eve_entity_id: obj
        for obj in (contact_set.contacts.filter(eve_entity_id__in=corporation_ids))
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
            if contact_set.contact_has_satisfied_standing(character_id):
                sr.mark_actioned(user=None)
                sr.mark_effective()

    if not ok:
        messages_plus.warning(
            request,
            "An unexpected error occurred when trying to process "
            "your standing request for %s. Please try again."
            % EveEntity.objects.resolve_name(character_id),
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
    elif MainOrganizations.is_character_a_member(character):
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
            StandingRequest.objects.remove_requests(
                character_id, reason=StandingRevocation.Reason.OWNER_REQUEST
            )
        else:
            try:
                contact_set = ContactSet.objects.latest()
            except ContactSet.DoesNotExist:
                logger.warning("Failed to get a contact set")
                ok = False
            else:
                if contact_set.contact_has_satisfied_standing(character_id):
                    logger.debug(
                        "Creating standings revocation for character ID %d by user %s",
                        character_id,
                        request.user,
                    )
                    StandingRevocation.objects.add_revocation(
                        contact_id=character_id,
                        contact_type=StandingRevocation.CHARACTER_CONTACT_TYPE,
                        user=request.user,
                        reason=StandingRevocation.Reason.OWNER_REQUEST,
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
            % EveEntity.objects.resolve_name(character_id),
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
            % EveEntity.objects.resolve_name(corporation_id),
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
                    if contact_set.contact_has_satisfied_standing(corporation_id):
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
                            reason=StandingRevocation.Reason.OWNER_REQUEST,
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
            % EveEntity.objects.resolve_name(corporation_id),
        )

    return redirect("standingsrequests:create_requests")


@login_required
@permission_required("standingsrequests.affect_standings")
@token_required(new=False, scopes=ContactSet.required_esi_scope())
def view_auth_page(request, token):
    source_entity = BaseConfig.standings_source_entity()
    char_name = EveEntity.objects.resolve_name(BaseConfig.standings_character_id)
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
    elif token.character_id == BaseConfig.standings_character_id:
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
                "standings_api_char_id": BaseConfig.standings_character_id,
                "token_char_name": EveEntity.objects.resolve_name(token.character_id),
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
        % {"char_name": EveEntity.objects.resolve_name(token.character_id)},
    )
    return redirect("standingsrequests:create_requests")


@login_required
@staff_member_required
def admin_changeset_update_now(request):
    update_all.delay(user_pk=request.user.pk)
    messages_plus.info(
        request,
        _(
            "Started updating contacts and affiliations. "
            "You will receive a notification when completed."
        ),
    )
    return redirect("admin:standingsrequests_contactset_changelist")
