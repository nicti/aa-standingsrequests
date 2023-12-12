from typing import Set

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from esi.decorators import token_required
from esi.models import Token
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from standingsrequests import __title__
from standingsrequests.app_settings import SR_CORPORATIONS_ENABLED
from standingsrequests.constants import CreateCharacterRequestResult
from standingsrequests.core import app_config
from standingsrequests.decorators import token_required_by_state
from standingsrequests.helpers.evecorporation import EveCorporation
from standingsrequests.models import ContactSet, StandingRequest, StandingRevocation
from standingsrequests.tasks import update_all, update_associations_api

from ._common import DEFAULT_ICON_SIZE, add_common_context

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

    return redirect("standingsrequests:create_requests")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def create_requests(request):
    organization = app_config.standings_source_entity()
    try:
        main_char_id = request.user.profile.main_character.character_id
    except AttributeError:
        main_char_id = None

    image_url = organization.icon_url(size=DEFAULT_ICON_SIZE) if organization else ""
    context = {
        "corporations_enabled": SR_CORPORATIONS_ENABLED,
        "organization": organization,
        "organization_image_url": image_url,
        "authinfo": {"main_char_id": main_char_id},
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

    eve_characters = _make_eve_characters_map(request)
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
    characters_data = [
        _create_character_row(
            user=request.user,
            character=character,
            characters_with_standing=characters_with_standing,
            characters_standings_requests=characters_standings_requests,
            characters_standing_revocation=characters_standing_revocation,
        )
        for character in eve_characters.values()
    ]

    context = {"characters": characters_data}
    return render(
        request,
        "standingsrequests/partials/request_characters.html",
        add_common_context(request, context),
    )


def _create_character_row(
    user: User,
    character: EveCharacter,
    characters_with_standing,
    characters_standings_requests,
    characters_standing_revocation,
):
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
        and characters_standings_requests[character_id].user == user
    )
    result = {
        "character": character,
        "standing": standing,
        "pendingRequest": has_pending_request,
        "pendingRevocation": has_pending_revocation,
        "requestActioned": has_actioned_request,
        "inOrganisation": app_config.is_character_a_member(character),
        "hasRequiredScopes": StandingRequest.has_required_scopes_for_request(
            character, user=user, quick_check=True
        ),
        "hasStanding": has_standing,
    }
    return result


def _make_eve_characters_map(request):
    eve_characters_qs = EveCharacter.objects.filter(
        character_ownership__user=request.user
    ).select_related("character_ownership__user")
    eve_characters = {obj.character_id: obj for obj in eve_characters_qs}
    return eve_characters


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

    corporation_ids = _calc_corporation_ids(request.user)
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
    corporations_data = []
    for corporation in EveCorporation.get_many_by_id(corporation_ids):
        if not corporation or corporation.is_npc:
            continue

        row = _create_corporation_row(
            user=request.user,
            corporation=corporation,
            corporations_standing_requests=corporations_standing_requests,
            corporations_revocation_requests=corporations_revocation_requests,
            corporation_contacts=corporation_contacts,
        )
        corporations_data.append(row)

    corporations_data.sort(key=lambda x: x["corp"].corporation_name)
    context = {"corps": corporations_data}
    return render(
        request,
        "standingsrequests/partials/request_corporations.html",
        add_common_context(request, context),
    )


def _create_corporation_row(
    user: User,
    corporation: EveCorporation,
    corporations_standing_requests,
    corporations_revocation_requests,
    corporation_contacts,
):
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
        and corporations_revocation_requests[corporation_id].is_pending_annotated
    )
    has_actioned_request = (
        corporation_id in corporations_standing_requests
        and corporations_standing_requests[corporation_id].is_actioned_annotated
    )
    has_standing = (
        corporation_id in corporations_standing_requests
        and corporations_standing_requests[corporation_id].is_effective
        and corporations_standing_requests[corporation_id].user == user
    )
    result = {
        "token_count": corporation.member_tokens_count_for_user(user, quick_check=True),
        "corp": corporation,
        "standing": standing,
        "pendingRequest": has_pending_request,
        "pendingRevocation": has_pending_revocation,
        "requestActioned": has_actioned_request,
        "hasStanding": has_standing,
    }

    return result


