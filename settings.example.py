# Bootstrap line for debugging, dont copy this
from alliance_auth.settings import *

# Add everything below this comment to your settings.py
# This is not a replacement for your existing settings.py

###############################################
# Standings Tool configuration
###############################################
# Access Mask: 16
# You need a character API key from any
# character in the alliance to pull standings
# for.
# STANDINGS_API_KEY: API key
# STANDINGS_API_VCODE: API vCode
# STANDINGS_API_CHARID: Character ID on the key
# to use standings from
###############################################
STANDINGS_API_KEY = ''
STANDINGS_API_VCODE = ''
STANDINGS_API_CHARID = ''


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
