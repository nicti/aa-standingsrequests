import inspect
import json
import os
from copy import deepcopy
from typing import Any

from bravado.exception import HTTPNotFound

from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import (
    EveAllianceInfo,
    EveCharacter,
    EveCorporationInfo,
)
from app_utils.esi_testing import BravadoOperationStub, BravadoResponseStub

from standingsrequests.managers import EsiContactsContainer
from standingsrequests.models import (
    CharacterAffiliation,
    Contact,
    ContactSet,
    CorporationDetails,
)

TEST_STANDINGS_API_CHARID = 1001
TEST_STANDINGS_API_CHARNAME = "Bruce Wayne"
TEST_STANDINGS_CORPORATION_ID = 2001
TEST_STANDINGS_CORPORATION_NAME = "Wayne Technologies"
TEST_STANDINGS_ALLIANCE_ID = 3001
TEST_STANDINGS_ALLIANCE_NAME = "Wayne Enterprises"

TEST_SCOPE = "publicData"


##########################
# internal functions


def _load_test_data():
    current_dir = os.path.dirname(
        os.path.abspath(inspect.getfile(inspect.currentframe()))
    )

    with open(current_dir + "/my_test_data.json", "r", encoding="utf-8") as f:
        my_test_data = json.load(f)

    return my_test_data


def _load_entities():
    entities = {}
    for character_id, character in _my_test_data["EveCharacter"].items():
        entities[int(character_id)] = character["character_name"]

    for corporation_id, corporation in _my_test_data["EveCorporationInfo"].items():
        entities[int(corporation_id)] = corporation["corporation_name"]

    for alliance_id, alliance in _my_test_data["EveAllianceInfo"].items():
        entities[int(alliance_id)] = alliance["alliance_name"]

    return entities


_my_test_data = _load_test_data()
_entities = _load_entities()


##########################
# common functions


def get_my_test_data() -> dict:
    """returns the raw test data dict"""
    return _my_test_data


def get_entity_name(entity_id: int):
    """returns name if entity is found, else None"""

    if int(entity_id) in _entities:
        return _entities[int(entity_id)]
    else:
        return None


def get_entity_names(eve_entity_ids: list) -> dict:
    """returns dict with {id: name} for found entities, else empty dict"""
    names_info = {}
    for id in eve_entity_ids:
        name = get_entity_name(id)
        if name:
            names_info[id] = name

    return names_info


def get_entity_data(EntityClass: type, entity_id: int) -> Any:
    if EntityClass not in [EveCharacter, EveCorporationInfo, EveAllianceInfo]:
        raise TypeError(f"Invalid entity_class: {EntityClass.__name__}")

    if str(entity_id) not in _my_test_data[EntityClass.__name__]:
        raise ValueError(
            f"not entity found in test data for that entity_id = {entity_id}"
        )

    return _my_test_data[EntityClass.__name__][str(entity_id)]


def create_entity(EntityClass: type, entity_id: int) -> Any:
    """creates an Eve entity from test data"""
    data = get_entity_data(EntityClass, entity_id)
    return EntityClass.objects.create(**data)


##########################
# esi emulation


def esi_post_universe_names(ids, *args, **kwargs) -> Any:
    entities = []
    for entity in _my_test_data["esi_post_universe_names"]:
        if entity["id"] in ids:
            entities.append(entity)

    return BravadoOperationStub(entities)


def esi_post_characters_affiliation(characters, *args, **kwargs) -> Any:
    result = []
    for assoc in _my_test_data["CharacterAffiliation"]:
        if assoc["character_id"] in characters:
            row = assoc.copy()
            result.append(row)

    return BravadoOperationStub(result)


def esi_get_corporations_corporation_id(corporation_id, *args, **kwargs) -> Any:
    result = []
    corporation_id = str(corporation_id)
    if corporation_id not in _my_test_data["EveCorporationInfo"]:
        raise HTTPNotFound(BravadoResponseStub(404, reason="Test Exception"))

    row = _my_test_data["EveCorporationInfo"][corporation_id]
    result = {
        "name": row["corporation_name"],
        "ticker": row["corporation_ticker"],
        "member_count": row["member_count"],
        "ceo_id": row["ceo_id"] if "ceo_id" in row else None,
    }
    if row["alliance_id"]:
        result["alliance_id"] = row["alliance_id"]

    return BravadoOperationStub(result)


