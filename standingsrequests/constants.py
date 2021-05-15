from django.db.models import TextChoices


class OperationMode(TextChoices):
    ALLIANCE = "alliance"
    CORPORATON = "corporation"
