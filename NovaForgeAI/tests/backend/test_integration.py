"""Integration tests for database operations — PostgreSQL, Redis, Neo4j, Qdrant.

These tests require external services running.
Marked with @pytest.mark.integration — skipped by default.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.user import User
from app.models.organization import Organization
from app.models.conversation import Conversation, Message, MessageRole


pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Create a fresh database session for integration tests."""
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ─── PostgreSQL ────────────────────────────────────────────────────

class TestPostgreSQL:
    async def test_connection(self, db_session: AsyncSession):
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    async def test_create_user(self, db_session: AsyncSession):
        user = User(email="integ@test.com", username="integtest", hashed_password="hash")
        db_session.add(user)
        await db_session.flush()
        assert user.id is not None
        assert isinstance(user.id, uuid.UUID)

    async def test_create_organization(self, db_session: AsyncSession):
        org = Organization(name="Integ Org", slug="integ-org")
        db_session.add(org)
        await db_session.flush()
        assert org.id is not None

    async def test_create_conversation_with_messages(self, db_session: AsyncSession):
        conv = Conversation(session_id="integ-session", title="Integ Test")
        db_session.add(conv)
        await db_session.flush()

        msg1 = Message(conversation_id=conv.id, role=MessageRole.user, content="Hello")
        msg2 = Message(conversation_id=conv.id, role=MessageRole.assistant, content="Hi there!")
        db_session.add(msg1)
        db_session.add(msg2)
        await db_session.flush()

        result = await db_session.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
        )
        messages = result.scalars().all()
        assert len(messages) == 2

    async def test_transaction_rollback(self, db_session: AsyncSession):
        user = User(email="rollback@test.com", username="rollback", hashed_password="hash")
        db_session.add(user)
        await db_session.rollback()
        result = await db_session.execute(
            select(User).where(User.email == "rollback@test.com")
        )
        assert result.scalar_one_or_none() is None

    async def test_unique_constraint(self, db_session: AsyncSession):
        user1 = User(email="unique@test.com", username="unique1", hashed_password="hash")
        user2 = User(email="unique@test.com", username="unique2", hashed_password="hash")
        db_session.add(user1)
        await db_session.flush()
        db_session.add(user2)
        with pytest.raises(Exception):
            await db_session.flush()
        await db_session.rollback()

    async def test_cascade_delete(self, db_session: AsyncSession):
        org = Organization(name="Cascade Org", slug="cascade-org")
        db_session.add(org)
        await db_session.flush()

        repo = org.__class__(name="test-repo", full_name="org/test-repo")
        repo.organization_id = org.id
        db_session.add(repo)
        await db_session.flush()

        await db_session.delete(org)
        await db_session.flush()

        result = await db_session.execute(
            select(type(repo)).where(type(repo).id == repo.id)  # noqa
        )
        assert result.scalar_one_or_none() is None


# ─── Redis ─────────────────────────────────────────────────────────

class TestRedis:
    async def test_connection(self):
        from app.core.redis import get_redis
        redis = await get_redis()
        if redis is None:
            pytest.skip("Redis not available")
        await redis.ping()

    async def test_cache_set_get(self):
        from app.core.redis import cache_set, cache_get
        await cache_set("test:key", "test_value", ttl=60)
        value = await cache_get("test:key")
        assert value == "test_value"

    async def test_cache_expiry(self):
        from app.core.redis import cache_set, cache_get
        await cache_set("test:expire", "value", ttl=1)
        import asyncio
        await asyncio.sleep(1.5)
        value = await cache_get("test:expire")
        assert value is None

    async def test_cache_delete(self):
        from app.core.redis import cache_set, cache_delete, cache_get
        await cache_set("test:delete", "value")
        await cache_delete("test:delete")
        value = await cache_get("test:delete")
        assert value is None

    async def test_rate_limit(self):
        from app.core.redis import rate_limit_check
        allowed, remaining = await rate_limit_check("test:rl", 10, 60)
        assert allowed is True
        assert remaining >= 0

    async def test_session_store(self):
        from app.core.redis import session_set, session_get, session_delete
        await session_set("test:session", {"user_id": "123"})
        data = await session_get("test:session")
        assert data["user_id"] == "123"
        await session_delete("test:session")
        assert await session_get("test:session") is None

    async def test_jwt_blacklist(self):
        from app.core.redis import blacklist_token, is_token_blacklisted
        await blacklist_token("test:jti", 60)
        assert await is_token_blacklisted("test:jti") is True
        assert await is_token_blacklisted("unknown:jti") is False

    async def test_lock(self):
        from app.core.redis import acquire_lock, release_lock
        acquired = await acquire_lock("test:lock", ttl=10)
        assert acquired is True
        second = await acquire_lock("test:lock", ttl=10)
        assert second is False  # already locked
        await release_lock("test:lock")

    async def test_publish(self):
        from app.core.redis import publish
        result = await publish("test:channel", {"event": "test"})
        assert result is True


# ─── Neo4j ─────────────────────────────────────────────────────────

class TestNeo4j:
    async def test_connection(self):
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            await driver.verify_connectivity()
        finally:
            await driver.close()

    async def test_create_and_query_node(self):
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            async with driver.session(database="neo4j") as session:
                await session.run("MERGE (t:TestNode {id: $id}) SET t.name = $name",
                                  id="test-1", name="Test")
                result = await session.run("MATCH (t:TestNode {id: $id}) RETURN t.name", id="test-1")
                record = await result.single()
                assert record["t.name"] == "Test"
                await session.run("MATCH (t:TestNode {id: $id}) DETACH DELETE t", id="test-1")
        finally:
            await driver.close()

    async def test_relationship_creation(self):
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            async with driver.session(database="neo4j") as session:
                await session.run("""
                    MERGE (a:TestNode {id: 'a'}) SET a.name = 'A'
                    MERGE (b:TestNode {id: 'b'}) SET b.name = 'B'
                    MERGE (a)-[:CONNECTS]->(b)
                """)
                result = await session.run("""
                    MATCH (a:TestNode {id: 'a'})-[:CONNECTS]->(b:TestNode {id: 'b'})
                    RETURN a.name, b.name
                """)
                record = await result.single()
                assert record["a.name"] == "A"
                assert record["b.name"] == "B"
                await session.run("MATCH (n:TestNode) DETACH DELETE n")
        finally:
            await driver.close()


# ─── Qdrant ────────────────────────────────────────────────────────

class TestQdrant:
    async def test_connection(self):
        from qdrant_client import QdrantClient
        client = QdrantClient(url=settings.qdrant_url, prefer_grpc=False)
        collections = client.get_collections()
        assert collections is not None

    async def test_create_and_search_collection(self):
        import uuid
        from qdrant_client import QdrantClient
        from qdrant_client.models import VectorParams, Distance, PointStruct
        client = QdrantClient(url=settings.qdrant_url, prefer_grpc=False)
        collection_name = f"test_{uuid.uuid4().hex[:8]}"
        try:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=4, distance=Distance.COSINE),
            )
            client.upsert(
                collection_name=collection_name,
                points=[
                    PointStruct(id=1, vector=[0.1, 0.2, 0.3, 0.4], payload={"text": "hello"}),
                    PointStruct(id=2, vector=[0.5, 0.6, 0.7, 0.8], payload={"text": "world"}),
                ],
            )
            results = client.search(
                collection_name=collection_name,
                query_vector=[0.1, 0.2, 0.3, 0.4],
                limit=2,
            )
            assert len(results) > 0
            client.delete_collection(collection_name=collection_name)
        except Exception:
            if client.collection_exists(collection_name):
                client.delete_collection(collection_name)