def esi_get_alliances_alliance_id_contacts_labels(*args, **kwargs) -> Any:
    return BravadoOperationStub(deepcopy(_my_test_data["alliance_labels"]))


def esi_get_alliances_alliance_id_contacts(*args, **kwargs) -> Any:
    return BravadoOperationStub(deepcopy(_my_test_data["alliance_contacts"]))


##########################
# app specific functions


def create_standings_char():
    character, _ = EveCharacter.objects.get_or_create(
        character_id=TEST_STANDINGS_API_CHARID,
        defaults={
            "character_name": TEST_STANDINGS_API_CHARNAME,
            "corporation_id": TEST_STANDINGS_CORPORATION_ID,
            "corporation_name": TEST_STANDINGS_CORPORATION_ID,
            "alliance_id": TEST_STANDINGS_ALLIANCE_ID,
            "alliance_name": TEST_STANDINGS_ALLIANCE_NAME,
        },
    )
    return character


def get_test_labels() -> list:
    """returns labels from test data as list of _ContactsWrapper.Label"""
    labels = []
    for label_data in get_my_test_data()["alliance_labels"]:
        labels.append(EsiContactsContainer.EsiLabel(label_data))

    return labels


def get_test_contacts():
    """returns contacts from test data as list of _ContactsWrapper.Contact"""
    labels = get_test_labels()

    contact_ids = [x["contact_id"] for x in get_my_test_data()["alliance_contacts"]]
    names_info = get_entity_names(contact_ids)
    contacts = []
    for contact_data in get_my_test_data()["alliance_contacts"]:
        contacts.append(
            EsiContactsContainer.EsiContact(contact_data, labels, names_info)
        )

    return contacts


