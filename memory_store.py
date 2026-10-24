import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

import voyageai
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

MEMORY_TTL_DAYS_BY_TYPE = {
    "project_fact": 365,
    "technical_decision": 180,
    "business_rule": 180,
    "ongoing_goal": 180,
    "user_preference": 30,
    "lesson_learned": 30,
    "project_milestone": 30,
}
MEMORY_TTL_POLICY_VERSION = 1


class MemoryStore:
    """Persist typed memories and their Voyage embeddings in local MongoDB."""

    def __init__(self, uri, database, voyage_key, voyage_model, vector_dimensions=1024):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        self.client.admin.command("ping")
        topology = self.client.admin.command("hello")
        if not topology.get("setName") and topology.get("msg") != "isdbgrid":
            self.client.close()
            raise RuntimeError(
                "MongoDB Vector Search requires a replica set or sharded deployment; "
                "the configured MongoDB server is standalone."
            )
        self.collection = self.client[database]["memories"]
        self.collection.create_index("expires_at", expireAfterSeconds=0, name="memory_ttl")
        self.collection.create_index("memory_key", unique=True, name="memory_key_unique")
        self._apply_ttl_policy()
        # Retry transient rate-limit responses, which are common on Voyage's free tier.
        self.voyage = voyageai.Client(api_key=voyage_key, max_retries=8)
        self.voyage_model = voyage_model
        self.vector_dimensions = vector_dimensions
        self._ensure_vector_index()

    def _apply_ttl_policy(self):
        """Recalculate legacy expiries once using each memory's last saved time."""
        branches = [
            {"case": {"$eq": ["$type", memory_type]}, "then": days}
            for memory_type, days in MEMORY_TTL_DAYS_BY_TYPE.items()
        ]
        self.collection.update_many(
            {
                "ttl_policy_version": {"$ne": MEMORY_TTL_POLICY_VERSION},
                "type": {"$in": list(MEMORY_TTL_DAYS_BY_TYPE)},
            },
            [{"$set": {
                "expires_at": {
                    "$dateAdd": {
                        "startDate": {
                            "$ifNull": [
                                "$updated_at",
                                {"$ifNull": ["$created_at", "$$NOW"]},
                            ]
                        },
                        "unit": "day",
                        "amount": {"$switch": {"branches": branches, "default": 30}},
                    }
                },
                "ttl_policy_version": MEMORY_TTL_POLICY_VERSION,
            }}],
        )

    def _ensure_vector_index(self):
        """Create/update the Vector Search index and wait until it is queryable."""
        filter_paths = ("expires_at", "source", "type", "created_at")
        vector_field = {
            "type": "vector",
            "path": "embedding",
            "numDimensions": self.vector_dimensions,
            "similarity": "cosine",
        }
        definition = {
            "fields": [vector_field] + [
                {"type": "filter", "path": path} for path in filter_paths
            ]
        }
        model = SearchIndexModel(
            definition=definition,
            name="memory_vector_index",
            type="vectorSearch",
        )

        def has_required_fields(fields):
            vector = next(
                (field for field in fields
                 if field.get("type") == "vector" and field.get("path") == "embedding"),
                None,
            )
            return (
                vector is not None
                and all(vector.get(key) == value for key, value in vector_field.items())
                and set(filter_paths).issubset({
                    field.get("path") for field in fields if field.get("type") == "filter"
                })
            )

        try:
            indexes = list(self.collection.list_search_indexes())
            current = next(
                (index for index in indexes
                 if index["name"] == "memory_vector_index"),
                None,
            )
            if current is None:
                self.collection.create_search_index(model=model)
            else:
                # Keep Atlas's existing fields and add any required retrieval filters.
                current_definition = current.get("latestDefinition", {})
                fields = list(current_definition.get("fields", []))
                existing_vector = next(
                    (field for field in fields
                     if field.get("type") == "vector"
                     and field.get("path") == "embedding"),
                    None,
                )
                vector_mismatch = not existing_vector or any(
                    existing_vector.get(key) != value for key, value in vector_field.items()
                )
                if vector_mismatch:
                    raise RuntimeError(
                        "memory_vector_index must index embedding with the configured Voyage "
                        f"dimension ({self.vector_dimensions}) and cosine similarity."
                    )

                indexed_filters = {
                    field.get("path") for field in fields if field.get("type") == "filter"
                }
                missing_filters = [path for path in filter_paths if path not in indexed_filters]
                if missing_filters:
                    fields.extend({"type": "filter", "path": path} for path in missing_filters)
                    self.collection.update_search_index(
                        "memory_vector_index",
                        {**current_definition, "fields": fields},
                    )

            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                current = next(
                    (index for index in self.collection.list_search_indexes()
                     if index["name"] == "memory_vector_index"),
                    None,
                )
                if current:
                    shards = current.get("statusDetail", [])
                    active_on_all_shards = all(
                        shard.get("status") == "READY"
                        and shard.get("queryable")
                        and has_required_fields(
                            shard.get("mainIndex", {}).get("definition", {}).get("fields", [])
                        )
                        for shard in shards
                    )
                    if (
                        current.get("status") == "READY"
                        and current.get("queryable")
                        and has_required_fields(
                            current.get("latestDefinition", {}).get("fields", [])
                        )
                        and active_on_all_shards
                    ):
                        return
                time.sleep(2)
            raise RuntimeError("memory_vector_index did not become queryable within 120 seconds.")
        except Exception as error:
            raise RuntimeError(
                "MongoDB Vector Search is unavailable. Use a supported MongoDB deployment "
                "with its mongot search process running; no Python search fallback is used."
            ) from error

    def relevant_memories(
        self, query, limit=8, sources=None, types=None, recency_days=None
    ):
        """Return active memories using MongoDB vector search and indexed filters."""
        now = datetime.now(timezone.utc)
        query_vector = self.voyage.embed(
            [query],
            model=self.voyage_model,
            input_type="query",
            output_dimension=self.vector_dimensions,
        ).embeddings[0]
        filters = [{"expires_at": {"$gt": now}}]
        if sources:
            filters.append({"source": {"$in": sources}})
        if types:
            filters.append({"type": {"$in": types}})
        if recency_days is not None:
            filters.append({"created_at": {"$gte": now - timedelta(days=recency_days)}})
        pre_filter = filters[0] if len(filters) == 1 else {"$and": filters}

        return list(self.collection.aggregate([
            {
                "$vectorSearch": {
                    "index": "memory_vector_index",
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(100, limit * 20),
                    "limit": limit,
                    "filter": pre_filter,
                }
            },
            {"$project": {"_id": 0, "memory_key": 1, "type": 1, "content": 1}},
        ]))

    def replace_memories(self, memories, session_id, retire_keys=()):
        """Save the updated retrieved subset and retire omitted matching memories."""
        now = datetime.now(timezone.utc)
        keep = set()
        items = []

        for item in memories:
            if item["type"] not in MEMORY_TTL_DAYS_BY_TYPE:
                raise ValueError(f"Unsupported memory type: {item['type']}")
            memory_key = hashlib.sha256(
                json.dumps([item["type"], item["content"]], ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            items.append((memory_key, item))

        # Voyage accepts multiple texts per request; type remains MongoDB metadata.
        vectors = []
        for start in range(0, len(items), 1000):
            batch = items[start:start + 1000]
            vectors.extend(self.voyage.embed(
                [item["content"] for _, item in batch],
                model=self.voyage_model,
                input_type="document",
                output_dimension=self.vector_dimensions,
            ).embeddings)

        prepared = []
        for (memory_key, item), vector in zip(items, vectors):
            keep.add(memory_key)
            prepared.append((memory_key, item, vector))

        for memory_key, item, vector in prepared:
            self.collection.update_one(
                {"memory_key": memory_key},
                {
                    "$set": {
                        "embedding": vector,
                        "updated_at": now,
                        "expires_at": now + timedelta(
                            days=MEMORY_TTL_DAYS_BY_TYPE[item["type"]]
                        ),
                        "ttl_policy_version": MEMORY_TTL_POLICY_VERSION,
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
