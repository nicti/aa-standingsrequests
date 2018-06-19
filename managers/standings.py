from __future__ import unicode_literals
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
import logging

from future.utils import python_2_unicode_compatible, iteritems

from ..models import ContactSet, ContactLabel, PilotStanding, CorpStanding, AllianceStanding
from ..models import AbstractStandingsRequest, StandingsRequest, StandingsRevocation
from ..models import CharacterAssociation, EveNameCache
from ..helpers.evecorporation import EveCorporation
from ..managers import SWAGGER_SPEC_PATH,\
    REQUIRED_TOKENS
from ..managers.eveentity import EveEntityManager
from esi.clients import esi_client_factory
from esi.models import Token
from allianceauth.eveonline.providers import Character, Alliance
from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.authentication.models import CharacterOwnership
from past.builtins import xrange

logger = logging.getLogger(__name__)


class StandingsManager:
    charID = settings.STANDINGS_API_CHARID

    def __init__(self):
        pass

    @classmethod
    def api_get_instance(cls):
        token = Token.objects.filter(character_id=cls.charID)\
                .require_scopes(REQUIRED_TOKENS).require_valid()[0]
        return esi_client_factory(token=token, spec_file=SWAGGER_SPEC_PATH)

    @classmethod
    @transaction.atomic
    def api_update_alliance_standings(cls):
        try:
            api = cls.api_get_instance()
            contacts = ContactsWrapper(api, cls.charID)
        except Exception:
            logger.exception("APIError occured while trying to query api server.")
            return

        contacts_set = ContactSet()
        contacts_set.save()
        # Add Labels
        cls.api_add_labels(contacts_set, contacts.allianceLabels)
        # Add Contacts
        cls.api_add_contacts(contacts_set, contacts.alliance)
        return contacts_set

    @classmethod
    def api_add_labels(cls, contact_set, labels):
        """
        Add the list of labels to the given ContactSet
        :param contact_set: ContactSet instance
        :param labels: Label dictionary
        :return:
        """
        for l in labels:
            contact = ContactLabel(
                labelID=l.id,
                name=l.name,
                set=contact_set
            )
            contact.save()

    @classmethod
    def api_add_contacts(cls, contact_set, contacts):
        """
        Add all contacts to the given ContactSet
        Labels _MUST_ be added before adding contacts
        :param contact_set: Django ContactSet to add contacts to
        :param contacts: List of ContactsWrapper.Contact to add
        :return:
        """
        for c in contacts:
            # Flatten labels so we can do a simple in comparison
            flat_labels = [l.id for l in c.labels]
            # Create a list of applicable django ContactLabel objects
            # Can be replaced in django 1.9 as .set() is available
            labels = [l for l in contact_set.contactlabel_set.all() if l.labelID in flat_labels]
            contact = StandingFactory.create_standing(
                contact_set=contact_set,
                contact_type=c.type_id,
                contact_id=c.id,
                name=c.name,
                standing=c.standing,
                labels=labels,
            )

    @classmethod
    def pilot_in_organisation(cls, character_id):
        """
        Check if the Pilot is in the auth instances organisation
        :param character_id: str EveCharacter character_id
        :return: bool True if the character is in the organisation, False otherwise
        """
        pilot = EveCharacter.objects.get_character_by_id(character_id)
        if pilot is None:
            return False
        if str(pilot.corporation_id) in settings.STR_CORP_IDS or str(pilot.alliance_id) in settings.STR_ALLIANCE_IDS:
            return True
        return False

    @classmethod
    def all_corp_apis_recorded(cls, corp_id, user):
        """
        Checks if a user has all of the required corps APIs recorded for standings to be permitted
        :param corp_id: corp to check for
        :param user: User to check for
        :return: True if they can request standings, False if they cannot
        """
        # TODO: Need to figure out how to check if esi keys exists.....
        keys_recorded = sum([1 for a in EveCharacter.objects.filter(user=user).filter(corporation_id=corp_id)
                             if StandingsManager.has_required_scopes_for_request(a)])
        corp = EveCorporation.get_corp_by_id(int(corp_id))
        logger.debug("Got {} keys recorded for {} total corp members".format(keys_recorded, corp.member_count or None))
        return corp is not None and keys_recorded >= corp.member_count

    @classmethod
    def process_pending_standings(cls, standings_type=None):
        """
        Process StandingsRequests and StandingsRevocations and mark them as effective if standings have been set
        :type standings_type: AbstractStandingsRequest concrete class to process exclusively
        :return: None
        """
        # Skip if a type is specified and this isn't the specified type
        if (standings_type is not None and type(StandingsRequest) is standings_type) or standings_type is None:
            logger.debug("Processing StandingsRequests")
            cls.process_requests(StandingsRequest.objects.all())
        else:
            logger.debug("Skipping StandingsRequests")

        if (standings_type is not None and type(StandingsRevocation) is standings_type) or standings_type is None:
            logger.debug("Processing StandingsRevocations")
            cls.process_requests(StandingsRevocation.objects.all())
        else:
            logger.debug("Skipping StandingsRevocations")

    @classmethod
    def process_requests(cls, reqs):
        """
        Process all the Standing requests/revocation objects
        :param reqs: AbstractStandingsRequest list
        :return: None
        """
        for r in reqs:

            sat = r.check_standing_satisfied()

            if sat and r.contactType in PilotStanding.contactTypes:
                pass
                """
                char = EveManager.get_character_by_id(r.contactID)
                if type(r) is StandingsRequest:
                    # Request, send a notification
                    notify(char.user, "Standings Request", message="Your standings request for {0} is now effective"
                                                                " in game".format(char.character_name))
                elif type(r) is StandingsRevocation:
                    # Revocation. Try and send a request (user or character may be deleted)
                    if char is not None:
                        notify(char.user, "Standings Revocation", message="Your standings for {0} have been revoked "
                                                                          "in game".format(char.character_name))
                """
            elif sat:
                pass  # Just catching all other contact types (corps/alliances) that are set effective
            elif not sat and r.effective:
                # Standing is not effective, but has previously been marked as effective.
                # Unset effective
                logger.info("Standing for {0} is marked as effective but is not satisifed in game. "
                            "Resetting to initial state".format(r.contactID))
                r.reset_to_initial()
            else:
                # Check the standing hasn't been set actioned and not updated in game
                act = r.check_standing_actioned_timeout()
                if act is not None and act:
                    # Notify the actor user
                    notify(act, "Standings Request Action", message="A standings request for contactID {0} you "
                                                                    "actioned has been reset as it did not appear in "
                                                                    "game before the timeout period expired."
                                                                    "".format(r.contactID))

    @classmethod
    def update_character_associations_auth(cls):
        """
        Update all character associations based on auth relationship data
        :return:
        """
        chars = EveCharacter.objects.all()
        for c in chars:
            logger.debug("Updating Association from Auth for %s", c.character_name)
            try:
                try:
                    ownership = CharacterOwnership.objects.get(character=c)
                    main = ownership.user.profile.main_character.character_id if ownership.user.profile.main_character else None
                except CharacterOwnership.DoesNotExist:
                    main = None

                assoc, created = CharacterAssociation.objects.update_or_create(character_id=c.character_id,
                                                                               defaults={'corporation_id': c.corporation_id,
                                                                                         'main_character_id': main,
                                                                                         'alliance_id': c.alliance_id,
                                                                                         'updated': timezone.now(),
                                                                                         })
                EveNameCache.update_name(assoc.character_id, c.character_name)
            except CharacterAssociation.DoesNotExist:
                pass

    @classmethod
    def update_character_associations_api(cls):
        """
        Update all character corp associations we have standings for that aren't being updated locally
        Cache timeout should be longer than update_character_associations_auth's update schedule to
        prevent unnecessarily updating characters we already have local data for.
        :return:
        """
        chunk_size = 1000  # Size of characterID API chunks
        try:
            # Sort out a set of character_ids we want to fetch
            standings = ContactSet.objects.latest()
            pilot_standing_list = standings.pilotstanding_set.values_list('contactID', flat=True)
            # Get the expired association pilots in this standings list
            cache_expired = CharacterAssociation.get_api_expired_items(pilot_standing_list)\
                .values_list('character_id', flat=True)
            pilots = set(pilot_standing_list).intersection(cache_expired)  # Make sure we're only fetching expired
            # And pilots we don't know about
            known_pilots = CharacterAssociation.objects.all().values_list('character_id', flat=True)
            unknown_pilots = [i for i in pilot_standing_list if i not in known_pilots]
            pilots |= set(unknown_pilots)  # Merge sets
        except ObjectDoesNotExist:
            logging.warn("No standings set available to update character associations with. Aborting")
            return
        pilots = list(pilots)  # Switch back to a list, don't attempt to add anything after this
        # Chunk the data into acceptable sizes for the API
        length = len(pilots)
        chunks = [pilots[x:x+chunk_size] for x in xrange(0, length, chunk_size)]

        logger.debug('Got %s chunks containing max %s each to process with a total of %s', len(chunks), chunk_size, length)

        api = cls.api_get_instance()
        for c in chunks:
            try:
                esi_response = api.Character.post_characters_affiliation(characters=c).result()
                for association in esi_response:
                    corp_id = association['corporation_id']
                    all_id = association['alliance_id'] if 'alliance_id' in association else None
                    character_id = association['character_id']
                    CharacterAssociation.objects.update_or_create(
                        character_id=character_id,
                        defaults={
                            'corporation_id': corp_id,
                            'alliance_id': all_id,
                            'updated': timezone.now(),
                        })

            except Exception:
                logging.exception("Could not fetch associations chunk")

    @classmethod
    def validate_standings_requests(cls):
        """
        Validate all StandingsRequests and check that the user requesting them has permission and has API keys
        associated with the character/corp. Invalid standings requests are deleted, which may or may not generate a
        StandingsRevocation depending on their state.
        :return: int The number of deleted requests
        """
        logger.debug("Validating standings requests")
        requests = StandingsRequest.objects.all()
        count = 0

        for req in requests:
            logger.debug("Checking request for contactID {0}".format(req.contactID))
            if req.user.has_perm('standings-requests.request_standings'):
                if CorpStanding.is_corp(req.contactType) and not cls.all_corp_apis_recorded(req.contactID, req.user):
                    logger.debug("Request is invalid, not all corp API keys recorded.")
                else:
                    # Permission is valid, no action
                    logger.debug("Request valid")
                    continue
            else:
                logger.debug("Request is invalid, user does not have permission")
            # Request is invalid, deleting
            logger.info("Deleting request for contactID {0}".format(req.contactID))
            count += 1
            req.delete()
        return count

    @staticmethod
    def has_required_scopes_for_request(char):
        state = None
        try:
            ownership = CharacterOwnership.objects.get(
                character__character_id=char.character_id)
            user = ownership.user
            state = user.profile.state.name
        except CharacterOwnership.DoesNotExist:
            pass

        scopes_string = ' '.join(
            StandingsManager.get_required_scopes_for_state(state))
        has_required_scopes = Token.objects.filter(
            character_id=char.character_id
            ).require_scopes(scopes_string).require_valid().exists()
        return has_required_scopes

    @staticmethod
    def get_required_scopes_for_state(state):
        if state is None:
            state = ''

        if hasattr(settings, 'SR_REQUIRED_SCOPES'):
            if state in settings.SR_REQUIRED_SCOPES:
                return settings.SR_REQUIRED_SCOPES[state]
            else:
                return []
        else:
            return []


