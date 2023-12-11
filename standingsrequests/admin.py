from typing import Optional

from django.contrib import admin
from django.db.models import Count
from eveuniverse.models import EveEntity

from .models import (
    AbstractStandingsRequest,
    ContactSet,
    RequestLogEntry,
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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display
    def _contact_name(self, obj: AbstractStandingsRequest):
        return EveEntity.objects.resolve_name(obj.contact_id)

    @admin.display(description="contact type")
    def _contact_type_str(self, obj: AbstractStandingsRequest):
        if obj.is_character:
            return "Character"

        if obj.is_corporation:
            return "Corporation"

        return "(undefined)"

    def _user(self, obj: AbstractStandingsRequest):
        try:
            return obj.user
        except AttributeError:
            return None


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

    @admin.display
    def _contacts_count(self, obj):
        return obj.contacts_count


@admin.register(RequestLogEntry)
class RequestLogEntryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "request_type",
        "_requested_for",
        "_requested_by",
        "requested_at",
        "_reason",
        "action",
        "_action_by",
    )
    list_display_links = None
    list_filter = (
        "request_type",
        ("action_by", admin.RelatedOnlyFieldListFilter),
        ("requested_by", admin.RelatedOnlyFieldListFilter),
        "created_at",
        "reason",
    )
    ordering = ("-created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "action_by__character",
            "action_by__corporation",
            "requested_by__character",
            "requested_by__corporation",
            "requested_for__character",
            "requested_for__corporation",
        )

    def has_change_permission(self, *args, **kwargs):
        return False

    def has_add_permission(self, *args, **kwargs):
        return False

    def has_delete_permission(self, *args, **kwargs) -> bool:
        return False

    @admin.display(ordering="action_by")
    def _action_by(self, obj: RequestLogEntry) -> str:
        return "SYSTEM" if obj.action_by is None else obj.action_by.html()

    @admin.display(ordering="requested_by")
    def _requested_by(self, obj: RequestLogEntry) -> str:
        return obj.requested_by.html()

    @admin.display(ordering="requested_for")
    def _requested_for(self, obj: RequestLogEntry) -> str:
        return obj.requested_for.html()

    @admin.display(ordering="reason")
    def _reason(self, obj: RequestLogEntry) -> Optional[str]:
        reason_obj = StandingRequest.Reason(obj.reason)
        return None if reason_obj is StandingRequest.Reason.NONE else reason_obj.label
