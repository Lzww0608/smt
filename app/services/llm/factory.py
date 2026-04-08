from app.core.config import Settings
from app.services.llm.base import LLMProvider
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.openai_compatible_provider import OpenAICompatibleLLMProvider
from app.services.llm.pending_provider import PendingLLMProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.lower().strip()

    if provider == "mock":
        return MockLLMProvider()

    if provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(settings)

    return PendingLLMProvider()
