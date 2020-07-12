from django.core.cache import cache
from django.test import TestCase

from ..helpers.viewcache import DataViewCache
from ..utils import set_test_logger


MODULE_PATH = "standingsrequests.helpers.viewcache"
logger = set_test_logger(MODULE_PATH, __file__)


class TestDataViewCache(TestCase):

    my_data = ["alpha", "bravo", "charlie"]

    @staticmethod
    def create_data():
        return TestDataViewCache.my_data

    def test_can_create_and_delete(self):
        my_cache = DataViewCache("test_view")
        result = my_cache.get_or_set(self.create_data)
        self.assertListEqual(result, self.my_data)
        self.assertIsNotNone(cache.get(my_cache._cache_key()))

        my_cache.clear()
        self.assertIsNone(cache.get(my_cache._cache_key()))
