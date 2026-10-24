# Coding Assistant

A coding assistant built with Python, LangChain, Groq, Voyage embeddings, and local MongoDB. It has a Python CLI and a React + Vite web frontend. Chat sessions stay in `sessions/`; long-term memories are saved in MongoDB and can be used across sessions.

See [documentation.md](documentation.md) for the architecture, request flow, memory model, API, and implementation boundaries.

## Setup

1. Start a MongoDB deployment with MongoDB Vector Search enabled. The app creates a vector search index and queries it with `$vectorSearch`; a regular standalone `mongod` without `mongot` is not sufficient.
2. Create a virtual environment and install packages:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. If `.env` does not exist, copy `.env.example` to `.env`; set `GROQ_API_KEY`, `VOYAGE_API_KEY`, and `MONGODB_URI` to your Atlas connection string. Ensure your current IP is allowed in Atlas Network Access and the database user can access the selected database.
4. Run the CLI app if you want to use the terminal interface:

   ```powershell
   python main.py
   ```

## Web app

Start the API from the project root in one terminal:

```powershell
uvicorn web_api:app --reload
```

In a second terminal, start the React + Vite frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal (usually `http://localhost:5173`). Keep the API and MongoDB running while using the web app.

The app creates a TTL index on `expires_at` and a MongoDB Vector Search index on `embedding` with an `expires_at` pre-filter. `VOYAGE_DIMENSIONS` defaults to 1024 and must match Voyage's embedding output. Memories expire after `MEMORY_TTL_DAYS` (365 days by default), counted from their latest save. Change that setting in `.env` to adjust retention.

The summarizer returns a JSON object containing a `memories` array. The app batches memory texts into Voyage embedding requests, then stores each type, text, embedding, source session ID, timestamps, and expiry in the `memories` collection. Memory types are not sent to Voyage. For each user prompt, the app creates a Voyage query embedding and asks MongoDB `$vectorSearch` for the top 8 active memories; both agents receive those matches. The summariser updates only the retrieved subset, leaving other stored memories intact.

MongoDB Vector Search requires a vector search index and a compatible MongoDB deployment with `mongot`; self-managed `mongot` also requires a replica set. Self-managed MongoDB on Windows does not have a native `mongot` binary; use a local Docker-based MongoDB Atlas Local deployment or another compatible setup. See the [MongoDB local development quickstart](https://www.mongodb.com/docs/search/self-managed/current/installation/quick-start/) and [self-managed platform limitations](https://www.mongodb.com/docs/search/self-managed/current/limitations/).

The app creates the `memory_vector_index` index through PyMongo when the cluster allows programmatic index creation. Atlas Free M0 clusters may require creating the same index in the Atlas UI first; use a cosine vector field on `embedding` and a filter field on `expires_at`.

Set `SUMMARIZER_ONLY=true` in `.env` to skip coding assistant calls while trying the summarizer.
