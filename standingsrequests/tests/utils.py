import json

from django.http import JsonResponse

from app_utils.testing import NoSocketsTestCase, response_text


class PartialDictEqualMixin:
    def assertPartialDictEqual(self, d1: dict, d2: dict):
        """Assert that d1 equals d2 for the subset of keys of d1."""
        subset = {k: v for k, v in d1.items() if k in d2}
        self.assertDictEqual(subset, d2)


class NoSocketsTestCasePlus(PartialDictEqualMixin, NoSocketsTestCase):
    pass


def json_response_to_python_2(response: JsonResponse, data_key="data") -> object:
    """Convert JSON response into Python object."""
    data = json.loads(response_text(response))
    return data[data_key]


def json_response_to_dict_2(response: JsonResponse, key="id", data_key="data") -> dict:
    """Convert JSON response into dict by given key."""
    return {x[key]: x for x in json_response_to_python_2(response, data_key)}
