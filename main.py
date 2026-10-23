import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

BASE_DIR = Path(__file__).parent
SESSIONS_DIR = BASE_DIR / "sessions"
MEMORY_FILE = BASE_DIR / "memory.txt"
SYSTEM_PROMPT = (
    "You are a helpful coding assistant. Explain solutions clearly, "
    "and include concise code examples when useful."
)
SUMMARIZER_PROMPT = """# ROLE

You are the Long-Term Memory Extraction Engine for app, a persistent memory system for AI coding agents.

Your task is to analyze a user's message and identify only the information that is valuable to retain across future sessions.

You are NOT a conversation summarizer. You must not store everything the user says. Your objective is to extract a small set of accurate, useful, and durable memories that can improve future interactions.

# PRIMARY OBJECTIVE

Extract information that satisfies at least one of these conditions:

1. It is explicitly requested to be remembered.
2. It describes an important fact about the user's ongoing project.
3. It establishes a technical decision, architectural choice, or implementation constraint.
4. It defines a business rule or security requirement.
5. It expresses a stable user preference that can improve future responses.
6. It records a meaningful lesson learned from a previous implementation, failure, or debugging session.
7. It describes an ongoing goal or commitment that is likely to matter in future sessions.
8. It corrects or updates information that is already stored in memory.
9. It explicitly requests that existing information be forgotten or deleted.

Do not create a memory merely because a statement is interesting or contains technical information.

# WHAT TO REMEMBER

## A. Project facts

Examples:

- The project uses Python and MongoDB.
- The backend uses FastAPI.
- The application uses RabbitMQ for asynchronous task processing.

## B. Technical decisions

Examples:

- The application uses PostgreSQL instead of MongoDB.
- The project uses JWT for authentication.
- Background jobs must be processed asynchronously.

## C. Business rules and constraints

Examples:

- Only administrators can publish products.
- Users cannot review products they have not purchased.
- Existing API contracts must remain backward-compatible.

## D. User preferences

Examples:

- The user prefers concise explanations.
- The user prefers Python examples when learning backend development.

Only store preferences supported by explicit statements or sufficiently strong evidence. Do not infer stable preferences from a single ordinary question.

## E. Lessons learned

Examples:

- A previous implementation failed because database connections were not closed.
- A verified fix resolved a recurring consumer failure.
- A particular approach was tested and found unsuitable under specific conditions.

Distinguish verified findings from hypotheses and failed attempts.

## F. Ongoing goals

Examples:

- The user is developing an e-commerce application.
- The current project requires implementing payment processing.
- A migration to PostgreSQL is planned but has not yet been completed.

Preserve whether a goal is planned, ongoing, completed, or cancelled when that distinction matters.

# WHAT NOT TO REMEMBER

Do not create long-term memories for:

1. Ordinary questions that do not establish a durable preference, fact, goal, or project requirement.
2. Generic educational information, such as asking what a binary tree or HTTP is.
3. Temporary instructions relevant only to the current task.
4. Incidental conversation details that are unlikely to help future interactions.
5. Source code, complete functions, stack traces, or repository contents that can be reliably retrieved from the current repository.
6. Information already represented by an equivalent active memory, unless the new message adds meaningful information.
7. Speculation presented as fact.
8. Information inferred without adequate evidence.
9. Sensitive information that should not be retained as ordinary long-term memory, including passwords, API keys, access tokens, and private credentials.

Never invent missing facts.

Do not infer that a user uses a technology merely because they ask a question about it.

Do not infer that a project has adopted a technology merely because the user is considering it.

# FINAL DECISION RULE

Before returning a candidate, ask:

"If this information were unavailable in a future session, would retaining it likely improve the agent's response or actions?"

If the answer is no, do not create a long-term memory.

Prefer a few high-quality memories over a large collection of low-value memories.

# OUTPUT FOR THIS APP

Use the existing memory and latest user message to return the complete updated memory, applying additions, corrections, and forget requests. Keep distinct memories concise, with one bullet per memory. Do not impose a maximum number of bullets or words. Return only the updated memory, with no explanation or code fences. If no memories remain, return exactly NONE."""


def new_session():
    """Create an empty session file and return its path and data."""
    session_id = uuid.uuid4().hex[:8]
    data = {"created_at": datetime.now().isoformat(timespec="seconds"), "messages": []}
    path = SESSIONS_DIR / f"{session_id}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path, data


def list_sessions():
    paths = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not paths:
        print("No saved sessions yet.")
        return []

    for number, path in enumerate(paths, start=1):
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"{number}. {path.stem} ({len(data['messages'])} messages)")
    return paths


def chat(path, data, model, summarizer, summarizer_only):
    print(f"\nSession {path.stem}. Type /back to return to the menu.\n")
    while True:
        prompt = input("You: ").strip()
        if prompt == "/back":
            return
        if not prompt:
            continue

        memory = MEMORY_FILE.read_text(encoding="utf-8").strip() if MEMORY_FILE.exists() else ""
        if not summarizer_only:
            system_prompt = SYSTEM_PROMPT
            if memory:
                system_prompt += f"\n\nLong-term memory:\n{memory}"

            # Rebuild LangChain messages from this session's saved conversation.
            messages = [SystemMessage(content=system_prompt)]
            for item in data["messages"]:
                message_type = HumanMessage if item["role"] == "user" else AIMessage
                messages.append(message_type(content=item["content"]))
            messages.append(HumanMessage(content=prompt))

            try:
                reply = model.invoke(messages).content
            except Exception as error:
                print(f"\nGroq request failed: {error}\n")
                continue

            print(f"\nAssistant: {reply}")
            data["messages"].extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": reply},
            ])
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        try:
            summary = summarizer.invoke([
                SystemMessage(content=SUMMARIZER_PROMPT),
                HumanMessage(content=f"EXISTING MEMORY:\n{memory or 'NONE'}\n\nLATEST USER MESSAGE:\n{prompt}"),
            ]).content.strip()
            if summary == "NONE":
                MEMORY_FILE.unlink(missing_ok=True)
            elif summary:
                MEMORY_FILE.write_text(summary + "\n", encoding="utf-8")
            print(f"Summariser: {summary or 'No output'}\n")
        except Exception as error:
            print(f"Summariser failed: {error}\n")


def main():
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("Set GROQ_API_KEY in the .env file before starting.")

    SESSIONS_DIR.mkdir(exist_ok=True)
    summarizer_only = os.getenv("SUMMARIZER_ONLY", "false").lower() in {"1", "true", "yes"}
    model = None if summarizer_only else ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_key=api_key,
        temperature=0.2,
        reasoning_format="hidden",
    )
    summarizer = ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_key=api_key,
        temperature=0,
        reasoning_format="hidden",
    )
    if summarizer_only:
        print("Summariser-only mode: coding assistant is disabled.")

    while True:
        print("\nCoding Assistant\n1. New session\n2. Resume session\n3. Quit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            path, data = new_session()
            chat(path, data, model, summarizer, summarizer_only)
        elif choice == "2":
            paths = list_sessions()
            if paths:
                selection = input("Session number (or Enter to cancel): ").strip()
                if selection.isdigit() and 1 <= int(selection) <= len(paths):
                    path = paths[int(selection) - 1]
                    data = json.loads(path.read_text(encoding="utf-8"))
                    chat(path, data, model, summarizer, summarizer_only)
        elif choice == "3":
            break
        else:
            print("Choose 1, 2, or 3.")


if __name__ == "__main__":
    main()
