from dataclasses import dataclass
from typing import Dict, List, Optional

from django.contrib.auth.models import User
from django.db import models
from django.utils.html import format_html

from allianceauth.eveonline.models import EveCharacter

from standingsrequests import __title__
from standingsrequests.constants import DATETIME_FORMAT_HTML
from standingsrequests.core import app_config
from standingsrequests.core.contact_types import ContactTypeId
from standingsrequests.helpers.evecharacter import EveCharacterHelper
from standingsrequests.helpers.evecorporation import EveCorporation
from standingsrequests.models import (
    AbstractStandingsRequest,
    Contact,
    ContactSet,
    StandingRequest,
    StandingRevocation,
)

DEFAULT_ICON_SIZE = 32


def label_with_icon(icon_url: str, text: str):
    return format_html(
        '<span class="text-nowrap">'
        '<img src="{}" class="img-circle" style="width:{}px;height:{}px"> {}'
        "</span>",
        icon_url,
        DEFAULT_ICON_SIZE,
        DEFAULT_ICON_SIZE,
        text,
    )


def add_common_context(request, context: dict) -> dict:
    """adds the common context used by all view"""
    new_context = {
        **{
            "app_title": __title__,
            "operation_mode": str(app_config.operation_mode()),
            "pending_total_count": (
                StandingRequest.objects.pending_requests().count()
                + StandingRevocation.objects.pending_requests().count()
            ),
            "DATETIME_FORMAT_HTML": DATETIME_FORMAT_HTML,
        },
        **context,
    }
    return new_context


@dataclass(frozen=True)
class MainCharacterInfo:
    """A main character for output."""

    character_name: str = "-"
    ticker: str = "-"
    icon_url: str = "-"

    @property
    def is_valid(self) -> bool:
        return bool(self.character_name)

    def html(self) -> str:
        if not self.character_name:
            return ""

        return label_with_icon(self.icon_url, f"[{self.ticker}] {self.character_name}")

    @classmethod
    def create_from_user(cls, user: User) -> "MainCharacterInfo":
        if not user:
            return cls()

        main_character: EveCharacter = user.profile.main_character
        if not main_character:
            return cls()

        character_name = main_character.character_name
        ticker = main_character.corporation_ticker
        icon_url = main_character.portrait_url(DEFAULT_ICON_SIZE)
        obj = cls(character_name=character_name, ticker=ticker, icon_url=icon_url)
        return obj


@dataclass(frozen=True)
class OrganizationInfo:
    """Organizational info about a requestor."""

    contact_name: str = ""
    contact_icon_url: str = ""
    corporation_id: Optional[int] = None
    corporation_name: str = ""
    corporation_ticker: str = ""
    alliance_id: int = Optional[None]
    alliance_name: str = ""
    has_scopes: bool = False

    def contact_name_html(self) -> str:
        if not self.contact_name:
            return ""

        return label_with_icon(self.contact_icon_url, self.contact_name)

    def organization_html(self) -> str:
        if self.corporation_name:
            organization_html = f"[{self.corporation_ticker}] {self.corporation_name}"
            if self.alliance_name:
                organization_html = format_html(
                    "{}<br>{}", organization_html, self.alliance_name
                )
        else:
            organization_html = ""

        return organization_html

    @classmethod
    def create(
        cls,
        quick_check: bool,
        eve_characters: Dict[int, EveCharacter],
        eve_corporations: Dict[int, EveCorporation],
        req: AbstractStandingsRequest,
    ) -> "OrganizationInfo":
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
            return cls(
                contact_name,
                contact_icon_url,
                corporation_id,
                corporation_name,
                corporation_ticker,
                alliance_id,
                alliance_name,
                has_scopes,
            )

        if req.is_corporation and req.contact_id in eve_corporations:
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
            return cls(
                contact_name,
                contact_icon_url,
                corporation_id,
                corporation_name,
                corporation_ticker,
                alliance_id,
                alliance_name,
                has_scopes,
            )

        return cls()


def compose_standing_requests_data(
    requests_qs: models.QuerySet, quick_check: bool = False
) -> list:
    """composes list of standings requests or revocations based on queryset
    and returns it
    """
    requests_query: models.QuerySet[
        AbstractStandingsRequest
    ] = requests_qs.select_related(
        "user", "user__profile__state", "user__profile__main_character"
    )
    eve_characters = _preload_eve_characters(requests_query)
    eve_corporations = _preload_eve_corporations(requests_query)
    contacts = _identify_contacts(eve_characters, eve_corporations)
    requests_data = []
    for req in requests_query:
        main_character = MainCharacterInfo.create_from_user(req.user)
        state_name = req.user.profile.state.name if req.user else "-"
        organization = OrganizationInfo.create(
            quick_check, eve_characters, eve_corporations, req
        )
        reason = req.get_reason_display() if req.is_standing_revocation else None
        requests_data.append(
            {
                "contact_id": req.contact_id,
                "contact_name": organization.contact_name,
                "contact_icon_url": organization.contact_icon_url,
                "contact_name_html": {
                    "display": organization.contact_name_html(),
                    "sort": organization.contact_name,
                },
                "corporation_id": organization.corporation_id,
                "corporation_name": organization.corporation_name,
                "corporation_ticker": organization.corporation_ticker,
                "alliance_id": organization.alliance_id,
                "alliance_name": organization.alliance_name,
                "organization_html": organization.organization_html(),
                "request_date": req.request_date,
                "action_date": req.action_date,
                "has_scopes": organization.has_scopes,
                "state": state_name,
                "reason": reason,
                "labels": sorted(_fetch_labels(contacts, req)),
                "main_character_name": main_character.character_name,
                "main_character_ticker": main_character.ticker,
                "main_character_icon_url": main_character.icon_url,
                "main_character_html": main_character.html(),
                "actioned": req.is_actioned,
                "is_effective": req.is_effective,
                "is_corporation": req.is_corporation,
                "is_character": req.is_character,
                "action_by": req.action_by.username if req.action_by else "(System)",
            }
        )
    return requests_data


# TODO: remove EveCorporation usage
def _preload_eve_corporations(
    requests_qs: models.QuerySet,
) -> Dict[int, EveCorporation]:
    corporation_ids = requests_qs.filter(
        contact_type_id=ContactTypeId.CORPORATION
    ).values_list("contact_id", flat=True)
    corporations = EveCorporation.get_many_by_id(corporation_ids)
    eve_corporations = {
        corporation.corporation_id: corporation for corporation in corporations
    }

    return eve_corporations


def _preload_eve_characters(requests_qs: models.QuerySet) -> Dict[int, EveCharacter]:
    eve_characters = EveCharacter.objects.filter(
        character_id__in=(
            requests_qs.exclude(contact_type_id=ContactTypeId.CORPORATION).values_list(
                "contact_id", flat=True
            )
        )
    )
    result = {character.character_id: character for character in eve_characters}

    return result


def _identify_contacts(eve_characters, eve_corporations) -> Dict[int, Contact]:
    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = {}
    else:
        all_contact_ids = set(eve_characters.keys()) | set(eve_corporations.keys())
        contacts = {
            obj.eve_entity_id: obj
            for obj in contact_set.contacts.prefetch_related("labels").filter(
                eve_entity_id__in=all_contact_ids
            )
        }
    return contacts


def _fetch_labels(
    contacts: Dict[int, Contact], req: AbstractStandingsRequest
) -> List[str]:
    try:
        my_contact = contacts[req.contact_id]
    except KeyError:
        labels = []
    else:
        labels = my_contact.labels_sorted
    return labels
