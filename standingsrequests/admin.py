from django.contrib import admin
from django.db.models import Count
from eveuniverse.models import EveEntity

from .core import ContactType
from .models import ContactSet, StandingRequest, StandingRevocation


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
        return EveEntity.objects.resolve_name(obj.contact_id)

    def _contact_type_str(self, obj):
        if obj.contact_type_id in ContactType.character_ids:
            return "Character"
        elif obj.contact_type_id in ContactType.corporation_ids:
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


@admin.register(ContactSet)
class ContactSetAdmin(admin.ModelAdmin):
    change_list_template = "admin/standingsrequests/contactset/change_list.html"
    list_display = ("date", "_contacts_count")
    list_display_links = None
    ordering = ("-date",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(contacts_count=Count("contacts"))

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def _contacts_count(self, obj):
        return obj.contacts_count
