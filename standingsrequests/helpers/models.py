from typing import Set

from django.contrib.auth.models import User
from django.db import models
from eveuniverse.models import EveEntity


class FrozenModelMixin:
    """Objects of this model type can only be created, but not updated."""

    def save(self: models.Model, *args, **kwargs) -> None:
        if self.pk is None:
            super().save(*args, **kwargs)
        else:
            raise RuntimeError("No updates allowed for this object.")


class GatherEntityIdsMixin:
    """Add ability to gather all entity IDs from foreign keys of an object."""

    def entity_ids(self: models.Model) -> Set[int]:
        """Return all entity IDs in this object and ignore fields, which are None.

        The relevant fields are automatically detected.
        """
        relevant_fields = (
            field
            for field in self._meta.get_fields()
            if field.is_relation and field.related_model is EveEntity
        )
        values = (field.value_from_object(self) for field in relevant_fields)
        result = {value for value in values if value is not None}
        return result


def get_or_create_sentinel_user() -> User:
    """Get or create the sentinel user."""
    return User.objects.get_or_create(username="deleted")[0]
