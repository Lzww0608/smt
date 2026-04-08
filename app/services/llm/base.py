from abc import ABC, abstractmethod
from typing import Optional

from app.models.schemas import ContentType


class LLMProvider(ABC):
    name: str = "unknown"

    @abstractmethod
    async def natural_language_to_smt(self, content: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def optimize_smt(
        self,
        content: str,
        optimization_context: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def diagnose_smt_issue(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def reflect_on_smt_issue(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        verifier_report: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def repair_smt(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        raise NotImplementedError
