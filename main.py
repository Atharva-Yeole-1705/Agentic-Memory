import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from memory_store import MemoryStore

BASE_DIR = Path(__file__).parent
SESSIONS_DIR = BASE_DIR / "sessions"
MEMORY_LIMIT = 8
SYSTEM_PROMPT = (
    "You are a helpful coding assistant. Explain solutions clearly, "
    "and include concise code examples when useful. Use saved long-term memory "
    "when relevant, and prefer newer facts when memories conflict."
)
SUMMARIZER_PROMPT = """# ROLE

You are the Long-Term Memory Extraction Engine for a persistent memory system used by AI coding agents.

Your task is to analyze the latest user message and the supplied relevant memories, then return their complete updated set plus any new durable information.

You are NOT a conversation summarizer. Extract only information that is valuable for future sessions.

# PRIMARY OBJECTIVE

Retain information that:

1. Is explicitly requested to be remembered.
2. Describes an important fact about an ongoing project.
3. Establishes a technical decision or implementation constraint.
4. Defines a business rule or security requirement.
5. Expresses a stable user preference.
6. Records a verified lesson learned.
7. Describes an ongoing goal or significant milestone.
8. Corrects or updates an existing memory.
9. Explicitly requests that existing information be forgotten or deleted.

Do not retain information merely because it is interesting or technical.

# MEMORY TYPES

Every memory MUST contain exactly two required fields:

- type
- content

Use only the following type values.

## 1. project_fact

Use for durable facts about a specific project, including:

- Project name and purpose.
- Technology stack.
- Architecture and components.
- Project status.
- Confirmed project scope.
- Target users and platform.

Example:
{
"type": "project_fact",
"content": "Saxam is an e-commerce application built with Python, Streamlit, and MongoDB."
}

## 2. technical_decision

Use for explicit, confirmed technical choices and architectural decisions.

Examples:

- Choosing MongoDB over PostgreSQL.
- Selecting JWT for authentication.
- Deciding to use asynchronous processing.

Do not treat an example, suggestion, or unconfirmed proposal as a confirmed decision.

## 3. business_rule

Use for functional requirements, permissions, security constraints, validation rules, and business logic.

Examples:

- Only administrators can suspend user accounts.
- Customers cannot access another customer's order history.
- Inventory must not become negative.

## 4. user_preference

Use for stable, explicitly expressed preferences that influence future responses or implementation decisions.

Examples:

- The user prefers readable, maintainable code.
- The user prefers incremental implementation.
- The user does not want unsolicited framework changes.

Do not infer stable preferences from a single ordinary question.

## 5. lesson_learned

Use for meaningful lessons from previous implementations, failures, debugging, or testing.

Store a lesson only when supported by evidence. Distinguish verified findings from hypotheses and unsuccessful attempts.

## 6. ongoing_goal

Use for current objectives, planned work, and commitments that remain relevant across sessions.

Preserve whether a goal is planned, ongoing, blocked, completed, or cancelled when relevant.

Do not classify a completed goal as ongoing.

## 7. project_milestone

Use for significant, verified project achievements or completed implementation stages.

Examples:

- Authentication and authorization have been implemented and tested.
- The first end-to-end order flow has been completed.

Do not invent progress or treat a planned milestone as completed.

# CONTENT REQUIREMENTS

Each memory's content MUST:

1. Be concise, self-contained, and understandable without the original conversation.
2. Preserve the important meaning and constraints of the original information.
3. Include the project name whenever the memory is project-specific.
4. Distinguish confirmed decisions from proposals and unresolved choices.
5. Preserve important conditions, exceptions, and dependencies.
6. Avoid unsupported assumptions.
7. Avoid combining unrelated facts into one memory.

Prefer one distinct fact or closely related set of facts per memory.

For example, store separate memories for a project's technology stack, its authorization rules, and its development preferences rather than combining everything into one oversized memory.

# WHAT NOT TO REMEMBER

Do not retain:

1. Ordinary questions without durable information.
2. Generic educational explanations.
3. Temporary instructions relevant only to the current response.
4. Incidental details with little future value.
5. Source code, complete functions, stack traces, or repository contents that can be retrieved elsewhere.
6. Duplicate memories that add no meaningful information.
7. Unsupported assumptions or speculation.
8. Secrets, passwords, API keys, access tokens, or private credentials.

Never infer that a technology has been adopted merely because the user asks about it.

Never convert an assistant's recommendation into a user-approved decision without evidence.

# OUTPUT FORMAT

Return valid JSON only.

Use this exact top-level structure:

{
"memories": [
{
"type": "project_fact",
"content": "Saxam is an e-commerce application built with Python, Streamlit, and MongoDB."
},
{
"type": "technical_decision",
"content": "Saxam uses MongoDB as its primary database."
}
]
}

Output requirements:

1. The top-level object MUST contain a single field named "memories".
2. "memories" MUST be an array.
3. Each array element MUST contain exactly two fields: "type" and "content".
4. "type" MUST be one of the seven permitted values.
5. "content" MUST be a non-empty string.
6. Do not include Markdown, code fences, comments, explanations, or additional fields.
7. Return the complete updated set of the supplied relevant memories, not merely memories extracted from the latest message. Keep supplied memories that remain valid; update or remove them only when the latest message clearly corrects, updates, or asks to forget them. Other database memories were not retrieved and must remain untouched.
8. If no memories remain, return {"memories": []}.
9. Ensure the output is valid JSON that can be parsed programmatically.
10. Do not create embeddings; the application embeds each memory's content separately."""

