from unittest.mock import AsyncMock, MagicMock, patch, sentinel
import pytest
import uuid


class AsyncContextManager:
    def __init__(self, mock_obj):
        self._mock = mock_obj

    async def __aenter__(self):
        return self._mock

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def mock_session():
    session = AsyncMock()
    result = AsyncMock()
    result.fetch = AsyncMock(return_value=[])
    session.run.return_value = result
    return session


@pytest.fixture
def mock_driver(mock_session):
    driver = MagicMock()
    cm = AsyncContextManager(mock_session)
    driver.session = MagicMock(return_value=cm)
    driver.close = AsyncMock()
    return driver


@pytest.fixture
def service(mock_driver):
    with patch(
        "app.services.graph_store.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        from app.services.graph_store import GraphStoreService
        svc = GraphStoreService()
        svc._driver = mock_driver
        return svc


class TestGraphStoreServiceInit:
    def test_creates_driver_with_settings(self):
        with patch(
            "app.services.graph_store.AsyncGraphDatabase.driver",
        ) as mock_driver_cls:
            from app.services.graph_store import GraphStoreService
            GraphStoreService()
            mock_driver_cls.assert_called_once()
            args, kwargs = mock_driver_cls.call_args
            assert kwargs["auth"] is not None

    def test_driver_credentials_from_settings(self):
        with patch(
            "app.services.graph_store.AsyncGraphDatabase.driver",
        ) as mock_driver_cls:
            from app.services.graph_store import GraphStoreService, settings
            GraphStoreService()
            _, kwargs = mock_driver_cls.call_args
            assert kwargs["auth"][0] == settings.neo4j_user
            assert kwargs["auth"][1] == settings.neo4j_password


class TestGraphStoreAsyncContext:
    @pytest.mark.asyncio
    async def test_aenter_returns_self(self, service):
        async with service as s:
            assert s is service

    @pytest.mark.asyncio
    async def test_aexit_closes_driver(self, service, mock_driver):
        async with service:
            pass
        mock_driver.close.assert_awaited_once()


class TestGraphStoreExecuteQuery:
    @pytest.mark.asyncio
    async def test_execute_query_runs_and_fetches(self, service, mock_session):
        result = mock_session.run.return_value
        result.fetch = AsyncMock(return_value=["record1", "record2"])

        records = await service.execute_query("MATCH (n) RETURN n", {"limit": 10})

        mock_session.run.assert_awaited_once_with("MATCH (n) RETURN n", {"limit": 10})
        result.fetch.assert_awaited_once()
        assert records == ["record1", "record2"]

    @pytest.mark.asyncio
    async def test_execute_query_defaults_empty_params(self, service, mock_session):
        await service.execute_query("MATCH (n) RETURN n")

        mock_session.run.assert_awaited_once_with("MATCH (n) RETURN n", {})


class TestGraphStoreCreateCodeNode:
    @pytest.mark.asyncio
    async def test_create_code_node_returns_dict(self, service, mock_session):
        result = mock_session.run.return_value
        result.fetch = AsyncMock(return_value=[{"n": {"id": "abc", "file_path": "main.py"}}])

        result_val = await service.create_code_node("main.py", "python", "hash123")

        assert result_val == {"id": "abc", "file_path": "main.py"}
        params = mock_session.run.call_args[0][1]
        assert params["file_path"] == "main.py"
        assert params["language"] == "python"
        assert params["content_hash"] == "hash123"

    @pytest.mark.asyncio
    async def test_create_code_node_returns_fallback_when_no_records(self, service, mock_session):
        result_val = await service.create_code_node("main.py", "python", "hash123")

        assert "id" in result_val


class TestGraphStoreCreateRelationship:
    @pytest.mark.asyncio
    async def test_create_relationship_with_properties(self, service, mock_session):
        result = mock_session.run.return_value
        result.fetch = AsyncMock(return_value=[{"r": {"from_id": "a", "to_id": "b", "type": "CALLS"}}])

        result_val = await service.create_relationship("a", "b", "CALLS", {"weight": 1})

        assert result_val == {"from_id": "a", "to_id": "b", "type": "CALLS"}
        params = mock_session.run.call_args[0][1]
        assert params["from_id"] == "a"
        assert params["to_id"] == "b"
        assert params["weight"] == 1

    @pytest.mark.asyncio
    async def test_create_relationship_without_properties(self, service, mock_session):
        result_val = await service.create_relationship("a", "b", "CALLS")

        assert result_val == {"from_id": "a", "to_id": "b", "type": "CALLS"}
        call = mock_session.run.call_args[0][0]
        assert "CALLS" in call

    @pytest.mark.asyncio
    async def test_create_relationship_empty_properties(self, service, mock_session):
        result_val = await service.create_relationship("a", "b", "CALLS", {})

        assert result_val == {"from_id": "a", "to_id": "b", "type": "CALLS"}


class TestGraphStoreSearchByEmbedding:
    @pytest.mark.asyncio
    async def test_search_by_embedding_returns_results(self, service, mock_session):
        result = mock_session.run.return_value
        result.fetch = AsyncMock(return_value=[
            {"node": {"id": "n1"}, "score": 0.95},
            {"node": {"id": "n2"}, "score": 0.87},
        ])

        results = await service.search_by_embedding([0.1, 0.2, 0.3], limit=5)

        assert len(results) == 2
        assert results[0]["id"] == "n1"
        assert results[0]["score"] == 0.95
        assert results[1]["id"] == "n2"
        assert results[1]["score"] == 0.87

    @pytest.mark.asyncio
    async def test_search_by_embedding_defaults_limit(self, service, mock_session):
        results = await service.search_by_embedding([0.1, 0.2])

        assert results == []
        params = mock_session.run.call_args[0][1]
        assert params["limit"] == 10

    @pytest.mark.asyncio
    async def test_search_by_embedding_passes_vector(self, service, mock_session):
        vector = [0.1, 0.2, 0.3]
        await service.search_by_embedding(vector, limit=3)

        params = mock_session.run.call_args[0][1]
        assert params["vector"] == vector
        assert params["limit"] == 3


class TestGraphStoreGetCodeGraph:
    @pytest.mark.asyncio
    async def test_get_code_graph_returns_nodes_and_rels(self, service, mock_session):
        result = mock_session.run.return_value

        mock_start = MagicMock()
        mock_start.get.side_effect = lambda k, d=None: {"id": "n1"}.get(k, d)
        mock_end = MagicMock()
        mock_end.get.side_effect = lambda k, d=None: {"id": "n2"}.get(k, d)
        mock_rel = MagicMock()
        mock_rel.type = "CALLS"
        mock_rel.start_node = mock_start
        mock_rel.end_node = mock_end
        mock_rel.__getitem__ = lambda self, k: {"weight": 1}[k]

        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, k: {
            "all_nodes": [{"id": "n1", "file_path": "main.py"}, {"id": "n2", "file_path": "util.py"}],
            "all_rels": [mock_rel],
            "root": {"id": "n1"},
        }[k]

        result.fetch = AsyncMock(return_value=[mock_record])

        result = await service.get_code_graph("main.py")

        assert len(result["nodes"]) == 2
        assert len(result["relationships"]) == 1
        assert result["relationships"][0]["type"] == "CALLS"
        assert result["relationships"][0]["from"] == "n1"
        assert result["relationships"][0]["to"] == "n2"

    @pytest.mark.asyncio
    async def test_get_code_graph_returns_empty_when_no_records(self, service, mock_session):
        result = await service.get_code_graph("nonexistent.py")

        assert result == {"nodes": [], "relationships": []}
