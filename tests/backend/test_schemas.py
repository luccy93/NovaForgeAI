"""Unit tests for schema definitions — graph_schema, qdrant_schema, indexing_strategy."""

import pytest


class TestGraphSchema:
    def test_graph_node_labels_have_values(self):
        from app.core.graph_schema import GraphNodeLabel
        for label in GraphNodeLabel:
            assert isinstance(label.value, str)
            assert len(label.value) > 0

    def test_graph_node_labels_unique(self):
        from app.core.graph_schema import GraphNodeLabel
        values = [e.value for e in GraphNodeLabel]
        assert len(values) == len(set(values))

    def test_graph_rel_types_have_values(self):
        from app.core.graph_schema import GraphRelType
        for rel in GraphRelType:
            assert isinstance(rel.value, str)
            assert len(rel.value) > 0

    def test_graph_rel_types_unique(self):
        from app.core.graph_schema import GraphRelType
        values = [e.value for e in GraphRelType]
        assert len(values) == len(set(values))

    def test_node_schema_contains_defined_labels(self):
        from app.core.graph_schema import GraphNodeLabel, NODE_SCHEMA
        defined = {GraphNodeLabel.REPOSITORY, GraphNodeLabel.FOLDER, GraphNodeLabel.FILE,
                   GraphNodeLabel.CLASS, GraphNodeLabel.FUNCTION, GraphNodeLabel.METHOD,
                   GraphNodeLabel.IMPORT, GraphNodeLabel.INTERFACE, GraphNodeLabel.COMMIT}
        for label in defined:
            assert label in NODE_SCHEMA, f"Missing schema for {label}"

    def test_node_schema_has_properties_and_indexes(self):
        from app.core.graph_schema import NODE_SCHEMA
        for label, schema in NODE_SCHEMA.items():
            assert "properties" in schema
            assert "indexes" in schema
            assert isinstance(schema["properties"], list)
            assert isinstance(schema["indexes"], list)
            assert len(schema["properties"]) > 0

    def test_node_schema_indexes_subset_of_properties(self):
        from app.core.graph_schema import NODE_SCHEMA
        for label, schema in NODE_SCHEMA.items():
            for idx in schema["indexes"]:
                assert idx in schema["properties"], f"Index {idx} not in properties for {label}"

    def test_queries_are_defined(self):
        from app.core.graph_schema import (
            QUERY_UPSERT_REPOSITORY, QUERY_UPSERT_FILE, QUERY_UPSERT_FUNCTION,
            QUERY_UPSERT_CLASS, QUERY_UPSERT_IMPORT, QUERY_GET_ARCHITECTURE,
            QUERY_GET_DEPENDENCIES, QUERY_GET_FUNCTION_CALLS, QUERY_GET_CLASS_HIERARCHY,
            QUERY_DELETE_REPOSITORY, QUERY_SEARCH_BY_EMBEDDING,
        )
        assert "MERGE" in QUERY_UPSERT_REPOSITORY
        assert "MERGE" in QUERY_UPSERT_FILE
        assert "MERGE" in QUERY_UPSERT_FUNCTION
        assert "MERGE" in QUERY_UPSERT_CLASS
        assert "MERGE" in QUERY_UPSERT_IMPORT
        assert "MATCH" in QUERY_GET_ARCHITECTURE
        assert "MATCH" in QUERY_GET_DEPENDENCIES
        assert "MATCH" in QUERY_GET_FUNCTION_CALLS
        assert "MATCH" in QUERY_GET_CLASS_HIERARCHY
        assert "DETACH DELETE" in QUERY_DELETE_REPOSITORY
        assert "db.index.vector.queryNodes" in QUERY_SEARCH_BY_EMBEDDING

    def test_create_vector_index_defined(self):
        from app.core.graph_schema import CREATE_VECTOR_INDEX
        assert "VECTOR INDEX" in CREATE_VECTOR_INDEX
        assert "code_embeddings" in CREATE_VECTOR_INDEX
        assert "cosine" in CREATE_VECTOR_INDEX
        assert "384" in CREATE_VECTOR_INDEX

    def test_create_node_indexes_list(self):
        from app.core.graph_schema import CREATE_NODE_INDEXES
        assert len(CREATE_NODE_INDEXES) == 5
        for idx in CREATE_NODE_INDEXES:
            assert idx.startswith("CREATE INDEX")
            assert "IF NOT EXISTS" in idx

    def test_all_queries_contain_param_placeholders(self):
        from app.core.graph_schema import (
            QUERY_UPSERT_REPOSITORY, QUERY_UPSERT_FILE, QUERY_UPSERT_FUNCTION,
            QUERY_UPSERT_CLASS, QUERY_UPSERT_IMPORT, QUERY_DELETE_REPOSITORY,
            QUERY_SEARCH_BY_EMBEDDING,
        )
        for q in [QUERY_UPSERT_REPOSITORY, QUERY_UPSERT_FILE, QUERY_UPSERT_FUNCTION,
                  QUERY_UPSERT_CLASS, QUERY_UPSERT_IMPORT, QUERY_DELETE_REPOSITORY]:
            assert "$" in q

    def test_code_node_label_has_embedding(self):
        from app.core.graph_schema import GraphNodeLabel
        assert GraphNodeLabel.FUNCTION.value == "Function"


