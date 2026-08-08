import logging
from typing import Any, AsyncGenerator, Optional
from dataclasses import dataclass, field, asdict

from app.core.config import settings
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.graph_store import GraphStoreService

logger = logging.getLogger(__name__)


@dataclass
class RAGSource:
    text: str
    source: str
    score: float
    type: str  # "vector" | "graph" | "web"


@dataclass
class RAGResult:
    answer: str
    sources: list[RAGSource] = field(default_factory=list)
    confidence: float = 0.0
    model_used: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [asdict(s) for s in self.sources],
            "confidence": self.confidence,
            "model_used": self.model_used,
        }


class RAGPipeline:
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[VectorStoreService] = None,
        graph_store: Optional[GraphStoreService] = None,
    ) -> None:
        self._embeddings = embedding_service or EmbeddingService()
        self._vector_store = vector_store or VectorStoreService()
        self._graph_store = graph_store
        self._llm_client: Optional[Any] = None
        self._llm_model: str = ""
        self._init_llm()

    def _init_llm(self) -> None:
        if settings.openai_api_key:
            try:
                import openai
                self._llm_client = openai.OpenAI(api_key=settings.openai_api_key)
                self._llm_model = "openai"
                return
            except Exception as e:
                logger.warning("OpenAI LLM init failed: %s", e)

        if settings.google_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.google_api_key)
                self._llm_client = genai
                self._llm_model = "google"
                return
            except Exception as e:
                logger.warning("Google LLM init failed: %s", e)

        if settings.anthropic_api_key:
            try:
                import anthropic
                self._llm_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                self._llm_model = "anthropic"
                return
            except Exception as e:
                logger.warning("Anthropic LLM init failed: %s", e)

        logger.warning("No LLM backend configured; RAG will return raw context only")

    async def _search_web(self, question: str, max_results: int = 3) -> list[RAGSource]:
        sources: list[RAGSource] = []
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(question, max_results=max_results))
                for r in results:
                    sources.append(RAGSource(
                        text=r.get("body", ""),
                        source=r.get("href", ""),
                        score=0.5,
                        type="web",
                    ))
        except ImportError:
            logger.warning("duckduckgo_search not installed; skipping web search")
        except Exception as e:
            logger.warning("Web search failed: %s", e)
        return sources

    async def query(
        self,
        question: str,
        repo_id: Optional[str] = None,
    ) -> dict[str, Any]:
        sources: list[RAGSource] = []

        query_vector = self._embeddings.get_embeddings([question])[0]

        vector_results = self._vector_store.search(
            collection=repo_id or "default",
            query_vector=query_vector,
            limit=5,
        )
        for r in vector_results:
            sources.append(RAGSource(
                text=str(r.get("payload", {}).get("content", "")),
                source=r.get("payload", {}).get("file_path", "vector_store"),
                score=r.get("score", 0.0),
                type="vector",
            ))

        if self._graph_store:
            try:
                graph_results = await self._graph_store.search_by_embedding(
                    vector=query_vector,
                    limit=5,
                )
                for r in graph_results:
                    sources.append(RAGSource(
                        text=r.get("content", r.get("file_path", "")),
                        source=r.get("file_path", "graph"),
                        score=r.get("score", 0.0),
                        type="graph",
                    ))
            except Exception as e:
                logger.warning("Graph search failed: %s", e)

        web_sources = await self._search_web(question)
        sources.extend(web_sources)

        sources = sources[:15]

        if not sources:
            return RAGResult(
                answer="No relevant context found to answer the question.",
                sources=[],
                confidence=0.0,
                model_used="",
            ).to_dict()

        avg_score = sum(s.score for s in sources) / len(sources)
        context = "\n\n".join(
            f"[{s.type.upper()}] {s.text[:500]}" for s in sources
        )

        prompt = f"""You are a helpful AI assistant. Answer the user's question based on the provided context.

Context:
{context}

Question: {question}

Provide a concise, accurate answer based on the context above. If the context doesn't contain enough information, say so."""

        answer = await self._synthesize(prompt)

        return RAGResult(
            answer=answer,
            sources=sources,
            confidence=round(avg_score, 4),
            model_used=self._llm_model,
        ).to_dict()

    async def _synthesize(self, prompt: str) -> str:
        if self._llm_model == "openai" and self._llm_client is not None:
            try:
                resp = self._llm_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1024,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:
                logger.error("OpenAI synthesis failed: %s", e)

        if self._llm_model == "google" and self._llm_client is not None:
            try:
                model = self._llm_client.GenerativeModel("gemini-2.0-flash")
                resp = model.generate_content(prompt)
                return resp.text or ""
            except Exception as e:
                logger.error("Google synthesis failed: %s", e)

        if self._llm_model == "anthropic" and self._llm_client is not None:
            try:
                resp = self._llm_client.messages.create(
                    model="claude-3-5-haiku-latest",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text if resp.content else ""
            except Exception as e:
                logger.error("Anthropic synthesis failed: %s", e)

        return "Unable to synthesize answer. No LLM backend available."

    async def query_stream(
        self,
        question: str,
        repo_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream the RAG answer token by token."""
        sources: list[RAGSource] = []
        query_vector = self._embeddings.get_embeddings([question])[0]

        vector_results = self._vector_store.search(
            collection=repo_id or "default",
            query_vector=query_vector,
            limit=3,
        )
        for r in vector_results:
            sources.append(RAGSource(
                text=str(r.get("payload", {}).get("content", "")),
                source=r.get("payload", {}).get("file_path", "vector_store"),
                score=r.get("score", 0.0),
                type="vector",
            ))

        context = "\n\n".join(f"[{s.type.upper()}] {s.text[:500]}" for s in sources) if sources else "No context available."
        prompt = f"""You are a helpful AI assistant. Answer the user's question based on the provided context.

Context:
{context}

Question: {question}

Provide a concise, accurate answer based on the context above."""

        if self._llm_model == "openai" and self._llm_client is not None:
            try:
                resp = self._llm_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1024,
                    stream=True,
                )
                for chunk in resp:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        yield content
                return
            except Exception as e:
                logger.error("OpenAI streaming failed: %s", e)

        yield await self._synthesize(prompt)
