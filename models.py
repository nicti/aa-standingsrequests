from __future__ import unicode_literals
from django.db import models
from django.core import exceptions
from django.utils import timezone
from django.contrib.auth.models import User
from .helpers import StandingsRequestManager
from .managers.eveentity import EveEntityManager
import logging
import datetime

logger = logging.getLogger(__name__)


class ContactSet(models.Model):
    class Meta:
        get_latest_by = 'date'
        permissions = (
            ("view", "User can view standings"),
            ("download", "User can export standings to a CSV file")
        )
    date = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=254)

    def __str__(self):
        return str(self.date)

    def get_standing_for_id(self, contact_id, contact_type):
        """
        Attempts to fetch the standing for the given ID and type
        :param contact_id: Integer contact ID
        :param contact_type: Integer contact type from the contactTypes attribute in concrete models
        :return: concrete contact Object or ObjectDoesNotExist exception
        """
        if contact_type in PilotStanding.contactTypes:
            return self.pilotstanding_set.get(contactID=contact_id)
        elif contact_type in CorpStanding.contactTypes:
            return self.corpstanding_set.get(contactID=contact_id)
        elif contact_type in AllianceStanding.contactTypes:
            return self.alliancestanding_set.get(contactID=contact_id)
        raise exceptions.ObjectDoesNotExist()


class ContactLabel(models.Model):
    labelID = models.BigIntegerField()
    set = models.ForeignKey(ContactSet, on_delete=models.CASCADE)
    name = models.CharField(max_length=254)


class AbstractStanding(models.Model):
    class Meta:
        abstract = True
    set = models.ForeignKey(ContactSet, on_delete=models.CASCADE)
    contactID = models.IntegerField()
    name = models.CharField(max_length=254)
    standing = models.FloatField()
    labels = models.ManyToManyField(ContactLabel)

    contactTypes = []

    @classmethod
    def get_contact_type(cls, contact_id):
        raise NotImplemented()


class PilotStanding(AbstractStanding):
    contactTypes = [i for i in range(1373, 1386+1)]
    inWatchlist = models.BooleanField(default=False)

    @classmethod
    def get_contact_type(cls, contact_id):
        """
        Get the type ID for the contactID

        Just spoofs it at the moment, not actually the correct race ID
        :return: contactType
        """
        return cls.contactTypes[0]

    @classmethod
    def is_pilot(cls, type_id):
        return type_id in cls.contactTypes


class CorpStanding(AbstractStanding):
    contactTypes = [2]

    @classmethod
    def get_contact_type(cls, contact_id):
        """
        Get the type ID for the contactID
        :return: contactType
        """
        return cls.contactTypes[0]

    @classmethod
    def is_corp(cls, type_id):
        return type_id in cls.contactTypes


class AllianceStanding(AbstractStanding):
    contactTypes = [16159]

    @classmethod
    def get_contact_type(cls, contact_id):
        """
        Get the type ID for the contactID
        :return: contactType
        """
        return cls.contactTypes[0]


