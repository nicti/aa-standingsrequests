from __future__ import unicode_literals
from django.http import Http404, JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from django.utils.translation import ugettext as _
from django.db.models import Q
from future.utils import iteritems

from .models import ContactSet, StandingsRequest, StandingsRevocation, PilotStanding, CorpStanding
from .managers.standings import StandingsManager
from .managers.eveentity import EveEntityManager
from .helpers.evecharacter import EveCharacterHelper
from .helpers.writers import UnicodeWriter
from .helpers.evecorporation import EveCorporation

import logging
from esi.decorators import token_required
from allianceauth.eveonline.managers import EveCharacterManager
from allianceauth.eveonline.models import EveCharacter
from django.conf import settings
from esi.models import Token
from allianceauth.authentication.models import CharacterOwnership
from .helpers.helpers import user_is_member
from allianceauth.standingsrequests.models import EveNameCache

logger = logging.getLogger(__name__)


@login_required
@permission_required('standingsrequests.request_standings')
def index_view(request):
    logger.debug("Start index_view request")
    characters = EveEntityManager.get_characters_by_user(request.user)

    char_ids = [c.character_id for c in characters]

    # Get all the unique corp IDs of non-member characters
    corp_ids = set([int(c.corporation_id) for c in characters
                    if not StandingsManager.pilot_in_organisation(c.character_id)])

    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        return render(request, 'standings-requests/error.html', {
            'error_message':
                _('You must fetch contacts using the standings_update task before using the standings tool')
        })

    standings = contact_set.pilotstanding_set.filter(contactID__in=char_ids)

    st_data = []

    for c in characters:
        try:
            standing = standings.get(contactID=c.character_id).standing
        except ObjectDoesNotExist:
            standing = None
        st_data.append({
            'character': c,
            'standing': standing,
            'pendingRequest': StandingsRequest.pending_request(c.character_id),
            'pendingRevocation': StandingsRevocation.pending_request(c.character_id),
            'requestActioned': StandingsRequest.actioned_request(c.character_id),
            'inOrganisation': StandingsManager.pilot_in_organisation(c.character_id),
        })

    standings = contact_set.corpstanding_set.filter(contactID__in=list(corp_ids))

    corp_st_data = []

    for c in corp_ids:
        try:
            standing = standings.get(contactID=c).standing
        except ObjectDoesNotExist:
            standing = None
        
        
        corp_st_data.append({
            'have_keys': sum([1 for a in CharacterOwnership.objects.filter(user=request.user).filter(character__corporation_id=c)
                              if True ]),# TODO if EveManager.check_if_api_key_pair_exist(a.api_id)
            'corp': EveCorporation.get_corp_by_id(c),
            'standing': standing,
            'pendingRequest': StandingsRequest.pending_request(c),
            'pendingRevocation': StandingsRevocation.pending_request(c),
            'requestActioned': StandingsRequest.actioned_request(c),
        })

    render_items = {'characters': st_data,
                    'corps': corp_st_data,
                    'authinfo': {
                        'main_char_id': request.user.profile.main_character.character_id
                        }
                    }
    return render(request, 'standings-requests/index.html', render_items)


@login_required
@permission_required('standingsrequests.request_standings')
def request_pilot_standings(request, character_id):
    """
    For a user to request standings for their own pilots
    """
    logger.debug("Standings request from user {0} for characterID {1}".format(request.user, character_id))
    if EveEntityManager.is_character_owned_by_user(character_id, request.user):
        if not StandingsRequest.pending_request(character_id) and not StandingsRevocation.pending_request(character_id):
            StandingsRequest.add_request(request.user, character_id, PilotStanding.get_contact_type(character_id))
        else:
            # Pending request, not allowed
            logger.warn("Contact ID {0} already has a pending request".format(character_id))
    else:
        logger.warn("User {0} does not own Pilot ID {1}, forbidden".format(request.user, character_id))
    return redirect('standings-requests:index')


