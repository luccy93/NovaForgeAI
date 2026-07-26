"""Qdrant collection schemas — vector search collections.

Each collection has a defined schema, payload indexes, and configuration.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PayloadIndex:
    field_name: str
    field_type: str  # "keyword" | "integer" | "float" | "geo"


@dataclass
class CollectionSchema:
    name: str
    vector_size: int
    distance: str = "Cosine"  # Cosine | Euclid | Dot
    payload_indexes: list[PayloadIndex] = field(default_factory=list)
    on_disk: bool = False
    replication_factor: int = 1


# ─── Collections ──────────────────────────────────────────────────────

COLLECTIONS: dict[str, CollectionSchema] = {
    "repository_chunks": CollectionSchema(
        name="repository_chunks",
        vector_size=384,
        distance="Cosine",
        payload_indexes=[
            PayloadIndex("repository_id", "keyword"),
            PayloadIndex("file_path", "keyword"),
            PayloadIndex("language", "keyword"),
            PayloadIndex("chunk_type", "keyword"),
            PayloadIndex("branch", "keyword"),
            PayloadIndex("hash", "keyword"),
        ],
    ),
    "documentation_chunks": CollectionSchema(
        name="documentation_chunks",
        vector_size=384,
        distance="Cosine",
        payload_indexes=[
            PayloadIndex("repository_id", "keyword"),
            PayloadIndex("doc_type", "keyword"),
            PayloadIndex("language", "keyword"),
        ],
    ),
    "conversation_memory": CollectionSchema(
        name="conversation_memory",
        vector_size=384,
        distance="Cosine",
        payload_indexes=[
            PayloadIndex("conversation_id", "keyword"),
            PayloadIndex("user_id", "keyword"),
            PayloadIndex("role", "keyword"),
        ],
    ),
    "architecture_chunks": CollectionSchema(
        name="architecture_chunks",
        vector_size=384,
        distance="Cosine",
        payload_indexes=[
            PayloadIndex("repository_id", "keyword"),
            PayloadIndex("node_type", "keyword"),
        ],
    ),
    "security_chunks": CollectionSchema(
        name="security_chunks",
        vector_size=384,
        distance="Cosine",
        payload_indexes=[
            PayloadIndex("repository_id", "keyword"),
            PayloadIndex("severity", "keyword"),
            PayloadIndex("scan_type", "keyword"),
        ],
    ),
    "testing_chunks": CollectionSchema(
        name="testing_chunks",
        vector_size=384,
        distance="Cosine",
        payload_indexes=[
            PayloadIndex("repository_id", "keyword"),
            PayloadIndex("test_type", "keyword"),
            PayloadIndex("status", "keyword"),
        ],
    ),
}


# ─── Default Payload Structure ────────────────────────────────────────

DEFAULT_PAYLOAD = {
    "repository_id": "",
    "project_id": "",
    "organization_id": "",
    "branch": "main",
    "file_path": "",
    "language": "",
    "chunk_type": "code",  # code | doc | comment | test | config
    "start_line": 0,
    "end_line": 0,
    "hash": "",
    "version": 1,
    "created_at": "",
    "metadata": {},
}


# ─── Collection Configuration ─────────────────────────────────────────

def get_collection_config(name: str) -> dict[str, Any]:
    """Build Qdrant collection create config from schema."""
    schema = COLLECTIONS.get(name)
    if not schema:
        raise ValueError(f"Unknown collection: {name}. Available: {list(COLLECTIONS.keys())}")

    return {
        "name": schema.name,
        "vectors_config": {
            "size": schema.vector_size,
            "distance": schema.distance,
        },
        "on_disk": schema.on_disk,
        "replication_factor": schema.replication_factor,
    }


def get_payload_index_configs(name: str) -> list[dict[str, Any]]:
    """Build list of payload index create operations."""
    schema = COLLECTIONS.get(name)
    if not schema:
        return []
    return [
        {
            "field_name": idx.field_name,
            "field_schema": idx.field_type,
        }
        for idx in schema.payload_indexes
    ]
