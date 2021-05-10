from __future__ import unicode_literals

from django.conf.urls import include, url

from . import views

app_name = "standingsrequests"

local_urlpatterns = [
    url(r"^$", views.index_view, name="index"),
    url(r"^create_requests", views.create_requests, name="create_requests"),
    url(r"^request_characters$", views.request_characters, name="request_characters"),
    url(
        r"^request_corporations$",
        views.request_corporations,
        name="request_corporations",
    ),
    url(
        r"^request_pilot_standing/(?P<character_id>\d+)/",
        views.request_pilot_standing,
        name="request_pilot_standing",
    ),
    url(
        r"^remove_pilot_standing/(?P<character_id>\d+)/",
        views.remove_pilot_standing,
        name="remove_pilot_standing",
    ),
    url(
        r"^request_corp_standing/(?P<corporation_id>\d+)/",
        views.request_corp_standing,
        name="request_corp_standing",
    ),
    url(
        r"^remove_corp_standing/(?P<corporation_id>\d+)/",
        views.remove_corp_standing,
        name="remove_corp_standing",
    ),
    url(r"^view/pilots/$", views.view_pilots_standings, name="view_pilots"),
    url(
        r"^view/pilots/json/$",
        views.view_pilots_standings_json,
        name="view_pilots_json",
    ),
    url(
        r"^view/pilots/download/$",
        views.download_pilot_standings,
        name="download_pilots",
    ),
    url(r"^view/corps/$", views.view_groups_standings, name="view_groups"),
    url(
        r"^view/corps/json$", views.view_groups_standings_json, name="view_groups_json"
    ),
    url(r"^manage/$", views.manage_standings, name="manage"),
    url(
        r"^manage/requests/$",
        views.manage_get_requests_json,
        name="manage_get_requests_json",
    ),
    # Should always follow the path of the GET path above
    url(
        r"^manage/requests/(?P<contact_id>\d+)/$",
        views.manage_requests_write,
        name="manage_requests_write",
    ),
    url(
        r"^manage/revocations/$",
        views.manage_get_revocations_json,
        name="manage_get_revocations_json",
    ),
    url(
        r"^manage/revocations/(?P<contact_id>\d+)/$",
        views.manage_revocations_write,
        name="manage_revocations_write",
    ),
    url(r"^view/requests/$", views.view_active_requests, name="view_requests"),
    url(
        r"^view/requests/json/$",
        views.view_requests_json,
        name="view_requests_json",
    ),
    url(r"^manage/setuptoken/$", views.view_auth_page, name="view_auth_page"),
    url(
        r"^requester_add_scopes/$",
        views.view_requester_add_scopes,
        name="view_requester_add_scopes",
    ),
]

urlpatterns = [
    url(r"^standingsrequests/", include((local_urlpatterns, "standingsrequests"))),
]
