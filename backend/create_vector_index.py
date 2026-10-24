"""Create the Atlas Vector Search index defined in vector_index.json."""
import json
from pathlib import Path

from pymongo.operations import SearchIndexModel

from .config import get_settings
from .database import get_database


def main():
    settings = get_settings()
    collection = get_database().memories
    existing = {item["name"] for item in collection.list_search_indexes()}
    if settings.mongodb_vector_index in existing:
        print(f"Search index '{settings.mongodb_vector_index}' already exists.")
        return
    definition = json.loads((Path(__file__).parent / "vector_index.json").read_text(encoding="utf-8"))
    model = SearchIndexModel(definition=definition, name=settings.mongodb_vector_index, type="vectorSearch")
    collection.create_search_index(model=model)
    print(f"Created '{settings.mongodb_vector_index}'. Wait for Atlas to report READY.")


if __name__ == "__main__":
    main()