@login_required
@permission_required('standingsrequests.request_standings')
def remove_pilot_standings(request, character_id):
    """
    Handles both removing requests and removing existing standings
    """
    logger.debug('remove_pilot_standings called by %s' % request.user)
    if EveEntityManager.is_character_owned_by_user(character_id, request.user):
        if (not StandingsManager.pilot_in_organisation(character_id) and
                (StandingsRequest.pending_request(character_id) or StandingsRequest.actioned_request(character_id)) and
                not StandingsRevocation.pending_request(character_id)):
            logger.debug('Removing standings requests for characterID {0} by user {1}'.format(character_id,
                                                                                              request.user))
            StandingsRequest.remove_requests(character_id)
        else:
            standing = ContactSet.objects.latest().pilotstanding_set.filter(contactID=character_id)
            if standing.exists() and standing[0].standing > 0:
                # Manual revocation required
                logger.debug('Creating standings revocation for characterID {0} by user {1}'.format(character_id,
                                                                                                    request.user))
                StandingsRevocation.add_revocation(character_id, PilotStanding.get_contact_type(character_id))
            else:
                logger.debug('No standings exist for characterID {0}'.format(character_id))
            logger.debug('Cannot remove standings for pilot {0}'.format(character_id))
    else:
        logger.warn('User {0} tried to remove standings for characterID {1} but was not permitted'.format(
            request.user, character_id))

    return redirect('standings-requests:index')


@login_required
@permission_required('standingsrequests.request_standings')
def request_corp_standings(request, corp_id):
    """
    For a user to request standings for their own corp
    """
    logger.debug("Standings request from user {0} for corpID {1}".format(request.user, corp_id))

    # Check the user has the required number of member keys for the corporation
    if StandingsManager.all_corp_apis_recorded(corp_id, request.user):
        if not StandingsRequest.pending_request(corp_id) and not StandingsRevocation.pending_request(corp_id):
            StandingsRequest.add_request(request.user, corp_id, CorpStanding.get_contact_type(corp_id))
        else:
            # Pending request, not allowed
            logger.warn("Contact ID {0} already has a pending request".format(corp_id))
    else:
        logger.warn("User {0} does not have enough keys for corpID {1}, forbidden".format(request.user, corp_id))
    return redirect('standings-requests:index')


@login_required
@permission_required('standingsrequests.request_standings')
def remove_corp_standings(request, corp_id):
    """
    Handles both removing corp requests and removing existing standings
    """
    logger.debug('remove_corp_standings called by %s' % request.user)
    # Need all corp APIs recorded to "own" the corp
    st_req = get_object_or_404(StandingsRequest, contactID=corp_id)
    if st_req.user == request.user:
        if ((StandingsRequest.pending_request(corp_id) or StandingsRequest.actioned_request(corp_id)) and
                not StandingsRevocation.pending_request(corp_id)):
            logger.debug('Removing standings requests for corpID {0} by user {1}'.format(corp_id,
                                                                                         request.user))
            StandingsRequest.remove_requests(corp_id)
        else:
            standing = ContactSet.objects.latest().corpstanding_set.filter(contactID=corp_id)
            if standing.exists() and standing[0].standing > 0:
                # Manual revocation required
                logger.debug('Creating standings revocation for corpID {0} by user {1}'.format(corp_id,
                                                                                               request.user))
                StandingsRevocation.add_revocation(corp_id, CorpStanding.get_contact_type(corp_id))
            else:
                logger.debug('No standings exist for corpID {0}'.format(corp_id))
            logger.debug('Cannot remove standings for pilot {0}'.format(corp_id))
    else:
        logger.warn('User {0} tried to remove standings for corpID {1} but was not permitted'.format(
            request.user, corp_id))

    return redirect('standings-requests:index')


####################
# Management views #
####################
@login_required
@permission_required('standingsrequests.view')
def view_pilots_standings(request):
    logger.debug('view_pilot_standings called by %s' % request.user)
    try:
        last_update = ContactSet.objects.latest().date
    except ObjectDoesNotExist:
        last_update = None
    return render(request, 'standings-requests/view_pilots.html', {'lastUpdate': last_update})