def create_contacts_set(my_set: ContactSet = None, include_assoc=True) -> ContactSet:
    if not my_set:
        my_set = ContactSet.objects.create(name="Dummy Set")

    # add labels
    ContactSet.objects._add_labels_from_api(my_set, get_test_labels())

    # create contacts for ContactSet
    for contact in _my_test_data["alliance_contacts"]:
        if contact["contact_type"] == "character":
            category = EveEntity.CATEGORY_CHARACTER
        elif contact["contact_type"] == "corporation":
            category = EveEntity.CATEGORY_CORPORATION
        elif contact["contact_type"] == "alliance":
            category = EveEntity.CATEGORY_ALLIANCE
        else:
            raise ValueError("Invalid contact type")

        eve_entity, _ = EveEntity.objects.get_or_create(
            id=contact["contact_id"],
            defaults={
                "name": get_entity_name(contact["contact_id"]),
                "category": category,
            },
        )
        my_standing = Contact.objects.create(
            contact_set=my_set,
            eve_entity=eve_entity,
            standing=contact["standing"],
        )
        for label_id in contact["label_ids"]:
            my_standing.labels.add(my_set.labels.get(label_id=label_id))

    # update EveEntity based on characters
    for character_id, character_data in _my_test_data["EveCharacter"].items():
        EveEntity.objects.get_or_create(
            id=character_id,
            defaults={
                "name": character_data["character_name"],
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )
        EveEntity.objects.get_or_create(
            id=character_data["corporation_id"],
            defaults={
                "name": character_data["corporation_name"],
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
        if character_data["alliance_id"]:
            EveEntity.objects.get_or_create(
                id=character_data["alliance_id"],
                defaults={
                    "name": character_data["alliance_name"],
                    "category": EveEntity.CATEGORY_ALLIANCE,
                },
            )

    # create CharacterAffiliation
    if include_assoc:
        CharacterAffiliation.objects.all().delete()
        for assoc in _my_test_data["CharacterAffiliation"]:
            CharacterAffiliation.objects.create(**assoc)

    return my_set


def create_eve_objects():
    """creates all Eve objects from test data"""
    for character_data in _my_test_data[EveCharacter.__name__].values():
        character = EveCharacter.objects.create(**character_data)
        if character.alliance_id:
            defaults = {
                "alliance_name": character.alliance_name,
                "alliance_ticker": character.alliance_ticker,
                "executor_corp_id": 2001,
            }
            alliance, _ = EveAllianceInfo.objects.get_or_create(
                alliance_id=character.alliance_id, defaults=defaults
            )
        else:
            alliance = None

        defaults = {
            "corporation_name": character.corporation_name,
            "corporation_ticker": character.corporation_ticker,
            "member_count": 99,
            "alliance": alliance,
        }
        EveCorporationInfo.objects.get_or_create(
            corporation_id=character.corporation_id, defaults=defaults
        )


def add_eve_object_to_eve_entities(obj: Any):
    if isinstance(obj, EveCharacter):
        EveEntity.objects.update_or_create(
            id=obj.character_id,
            defaults={
                "name": obj.character_name,
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )
        EveEntity.objects.update_or_create(
            id=obj.corporation_id,
            defaults={
                "name": obj.corporation_name,
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
        if obj.alliance_id:
            EveEntity.objects.update_or_create(
                id=obj.alliance_id,
                defaults={
                    "name": obj.alliance_name,
                    "category": EveEntity.CATEGORY_ALLIANCE,
                },
            )
    elif isinstance(obj, EveCorporationInfo):
        EveEntity.objects.update_or_create(
            id=obj.corporation_id,
            defaults={
                "name": obj.corporation_name,
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
    elif isinstance(obj, EveAllianceInfo):
        EveEntity.objects.update_or_create(
            id=obj.alliance_id,
            defaults={
                "name": obj.alliance_name,
                "category": EveEntity.CATEGORY_ALLIANCE,
            },
        )
    else:
        raise NotImplementedError()


def generate_eve_entities_from_allianceauth():
    for character in EveCharacter.objects.all():
        EveEntity.objects.get_or_create(
            id=character.character_id,
            defaults={
                "name": character.character_name,
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )
        EveEntity.objects.get_or_create(
            id=character.corporation_id,
            defaults={
                "name": character.corporation_name,
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
        if character.alliance_id:
            EveEntity.objects.get_or_create(
                id=character.alliance_id,
                defaults={
                    "name": character.alliance_name,
                    "category": EveEntity.CATEGORY_ALLIANCE,
                },
            )
    for corporation in EveCorporationInfo.objects.all():
        EveEntity.objects.get_or_create(
            id=corporation.corporation_id,
            defaults={
                "name": corporation.corporation_name,
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
    for alliance in EveAllianceInfo.objects.all():
        EveEntity.objects.get_or_create(
            id=alliance.alliance_id,
            defaults={
                "name": alliance.alliance_name,
                "category": EveEntity.CATEGORY_ALLIANCE,
            },
        )


def load_eve_entities():
    for character in _my_test_data["EveCharacter"].values():
        EveEntity.objects.get_or_create(
            id=character["character_id"],
            defaults={
                "name": character["character_name"],
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )
        EveEntity.objects.get_or_create(
            id=character["corporation_id"],
            defaults={
                "name": character["corporation_name"],
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
        if character["alliance_id"]:
            EveEntity.objects.get_or_create(
                id=character["alliance_id"],
                defaults={
                    "name": character["alliance_name"],
                    "category": EveEntity.CATEGORY_ALLIANCE,
                },
            )
    for corporation in _my_test_data["EveCorporationInfo"].values():
        EveEntity.objects.get_or_create(
            id=corporation["corporation_id"],
            defaults={
                "name": corporation["corporation_name"],
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
    for alliance in _my_test_data["EveAllianceInfo"].values():
        EveEntity.objects.get_or_create(
            id=alliance["alliance_id"],
            defaults={
                "name": alliance["alliance_name"],
                "category": EveEntity.CATEGORY_ALLIANCE,
            },
        )

    for id, name in [
        (500001, "Caldari State"),
        (500002, "Minmatar Republic"),
        (500003, "Amarr Empire"),
        (500004, "Gallente Federation"),
    ]:
        EveEntity.objects.get_or_create(
            id=id,
            defaults={"name": name, "category": EveEntity.CATEGORY_FACTION},
        )


def load_corporation_details():
    for record in _my_test_data["EveCorporationInfo"].values():
        alliance_id = record["alliance_id"] if record.get("alliance_id") else None
        CorporationDetails.objects.update_or_create(
            corporation_id=record["corporation_id"],
            defaults={
                "alliance_id": alliance_id,
                "ceo_id": 2102,
                "member_count": 99,
                "ticker": record["corporation_ticker"],
            },
        )
