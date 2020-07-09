"""helper for managing view caches accross modules"""

from django.core.cache import cache

_CACHE_KEY = "STANDINGSREQUESTS_KEY_CHARACTER_STANDINGS_DATA"


def cache_get_or_set_character_standings_data(func) -> object:
    return cache.get_or_set(_CACHE_KEY, func, timeout=600)


def cache_clear_character_standings_data() -> None:
    cache.delete(_CACHE_KEY)
