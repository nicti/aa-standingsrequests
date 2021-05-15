# flake8: noqa

from .views_1 import (
    admin_changeset_update_now,
    create_requests,
    index_view,
    remove_character_standing,
    remove_corp_standing,
    request_character_standing,
    request_characters,
    request_corp_standing,
    request_corporations,
    view_auth_page,
    view_requester_add_scopes,
)
from .views_2 import (
    _compose_standing_requests_data,
    download_pilot_standings,
    manage_get_requests_json,
    manage_get_revocations_json,
    manage_requests_write,
    manage_revocations_write,
    manage_standings,
    view_active_requests,
    view_groups_standings,
    view_groups_standings_json,
    view_pilots_standings,
    view_pilots_standings_json,
    view_requests_json,
)
