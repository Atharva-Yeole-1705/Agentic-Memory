from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient

from .config import get_settings


@lru_cache
def get_client():
    settings = get_settings()
    return MongoClient(settings.mongodb_uri, tz_aware=True)


def get_database():
    settings = get_settings()
    client = get_client()
    database = client[settings.mongodb_database]
    database.memories.create_index([("owner_id", ASCENDING), ("workspace_id", ASCENDING), ("updated_at", DESCENDING)])
    database.memories.create_index("expires_at", expireAfterSeconds=0)
    database.sessions.create_index([("owner_id", ASCENDING), ("updated_at", DESCENDING)])
    return database
