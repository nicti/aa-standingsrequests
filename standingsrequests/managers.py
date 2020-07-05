from datetime import timedelta

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger

from esi.models import Token

from . import __title__
from .app_settings import (
    STANDINGS_API_CHARID,
    SR_OPERATION_MODE,
    SR_NOTIFICATIONS_ENABLED,
    SR_PREVIOUSLY_EFFECTIVE_GRACE_HOURS,
)
from .helpers.esi_fetch import esi_fetch
from .helpers.eveentity import EveEntityHelper
from .utils import chunks, LoggerAddTag


logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class ContactSetManager(models.Manager):
    @transaction.atomic
    def create_new_from_api(self) -> object:
        """fetches contacts with standings for configured alliance 
        or corporation from ESI and stores them as newly created ContactSet

        Returns new ContactSet on success, else None
        """
        token = (
            Token.objects.filter(character_id=STANDINGS_API_CHARID)
            .require_scopes(self.model.required_esi_scope())
            .require_valid()
            .first()
        )
        if not token:
            logger.warning("Token for standing char could not be found")
            return None
        try:
            contacts = _ContactsWrapper(token, STANDINGS_API_CHARID)
        except Exception as ex:
            logger.exception(
                "APIError occurred while trying to query api server: %s", ex
            )
            return None

        contacts_set = self.create()
        self._add_labels_from_api(contacts_set, contacts.allianceLabels)
        self._add_contacts_from_api(contacts_set, contacts.alliance)
        return contacts_set

    def _add_labels_from_api(self, contact_set, labels):
        """Add the list of labels to the given ContactSet
        
        contact_set: ContactSet instance
        labels: Label dictionary        
        """
        from .models import ContactLabel

        contact_labels = [
            ContactLabel(label_id=label.id, name=label.name, contact_set=contact_set)
            for label in labels
        ]
        ContactLabel.objects.bulk_create(contact_labels, ignore_conflicts=True)

    def _add_contacts_from_api(self, contact_set, contacts):
        """Add all contacts to the given ContactSet
        Labels _MUST_ be added before adding contacts
        
        :param contact_set: Django ContactSet to add contacts to
        :param contacts: List of _ContactsWrapper.Contact to add        
        """
        for contact in contacts:
            flat_labels = [label.id for label in contact.labels]
            labels = contact_set.contactlabel_set.filter(label_id__in=flat_labels)
            contact_set.create_standing(
                contact_type_id=contact.type_id,
                contact_id=contact.id,
                name=contact.name,
                standing=contact.standing,
                labels=labels,
            )


class _ContactsWrapper:
    """Converts raw contacts and contact labels data from ESI into an object"""

    class Label:
        def __init__(self, json):
            self.id = json["label_id"]
            self.name = json["label_name"]

        def __str__(self):
            return u"{}".format(self.name)

        def __repr__(self):
            return str(self)

    class Contact:
        @staticmethod
        def get_type_id_from_name(type_name):
            """
            Maps new ESI name to old type id.
            Character type is allways mapped to 1373
            And faction type to 500000
            Determines the contact type:
            2 = Corporation
            1373-1386 = Character
            16159 = Alliance
            500001 - 500024 = Faction
            """
            if type_name == "character":
                return 1373
            if type_name == "alliance":
                return 16159
            if type_name == "faction":
                return 500001
            if type_name == "corporation":
                return 2

            raise NotImplementedError("This contact type is not mapped")

        def __init__(self, json, labels, names_info):
            self.id = json["contact_id"]
            self.name = names_info[self.id] if self.id in names_info else ""
            self.standing = json["standing"]
            self.in_watchlist = json["in_watchlist"] if "in_watchlist" in json else None
            self.label_ids = (
                json["label_ids"]
                if "label_ids" in json and json["label_ids"] is not None
                else []
            )
            self.type_id = self.__class__.get_type_id_from_name(json["contact_type"])
            # list of labels
            self.labels = [label for label in labels if label.id in self.label_ids]

        def __str__(self):
            return u"{}".format(self.name)

        def __repr__(self):
            return str(self)

    def __init__(self, token, character_id):
        from .models import EveNameCache

        self.alliance = []
        self.allianceLabels = []

        if SR_OPERATION_MODE == "alliance":
            alliance_id = EveCharacter.objects.get_character_by_id(
                character_id
            ).alliance_id
            labels = esi_fetch(
                "Contacts.get_alliances_alliance_id_contacts_labels",
                args={"alliance_id": alliance_id},
                token=token,
            )
            for label in labels:
                self.allianceLabels.append(self.Label(label))

            contacts = esi_fetch(
                "Contacts.get_alliances_alliance_id_contacts",
                args={"alliance_id": alliance_id},
                token=token,
                has_pages=True,
            )
        elif SR_OPERATION_MODE == "corporation":
            corporation_id = EveCharacter.objects.get_character_by_id(
                character_id
            ).corporation_id
            labels = esi_fetch(
                "Contacts.get_corporations_corporation_id_contacts_labels",
                args={"corporation_id": corporation_id},
                token=token,
            )
            for label in labels:
                self.allianceLabels.append(self.Label(label))

            contacts = esi_fetch(
                "Contacts.get_corporations_corporation_id_contacts",
                args={"corporation_id": corporation_id},
                token=token,
                has_pages=True,
            )
        else:
            raise NotImplementedError()

        logger.debug("Got %d contacts in total", len(contacts))
        entity_ids = []
        for contact in contacts:
            entity_ids.append(contact["contact_id"])

        name_info = EveNameCache.objects.get_names(entity_ids)
        for contact in contacts:
            self.alliance.append(self.Contact(contact, self.allianceLabels, name_info))


