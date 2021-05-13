from datetime import timedelta

from django.contrib.auth.models import User
from django.core import exceptions
from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from esi.models import Token
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .app_settings import SR_REQUIRED_SCOPES, SR_STANDING_TIMEOUT_HOURS
from .core import BaseConfig, ContactType, MainOrganizations
from .helpers.evecorporation import EveCorporation
from .managers import (
    AbstractStandingsRequestManager,
    CharacterAffiliationManager,
    ContactQuerySet,
    ContactSetManager,
    CorporationDetailsManager,
    StandingRequestManager,
    StandingRevocationManager,
)

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class ContactSet(models.Model):
    """Set of contacts from configured alliance or corporation
    which defines its current standings
    """

    date = models.DateTimeField(auto_now_add=True, db_index=True)
    name = models.CharField(max_length=254)

    objects = ContactSetManager()

    class Meta:
        get_latest_by = "date"
        permissions = (
            ("view", "User can view standings"),
            ("download", "User can export standings to a CSV file"),
        )

    def __str__(self):
        return str(self.date)

    def __repr__(self):
        return f"{type(self).__name__}(pk={self.pk}, date='{self.date}')"

    def contact_has_satisfied_standing(self, contact_id: int) -> bool:
        """Return True if give contact has standing exists"""
        try:
            contact = self.contacts.get(eve_entity_id=contact_id)
        except Contact.DoesNotExist:
            return False
        return contact.is_standing_satisfied

    def generate_standing_requests_for_blue_alts(self) -> int:
        """Automatically creates effective standings requests for
        alt characters on Auth that already have blue standing in-game.

        return count of generated standings requests
        """
        logger.info("Started generating standings request for blue alts.")
        owned_characters_qs = EveCharacter.objects.filter(
            character_ownership__isnull=False
        )
        created_counter = 0
        for alt in owned_characters_qs:
            user = alt.character_ownership.user
            if (
                not MainOrganizations.is_character_a_member(alt)
                and not StandingRequest.objects.filter(
                    user=user, contact_id=alt.character_id
                ).exists()
                and not StandingRevocation.objects.filter(
                    contact_id=alt.character_id
                ).exists()
                and self.contact_has_satisfied_standing(alt.character_id)
            ):
                sr = StandingRequest.objects.add_request(
                    user=user,
                    contact_id=alt.character_id,
                    contact_type=StandingRequest.CHARACTER_CONTACT_TYPE,
                )
                sr.mark_actioned(None)
                sr.mark_effective()
                logger.info(
                    "Generated standings request for blue alt %s "
                    "belonging to user %s.",
                    alt,
                    user,
                )
                created_counter += 1

        logger.info(
            "Completed generating %d standings request for blue alts.",
            created_counter,
        )
        return created_counter

    @staticmethod
    def required_esi_scope() -> str:
        """returns the required ESI scopes for syncing"""
        if BaseConfig.operation_mode == "alliance":
            return "esi-alliances.read_contacts.v1"
        elif BaseConfig.operation_mode == "corporation":
            return "esi-corporations.read_contacts.v1"
        else:
            raise NotImplementedError()


class ContactLabel(models.Model):
    """A contact label"""

    contact_set = models.ForeignKey(
        ContactSet, on_delete=models.CASCADE, related_name="labels"
    )
    label_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=254, db_index=True)

    def __str__(self):
        return self.name

    def __repr__(self):
        return (
            f"{type(self).__name__}(pk={self.pk}, "
            f"label_id={self.label_id}, name='{self.name}')"
        )


class Contact(models.Model):
    """An Eve Online contact."""

    contact_set = models.ForeignKey(
        ContactSet, on_delete=models.CASCADE, related_name="contacts"
    )
    eve_entity = models.ForeignKey(
        EveEntity, on_delete=models.CASCADE, related_name="standingrequests_contact"
    )
    standing = models.FloatField(db_index=True)
    labels = models.ManyToManyField(ContactLabel, related_name="contacts")
    is_watched = models.BooleanField(default=False)

    objects = ContactQuerySet.as_manager()

    def __str__(self):
        return self.eve_entity.name

    def __repr__(self):
        return (
            f"{type(self).__name__}(pk={self.pk}, "
            f"contact_id={self.eve_entity_id}, name='{self.eve_entity.name}', "
            f"standing={self.standing})"
        )

    @property
    def name(self) -> str:
        return self.eve_entity.name

    @property
    def is_standing_satisfied(self) -> str:
        return StandingRequest.is_standing_satisfied(self.standing)


