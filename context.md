# Project Context

## Overview

This project is a coding assistant with a Python CLI and a React + Vite web interface. It uses LangChain and Groq for the coding assistant and memory summariser, Voyage AI for embeddings, and local MongoDB for persistent long-term memory. Keep implementation clear and concise, with comments where they help explain non-obvious behavior. The frontend should stay minimalist and responsive.

## Main Components

- `main.py` - CLI, chat session handling, coding and summariser prompts, and validation of summariser JSON.
- `web_api.py` - FastAPI endpoints used by the browser frontend. It reuses prompts and session helpers from `main.py`.
- `memory_store.py` - MongoDB persistence, Voyage embeddings, TTL index setup, and similarity retrieval.
- `frontend/` - React + Vite UI. It lists sessions, renders Markdown replies, sends messages, and displays the summariser's latest memory result.
- `sessions/` - One JSON file per chat session, keyed by an 8-character hexadecimal session ID.
- `.env` - Local credentials and configuration. It is git-ignored; never copy secret values into docs or source code.

## Assistant and Summariser

- The default Groq model is `openai/gpt-oss-120b`, configured with `GROQ_MODEL`.
- Each user prompt is sent to the coding assistant and the long-term memory summariser unless `SUMMARIZER_ONLY=true`.
- The summariser returns JSON in this shape: `{"memories":[{"type":"...","content":"..."}]}`.
- Permitted memory types are `project_fact`, `technical_decision`, `business_rule`, `user_preference`, `lesson_learned`, `ongoing_goal`, and `project_milestone`.
- Summariser output is printed after the coding response in the CLI. In the web UI, the latest result appears in a collapsible memory update panel.
- Chat messages are saved in the session JSON. The web UI's summariser output is not part of the saved chat transcript.

## Long-Term Memory

- MongoDB defaults to `mongodb://localhost:27017`, database `agentic_memory`, collection `memories`.
- Each memory's **content only** is sent to Voyage with `input_type="document"`; multiple memories are batched per request to reduce rate-limit pressure. Its type is stored as MongoDB metadata and is not included in the embedding text. The Voyage client retries transient rate-limit errors.
- Stored fields include `type`, `content`, `embedding`, `source` session ID, `created_at`, `updated_at`, `expires_at`, and a content-derived `memory_key`.
- TTL by memory type: `project_fact` 365 days; `technical_decision`, `business_rule`, `ongoing_goal` 180 days; `user_preference`, `lesson_learned`, `project_milestone` 30 days. Expiry refreshes on each save; MongoDB's TTL cleanup is asynchronous. Existing records are migrated once from `updated_at` (or `created_at`).
- For each new prompt, the app embeds it with `input_type="query"` and uses MongoDB's `$vectorSearch` aggregation stage to retrieve up to the top 8 active memories for both agents. UI filters support selected conversation sources, memory types, and creation-date recency (1, 7, 14, 30, custom days, or forever). Defaults are all conversations, all types, and forever. There is no Python similarity-ranking fallback.
- `memory_store.py` creates a vector search index on `embedding` plus filter fields on `expires_at`, `source`, `type`, and `created_at`, and waits for those active fields to become queryable. `VOYAGE_DIMENSIONS` defaults to 1024 and must match the stored embeddings.
- The app's `.env` points to MongoDB Atlas (never copy its credential into docs). MongoDB Vector Search requires a compatible deployment; self-managed `mongot` requires a replica set. Native Windows `mongot` is unavailable, so local Windows development should use Docker-based MongoDB Atlas Local. The separately running local service was observed as standalone MongoDB 8.2.1 with no `mongot`; it cannot serve native vector search.
- The summariser updates the retrieved subset. Its returned records are upserted; retrieved records it omits are deleted. Records outside the retrieved subset remain stored.
- `memory.txt` and its legacy fallback have been removed. MongoDB is the only long-term memory store.
- Long-term memories and prompts are sent to the configured Voyage and Groq APIs as needed. Do not retain API keys or other credentials as memory.

## Web API

- `GET /api/status` - returns whether summariser-only mode is enabled.
- `GET /api/sessions` - lists sessions for the sidebar.
- `POST /api/sessions` - creates a session.
- `GET /api/sessions/{session_id}` - loads a session.
- `POST /api/sessions/{session_id}/messages` - runs retrieval, coding response, summarisation, and memory persistence.
- The API uses FastAPI CORS settings for the local Vite origins (`localhost:5173` and `127.0.0.1:5173`). The Vite development server proxies `/api` to `127.0.0.1:8000`.

## Configuration

Set these values in `.env`; use `.env.example` as a template. Keep actual keys private.

- `GROQ_API_KEY` - required Groq credential.
- `GROQ_MODEL` - defaults to `openai/gpt-oss-120b`.
- `SUMMARIZER_ONLY` - defaults to `false`; set `true` to skip coding responses.
- `VOYAGE_API_KEY` - required Voyage credential.
- `VOYAGE_MODEL` - defaults to `voyage-4-lite`.
- `MONGODB_URI` - configured in the ignored local `.env`; do not copy credentials into source files or documentation.
- `MONGODB_DATABASE` - defaults to `agentic_memory`.
- `VOYAGE_DIMENSIONS` - defaults to `1024`, matching `voyage-4-lite`'s default output dimension.

## Running Locally

Start MongoDB and install Python dependencies from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run the CLI:

```powershell
python main.py
```

For the web app, run the API in one terminal from the project root:

```powershell
uvicorn web_api:app --reload
```

Then run the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually `http://localhost:5173`.

## Current Verification State

The app and frontend have not been built or integration-tested in this workspace yet. Install the updated Python dependencies before running the API; install frontend packages with `npm install` before starting Vite.
