from django.test import TestCase

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils

from ..helpers.eveentity import EveEntityHelper
from .my_test_data import get_entity_names

MODULE_PATH = "standingsrequests.helpers.eveentity"


def get_names_from_api(entity_ids, count=1):
    """returns list of found entities in ESI format"""
    return [
        {"id": key, "name": value}
        for key, value in get_entity_names(entity_ids).items()
    ]


class TestEveEntityHelper(TestCase):
    def setUp(self):
        EveCharacter.objects.all().delete()

    def test_get_owner_from_character_id_normal(self):
        my_user = AuthUtils.create_user("Mike Manager")
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name="Bruce Wayne",
            corporation_id=2001,
            corporation_name="Dummy Corp 1",
            corporation_ticker="DC1",
        )
        CharacterOwnership.objects.create(
            character=my_character, owner_hash="abc", user=my_user
        )
        self.assertEqual(EveEntityHelper.get_owner_from_character_id(1001), my_user)

    def test_get_owner_from_character_id_no_owner(self):
        EveCharacter.objects.create(
            character_id=1001,
            character_name="Bruce Wayne",
            corporation_id=2001,
            corporation_name="Dummy Corp 1",
            corporation_ticker="DC1",
        )
        self.assertIsNone(EveEntityHelper.get_owner_from_character_id(1001))

    def test_get_owner_from_character_id_no_char(self):
        self.assertIsNone(EveEntityHelper.get_owner_from_character_id(1001))

    def test_get_character_by_user(self):
        my_user = AuthUtils.create_user("Mike Manager")
        my_character_1 = EveCharacter.objects.create(
            character_id=1001,
            character_name="Bruce Wayne",
            corporation_id=2001,
            corporation_name="Dummy Corp 1",
            corporation_ticker="DC1",
        )
        CharacterOwnership.objects.create(
            character=my_character_1, owner_hash="abc1", user=my_user
        )
        my_character_2 = EveCharacter.objects.create(
            character_id=1002,
            character_name="Peter Parker",
            corporation_id=2002,
            corporation_name="Dummy Corp 2",
            corporation_ticker="DC2",
        )
        CharacterOwnership.objects.create(
            character=my_character_2, owner_hash="abc2", user=my_user
        )
        characters = EveEntityHelper.get_characters_by_user(my_user)
        self.assertSetEqual(set(characters), {my_character_1, my_character_2})

    def test_is_character_owned_by_user_match(self):
        my_user = AuthUtils.create_user("Mike Manager")
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name="Bruce Wayne",
            corporation_id=2001,
            corporation_name="Dummy Corp 1",
            corporation_ticker="DC1",
        )
        CharacterOwnership.objects.create(
            character=my_character, owner_hash="abc", user=my_user
        )
        self.assertTrue(EveEntityHelper.is_character_owned_by_user(1001, my_user))

    def test_is_character_owned_by_user_no_match(self):
        my_user = AuthUtils.create_user("Mike Manager")
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name="Bruce Wayne",
            corporation_id=2001,
            corporation_name="Dummy Corp 1",
            corporation_ticker="DC1",
        )
        CharacterOwnership.objects.create(
            character=my_character, owner_hash="abc", user=my_user
        )
        self.assertFalse(EveEntityHelper.is_character_owned_by_user(1002, my_user))

    def test_get_state_of_character_match(self):
        my_user = AuthUtils.create_user("Mike Manager")
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name="Bruce Wayne",
            corporation_id=2001,
            corporation_name="Dummy Corp 1",
            corporation_ticker="DC1",
        )
        CharacterOwnership.objects.create(
            character=my_character, owner_hash="abc", user=my_user
        )
        self.assertEqual(EveEntityHelper.get_state_of_character(my_character), "Guest")

    def test_get_state_of_character_no_match(self):
        my_character = EveCharacter.objects.create(
            character_id=1001,
            character_name="Bruce Wayne",
            corporation_id=2001,
            corporation_name="Dummy Corp 1",
            corporation_ticker="DC1",
        )
        self.assertIsNone(EveEntityHelper.get_state_of_character(my_character))
