# Standings Requests

App for managing character standing requests, made for [Alliance Auth](https://gitlab.com/allianceauth/allianceauth).

![release](https://img.shields.io/pypi/v/aa-standingsrequests?label=release) ![python](https://img.shields.io/pypi/pyversions/aa-standingsrequests) ![django](https://img.shields.io/pypi/djversions/aa-standingsrequests?label=django) ![pipeline](https://gitlab.com/basraah/standingsrequests/badges/master/pipeline.svg) ![coverage](https://gitlab.com/basraah/standingsrequests/badges/master/coverage.svg) ![license](https://img.shields.io/badge/license-GPLv3-green)

## Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Installation](#installation)
- [Settings](#settings)
- [Permissions](#permissions)
- [Standings Requirements](#standings-requirements)
- [Manual for Standing Managers](#manual-for-standing-managers)
- [Change Log](CHANGELOG.md)

## Features

- User can requests alliance standings for their characters
- Standing managers can approve / deny standings requests from users
- Automatic verification that approved / revoked standings are added / removed in-game
- When user leaves alliance app will automatically identify and suggest required standing revocations
- Tool for researching all current alliance standing incl. link to their owners

## Screenshots

Here are some example screenshots:

### Requesting standings for a character

![image_1](https://i.imgur.com/zrKCW1D.png)

### Reviewing standings requests

![image_2](https://i.imgur.com/6vCpFm0.png)

## Installation

1. Activate your virtual environment and install this app with: `pip install aa-standingsrequests`

1. Add the scope `esi-alliances.read_contacts.v1` to your Eve Online app

1. Add `'standingsrequests'` to `INSTALLED_APPS` in your Alliance Auth local settings file. Also add the other settings from the [Settings Example](#settings-example) and update the example config for your alliance.

1. Run database migrations: `python manage.py migrate standingsrequests`

1. Copy static files to your webserver: `python manage.py collectstatic`

1. Restart Django and Celery.

1. Open the standingsrequests app in Alliance Auth and add your alliance token

1. Do the initial pull of standings data: `celery -A myauth call standings_requests.standings_update`

1. When that's completed, pull all the name data available locally: `celery -A myauth call standings_requests.update_associations_auth`

1. When *that's* completed, pull the rest of the data from API: `celery -A myauth call standings_requests.update_associations_api`

1. Add permissions to groups where required.

That's it, you should be ready to roll.

**Note on celery commands:** The celery commands will only work correctly if you run them from with your AA project folder (the one that has `manage.py`).

## Settings Example

Here is a complete example of all settings that goes into your local settings file.

```Python
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
```

## Settings

Here is a brief explanation of all available settings:

Name | Description | Default
-- | -- | --
`STANDINGS_API_CHARID` | id of character to use for updating alliance contacts (Mandatory) | N/A
`STR_ALLIANCE_IDS` | id of standing alliances (Mandatory) | N/A
`STR_CORP_IDS` | id of standing corporations (Mandatory, can be []) | N/A
`SR_REQUIRED_SCOPES` | map of required scopes per state (Mandatory, can be [] per state) | N/A
`SR_CORPORATIONS_ENABLED` | switch to enable/disable ability to request standings for corporations |True
`SR_STANDINGS_STALE_HOURS` | Standing data will be considered stale and removed from the local database after the configured hours. The latest standings data will never be purged, no matter how old it is |48
`SR_REVOCATIONS_STALE_DAYS` | Standings revocations will be considered stale and removed from the local database after the configured days | 7

## Permissions

These are all relevant permissions:

Codename | Description
-- | --
`standingsrequests.request_standings` | This is the permission required to request and maintain blue standings without them being revoked. When the user no longer has this permission all of their standings will be revoked.
`standingsrequests.view` | This includes seeing if the user has API keys for that character (but not the API keys themselves) and who the character belongs to. Typically you'll probably only want standings managers to have this.
`standingsrequests.affect_standings` | User can see standings requests and process/approve/reject them.
`standingsrequests.download` | User can download all of the standings data, including main character associations, as a CSV file. Useful if you want to do some extra fancy processing in a spreadsheet or something.

## Standings Requirements

These are the requirements to be able to request and maintain blue standings. If a character or account falls out of these requirement scopes then their standing(s) will be revoked.

Request Type | Requirements
-- | --
Character | • Valid Member-level API key on record. <br>• Users main character is a member of one of the tenant corps.<br>• User has the `request_standings` permissions.
Corporation | • ALL Corporation member API keys recorded in auth.<br>• Users main character is a member of one of the tenant corps.<br>• User has the `request_standings` permission.

## Manual for Standing Managers

Standing managers have the ability to review standings requests on the "Manage Requests" page.

### Standings Requests

Standings Requests are fairly straightforward, there are two options:

#### Reject

Reject the standings request, effectively deleting it. The user will be able to request it again however.

#### Actioned

The requested standing has been actioned/changed in game. The system then expects to see this request become effective within 24 hours. If it does not show up in a standings API pull within 24 hours the actioned flag is removed and it will show up as a standings request again.

Once a standing is actioned it will be maintained as an "effective" standings request. If the standing is removed in game while it is still valid in the system then it will become an active request again.

### Standings Revocations

Standings will show up here in one of two situations:

1. The user has deleted the standings request for that contact, indicating they no longer require the standing.
2. The user is no longer eligible to hold active standings.

Currently it is not indicated which of these two cases (or which automatic revocation case) triggered the standing revocation.

#### Delete

Make sure you fully understand delete before using it, you will usually use one of the other two options instead of delete. When you delete a standings request *it is literally deleted*. The system will no longer attempt to manage this request or verify that it has been revoked etc. *The standing becomes "unmanaged"*.

#### Undo

Turns the standing revocation into a standings request again. Useful if someone got booted from corp or auth temporarily. If they still don't have the requirements met the next time a validation pass happens then it will be turned into a revocation again.

#### Actioned

Same as for Standings Requests. The system will hold the revocation in the background until it sees it removed in game. If the standing has still not been unset (or set to neutral or below) in 24 hours then it will appear as a standings revocation again.
