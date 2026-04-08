from typing import Optional

from fastapi import HTTPException, status

from app.models.schemas import ContentType
from app.services.llm.base import LLMProvider


class PendingLLMProvider(LLMProvider):
    name = "pending"

    async def natural_language_to_smt(self, content: str) -> str:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Unsupported LLM_PROVIDER. Supported values: mock, openai_compatible.",
        )

    async def optimize_smt(
        self,
        content: str,
        optimization_context: Optional[str] = None,
    ) -> str:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Unsupported LLM_PROVIDER. Supported values: mock, openai_compatible.",
        )

    async def diagnose_smt_issue(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Unsupported LLM_PROVIDER. Supported values: mock, openai_compatible.",
        )

    async def reflect_on_smt_issue(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        verifier_report: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Unsupported LLM_PROVIDER. Supported values: mock, openai_compatible.",
        )

    async def repair_smt(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Unsupported LLM_PROVIDER. Supported values: mock, openai_compatible.",
        )
