"""helper for managing view caches accross modules"""

from django.core.cache import cache


class DataViewCache:
    """class for managing server side caching of data views"""

    CACHE_KEY_BASE = "STANDINGSREQUESTS_VIEW_CACHE"
    CACHE_DURATION = 600

    def __init__(self, view_name: str) -> None:
        self._view_name = str(view_name)

    @property
    def view_name(self) -> str:
        return self._view_name

    def get_or_set(self, func):
        return cache.get_or_set(self._cache_key(), func, timeout=self.CACHE_DURATION)

    def clear(self) -> None:
        cache.delete(self._cache_key())

    def _cache_key(self) -> str:
        return f"{self.CACHE_KEY_BASE}_{self.view_name}"


cache_view_pilots_json = DataViewCache("view_pilots_json")

cache_view_groups_json = DataViewCache("view_groups_json")
