import json
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.test import RequestFactory, TestCase
from django.utils.timezone import now

from allianceauth.eveonline.models import (
    EveAllianceInfo,
    EveCharacter,
    EveCorporationInfo,
)
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.testing import add_character_to_user, response_text

from standingsrequests.core.contact_types import ContactTypeId
from standingsrequests.models import Contact, StandingRequest
from standingsrequests.tests.testdata.my_test_data import (
    TEST_SCOPE,
    create_contacts_set,
    create_eve_objects,
)


class PartialDictEqualMixin:
    def assertPartialDictEqual(self, d1: dict, d2: dict):
        """Assert that d1 equals d2 for the subset of keys of d1."""
        subset = {k: v for k, v in d1.items() if k in d2}
        self.assertDictEqual(subset, d2)


def json_response_to_python_2(response: JsonResponse, data_key="data") -> object:
    """Convert JSON response into Python object."""
    data = json.loads(response_text(response))
    return data[data_key]


def json_response_to_dict_2(response: JsonResponse, key="id", data_key="data") -> dict:
    """Convert JSON response into dict by given key."""
    return {x[key]: x for x in json_response_to_python_2(response, data_key)}


class TestViewPagesBase(PartialDictEqualMixin, TestCase):
    """Base TestClass for all tests that deal with standing requests

    Defines common test data
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()

        create_eve_objects()
        cls.contact_set = create_contacts_set()

        # State is alliance, all members can add standings
        member_state = AuthUtils.get_member_state()
        member_state.member_alliances.add(EveAllianceInfo.objects.get(alliance_id=3001))
        perm = AuthUtils.get_permission_by_name(StandingRequest.REQUEST_PERMISSION_NAME)
        member_state.permissions.add(perm)

        # Requesting user - can only make requests
        cls.main_character_1 = EveCharacter.objects.get(character_id=1002)
        cls.user_requestor = AuthUtils.create_member(
            cls.main_character_1.character_name
        )
        add_character_to_user(
            cls.user_requestor,
            cls.main_character_1,
            is_main=True,
            scopes=[TEST_SCOPE],
        )
        cls.alt_character_1 = EveCharacter.objects.get(character_id=1007)
        add_character_to_user(
            cls.user_requestor,
            cls.alt_character_1,
            scopes=[TEST_SCOPE],
        )
        cls.alt_corporation = EveCorporationInfo.objects.get(
            corporation_id=cls.alt_character_1.corporation_id
        )
        cls.alt_character_2 = EveCharacter.objects.get(character_id=1008)
        add_character_to_user(
            cls.user_requestor,
            cls.alt_character_2,
            scopes=[TEST_SCOPE],
        )

        # Standing manager - can do everything
        cls.main_character_2 = EveCharacter.objects.get(character_id=1001)
        cls.user_manager = AuthUtils.create_member(cls.main_character_2.character_name)
        add_character_to_user(
            cls.user_manager,
            cls.main_character_2,
            is_main=True,
            scopes=[TEST_SCOPE],
        )
        cls.user_manager = AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.affect_standings", cls.user_manager
        )
        cls.user_manager = AuthUtils.add_permission_to_user_by_name(
            "standingsrequests.view", cls.user_manager
        )
        cls.user_manager = User.objects.get(pk=cls.user_manager.pk)

        # Old user - has no main and no rights
        cls.user_former_member = AuthUtils.create_user("Lex Luthor")
        cls.alt_character_3 = EveCharacter.objects.get(character_id=1010)
        add_character_to_user(
            cls.user_former_member,
            cls.alt_character_3,
            scopes=[TEST_SCOPE],
        )

    def _create_standing_for_alt(self, alt: Any) -> StandingRequest:
        if isinstance(alt, EveCharacter):
            contact_id = alt.character_id
            contact_type_id = ContactTypeId.character_id()
        elif isinstance(alt, EveCorporationInfo):
            contact_id = alt.corporation_id
            contact_type_id = ContactTypeId.CORPORATION
        else:
            raise NotImplementedError()

        return StandingRequest.objects.create(
            user=self.user_requestor,
            contact_id=contact_id,
            contact_type_id=contact_type_id,
            action_by=self.user_manager,
            action_date=now() - timedelta(days=1, hours=1),
            is_effective=True,
            effective_date=now() - timedelta(days=1),
        )

    def _set_standing_for_alt_in_game(self, alt: Any) -> None:
        if isinstance(alt, EveCharacter):
            contact_id = alt.character_id
            Contact.objects.update_or_create(
                contact_set=self.contact_set,
                eve_entity_id=contact_id,
                defaults={"standing": 10},
            )
        elif isinstance(alt, EveCorporationInfo):
            contact_id = alt.corporation_id
            Contact.objects.update_or_create(
                contact_set=self.contact_set,
                eve_entity_id=contact_id,
                defaults={"standing": 10},
            )
        else:
            raise NotImplementedError()

        self.contact_set.refresh_from_db()
