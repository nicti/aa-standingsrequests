import enum

from django.db.models import TextChoices

DATETIME_FORMAT_HTML = "Y-m-d H:i"
DATETIME_FORMAT_PY = "%Y-%m-%d %H:%M"


class OperationMode(TextChoices):
    ALLIANCE = "alliance"
    CORPORATION = "corporation"


class CreateCharacterRequestResult(enum.IntEnum):
    """A result from StandingsRequests.objects.create_character_request."""

    NO_ERROR = enum.auto()
    USER_IS_NOT_OWNER = enum.auto()
    CHARACTER_HAS_REQUEST = enum.auto()
    CHARACTER_IS_MISSING_SCOPES = enum.auto()
    UNKNOWN_ERROR = enum.auto()


DEFAULT_IMAGE_SIZE = 32
