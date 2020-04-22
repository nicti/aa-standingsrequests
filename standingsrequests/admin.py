from django.contrib import admin

from .models import (
    StandingsRequest, 
    StandingsRevocation, 
    EveNameCache, 
    PilotStanding, 
    CorpStanding
)


class AbstractStandingsRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        '_contact_type_str', 
        '_contact_name',         
        '_user', 
        'requestDate', 
        'actionBy', 
        'actionDate', 
        'effective', 
        'effectiveDate'
    )
    list_filter = ('effective',)
    ordering = ('-id',)
    
    def _contact_name(self, obj):
        return EveNameCache.get_name(obj.contactID)

    def _contact_type_str(self, obj):
        if obj.contactType in PilotStanding.contactTypes:
            return 'Character'
        elif obj.contactType in CorpStanding.contactTypes:
            return 'Corporation'
        else:
            return '(undefined)'
    _contact_type_str.short_description = 'contact type'

    def _user(self, obj):
        if hasattr(obj, 'user'):
            return obj.user
        else:
            return None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(StandingsRequest)
class StandingsRequestAdmin(AbstractStandingsRequestAdmin):
    pass


@admin.register(StandingsRevocation)
class StandingsRevocationAdmin(AbstractStandingsRequestAdmin):
    pass


@admin.register(EveNameCache)
class EveNameCacheAdmin(admin.ModelAdmin):
    list_display = ('entityID', 'name', 'updated')
    
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