class AbstractStandingsRequest(models.Model):
    class Meta:
        permissions = (
            ("affect_standings", "User can process standings requests."),
            ("request_standings", "User can request standings."),
        )

    contactID = models.IntegerField()
    contactType = models.IntegerField()
    requestDate = models.DateTimeField(auto_now_add=True)
    actionBy = models.ForeignKey(User, null=True, on_delete=models.DO_NOTHING)
    actionDate = models.DateTimeField(null=True)
    effective = models.BooleanField(default=False)
    effectiveDate = models.DateTimeField(null=True)

    expectStandingLTEQ = 10.0  # Standing less than or equal
    expectStandingGTEQ = -10.0  # Standing greater than or equal

    standingTimeoutHours = 24  # Hours to wait for a standing to be effective after being marked actioned

    def check_standing_satisfied(self, check_only=False):
        """
        Check and mark a standing as satisfied
        :param check_only: Check the standing only, take no action
        :return: True if satisfied else False
        """
        try:
            logger.debug("Checking standing for {0}".format(self.contactID))
            latest = ContactSet.objects.latest()
            contact = latest.get_standing_for_id(self.contactID, self.contactType)
            if self.expectStandingGTEQ <= contact.standing <= self.expectStandingLTEQ:
                # Standing is satisfied
                logger.debug("Standing satisfied for {0}".format(self.contactID))
                if not check_only:
                    self.mark_standing_effective()
                return True
        except exceptions.ObjectDoesNotExist:
            logger.debug("No standing set for {0}, checking if neutral is OK".format(self.contactID))
            if self.expectStandingLTEQ == 0:
                # Standing satisfied but deleted (neutral)
                logger.debug("Standing satisfied but deleted (neutral) for {0}".format(self.contactID))
                if not check_only:
                    self.mark_standing_effective()
                return True
        # Standing not satisfied
        logger.debug("Standing NOT satisfied for {0}".format(self.contactID))
        return False

    def mark_standing_effective(self, date=None):
        """
        Marks a standing as effective (standing exists in game) from the current or supplied TZ aware datetime
        :param date: TZ aware datetime object of when the standing became effective
        :return:
        """
        logger.debug("Marking standing for {0} as effective".format(self.contactID))
        self.effective = True
        self.effectiveDate = date if date else timezone.now()
        self.save()

    def mark_standing_actioned(self, user, date=None):
        """
        Marks a standing as actioned (user has made the change in game) with the current or supplied TZ aware datetime
        :param user: Actioned By django User
        :param date: TZ aware datetime object of when the action was taken
        :return:
        """
        logger.debug("Marking standing for {0} as actioned".format(self.contactID))
        self.actionBy = user
        self.actionDate = date if date else timezone.now()
        self.save()

    def check_standing_actioned_timeout(self):
        """
        Check that a standing hasn't been marked as actioned and is still not effective ~24hr later
        :return: User if the actioned has timed out, False if it has not, None if the check was unsuccessful
        """
        logger.debug("Checking standings request timeout")
        if self.effective:
            logger.debug("Standing is already marked as effective...")
            return None

        if self.actionBy is None:
            logger.debug("Standing was never actioned, cannot timeout")
            return None

        latest = ContactSet.objects.latest()
        if latest is None:
            logger.debug("Cannot check standing timeout, no standings available")
            return None

        # More than 24 hours after, reset
        if self.actionDate + datetime.timedelta(hours=self.standingTimeoutHours) < latest.date:
            logger.debug("Standing actioned timed out, resetting actioned for contactID {0}".format(self.contactID))
            actioner = self.actionBy
            self.actionBy = None
            self.actionDate = None
            self.save()
            return actioner
        return False

    def reset_to_initial(self):
        """
        Reset a standing back to its initial creation state (Not actioned and not effective)
        :return:
        """
        self.effective = False
        self.effectiveDate = None
        self.actionBy = None
        self.actionDate = None
        self.save()

    @classmethod
    def pending_request(cls, contact_id):
        """
        Checks if a request is pending for the given contact_id
        :param contact_id: int contactID to check the pending request for
        :return: bool True if a request is already pending, False otherwise
        """
        pending = cls.objects.filter(contactID=contact_id).filter(actionBy=None).filter(effective=False)
        return pending.exists()

    @classmethod
    def actioned_request(cls, contact_id):
        """
        Checks if an actioned request is pending API confirmation for the given contact_id
        :param contact_id: int contactID to check the pending request for
        :return: bool True if a request is pending API confirmation, False otherwise
        """
        pending = cls.objects.filter(contactID=contact_id).exclude(actionBy=None).filter(effective=False)
        return pending.exists()