class AbstractStandingsRequestManager(models.Manager):
    def process_requests(self) -> None:
        """Process all the Standing requests/revocation objects"""
        from .models import (
            ContactSet,
            EveNameCache,
            PilotStanding,
            StandingsRequest,
            StandingsRevocation,
            AbstractStandingsRequest,
        )

        if self.model == AbstractStandingsRequest:
            raise TypeError("Can not be called from abstract objects")

        organization = ContactSet.standings_source_entity()
        organization_name = organization.name if organization else ""
        for standing_request in self.all():
            character_name = EveNameCache.objects.get_name(standing_request.contact_id)
            was_already_effective = standing_request.is_effective
            is_satisfied_standing = standing_request.process_standing()
            if (
                is_satisfied_standing
                and standing_request.contact_type_id in PilotStanding.contact_types
            ):
                if SR_NOTIFICATIONS_ENABLED and not was_already_effective:
                    if type(standing_request) == StandingsRequest:
                        # Request, send a notification
                        notify(
                            user=standing_request.user,
                            title=_(
                                "%s: Standing for %s now in effect"
                                % (__title__, character_name)
                            ),
                            message=_(
                                "'%s' now has blue standing with your "
                                "character '%s' Please also update "
                                "the standing of your character accordingly."
                            )
                            % (organization_name, character_name),
                        )
                    elif type(standing_request) == StandingsRevocation:
                        # Revocation. Try and send a standing_request
                        # (user or character may be deleted)
                        try:
                            character = EveCharacter.objects.get(
                                character_id=standing_request.contact_id
                            )
                        except EveCharacter.DoesNotExist:
                            pass
                        else:
                            if hasattr(character, "userprofile"):
                                user = character.userprofile.user
                                notify(
                                    user=user,
                                    title="%s: Standing for %s revoked"
                                    % (__title__, character_name),
                                    message=_(
                                        "'%s' no longer has blue standing with your "
                                        "character '%s' Please also update "
                                        "the standing of your character accordingly."
                                    )
                                    % (organization_name, character_name),
                                )

            elif is_satisfied_standing:
                # Just catching all other contact types (corps/alliances)
                # that are set effective
                pass

            elif (
                not is_satisfied_standing
                and standing_request.is_effective
                and (
                    standing_request.effective_date
                    < now() - timedelta(SR_PREVIOUSLY_EFFECTIVE_GRACE_HOURS)
                )
            ):
                # Standing is not effective, but has previously
                # been marked as effective.
                # Unset effective
                logger.info(
                    "Standing for %d is marked as effective but is not "
                    "satisfied in game. Resetting to initial state"
                    % standing_request.contact_id
                )
                standing_request.reset_to_initial()

            else:
                # Check the standing hasn't been set actioned
                # and not updated in game
                actioned_timeout = standing_request.check_standing_actioned_timeout()
                if actioned_timeout is not None and actioned_timeout:
                    logger.info(
                        "Standing request for contact ID %d has timedout "
                        "and will be reset" % standing_request.contact_id
                    )
                    if SR_NOTIFICATIONS_ENABLED:
                        title = _("Standing request reset for %s" % character_name)
                        message = _(
                            "The standings request for character '%s' from user "
                            "'%s' has been reset as it did not appear in "
                            "game before the timeout period expired."
                            % (character_name, standing_request.user)
                        )
                        # Notify standing manager
                        notify(user=actioned_timeout, title=title, message=message)
                        # Notify the user
                        notify(user=standing_request.user, title=title, message=message)

    def pending_request(self, contact_id) -> bool:
        """Checks if a request is pending for the given contact_id
        
        contact_id: int contact_id to check the pending request for
        
        returns True if a request is already pending, False otherwise
        """
        pending = (
            self.filter(contact_id=contact_id)
            .filter(action_by=None)
            .filter(is_effective=False)
        )
        return pending.exists()

    def actioned_request(self, contact_id) -> bool:
        """Checks if an actioned request is pending API confirmation for 
        the given contact_id
        
        contact_id: int contact_id to check the pending request for
        
        returns True if a request is pending API confirmation, False otherwise
        """
        pending = (
            self.filter(contact_id=contact_id)
            .exclude(action_by=None)
            .filter(is_effective=False)
        )
        return pending.exists()


