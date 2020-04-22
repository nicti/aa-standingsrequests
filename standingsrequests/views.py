import logging

from django.http import Http404, JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from allianceauth.eveonline.models import EveCharacter
from allianceauth.authentication.models import CharacterOwnership

from esi.decorators import token_required

from . import __title__
from .decorators import token_required_by_state
from .app_settings import STANDINGS_API_CHARID, SR_CORPORATIONS_ENABLED
from .helpers.evecharacter import EveCharacterHelper
from .helpers.writers import UnicodeWriter
from .helpers.evecorporation import EveCorporation
from .models import ContactSet, StandingsRequest, StandingsRevocation
from .models import PilotStanding, CorpStanding, EveNameCache
from .models import CharacterAssociation
from .managers.standings import StandingsManager
from .managers.eveentity import EveEntityManager
from .utils import messages_plus

logger = logging.getLogger(__name__)


@login_required
@permission_required('standingsrequests.request_standings')
def index_view(request):    
    logger.debug("Start index_view request")    
    context = {
        'app_title': __title__,
        'corporations_enabled': SR_CORPORATIONS_ENABLED
    }
    return render(request, 'standingsrequests/index.html', context)


@login_required
@permission_required('standingsrequests.request_standings')
def partial_request_entities(request):    
    logger.debug("Start partial_request_entities request")
        
    try:
        contact_set = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        return render(
            request, 'standingsrequests/error.html', {'app_title': __title__}
        )

    characters = EveEntityManager.get_characters_by_user(request.user)
    char_ids = [c.character_id for c in characters]
    standings = contact_set.pilotstanding_set.filter(contactID__in=char_ids)

    char_standings_data = list()
    for character in characters:
        try:
            standing = standings.get(contactID=character.character_id).standing
        except ObjectDoesNotExist:
            standing = None
        
        try:
            standing_req = StandingsRequest.objects\
                .get(contactID=character.character_id)
        except ObjectDoesNotExist:
            standing_req = None

        char_standings_data.append({
            'character': character,
            'standing': standing,
            'pendingRequest': StandingsRequest.pending_request(
                character.character_id
            ),
            'pendingRevocation': StandingsRevocation.pending_request(
                character.character_id
            ),
            'requestActioned': StandingsRequest.actioned_request(
                character.character_id
            ),
            'inOrganisation': StandingsManager.pilot_in_organisation(
                character.character_id
            ),
            'hasRequiredScopes': StandingsManager.has_required_scopes_for_request(
                character
            ),
            'standingReqExists': standing_req,
        })

    corp_standings_data = list()
    if SR_CORPORATIONS_ENABLED:
        corp_ids = set([
            int(character.corporation_id) for character in characters
            if not StandingsManager.pilot_in_organisation(character.character_id)
        ])
        standings = contact_set.corpstanding_set.filter(
            contactID__in=list(corp_ids)
        )        
        for corp_id in corp_ids:
            corporation = EveCorporation.get_corp_by_id(corp_id)
            if corporation and not corporation.is_npc:
                try:
                    standing = standings.get(contactID=corp_id).standing
                except ObjectDoesNotExist:
                    standing = None
                
                try:
                    standing_req = StandingsRequest.objects.get(contactID=corp_id)
                except ObjectDoesNotExist:
                    standing_req = None
                
                have_scopes = sum([
                    1 for a in CharacterOwnership.objects
                    .filter(user=request.user)
                    .filter(character__corporation_id=corp_id)
                    if StandingsManager.has_required_scopes_for_request(a.character)
                ])            
                corp_standings_data.append({
                    'have_scopes': have_scopes,
                    'corp': corporation,
                    'standing': standing,
                    'pendingRequest': StandingsRequest.pending_request(corp_id),
                    'pendingRevocation': StandingsRevocation.pending_request(corp_id),
                    'requestActioned': StandingsRequest.actioned_request(corp_id),
                    'standingReqExists': standing_req,
                })
    
    render_items = {        
        'app_title': __title__,
        'characters': char_standings_data,
        'corps': corp_standings_data,
        'corporations_enabled': SR_CORPORATIONS_ENABLED,                  
        'authinfo': {
            'main_char_id': request.user.profile.main_character.character_id
        }
    }
    return render(
        request, 
        'standingsrequests/partials/_request_entities.html', 
        render_items
    )


