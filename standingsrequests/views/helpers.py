from .. import __title__
from ..constants import DATETIME_FORMAT_HTML
from ..core import BaseConfig
from ..models import StandingRequest, StandingRevocation

DEFAULT_ICON_SIZE = 32


def add_common_context(request, context: dict) -> dict:
    """adds the common context used by all view"""
    new_context = {
        **{
            "app_title": __title__,
            "operation_mode": str(BaseConfig.operation_mode),
            "pending_total_count": (
                StandingRequest.objects.pending_requests().count()
                + StandingRevocation.objects.pending_requests().count()
            ),
            "DATETIME_FORMAT_HTML": DATETIME_FORMAT_HTML,
        },
        **context,
    }
    return new_context
