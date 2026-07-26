from unittest.mock import MagicMock, patch, AsyncMock
import pytest


_counter = [0]


def _new_chat_history():
    _counter[0] += 1
    return MagicMock(name=f"ChatMessageHistory_{_counter[0]}")


@pytest.fixture(autouse=True)
def mock_rag_deps():
    chat_history_mod = MagicMock()
    chat_history_mod.ChatMessageHistory = MagicMock(side_effect=_new_chat_history)

    mocks = {
        "graphRag_cypher_chain_cd": MagicMock(),
        "langchain_community.chat_message_histories": chat_history_mod,
        "langchain_community.chat_message_histories.ChatMessageHistory": chat_history_mod.ChatMessageHistory,
        "langchain_core.chat_history": MagicMock(),
        "langchain_core.runnables": MagicMock(),
        "langchain_core.runnables.history": MagicMock(),
        "langchain_community.tools": MagicMock(),
        "langchain_google_genai": MagicMock(),
    }
    for mod_name, mock in mocks.items():
        import sys
        sys.modules[mod_name] = mock
    yield
    for mod_name in mocks:
        if mod_name in sys.modules:
            del sys.modules[mod_name]
    for k in list(sys.modules.keys()):
        if "graph_rag_agent" in k:
            del sys.modules[k]


@pytest.fixture
def module():
    import importlib
    import sys
    for k in list(sys.modules.keys()):
        if "graph_rag_agent" in k:
            del sys.modules[k]
    import app.services.graph_rag_agent as m
    importlib.reload(m)
    return m


class TestHybridRagRunner:
    def test_empty_input_returns_prompt(self, module):
        result = module.hybrid_rag_runner({"input": ""})
        assert "enter a question" in result["output"].lower()

    def test_empty_input_whitespace(self, module):
        result = module.hybrid_rag_runner({"input": "   "})
        assert "enter a question" in result["output"].lower()

    def test_missing_input_key(self, module):
        result = module.hybrid_rag_runner({})
        assert "enter a question" in result["output"].lower()

    def test_graph_and_web_success(self, module):
        module.graph_cypher_chain.invoke.return_value = {"result": "Gene found in database"}
        module.web_search.invoke.return_value = "Web context about gene"
        mock_response = MagicMock()
        mock_response.content = "Final synthesized answer"
        module.synthesizer_llm.invoke.return_value = mock_response

        result = module.hybrid_rag_runner({"input": "What is BSG?"})

        assert result["output"] == "Final synthesized answer"
        module.graph_cypher_chain.invoke.assert_called_once_with({"query": "What is BSG?"})
        module.web_search.invoke.assert_called_once_with("What is BSG?")

    def test_graph_empty_result_triggers_web_fallback(self, module):
        module.graph_cypher_chain.invoke.return_value = {"result": ""}
        module.web_search.invoke.return_value = "Web result"
        mock_response = MagicMock()
        mock_response.content = "Answer from web"
        module.synthesizer_llm.invoke.return_value = mock_response

        result = module.hybrid_rag_runner({"input": "test question"})

        assert result["output"] == "Answer from web"

    def test_graph_dont_know_triggers_web(self, module):
        module.graph_cypher_chain.invoke.return_value = {"result": "I don't know the answer"}
        module.web_search.invoke.return_value = "Web fallback"
        mock_response = MagicMock()
        mock_response.content = "Fallback answer"
        module.synthesizer_llm.invoke.return_value = mock_response

        result = module.hybrid_rag_runner({"input": "unknown topic"})

        assert result["output"] == "Fallback answer"

    def test_graph_exception_caught(self, module):
        module.graph_cypher_chain.invoke.side_effect = Exception("Neo4j down")
        module.web_search.invoke.return_value = "Web result works"
        mock_response = MagicMock()
        mock_response.content = "Recovered answer"
        module.synthesizer_llm.invoke.return_value = mock_response

        result = module.hybrid_rag_runner({"input": "test"})

        assert result["output"] == "Recovered answer"

    def test_web_exception_caught(self, module):
        module.graph_cypher_chain.invoke.return_value = {"result": "Graph data"}
        module.web_search.invoke.side_effect = Exception("DuckDuckGo down")
        mock_response = MagicMock()
        mock_response.content = "Graph-only answer"
        module.synthesizer_llm.invoke.return_value = mock_response

        result = module.hybrid_rag_runner({"input": "test"})

        assert result["output"] == "Graph-only answer"

    def test_both_exceptions_caught(self, module):
        module.graph_cypher_chain.invoke.side_effect = Exception("Neo4j down")
        module.web_search.invoke.side_effect = Exception("Web down")
        mock_response = MagicMock()
        mock_response.content = "Recovered from all errors"
        module.synthesizer_llm.invoke.return_value = mock_response

        result = module.hybrid_rag_runner({"input": "test"})

        assert result["output"] == "Recovered from all errors"

    def test_synthesizer_exception_returns_error_message(self, module):
        module.graph_cypher_chain.invoke.return_value = {"result": "Graph data"}
        module.web_search.invoke.return_value = "Web data"
        module.synthesizer_llm.invoke.side_effect = Exception("LLM failure")

        result = module.hybrid_rag_runner({"input": "test"})

        assert "Error synthesizing response" in result["output"]


class TestSessionHistory:
    def test_get_session_history_creates_new(self, module):
        history = module.get_session_history("session-1")
        assert history is not None

    def test_get_session_history_returns_same(self, module):
        h1 = module.get_session_history("session-2")
        h2 = module.get_session_history("session-2")
        assert h1 is h2

    def test_get_session_history_different_sessions(self, module):
        h1 = module.get_session_history("session-a")
        h2 = module.get_session_history("session-b")
        assert h1 is not h2


class TestModuleExports:
    def test_agent_with_chat_history_exists(self, module):
        assert hasattr(module, "agent_with_chat_history")

    def test_graph_rag_executor_exists(self, module):
        assert hasattr(module, "graph_rag_executor")

    def test_synthesizer_llm_exists(self, module):
        assert hasattr(module, "synthesizer_llm")

    def test_web_search_exists(self, module):
        assert hasattr(module, "web_search")

    def test_hybrid_rag_runner_is_callable(self, module):
        assert callable(module.hybrid_rag_runner)