@login_required
@permission_required('standingsrequests.request_standings')
def request_pilot_standings(request, character_id):
    """
    For a user to request standings for their own pilots
    """
    logger.debug(
        "Standings request from user %s for characterID %d", 
        request.user, 
        character_id
    )
    if EveEntityManager.is_character_owned_by_user(character_id, request.user):
        if (
            not StandingsRequest.pending_request(character_id) 
            and not StandingsRevocation.pending_request(character_id)
        ):
            StandingsRequest.add_request(
                request.user, character_id, 
                PilotStanding.get_contact_type(character_id)
            )
        else:
            # Pending request, not allowed
            logger.warning(
                "Contact ID %d already has a pending request", character_id
            )
    else:
        logger.warning(
            "User %s does not own Pilot ID %d, forbidden", 
            request.user, 
            character_id
        )
    return redirect('standingsrequests:index')


@login_required
@permission_required('standingsrequests.request_standings')
def remove_pilot_standings(request, character_id):
    """
    Handles both removing requests and removing existing standings
    """
    logger.debug('remove_pilot_standings called by %s', request.user)
    if EveEntityManager.is_character_owned_by_user(character_id, request.user):
        if (
            not StandingsManager.pilot_in_organisation(character_id) 
            and (
                StandingsRequest.pending_request(character_id) 
                or StandingsRequest.actioned_request(character_id)
            )
            and not StandingsRevocation.pending_request(character_id)
        ):
            logger.debug(
                'Removing standings requests for characterID %d by user %d', 
                character_id, 
                request.user
            )
            StandingsRequest.remove_requests(character_id)
        else:
            standing = ContactSet.objects\
                .latest().pilotstanding_set\
                .filter(contactID=character_id)
            if standing.exists() and standing[0].standing > 0:
                # Manual revocation required
                logger.debug(
                    'Creating standings revocation for characterID %d by user %s',
                    character_id,
                    request.user
                )
                StandingsRevocation.add_revocation(
                    character_id, PilotStanding.get_contact_type(character_id)
                )
            else:
                logger.debug(
                    'No standings exist for characterID %d', character_id
                )
            logger.debug('Cannot remove standings for pilot %d', character_id)
    else:
        logger.warning(
            'User %s tried to remove standings for characterID %d '
            'but was not permitted',
            request.user, 
            character_id
        )

    return redirect('standingsrequests:index')


@login_required
@permission_required('standingsrequests.request_standings')
def request_corp_standings(request, corp_id):
    """
    For a user to request standings for their own corp
    """
    logger.debug(
        "Standings request from user %s for corpID %d",
        request.user, 
        corp_id
    )

    # Check the user has the required number of member keys for the corporation
    if StandingsManager.all_corp_apis_recorded(corp_id, request.user):
        if (
            not StandingsRequest.pending_request(corp_id) 
            and not StandingsRevocation.pending_request(corp_id)
        ):
            StandingsRequest.add_request(
                request.user, corp_id, CorpStanding.get_contact_type(corp_id)
            )
        else:
            # Pending request, not allowed
            logger.warning("Contact ID %d already has a pending request", corp_id)
    else:
        logger.warning(
            "User %s does not have enough keys for corpID %d, forbidden", 
            request.user, 
            corp_id
        )
    return redirect('standingsrequests:index')


@login_required
@permission_required('standingsrequests.request_standings')
def remove_corp_standings(request, corp_id):
    """
    Handles both removing corp requests and removing existing standings
    """
    logger.debug('remove_corp_standings called by %s', request.user)
    # Need all corp APIs recorded to "own" the corp
    st_req = get_object_or_404(StandingsRequest, contactID=corp_id)
    if st_req.user == request.user:
        if (
            (
                StandingsRequest.pending_request(corp_id) 
                or StandingsRequest.actioned_request(corp_id)
            ) 
            and not StandingsRevocation.pending_request(corp_id)
        ):
            logger.debug(
                'Removing standings requests for corpID %d by user %s', 
                corp_id, 
                request.user
            )
            StandingsRequest.remove_requests(corp_id)
        else:
            standing = ContactSet.objects\
                .latest().corpstanding_set\
                .filter(contactID=corp_id)
            if standing.exists() and standing[0].standing > 0:
                # Manual revocation required
                logger.debug(
                    'Creating standings revocation for corpID %d by user %s', 
                    corp_id, 
                    request.user
                )
                StandingsRevocation.add_revocation(
                    corp_id, CorpStanding.get_contact_type(corp_id)
                )
            else:
                logger.debug('No standings exist for corpID %d', corp_id)
            logger.debug('Cannot remove standings for pilot %d', corp_id)
    else:
        logger.warning(
            'User %s tried to remove standings for corpID %d but was not permitted',
            request.user, 
            corp_id
        )

    return redirect('standingsrequests:index')


