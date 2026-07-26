from abc import ABC, abstractmethod
import os
from typing import Optional


class BaseAgent(ABC):
    name: str = ""
    description: str = ""
    model: str = "gpt-4"

    def __init__(self, llm: Optional[object] = None):
        self._llm = llm or self._get_llm()

    def _get_llm(self) -> object:
        openai_key = os.getenv("OPENAI_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")

        if openai_key:
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(model=self.model, temperature=0.1)
            except ImportError:
                pass

        if anthropic_key:
            try:
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0.1)
            except ImportError:
                pass

        if google_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.1)
            except ImportError:
                pass

        raise RuntimeError(
            "No LLM provider available. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "or GOOGLE_API_KEY and install the corresponding langchain package."
        )

    @abstractmethod
    async def run(self, input: dict) -> dict:
        pass
