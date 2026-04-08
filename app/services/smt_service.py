from app.core.config import Settings
from app.models.schemas import ContentType, TransformRequest, TransformResponse
from app.services.detection import detect_content_type
from app.services.llm.factory import create_llm_provider
from app.services.workflow import SMTWorkflowService


class SMTService:
    def __init__(self, settings: Settings) -> None:
        self._provider = create_llm_provider(settings)
        self._workflow = SMTWorkflowService(settings=settings, provider=self._provider)

    async def transform(self, payload: TransformRequest) -> TransformResponse:
        request_type = payload.content_type

        if request_type == ContentType.AUTO:
            request_type = detect_content_type(payload.content)

        if request_type == ContentType.NATURAL_LANGUAGE:
            workflow_result = await self._workflow.generate_from_text(payload.content)
        else:
            workflow_result = await self._workflow.optimize_smt(payload.content)

        return TransformResponse(
            success=workflow_result.success,
            request_type=request_type,
            result=workflow_result.result,
            provider=self._provider.name,
            message=workflow_result.message,
            trace_id=payload.trace_id,
            validation=workflow_result.validation,
            workflow=workflow_result.workflow,
            source_validation=workflow_result.source_validation,
            equivalence=workflow_result.equivalence,
            agent_trace=workflow_result.agent_trace,
            optimization_summary=workflow_result.optimization_summary,
        )
