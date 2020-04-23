from django.conf import settings
from .utils import clean_setting


# id of character to use for updating alliance contacts - needs to be set
STANDINGS_API_CHARID = \
    clean_setting('STANDINGS_API_CHARID', None, required_type=int)

STR_ALLIANCE_IDS = \
    clean_setting('STR_ALLIANCE_IDS', None, required_type=list)

STR_CORP_IDS = \
    clean_setting('STR_CORP_IDS', None, required_type=list)

# This is a map, where the key is the State the user is in
# and the value is a list of required scopes to check
SR_REQUIRED_SCOPES = getattr(
    settings, 
    'SR_REQUIRED_SCOPES', 
    {
        'Member': ['publicData'],
        'Blue': [],
        '': []  # no state
    }
)

# switch to enable/disable ability to request standings for corporations
SR_CORPORATIONS_ENABLED = \
    clean_setting('SR_CORPORATIONS_ENABLED', True)


# Standing data will be considered stale and removed from the local 
# database after the configured hours.
# The latest standings data will never be purged, no matter how old it is
SR_STANDINGS_STALE_HOURS = \
    clean_setting('SR_STANDINGS_STALE_HOURS', 48)

# Standings revocations will be considered stale and removed 
# from the local database after the configured days
SR_REVOCATIONS_STALE_DAYS = \
    clean_setting('SR_REVOCATIONS_STALE_DAYS', 7)