def _calc_corporation_ids(user: User) -> Set[int]:
    eve_characters_qs = EveCharacter.objects.filter(
        character_ownership__user=user
    ).select_related("character_ownership__user")
    corporation_ids = set(
        eve_characters_qs.exclude(corporation_id__in=app_config.corporation_ids())
        .exclude(alliance_id__in=app_config.alliance_ids())
        .values_list("corporation_id", flat=True)
    )

    return corporation_ids


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def request_character_standing(request: HttpRequest, character_id: int):
    """For a user to request standings for their own characters"""
    logger.debug(
        "Standings request from user %s for characterID %s",
        str(request.user),
        character_id,
    )
    character = get_object_or_404(
        EveCharacter.objects.select_related("character_ownership__user"),
        character_id=character_id,
    )
    result: CreateCharacterRequestResult = (
        StandingRequest.objects.create_character_request(
            user=request.user, character=character
        )
    )
    if result is CreateCharacterRequestResult.NO_ERROR:
        update_associations_api.delay()

    else:
        if result is CreateCharacterRequestResult.CHARACTER_IS_MISSING_SCOPES:
            messages.error(
                request,
                _("You character %s is missing scopes.")
                % EveEntity.objects.resolve_name(character_id),
            )
        elif result is CreateCharacterRequestResult.USER_IS_NOT_OWNER:
            messages.error(
                request,
                _("You are not the owner of character %s.")
                % EveEntity.objects.resolve_name(character_id),
            )
        else:
            messages.error(
                request,
                _(
                    "An unexpected error occurred when trying to process "
                    "your standing request for %s. Please try again."
                )
                % EveEntity.objects.resolve_name(character_id),
            )

    return redirect("standingsrequests:create_requests")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def remove_character_standing(request: HttpRequest, character_id: int):
    """
    Handles both removing requests and removing existing standings
    """
    logger.debug(
        "remove_character_standing called by %s for character %s",
        str(request.user),
        character_id,
    )
    req = get_object_or_404(StandingRequest, user=request.user, contact_id=character_id)
    success = req.remove()
    if not success:
        messages.warning(
            request,
            _(
                "An unexpected error occurred when trying to process "
                "your request to revoke standing for %s. Please try again."
            )
            % EveEntity.objects.resolve_name(character_id),
        )
    return redirect("standingsrequests:create_requests")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def request_corp_standing(request: HttpRequest, corporation_id):
    """
    For a user to request standings for their own corp
    """
    corporation_id = int(corporation_id)
    logger.debug(
        "Standings request from user %s for corpID %d", request.user, corporation_id
    )
    if not StandingRequest.objects.create_corporation_request(
        request.user, corporation_id
    ):
        messages.warning(
            request,
            _(
                "An unexpected error occurred when trying to process "
                "your standing request for %s. Please try again."
            )
            % EveEntity.objects.resolve_name(corporation_id),
        )
    else:
        update_associations_api.delay()
    return redirect("standingsrequests:create_requests")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
def remove_corp_standing(request: HttpRequest, corporation_id: int):
    """
    Handles both removing corp requests and removing existing standings
    """
    logger.debug("remove_corp_standing called by %s", request.user)
    try:
        req = StandingRequest.objects.filter(user=request.user).get(
            contact_id=corporation_id
        )
    except StandingRequest.DoesNotExist:
        success = False
    else:
        success = req.remove()
    if not success:
        messages.warning(
            request,
            _(
                "An unexpected error occurred when trying to process "
                "your request to revoke standing for %s. Please try again."
            )
            % EveEntity.objects.resolve_name(corporation_id),
        )
    return redirect("standingsrequests:create_requests")


@login_required
@permission_required("standingsrequests.affect_standings")
@token_required(new=False, scopes=ContactSet.required_esi_scope())
def view_auth_page(request: HttpRequest, token: Token):
    source_entity = app_config.standings_source_entity()
    owner_character = app_config.owner_character()
    if not source_entity:
        messages.error(
            request,
            format_html(
                _(
                    "The configured character %s does not belong "
                    "to an alliance and can therefore not be used "
                    "to setup alliance standings. "
                    "Please configure a character that has an alliance."
                )
                % owner_character.character_name,
            ),
        )

    elif token.character_id == owner_character.character_id:
        update_all.delay(user_pk=request.user.pk)
        messages.success(
            request,
            format_html(
                _(
                    "Token for character %(user_character)s has been setup "
                    "successfully and the app has started pulling standings "
                    "from %(standings_character)s."
                )
                % {
                    "user_character": owner_character.character_name,
                    "standings_character": source_entity.name,
                },
            ),
        )

    else:
        messages.error(
            request,
            _(
                "Failed to setup token for configured character "
                "%(char_name)s (id:%(standings_api_char_id)s). "
                "Instead got token for different character: "
                "%(token_char_name)s (id:%(token_char_id)s)"
            )
            % {
                "char_name": owner_character.character_name,
                "standings_api_char_id": owner_character.character_id,
                "token_char_name": EveEntity.objects.resolve_name(token.character_id),
                "token_char_id": token.character_id,
            },
        )
    return redirect("standingsrequests:index")


@login_required
@permission_required(StandingRequest.REQUEST_PERMISSION_NAME)
@token_required_by_state(new=False)
def view_requester_add_scopes(request: HttpRequest, token):
    messages.success(
        request,
        _("Successfully added token with required scopes for %(char_name)s")
        % {"char_name": EveEntity.objects.resolve_name(token.character_id)},
    )
    return redirect("standingsrequests:create_requests")