class TestQdrantSchema:
    def test_payload_index_dataclass(self):
        from app.core.qdrant_schema import PayloadIndex
        idx = PayloadIndex("repository_id", "keyword")
        assert idx.field_name == "repository_id"
        assert idx.field_type == "keyword"

    def test_collection_schema_defaults(self):
        from app.core.qdrant_schema import CollectionSchema
        cs = CollectionSchema(name="test", vector_size=128)
        assert cs.distance == "Cosine"
        assert cs.payload_indexes == []
        assert cs.on_disk is False
        assert cs.replication_factor == 1

    def test_collection_schema_custom(self):
        from app.core.qdrant_schema import CollectionSchema, PayloadIndex
        cs = CollectionSchema(
            name="custom", vector_size=768, distance="Euclid",
            on_disk=True, replication_factor=3,
            payload_indexes=[PayloadIndex("field", "integer")],
        )
        assert cs.vector_size == 768
        assert cs.distance == "Euclid"
        assert cs.on_disk is True
        assert cs.replication_factor == 3

    def test_collections_defined(self):
        from app.core.qdrant_schema import COLLECTIONS
        expected = ["repository_chunks", "documentation_chunks", "conversation_memory",
                    "architecture_chunks", "security_chunks", "testing_chunks"]
        for name in expected:
            assert name in COLLECTIONS
            assert COLLECTIONS[name].name == name

    def test_all_collections_have_same_vector_size(self):
        from app.core.qdrant_schema import COLLECTIONS
        for name, schema in COLLECTIONS.items():
            assert schema.vector_size == 384, f"{name} has wrong vector_size"

    def test_all_collections_have_cosine_distance(self):
        from app.core.qdrant_schema import COLLECTIONS
        for name, schema in COLLECTIONS.items():
            assert schema.distance == "Cosine", f"{name} has wrong distance"

    def test_collections_have_payload_indexes(self):
        from app.core.qdrant_schema import COLLECTIONS
        for name, schema in COLLECTIONS.items():
            assert len(schema.payload_indexes) > 0, f"{name} has no payload indexes"

    def test_get_collection_config(self):
        from app.core.qdrant_schema import get_collection_config
        config = get_collection_config("repository_chunks")
        assert config["name"] == "repository_chunks"
        assert config["vectors_config"]["size"] == 384
        assert config["vectors_config"]["distance"] == "Cosine"
        assert config["on_disk"] is False
        assert config["replication_factor"] == 1

    def test_get_collection_config_unknown_raises(self):
        from app.core.qdrant_schema import get_collection_config
        with pytest.raises(ValueError, match="Unknown collection"):
            get_collection_config("nonexistent")

    def test_get_payload_index_configs(self):
        from app.core.qdrant_schema import get_payload_index_configs
        configs = get_payload_index_configs("repository_chunks")
        assert len(configs) > 0
        for cfg in configs:
            assert "field_name" in cfg
            assert "field_schema" in cfg

    def test_get_payload_index_configs_unknown(self):
        from app.core.qdrant_schema import get_payload_index_configs
        configs = get_payload_index_configs("nonexistent")
        assert configs == []

    def test_default_payload_structure(self):
        from app.core.qdrant_schema import DEFAULT_PAYLOAD
        assert "repository_id" in DEFAULT_PAYLOAD
        assert "file_path" in DEFAULT_PAYLOAD
        assert "language" in DEFAULT_PAYLOAD
        assert "chunk_type" in DEFAULT_PAYLOAD
        assert "start_line" in DEFAULT_PAYLOAD
        assert "end_line" in DEFAULT_PAYLOAD
        assert "hash" in DEFAULT_PAYLOAD
        assert "version" in DEFAULT_PAYLOAD
        assert DEFAULT_PAYLOAD["chunk_type"] == "code"
        assert DEFAULT_PAYLOAD["branch"] == "main"


