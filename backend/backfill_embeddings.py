"""Generate embeddings for memory documents created before vector retrieval was enabled."""
from .database import get_database
from .services import embed_text, retrieval_deadline


def main():
    collection = get_database().memories
    updated = 0
    for memory in collection.find({"embedding": {"$exists": False}}):
        collection.update_one(
            {"_id": memory["_id"]},
            {"$set": {
                "embedding": embed_text(memory["content"], "document"),
                "retrieval_until": retrieval_deadline(memory.get("expires_at")),
            }},
        )
        updated += 1
    print(f"Backfilled embeddings for {updated} memories.")


if __name__ == "__main__":
    main()
