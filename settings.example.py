# Bootstrap line for debugging, dont copy this
from allianceauth.settings.local import *

# Add everything below this comment to your settings.py
# This is not a replacement for your existing settings.py

# id of character to use for updating alliance contacts
STANDINGS_API_CHARID = 1234
STR_CORP_IDS = ['CORP1ID', 'CORP2ID', '...']
STR_ALLIANCE_IDS = ['YOUR_ALLIANCE_ID', '...']

# This is a map, where the key is the State the user is in
# and the value is a list of required scopes to check
SR_REQUIRED_SCOPES = {
    'Member': ['publicData'],
    'Blue': [],
    '': []  # no state
}

# CELERY tasks
if 'standingsrequests' in INSTALLED_APPS:
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