class StandingsRequest(AbstractStandingsRequest):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    expectStandingGTEQ = 0.01

    objects = StandingsRequestManager()

    def delete(self, using=None, keep_parents=False):
        """
        Add a revocation before deleting if the standing has been actioned (pending) or is effective and
        doesnt already have a pending revocation request.
        """
        if self.actionBy is not None or self.effective:
            # Check if theres not already a revocation pending
            if not StandingsRevocation.pending_request(self.contactID):
                logger.debug("Adding revocation for deleted request with contactID {0} type {1}".format(
                    self.contactID,
                    self.contactType,
                ))
                StandingsRevocation.add_revocation(self.contactID, self.contactType)
            else:
                logger.debug("Revocation already pending for deleted request with contactID {0} type {1}".format(
                    self.contactID,
                    self.contactType,
                ))
        else:
            logger.debug("Standing never effective, no revocation required "
                         "for deleted request with contactID {0} type {1}".format(
                            self.contactID,
                            self.contactType,
                            ))

        super(AbstractStandingsRequest, self).delete(using, keep_parents)

    @classmethod
    def add_request(cls, user, contact_id, contact_type):
        """
        Add a new standings request
        :param user: User the request and contactID belongs to
        :param contact_id: contactID to request standings on
        :param contact_type: contactType from a AbstractStanding concrete class
        :return: the created StandingsRequest instance
        """
        logger.debug("Adding new standings request for user {0}, contact {1} type {2}".format(user,
                                                                                              contact_id,
                                                                                              contact_type))

        if cls.objects.filter(contactID=contact_id, contactType=contact_type).exists():
            logger.debug("Standings request already exists, returning first existing request")
            return cls.objects.filter(contactID=contact_id, contactType=contact_type)[0]

        instance = cls(user=user, contactID=contact_id, contactType=contact_type)
        instance.save()
        return instance

    @classmethod
    def remove_requests(cls, contact_id):
        """
        Remove the requests for the given contact_id. If any of these requests have been actioned or are effective
        a Revocation request will automatically be generated
        :param contact_id: str contactID to remove.
        :return:
        """
        logger.debug("Removing requests for contactID {0}".format(contact_id))
        requests = cls.objects.filter(contactID=contact_id)
        logger.debug("{0} requests to be removed".format(len(requests)))
        requests.delete()


class StandingsRevocation(AbstractStandingsRequest):
    expectStandingLTEQ = 0.0

    @classmethod
    def add_revocation(cls, contact_id, contact_type):
        """
        Add a new standings revocation
        :param contact_id: contactID to request standings on
        :param contact_type: contactType from AbstractStanding concrete implementation
        :return: the created StandingsRevocation instance
        """
        logger.debug("Adding new standings revocation for contact {0} type {1}".format(contact_id, contact_type))
        pending = cls.objects.filter(contactID=contact_id).filter(effective=False)
        if pending.exists():
            logger.debug("Cannot add revocation for contact {0}, pending revocation exists".format(contact_id,
                                                                                                   contact_type))
            return None
        instance = cls(contactID=contact_id, contactType=contact_type)
        instance.save()
        return instance

    @classmethod
    def undo_revocation(cls, contact_id, owner):
        logger.debug("Undoing revocation for contactID {0}".format(contact_id))
        revocs = cls.objects.filter(contactID=contact_id)

        if not revocs.exists():
            return False

        request = StandingsRequest.add_request(owner, contact_id, revocs[0].contactType)
        revocs.delete()
        return request


class CharacterAssociation(models.Model):
    """
    Alt Character Associations with declared mains
    Main characters are associated with themselves
    """
    character_id = models.IntegerField(primary_key=True)
    corporation_id = models.IntegerField(null=True)
    alliance_id = models.IntegerField(null=True)
    main_character_id = models.IntegerField(null=True)
    updated = models.DateTimeField(auto_now_add=True)

    API_CACHE_TIMER = datetime.timedelta(days=3)

    @property
    def character_name(self):
        """
        Character name property for character_id
        :return: str character name
        """
        if self._character_name is not None:
            return self._character_name
        else:
            name = EveNameCache.get_name(self.character_id)
            self._character_name = name
            return name

    @property
    def main_character_name(self):
        """
        Character name property for character_id
        :return: str character name
        """
        if self._main_character_name is not None:
            return self._main_character_name
        else:
            name = EveNameCache.get_name(self.main_character_id)
            self._main_character_name = name
            return name

    @classmethod
    def get_api_expired_items(cls, items_in=None):
        """
        Get all API timer expired items
        :param items_in: list optional parameter to limit the results to character_ids in the list
        :return: QuerySet of CharacterAssociation items that have expired their API timer
        """
        expired = cls.objects.filter(updated__lt=timezone.now()-cls.API_CACHE_TIMER)
        if items_in is not None:
            expired = expired.filter(character_id__in=items_in)
        return expired


