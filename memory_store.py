import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

import voyageai
from pymongo import MongoClient


class MemoryStore:
    """Persist typed memories and their Voyage embeddings in local MongoDB."""

    def __init__(self, uri, database, voyage_key, voyage_model, ttl_days):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        self.client.admin.command("ping")
        self.collection = self.client[database]["memories"]
        self.collection.create_index("expires_at", expireAfterSeconds=0, name="memory_ttl")
        self.collection.create_index("memory_key", unique=True, name="memory_key_unique")
        self.voyage = voyageai.Client(api_key=voyage_key)
        self.voyage_model = voyage_model
        self.ttl = timedelta(days=ttl_days)

    def relevant_memories(self, query, limit=8):
        """Return the top matching active memories using cosine similarity."""
        now = datetime.now(timezone.utc)
        records = list(self.collection.find(
            {"expires_at": {"$gt": now}},
            {"_id": 0, "memory_key": 1, "type": 1, "content": 1, "embedding": 1},
        ))
        if not records:
            return []

        query_vector = self.voyage.embed(
            [query], model=self.voyage_model, input_type="query"
        ).embeddings[0]

        ranked = []
        for memory in records:
            vector = memory.get("embedding", [])
            if not vector or len(vector) != len(query_vector):
                continue
            dot = sum(a * b for a, b in zip(query_vector, vector))
            norm = math.sqrt(sum(value * value for value in query_vector)) * math.sqrt(
                sum(value * value for value in vector)
            )
            if norm:
                ranked.append((dot / norm, memory))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in ranked[:limit]]

    def replace_memories(self, memories, session_id, retire_keys=()):
        """Save the updated retrieved subset and retire omitted matching memories."""
        now = datetime.now(timezone.utc)
        keep = set()
        prepared = []

        for item in memories:
            memory_key = hashlib.sha256(
                json.dumps([item["type"], item["content"]], ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            # Only the memory text goes to Voyage; its type stays as MongoDB metadata.
            vector = self.voyage.embed(
                [item["content"]], model=self.voyage_model, input_type="document"
            ).embeddings[0]
            keep.add(memory_key)
            prepared.append((memory_key, item, vector))

        for memory_key, item, vector in prepared:
            self.collection.update_one(
                {"memory_key": memory_key},
                {
                    "$set": {
                        "embedding": vector,
                        "updated_at": now,
                        "expires_at": now + self.ttl,
                    },
                    "$setOnInsert": {
                        "memory_key": memory_key,
                        "type": item["type"],
                        "content": item["content"],
                        "source": session_id,
                        "created_at": now,
                    },
                },
                upsert=True,
            )

        stale = set(retire_keys) - keep
        if stale:
            self.collection.delete_many({"memory_key": {"$in": list(stale)}})