@login_required
@permission_required('standingsrequests.view')
def view_pilots_standings_json(request):
    logger.debug('view_pilot_standings_json called by %s' % request.user)
    contacts = ContactSet.objects.latest()

    def get_pilots():
        pilots = []
        # lets catch these in bulk
        pilot_standings = contacts.pilotstanding_set.all().order_by('-standing')
        contact_ids = [p.contactID for p in pilot_standings]
        EveNameCache.get_names(contact_ids)
        for p in pilot_standings:
            char = EveCharacter.objects.get_character_by_id(p.contactID)
            if char is None:
                char = EveCharacterHelper(p.contactID)

            is_member = False
            main = None
            try:
                ownership = CharacterOwnership.objects.get(character__character_id=char.character_id)
                user = ownership.user
                main = user.profile.main_character
                is_member = user_is_member(user)
            except CharacterOwnership.DoesNotExist:
                pass

            pilot = {
                'character_id': p.contactID,
                'character_name': p.name,
                'corporation_id': char.corporation_id if char else None,
                'corporation_name': char.corporation_name if char else None,
                'corporation_ticker': char.corporation_ticker if char else None,
                'alliance_id': char.alliance_id if char else None,
                'alliance_name': char.alliance_name if char else None,
                'api_key': False,
                'member': is_member,
                'main_character_ticker': main.corporation_ticker if main else None,
                'standing': p.standing,
                'labels': [l.name for l in p.labels.all()]
            }

            try:
                pilot['main_character_name'] = main.character_name if main else char.main_character.character_name
            except AttributeError:
                pilot['main_character_name'] = None

            pilots.append(pilot)

        return pilots

    # Cache result for 10 minutes, with a large number of standings this view can be very CPU intensive
    pilots = cache.get_or_set('standings_requests_view_pilots_standings_json', get_pilots, timeout=60*10)

    return JsonResponse(pilots, safe=False)


@login_required
@permission_required('standingsrequests.download')
def download_pilot_standings(request):
    logger.info('download_pilot_standings called by %s' % request.user)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="standings.csv"'

    writer = UnicodeWriter(response)

    contacts = ContactSet.objects.latest()

    writer.writerow([
            'character_id',
            'character_name',
            'corporation_id',
            'corporation_name',
            'corporation_ticker',
            'alliance_id',
            'alliance_name',
            'api_key',
            'member',
            'main_character_name',
            'main_character_ticker',
            'standing',
            'labels',
        ])

    # lets request make sure all info is there in bulk
    pilot_standings = contacts.pilotstanding_set.all().order_by('-standing')
    EveNameCache.get_names([p.contactID for p in pilot_standings])

    for p in pilot_standings:
        char = EveCharacter.objects.get_character_by_id(p.contactID)
        main = ''
        is_member = False
        """
        TODO: this should include roles instead of ismember state
        if char:
            try:
                auth = AuthServicesInfo.objects.get(user=char.user)
                main = EveManager.get_character_by_id(auth.main_char_id)
                is_member = auth_services_is_member(auth)
            except ObjectDoesNotExist:
                pass
        else:
            char = EveCharacterHelper(p.contactID)
        """
        try:
            main_character_name = main.character_name if main else char.main_character.character_name
        except AttributeError:
            main_character_name = ''

        pilot = [
            p.contactID,
            p.name,
            char.corporation_id if char else '',
            char.corporation_name if char else '',
            char.corporation_ticker if char else '',
            char.alliance_id if char else '',
            char.alliance_name if char else '',
            False,
            is_member,
            main_character_name,
            main.corporation_ticker if main else '',
            p.standing,
            ', '.join([l.name for l in p.labels.all()])
        ]

        writer.writerow([str(v) if v is not None else '' for v in pilot])
    return response


@login_required
@permission_required('standingsrequests.view')
def view_groups_standings(request):
    logger.debug('view_group_standings called by %s' % request.user)
    try:
        last_update = ContactSet.objects.latest().date
    except ObjectDoesNotExist:
        last_update = None
    return render(request, 'standings-requests/view_groups.html', {'lastUpdate': last_update})


@login_required
@permission_required('standingsrequests.view')
def view_groups_standings_json(request):
    logger.debug('view_pilot_standings_json called by %s' % request.user)
    contacts = ContactSet.objects.latest()

    corps = []
    for p in contacts.corpstanding_set.all().order_by('-standing'):
        corps.append({
            'corporation_id': p.contactID,
            'corporation_name': p.name,
            'standing': p.standing,
            'labels': [l.name for l in p.labels.all()]
        })

    alli = []
    for p in contacts.alliancestanding_set.all().order_by('-standing'):
        alli.append({
            'alliance_id': p.contactID,
            'alliance_name': p.name,
            'standing': p.standing,
            'labels': [l.name for l in p.labels.all()]
        })

    return JsonResponse({'corps': corps, 'alliances': alli}, safe=False)