class EveNameCache(models.Model):
    """
    Cache for all entity names (Characters, Corps, Alliances)

    Keeping our own cache because allianceauth deletes characters with no API key
    """
    entityID = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=254)
    updated = models.DateTimeField(auto_now_add=True)

    cache_time = datetime.timedelta(days=30)

    @classmethod
    def get_names(cls, entity_ids):
        """
        Get the names of the given entity ids from catch or other locations
        :param eve_entity_ids: array of int entity ids whos names to fetch
        :return: dict with entity_id as key and name as value
        """
        # make sure there is no duplicates
        entity_ids = set(entity_ids)
        name_info = {}
        entities_need_update = []
        entity_ids_not_found = []
        for entity_id in entity_ids:
            if cls.objects.filter(entityID=entity_id).exists():
                # Cached
                entity = cls.objects.get(entityID=entity_id)
                if entity.cache_timeout():
                    entities_need_update.append(entity)
                else:
                    name_info[entity.entityID] = entity.name
            else:
                entity_ids_not_found.append(entity_id)

        entities_need_names = [e.entityID for e in entities_need_update] + entity_ids_not_found

        names_info_api = EveEntityManager.get_names(entities_need_names)

        # update existing entities
        for entity in entities_need_update:
            if entity.entityID in names_info_api:
                name = names_info_api[entity.entityID]
                entity._set_name(name)
            else:
                entity._update_entity()

            name_info[entity.entityID] = entity.name

        # create new entities
        for entity_id in entity_ids_not_found:
            if entity_id in names_info_api:
                entity = cls()
                entity.entityID = entity_id
                entity._set_name(names_info_api[entity_id])
                name_info[entity_id] = entity.name

        return name_info

    @classmethod
    def get_name(cls, entity_id):
        """
        Get the name for the given entity
        :param entity_id: EVE id of the entity
        :return: str name if it exists or None
        """
        if cls.objects.filter(entityID=entity_id).exists():
            # Cached
            entity = cls.objects.get(entityID=entity_id)
            if entity.cache_timeout():
                entity._update_entity()
        else:
            # Fetch name/not cached
            entity = cls()
            entity.entityID = entity_id
            entity._update_entity()
            # If the name is updated it will be saved, otherwise this object will be discarded
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
        contacts = ContactSet.objects.latest()
        contact = None
        if contacts.pilotstanding_set.filter(contactID=self.entityID).exists():
            contact = contacts.pilotstanding_set.get(contactID=self.entityID)
        elif contacts.corpstanding_set.filter(contactID=self.entityID).exists():
            contact = contacts.corpstanding_set.get(contactID=self.entityID)
        elif contacts.alliancestanding_set.filter(contactID=self.entityID).exists():
            contact = contacts.alliancestanding_set.get(contactID=self.entityID)

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
        auth_name = EveEntityManager.get_name_from_auth(self.entityID)
        if auth_name is not None:
            self._set_name(auth_name)
            return True
        else:
            return False

    def _update_from_api(self):
        """
        Attempt to update the entity from the EVE API. Should be a last resort (because slow)
        :return: bool True if successful, False otherwise
        """
        api_name = EveEntityManager.get_name_from_api(self.entityID)
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
        return timezone.now() > self.updated + self.cache_time

    @classmethod
    def update_name(cls, entity_id, name):
        cls.objects.update_or_create(entityID=entity_id,
                                     defaults={
                                         'name': name,
                                         'updated': timezone.now(),
                                     })
