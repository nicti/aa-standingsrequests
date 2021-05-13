from typing import Tuple

from bravado.exception import HTTPError

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Case, Q, Value, When
from django.utils.translation import gettext_lazy as _
from esi.models import Token
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.helpers import chunks
from app_utils.logging import LoggerAddTag

from . import __title__
from .app_settings import SR_NOTIFICATIONS_ENABLED
from .core import BaseConfig, ContactType
from .providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class ContactSetManager(models.Manager):
    def create_new_from_api(self) -> object:
        """fetches contacts with standings for configured alliance
        or corporation from ESI and stores them as newly created ContactSet

        Returns new ContactSet on success, else None
        """
        token = (
            Token.objects.filter(character_id=BaseConfig.standings_character_id)
            .require_scopes(self.model.required_esi_scope())
            .require_valid()
            .first()
        )
        if not token:
            logger.warning("Token for standing char could not be found")
            return None
        try:
            contacts = _ContactsWrapper(token, BaseConfig.standings_character_id)
        except HTTPError as ex:
            logger.exception(
                "APIError occurred while trying to query api server: %s", ex
            )
            return None

        with transaction.atomic():
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
        from .models import Contact

        for contact in contacts:
            eve_entity, _ = EveEntity.objects.get_or_create_esi(id=contact.id)
            obj = Contact.objects.create(
                contact_set=contact_set,
                eve_entity=eve_entity,
                standing=contact.standing,
            )
            flat_labels = [label.id for label in contact.labels]
            labels = contact_set.labels.filter(label_id__in=flat_labels)
            obj.labels.add(*labels)


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
        self.alliance = []
        self.allianceLabels = []

        if BaseConfig.operation_mode == "alliance":
            alliance_id = EveCharacter.objects.get_character_by_id(
                character_id
            ).alliance_id
            labels = esi.client.Contacts.get_alliances_alliance_id_contacts_labels(
                alliance_id=alliance_id, token=token.valid_access_token()
            ).results()
            self.allianceLabels = [self.Label(label) for label in labels]
            contacts = esi.client.Contacts.get_alliances_alliance_id_contacts(
                alliance_id=alliance_id, token=token.valid_access_token()
            ).results()

        elif BaseConfig.operation_mode == "corporation":
            corporation_id = EveCharacter.objects.get_character_by_id(
                character_id
            ).corporation_id
            labels = (
                esi.client.Contacts.get_corporations_corporation_id_contacts_labels(
                    corporation_id=corporation_id, token=token.valid_access_token()
                ).results()
            )
            self.allianceLabels = [self.Label(label) for label in labels]
            contacts = esi.client.Contacts.get_corporations_corporation_id_contacts(
                corporation_id=corporation_id, token=token.valid_access_token()
            ).results()
        else:
            raise NotImplementedError()

        logger.debug("Got %d contacts in total", len(contacts))
        entity_ids = []
        for contact in contacts:
            entity_ids.append(contact["contact_id"])

        resolver = EveEntity.objects.bulk_resolve_names(entity_ids)
        for contact in contacts:
            self.alliance.append(
                self.Contact(contact, self.allianceLabels, resolver._names_map)
            )


class ContactQuerySet(models.QuerySet):
    def filter_characters(self):
        return self.filter(eve_entity__category=EveEntity.CATEGORY_CHARACTER)

    def filter_corporations(self):
        return self.filter(eve_entity__category=EveEntity.CATEGORY_CORPORATION)

    def filter_alliances(self):
        return self.filter(eve_entity__category=EveEntity.CATEGORY_ALLIANCE)


class AbstractStandingsRequestQuerySet(models.QuerySet):
    def annotate_is_pending(self) -> models.QuerySet:
        return self.annotate(
            is_pending_annotated=Case(
                When(Q(action_date__isnull=True) & Q(is_effective=False), then=True),
                default=Value(False),
                output_field=models.BooleanField(),
            )
        )

    def annotate_is_actioned(self) -> models.QuerySet:
        return self.annotate(
            is_actioned_annotated=Case(
                When(Q(action_date__isnull=False) & Q(is_effective=False), then=True),
                default=Value(False),
                output_field=models.BooleanField(),
            )
        )


