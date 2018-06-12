from __future__ import unicode_literals

from .urls import urlpatterns
from .models import StandingsRequest

import logging
from allianceauth import hooks
from allianceauth.services.hooks import ServicesHook, MenuItemHook

logger = logging.getLogger(__name__)


class StandingsRequestService(ServicesHook):
    def __init__(self):
        ServicesHook.__init__(self)
        self.name = 'standingsrequests'
        self.urlpatterns = urlpatterns
        self.access_perm = 'standingsrequests.request_standings'

    def delete_user(self, user, notify_user=False):
        logger.debug('Deleting user {} standings'.format(user))
        StandingsRequest.objects.delete_for_user(user)

    def validate_user(self, user):
        logger.debug('Validating user {} standings'.format(user))
        if not self.service_active_for_user(user):
            self.delete_user(user)

    def service_active_for_user(self, user):
        return user.has_perm(self.access_perm)


@hooks.register('services_hook')
def register_service():
    return StandingsRequestService()


class StandingsRequestMenuItem(MenuItemHook):
    def __init__(self):
        MenuItemHook.__init__(self,
                              'Standings Requests',
                              'fa fa-plus-square fa-fw grayiconecolor',
                              'standings-requests:index')

    def render(self, request):
        if request.user.has_perm('standingsrequests.request_standings'):
            return MenuItemHook.render(self, request)
        return ''


@hooks.register('menu_item_hook')
def register_menu():
    return StandingsRequestMenuItem()