####################
# Management views #
####################
@login_required
@permission_required('standingsrequests.view')
def view_pilots_standings(request):
    logger.debug('view_pilot_standings called by %s', request.user)
    try:
        last_update = ContactSet.objects.latest().date
    except (ObjectDoesNotExist, ContactSet.DoesNotExist):
        last_update = None
    return render(
        request, 
        'standingsrequests/view_pilots.html', 
        {
            'lastUpdate': last_update, 
            'app_title': __title__
        }
    )


@login_required
@permission_required('standingsrequests.view')
def view_pilots_standings_json(request):
    logger.debug('view_pilot_standings_json called by %s', request.user)
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()

    def get_pilots():
        pilots = list()
        # lets catch these in bulk
        pilot_standings = contacts.pilotstanding_set.all().order_by('-standing')
        contact_ids = [p.contactID for p in pilot_standings]
        for p in pilot_standings:
            try:
                assoc = CharacterAssociation.objects.get(character_id=p.contactID)
                if assoc.corporation_id is not None:
                    contact_ids.append(assoc.corporation_id)
                if assoc.alliance_id is not None:
                    contact_ids.append(assoc.alliance_id)
            except CharacterAssociation.DoesNotExist:
                pass
        EveNameCache.get_names(contact_ids)
        for p in pilot_standings:
            char = EveCharacter.objects.get_character_by_id(p.contactID)
            if char is None:
                char = EveCharacterHelper(p.contactID)

            main = None
            state = ''
            try:
                ownership = CharacterOwnership.objects\
                    .get(character__character_id=char.character_id)
                user = ownership.user
                main = user.profile.main_character
                if user.profile.state:
                    state = user.profile.state.name
            except CharacterOwnership.DoesNotExist:
                pass

            has_required_scopes = \
                StandingsManager.has_required_scopes_for_request(char)
            pilot = {
                'character_id': p.contactID,
                'character_name': p.name,
                'corporation_id': char.corporation_id if char else None,
                'corporation_name': char.corporation_name if char else None,
                'corporation_ticker': char.corporation_ticker if char else None,
                'alliance_id': char.alliance_id if char else None,
                'alliance_name': char.alliance_name if char else None,
                'has_required_scopes': has_required_scopes,
                'state': state,
                'main_character_ticker': main.corporation_ticker if main else None,
                'standing': p.standing,
                'labels': [l.name for l in p.labels.all()]
            }

            try:
                pilot['main_character_name'] = main.character_name \
                    if main else char.main_character.character_name
            except AttributeError:
                pilot['main_character_name'] = None

            pilots.append(pilot)
        return pilots

    # Cache result for 10 minutes, 
    # with a large number of standings this view can be very CPU intensive
    pilots = cache.get_or_set(
        'standings_requests_view_pilots_standings_json', 
        get_pilots, 
        timeout=60 * 10
    )
    return JsonResponse(pilots, safe=False)


