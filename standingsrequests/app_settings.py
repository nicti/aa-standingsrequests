from django.conf import settings

# id of character to use for updating alliance contacts - needs to be set
STANDINGS_API_CHARID = getattr(
    settings, 
    'STANDINGS_API_CHARID', 
    None
)

STR_ALLIANCE_IDS = getattr(
    settings, 
    'STR_ALLIANCE_IDS', 
    None
)

STR_CORP_IDS  = getattr(
    settings, 
    'STR_CORP_IDS', 
    None
)

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
SR_CORPORATIONS_ENABLED = getattr(
    settings, 
    'SR_CORPORATIONS_ENABLED', 
    True
)
