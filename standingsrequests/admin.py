from django.contrib import admin

from .models import (
    CharacterContact,
    CorporationContact,
    EveEntity,
    StandingRequest,
    StandingRevocation,
)


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
    list_select_related = True
    ordering = ("-id",)

    def _contact_name(self, obj):
        return EveEntity.objects.get_name(obj.contact_id)

    def _contact_type_str(self, obj):
        if obj.contact_type_id in CharacterContact.contact_type_ids:
            return "Character"
        elif obj.contact_type_id in CorporationContact.contact_type_ids:
            return "Corporation"
        else:
            return "(undefined)"

    _contact_type_str.short_description = "contact type"

    def _user(self, obj):
        try:
            return obj.user
        except AttributeError:
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