###################
# Manage requests #
###################


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_standings(request):
    logger.debug('manage_standings called by %s' % request.user)
    return render(request, 'standings-requests/manage.html')


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_get_requests_json(request):
    logger.debug('manage_get_requests_json called by %s' % request.user)
    reqs = StandingsRequest.objects.filter(Q(actionBy=None) & Q(effective=False)).order_by('requestDate')

    response = []
    # precache missing names in bulk
    entity_ids = [r.contactID for r in reqs]
    EveNameCache.get_names(entity_ids)

    for r in reqs:
        # Dont forget that contact requests aren't strictly ALWAYS pilots (at least can potentially be corps/alliances)
        is_member = False
        api_key = False
        main = r.user.profile.main_character

        is_member = user_is_member(r.user)

        pilot = None
        corp = None
        if PilotStanding.is_pilot(r.contactType):
            pilot = EveCharacter.objects.get_character_by_id(r.contactID)
            if pilot:
                api_key = ''# TODO EveManager.check_if_api_key_pair_exist(pilot.api_id)
            else:
                pilot = EveCharacterHelper(r.contactID)
        elif CorpStanding.is_corp(r.contactType):
            corp = EveCorporation.get_corp_by_id(r.contactID)

        response.append({
            'contact_id': r.contactID,
            'contact_name': pilot.character_name if pilot else corp.corporation_name if corp else None,
            'corporation_id': pilot.corporation_id if pilot else corp.corporation_id if corp else None,
            'corporation_name': pilot.corporation_name if pilot else corp.corporation_name if corp else None,
            'corporation_ticker': pilot.corporation_ticker if pilot else corp.ticker if corp else None,
            'alliance_id': pilot.alliance_id if pilot else None,
            'alliance_name': pilot.alliance_name if pilot else None,
            'api_key': api_key if pilot else
            StandingsManager.all_corp_apis_recorded(corp.corporation_id, r.user) if corp else False,
            'member': is_member,
            'main_character_name': main.character_name if main else None,
            'main_character_ticker': main.corporation_ticker if main else None,
        })

    return JsonResponse(response, safe=False)


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_requests_write(request, contact_id):
    logger.debug('manage_requests_write called by %s' % request.user)
    if request.method == "PUT":
        reqs = StandingsRequest.objects.filter(contactID=contact_id)
        actioned = 0
        for r in reqs:
            r.mark_standing_actioned(request.user)
            actioned += 1
        if actioned > 0:
            return JsonResponse({}, status=204)
        else:
            return Http404
    elif request.method == "DELETE":
        StandingsRequest.remove_requests(contact_id)
        # TODO: Notify user
        # TODO: Error handling
        return JsonResponse({}, status=204)
    else:
        return Http404


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_get_revocations_json(request):
    logger.debug('manage_get_revocations_json called by %s' % request.user)
    reqs = StandingsRevocation.objects.filter(Q(actionBy=None) & Q(effective=False)).order_by('requestDate')

    response = []

    # precache names in bulk
    EveNameCache.get_names([r.contactID for r in reqs])
    for r in reqs:
        # Dont forget that contact requests aren't strictly ALWAYS pilots (at least can potentially be corps/alliances)
        is_member = False
        api_key = False

        pilot = None
        corp = None
        corp_user = None
        main = None
        if PilotStanding.is_pilot(r.contactType):
            pilot = EveCharacter.get_character_by_id(r.contactID)
            if pilot:
                api_key = ''# TODO:  check for token EveManager.check_if_api_key_pair_exist(pilot.api_id)

            else:
                pilot = EveCharacterHelper(r.contactID)
        elif CorpStanding.is_corp(r.contactType):
            corp = EveCorporation.get_corp_by_id(r.contactID)
            user_election = {}
            # Figure out which user has the most APIs for this corp, if any
            for c in EveCharacter.objects.filter(corporation_id=r.contactID):
                # get_or_set type increment
                user_election[c.user.pk] = 1 + user_election.get(c.user.pk, 0)

            if user_election:
                # Py2 compatible??
                corp_user = User.objects.get(pk=max(user_election.keys(), key=(lambda key: user_election[key])))

        if pilot or corp_user:
            # Get member details if we found a user
            main = pilot.user.profile.main_character
            is_member = user_is_member(pilot.user)

        revoke = {
            'contact_id': r.contactID,
            'contact_name': pilot.character_name if pilot else corp.corporation_name if corp else None,
            'corporation_id': pilot.corporation_id if pilot else corp.corporation_id if corp else None,
            'corporation_name': pilot.corporation_name if pilot else corp.corporation_name if corp else None,
            'corporation_ticker': pilot.corporation_ticker if pilot else corp.ticker if corp else None,
            'alliance_id': pilot.alliance_id if pilot else None,
            'alliance_name': pilot.alliance_name if pilot else None,
            'api_key': api_key if pilot else
            StandingsManager.all_corp_apis_recorded(corp.corporation_id, corp_user) if corp and corp_user else False,
            'member': is_member,
            'main_character_name': main.character_name if main else None,
            'main_character_ticker': main.corporation_ticker if main else None,
        }

        try:
            revoke['main_character_name'] = main.character_name if main else pilot.main_character.character_name
        except AttributeError:
            revoke['main_character_name'] = None

        response.append(revoke)

    return JsonResponse(response, safe=False)


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_revocations_write(request, contact_id):
    logger.debug('manage_revocations_write called by %s' % request.user)
    if request.method == "PUT":
        reqs = StandingsRevocation.objects.filter(contactID=contact_id)
        actioned = 0
        for r in reqs:
            r.mark_standing_actioned(request.user)
            actioned += 1
        if actioned > 0:
            return JsonResponse({}, status=204)
        else:
            return Http404
    elif request.method == "DELETE":
        StandingsRevocation.objects.filter(contactID=contact_id).delete()
        # TODO: Error handling
        return JsonResponse({}, status=204)
    else:
        return Http404


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_revocations_undo(request, contact_id):
    logger.debug('manage_revocations_undo called by %s' % request.user)
    if StandingsRevocation.objects.filter(contactID=contact_id).exists():
        owner = EveEntityManager.get_owner_from_character_id(contact_id)
        if owner is None:
            return JsonResponse({'Success': False, 'Message': 'Cannot find an owner for that contact ID'}, status=404)

        result = StandingsRevocation.undo_revocation(contact_id, owner)
        if result:
            return JsonResponse({}, status=204)
    return JsonResponse({'Success': False, 'Message': 'Cannot find a revocation for that contact ID'}, status=404)


