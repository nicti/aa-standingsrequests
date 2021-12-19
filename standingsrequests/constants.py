from enum import IntEnum

from django.db.models import TextChoices


class OperationMode(TextChoices):
    ALLIANCE = "alliance"
    CORPORATON = "corporation"


class CreateCharacterRequestError(IntEnum):
    NO_ERROR = 0
    USER_IS_NOT_OWNER = 1
    CHARACTER_HAS_REQUEST = 2
    CHARACTER_IS_MISSING_SCOPES = 3
    UNKNOWN_ERROR = 99
