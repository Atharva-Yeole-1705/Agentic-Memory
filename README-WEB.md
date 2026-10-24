# Agentic Memory Web App

This implementation upgrades the CLI prototype into a React/TypeScript application backed by FastAPI and MongoDB, while keeping its core behavior: answer a user, extract only durable context, and use the relevant context in later sessions.

## What it demonstrates

- Separate durable memories from per-session message history.
- Retrieve scoped, relevant memory before every answer, so memory visibly affects the response.
- Inspect, add, and delete memory in the UI.
- Store an owner, workspace, type, source, timestamps, and optional expiry for each memory.
- MongoDB TTL index on `expires_at` for automatic expiration.
- Explicit correction/deletion path through the memory API and UI.

## Prerequisites

- Python 3.11+
- Node.js 20+
- A free MongoDB Atlas cluster (no local MongoDB installation)
- A Groq API key

## Run it

From the repository root, create `.env` from the safe template and set your Groq key and Atlas MongoDB URI:

```powershell
Copy-Item .env.web.example .env
notepad .env
```

In MongoDB Atlas, create a free cluster, create a database user, allow your current IP address in **Network Access**, then copy its **Connect → Drivers → Python** connection string into `MONGODB_URI`. The database is created automatically on first use. Keep this URI private: it includes your database credentials.

Start the API in one PowerShell window:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Start the frontend in another:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). The backend API documentation is at `http://localhost:8000/docs`.

## Data model

`sessions` documents contain session-scoped messages. `memories` documents contain `owner_id`, `workspace_id`, `memory_type`, `content`, `source`, `created_at`, `updated_at`, and `expires_at`. TTL removes records after their expiry time.

## Groq rate-limit protection

The app caps a normal assistant answer at 500 completion tokens and the memory extractor at 180. It also trims overlong chat context and maintains a conservative 7,000-token rolling one-minute reservation across both calls, leaving headroom under an 8K TPM organization limit. Adjust `GROQ_*` controls in `.env` only if your account limit changes.

## Enable semantic memory with Atlas Vector Search

The app uses Voyage `voyage-3.5-lite` embeddings at 1024 dimensions and searches `memories.embedding` with MongoDB's `$vectorSearch` aggregation stage. Add this to `.env`:

```env
VOYAGE_API_KEY=your_voyage_api_key
VOYAGE_EMBEDDING_MODEL=voyage-3.5-lite
VOYAGE_EMBEDDING_DIMENSIONS=1024
MONGODB_VECTOR_INDEX=memory_vector_index
```

Your Atlas deployment must support Atlas Search/Vector Search. Create the vector index on database `agentic_memory`, collection `memories`, using [backend/vector_index.json](backend/vector_index.json), or run:

```powershell
python -m backend.create_vector_index
```

Wait until Atlas reports the index as **READY**, then add embeddings to any pre-existing memories:

```powershell
python -m backend.backfill_embeddings
```

New and edited memories receive an embedding. For each user message, the backend embeds the query and runs `$vectorSearch`, pre-filtered by owner, workspace, and retrieval deadline. It gives the top semantic matches to Groq and the frontend highlights the memories that were retrieved.