@login_required
@permission_required('standingsrequests.affect_standings')
def view_active_requests(request):
    return render(request, 'standings-requests/requests.html')


@login_required
@permission_required('standingsrequests.affect_standings')
def view_active_requests_json(request):
    reqs = StandingsRequest.objects.all().order_by('requestDate')

    response = []
    # pre cache names in bulk
    EveNameCache.get_names([r.contactID for r in reqs])
    for r in reqs:
        # Dont forget that contact requests aren't strictly ALWAYS pilots (at least can potentially be corps/alliances)
        is_member = False
        api_key = False
        main = r.user.profile.main_character
        is_member = user_is_member(r.user)

        pilot = None
        corp = None
        if PilotStanding.is_pilot(r.contactType):
            pilot = EveCharacter.objects.get_character_by_id(r.contactID)
            if pilot:
                api_key = ''#  EveManager.check_if_api_key_pair_exist(pilot.api_id)
            else:
                pilot = EveCharacterHelper(r.contactID)
        elif CorpStanding.is_corp(r.contactType):
            corp = EveCorporation.get_corp_by_id(r.contactID)

        response.append({
            'contact_id': r.contactID,
            'contact_name': pilot.character_name if pilot else corp.corporation_name if corp else None,
            'corporation_id': pilot.corporation_id if pilot else corp.corporation_id if corp else None,
            'corporation_name': pilot.corporation_name if pilot else corp.corporation_name if corp else None,
            'corporation_ticker': pilot.corporation_ticker if pilot else corp.ticker if corp else None,
            'alliance_id': pilot.alliance_id if pilot else None,
            'alliance_name': pilot.alliance_name if pilot else None,
            'api_key': api_key if pilot else
            StandingsManager.all_corp_apis_recorded(corp.corporation_id, r.user) if corp else False,
            'member': is_member,
            'main_character_name': main.character_name if main else None,
            'main_character_ticker': main.corporation_ticker if main else None,
            'actioned': r.actionBy is not None,
            'effective': r.effective,
            'is_corp': CorpStanding.is_corp(r.contactType),
            'is_pilot': PilotStanding.is_pilot(r.contactType),
            'action_by': r.actionBy.username if r.actionBy is not None else None,
        })

    return JsonResponse(response, safe=False)


@login_required
@permission_required('standingsrequests.affect_standings')
@token_required(new=False, scopes='esi-alliances.read_contacts.v1')
def view_auth_page(request, token):
    have_token = Token.objects.filter(character_id=settings.STANDINGS_API_CHARID
                             ).require_scopes('esi-alliances.read_contacts.v1'
                                              ).require_valid().exists()
    return render(request, 'standings-requests/view_sso.html', {'have_token': have_token, 'char_id': settings.STANDINGS_API_CHARID})
