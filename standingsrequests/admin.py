from django.contrib import admin

from .models import (
    ContactSet,
    StandingRequest,
    StandingRevocation,
    EveEntity,
    CharacterContact,
    CorporationContact,
)
from .tasks import standings_update


class AbstractStandingsRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "_contact_type_str",
        "_contact_name",
        "_user",
        "request_date",
        "action_by",
        "action_date",
        "is_effective",
        "effective_date",
    )
    list_filter = ("is_effective",)
    ordering = ("-id",)

    def _contact_name(self, obj):
        return EveEntity.objects.get_name(obj.contact_id)

    def _contact_type_str(self, obj):
        if obj.contact_type_id in CharacterContact.contact_types:
            return "Character"
        elif obj.contact_type_id in CorporationContact.contact_types:
            return "Corporation"
        else:
            return "(undefined)"

    _contact_type_str.short_description = "contact type"

    def _user(self, obj):
        if hasattr(obj, "user"):
            return obj.user
        else:
            return None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(StandingRequest)
class StandingsRequestAdmin(AbstractStandingsRequestAdmin):
    pass


@admin.register(StandingRevocation)
class StandingsRevocationAdmin(AbstractStandingsRequestAdmin):
    pass


@admin.register(EveEntity)
class EveEntityAdmin(admin.ModelAdmin):
    list_display = ("entity_id", "name", "category", "updated")
    list_filter = ("category",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ContactSet)
class ContactSetAdmin(admin.ModelAdmin):
    list_display = ("date",)

    actions = ("start_update",)

    def start_update(self, request, queryset):
        standings_update.delay()
        self.message_user(request, "Fetching new contact set / standings...")

    start_update.short_description = "Fetch new contact set / standings"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