class AbstractStandingsRequest(models.Model):
    """Base class for a standing request"""

    # possible contact types to make a request for
    CHARACTER_CONTACT_TYPE = "character"
    CORPORATION_CONTACT_TYPE = "corporation"

    # Standing less than or equal
    EXPECT_STANDING_LTEQ = 10.0

    # Standing greater than or equal
    EXPECT_STANDING_GTEQ = -10.0

    # permission needed to request standing
    REQUEST_PERMISSION_NAME = "standingsrequests.request_standings"

    contact_id = models.PositiveIntegerField(
        db_index=True, help_text="EVE Online ID of contact this standing is for"
    )
    contact_type_id = models.PositiveIntegerField(
        db_index=True, help_text="EVE Online Type ID of this contact"
    )
    request_date = models.DateTimeField(
        auto_now_add=True, db_index=True, help_text="datetime this request was created"
    )
    action_by = models.ForeignKey(
        User,
        default=None,
        null=True,
        on_delete=models.SET_DEFAULT,
        db_index=True,
        help_text="standing manager that accepted or rejected this requests",
    )
    action_date = models.DateTimeField(
        null=True, db_index=True, help_text="datetime of action by standing manager"
    )
    is_effective = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True, when this standing is also set in-game, else False",
    )
    effective_date = models.DateTimeField(
        null=True, help_text="Datetime when this standing was set active in-game"
    )

    objects = AbstractStandingsRequestManager()

    class Meta:
        permissions = (
            ("affect_standings", "User can process standings requests."),
            ("request_standings", "User can request standings."),
        )

    def __repr__(self) -> str:
        try:
            user_str = f", user='{self.user}'"
        except AttributeError:
            user_str = ""

        return (
            f"{type(self).__name__}(pk={self.pk}, contact_id={self.contact_id}"
            f"{user_str}, is_effective={self.is_effective})"
        )

    @property
    def is_character(self) -> bool:
        return ContactType.is_character(self.contact_type_id)

    @property
    def is_corporation(self) -> bool:
        return ContactType.is_corporation(self.contact_type_id)

    @property
    def is_actioned(self) -> bool:
        return self.action_date is not None and not self.is_effective

    @property
    def is_pending(self) -> bool:
        return self.action_date is None and self.is_effective is False

    @classmethod
    def is_standing_satisfied(cls, standing: float) -> bool:
        if standing is not None:
            return (
                cls.EXPECT_STANDING_GTEQ <= float(standing) <= cls.EXPECT_STANDING_LTEQ
            )
        else:
            return False

    @classmethod
    def contact_type_2_id(cls, contact_type) -> int:
        if contact_type == cls.CHARACTER_CONTACT_TYPE:
            return ContactType.character_id
        elif contact_type == cls.CORPORATION_CONTACT_TYPE:
            return ContactType.corporation_id
        else:
            raise ValueError("Invalid contact type")

    @classmethod
    def contact_id_2_type(cls, contact_type_id) -> str:
        if contact_type_id in ContactType.character_ids:
            return cls.CHARACTER_CONTACT_TYPE
        elif contact_type_id in ContactType.corporation_ids:
            return cls.CORPORATION_CONTACT_TYPE
        else:
            raise ValueError("Invalid contact type")

    def evaluate_effective_standing(self, check_only: bool = False) -> bool:
        """
        Check and mark a standing as satisfied
        :param check_only: Check the standing only, take no action
        """
        try:
            logger.debug("Checking standing for %d", self.contact_id)
            latest = ContactSet.objects.latest()
            contact = latest.contacts.get(eve_entity_id=self.contact_id)
            if self.is_standing_satisfied(contact.standing):
                # Standing is satisfied
                logger.debug("Standing satisfied for %d", self.contact_id)
                if not check_only:
                    self.mark_effective()
                return True

        except exceptions.ObjectDoesNotExist:
            logger.debug(
                "No standing set for %d, checking if neutral is OK", self.contact_id
            )
            if self.is_standing_satisfied(0):
                # Standing satisfied but deleted (neutral)
                logger.debug(
                    "Standing satisfied but deleted (neutral) for %d", self.contact_id
                )
                if not check_only:
                    self.mark_effective()
                return True

        # Standing not satisfied
        logger.debug("Standing NOT satisfied for %d", self.contact_id)
        return False

    def mark_effective(self, date=None):
        """
        Marks a standing as effective (standing exists in game)
        from the current or supplied TZ aware datetime
        :param date: TZ aware datetime object of when the standing became effective
        :return:
        """
        logger.debug("Marking standing for %d as effective", self.contact_id)
        self.is_effective = True
        self.effective_date = date if date else now()
        self.save()

    def mark_actioned(self, user, date=None):
        """
        Marks a standing as actioned (user has made the change in game)
        with the current or supplied TZ aware datetime
        :param user: Actioned By django User
        :param date: TZ aware datetime object of when the action was taken
        :return:
        """
        logger.debug("Marking standing for %d as actioned", self.contact_id)
        self.action_by = user
        self.action_date = date if date else now()
        self.save()

    def check_actioned_timeout(self):
        """
        Check that a standing hasn't been marked as actioned
        and is still not effective ~24hr later
        :return: User if the actioned has timed out, False if it has not,
        None if the check was unsuccessful
        """
        logger.debug("Checking standings request timeout")
        if self.is_effective:
            logger.debug("Standing is already marked as effective...")
            return None

        if self.action_by is None:
            logger.debug("Standing was never actioned, cannot timeout")
            return None

        try:
            latest = ContactSet.objects.latest()
        except ContactSet.DoesNotExist:
            logger.debug("Cannot check standing timeout, no standings available")
            return None

        # Reset request that has not become effective after timeout expired
        if self.action_date + timedelta(hours=SR_STANDING_TIMEOUT_HOURS) < latest.date:
            logger.info(
                "Standing actioned timed out, resetting actioned for contact_id %d",
                self.contact_id,
            )
            actioner = self.action_by
            self.action_by = None
            self.action_date = None
            self.save()
            return actioner
        return False

    def reset_to_initial(self) -> None:
        """
        Reset a standing back to its initial creation state
        (Not actioned and not effective)
        :return:
        """
        self.is_effective = False
        self.effective_date = None
        self.action_by = None
        self.action_date = None
        self.save()


