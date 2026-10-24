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

The current retriever is deterministic lexical relevance plus recency ranking. For semantic recall, replace `relevant_memories` in `backend/services.py` with an Atlas `$vectorSearch` stage after choosing an embedding provider and creating its vector index.
