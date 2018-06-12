# Bootstrap line for debugging, dont copy this
from allianceauth.settings.local import *

# Add everything below this comment to your settings.py
# This is not a replacement for your existing settings.py

# id of character to use for updating alliance contacts
STANDINGS_API_CHARID = ''
MEMBER_STATES = ['Member',]

# CELERY tasks
if 'standings-requests' in INSTALLED_APPS:
    CELERYBEAT_SCHEDULE['standings_requests_standings_update'] = {
        'task': 'standings_requests.standings_update',
        'schedule': crontab(minute='*/30'),
    }
    CELERYBEAT_SCHEDULE['standings_requests_validate_standings_requests'] = {
        'task': 'standings_requests.validate_standings_requests',
        'schedule': crontab(hour='*/6'),
    }
    CELERYBEAT_SCHEDULE['standings_requests.update_associations_auth'] = {
        'task': 'standings_requests.update_associations_auth',
        'schedule': crontab(hour='*/12'),
    }
    CELERYBEAT_SCHEDULE['standings_requests_update_associations_api'] = {
        'task': 'standings_requests.update_associations_api',
        'schedule': crontab(hour='*/12', minute='30'),
    }
    CELERYBEAT_SCHEDULE['standings_requests_purge_stale_data'] = {
        'task': 'standings_requests.purge_stale_data',
        'schedule': crontab(hour='*/24'),
    }
