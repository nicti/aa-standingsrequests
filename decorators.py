import logging
from django.conf import settings
from functools import wraps
from django.utils.decorators import available_attrs
from esi.decorators import _check_callback
from esi.models import Token
from .managers.standings import StandingsManager


logger = logging.getLogger(__name__)

def token_required_by_state(new=False):
    """
    Decorator for views which supplies a single, user-selected token for the view to process.
    Same parameters as tokens_required.
    """

    def decorator(view_func):
        @wraps(view_func, assigned=available_attrs(view_func))
        def _wrapped_view(request, *args, **kwargs):
            scopes = ''
            if request.user.profile.state is not None:
                scopes = ' '.join(
                    StandingsManager.get_required_scopes_for_state(
                        request.user.profile.state.name)
                    )

            # if we're coming back from SSO for a new token, return it
            token = _check_callback(request)
            if token and new:
                logger.debug("Got new token from {0} session {1}. Returning to view.".format(request.user, request.session.session_key[:5]))
                return view_func(request, token, *args, **kwargs)

            # if we're selecting a token, return it
            if request.method == 'POST':
                if request.POST.get("_add", False):
                    logger.debug("{0} has selected to add new token. Redirecting to SSO.".format(request.user))
                    # user has selected to add a new token
                    from esi.views import sso_redirect
                    return sso_redirect(request, scopes=scopes)

                token_pk = request.POST.get('_token', None)
                if token_pk:
                    logger.debug("{0} has selected token {1}".format(request.user, token_pk))
                    try:
                        token = Token.objects.get(pk=token_pk)
                        # ensure token belongs to this user and has required scopes
                        if ((token.user and token.user == request.user) or not token.user) and Token.objects.filter(
                                pk=token_pk).require_scopes(scopes).require_valid().exists():
                            logger.debug("Selected token fulfills requirements of view. Returning.")
                            return view_func(request, token, *args, **kwargs)
                    except Token.DoesNotExist:
                        logger.debug("Token {0} not found.".format(token_pk))
                        pass

            if not new:
                # present the user with token choices
                tokens = Token.objects.filter(user__pk=request.user.pk).require_scopes(scopes).require_valid()
                if tokens.exists():
                    logger.debug("Returning list of available tokens for {0}.".format(request.user))
                    from esi.views import select_token
                    return select_token(request, scopes=scopes, new=new)
                else:
                    logger.debug("No tokens found for {0} session {1} with scopes {2}".format(request.user, request.session.session_key[:5], scopes))

            # prompt the user to add a new token
            logger.debug("Redirecting {0} session {1} to SSO.".format(request.user, request.session.session_key[:5]))
            from esi.views import sso_redirect
            return sso_redirect(request, scopes=scopes)

        return _wrapped_view

    return decorator
