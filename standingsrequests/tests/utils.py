from app_utils.testing import NoSocketsTestCase


class PartialDictEqualMixin:
    def assertPartialDictEqual(self, d1: dict, d2: dict):
        """Assert that d1 equals d2 for the subset of keys of d1."""
        subset = {k: v for k, v in d1.items() if k in d2}
        self.assertDictEqual(subset, d2)


class NoSocketsTestCasePlus(PartialDictEqualMixin, NoSocketsTestCase):
    pass
