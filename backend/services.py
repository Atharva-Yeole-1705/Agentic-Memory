import json
import time
from collections import deque
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from bson import ObjectId
from groq import Groq
import httpx

from .config import get_settings


class EmbeddingRateLimitError(RuntimeError):
    """The embedding provider asked us to slow down."""


class GroqBudgetExceededError(RuntimeError):
    """The application's conservative rolling Groq budget is exhausted."""


_groq_budget_lock = Lock()
_groq_reservations: deque[tuple[float, int]] = deque()


def _estimate_tokens(messages: list[dict[str, str]]) -> int:
    # A conservative character-based estimate avoids adding a second tokenizer dependency.
    return sum((len(message["content"]) + 3) // 4 + 4 for message in messages)


def _trim_messages(messages: list[dict[str, str]], max_chars: int) -> list[dict[str, str]]:
    """Keep the system instruction and newest context within a hard input-size limit."""
    if not messages:
        return messages
    system = messages[0] if messages[0].get("role") == "system" else None
    remaining = max_chars - (len(system["content"]) if system else 0)
    result: list[dict[str, str]] = []
    for message in reversed(messages[1:] if system else messages):
        if remaining <= 0:
            break
        content = message["content"]
        if len(content) > remaining:
            content = content[-remaining:]
        result.append({**message, "content": content})
        remaining -= len(content)
    result.reverse()
    if system:
        return [system, *result]
    return result


def _reserve_groq_tokens(messages: list[dict[str, str]], max_completion_tokens: int) -> None:
    settings = get_settings()
    reservation = _estimate_tokens(messages) + max_completion_tokens
    now = time.monotonic()
    with _groq_budget_lock:
        while _groq_reservations and now - _groq_reservations[0][0] >= 60:
            _groq_reservations.popleft()
        used = sum(tokens for _, tokens in _groq_reservations)
        if used + reservation > settings.groq_window_token_budget:
            wait_seconds = max(1, int(60 - (now - _groq_reservations[0][0]))) if _groq_reservations else 60
            raise GroqBudgetExceededError(
                f"Groq safety budget reached. Wait about {wait_seconds} seconds before sending another message."
            )
        _groq_reservations.append((now, reservation))

SYSTEM_PROMPT = """You are a helpful coding assistant. Use the supplied long-term memory when it is relevant.
If memories conflict, favor the newest memory and mention the conflict when it affects your answer."""

EXTRACTOR_PROMPT = """You maintain long-term memory for a coding assistant. Read the user message and return JSON only.
Extract only durable project facts, decisions, constraints, preferences, lessons, or ongoing goals.
Do not store credentials, secrets, or transient questions. A correction should supersede an existing fact.
Schema: {"memories":[{"content":"concise statement","memory_type":"fact|preference|decision|constraint|goal|lesson","expires_at":null}]}
If nothing is durable, return {"memories":[]}."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def retrieval_deadline(expires_at: datetime | None = None) -> datetime:
    """A filterable date used by vector search; TTL continues to use expires_at."""
    return expires_at or datetime(9999, 12, 31, tzinfo=UTC)


def serialize(document: dict[str, Any]) -> dict[str, Any]:
    document = document.copy()
    document["id"] = str(document.pop("_id"))
    # Embeddings are internal search data and must not be sent to the browser.
    document.pop("embedding", None)
    document.pop("retrieval_until", None)
    for key in ("created_at", "updated_at", "expires_at"):
        if document.get(key):
            document[key] = document[key].isoformat()
    return document


def embed_texts(texts: list[str], input_type: str) -> list[list[float]]:
    settings = get_settings()
    if not settings.voyage_api_key:
        raise RuntimeError("VOYAGE_API_KEY is not configured. Semantic memory requires a Voyage embedding key.")
    for attempt in range(3):
        try:
            response = httpx.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.voyage_api_key}"},
                json={"input": texts, "model": settings.voyage_embedding_model,
                      "input_type": input_type, "output_dimension": settings.voyage_embedding_dimensions},
                timeout=20,
            )
            if response.status_code == 429:
                if attempt == 2:
                    raise EmbeddingRateLimitError("Voyage AI is rate-limiting embedding requests. Wait a minute, then try again.")
                delay = min(float(response.headers.get("Retry-After", 2 ** attempt)), 10)
                time.sleep(delay)
                continue
            response.raise_for_status()
            embeddings = [item["embedding"] for item in response.json()["data"]]
            if len(embeddings) != len(texts) or any(len(item) != settings.voyage_embedding_dimensions for item in embeddings):
                raise RuntimeError("Embedding dimensions do not match VOYAGE_EMBEDDING_DIMENSIONS.")
            return embeddings
        except EmbeddingRateLimitError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            if attempt == 2:
                raise RuntimeError(f"Embedding request failed: {error}") from error
            time.sleep(2 ** attempt)
    raise RuntimeError("Embedding request failed.")


def embed_text(text: str, input_type: str) -> list[float]:
    try:
        return embed_texts([text], input_type)[0]
    except EmbeddingRateLimitError:
        raise
    except RuntimeError as error:
        raise RuntimeError(f"Embedding request failed: {error}") from error


def relevant_memories(database, owner_id: str, workspace_id: str, prompt: str, limit: int = 8):
    now = utc_now()
    settings = get_settings()
    query_embedding = embed_text(prompt, "query")
    pipeline = [
        {"$vectorSearch": {
            "index": settings.mongodb_vector_index,
            "path": "embedding",
            "queryVector": query_embedding,
            "numCandidates": max(limit * 20, 100),
            "limit": limit,
            "filter": {"owner_id": owner_id, "workspace_id": workspace_id,
                       "retrieval_until": {"$gt": now}},
        }},
        {"$set": {"vector_score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},
    ]
    return list(database.memories.aggregate(pipeline))


def invoke_chat(messages: list[dict[str, str]], temperature: float, max_completion_tokens: int | None = None) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    output_limit = max_completion_tokens or settings.groq_answer_max_tokens
    bounded_messages = _trim_messages(messages, settings.groq_max_input_chars)
    _reserve_groq_tokens(bounded_messages, output_limit)
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model, messages=bounded_messages, temperature=temperature,
        max_completion_tokens=output_limit,
    )
    return response.choices[0].message.content or ""


def extract_memories(prompt: str) -> list[dict[str, Any]]:
    raw = invoke_chat([
        {"role": "system", "content": EXTRACTOR_PROMPT},
        {"role": "user", "content": prompt},
    ], temperature=0, max_completion_tokens=get_settings().groq_memory_max_tokens)
    try:
        data = json.loads(raw.removeprefix("```json").removesuffix("```").strip())
        return data.get("memories", []) if isinstance(data, dict) else []
    except json.JSONDecodeError:
        return []


def persist_extracted_memories(database, owner_id: str, workspace_id: str, prompt: str):
    now = utc_now()
    candidates = []
    for item in extract_memories(prompt):
        content = str(item.get("content", "")).strip()
        memory_type = str(item.get("memory_type", "fact"))
        if not content or memory_type not in {"fact", "preference", "decision", "constraint", "goal", "lesson"}:
            continue
        candidates.append((content, memory_type))
    embeddings = embed_texts([content for content, _ in candidates], "document") if candidates else []
    for (content, memory_type), embedding in zip(candidates, embeddings):
        # Same statement updates its timestamp rather than creating duplicate memory.
        now = utc_now()
        database.memories.update_one(
            {"owner_id": owner_id, "workspace_id": workspace_id, "content": content},
            {"$set": {"memory_type": memory_type, "updated_at": now, "source": "assistant-extracted",
                      "embedding": embedding, "retrieval_until": retrieval_deadline()},
             "$setOnInsert": {"created_at": now, "expires_at": None}},
            upsert=True,
        )


def object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise ValueError("Invalid resource id")
    return ObjectId(value)
