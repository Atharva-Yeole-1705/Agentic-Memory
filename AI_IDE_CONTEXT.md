# Agentic Memory — AI IDE Handoff Context

## Project objective

Convert the original Python command-line coding chatbot into a full-stack web application for the **Agentic Memory** challenge. The application must retain useful information between sessions and visibly use retrieved memory to influence later answers.

The user specifically requires:

- A TypeScript/TSX frontend.
- A robust Python backend.
- MongoDB Atlas only; do **not** require a local MongoDB server.
- Persistent session history and long-term memory.
- MongoDB Vector Search for semantic memory retrieval.
- Groq for chat completion and a separate long-term-memory extraction pass.
- Conservative protection against an 8,000 TPM Groq limit.

Never expose or commit any API key, password, or complete MongoDB URI.

## Current architecture

```text
React + TypeScript frontend (Vite, port 5173)
        |
        | HTTP JSON
        v
FastAPI backend (port 8000)
        |
        +-- MongoDB Atlas
        |     - sessions collection
        |     - memories collection
        |     - TTL expiry index
        |     - Atlas Vector Search index: memory_vector_index
        |
        +-- Voyage AI embeddings (voyage-3.5-lite, 1024 dimensions)
        |
        +-- Groq (openai/gpt-oss-120b)
              - coding-assistant response
              - long-term-memory extraction
```

## Implemented behavior

### Session memory

- Each conversation is stored in MongoDB `sessions`.
- Each session contains its own ordered `messages` array.
- The UI supports creating and selecting sessions.

### Long-term memory

- A memory document stores `owner_id`, `workspace_id`, `memory_type`, `content`, `source`, `created_at`, `updated_at`, `expires_at`, `retrieval_until`, and an internal `embedding`.
- Supported memory types: `fact`, `preference`, `decision`, `constraint`, `goal`, and `lesson`.
- The memory extractor uses a dedicated Groq call and returns only durable information.
- Duplicate extracted content updates the existing record instead of creating another identical memory.
- The UI can create and delete manual memories.
- Embeddings are intentionally removed before data is sent to the browser.

### Semantic retrieval

- `backend/services.py` embeds the user query with Voyage AI.
- `relevant_memories()` performs an Atlas `$vectorSearch` query over `memories.embedding`.
- Search is pre-filtered by `owner_id`, `workspace_id`, and `retrieval_until`.
- The top semantic matches are placed in the Groq system context before the assistant response is generated.
- The frontend highlights memories returned by the latest retrieval, so the effect of memory is visible.

### Lifecycle and deletion

- MongoDB TTL index exists on `expires_at`.
- `retrieval_until` is a date used to exclude expired memories from vector retrieval. Non-expiring memories receive a far-future retrieval deadline.
- Manual delete API/UI support exists.
- Automatic deletion when a feature flag changes is **not implemented**.

### Groq protection

Every user message normally involves two Groq requests: one assistant response and one memory-extraction response.

- Assistant completion cap: 500 tokens.
- Memory extractor completion cap: 180 tokens.
- Input context cap: 18,000 characters.
- Local rolling 60-second reservation: 7,000 estimated tokens.
- Requests exceeding the local budget return HTTP 429 and a suggested wait time.
- This is a conservative local guard. Groq's account-level headers and limits remain authoritative, and other applications using the same Groq organization also count toward the organization limit.

## Key files

| Path | Purpose |
|---|---|
| `backend/main.py` | FastAPI routes for health, sessions, messages, and memory CRUD. |
| `backend/services.py` | Groq calls, memory extraction, Voyage embeddings, `$vectorSearch`, token guard, serialization. |
| `backend/database.py` | Cached Mongo client and MongoDB indexes. |
| `backend/config.py` | Typed `.env` configuration. |
| `backend/vector_index.json` | Atlas Vector Search definition. |
| `backend/create_vector_index.py` | Creates `memory_vector_index` with PyMongo. |
| `backend/backfill_embeddings.py` | Adds vectors/retrieval deadlines to memories created before vector search. |
| `frontend/src/main.tsx` | React application UI. |
| `frontend/src/api.ts` | Backend API client. |
| `frontend/src/styles.css` | Main styling. |
| `frontend/src/retrieval.css` | Highlight styling for retrieved memory. |
| `.env.web.example` | Safe configuration template. |
| `README-WEB.md` | User-facing setup guide. |

## Required environment variables

Create a private `.env` in the repository root. Do not place real secrets in tracked files.

```env
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b

MONGODB_URI=mongodb+srv://...
MONGODB_DATABASE=agentic_memory
MONGODB_VECTOR_INDEX=memory_vector_index
ALLOWED_ORIGIN=http://localhost:5173

VOYAGE_API_KEY=...
VOYAGE_EMBEDDING_MODEL=voyage-3.5-lite
VOYAGE_EMBEDDING_DIMENSIONS=1024

GROQ_WINDOW_TOKEN_BUDGET=7000
GROQ_MAX_INPUT_CHARS=18000
GROQ_ANSWER_MAX_TOKENS=500
GROQ_MEMORY_MAX_TOKENS=180
```

## Atlas setup requirements

1. Atlas database user and Network Access allowlist must permit the application machine.
2. Atlas must support Search/Vector Search. Confirm the cluster tier supports it before proceeding; a free cluster may not.
3. Create `memory_vector_index` on database `agentic_memory`, collection `memories`, using `backend/vector_index.json`, or run `python -m backend.create_vector_index`.
4. Wait until the Atlas index state is `READY` and queryable.
5. Run `python -m backend.backfill_embeddings` once for memory records created before vector search was added.

## Run commands

Backend, from repository root:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Frontend, from another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. API documentation is available at `http://localhost:8000/docs`.

## Current operational findings

- Atlas connectivity was verified successfully.
- `memory_vector_index` was verified as `READY` and queryable.
- Voyage embedding connectivity was verified and returns 1024-dimensional embeddings.
- Groq connectivity was verified.
- The frontend production build and Python compilation passed after the implemented changes.
- Voyage returned HTTP 429 during rapid testing. The backend now batches extracted-memory embeddings and retries temporary 429s before returning a clear client error. If the issue persists, wait for the provider's rate-limit window or check the Voyage API account quota.

## Known limitations / next work

- Authentication is not implemented. The app currently uses `demo-user` and workspace `default`; replace them with authenticated identity before production use.
- Memory type and recency filtering are present in schema/index design but are not exposed as frontend search controls.
- Change Streams/WebSockets for multi-user live updates are not implemented.
- Feature-flag-driven memory invalidation is not implemented.
- There are no automated backend/API tests yet.
- Vector index creation and end-to-end live chat should be retested after provider rate limits reset.
- The original CLI prototype remains in `main.py`; the web app is the intended current implementation.

## Safety and implementation rules for the next AI

- Do not remove the semantic `$vectorSearch` flow or silently fall back to keyword-only retrieval.
- Do not return embedding arrays to the browser.
- Keep the TTL lifecycle behavior and owner/workspace filters.
- Keep Groq calls bounded; do not increase limits without checking the user's actual Groq account limits.
- Do not log or display secrets, MongoDB URIs, API keys, or database passwords.
- Preserve existing user changes and avoid destructive Git commands.
