from __future__ import unicode_literals

from django.core.cache import cache

import logging
from esi.clients import esi_client_factory
from bravado.exception import HTTPNotFound, HTTPBadGateway, HTTPGatewayTimeout
from time import sleep
from ..managers import SWAGGER_SPEC_PATH

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
    def get_corp_esi(cls, corp_id, count=1):
        logger.debug("Attempting to get corp from esi with id %s", corp_id)
        client = esi_client_factory(spec_file=SWAGGER_SPEC_PATH)
        try:
            info = client.Corporation.get_corporations_corporation_id(corporation_id=corp_id).result()
            return cls(corporation_id=corp_id,
                       corporation_name=info['name'],
                       ticker=info['ticker'],
                       member_count=info['member_count'],
                       ceo_id=info['ceo_id'],
                       alliance_id=info['alliance_id'] if 'alliance_id' in info else None
                       )

        except HTTPNotFound:
            raise None
        except (HTTPBadGateway, HTTPGatewayTimeout):
            if count >= 5:
                logger.exception('Failed to get entity name %s times.', count)
                return None
            else:
                sleep(count**2)
                return cls.get_corp_esi(corp_id, count+1)