class AbstractStandingsRequestManager(models.Manager):
    def filter_characters(self) -> models.QuerySet:
        return self.filter(contact_type_id__in=ContactType.character_ids)

    def filter_corporations(self) -> models.QuerySet:
        return self.filter(contact_type_id__in=ContactType.corporation_ids)

    def get_queryset(self) -> models.QuerySet:
        return AbstractStandingsRequestQuerySet(self.model, using=self._db)

    def process_requests(self) -> None:
        """Process all the Standing requests/revocation objects"""
        from .models import (
            AbstractStandingsRequest,
            StandingRequest,
            StandingRevocation,
        )

        if self.model is AbstractStandingsRequest:
            raise TypeError("Can not be called from abstract objects")

        organization = BaseConfig.standings_source_entity()
        organization_name = organization.name if organization else ""
        for standing_request in self.all():
            contact, dummy = EveEntity.objects.get_or_create_esi(
                id=standing_request.contact_id
            )
            is_currently_effective = standing_request.is_effective
            is_satisfied_standing = standing_request.evaluate_effective_standing()
            if is_satisfied_standing and not is_currently_effective:
                if SR_NOTIFICATIONS_ENABLED:
                    # send notification to user about standing change if enabled
                    if type(standing_request) is StandingRequest:
                        notify(
                            user=standing_request.user,
                            title=_(
                                "%s: Standing with %s now in effect"
                                % (__title__, contact.name)
                            ),
                            message=_(
                                "'%(organization_name)s' now has blue standing with "
                                "your alt %(contact_category)s '%(contact_name)s'. "
                                "Please also update the standing of "
                                "your %(contact_category)s accordingly."
                            )
                            % {
                                "organization_name": organization_name,
                                "contact_category": contact.category,
                                "contact_name": contact.name,
                            },
                        )
                    elif type(standing_request) is StandingRevocation:
                        if standing_request.user:
                            notify(
                                user=standing_request.user,
                                title="%s: Standing with %s revoked"
                                % (__title__, contact.name),
                                message=_(
                                    "'%(organization_name)s' no longer has "
                                    "standing with your "
                                    "%(contact_category)s '%(contact_name)s'. "
                                    "Please also update the standing of "
                                    "your %(contact_category)s accordingly."
                                )
                                % {
                                    "organization_name": organization_name,
                                    "contact_category": contact.category,
                                    "contact_name": contact.name,
                                },
                            )

                # if this was a revocation the standing requests need to be remove
                # to indicate that this character no longer has standing
                if type(standing_request) == StandingRevocation:
                    StandingRequest.objects.filter(
                        contact_id=standing_request.contact_id
                    ).delete()
                    StandingRevocation.objects.filter(
                        contact_id=standing_request.contact_id
                    ).delete()

            elif is_satisfied_standing:
                # Just catching all other contact types (corps/alliances)
                # that are set effective
                pass

            elif not is_satisfied_standing and is_currently_effective:
                # Effective standing no longer effective
                logger.info(
                    "Standing for %d is marked as effective but is not "
                    "satisfied in game. Deleting." % standing_request.contact_id
                )
                standing_request.delete(
                    reason=StandingRevocation.Reason.REVOKED_IN_GAME
                )

            else:
                # Check the standing hasn't been set actioned
                # and not updated in game
                actioned_timeout = standing_request.check_actioned_timeout()
                if actioned_timeout is not None and actioned_timeout:
                    logger.info(
                        "Standing request for contact ID %d has timedout "
                        "and will be reset" % standing_request.contact_id
                    )
                    if SR_NOTIFICATIONS_ENABLED:
                        title = _("Standing Request for %s reset" % contact.name)
                        message = _(
                            "The standing request for %(contact_category)s "
                            "'%(contact_name)s' from %(user_name)s "
                            "has been reset as it did not appear in "
                            "game before the timeout period expired."
                            % {
                                "contact_category": contact.category,
                                "contact_name": contact.name,
                                "user_name": standing_request.user.username,
                            },
                        )
                        # Notify standing manager
                        notify(user=actioned_timeout, title=title, message=message)
                        # Notify the user
                        notify(user=standing_request.user, title=title, message=message)

    def has_pending_request(self, contact_id: int) -> bool:
        """Checks if a request is pending for the given contact_id

        contact_id: int contact_id to check the pending request for

        returns True if a request is already pending, False otherwise
        """
        return self.pending_requests().filter(contact_id=contact_id).exists()

    def has_actioned_request(self, contact_id: int) -> bool:
        """Checks if an actioned request is pending API confirmation for
        the given contact_id

        contact_id: int contact_id to check the pending request for

        returns True if a request is pending API confirmation, False otherwise
        """
        return self.filter(
            contact_id=contact_id, action_date__isnull=False, is_effective=False
        ).exists()

    def has_effective_request(self, contact_id: int) -> bool:
        """return True if an effective request exists for given contact_id,
        else False
        """
        return self.filter(contact_id=contact_id, is_effective=True).exists()

    def pending_requests(self) -> models.QuerySet:
        """returns all pending requests for this class"""
        return self.filter(action_date__isnull=True, is_effective=False)


