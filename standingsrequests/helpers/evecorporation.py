from bravado.exception import HTTPError

from django.core.cache import cache

from allianceauth.services.hooks import get_extension_logger

from .. import __title__
from ..helpers.esi_fetch import esi_fetch
from ..utils import LoggerAddTag


logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class EveCorporation:
    CACHE_PREFIX = "STANDINGS_REQUESTS_EVECORPORATION_"
    CACHE_TIME = 60 * 30  # 30 minutes

    def __init__(self, **kwargs):
        self.corporation_id = int(kwargs.get("corporation_id"))
        self.corporation_name = kwargs.get("corporation_name")
        self.ticker = kwargs.get("ticker")
        self.member_count = kwargs.get("member_count")
        self.ceo_id = kwargs.get("ceo_id")
        self.alliance_id = kwargs.get("alliance_id")
        self.alliance_name = kwargs.get("alliance_name")

    def __str__(self):
        return self.corporation_name

    def __eq__(self, o: object) -> bool:
        return (
            isinstance(o, type(self))
            and self.corporation_id == o.corporation_id
            and self.corporation_name == o.corporation_name
            and self.ticker == o.ticker
            and self.member_count == o.member_count
            and self.ceo_id == o.ceo_id
            and self.alliance_id == o.alliance_id
            and self.alliance_name == o.alliance_name
        )

    @property
    def is_npc(self) -> bool:
        """returns true if this corporation is an NPC, else false"""
        return self.corporation_is_npc(self.corporation_id)

    @staticmethod
    def corporation_is_npc(corporation_id) -> bool:
        return 1000000 <= corporation_id <= 2000000

    @classmethod
    def get_by_id(cls, corporation_id: int) -> object:
        """
        Get a corporation from the cache or ESI if not cached
        Corps are cached for 3 hours
        :param corporation_id: int corporation ID to get
        :return: corporation object or None
        """
        logger.debug("Getting corporation by id %d", corporation_id)
        corporation = cache.get(cls._get_cache_key(corporation_id))
        if corporation is None:
            logger.debug("Corp not in cache, fetching")
            corporation = cls.fetch_corporation_from_api(corporation_id)
            if corporation is not None:
                cache.set(
                    cls._get_cache_key(corporation_id), corporation, cls.CACHE_TIME
                )
        else:
            logger.debug("Corp in cache")
        return corporation

    @classmethod
    def _get_cache_key(cls, corporation_id):
        return cls.CACHE_PREFIX + str(corporation_id)

    @classmethod
    def fetch_corporation_from_api(cls, corporation_id):
        from ..models import EveEntity

        logger.debug("Attempting to get corp from esi with id %s", corporation_id)
        try:
            info = esi_fetch(
                "Corporation.get_corporations_corporation_id",
                args={"corporation_id": corporation_id},
            )
        except HTTPError:
            logger.exception("Failed to get corp from ESI with id %i", corporation_id)
            return None

        else:
            args = {
                "corporation_id": corporation_id,
                "corporation_name": info["name"],
                "ticker": info["ticker"],
                "member_count": info["member_count"],
                "ceo_id": info["ceo_id"],
            }
            if "alliance_id" in info and info["alliance_id"]:
                args["alliance_id"] = info["alliance_id"]
                args["alliance_name"] = EveEntity.objects.get_name(info["alliance_id"])

            return cls(**args)
