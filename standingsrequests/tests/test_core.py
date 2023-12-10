from unittest.mock import patch

from django.test import TestCase

from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import NoSocketsTestCase

from standingsrequests.core.config import BaseConfig
from standingsrequests.core.contact_types import ContactType

from .testdata.entity_type_ids import CHARACTER_TYPE_ID, CORPORATION_TYPE_ID
from .testdata.my_test_data import create_entity, load_eve_entities

MODULE_PATH = "standingsrequests.core"


class TestContactType(TestCase):
    def test_get_contact_type(self):
        self.assertEqual(ContactType.character_id(), CHARACTER_TYPE_ID)

    def test_is_character(self):
        self.assertTrue(ContactType(CHARACTER_TYPE_ID).is_character)
        self.assertFalse(ContactType(CORPORATION_TYPE_ID).is_character)

    def test_get_contact_type_2(self):
        self.assertEqual(ContactType.corporation_id(), CORPORATION_TYPE_ID)

    def test_is_corporation(self):
        self.assertFalse(ContactType(CHARACTER_TYPE_ID).is_corporation)
        self.assertTrue(ContactType(CORPORATION_TYPE_ID).is_corporation)


@patch(MODULE_PATH + ".config.STANDINGS_API_CHARID", 1001)
class TestBaseConfig(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eve_entities()

    def test_should_return_existing_character(self):
        # given
        character = create_entity(EveCharacter, 1001)
        # when
        owner_character = BaseConfig.owner_character()
        # then
        self.assertEqual(character, owner_character)

    @patch(MODULE_PATH + ".config.EveCharacter.objects.create_character")
    def test_create_new_character_if_not_exists(self, mock_create_character):
        # given
        character = create_entity(EveCharacter, 1002)
        mock_create_character.return_value = character
        # when
        owner_character = BaseConfig.owner_character()
        # then
        self.assertEqual(character, owner_character)

    @patch(MODULE_PATH + ".config.SR_OPERATION_MODE", "alliance")
    def test_should_return_alliance(self):
        # given
        create_entity(EveCharacter, 1001)
        # when
        result = BaseConfig.standings_source_entity()
        # then
        self.assertEqual(result.id, 3001)

    @patch(MODULE_PATH + ".config.SR_OPERATION_MODE", "corporation")
    def test_should_return_corporation(self):
        # given
        create_entity(EveCharacter, 1001)
        # when
        result = BaseConfig.standings_source_entity()
        # then
        self.assertEqual(result.id, 2001)
