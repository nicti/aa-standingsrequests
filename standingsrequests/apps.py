from django.apps import AppConfig

from . import __title__, __version__


class StandingsRequestsConfig(AppConfig):
    name = "standingsrequests"
    label = "standingsrequests"
    verbose_name = f"{__title__} v{__version__}"

    def ready(self):
        pass
