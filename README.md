# Coding Assistant

A coding assistant built with Python, LangChain, Groq, Voyage embeddings, and local MongoDB. It has a Python CLI and a React + Vite web frontend. Chat sessions stay in `sessions/`; long-term memories are saved in MongoDB and can be used across sessions.

## Setup

1. Start your local MongoDB server.
2. Create a virtual environment and install packages:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. If `.env` does not exist, copy `.env.example` to `.env`; set `GROQ_API_KEY` and `VOYAGE_API_KEY`. The default MongoDB URI is `mongodb://localhost:27017`.
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

The app creates a TTL index on `expires_at`. Memories expire after `MEMORY_TTL_DAYS` (365 days by default), counted from their latest save. Change that setting in `.env` to adjust retention.

The summarizer returns a JSON object containing a `memories` array. The app sends each memory's text alone to Voyage, then stores its type, text, embedding, source session ID, timestamps, and expiry in the `memories` collection. The memory type is not sent to Voyage. For each user prompt, the app embeds it as a Voyage query, ranks active MongoDB memories by cosine similarity, and sends the top 8 to both the coding assistant and summariser. This uses an exact scan of stored vectors in local Python; it does not require MongoDB Atlas Vector Search. The summariser updates only the retrieved subset, leaving other stored memories intact.

Set `SUMMARIZER_ONLY=true` in `.env` to skip coding assistant calls while trying the summarizer.
