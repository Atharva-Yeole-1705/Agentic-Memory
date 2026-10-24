"""HTTP API used by the React frontend."""

import json
import os
import re
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from main import (
    BASE_DIR,
    MEMORY_LIMIT,
    MEMORY_TYPES,
    SESSIONS_DIR,
    SUMMARIZER_PROMPT,
    SYSTEM_PROMPT,
    new_session,
    parse_memories,
)
from memory_store import MemoryStore

load_dotenv(BASE_DIR / ".env")


@asynccontextmanager
async def lifespan(app):
    groq_key = os.getenv("GROQ_API_KEY")
    voyage_key = os.getenv("VOYAGE_API_KEY")
    if not groq_key or not voyage_key:
        raise RuntimeError("Set GROQ_API_KEY and VOYAGE_API_KEY in .env.")

    app.state.memory_store = MemoryStore(
        os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        os.getenv("MONGODB_DATABASE", "agentic_memory"),
        voyage_key,
        os.getenv("VOYAGE_MODEL", "voyage-4-lite"),
        int(os.getenv("VOYAGE_DIMENSIONS", "1024")),
    )
    app.state.summarizer_only = os.getenv("SUMMARIZER_ONLY", "false").lower() in {
        "1", "true", "yes"
    }
    app.state.model = None if app.state.summarizer_only else ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_key=groq_key,
        temperature=0.2,
        reasoning_format="hidden",
    )
    app.state.summarizer = ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_key=groq_key,
        temperature=0,
        reasoning_format="hidden",
    )
    SESSIONS_DIR.mkdir(exist_ok=True)
    yield
    app.state.memory_store.client.close()


app = FastAPI(title="Coding Assistant API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class MemoryFilters(BaseModel):
    sources: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    recency_days: int | None = Field(default=None, ge=1)


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    memory_filters: MemoryFilters = Field(default_factory=MemoryFilters)


def session_path(session_id: str):
    if not re.fullmatch(r"[a-f0-9]{8}", session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Session not found.")
    return path


@app.get("/api/status")
def get_status(request: Request):
    return {
        "summarizer_only": request.app.state.summarizer_only,
        "memory_types": sorted(MEMORY_TYPES),
    }


@app.get("/api/sessions")
def get_sessions():
    sessions = []
    paths = sorted(
        SESSIONS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True
    )
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        first_user_message = next(
            (message["content"] for message in data["messages"] if message["role"] == "user"),
            "New conversation",
        )
        sessions.append({
            "id": path.stem,
            "created_at": data.get("created_at"),
            "title": first_user_message[:52],
            "message_count": len(data["messages"]),
        })
    return {"sessions": sessions}


@app.post("/api/sessions", status_code=201)
def create_session():
    path, data = new_session()
    return {"id": path.stem, **data}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    path = session_path(session_id)
    return {"id": session_id, **json.loads(path.read_text(encoding="utf-8"))}


@app.post("/api/sessions/{session_id}/messages")
def send_message(session_id: str, body: ChatRequest, request: Request):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message cannot be blank.")

    path = session_path(session_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    services = request.app.state
    filters = body.memory_filters
    if any(not re.fullmatch(r"[a-f0-9]{8}", source) for source in filters.sources):
        raise HTTPException(status_code=422, detail="Invalid conversation filter.")
    if any(memory_type not in MEMORY_TYPES for memory_type in filters.types):
        raise HTTPException(status_code=422, detail="Invalid memory type filter.")

    memories = services.memory_store.relevant_memories(
        content,
        limit=MEMORY_LIMIT,
        sources=filters.sources,
        types=filters.types,
        recency_days=filters.recency_days,
    )
    assistant_reply = None

    if not services.summarizer_only:
        system_prompt = SYSTEM_PROMPT
        if memories:
            context = "\n".join(
                f"- [{item['type']}] {item['content']}" for item in memories
            )
            system_prompt += f"\n\nLong-term memory:\n{context}"

        messages = [SystemMessage(content=system_prompt)]
        for item in data["messages"]:
            message_type = HumanMessage if item["role"] == "user" else AIMessage
            messages.append(message_type(content=item["content"]))
        messages.append(HumanMessage(content=content))
        try:
            assistant_reply = services.model.invoke(messages).content
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"Coding assistant failed: {error}")

        data["messages"].extend([
            {"role": "user", "content": content},
            {"role": "assistant", "content": assistant_reply},
        ])
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    else:
        data["messages"].append({"role": "user", "content": content})
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    existing_memory = json.dumps(
        [{"type": item["type"], "content": item["content"]} for item in memories],
        ensure_ascii=False,
        indent=2,
    )
    summary_input = (
        f"RELEVANT EXISTING MEMORIES (top {MEMORY_LIMIT}):\n{existing_memory}"
        f"\n\nLATEST USER MESSAGE:\n{content}"
    )
    summary_output = None
    memory_error = None
    try:
        summary_output = services.summarizer.invoke([
            SystemMessage(content=SUMMARIZER_PROMPT),
            HumanMessage(content=summary_input),
        ]).content.strip()
        updated_memories = parse_memories(summary_output)
        services.memory_store.replace_memories(
            updated_memories,
            session_id,
            retire_keys=[item["memory_key"] for item in memories],
        )
    except Exception as error:
        memory_error = str(error)

    return {
        "assistant_reply": assistant_reply,
        "summarizer_output": summary_output,
        "memory_error": memory_error,
        "messages": data["messages"],
        "summarizer_only": services.summarizer_only,
    }
