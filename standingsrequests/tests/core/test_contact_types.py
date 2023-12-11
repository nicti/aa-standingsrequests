from django.test import TestCase

from standingsrequests.core.contact_types import ContactTypeId
from standingsrequests.tests.testdata.entity_type_ids import (
    CHARACTER_TYPE_ID,
    CORPORATION_TYPE_ID,
)


class TestContactType(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(ContactTypeId.character_id(), CHARACTER_TYPE_ID)

    def test_is_character(self):
        self.assertTrue(ContactTypeId(CHARACTER_TYPE_ID).is_character)
        self.assertFalse(ContactTypeId(CORPORATION_TYPE_ID).is_character)

    def test_get_contact_type_2(self):
        self.assertEqual(ContactTypeId.CORPORATION, CORPORATION_TYPE_ID)

    def test_is_corporation(self):
        self.assertFalse(ContactTypeId(CHARACTER_TYPE_ID).is_corporation)
        self.assertTrue(ContactTypeId(CORPORATION_TYPE_ID).is_corporation)