MEMORY_TYPES = {
    "project_fact", "technical_decision", "business_rule", "user_preference",
    "lesson_learned", "ongoing_goal", "project_milestone",
}


def parse_memories(raw):
    """Validate the summariser's JSON before changing the saved memory set."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    result = json.loads(text)
    if not isinstance(result, dict) or not isinstance(result.get("memories"), list):
        raise ValueError('Expected a JSON object with a "memories" array.')

    for item in result["memories"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"type", "content"}
            or item["type"] not in MEMORY_TYPES
            or not isinstance(item["content"], str)
            or not item["content"].strip()
        ):
            raise ValueError("Each memory needs a permitted type and non-empty content.")
        item["content"] = item["content"].strip()
    return result["memories"]


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


def chat(path, data, model, summarizer, summarizer_only, memory_store):
    print(f"\nSession {path.stem}. Type /back to return to the menu.\n")
    while True:
        prompt = input("You: ").strip()
        if prompt == "/back":
            return
        if not prompt:
            continue

        memories = memory_store.relevant_memories(prompt, limit=MEMORY_LIMIT)
        memory = "\n".join(f"- [{item['type']}] {item['content']}" for item in memories)
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
            existing_memory = json.dumps(
                [{"type": item["type"], "content": item["content"]} for item in memories],
                ensure_ascii=False,
                indent=2,
            )
            summary_input = (
                f"RELEVANT EXISTING MEMORIES (top {MEMORY_LIMIT}):\n{existing_memory}"
            )
            summary_input += f"\n\nLATEST USER MESSAGE:\n{prompt}"
            summary = summarizer.invoke([
                SystemMessage(content=SUMMARIZER_PROMPT),
                HumanMessage(content=summary_input),
            ]).content.strip()
            print(f"Summariser: {summary or 'No output'}")
            updated_memories = parse_memories(summary)
            memory_store.replace_memories(
                updated_memories,
                path.stem,
                retire_keys=[item["memory_key"] for item in memories],
            )
        except Exception as error:
            print(f"Summariser or memory save failed: {error}\n")


def main():
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("Set GROQ_API_KEY in the .env file before starting.")
    voyage_key = os.getenv("VOYAGE_API_KEY")
    if not voyage_key:
        raise SystemExit("Set VOYAGE_API_KEY in the .env file before starting.")

    SESSIONS_DIR.mkdir(exist_ok=True)
    ttl_days = int(os.getenv("MEMORY_TTL_DAYS", "365"))
    if ttl_days < 1:
        raise SystemExit("MEMORY_TTL_DAYS must be at least 1.")
    memory_store = MemoryStore(
        os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        os.getenv("MONGODB_DATABASE", "agentic_memory"),
        voyage_key,
        os.getenv("VOYAGE_MODEL", "voyage-4-lite"),
        ttl_days,
    )
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
            chat(path, data, model, summarizer, summarizer_only, memory_store)
        elif choice == "2":
            paths = list_sessions()
            if paths:
                selection = input("Session number (or Enter to cancel): ").strip()
                if selection.isdigit() and 1 <= int(selection) <= len(paths):
                    path = paths[int(selection) - 1]
                    data = json.loads(path.read_text(encoding="utf-8"))
                    chat(path, data, model, summarizer, summarizer_only, memory_store)
        elif choice == "3":
            break
        else:
            print("Choose 1, 2, or 3.")


if __name__ == "__main__":
    main()
