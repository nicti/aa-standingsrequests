import logging

from django.utils.translation import gettext_lazy as _
from allianceauth import hooks
from allianceauth.services.hooks import ServicesHook, MenuItemHook

from . import __title__
from .models import StandingsRequest
from .urls import urlpatterns

logger = logging.getLogger(__name__)


class StandingsRequestService(ServicesHook):
    def __init__(self):
        ServicesHook.__init__(self)
        self.name = 'standingsrequests'
        self.urlpatterns = urlpatterns
        self.access_perm = 'standingsrequests.request_standings'

    def delete_user(self, user, notify_user=False):
        logger.debug('Deleting user %s standings', user)
        StandingsRequest.objects.delete_for_user(user)

    def validate_user(self, user):
        logger.debug('Validating user %s standings', user)
        if not self.service_active_for_user(user):
            self.delete_user(user)

    def service_active_for_user(self, user):
        return user.has_perm(self.access_perm)


@hooks.register('services_hook')
def register_service():
    return StandingsRequestService()


class StandingsRequestMenuItem(MenuItemHook):
    def __init__(self):
        MenuItemHook.__init__(
            self,
            _(__title__),
            'fa fa-plus-square fa-fw grayiconecolor',
            'standingsrequests:index'
        )

    def render(self, request):
        if request.user.has_perm('standingsrequests.request_standings'):
            return MenuItemHook.render(self, request)
        return ''


@hooks.register('menu_item_hook')
def register_menu():
    return StandingsRequestMenuItem()
