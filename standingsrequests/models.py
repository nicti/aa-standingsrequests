import datetime

from django.core import exceptions
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger

from . import __title__
from .app_settings import (
    SR_OPERATION_MODE,
    STANDINGS_API_CHARID,
    SR_STANDING_TIMEOUT_HOURS,
)
from .helpers import StandingsRequestManager
from .managers.eveentity import EveEntityManager
from .utils import LoggerAddTag

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class ContactSet(models.Model):
    """Set of contacts from configured alliance or corporation 
    which defines its current standings
    """

    date = models.DateTimeField(auto_now_add=True, db_index=True)
    name = models.CharField(max_length=254)

    class Meta:
        get_latest_by = "date"
        permissions = (
            ("view", "User can view standings"),
            ("download", "User can export standings to a CSV file"),
        )

    def __str__(self):
        return str(self.date)

    def get_standing_for_id(self, contact_id, contact_type_id):
        """
        Attempts to fetch the standing for the given ID and type
        :param contact_id: Integer contact ID
        :param contact_type_id: Integer contact type from the contact_types attribute 
        in concrete models
        :return: concrete contact Object or ObjectDoesNotExist exception
        """
        if contact_type_id in PilotStanding.contact_types:
            return self.pilotstanding_set.get(contact_id=contact_id)
        elif contact_type_id in CorpStanding.contact_types:
            return self.corpstanding_set.get(contact_id=contact_id)
        elif contact_type_id in AllianceStanding.contact_types:
            return self.alliancestanding_set.get(contact_id=contact_id)
        raise exceptions.ObjectDoesNotExist()

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
            EveNameCache.objects.get_or_create(
                entity_id=character.character_id,
                defaults={"name": character.character_name},
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
                entity, _ = EveNameCache.objects.get_or_create(
                    entity_id=character.alliance_id,
                    defaults={"name": character.alliance_name},
                )
            else:
                entity = None
        elif SR_OPERATION_MODE == "corporation":
            entity, _ = EveNameCache.objects.get_or_create(
                entity_id=character.corporation_id,
                defaults={"name": character.corporation_name},
            )
        else:
            raise NotImplementedError()

        return entity


class ContactLabel(models.Model):
    """A contact label"""

    contact_set = models.ForeignKey(ContactSet, on_delete=models.CASCADE)
    label_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=254)


class AbstractStanding(models.Model):
    """Base class for a standing"""

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
    name = models.CharField(max_length=254)
    standing = models.FloatField(db_index=True)
    labels = models.ManyToManyField(ContactLabel)

    class Meta:
        abstract = True

    @classmethod
    def get_contact_type_id(cls, contact_id):
        raise NotImplementedError()


class PilotStanding(AbstractStanding):
    contact_types = [
        AbstractStanding.CHARACTER_AMARR_TYPE_ID,
        AbstractStanding.CHARACTER_NI_KUNNI_TYPE_ID,
        AbstractStanding.CHARACTER_CIVRE_TYPE_ID,
        AbstractStanding.CHARACTER_DETEIS_TYPE_ID,
        AbstractStanding.CHARACTER_GALLENTE_TYPE_ID,
        AbstractStanding.CHARACTER_INTAKI_TYPE_ID,
        AbstractStanding.CHARACTER_SEBIESTOR_TYPE_ID,
        AbstractStanding.CHARACTER_BRUTOR_TYPE_ID,
        AbstractStanding.CHARACTER_STATIC_TYPE_ID,
        AbstractStanding.CHARACTER_MODIFIER_TYPE_ID,
        AbstractStanding.CHARACTER_ACHURA_TYPE_ID,
        AbstractStanding.CHARACTER_JIN_MEI_TYPE_ID,
        AbstractStanding.CHARACTER_KHANID_TYPE_ID,
        AbstractStanding.CHARACTER_VHEROKIOR_TYPE_ID,
        AbstractStanding.CHARACTER_DRIFTER_TYPE_ID,
    ]
    is_watched = models.BooleanField(default=False)

    @classmethod
    def get_contact_type_id(cls, contact_id):
        """
        Get the type ID for the contact_id

        Just spoofs it at the moment, not actually the correct race ID
        :return: contact_type_id
        """
        return cls.contact_types[0]

    @classmethod
    def is_pilot(cls, type_id):
        return type_id in cls.contact_types


class CorpStanding(AbstractStanding):
    contact_types = [AbstractStanding.CORPORATION_TYPE_ID]

    @classmethod
    def get_contact_type_id(cls, contact_id):
        """
        Get the type ID for the contact_id
        :return: contact_type_id
        """
        return cls.contact_types[0]

    @classmethod
    def is_corp(cls, type_id):
        return type_id in cls.contact_types


