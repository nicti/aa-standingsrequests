from django.urls import path

from .views import (
    admin,
    character_standings,
    create_requests,
    effective_requests,
    group_standings,
    manage_requests,
)

app_name = "standingsrequests"

urlpatterns = [
    # index
    path("", create_requests.index_view, name="index"),
    # admin
    path(
        "admin_changeset_update_now/",
        admin.admin_changeset_update_now,
        name="admin_changeset_update_now",
    ),
    # create_requests
    path("create_requests", create_requests.create_requests, name="create_requests"),
    path(
        "request_characters",
        create_requests.request_characters,
        name="request_characters",
    ),
    path(
        "request_corporations",
        create_requests.request_corporations,
        name="request_corporations",
    ),
    path(
        "request_character_standing/<int:character_id>/",
        create_requests.request_character_standing,
        name="request_character_standing",
    ),
    path(
        "remove_character_standing/<int:character_id>/",
        create_requests.remove_character_standing,
        name="remove_character_standing",
    ),
    path(
        "request_corp_standing/<int:corporation_id>/",
        create_requests.request_corp_standing,
        name="request_corp_standing",
    ),
    path(
        "remove_corp_standing/<int:corporation_id>/",
        create_requests.remove_corp_standing,
        name="remove_corp_standing",
    ),
    path("manage/setuptoken/", create_requests.view_auth_page, name="view_auth_page"),
    path(
        "requester_add_scopes/",
        create_requests.view_requester_add_scopes,
        name="view_requester_add_scopes",
    ),
    # character standings
    path("view/pilots/", character_standings.view_pilots_standings, name="view_pilots"),
    path(
        "view/pilots/json/",
        character_standings.view_pilots_standings_json,
        name="view_pilots_json",
    ),
    path(
        "view/pilots/download/",
        character_standings.download_pilot_standings,
        name="download_pilots",
    ),
    # effective requests
    path(
        "view/requests/",
        effective_requests.effective_requests,
        name="effective_requests",
    ),
    path(
        "view/requests/list/",
        effective_requests.effective_requests_list,
        name="effective_requests_list",
    ),
    path(
        "view/requests/list2/",
        effective_requests.EffectiveRequestListView.as_view(),
        name="effective_requests_list_2",
    ),
    # group standings
    path("view/groups/", group_standings.view_groups_standings, name="view_groups"),
    path(
        "view/groups/corporations_json",
        group_standings.view_corporation_standings_json,
        name="view_corporation_standings_json",
    ),
    path(
        "view/groups/alliances_json",
        group_standings.view_alliance_standings_json,
        name="view_alliance_standings_json",
    ),
    # manage requests
    path("manage/", manage_requests.manage_standings, name="manage"),
    path(
        "manage/requests/",
        manage_requests.manage_requests_list,
        name="manage_requests_list",
    ),  # Should always follow the path of the GET path above
    path(
        "manage/requests/<int:contact_id>/",
        manage_requests.manage_requests_write,
        name="manage_requests_write",
    ),
    path(
        "manage/revocations/",
        manage_requests.manage_revocations_list,
        name="manage_revocations_list",
    ),
    path(
        "manage/revocations/<int:contact_id>/",
        manage_requests.manage_revocations_write,
        name="manage_revocations_write",
    ),
]