class StandingRequest(AbstractStandingsRequest):
    """A change request to get standing for a character or corporation

    OR a record representing that a character or corporation currently has standing

    Standing Requests (SR) can have one of 3 states:
    - new: Newly created SRs represent a new request from a user. They are not actioned and not effective
    - actionied: A standing manager marks a SR as actionied, once he has set the new standing in-game
    - effective: Once the new standing is returned from the API a SR is marked effective. Effective SRs stay in database to represent that a user has standing.
    """

    EXPECT_STANDING_GTEQ = 0.01

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    objects = StandingRequestManager()

    def delete(self, using=None, keep_parents=False, reason=None):
        """
        Add a revocation before deleting if the standing has been
        actioned (pending) or is effective and
        doesn't already have a pending revocation request.
        """
        if self.action_by is not None or self.is_effective:
            # Check if theres not already a revocation pending
            if not StandingRevocation.objects.has_pending_request(self.contact_id):
                logger.debug(
                    "Adding revocation for deleted request "
                    "with contact_id %d type %s",
                    self.contact_id,
                    self.contact_type_id,
                )
                StandingRevocation.objects.add_revocation(
                    contact_id=self.contact_id,
                    contact_type=self.contact_id_2_type(self.contact_type_id),
                    user=self.user,
                    reason=reason,
                )
            else:
                logger.debug(
                    "Revocation already pending for deleted request "
                    "with contact_id %d type %s",
                    self.contact_id,
                    self.contact_type_id,
                )
        else:
            logger.debug(
                "Standing never effective, no revocation required "
                "for deleted request with contact_id %d type %s",
                self.contact_id,
                self.contact_type_id,
            )

        super().delete(using, keep_parents)

    @classmethod
    def can_request_corporation_standing(cls, corporation_id: int, user: User) -> bool:
        """
        Checks if given user owns all of the required corp tokens for standings to be permitted

        Params
        - corporation_id: corp to check for
        - user: User to check for

        returns True if they can request standings, False if they cannot
        """
        corporation = EveCorporation.get_by_id(corporation_id)
        return (
            corporation is not None
            and not corporation.is_npc
            and corporation.user_has_all_member_tokens(user)
        )

    @classmethod
    def has_required_scopes_for_request(
        cls, character: EveCharacter, user: User = None, quick_check: bool = False
    ) -> bool:
        """returns true if given character has the required scopes
        for issueing a standings request else false

        Params:
        - user: provide User object to shorten processing time
        - quick: if True will not check if tokens are valid to save time
        """
        if not user:
            try:
                ownership = CharacterOwnership.objects.select_related(
                    "user__profile__state"
                ).get(character__character_id=character.character_id)
            except CharacterOwnership.DoesNotExist:
                return False
            else:
                user = ownership.user

        state_name = user.profile.state.name
        scopes_string = " ".join(cls.get_required_scopes_for_state(state_name))
        token_qs = Token.objects.filter(
            character_id=character.character_id
        ).require_scopes(scopes_string)
        if not quick_check:
            token_qs = token_qs.require_valid()

        return token_qs.exists()

    @staticmethod
    def get_required_scopes_for_state(state_name: str) -> list:
        state_name = "" if not state_name else state_name
        return (
            SR_REQUIRED_SCOPES[state_name]
            if state_name in SR_REQUIRED_SCOPES
            else list()
        )