class AllianceStanding(AbstractStanding):
    contact_types = [AbstractStanding.ALLIANCE_TYPE_ID]

    @classmethod
    def get_contact_type_id(cls, contact_id):
        """
        Get the type ID for the contact
        :return: contact_type_id
        """
        return cls.contact_types[0]

    @classmethod
    def is_alliance(cls, type_id):
        return type_id in cls.contact_types


class AbstractStandingsRequest(models.Model):
    """Base class for a standing request"""

    # Standing less than or equal
    EXPECT_STANDING_LTEQ = 10.0

    # Standing greater than or equal
    EXPECT_STANDING_GTEQ = -10.0

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
        null=True, help_text="datetime of action by standing manager"
    )
    is_effective = models.BooleanField(
        default=False,
        help_text="True, when this standing is also set in-game, else False",
    )
    effective_date = models.DateTimeField(
        null=True, help_text="Datetime when this standing was set active in-game"
    )

    class Meta:
        permissions = (
            ("affect_standings", "User can process standings requests."),
            ("request_standings", "User can request standings."),
        )

    def __repr__(self) -> str:
        user_str = f", user='{self.user}'" if hasattr(self, "user") else ""
        return (
            f"{type(self).__name__}(pk={self.pk}, contact_id={self.contact_id}"
            f"{user_str}, is_effective={self.is_effective})"
        )

    def process_standing(self, check_only: bool = False) -> bool:
        """
        Check and mark a standing as satisfied
        :param check_only: Check the standing only, take no action        
        """
        try:
            logger.debug("Checking standing for %d", self.contact_id)
            latest = ContactSet.objects.latest()
            contact = latest.get_standing_for_id(self.contact_id, self.contact_type_id)
            if (
                self.EXPECT_STANDING_GTEQ
                <= contact.standing
                <= self.EXPECT_STANDING_LTEQ
            ):
                # Standing is satisfied
                logger.debug("Standing satisfied for %d", self.contact_id)
                if not check_only:
                    self.mark_standing_effective()
                return True

        except exceptions.ObjectDoesNotExist:
            logger.debug(
                "No standing set for %d, checking if neutral is OK", self.contact_id
            )
            if self.EXPECT_STANDING_LTEQ == 0:
                # Standing satisfied but deleted (neutral)
                logger.debug(
                    "Standing satisfied but deleted (neutral) for %d", self.contact_id
                )
                if not check_only:
                    self.mark_standing_effective()
                return True

        # Standing not satisfied
        logger.debug("Standing NOT satisfied for %d", self.contact_id)
        return False

    def mark_standing_effective(self, date=None):
        """
        Marks a standing as effective (standing exists in game) 
        from the current or supplied TZ aware datetime
        :param date: TZ aware datetime object of when the standing became effective
        :return:
        """
        logger.debug("Marking standing for %d as effective", self.contact_id)
        self.is_effective = True
        self.effective_date = date if date else timezone.now()
        self.save()

    def mark_standing_actioned(self, user, date=None):
        """
        Marks a standing as actioned (user has made the change in game) 
        with the current or supplied TZ aware datetime
        :param user: Actioned By django User
        :param date: TZ aware datetime object of when the action was taken
        :return:
        """
        logger.debug("Marking standing for %d as actioned", self.contact_id)
        self.action_by = user
        self.action_date = date if date else timezone.now()
        self.save()

    def check_standing_actioned_timeout(self):
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
        if (
            self.action_date + datetime.timedelta(hours=SR_STANDING_TIMEOUT_HOURS)
            < latest.date
        ):
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

    @classmethod
    def pending_request(cls, contact_id) -> bool:
        """
        Checks if a request is pending for the given contact_id
        :param contact_id: int contact_id to check the pending request for
        :return: bool True if a request is already pending, False otherwise
        """
        pending = (
            cls.objects.filter(contact_id=contact_id)
            .filter(action_by=None)
            .filter(is_effective=False)
        )
        return pending.exists()

    @classmethod
    def actioned_request(cls, contact_id) -> bool:
        """
        Checks if an actioned request is pending API confirmation for 
        the given contact_id
        :param contact_id: int contact_id to check the pending request for
        :return: bool True if a request is pending API confirmation, False otherwise
        """
        pending = (
            cls.objects.filter(contact_id=contact_id)
            .exclude(action_by=None)
            .filter(is_effective=False)
        )
        return pending.exists()


