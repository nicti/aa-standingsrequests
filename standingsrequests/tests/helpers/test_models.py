from django.test import TestCase
from eveuniverse.models import EveEntity

from allianceauth.tests.auth_utils import AuthUtils

from standingsrequests.models import FrozenAuthUser
from standingsrequests.tests.test_models import TEST_USER_NAME
from standingsrequests.tests.testdata.my_test_data import load_eve_entities


class TestGatherEntityIds(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eve_entities()

    def test_should_gather_all_entity_ids(self):
        # given
        user = AuthUtils.create_member(TEST_USER_NAME)
        alliance = EveEntity.objects.get(id=3001)
        character = EveEntity.objects.get(id=1001)
        corporation = EveEntity.objects.get(id=2001)
        faction = EveEntity.objects.create(
            id=5001, name="Caldari", category=EveEntity.CATEGORY_FACTION
        )
        alt = FrozenAuthUser.objects.create(
            alliance=alliance,
            character=character,
            corporation=corporation,
            faction=faction,
            user=user,
        )

        # when
        result = alt.entity_ids()

        # then
        expected = {alliance.id, character.id, corporation.id, faction.id}
        self.assertSetEqual(result, expected)

    def test_should_ignore_none_values(self):
        # given
        user = AuthUtils.create_member(TEST_USER_NAME)
        alliance = EveEntity.objects.get(id=3001)
        character = EveEntity.objects.get(id=1001)
        corporation = EveEntity.objects.get(id=2001)
        alt = FrozenAuthUser.objects.create(
            alliance=alliance, character=character, corporation=corporation, user=user
        )

        # when
        result = alt.entity_ids()

        # then
        expected = {alliance.id, character.id, corporation.id}
        self.assertSetEqual(result, expected)
