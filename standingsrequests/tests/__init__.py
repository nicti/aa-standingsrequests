def _dt_eveformat(dt: object) -> str:
    """converts a datetime to a string in eve format
    e.g. '2019-06-25T19:04:44'
    """
    from datetime import datetime

    dt2 = datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    return dt2.isoformat()


def _get_entity_name(entity_id):
    """returns name if entity is found, else None"""    

    entities = {
        1001: 'Bruce Wayne',
        1002: 'Peter Parker',
        1003: 'Clark Kent',
        1004: 'Kara Danvers',
        1005: 'Kathy Kane',
        1006: 'Steven Rogers',
    }
    if entity_id in entities:
        return entities[entity_id]
    else:
        return None


def _get_entity_names(eve_entity_ids):
    """returns dict with {id: name} for found entities, else empty dict"""
    names_info = {}
    for id in eve_entity_ids:
        name = _get_entity_name(id)
        if name:
            names_info[id] = name

    return names_info


def _set_logger(logger_name: str, name: str) -> object:
    """set logger for current test module
    
    Args:
    - logger: current logger object
    - name: name of current module, e.g. __file__
    
    Returns:
    - amended logger
    """
    import logging
    import os

    # reconfigure logger so we get logging from tested module
    f_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s:%(funcName)s - %(message)s'
    )
    f_handler = logging.FileHandler(
        '{}.log'.format(os.path.splitext(name)[0]),
        'w+'
    )
    f_handler.setFormatter(f_format)
    logger = logging.getLogger(logger_name)
    logger.level = logging.DEBUG
    logger.addHandler(f_handler)
    logger.propagate = False
    return logger