class StandingRequestManager(AbstractStandingsRequestManager):
    def delete_for_user(self, user):
        self.filter(user=user).delete()

    def validate_requests(self) -> int:
        """Validate all StandingsRequests and check
        that the user requesting them has permission and has API keys
        associated with the character/corp.

        StandingRevocation are created for invalid standing requests

        returns the number of invalid requests
        """
        from .models import StandingRevocation

        logger.debug("Validating standings requests")
        invalid_count = 0
        for standing_request in self.all():
            logger.debug(
                "Checking request for contact_id %d", standing_request.contact_id
            )
            reason = StandingRevocation.Reason.NONE
            if not standing_request.user.has_perm(self.model.REQUEST_PERMISSION_NAME):
                logger.debug("Request is invalid, user does not have permission")
                reason = StandingRevocation.Reason.LOST_PERMISSION
                is_valid = False

            elif ContactType.is_corporation(
                standing_request.contact_type_id
            ) and not self.model.can_request_corporation_standing(
                standing_request.contact_id, standing_request.user
            ):
                logger.debug("Request is invalid, not all corp API keys recorded.")
                reason = StandingRevocation.Reason.MISSING_CORP_TOKEN
                is_valid = False

            else:
                is_valid = True

            if not is_valid:
                logger.info(
                    "Standing request for contact_id %d no longer valid. "
                    "Creating revocation",
                    standing_request.contact_id,
                )
                StandingRevocation.objects.add_revocation(
                    contact_id=standing_request.contact_id,
                    contact_type=self.model.contact_id_2_type(
                        standing_request.contact_type_id
                    ),
                    user=standing_request.user,
                    reason=reason,
                )
                invalid_count += 1

        return invalid_count

    def add_request(self, user: User, contact_id: int, contact_type: str) -> object:
        """Add a new standings request

        Params:
        - user: User the request and contact_id belongs to
        - contact_id: contact_id to request standings on
        - contact_type: type of this contact

        Restuns the created StandingRequest instance
        """
        logger.debug(
            "Adding new standings request for user %s, contact %d type %s",
            user,
            contact_id,
            contact_type,
        )
        contact_type_id = self.model.contact_type_2_id(contact_type)
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

    def remove_requests(self, contact_id: int, reason=None):
        """
        Remove the requests for the given contact_id. If any of these requests
        have been actioned or are effective
        a Revocation request will automatically be generated

        Params:
        - contact_id: contact_id to remove
        - user_responsible: User responsible for removing.
        When provided will sent notification to requestor.
        """
        standing_requests = self.filter(contact_id=contact_id)
        if standing_requests:
            logger.debug(
                "%s: Removing %d requests", contact_id, standing_requests.count()
            )
            for req in standing_requests:
                req.delete(reason=reason)


class StandingRevocationManager(AbstractStandingsRequestManager):
    def add_revocation(
        self, contact_id: int, contact_type: str, user: User = None, reason: str = None
    ) -> object:
        """Add a new standings revocation

        Params:
        - contact_id: contact_id to request standings on
        - contact_type_id: contact_type_id from AbstractContact concrete implementation
        - user: user making the request

        Returns the created StandingRevocation instance
        """
        logger.debug(
            "Adding new standings revocation for contact %d type %s",
            contact_id,
            contact_type,
        )
        contact_type_id = self.model.contact_type_2_id(contact_type)
        pending = self.filter(contact_id=contact_id).filter(is_effective=False)
        if pending.exists():
            logger.debug(
                "Cannot add revocation for contact %d %s, pending revocation exists",
                contact_id,
                contact_type_id,
            )
            return None
        if not reason:
            reason = self.model.Reason.NONE
        instance = self.create(
            contact_id=contact_id,
            contact_type_id=contact_type_id,
            user=user,
            reason=reason,
        )
        return instance


