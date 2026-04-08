from typing import Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings
from app.models.schemas import ContentType
from app.services.llm.base import LLMProvider
from app.services.prompts import (
    NATURAL_LANGUAGE_TO_SMT_SYSTEM_PROMPT,
    SMT_OPTIMIZATION_SYSTEM_PROMPT,
    SMT_REFLECTION_SYSTEM_PROMPT,
    SMT_VERIFIER_SYSTEM_PROMPT,
    build_natural_language_to_smt_user_prompt,
    build_reflection_user_prompt,
    build_repair_user_prompt,
    build_smt_optimization_user_prompt,
    build_verifier_user_prompt,
    get_repair_system_prompt,
)


class OpenAICompatibleLLMProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def natural_language_to_smt(self, content: str) -> str:
        return await self._chat(
            system_prompt=NATURAL_LANGUAGE_TO_SMT_SYSTEM_PROMPT,
            user_prompt=build_natural_language_to_smt_user_prompt(content),
        )

    async def optimize_smt(
        self,
        content: str,
        optimization_context: Optional[str] = None,
    ) -> str:
        return await self._chat(
            system_prompt=SMT_OPTIMIZATION_SYSTEM_PROMPT,
            user_prompt=build_smt_optimization_user_prompt(content, optimization_context),
        )

    async def diagnose_smt_issue(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        return await self._chat(
            system_prompt=SMT_VERIFIER_SYSTEM_PROMPT,
            user_prompt=build_verifier_user_prompt(
                request_type,
                source_input,
                current_output,
                validation_feedback,
                reference_smt,
            ),
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
        return await self._chat(
            system_prompt=SMT_REFLECTION_SYSTEM_PROMPT,
            user_prompt=build_reflection_user_prompt(
                request_type,
                source_input,
                current_output,
                validation_feedback,
                verifier_report,
                reference_smt,
            ),
        )

    async def repair_smt(
        self,
        request_type: ContentType,
        source_input: str,
        current_output: str,
        validation_feedback: str,
        reference_smt: Optional[str] = None,
    ) -> str:
        return await self._chat(
            system_prompt=get_repair_system_prompt(request_type),
            user_prompt=build_repair_user_prompt(
                request_type,
                source_input,
                current_output,
                validation_feedback,
                reference_smt,
            ),
        )

    async def _chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self._settings.llm_api_base_url or not self._settings.llm_model:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "LLM_API_BASE_URL or LLM_MODEL is not configured for the openai_compatible provider."
                ),
            )

        url = f"{self._settings.llm_api_base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self._settings.llm_api_key}"

        payload = {
            "model": self._settings.llm_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.llm_timeout_seconds
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or str(exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM API returned an error: {detail[:500]}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to call the LLM API: {exc}",
            ) from exc

        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not content:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The LLM API response did not contain any text.",
            )

        return _strip_markdown_fences(content)


def _strip_markdown_fences(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
