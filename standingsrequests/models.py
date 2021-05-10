from datetime import timedelta

from django.contrib.auth.models import User
from django.core import exceptions
from django.db import models
from django.utils.timezone import now
from esi.models import Token

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.evelinks import eveimageserver
from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .app_settings import (
    SR_OPERATION_MODE,
    SR_REQUIRED_SCOPES,
    SR_STANDING_TIMEOUT_HOURS,
    STANDINGS_API_CHARID,
    STR_ALLIANCE_IDS,
    STR_CORP_IDS,
)
from .helpers.evecorporation import EveCorporation
from .managers import (
    AbstractStandingsRequestManager,
    CharacterAssociationManager,
    ContactSetManager,
    EveEntityManager,
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

    def get_contact_by_id(self, contact_id: int, contact_type_id: int) -> object:
        """Attempts to fetch the contact for the given ID and type

        Params:
        - contact_id: Integer contact ID
        - contact_type_id: Integer contact type from the contact_type_ids attribute
        in concrete models

        Returns concrete contact Object or ObjectDoesNotExist exception
        """
        if contact_type_id in CharacterContact.contact_type_ids:
            return self.charactercontact_set.get(contact_id=contact_id)
        elif contact_type_id in CorporationContact.contact_type_ids:
            return self.corporationcontact_set.get(contact_id=contact_id)
        elif contact_type_id in AllianceContact.contact_type_ids:
            return self.alliancecontact_set.get(contact_id=contact_id)
        raise exceptions.ObjectDoesNotExist()

    def create_contact(
        self,
        contact_type_id: int,
        contact_id: int,
        name: str,
        standing: float,
        labels: list,
    ) -> object:
        """creates new contact"""
        StandingType = self.get_class_for_contact_type(contact_type_id)
        contact = StandingType.objects.create(
            contact_set=self,
            contact_id=contact_id,
            name=name,
            standing=standing,
        )
        for label in labels:
            contact.labels.add(label)

        return contact

    def character_has_satisfied_standing(self, contact_id: int) -> bool:
        return self.contact_has_satisfied_standing(
            contact_id, CharacterContact.get_contact_type_id()
        )

    def corporation_has_satisfied_standing(self, contact_id: int) -> bool:
        return self.contact_has_satisfied_standing(
            contact_id, CorporationContact.get_contact_type_id()
        )

    def contact_has_satisfied_standing(
        self, contact_id: int, contact_type_id: int
    ) -> bool:
        """Return True if give contact has standing exists"""
        if contact_type_id in CharacterContact.contact_type_ids:
            try:
                contact = self.charactercontact_set.get(contact_id=contact_id)
            except CharacterContact.DoesNotExist:
                return False

        elif contact_type_id in CorporationContact.contact_type_ids:
            try:
                contact = self.corporationcontact_set.get(contact_id=contact_id)
            except CorporationContact.DoesNotExist:
                return False

        elif contact_type_id in AllianceContact.contact_type_ids:
            try:
                contact = self.alliancecontact_set.get(contact_id=contact_id)
            except CorporationContact.DoesNotExist:
                return False

        else:
            raise ValueError("Invalid contact type ID: %s" % contact_type_id)

        return StandingRequest.is_standing_satisfied(contact.standing)

    @staticmethod
    def get_class_for_contact_type(contact_type_id):
        if contact_type_id in CharacterContact.contact_type_ids:
            return CharacterContact
        elif contact_type_id in CorporationContact.contact_type_ids:
            return CorporationContact
        elif contact_type_id in AllianceContact.contact_type_ids:
            return AllianceContact
        raise ValueError("Invalid contact type ID: %s" % contact_type_id)

    @classmethod
    def is_character_in_organisation(cls, character: EveCharacter) -> bool:
        """Check if the Pilot is in the auth instances organisation

        character: EveCharacter

        returns True if the character is in the organisation, False otherwise
        """
        return (
            character.corporation_id in cls.corporation_ids_in_organization()
            or character.alliance_id in cls.alliance_ids_in_organization()
        )

    def corporation_ids_in_organization() -> set:
        return {int(org_id) for org_id in list(STR_CORP_IDS)}

    @staticmethod
    def alliance_ids_in_organization() -> set:
        return {int(org_id) for org_id in list(STR_ALLIANCE_IDS)}

    @staticmethod
    def required_esi_scope() -> str:
        """returns the required ESI scopes for syncing"""
        if SR_OPERATION_MODE == "alliance":
            return "esi-alliances.read_contacts.v1"
        elif SR_OPERATION_MODE == "corporation":
            return "esi-corporations.read_contacts.v1"
        else:
            raise NotImplementedError()

    @staticmethod
    def standings_character() -> EveCharacter:
        """returns the configured standings character"""
        try:
            character = EveCharacter.objects.get(character_id=STANDINGS_API_CHARID)
        except EveCharacter.DoesNotExist:
            character = EveCharacter.objects.create_character(STANDINGS_API_CHARID)
            EveEntity.objects.get_or_create(
                entity_id=character.character_id,
                defaults={
                    "name": character.character_name,
                    "category": EveEntity.CATEGORY_CHARACTER,
                },
            )

        return character

    @classmethod
    def standings_source_entity(cls) -> object:
        """returns the entity that all standings are fetched from

        returns None when in alliance mode, but character has no alliance
        """
        character = cls.standings_character()
        if SR_OPERATION_MODE == "alliance":
            if character.alliance_id:
                entity, _ = EveEntity.objects.get_or_create(
                    entity_id=character.alliance_id,
                    defaults={
                        "name": character.alliance_name,
                        "category": EveEntity.CATEGORY_ALLIANCE,
                    },
                )
            else:
                entity = None
        elif SR_OPERATION_MODE == "corporation":
            entity, _ = EveEntity.objects.get_or_create(
                entity_id=character.corporation_id,
                defaults={
                    "name": character.corporation_name,
                    "category": EveEntity.CATEGORY_CORPORATION,
                },
            )
        else:
            raise NotImplementedError()

        return entity

    def generate_standing_requests_for_blue_alts(self) -> int:
        """Automatically creates effective standings requests for
        alt characters on Auth that already have blue standing in-game.

        return count of generated standings requests
        """
        logger.info("Started generating standings request for blue alts.")
        owned_characters_qs = EveCharacter.objects.filter(
            character_ownership__isnull=False
        ).select_related()
        created_counter = 0
        for alt in owned_characters_qs:
            user = alt.character_ownership.user
            if (
                not self.is_character_in_organisation(alt)
                and not StandingRequest.objects.filter(
                    user=user, contact_id=alt.character_id
                ).exists()
                and not StandingRevocation.objects.filter(
                    contact_id=alt.character_id
                ).exists()
                and self.character_has_satisfied_standing(alt.character_id)
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


class ContactLabel(models.Model):
    """A contact label"""

    contact_set = models.ForeignKey(ContactSet, on_delete=models.CASCADE)
    label_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=254, db_index=True)

    def __str__(self):
        return self.name

    def __repr__(self):
        return (
            f"{type(self).__name__}(pk={self.pk}, "
            f"label_id={self.label_id}, name='{self.name}')"
        )


class AbstractContact(models.Model):
    """Base class for a contact"""

    CHARACTER_AMARR_TYPE_ID = 1373
    CHARACTER_NI_KUNNI_TYPE_ID = 1374
    CHARACTER_CIVRE_TYPE_ID = 1375
    CHARACTER_DETEIS_TYPE_ID = 1376
    CHARACTER_GALLENTE_TYPE_ID = 1377
    CHARACTER_INTAKI_TYPE_ID = 1378
    CHARACTER_SEBIESTOR_TYPE_ID = 1379
    CHARACTER_BRUTOR_TYPE_ID = 1380
    CHARACTER_STATIC_TYPE_ID = 1381
    CHARACTER_MODIFIER_TYPE_ID = 1382
    CHARACTER_ACHURA_TYPE_ID = 1383
    CHARACTER_JIN_MEI_TYPE_ID = 1384
    CHARACTER_KHANID_TYPE_ID = 1385
    CHARACTER_VHEROKIOR_TYPE_ID = 1386
    CHARACTER_DRIFTER_TYPE_ID = 34574
    ALLIANCE_TYPE_ID = 16159
    CORPORATION_TYPE_ID = 2

    contact_set = models.ForeignKey(ContactSet, on_delete=models.CASCADE)
    contact_id = models.PositiveIntegerField(db_index=True)
    name = models.CharField(max_length=254, db_index=True)
    standing = models.FloatField(db_index=True)
    labels = models.ManyToManyField(ContactLabel)

    class Meta:
        abstract = True

    def __repr__(self):
        return (
            f"{type(self).__name__}(pk={self.pk}, "
            f"contact_id={self.contact_id}, name='{self.name}', "
            f"standing={self.standing})"
        )

    @classmethod
    def get_contact_type_id(cls) -> int:
        """returns the contact type ID for this type of contact"""
        try:
            return cls.contact_type_ids[0]
        except AttributeError:
            raise NotImplementedError() from None

    @classmethod
    def get_contact_type_ids(cls) -> int:
        """returns the list of valid contact type IDs for this type of contact"""
        try:
            return cls.contact_type_ids
        except AttributeError:
            raise NotImplementedError() from None

    @staticmethod
    def is_character(type_id):
        return type_id in CharacterContact.contact_type_ids

    @staticmethod
    def is_corporation(type_id):
        return type_id in CorporationContact.contact_type_ids

    @staticmethod
    def is_alliance(type_id):
        return type_id in AllianceContact.contact_type_ids


class CharacterContact(AbstractContact):
    """A character contact"""

    contact_type_ids = [
        AbstractContact.CHARACTER_AMARR_TYPE_ID,
        AbstractContact.CHARACTER_NI_KUNNI_TYPE_ID,
        AbstractContact.CHARACTER_CIVRE_TYPE_ID,
        AbstractContact.CHARACTER_DETEIS_TYPE_ID,
        AbstractContact.CHARACTER_GALLENTE_TYPE_ID,
        AbstractContact.CHARACTER_INTAKI_TYPE_ID,
        AbstractContact.CHARACTER_SEBIESTOR_TYPE_ID,
        AbstractContact.CHARACTER_BRUTOR_TYPE_ID,
        AbstractContact.CHARACTER_STATIC_TYPE_ID,
        AbstractContact.CHARACTER_MODIFIER_TYPE_ID,
        AbstractContact.CHARACTER_ACHURA_TYPE_ID,
        AbstractContact.CHARACTER_JIN_MEI_TYPE_ID,
        AbstractContact.CHARACTER_KHANID_TYPE_ID,
        AbstractContact.CHARACTER_VHEROKIOR_TYPE_ID,
        AbstractContact.CHARACTER_DRIFTER_TYPE_ID,
    ]
    is_watched = models.BooleanField(default=False)


class CorporationContact(AbstractContact):
    """A corporation contact"""

    contact_type_ids = [AbstractContact.CORPORATION_TYPE_ID]


class AllianceContact(AbstractContact):
    """An alliance contact"""

    contact_type_ids = [AbstractContact.ALLIANCE_TYPE_ID]


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
        return AbstractContact.is_character(self.contact_type_id)

    @property
    def is_corporation(self) -> bool:
        return AbstractContact.is_corporation(self.contact_type_id)

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
            return CharacterContact.get_contact_type_id()
        elif contact_type == cls.CORPORATION_CONTACT_TYPE:
            return CorporationContact.get_contact_type_id()
        else:
            raise ValueError("Invalid contact type")

    @classmethod
    def contact_id_2_type(cls, contact_type_id) -> str:
        if contact_type_id in CharacterContact.get_contact_type_ids():
            return cls.CHARACTER_CONTACT_TYPE
        elif contact_type_id in CorporationContact.get_contact_type_ids():
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
            contact = latest.get_contact_by_id(self.contact_id, self.contact_type_id)
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

    def delete(self, using=None, keep_parents=False):
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

    user = models.ForeignKey(
        User, on_delete=models.SET_DEFAULT, default=None, null=True
    )

    objects = StandingRevocationManager()


class CharacterAssociation(models.Model):
    """
    Alt Character Associations with declared mains
    Main characters are associated with themselves
    """

    API_CACHE_TIMER = timedelta(days=3)

    character_id = models.PositiveIntegerField(primary_key=True)
    corporation_id = models.PositiveIntegerField(null=True)
    alliance_id = models.PositiveIntegerField(null=True)
    main_character_id = models.PositiveIntegerField(null=True)
    updated = models.DateTimeField(auto_now_add=True)

    objects = CharacterAssociationManager()

    @property
    def character_name(self):
        """
        Character name property for character_id
        :return: str character name
        """
        name = EveEntity.objects.get_name(self.character_id)
        return name

    @property
    def main_character_name(self):
        """
        Character name property for character_id
        :return: str character name
        """
        if self.main_character_id:
            name = EveEntity.objects.get_name(self.main_character_id)
        else:
            name = None
        return name


class EveEntity(models.Model):
    """An Eve Online entity like a character or a corporation

    A main function of this class is to enable name matching for Eve IDs
    """

    CACHE_TIME = timedelta(days=30)

    CATEGORY_ALLIANCE = "alliance"
    CATEGORY_CHARACTER = "character"
    CATEGORY_CONSTELLATION = "constellation"
    CATEGORY_CORPORATION = "corporation"
    CATEGORY_FACTION = "faction"
    CATEGORY_INVENTORY_TYPE = "inventory_type"
    CATEGORY_REGION = "region"
    CATEGORY_SOLAR_SYSTEM = "solar_system"
    CATEGORY_STATION = "station"

    CATEGORY_CHOICES = (
        (CATEGORY_ALLIANCE, "alliance"),
        (CATEGORY_CHARACTER, "character"),
        (CATEGORY_CONSTELLATION, "constellation"),
        (CATEGORY_CORPORATION, "corporation"),
        (CATEGORY_FACTION, "faction"),
        (CATEGORY_INVENTORY_TYPE, "inventory_type"),
        (CATEGORY_REGION, "region"),
        (CATEGORY_SOLAR_SYSTEM, "solar_system"),
        (CATEGORY_STATION, "station"),
    )

    entity_id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=254)
    category = models.CharField(
        max_length=16, choices=CATEGORY_CHOICES, default=None, null=True
    )
    updated = models.DateTimeField(auto_now=True, db_index=True)

    objects = EveEntityManager()

    def icon_url(self, size: int = eveimageserver._DEFAULT_IMAGE_SIZE) -> str:
        map_category_2_other = {
            self.CATEGORY_ALLIANCE: "alliance_logo_url",
            self.CATEGORY_CHARACTER: "character_portrait_url",
            self.CATEGORY_CORPORATION: "corporation_logo_url",
            self.CATEGORY_INVENTORY_TYPE: "type_icon_url",
        }
        if self.category not in map_category_2_other:
            return ""
        else:
            func = map_category_2_other[self.category]
            return getattr(eveimageserver, func)(self.entity_id, size=size)