class CharacterAffiliationManager(models.Manager):
    def update_evecharacter_relations(self) -> None:
        """Update links to eve character in auth if any"""

        eve_character_id_map = {
            obj["character_id"]: obj["id"]
            for obj in EveCharacter.objects.values("id", "character_id")
        }
        with transaction.atomic():
            affiliations = [
                obj for obj in self.filter(character_id__in=eve_character_id_map.keys())
            ]
            for affiliation in affiliations:
                affiliation.eve_character_id = eve_character_id_map[
                    affiliation.character_id
                ]
            self.bulk_update(
                objs=affiliations, fields=["eve_character_id"], batch_size=500
            )

    def update_from_esi(self) -> None:
        """Update all character affiliations we have contacts or requests for."""
        character_ids = self._gather_character_ids()
        if character_ids:
            affiliations = self._fetch_characters_affiliation_from_esi(character_ids)
            if affiliations:
                self._store_affiliations(affiliations)

    def _gather_character_ids(self) -> list:
        from .models import ContactSet, StandingRequest, StandingRevocation

        try:
            contact_set = ContactSet.objects.latest()
        except ContactSet.DoesNotExist:
            logger.warning("Could not find a contact set")
            return []

        character_ids_contacts = set(
            contact_set.contacts.filter_characters()
            .values_list("eve_entity_id", flat=True)
            .distinct()
        )
        character_ids_requests = set(
            StandingRequest.objects.filter_characters()
            .values_list("contact_id", flat=True)
            .distinct()
        )
        character_ids_revocations = set(
            StandingRevocation.objects.filter_characters()
            .values_list("contact_id", flat=True)
            .distinct()
        )
        return list(
            character_ids_contacts | character_ids_requests | character_ids_revocations
        )

    def _fetch_characters_affiliation_from_esi(self, character_ids) -> list:
        chunk_size = 1000
        affiliations = []
        for character_ids_chunk in chunks(character_ids, chunk_size):
            try:
                response = esi.client.Character.post_characters_affiliation(
                    characters=character_ids_chunk
                ).results()
            except HTTPError:
                logger.exception("Could not fetch character affiliations from ESI")
                return []
            else:
                affiliations += response
        return affiliations

    def _store_affiliations(self, affiliations) -> None:
        affiliation_objects = list()
        for affiliation in affiliations:
            character, _ = EveEntity.objects.get_or_create(
                id=affiliation["character_id"]
            )
            corporation, _ = EveEntity.objects.get_or_create(
                id=affiliation["corporation_id"]
            )
            if affiliation.get("alliance_id"):
                alliance, _ = EveEntity.objects.get_or_create(
                    id=affiliation["alliance_id"]
                )
            else:
                alliance = None
            if affiliation.get("faction_id"):
                faction, _ = EveEntity.objects.get_or_create(
                    id=affiliation["faction_id"]
                )
            else:
                faction = None
            affiliation_objects.append(
                self.model(
                    character=character,
                    corporation=corporation,
                    alliance=alliance,
                    faction=faction,
                )
            )
        with transaction.atomic():
            self.all().delete()
            self.bulk_create(affiliation_objects, batch_size=500)

        EveEntity.objects.bulk_create_esi(
            filter(
                lambda x: x is not None,
                [
                    affiliation["character_id"],
                    affiliation["corporation_id"],
                    affiliation["alliance_id"],
                ],
            )
        )


class CorporationDetailsManager(models.Manager):
    def corporation_ids_from_contacts(self) -> set:
        from .models import Contact

        contact_corporation_ids = set(
            Contact.objects.filter_corporations().values_list(
                "eve_entity_id", flat=True
            )
        )
        character_affiliation_corporation_ids = set(
            Contact.objects.filter_characters().values_list(
                "eve_entity__character_affiliation__corporation_id", flat=True
            )
        )
        return set(contact_corporation_ids | character_affiliation_corporation_ids)

    def update_or_create_from_esi(self, id: int) -> Tuple[models.Model, bool]:
        """Updates or create an obj from ESI"""
        logger.info("%s: Fetching corporation from ESI", id)
        data = esi.client.Corporation.get_corporations_corporation_id(
            corporation_id=id
        ).results()
        corporation = EveEntity.objects.get_or_create(id=id)[0]
        alliance = (
            EveEntity.objects.get_or_create(id=data["alliance_id"])[0]
            if data.get("alliance_id")
            else None
        )
        ceo = EveEntity.objects.get_or_create(id=data["ceo_id"])[0]
        faction = (
            EveEntity.objects.get_or_create(id=data["faction_id"])[0]
            if data.get("faction_id")
            else None
        )
        EveEntity.objects.bulk_create_esi(
            filter(
                lambda x: x is not None,
                [id, data.get("alliance_id"), data["ceo_id"], data.get("faction_id")],
            )
        )
        return self.update_or_create(
            corporation=corporation,
            defaults={
                "alliance": alliance,
                "ceo": ceo,
                "faction": faction,
                "member_count": data["member_count"],
                "ticker": data["ticker"],
            },
        )
