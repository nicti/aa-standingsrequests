from django.contrib.auth.decorators import login_required, permission_required
from django.db import models
from django.http import JsonResponse
from django.shortcuts import render

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from standingsrequests import __title__
from standingsrequests.core import BaseConfig
from standingsrequests.models import StandingRequest

from ._common import add_common_context, compose_standing_requests_data

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@login_required
@permission_required("standingsrequests.affect_standings")
def view_active_requests(request):
    context = {
        "organization": BaseConfig.standings_source_entity(),
        "requests_count": _standing_requests_to_view().count(),
    }
    return render(
        request, "standingsrequests/requests.html", add_common_context(request, context)
    )


@login_required
@permission_required("standingsrequests.affect_standings")
def view_requests_json(request):

    response_data = compose_standing_requests_data(
        _standing_requests_to_view(), quick_check=True
    )
    return JsonResponse(response_data, safe=False)


def _standing_requests_to_view() -> models.QuerySet:
    return (
        StandingRequest.objects.filter(is_effective=True)
        .select_related("user__profile")
        .order_by("-request_date")
    )
