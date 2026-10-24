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
- Each memory's **content only** is sent to Voyage with `input_type="document"`. Its type is stored as MongoDB metadata and is not included in the embedding text.
- Stored fields include `type`, `content`, `embedding`, `source` session ID, `created_at`, `updated_at`, `expires_at`, and a content-derived `memory_key`.
- A TTL index on `expires_at` expires memories after `MEMORY_TTL_DAYS` (365 days by default). MongoDB's TTL cleanup is asynchronous.
- For each new prompt, the app embeds it with `input_type="query"`, scans active MongoDB embeddings in Python, ranks them using cosine similarity, and supplies up to the top 8 to both agents. This is an exact application-side scan, not MongoDB Atlas Vector Search.
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
- `MONGODB_URI` - defaults to `mongodb://localhost:27017`.
- `MONGODB_DATABASE` - defaults to `agentic_memory`.
- `MEMORY_TTL_DAYS` - defaults to `365` and must be at least 1.

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
