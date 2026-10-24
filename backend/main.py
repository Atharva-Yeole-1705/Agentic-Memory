from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import APIError
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from .config import get_settings
from .database import get_database
from .schemas import MemoryCreate, MemoryUpdate, MessageCreate, SessionCreate
from .services import EmbeddingRateLimitError, GroqBudgetExceededError, SYSTEM_PROMPT, embed_text, invoke_chat, object_id, persist_extracted_memories, relevant_memories, retrieval_deadline, serialize

settings = get_settings()
app = FastAPI(title="Agentic Memory API", version="1.0.0")
cors_origins = [origin.strip() for origin in settings.allowed_origin.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    get_database().command("ping")
    return {"status": "ok"}


@app.post("/api/sessions", status_code=201)
def create_session(payload: SessionCreate):
    now = datetime.now(UTC)
    document = payload.model_dump() | {"messages": [], "created_at": now, "updated_at": now}
    result = get_database().sessions.insert_one(document)
    return serialize(get_database().sessions.find_one({"_id": result.inserted_id}))


@app.get("/api/sessions")
def list_sessions(owner_id: str = "demo-user", workspace_id: str = "default"):
    records = get_database().sessions.find({"owner_id": owner_id, "workspace_id": workspace_id}).sort("updated_at", -1)
    return [serialize(record) for record in records]


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    try:
        record = get_database().sessions.find_one({"_id": object_id(session_id)})
    except ValueError as error:
        raise HTTPException(400, str(error))
    if not record:
        raise HTTPException(404, "Session not found")
    return serialize(record)


@app.post("/api/sessions/{session_id}/messages")
def send_message(session_id: str, payload: MessageCreate):
    database = get_database()
    try:
        session = database.sessions.find_one({"_id": object_id(session_id)})
    except ValueError as error:
        raise HTTPException(400, str(error))
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        memories = relevant_memories(database, session["owner_id"], session["workspace_id"], payload.content)
        memory_context = "\n".join(f"- [{m.get('memory_type', 'fact')}] {m.get('content', '')}" for m in memories) or "No relevant memories."
        history = session["messages"][-20:]
        messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nRelevant long-term memory:\n{memory_context}"}, *history, {"role": "user", "content": payload.content}]
        reply = invoke_chat(messages, temperature=0.2)
        persist_extracted_memories(database, session["owner_id"], session["workspace_id"], payload.content)
    except EmbeddingRateLimitError as error:
        raise HTTPException(429, str(error))
    except GroqBudgetExceededError as error:
        raise HTTPException(429, str(error))
    except (RuntimeError, APIError, PyMongoError) as error:
        raise HTTPException(503, f"Upstream service failed: {error}")
    now = datetime.now(UTC)
    exchange = [{"role": "user", "content": payload.content}, {"role": "assistant", "content": reply}]
    database.sessions.update_one({"_id": session["_id"]}, {"$push": {"messages": {"$each": exchange}}, "$set": {"updated_at": now}})
    return {"reply": reply, "retrieved_memories": [serialize(item) for item in memories]}


@app.get("/api/memories")
def list_memories(owner_id: str = "demo-user", workspace_id: str = "default"):
    records = get_database().memories.find({"owner_id": owner_id, "workspace_id": workspace_id}).sort("updated_at", -1)
    return [serialize(record) for record in records]


@app.post("/api/memories", status_code=201)
def create_memory(payload: MemoryCreate):
    now = datetime.now(UTC)
    document = payload.model_dump() | {"owner_id": "demo-user", "workspace_id": "default", "source": "manual", "created_at": now, "updated_at": now,
                                       "embedding": embed_text(payload.content, "document"), "retrieval_until": retrieval_deadline(payload.expires_at)}
    result = get_database().memories.insert_one(document)
    return serialize(get_database().memories.find_one({"_id": result.inserted_id}))


@app.patch("/api/memories/{memory_id}")
def update_memory(memory_id: str, payload: MemoryUpdate):
    try:
        changes = payload.model_dump(exclude_unset=True)
        if "content" in changes:
            changes["embedding"] = embed_text(changes["content"], "document")
        if "expires_at" in changes:
            changes["retrieval_until"] = retrieval_deadline(changes["expires_at"])
        result = get_database().memories.find_one_and_update({"_id": object_id(memory_id)}, {"$set": changes | {"updated_at": datetime.now(UTC)}}, return_document=ReturnDocument.AFTER)
    except ValueError as error:
        raise HTTPException(400, str(error))
    if not result:
        raise HTTPException(404, "Memory not found")
    return serialize(result)


@app.delete("/api/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: str):
    try:
        result = get_database().memories.delete_one({"_id": object_id(memory_id)})
    except ValueError as error:
        raise HTTPException(400, str(error))
    if not result.deleted_count:
        raise HTTPException(404, "Memory not found")