class StandingsRequestQuerySet(models.query.QuerySet):
    def delete(self):
        for obj in self:
            obj.delete()


class StandingsRequestManager(AbstractStandingsRequestManager):
    def get_queryset(self):
        return StandingsRequestQuerySet(self.model, using=self._db)

    def delete_for_user(self, user):
        to_delete = self.filter(user=user)

        # We have to delete each one manually in order to trigger the logic
        for d in to_delete:
            d.delete()

    def validate_standings_requests(self) -> int:
        """Validate all StandingsRequests and check 
        that the user requesting them has permission and has API keys
        associated with the character/corp. 

        Invalid standings requests are deleted, which may or may not generate a
        StandingsRevocation depending on their state.
        
        returns the number of deleted requests
        """
        from .models import CorpStanding

        logger.debug("Validating standings requests")
        deleted_count = 0
        for standing_request in self.all():
            logger.debug(
                "Checking request for contact_id %d", standing_request.contact_id
            )
            if not standing_request.user.has_perm(
                "standingsrequests.request_standings"
            ):
                logger.debug("Request is invalid, user does not have permission")
                is_valid = False

            elif CorpStanding.is_corp(
                standing_request.contact_type_id
            ) and not self.model.all_corp_apis_recorded(
                standing_request.contact_id, standing_request.user
            ):
                logger.debug("Request is invalid, not all corp API keys recorded.")
                is_valid = False

            else:
                is_valid = True

            if not is_valid:
                logger.info(
                    "Deleting invalid standing request for contact_id %d",
                    standing_request.contact_id,
                )
                standing_request.delete()
                deleted_count += 1

        return deleted_count

    def add_request(self, user, contact_id, contact_type_id):
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

        if self.filter(contact_id=contact_id, contact_type_id=contact_type_id).exists():
            logger.debug(
                "Standings request already exists, " "returning first existing request"
            )
            return self.filter(contact_id=contact_id, contact_type_id=contact_type_id)[
                0
            ]

        instance = self.create(
            user=user, contact_id=contact_id, contact_type_id=contact_type_id
        )
        return instance

    def remove_requests(self, contact_id):
        """
        Remove the requests for the given contact_id. If any of these requests 
        have been actioned or are effective
        a Revocation request will automatically be generated
        :param contact_id: str contact_id to remove.
        :return:
        """
        logger.debug("Removing requests for contact_id %d", contact_id)
        requests = self.filter(contact_id=contact_id)
        logger.debug("%d requests to be removed", len(requests))
        requests.delete()


class StandingsRevocationManager(AbstractStandingsRequestManager):
    def add_revocation(self, contact_id, contact_type_id):
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
        pending = self.filter(contact_id=contact_id).filter(is_effective=False)
        if pending.exists():
            logger.debug(
                "Cannot add revocation for contact %d %s, " "pending revocation exists",
                contact_id,
                contact_type_id,
            )
            return None

        instance = self.create(contact_id=contact_id, contact_type_id=contact_type_id)
        return instance

    def undo_revocation(self, contact_id, owner):
        """
        Converts existing revocation into request if it exists
        :param contact_id: contact_id to request standings on
        :param owner: user owning the revocation
        :return: created StandingsRequest pendant 
            or False if revocation does not exist
        """
        from .models import StandingsRequest

        logger.debug("Undoing revocation for contact_id %d", contact_id)

        try:
            revocation = self.get(contact_id=contact_id)
        except self.model.DoesNotExist:
            return False
        else:
            request = StandingsRequest.objects.add_request(
                owner, contact_id, revocation.contact_type_id
            )
            revocation.delete()
            return request