class TestIndexingStrategy:
    def test_postgres_indexes_defined(self):
        from app.core.indexing_strategy import POSTGRES_INDEXES
        expected_tables = ["users", "organizations", "user_organizations", "repositories",
                          "messages", "conversations", "commits", "branches", "audit_logs",
                          "agent_runs", "usage_records", "analytics_events", "security_reports",
                          "api_keys", "notifications"]
        for table in expected_tables:
            assert table in POSTGRES_INDEXES, f"Missing indexes for {table}"

    def test_all_postgres_indexes_valid_syntax(self):
        from app.core.indexing_strategy import POSTGRES_INDEXES
        for table, indexes in POSTGRES_INDEXES.items():
            assert len(indexes) > 0
            for idx in indexes:
                assert idx.startswith("idx_")
                assert f"ON {table}" in idx

    def test_neo4j_indexes_defined(self):
        from app.core.indexing_strategy import NEO4J_INDEXES
        assert len(NEO4J_INDEXES) == 6
        for idx in NEO4J_INDEXES:
            assert "CREATE" in idx
            assert "IF NOT EXISTS" in idx

    def test_neo4j_vector_index(self):
        from app.core.indexing_strategy import NEO4J_INDEXES
        vector_idx = [i for i in NEO4J_INDEXES if "VECTOR" in i]
        assert len(vector_idx) == 1
        assert "384" in vector_idx[0]
        assert "cosine" in vector_idx[0]

    def test_redis_ttl_defined(self):
        from app.core.indexing_strategy import REDIS_TTL
        expected_keys = ["cache:repo:*", "cache:user:*", "cache:org:*", "cache:search:*",
                        "cache:prompt:*", "cache:embedding:*", "ratelimit:*", "session:*",
                        "blacklist:*", "lock:*", "queue:*"]
        for key in expected_keys:
            assert key in REDIS_TTL, f"Missing TTL for {key}"

    def test_redis_ttl_values_positive(self):
        from app.core.indexing_strategy import REDIS_TTL
        for key, ttl in REDIS_TTL.items():
            assert ttl > 0, f"TTL for {key} must be positive"

    def test_redis_ttl_embedding_longest(self):
        from app.core.indexing_strategy import REDIS_TTL
        assert REDIS_TTL["cache:embedding:*"] >= REDIS_TTL["cache:repo:*"]

    def test_query_patterns_defined(self):
        from app.core.indexing_strategy import QUERY_PATTERNS
        expected = ["pagination", "n_plus_1", "batch_insert", "async", "connection_pool",
                    "read_replicas", "prepared_statements"]
        for key in expected:
            assert key in QUERY_PATTERNS

    def test_query_patterns_have_advice(self):
        from app.core.indexing_strategy import QUERY_PATTERNS
        for key, advice in QUERY_PATTERNS.items():
            assert len(advice) > 10
            assert advice.endswith(".") or advice.endswith(")")

    def test_all_tables_have_at_least_one_index(self):
        from app.core.indexing_strategy import POSTGRES_INDEXES
        for table, indexes in POSTGRES_INDEXES.items():
            assert len(indexes) >= 1, f"Table {table} has no indexes"

    def test_audit_logs_have_user_action_composite(self):
        from app.core.indexing_strategy import POSTGRES_INDEXES
        assert any("user_id, action" in idx for idx in POSTGRES_INDEXES["audit_logs"])
