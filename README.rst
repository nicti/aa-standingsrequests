==================
Standings Requests
==================

Quick start
-----------

1. Add ``standingsrequests`` to your ``INSTALLED_APPS`` in your Django config file. Add the other settings from the ``settings.example.py`` file.
2. Run database migrations, ``python manage.py migrate standingsrequests``.
3. Restart Django and Celery.
4. Do the initial pull of standings data. ``celery -A alliance_auth call standings_requests.standings_update``
5. When that's completed, pull all the name data available locally. ``celery -A alliance_auth call standings_requests.update_associations_auth``
6. When *that's* completed, pull the rest of the data from API. ``celery -A alliance_auth call standings_requests.update_associations_api``
7. Add permissions to groups where required.

That's it, you should be ready to roll


Permissions
-----------

``standingsrequests.request_standings | User can request standings`` User can request standings. This is the permission required to request and maintain blue standings without them being revoked. When the user no longer has this permission all of their standings will be revoked.

``standingsrequests.view | User can view standings`` This includes seeing if the user has API keys for that character (but not the API keys themselves) and who the character belongs to. Typically you'll probably only want standings managers to have this.

``standingsrequests.affect_standings | User can process standings requests`` User can see standings requests and process/approve/reject them.

``standingsrequests.download | User can export standings to a CSV file`` User can download all of the standings data, including main character associations, as a CSV file. Useful if you want to do some extra fancy processing in a spreadsheet or something.

Standings Requirements
----------------------
These are the requirements to be able to request and maintain blue standings. If a character or account falls out of these requirement scopes then their standing(s) will be revoked.

Pilot
#####
Valid Member-level API key on record.
Users main character is a member of one of the tenant corps.
User has the ``request_standings`` permissions.

Corp
####
ALL Corporation member API keys recorded in auth.
Users main character is a member of one of the tenant corps.
User has the ``request_standings`` permission.

Manager Actions
---------------

Standings Requests
##################

Standings Requests are fairly straightforward, there are two options:

**Reject**
Reject the standings request, effectively deleting it. The user will be able to request it again however.

**Actioned**
The requested standing has been actioned/changed in game. The system then expects to see this request become effective within 24 hours. If it does not show up in a standings API pull within 24 hours the actioned flag is removed and it will show up as a standings request again.

Once a standing is actioned it will be maintained as an "effective" standings request. If the standing is removed in game while it is still valid in the system then it will become an active request again.

Standings Revocations
#####################

Standings will show up here in one of two situations:
1. The user has deleted the standings request for that contact, indicating they no longer require the standing.
2. The user is no longer eligible to hold active standings.

Currently it is not indicated which of these two cases (or which automatic revocation case) triggered the standing revocation.

**Delete**
Make sure you fully understand delete before using it, you will usually use one of the other two options instead of delete. When you delete a standings request *it is literally deleted*. The system will no longer attempt to manage this request or verify that it has been revoked etc. *The standing becomes "unmanaged"*.

**Undo**
Turns the standing revocation into a standings request again. Useful if someone got booted from corp or auth temporarily. If they still don't have the requirements met the next time a validation pass happens then it will be turned into a revocation again.

**Actioned**
Same as for Standings Requests. The system will hold the revocation in the background until it sees it removed in game. If the standing has still not been unset (or set to neutral or below) in 24 hours then it will appear as a standings revocation again.
