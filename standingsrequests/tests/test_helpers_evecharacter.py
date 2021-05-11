from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import NoSocketsTestCase

from ..helpers.evecharacter import EveCharacterHelper
from .my_test_data import (
    create_contacts_set,
    create_entity,
    generate_eve_entities_from_allianceauth,
    get_my_test_data,
)

MODULE_PATH = "standingsrequests.helpers.evecorporation"


class TestEveCharacter(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_contacts_set()
        create_entity(EveCharacter, 1001)
        generate_eve_entities_from_allianceauth()

    def test_init_with_data_has_alliance(self):
        character = EveCharacterHelper(character_id=1002)
        self.assertEqual(character.character_id, 1002)
        self.assertEqual(character.character_name, "Peter Parker")
        self.assertEqual(character.corporation_id, 2001)
        self.assertEqual(character.corporation_name, "Wayne Technologies")
        self.assertEqual(character.alliance_id, 3001)
        self.assertEqual(character.alliance_name, "Wayne Enterprises")

    def test_init_with_data_has_no_alliance(self):
        character = EveCharacterHelper(character_id=1004)
        self.assertEqual(character.character_id, 1004)
        self.assertEqual(character.character_name, "Kara Danvers")
        self.assertEqual(character.corporation_id, 2003)
        self.assertEqual(character.corporation_name, "CatCo Worldwide Media")
        self.assertIsNone(character.alliance_id)
        self.assertIsNone(character.alliance_name)

    def test_init_with_data_has_no_main(self):
        character = EveCharacterHelper(character_id=1001)
        self.assertEqual(character.character_id, 1001)
        self.assertEqual(character.character_name, "Bruce Wayne")
        self.assertEqual(character.corporation_id, 2001)
        self.assertEqual(character.corporation_name, "Wayne Technologies")
        self.assertEqual(character.alliance_id, 3001)
        self.assertEqual(character.alliance_name, "Wayne Enterprises")

    def test_init_without_data(self):
        EveCharacter.objects.filter(character_id=1001).delete()
        data = get_my_test_data()["EveCharacter"]["1001"]
        EveCharacter.objects.create(**data)
        character = EveCharacterHelper(character_id=1001)
        self.assertEqual(character.character_id, 1001)
        self.assertEqual(character.character_name, "Bruce Wayne")
