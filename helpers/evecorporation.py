from __future__ import unicode_literals

from django.core.cache import cache

import requests
import logging

logger = logging.getLogger(__name__)


class EveCorporation:
    CACHE_PREFIX = 'STANDINGS_REQUESTS_EVECORPORATION_'
    CACHE_TIME = 60*30  # 30 minutes

    def __init__(self, *args, **kwargs):
        self.corporation_id = int(kwargs.get('corporation_id'))
        self.corporation_name = kwargs.get('corporation_name')
        self.ticker = kwargs.get('ticker')
        self.member_count = kwargs.get('member_count')
        self.ceo_id = kwargs.get('ceo_id')
        self.alliance_id = kwargs.get('alliance_id')

    def __str__(self):
        return self.corporation_name

    @classmethod
    def get_corp_by_id(cls, corp_id):
        """
        Get a corp from the cache or ESI if not cached
        Corps are cached for 3 hours
        :param corp_id: int corp ID to get
        :return:
        """
        logger.debug("Getting corp by id {}".format(corp_id))
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
        url = 'https://esi.tech.ccp.is/v3/corporations/{corporation_id}/'.format(corporation_id=int(corp_id))
        logger.debug("Getting corp_id {} from ESI {}".format(corp_id, url))
        try:
            r = requests.get(url)
            r.raise_for_status()
            return cls(corporation_id=corp_id, **r.json())
        except requests.HTTPError:
            logger.exception("Failed to get corp_id {} from ESI".format(corp_id))
            return None
