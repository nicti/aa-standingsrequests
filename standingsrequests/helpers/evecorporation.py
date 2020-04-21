from __future__ import unicode_literals

import logging

from django.core.cache import cache
from bravado.exception import HTTPError

from ..helpers.esi_fetch import esi_fetch

logger = logging.getLogger(__name__)


class EveCorporation:
    CACHE_PREFIX = 'STANDINGS_REQUESTS_EVECORPORATION_'
    CACHE_TIME = 60 * 30  # 30 minutes

    def __init__(self, **kwargs):
        self.corporation_id = int(kwargs.get('corporation_id'))
        self.corporation_name = kwargs.get('corporation_name')
        self.ticker = kwargs.get('ticker')
        self.member_count = kwargs.get('member_count')
        self.ceo_id = kwargs.get('ceo_id')
        self.alliance_id = kwargs.get('alliance_id')

    def __str__(self):
        return self.corporation_name

    @property
    def is_npc(self):
        """returns true if this corporation is an NPC, else false"""
        return 1000000 <= self.corporation_id <= 2000000

    @classmethod
    def get_corp_by_id(cls, corp_id):
        """
        Get a corp from the cache or ESI if not cached
        Corps are cached for 3 hours
        :param corp_id: int corp ID to get
        :return: corporation object or None
        """
        logger.debug("Getting corp by id %d", corp_id)
        corp = cache.get(cls.__get_cache_key(corp_id))
        if corp is None:
            logger.debug("Corp not in cache, fetching")
            corp = cls.get_corp_esi(corp_id)
            if corp is not None:
                cache.set(cls.__get_cache_key(corp_id), corp, cls.CACHE_TIME)
        else:
            logger.debug("Corp in cache")
        return corp

    @classmethod
    def __get_cache_key(cls, corp_id):
        return cls.CACHE_PREFIX + str(corp_id)

    @classmethod
    def get_corp_esi(cls, corp_id):
        logger.debug("Attempting to get corp from esi with id %s", corp_id)        
        try:
            info = esi_fetch(
                'Corporation.get_corporations_corporation_id',
                args={'corporation_id': corp_id}
            )
            return cls(
                corporation_id=corp_id,
                corporation_name=info['name'],
                ticker=info['ticker'],
                member_count=info['member_count'],
                ceo_id=info['ceo_id'],
                alliance_id=info['alliance_id'] if 'alliance_id' in info else None
            )
        
        except HTTPError:
            logger.exception('Failed to get corp from ESI with id %i', corp_id)
            return None
