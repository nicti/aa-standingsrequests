from unittest.mock import patch

from django.test import TestCase

from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import NoSocketsTestCase

from standingsrequests.core import app_config
from standingsrequests.tests.testdata.my_test_data import (
    create_entity,
    create_eve_objects,
    load_eve_entities,
)

MODULE_PATH = "standingsrequests.core.app_config"


@patch(MODULE_PATH + ".STANDINGS_API_CHARID", 1001)
class TestBaseConfig(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eve_entities()

    def test_should_return_existing_character(self):
        # given
        character = create_entity(EveCharacter, 1001)
        # when
        owner_character = app_config.owner_character()
        # then
        self.assertEqual(character, owner_character)

    @patch(MODULE_PATH + ".EveCharacter.objects.create_character")
    def test_create_new_character_if_not_exists(self, mock_create_character):
        # given
        character = create_entity(EveCharacter, 1002)
        mock_create_character.return_value = character
        # when
        owner_character = app_config.owner_character()
        # then
        self.assertEqual(character, owner_character)

    @patch(MODULE_PATH + ".SR_OPERATION_MODE", "alliance")
    def test_should_return_alliance(self):
        # given
        create_entity(EveCharacter, 1001)
        # when
        result = app_config.standings_source_entity()
        # then
        self.assertEqual(result.id, 3001)

    @patch(MODULE_PATH + ".SR_OPERATION_MODE", "corporation")
    def test_should_return_corporation(self):
        # given
        create_entity(EveCharacter, 1001)
        # when
        result = app_config.standings_source_entity()
        # then
        self.assertEqual(result.id, 2001)


class TestConfiguredOrganizations(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_eve_objects()
        cls.character_1001 = EveCharacter.objects.get(character_id=1001)

    @patch(MODULE_PATH + ".STR_CORP_IDS", ["2001"])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organization_matches_corp(self):
        self.assertTrue(app_config.is_character_a_member(self.character_1001))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", ["3001"])
    def test_pilot_in_organization_matches_alliance(self):
        self.assertTrue(app_config.is_character_a_member(self.character_1001))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [3101])
    def test_pilot_in_organization_doest_not_exist(self):
        self.assertFalse(app_config.is_character_a_member(self.character_1001))

    @patch(MODULE_PATH + ".STR_CORP_IDS", [])
    @patch(MODULE_PATH + ".STR_ALLIANCE_IDS", [])
    def test_pilot_in_organization_matches_none(self):
        self.assertFalse(app_config.is_character_a_member(self.character_1001))
