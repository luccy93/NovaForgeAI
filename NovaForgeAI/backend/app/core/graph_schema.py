"""Neo4j graph schema — nodes, edges, indexes, and queries.

Every repository is modeled as a graph in Neo4j.
Nodes represent code entities. Edges represent relationships.
"""

import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─── Node Labels ──────────────────────────────────────────────────────

class GraphNodeLabel(str, Enum):
    REPOSITORY = "Repository"
    FOLDER = "Folder"
    FILE = "File"
    CLASS = "Class"
    FUNCTION = "Function"
    METHOD = "Method"
    MODULE = "Module"
    PACKAGE = "Package"
    IMPORT = "Import"
    INTERFACE = "Interface"
    ENUM = "Enum"
    VARIABLE = "Variable"
    BRANCH = "Branch"
    COMMIT = "Commit"


# ─── Relationship Types ───────────────────────────────────────────────

class GraphRelType(str, Enum):
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    DEPENDS_ON = "DEPENDS_ON"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"
    BELONGS_TO = "BELONGS_TO"
    REFERENCES = "REFERENCES"
    USES = "USES"
    GENERATED_BY = "GENERATED_BY"


# ─── Schema Definitions ───────────────────────────────────────────────

NODE_SCHEMA = {
    GraphNodeLabel.REPOSITORY: {
        "properties": ["id", "name", "full_name", "language", "default_branch"],
        "indexes": ["id", "full_name"],
    },
    GraphNodeLabel.FOLDER: {
        "properties": ["id", "path", "name", "repository_id"],
        "indexes": ["path", "repository_id"],
    },
    GraphNodeLabel.FILE: {
        "properties": ["id", "path", "name", "extension", "language", "size", "repository_id", "hash"],
        "indexes": ["path", "repository_id", "hash"],
    },
    GraphNodeLabel.CLASS: {
        "properties": ["id", "name", "file_path", "start_line", "end_line", "language", "repository_id"],
        "indexes": ["name", "file_path", "repository_id"],
    },
    GraphNodeLabel.FUNCTION: {
        "properties": ["id", "name", "file_path", "start_line", "end_line", "language", "repository_id", "complexity"],
        "indexes": ["name", "file_path", "repository_id"],
    },
    GraphNodeLabel.METHOD: {
        "properties": ["id", "name", "class_name", "file_path", "start_line", "end_line", "language", "repository_id"],
        "indexes": ["name", "class_name", "file_path"],
    },
    GraphNodeLabel.IMPORT: {
        "properties": ["id", "source", "alias", "file_path", "repository_id"],
        "indexes": ["source", "file_path"],
    },
    GraphNodeLabel.INTERFACE: {
        "properties": ["id", "name", "file_path", "start_line", "end_line", "language", "repository_id"],
        "indexes": ["name", "file_path"],
    },
    GraphNodeLabel.COMMIT: {
        "properties": ["id", "sha", "message", "author", "timestamp", "repository_id"],
        "indexes": ["sha", "repository_id"],
    },
}


# ─── Cypher Queries ───────────────────────────────────────────────────

QUERY_UPSERT_REPOSITORY = """
MERGE (r:Repository {id: $id})
SET r.name = $name, r.full_name = $full_name, r.language = $language,
    r.default_branch = $default_branch, r.updated_at = timestamp()
"""

QUERY_UPSERT_FILE = """
MERGE (f:File {id: $id})
SET f.path = $path, f.name = $name, f.extension = $extension,
    f.language = $language, f.size = $size, f.repository_id = $repo_id,
    f.hash = $hash, f.updated_at = timestamp()
WITH f
MATCH (r:Repository {id: $repo_id})
MERGE (r)-[:CONTAINS]->(f)
"""

QUERY_UPSERT_FUNCTION = """
MERGE (fn:Function {id: $id})
SET fn.name = $name, fn.file_path = $file_path, fn.start_line = $start_line,
    fn.end_line = $end_line, fn.language = $language, fn.repository_id = $repo_id,
    fn.complexity = $complexity, fn.updated_at = timestamp()
WITH fn
MATCH (f:File {id: $file_id})
MERGE (f)-[:CONTAINS]->(fn)
"""

QUERY_UPSERT_CLASS = """
MERGE (c:Class {id: $id})
SET c.name = $name, c.file_path = $file_path, c.start_line = $start_line,
    c.end_line = $end_line, c.language = $language, c.repository_id = $repo_id,
    c.updated_at = timestamp()
WITH c
MATCH (f:File {id: $file_id})
MERGE (f)-[:CONTAINS]->(c)
"""

QUERY_UPSERT_IMPORT = """
MERGE (i:Import {id: $id})
SET i.source = $source, i.alias = $alias, i.file_path = $file_path,
    i.repository_id = $repo_id, i.updated_at = timestamp()
WITH i
MATCH (f:File {id: $file_id})
MERGE (f)-[:IMPORTS]->(i)
"""

QUERY_GET_ARCHITECTURE = """
MATCH (r:Repository {id: $repo_id})-[:CONTAINS*1..3]->(n)
WHERE n:Folder OR n:File
RETURN n
ORDER BY n.path
"""

QUERY_GET_DEPENDENCIES = """
MATCH (f:File {repository_id: $repo_id})-[:IMPORTS]->(i:Import)
RETURN f.path AS file, i.source AS dependency
ORDER BY f.path
"""

QUERY_GET_FUNCTION_CALLS = """
MATCH (fn:Function {repository_id: $repo_id})-[:CALLS]->(called:Function)
RETURN fn.name AS caller, called.name AS callee, called.file_path AS file
"""

QUERY_GET_CLASS_HIERARCHY = """
MATCH (c:Class {repository_id: $repo_id})
OPTIONAL MATCH (c)-[:EXTENDS]->(parent:Class)
OPTIONAL MATCH (c)-[:IMPLEMENTS]->(iface:Interface)
RETURN c.name AS class, parent.name AS extends,
       collect(iface.name) AS implements
"""

QUERY_DELETE_REPOSITORY = """
MATCH (r:Repository {id: $repo_id})
DETACH DELETE r
"""

QUERY_SEARCH_BY_EMBEDDING = """
CALL db.index.vector.queryNodes('code_embeddings', $limit, $vector)
YIELD node, score
RETURN node {.*, score: score} AS result
"""

# ─── Index Creation ───────────────────────────────────────────────────

CREATE_VECTOR_INDEX = """
CREATE VECTOR INDEX code_embeddings IF NOT EXISTS
FOR (n:Function) ON (n.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 384,
  `vector.similarity_function`: 'cosine'
}}
"""

CREATE_NODE_INDEXES = [
    "CREATE INDEX repo_id IF NOT EXISTS FOR (n:Repository) ON (n.id)",
    "CREATE INDEX file_path IF NOT EXISTS FOR (n:File) ON (n.path)",
    "CREATE INDEX func_name IF NOT EXISTS FOR (n:Function) ON (n.name)",
    "CREATE INDEX class_name IF NOT EXISTS FOR (n:Class) ON (n.name)",
    "CREATE INDEX commit_sha IF NOT EXISTS FOR (n:Commit) ON (n.sha)",
]
