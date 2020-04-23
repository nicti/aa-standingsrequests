from django.db import models

##
# QuerySet helpers for overriding StandingsRequest.objects.delete()
##


class StandingsRequestQuerySet(models.query.QuerySet):
    def delete(self):
        for o in self:
            o.delete()


class StandingsRequestManager(models.Manager):
    def get_queryset(self):
        return StandingsRequestQuerySet(self.model, using=self._db)

    def get_query_set(self):
        return self.get_queryset()

    def delete_for_user(self, user):
        to_delete = self.filter(user=user)

        # We have to delete each one manually in order to trigger the logic
        for d in to_delete:
            d.delete()
