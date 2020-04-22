from allianceauth.eveonline.models import EveCharacter

from ..helpers.evecharacter import EveCharacterHelper
from ..models import CharacterAssociation
from .my_test_data import create_contacts_set, get_my_test_data
from ..utils import set_test_logger, NoSocketsTestCase


MODULE_PATH = 'standingsrequests.helpers.evecorporation'
logger = set_test_logger(MODULE_PATH, __file__)


class TestEveCorporation(NoSocketsTestCase):

    def test_init_with_data_has_alliance(self):
        create_contacts_set()
        character = EveCharacterHelper(character_id=1002)
        self.assertEqual(character.character_id, 1002)
        self.assertEqual(character.character_name, 'Peter Parker')
        self.assertEqual(character.corporation_id, 2001)
        self.assertEqual(character.corporation_name, 'Wayne Technologies')
        self.assertEqual(character.alliance_id, 3001)
        self.assertEqual(character.alliance_name, 'Wayne Enterprises')
        main = character.main_character
        self.assertEqual(main.character_id, 1001)

    def test_init_with_data_has_no_alliance(self):
        create_contacts_set()
        character = EveCharacterHelper(character_id=1004)
        self.assertEqual(character.character_id, 1004)
        self.assertEqual(character.character_name, 'Kara Danvers')
        self.assertEqual(character.corporation_id, 2003)
        self.assertEqual(character.corporation_name, 'CatCo Worldwide Media')
        self.assertIsNone(character.alliance_id)
        self.assertIsNone(character.alliance_name)

    def test_init_with_data_has_no_main(self):
        create_contacts_set()
        assoc = CharacterAssociation.objects.get(character_id=1001)
        assoc.main_character = None
        assoc.save()
        character = EveCharacterHelper(character_id=1001)
        self.assertEqual(character.character_id, 1001)
        self.assertEqual(character.character_name, 'Bruce Wayne')
        self.assertEqual(character.corporation_id, 2001)
        self.assertEqual(character.corporation_name, 'Wayne Technologies')
        self.assertEqual(character.alliance_id, 3001)
        self.assertEqual(character.alliance_name, 'Wayne Enterprises')
        self.assertIsNone(character.main_character)
    
    def test_init_without_data(self):
        EveCharacter.objects.filter(character_id=1001).delete()
        data = get_my_test_data()['EveCharacter']['1001']
        EveCharacter.objects.create(**data)
        character = EveCharacterHelper(character_id=1001)
        self.assertEqual(character.character_id, 1001)
        self.assertEqual(character.character_name, 'Bruce Wayne')