class StandingFactory:
    def __init__(self):
        pass

    @classmethod
    def create_standing(cls, contact_set, contact_type, contact_id, name, standing, labels):
        standing_type = cls.get_class_for_contact_type(contact_type)

        standing = standing_type(
            set=contact_set,
            contactID=contact_id,
            name=name,
            standing=standing,
        )
        standing.save()
        for l in labels:
            standing.labels.add(l)
        standing.save()
        return standing

    @staticmethod
    def get_class_for_contact_type(contact_type):
        if contact_type in PilotStanding.contactTypes:
            return PilotStanding
        elif contact_type in CorpStanding.contactTypes:
            return CorpStanding
        elif contact_type in AllianceStanding.contactTypes:
            return AllianceStanding
        raise NotImplemented()


class ContactsWrapper:
    """
    XML API Wrapper for /char/ContactList
    Basically replicates evelinks behaviour while including contactTypeID
    """

    # These need to match the XML name on the leftm self attributes on the right
    CONTACTS_MAP = {
        'contactList': 'personal',
        'corporateContactList': 'corp',
        'allianceContactList': 'alliance',
    }

    LABEL_MAP = {
        'contactLabels': 'personalLabels',
        'corporateContactLabels': 'corpLabels',
        'allianceContactLabels': 'allianceLabels',
    }

    @python_2_unicode_compatible
    class Label:
        def __init__(self, json):
            self.id = json['label_id']
            self.name = json['label_name']

        def __str__(self):
            return u'{}'.format(self.name)

        def __repr__(self):
            return str(self)

    @python_2_unicode_compatible
    class Contact:

        @staticmethod
        def get_type_id_from_name(type_name):
            """
            Mapps new ESI name to old type id.
            Character type is allways mapped to 1373
            And faction type to 500000
            Determines the contact type:
            2 = Corporation
            1373-1386 = Character
            16159 = Alliance
            500001 - 500024 = Faction
            """
            if type_name == 'character':
                return 1373
            if type_name == 'alliance':
                return 16159
            if type_name == 'faction':
                return 500001
            if type_name == 'corporation':
                return 2

            raise NotImplementedError('This contact type is not mapped')

        def __init__(self, json, labels, names_info):
            self.id = json['contact_id']
            # TODO: remove this and translate id to name when displayed
            self.name = names_info[self.id] if self.id in names_info else 'Could not get name from API'
            self.standing = json['standing']
            self.in_watchlist = json['in_watchlist'] if 'in_watchlist' in json else None
            self.label_ids = json['label_ids'] if 'label_ids' in json and json['label_ids'] is not None else []
            self.type_id = self.__class__.get_type_id_from_name(
                json['contact_type'])
            # list of lanbels
            self.labels = [l for l in labels if l.id in self.label_ids]

        def __str__(self):
            return u'{}'.format(self.name)

        def __repr__(self):
            return str(self)

    def __init__(self, api, character_id):
        self.alliance = []
        self.allianceLabels = []

        alliance_id = EveCharacter.objects.get_character_by_id(character_id).alliance_id
        allianceLabelInfo = api.Contacts.get_alliances_alliance_id_contacts_labels(alliance_id=alliance_id)
        allianceContactsInfo = api.Contacts.get_alliances_alliance_id_contacts(alliance_id=alliance_id, page=1)
        allianceContactsInfo.also_return_response = True

        for label in allianceLabelInfo.result():
            self.allianceLabels.append(self.Label(label))

        entity_ids = []

        contacts, response = allianceContactsInfo.result()
        logger.debug("Got %d contacs with 1st page", len(contacts))
        # get the x-pages header
        pages = int(response.headers['X-Pages']) if 'X-Pages' in response.headers else 1
        logger.debug("We need to get %d page(s) of contacts in total", pages)

        for page in xrange(2, pages+1):
            logger.debug("Getting page %d/%d of contacts", page, pages)
            allianceContactsInfo = api.Contacts.get_alliances_alliance_id_contacts(
                alliance_id=alliance_id,
                page=page
                )
            new_contacts = allianceContactsInfo.result()
            logger.debug("Got %d contacs with %d page", len(new_contacts), page)
            contacts = contacts + new_contacts
        logger.debug("Got %d contact in total from %d pages", len(contacts), pages)
        for contact in contacts:
            entity_ids.append(contact['contact_id'])

        name_info = EveNameCache.get_names(entity_ids)

        for contact in contacts:
            self.alliance.append(self.Contact(contact, self.allianceLabels, name_info))

