from django.urls import path

from . import views

app_name = "standingsrequests"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("create_requests", views.create_requests, name="create_requests"),
    path("request_characters", views.request_characters, name="request_characters"),
    path(
        "request_corporations", views.request_corporations, name="request_corporations"
    ),
    path(
        "request_character_standing/<int:character_id>/",
        views.request_character_standing,
        name="request_character_standing",
    ),
    path(
        "remove_character_standing/<int:character_id>/",
        views.remove_character_standing,
        name="remove_character_standing",
    ),
    path(
        "request_corp_standing/<int:corporation_id>/",
        views.request_corp_standing,
        name="request_corp_standing",
    ),
    path(
        "remove_corp_standing/<int:corporation_id>/",
        views.remove_corp_standing,
        name="remove_corp_standing",
    ),
    path("view/pilots/", views.view_pilots_standings, name="view_pilots"),
    path(
        "view/pilots/json/", views.view_pilots_standings_json, name="view_pilots_json"
    ),
    path(
        "view/pilots/download/",
        views.download_pilot_standings,
        name="download_pilots",
    ),
    path("view/corps/", views.view_groups_standings, name="view_groups"),
    path("view/corps/json", views.view_groups_standings_json, name="view_groups_json"),
    path("manage/", views.manage_standings, name="manage"),
    path("manage/requests/", views.manage_requests_list, name="manage_requests_list"),
    # Should always follow the path of the GET path above
    path(
        "manage/requests/<int:contact_id>/",
        views.manage_requests_write,
        name="manage_requests_write",
    ),
    path(
        "manage/revocations/",
        views.manage_revocations_list,
        name="manage_revocations_list",
    ),
    path(
        "manage/revocations/<int:contact_id>/",
        views.manage_revocations_write,
        name="manage_revocations_write",
    ),
    path("view/requests/", views.view_active_requests, name="view_requests"),
    path("view/requests/json/", views.view_requests_json, name="view_requests_json"),
    path("manage/setuptoken/", views.view_auth_page, name="view_auth_page"),
    path(
        "requester_add_scopes/",
        views.view_requester_add_scopes,
        name="view_requester_add_scopes",
    ),
    path(
        "admin_changeset_update_now/",
        views.admin_changeset_update_now,
        name="admin_changeset_update_now",
    ),
]
