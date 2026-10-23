# Coding Assistant

A small command-line coding chatbot built with Python, LangChain, and Groq. It supports multiple sessions, saves each conversation in its own JSON file under `sessions/`, and keeps concise shared long-term memory in the git-ignored `memory.txt` file.

## Setup

1. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. A local, git-ignored `.env` is configured with the provided Groq key. Edit it if you need to replace the key. `.env.example` documents the settings. The default model is `openai/gpt-oss-120b`; set `GROQ_MODEL` in `.env` to change it.

4. Start the chatbot:

   ```powershell
   python main.py
   ```

Each user prompt is sent to both the coding assistant and a long-term memory extractor. It keeps durable project facts, technical decisions, constraints, preferences, lessons, and goals in `memory.txt`, applies corrections and forget requests, and prints its complete updated memory after the assistant's reply. Choose **New session** to start a conversation or **Resume session** to continue one. Type `/back` during a conversation to return to the menu.

To test only the memory extractor, set `SUMMARIZER_ONLY=true` in `.env`. Prompts then skip the coding assistant and are not added to session chat history, while the shared memory is still updated. Set it to `false` to restore normal chat mode.