@login_required
@permission_required('standingsrequests.download')
def download_pilot_standings(request):
    logger.info('download_pilot_standings called by %s', request.user)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="standings.csv"'

    writer = UnicodeWriter(response)
    
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()

    writer.writerow([
        'character_id',
        'character_name',
        'corporation_id',
        'corporation_name',
        'corporation_ticker',
        'alliance_id',
        'alliance_name',
        'has_scopes',
        'state',
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
        state = ''
        try:
            ownership = CharacterOwnership.objects.get(character=char)
            state = ownership.user.profile.state.name
            main = ownership.user.profile.main_character
            if main is None:
                main_character_name = ''
            else:
                main_character_name = main.character_name
        except CharacterOwnership.DoesNotExist:
            main_character_name = ''
            main = None

        pilot = [
            p.contactID,
            p.name,
            char.corporation_id if char else '',
            char.corporation_name if char else '',
            char.corporation_ticker if char else '',
            char.alliance_id if char else '',
            char.alliance_name if char else '',
            StandingsManager.has_required_scopes_for_request(char),
            state,
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
    logger.debug('view_group_standings called by %s', request.user)
    try:
        last_update = ContactSet.objects.latest().date
    except (ObjectDoesNotExist, ContactSet.DoesNotExist):
        last_update = None
    return render(
        request, 
        'standingsrequests/view_groups.html', 
        {'lastUpdate': last_update, 'app_title': __title__}
    )


@login_required
@permission_required('standingsrequests.view')
def view_groups_standings_json(request):
    logger.debug('view_pilot_standings_json called by %s', request.user)    
    try:
        contacts = ContactSet.objects.latest()
    except ContactSet.DoesNotExist:
        contacts = ContactSet()

    corps = list()
    for p in contacts.corpstanding_set.all().order_by('-standing'):
        corps.append({
            'corporation_id': p.contactID,
            'corporation_name': p.name,
            'standing': p.standing,
            'labels': [l.name for l in p.labels.all()]
        })

    alliances = list()
    for p in contacts.alliancestanding_set.all().order_by('-standing'):
        alliances.append({
            'alliance_id': p.contactID,
            'alliance_name': p.name,
            'standing': p.standing,
            'labels': [l.name for l in p.labels.all()]
        })

    return JsonResponse({'corps': corps, 'alliances': alliances}, safe=False)

###################
# Manage requests #
###################


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_standings(request):
    logger.debug('manage_standings called by %s', request.user)
    return render(
        request, 'standingsrequests/manage.html', {'app_title': __title__}
    )


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_get_requests_json(request):
    logger.debug('manage_get_requests_json called by %s', request.user)
    requests_qs = StandingsRequest.objects\
        .filter(Q(actionBy=None) & Q(effective=False))\
        .order_by('requestDate')

    response = list()
    # precache missing names in bulk
    entity_ids = [r.contactID for r in requests_qs]
    for p in requests_qs:
        try:
            assoc = CharacterAssociation.objects.get(character_id=p.contactID)
            if assoc.corporation_id is not None:
                entity_ids.append(assoc.corporation_id)
            if assoc.alliance_id is not None:
                entity_ids.append(assoc.alliance_id)
        except CharacterAssociation.DoesNotExist:
            pass
    EveNameCache.get_names(entity_ids)

    for r in requests_qs:
        # Dont forget that contact requests aren't strictly ALWAYS pilots 
        # (at least can potentially be corps/alliances)
        main = r.user.profile.main_character
        state = ''
        pilot = None
        corp = None

        if PilotStanding.is_pilot(r.contactType):
            pilot = EveCharacter.objects.get_character_by_id(r.contactID)
            if not pilot:
                pilot = EveCharacterHelper(r.contactID)

            state_name = EveEntityManager.get_state_of_character(pilot)
            if state_name is not None:
                state = state_name

        elif CorpStanding.is_corp(r.contactType):
            corp = EveCorporation.get_corp_by_id(r.contactID)

        contact_name = \
            pilot.character_name if pilot \
            else corp.corporation_name if corp \
            else None
        corporation_id = \
            pilot.corporation_id if pilot \
            else corp.corporation_id if corp \
            else None
        corporation_name = \
            pilot.corporation_name if pilot \
            else corp.corporation_name if corp \
            else None
        corporation_ticker = \
            pilot.corporation_ticker if pilot \
            else corp.ticker if corp \
            else None
        has_scopes = \
            StandingsManager.has_required_scopes_for_request(pilot) if pilot \
            else StandingsManager.all_corp_apis_recorded(
                corp.corporation_id, r.user
            ) if corp \
            else False
        
        response.append({
            'contact_id': r.contactID,
            'contact_name': contact_name,
            'corporation_id': corporation_id,
            'corporation_name': corporation_name,
            'corporation_ticker': corporation_ticker,
            'alliance_id': pilot.alliance_id if pilot else None,
            'alliance_name': pilot.alliance_name if pilot else None,
            'has_scopes': has_scopes,
            'state': state,
            'main_character_name': main.character_name if main else None,
            'main_character_ticker': main.corporation_ticker if main else None,
        })

    return JsonResponse(response, safe=False)


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_requests_write(request, contact_id):
    logger.debug('manage_requests_write called by %s', request.user)
    if request.method == "PUT":        
        actioned = 0
        for r in StandingsRequest.objects.filter(contactID=contact_id):
            r.mark_standing_actioned(request.user)
            actioned += 1
        if actioned > 0:
            return JsonResponse(dict(), status=204)
        else:
            return Http404
    elif request.method == "DELETE":
        StandingsRequest.remove_requests(contact_id)
        # TODO: Notify user
        # TODO: Error handling
        return JsonResponse(dict(), status=204)
    else:
        return Http404


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_get_revocations_json(request):
    logger.debug('manage_get_revocations_json called by %s', request.user)
    revocations_qs = StandingsRevocation.objects\
        .filter(Q(actionBy=None) & Q(effective=False))\
        .order_by('requestDate')

    response = list()

    # precache names in bulk
    entity_ids = [r.contactID for r in revocations_qs]
    for p in revocations_qs:
        try:
            assoc = CharacterAssociation.objects.get(character_id=p.contactID)
            if assoc.corporation_id is not None:
                entity_ids.append(assoc.corporation_id)
            if assoc.alliance_id is not None:
                entity_ids.append(assoc.alliance_id)
        except CharacterAssociation.DoesNotExist:
            pass
    EveNameCache.get_names(entity_ids)
    for r in revocations_qs:
        # Dont forget that contact requests aren't strictly ALWAYS pilots 
        # (at least can potentially be corps/alliances)
        state = ''

        pilot = None
        corp = None
        corp_user = None
        main = None
        if PilotStanding.is_pilot(r.contactType):
            pilot = EveCharacter.objects.get_character_by_id(r.contactID)

            if not pilot:
                pilot = EveCharacterHelper(r.contactID)
            state_name = EveEntityManager.get_state_of_character(pilot)
            if state_name is not None:
                state = state_name

        elif CorpStanding.is_corp(r.contactType):
            corp = EveCorporation.get_corp_by_id(r.contactID)
            user_election = dict()
            # Figure out which user has the most APIs for this corp, if any
            for c in EveCharacter.objects.filter(corporation_id=r.contactID):
                # get_or_set type increment
                user_election[c.user.pk] = 1 + user_election.get(c.user.pk, 0)

            if user_election:
                # Py2 compatible??
                corp_user = User.objects.get(
                    pk=max(
                        user_election.keys(), 
                        key=(lambda key: user_election[key])
                    )
                )

        if pilot or corp_user:
            # Get member details if we found a user
            try:
                user = CharacterOwnership.objects.get(character=pilot).user
                main = user.profile.main_character
            except CharacterOwnership.DoesNotExist:
                main = None
            
        contact_name = pilot.character_name if pilot \
            else corp.corporation_name if corp \
            else None
        corporation_id = pilot.corporation_id if pilot \
            else corp.corporation_id if corp \
            else None
        corporation_name = pilot.corporation_name if pilot \
            else corp.corporation_name if corp \
            else None
        corporation_ticker = pilot.corporation_ticker if pilot \
            else corp.ticker if corp \
            else None
        has_scopes = (
            StandingsManager.has_required_scopes_for_request(pilot) 
            if pilot else StandingsManager.all_corp_apis_recorded(
                corp.corporation_id, corp_user
            ) if corp and corp_user 
            else False
        )        
        revoke = {
            'contact_id': r.contactID,
            'contact_name': contact_name,
            'corporation_id': corporation_id,
            'corporation_name': corporation_name,
            'corporation_ticker': corporation_ticker,
            'alliance_id': pilot.alliance_id if pilot else None,
            'alliance_name': pilot.alliance_name if pilot else None,
            'has_scopes': has_scopes,
            'state': state,
            'main_character_name': main.character_name if main else None,
            'main_character_ticker': main.corporation_ticker if main else None,
        }

        try:
            revoke['main_character_name'] = \
                main.character_name if main else pilot.main_character.character_name
        except AttributeError:
            revoke['main_character_name'] = None

        response.append(revoke)

    return JsonResponse(response, safe=False)


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_revocations_write(request, contact_id):
    logger.debug('manage_revocations_write called by %s', request.user)
    if request.method == "PUT":        
        actioned = 0
        for r in StandingsRevocation.objects.filter(contactID=contact_id):
            r.mark_standing_actioned(request.user)
            actioned += 1
        if actioned > 0:
            return JsonResponse(dict(), status=204)
        else:
            return Http404
    elif request.method == "DELETE":
        StandingsRevocation.objects.filter(contactID=contact_id).delete()
        # TODO: Error handling
        return JsonResponse(dict(), status=204)
    else:
        return Http404


@login_required
@permission_required('standingsrequests.affect_standings')
def manage_revocations_undo(request, contact_id):
    logger.debug('manage_revocations_undo called by %s', request.user)
    if StandingsRevocation.objects.filter(contactID=contact_id).exists():
        owner = EveEntityManager.get_owner_from_character_id(contact_id)
        if owner is None:
            return JsonResponse(
                {
                    'Success': False, 
                    'Message': 'Cannot find an owner for that contact ID'
                }, 
                status=404
            )

        result = StandingsRevocation.undo_revocation(contact_id, owner)
        if result:
            return JsonResponse(dict(), status=204)
            
    return JsonResponse(
        {
            'Success': False, 
            'Message': 'Cannot find a revocation for that contact ID'
        }, 
        status=404
    )


@login_required
@permission_required('standingsrequests.affect_standings')
def view_active_requests(request):
    return render(
        request, 'standingsrequests/requests.html', {'app_title': __title__}
    )


@login_required
@permission_required('standingsrequests.affect_standings')
def view_active_requests_json(request):
    
    requests_qs = StandingsRequest.objects.all().order_by('requestDate')
    response = list()
    # pre cache names in bulk
    entity_ids = [r.contactID for r in requests_qs]
    for p in requests_qs:
        try:
            assoc = CharacterAssociation.objects.get(character_id=p.contactID)
            if assoc.corporation_id is not None:
                entity_ids.append(assoc.corporation_id)
            if assoc.alliance_id is not None:
                entity_ids.append(assoc.alliance_id)
        except CharacterAssociation.DoesNotExist:
            pass
    EveNameCache.get_names(entity_ids)
    for r in requests_qs:
        # Dont forget that contact requests aren't strictly ALWAYS pilots 
        # (at least can potentially be corps/alliances)
        state = ''
        if r.user.profile.state:
            state = r.user.profile.state.name

        main = r.user.profile.main_character
        pilot = None
        corp = None
        if PilotStanding.is_pilot(r.contactType):
            pilot = EveCharacter.objects.get_character_by_id(r.contactID)
            if not pilot:
                pilot = EveCharacterHelper(r.contactID)

        elif CorpStanding.is_corp(r.contactType):
            corp = EveCorporation.get_corp_by_id(r.contactID)

        contact_name = pilot.character_name if pilot \
            else corp.corporation_name if corp \
            else None
        corporation_id = pilot.corporation_id if pilot \
            else corp.corporation_id if corp \
            else None
        corporation_name = pilot.corporation_name if pilot \
            else corp.corporation_name if corp \
            else None
        corporation_ticker = pilot.corporation_ticker if pilot \
            else corp.ticker if corp \
            else None
        has_scopes = (
            StandingsManager.has_required_scopes_for_request(pilot) if pilot 
            else StandingsManager.all_corp_apis_recorded(
                corp.corporation_id, r.user
            ) if corp 
            else False
        )
        response.append({
            'contact_id': r.contactID,
            'contact_name': contact_name,
            'corporation_id': corporation_id,
            'corporation_name': corporation_name,
            'corporation_ticker': corporation_ticker,
            'alliance_id': pilot.alliance_id if pilot else None,
            'alliance_name': pilot.alliance_name if pilot else None,
            'has_scopes': has_scopes,
            'state': state,
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
    char_name = EveNameCache.get_name(STANDINGS_API_CHARID)    
    if token.character_id == STANDINGS_API_CHARID:
        messages_plus.success(
            request, 
            _(
                'Successfully setup alliance token for configured character %s'
            ) % char_name
        )
    else:        
        messages_plus.error(
            request, 
            _(
                'Failed to setup alliance token for configured character '
                '%(char_name)s (id:%(standings_api_char_id)s). '
                'Instead got token for different character: '
                '%(token_char_name)s (id:%(token_char_id)s)'
            ) % {
                'char_name': char_name,
                'standings_api_char_id': STANDINGS_API_CHARID,
                'token_char_name': EveNameCache.get_name(token.character_id),
                'token_char_id': token.character_id,
            }
        )        
    return redirect('standingsrequests:index')


@login_required
@permission_required('standingsrequests.request_standings')
@token_required_by_state(new=False)
def view_requester_add_scopes(request, token):            
    messages_plus.success(
        request,
        _(
            'Successfully added token with required scopes for %(char_name)s'
        ) % {'char_name': EveNameCache.get_name(token.character_id)}
    )    
    return redirect('standingsrequests:index')