class CharacterAssociationManager(models.Manager):
    def update_from_auth(self) -> None:
        """Update all character associations based on auth relationship data"""
        from .models import EveNameCache

        chars = EveCharacter.objects.all()
        for c in chars:
            logger.debug("Updating Association from Auth for %s", c.character_name)
            try:
                ownership = CharacterOwnership.objects.get(character=c)
            except CharacterOwnership.DoesNotExist:
                main = None
            else:
                main = (
                    ownership.user.profile.main_character.character_id
                    if ownership.user.profile.main_character
                    else None
                )

            assoc, _ = self.update_or_create(
                character_id=c.character_id,
                defaults={
                    "corporation_id": c.corporation_id,
                    "main_character_id": main,
                    "alliance_id": c.alliance_id,
                    "updated": now(),
                },
            )
            EveNameCache.objects.update_name(assoc.character_id, c.character_name)

    def update_from_api(self) -> None:
        """Update all character corp associations we have standings for that 
        aren't being updated locally
        Cache timeout should be longer than update_from_auth 
        update schedule to
        prevent unnecessarily updating characters we already have local data for.        
        """
        # gather character associations of pilots which meed to be updated
        from .models import ContactSet

        try:
            contact_set = ContactSet.objects.latest()
        except ContactSet.DoesNotExist:
            logger.warning("Could not find a contact set")
        else:
            all_pilots = contact_set.pilotstanding_set.values_list(
                "contact_id", flat=True
            )
            expired_character_associations = self.get_api_expired_items(
                all_pilots
            ).values_list("character_id", flat=True)
            expired_pilots = set(all_pilots).intersection(
                expired_character_associations
            )
            known_pilots = self.values_list("character_id", flat=True)
            unknown_pilots = [
                pilot for pilot in all_pilots if pilot not in known_pilots
            ]
            pilots_to_fetch = list(expired_pilots | set(unknown_pilots))

            # Fetch the data in acceptable sizes from the API
            chunk_size = 1000
            for pilots_chunk in chunks(pilots_to_fetch, chunk_size):
                try:
                    esi_response = esi_fetch(
                        "Character.post_characters_affiliation",
                        args={"characters": pilots_chunk},
                    )
                    for association in esi_response:
                        corporation_id = association["corporation_id"]
                        alliance_id = (
                            association["alliance_id"]
                            if "alliance_id" in association
                            else None
                        )
                        character_id = association["character_id"]
                        self.update_or_create(
                            character_id=character_id,
                            defaults={
                                "corporation_id": corporation_id,
                                "alliance_id": alliance_id,
                                "updated": now(),
                            },
                        )

                except Exception:
                    logger.exception(
                        "Could not fetch associations pilots_chunk from ESI"
                    )

    def get_api_expired_items(self, items_in=None) -> models.QuerySet:
        """Get all API timer expired items

        items_in: list optional parameter to limit the results 
        to character_ids in the list
        
        returns: QuerySet of CharacterAssociation items        
        """
        expired = self.filter(updated__lt=now() - self.model.API_CACHE_TIMER)
        if items_in is not None:
            expired = expired.filter(character_id__in=items_in)

        return expired


class EveNameCacheManager(models.Manager):
    def get_names(self, entity_ids: list) -> dict:
        """Get the names of the given entity ids from catch or other locations
        
        eve_entity_ids: array of int entity ids who's names to fetch
        
        returns dict with entity_id as key and name as value
        """
        # make sure there are no duplicates
        entity_ids = set(entity_ids)
        name_info = {}
        entities_need_update = []
        entity_ids_not_found = []
        for entity_id in entity_ids:
            if self.filter(entity_id=entity_id).exists():
                # Cached
                entity = self.get(entity_id=entity_id)
                if entity.cache_timeout():
                    entities_need_update.append(entity)
                else:
                    name_info[entity.entity_id] = entity.name
            else:
                entity_ids_not_found.append(entity_id)

        entities_need_names = [
            e.entity_id for e in entities_need_update
        ] + entity_ids_not_found

        names_info_api = EveEntityHelper.get_names(entities_need_names)

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
                entity = self.model()
                entity.entity_id = entity_id
                entity._set_name(names_info_api[entity_id])
                name_info[entity_id] = entity.name

        return name_info

    def get_name(self, entity_id: int) -> str:
        """
        Get the name for the given entity
        :param entity_id: EVE id of the entity
        :return: str name if it exists or None
        """
        if self.filter(entity_id=entity_id).exists():
            # Cached
            entity = self.get(entity_id=entity_id)
            if entity.cache_timeout():
                entity._update_entity()
        else:
            # Fetch name/not cached
            entity = self.model()
            entity.entity_id = entity_id
            entity._update_entity()
            # If the name is updated it will be saved,
            # otherwise this object will be discarded
            # when it goes out of scope
        return entity.name or None

    def update_name(self, entity_id, name):
        self.update_or_create(
            entity_id=entity_id, defaults={"name": name, "updated": now(),}
        )
