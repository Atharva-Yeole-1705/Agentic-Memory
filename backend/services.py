import json
import re
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from groq import Groq

from .config import get_settings

SYSTEM_PROMPT = """You are a helpful coding assistant. Use the supplied long-term memory when it is relevant.
If memories conflict, favor the newest memory and mention the conflict when it affects your answer."""

EXTRACTOR_PROMPT = """You maintain long-term memory for a coding assistant. Read the user message and return JSON only.
Extract only durable project facts, decisions, constraints, preferences, lessons, or ongoing goals.
Do not store credentials, secrets, or transient questions. A correction should supersede an existing fact.
Schema: {"memories":[{"content":"concise statement","memory_type":"fact|preference|decision|constraint|goal|lesson","expires_at":null}]}
If nothing is durable, return {"memories":[]}."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def serialize(document: dict[str, Any]) -> dict[str, Any]:
    document = document.copy()
    document["id"] = str(document.pop("_id"))
    for key in ("created_at", "updated_at", "expires_at"):
        if document.get(key):
            document[key] = document[key].isoformat()
    return document


def relevant_memories(database, owner_id: str, workspace_id: str, prompt: str, limit: int = 8):
    now = utc_now()
    documents = list(database.memories.find({
        "owner_id": owner_id,
        "workspace_id": workspace_id,
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}],
    }).sort("updated_at", -1).limit(100))
    tokens = set(re.findall(r"[a-zA-Z0-9_+-]{3,}", prompt.lower()))
    def score(item):
        words = set(re.findall(r"[a-zA-Z0-9_+-]{3,}", item["content"].lower()))
        return len(tokens & words)
    # Lexical retrieval is deterministic and works on local MongoDB. Replace this with
    # an Atlas $vectorSearch stage once embeddings/vector index are provisioned.
    return sorted(documents, key=lambda item: (score(item), item["updated_at"]), reverse=True)[:limit]


def invoke_chat(messages: list[dict[str, str]], temperature: float) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model, messages=messages, temperature=temperature,
    )
    return response.choices[0].message.content or ""


def extract_memories(prompt: str) -> list[dict[str, Any]]:
    raw = invoke_chat([
        {"role": "system", "content": EXTRACTOR_PROMPT},
        {"role": "user", "content": prompt},
    ], temperature=0)
    try:
        data = json.loads(raw.removeprefix("```json").removesuffix("```").strip())
        return data.get("memories", []) if isinstance(data, dict) else []
    except json.JSONDecodeError:
        return []


def persist_extracted_memories(database, owner_id: str, workspace_id: str, prompt: str):
    now = utc_now()
    for item in extract_memories(prompt):
        content = str(item.get("content", "")).strip()
        memory_type = str(item.get("memory_type", "fact"))
        if not content or memory_type not in {"fact", "preference", "decision", "constraint", "goal", "lesson"}:
            continue
        # Same statement updates its timestamp rather than creating duplicate memory.
        database.memories.update_one(
            {"owner_id": owner_id, "workspace_id": workspace_id, "content": content},
            {"$set": {"memory_type": memory_type, "updated_at": now, "source": "assistant-extracted"},
             "$setOnInsert": {"created_at": now, "expires_at": None}},
            upsert=True,
        )


def object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise ValueError("Invalid resource id")
    return ObjectId(value)