class StandingsRequest(AbstractStandingsRequest):
    """A standing request"""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    EXPECT_STANDING_GTEQ = 0.01

    objects = StandingsRequestManager()

    def delete(self, using=None, keep_parents=False):
        """
        Add a revocation before deleting if the standing has been 
        actioned (pending) or is effective and
        doesn't already have a pending revocation request.
        """
        if self.action_by is not None or self.is_effective:
            # Check if theres not already a revocation pending
            if not StandingsRevocation.pending_request(self.contact_id):
                logger.debug(
                    "Adding revocation for deleted request "
                    "with contact_id %d type %s",
                    self.contact_id,
                    self.contact_type_id,
                )
                StandingsRevocation.add_revocation(
                    self.contact_id, self.contact_type_id
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

        super(AbstractStandingsRequest, self).delete(using, keep_parents)

    @classmethod
    def add_request(cls, user, contact_id, contact_type_id):
        """
        Add a new standings request
        :param user: User the request and contact_id belongs to
        :param contact_id: contact_id to request standings on
        :param contact_type_id: contact_type_id from a AbstractStanding concrete class
        :return: the created StandingsRequest instance
        """
        logger.debug(
            "Adding new standings request for user %s, contact %d type %s",
            user,
            contact_id,
            contact_type_id,
        )

        if cls.objects.filter(
            contact_id=contact_id, contact_type_id=contact_type_id
        ).exists():
            logger.debug(
                "Standings request already exists, " "returning first existing request"
            )
            return cls.objects.filter(
                contact_id=contact_id, contact_type_id=contact_type_id
            )[0]

        instance = cls(
            user=user, contact_id=contact_id, contact_type_id=contact_type_id
        )
        instance.save()
        return instance

    @classmethod
    def remove_requests(cls, contact_id):
        """
        Remove the requests for the given contact_id. If any of these requests 
        have been actioned or are effective
        a Revocation request will automatically be generated
        :param contact_id: str contact_id to remove.
        :return:
        """
        logger.debug("Removing requests for contact_id %d", contact_id)
        requests = cls.objects.filter(contact_id=contact_id)
        logger.debug("%d requests to be removed", len(requests))
        requests.delete()


class StandingsRevocation(AbstractStandingsRequest):
    """A standing revocation"""

    EXPECT_STANDING_LTEQ = 0.0

    @classmethod
    def add_revocation(cls, contact_id, contact_type_id):
        """
        Add a new standings revocation
        :param contact_id: contact_id to request standings on
        :param contact_type_id: contact_type_id from AbstractStanding concrete implementation
        :return: the created StandingsRevocation instance
        """
        logger.debug(
            "Adding new standings revocation for contact %d type %s",
            contact_id,
            contact_type_id,
        )
        pending = cls.objects.filter(contact_id=contact_id).filter(is_effective=False)
        if pending.exists():
            logger.debug(
                "Cannot add revocation for contact %d %s, " "pending revocation exists",
                contact_id,
                contact_type_id,
            )
            return None

        instance = cls(contact_id=contact_id, contact_type_id=contact_type_id)
        instance.save()
        return instance

    @classmethod
    def undo_revocation(cls, contact_id, owner):
        """
        Converts existing revocation into request if it exists
        :param contact_id: contact_id to request standings on
        :param owner: user owning the revocation
        :return: created StandingsRequest pendant 
            or False if revocation does not exist
        """
        logger.debug("Undoing revocation for contact_id %d", contact_id)
        revocations = cls.objects.filter(contact_id=contact_id)

        if not revocations.exists():
            return False

        request = StandingsRequest.add_request(
            owner, contact_id, revocations[0].contact_type_id
        )
        revocations.delete()
        return request


class CharacterAssociation(models.Model):
    """
    Alt Character Associations with declared mains
    Main characters are associated with themselves
    """

    API_CACHE_TIMER = datetime.timedelta(days=3)

    character_id = models.PositiveIntegerField(primary_key=True)
    corporation_id = models.PositiveIntegerField(null=True)
    alliance_id = models.PositiveIntegerField(null=True)
    main_character_id = models.PositiveIntegerField(null=True)
    updated = models.DateTimeField(auto_now_add=True)

    @property
    def character_name(self):
        """
        Character name property for character_id
        :return: str character name
        """
        name = EveNameCache.get_name(self.character_id)
        return name

    @property
    def main_character_name(self):
        """
        Character name property for character_id
        :return: str character name
        """
        if self.main_character_id:
            name = EveNameCache.get_name(self.main_character_id)
        else:
            name = None
        return name

    @classmethod
    def get_api_expired_items(cls, items_in=None):
        """
        Get all API timer expired items
        :param items_in: list optional parameter to limit the results 
        to character_ids in the list
        :return: QuerySet of CharacterAssociation items 
        that have expired their API timer
        """
        expired = cls.objects.filter(updated__lt=timezone.now() - cls.API_CACHE_TIMER)
        if items_in is not None:
            expired = expired.filter(character_id__in=items_in)

        return expired


class EveNameCache(models.Model):
    """
    Cache for all entity names (Characters, Corps, Alliances)

    Keeping our own cache because allianceauth deletes characters with no API key
    """

    CACHE_TIME = datetime.timedelta(days=30)

    entity_id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=254)
    updated = models.DateTimeField(auto_now_add=True)

    @classmethod
    def get_names(cls, entity_ids: list):
        """
        Get the names of the given entity ids from catch or other locations
        :param eve_entity_ids: array of int entity ids who's names to fetch
        :return: dict with entity_id as key and name as value
        """
        # make sure there are no duplicates
        entity_ids = set(entity_ids)
        name_info = {}
        entities_need_update = []
        entity_ids_not_found = []
        for entity_id in entity_ids:
            if cls.objects.filter(entity_id=entity_id).exists():
                # Cached
                entity = cls.objects.get(entity_id=entity_id)
                if entity.cache_timeout():
                    entities_need_update.append(entity)
                else:
                    name_info[entity.entity_id] = entity.name
            else:
                entity_ids_not_found.append(entity_id)

        entities_need_names = [
            e.entity_id for e in entities_need_update
        ] + entity_ids_not_found

        names_info_api = EveEntityManager.get_names(entities_need_names)

        # update existing entities
        for entity in entities_need_update:
            if entity.entity_id in names_info_api:
                name = names_info_api[entity.entity_id]
                entity._set_name(name)
            else:
                entity._update_entity()

            name_info[entity.entity_id] = entity.name

        # create new entities
        for entity_id in entity_ids_not_found:
            if entity_id in names_info_api:
                entity = cls()
                entity.entity_id = entity_id
                entity._set_name(names_info_api[entity_id])
                name_info[entity_id] = entity.name

        return name_info

    @classmethod
    def get_name(cls, entity_id: int) -> str:
        """
        Get the name for the given entity
        :param entity_id: EVE id of the entity
        :return: str name if it exists or None
        """
        if cls.objects.filter(entity_id=entity_id).exists():
            # Cached
            entity = cls.objects.get(entity_id=entity_id)
            if entity.cache_timeout():
                entity._update_entity()
        else:
            # Fetch name/not cached
            entity = cls()
            entity.entity_id = entity_id
            entity._update_entity()
            # If the name is updated it will be saved,
            # otherwise this object will be discarded
            # when it goes out of scope
        return entity.name or None

    def _update_entity(self, allow_api=True):
        """
        Update the entities name. Callers are responsible for checking cache timing.
        :return: bool
        """
        # Try sources in order of preference, API call last

        if self._update_from_contacts():
            return True
        elif self._update_from_auth():
            return True
        elif allow_api and self._update_from_api():
            return True
        return False

    def _update_from_contacts(self):
        """
        Attempt to update the entity from the latest contacts data
        :return: bool True if successful, False otherwise
        """
        contact = None
        try:
            contacts = ContactSet.objects.latest()
            if contacts.pilotstanding_set.filter(contact_id=self.entity_id).exists():
                contact = contacts.pilotstanding_set.get(contact_id=self.entity_id)

            elif contacts.corpstanding_set.filter(contact_id=self.entity_id).exists():
                contact = contacts.corpstanding_set.get(contact_id=self.entity_id)

            elif contacts.alliancestanding_set.filter(
                contact_id=self.entity_id
            ).exists():
                contact = contacts.alliancestanding_set.get(contact_id=self.entity_id)

        except ContactSet.DoesNotExist:
            pass

        if contact is not None:
            self._set_name(contact.name)
            return True
        else:
            return False

    def _update_from_auth(self):
        """
        Attempt to update the entity from the parent auth installation
        :return: bool True if successful, False otherwise
        """
        auth_name = EveEntityManager.get_name_from_auth(self.entity_id)
        if auth_name is not None:
            self._set_name(auth_name)
            return True
        else:
            return False

    def _update_from_api(self):
        """
        Attempt to update the entity from the EVE API. 
        Should be a last resort (because slow)
        :return: bool True if successful, False otherwise
        """
        api_name = EveEntityManager.get_name_from_api(self.entity_id)
        if api_name is not None:
            self._set_name(api_name)
            return True
        else:
            return False

    def _set_name(self, name):
        """
        Set the entities name to name
        :param name: name to set the entities name to
        :return:
        """
        self.name = name
        self.updated = timezone.now()
        self.save()

    def cache_timeout(self):
        """
        Check if the cache timeout has been passed
        :return: bool True if the cache timer has expired, False otherwise
        """
        return timezone.now() > self.updated + self.CACHE_TIME

    @classmethod
    def update_name(cls, entity_id, name):
        cls.objects.update_or_create(
            entity_id=entity_id, defaults={"name": name, "updated": timezone.now(),}
        )