class StandingRevocation(AbstractStandingsRequest):
    """A standing revocation"""

    EXPECT_STANDING_LTEQ = 0.0

    class Reason(models.TextChoices):
        """Reason for revoking a standing."""

        NONE = "NO", _("None recorded")
        OWNER_REQUEST = "OR", _("Requested by character owner")
        LOST_PERMISSION = "LP", _("Character owner has lost permission")
        MISSING_CORP_TOKEN = "CT", _("Not all corp tokens are recorded in Auth.")
        REVOKED_IN_GAME = "RG", _("Standing has been revoked in game")

    user = models.ForeignKey(
        User, on_delete=models.SET_DEFAULT, default=None, null=True
    )
    reason = models.CharField(max_length=2, choices=Reason.choices, default=Reason.NONE)

    objects = StandingRevocationManager()


class CharacterAffiliation(models.Model):
    """Affiliation of a character."""

    character = models.OneToOneField(
        EveEntity,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="character_affiliation",
    )
    corporation = models.ForeignKey(
        EveEntity, on_delete=models.CASCADE, related_name="+"
    )
    alliance = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
    )
    faction = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
    )
    eve_character = models.ForeignKey(
        EveCharacter,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text="Related auth character (if any)",
    )
    updated = models.DateTimeField(auto_now_add=True)

    objects = CharacterAffiliationManager()

    def __str__(self) -> str:
        return self.character.name

    @cached_property
    def character_name(self) -> str:
        """Return character name for main."""
        return self.character.name if self.character.name else None


class CorporationDetails(models.Model):
    """A corporation affiliation."""

    corporation = models.OneToOneField(
        EveEntity,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="corporation_details",
    )

    alliance = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
    )
    ceo = models.ForeignKey(
        EveEntity,
        on_delete=models.CASCADE,
        related_name="+",
    )
    faction = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
    )
    member_count = models.PositiveIntegerField()
    ticker = models.CharField(max_length=255)

    objects = CorporationDetailsManager()

    def __str__(self) -> str:
        return self.corporation.name
