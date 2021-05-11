from django.test import TestCase

from ..core import ContactType
from .entity_type_ids import (
    ALLIANCE_TYPE_ID,
    CHARACTER_ACHURA_TYPE_ID,
    CHARACTER_BRUTOR_TYPE_ID,
    CHARACTER_CIVRE_TYPE_ID,
    CHARACTER_DETEIS_TYPE_ID,
    CHARACTER_DRIFTER_TYPE_ID,
    CHARACTER_GALLENTE_TYPE_ID,
    CHARACTER_INTAKI_TYPE_ID,
    CHARACTER_JIN_MEI_TYPE_ID,
    CHARACTER_KHANID_TYPE_ID,
    CHARACTER_MODIFIER_TYPE_ID,
    CHARACTER_NI_KUNNI_TYPE_ID,
    CHARACTER_SEBIESTOR_TYPE_ID,
    CHARACTER_STATIC_TYPE_ID,
    CHARACTER_TYPE_ID,
    CHARACTER_VHEROKIOR_TYPE_ID,
    CORPORATION_TYPE_ID,
)


class TestContactType(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(ContactType.character_id, CHARACTER_TYPE_ID)

    def test_is_pilot(self):
        self.assertTrue(ContactType.is_character(CHARACTER_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_NI_KUNNI_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_CIVRE_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_DETEIS_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_GALLENTE_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_INTAKI_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_SEBIESTOR_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_BRUTOR_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_STATIC_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_MODIFIER_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_ACHURA_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_JIN_MEI_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_KHANID_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_VHEROKIOR_TYPE_ID))
        self.assertTrue(ContactType.is_character(CHARACTER_DRIFTER_TYPE_ID))

        self.assertFalse(ContactType.is_character(CORPORATION_TYPE_ID))
        self.assertFalse(ContactType.is_character(ALLIANCE_TYPE_ID))
        self.assertFalse(ContactType.is_character(1))
        self.assertFalse(ContactType.is_character(None))
        self.assertFalse(ContactType.is_character(-1))
        self.assertFalse(ContactType.is_character(0))

    def test_get_contact_type_2(self):
        self.assertEqual(ContactType.corporation_id, CORPORATION_TYPE_ID)

    def test_is_corporation(self):
        self.assertTrue(ContactType.is_corporation(CORPORATION_TYPE_ID))
        self.assertFalse(ContactType.is_corporation(CHARACTER_TYPE_ID))
        self.assertFalse(ContactType.is_corporation(ALLIANCE_TYPE_ID))
        self.assertFalse(ContactType.is_corporation(1))
        self.assertFalse(ContactType.is_corporation(None))
        self.assertFalse(ContactType.is_corporation(-1))
        self.assertFalse(ContactType.is_corporation(0))

    def test_get_contact_type_3(self):
        self.assertEqual(ContactType.alliance_id, ALLIANCE_TYPE_ID)

    def test_is_alliance(self):
        self.assertTrue(ContactType.is_alliance(ALLIANCE_TYPE_ID))
        self.assertFalse(ContactType.is_alliance(CHARACTER_TYPE_ID))
        self.assertFalse(ContactType.is_alliance(CORPORATION_TYPE_ID))
        self.assertFalse(ContactType.is_alliance(1))
        self.assertFalse(ContactType.is_alliance(None))
        self.assertFalse(ContactType.is_alliance(-1))
        self.assertFalse(ContactType.is_alliance(0))
