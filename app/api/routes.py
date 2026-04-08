from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.models.schemas import TransformRequest, TransformResponse
from app.services.smt_service import SMTService


router = APIRouter()


def get_service(settings: Settings = Depends(get_settings)) -> SMTService:
    return SMTService(settings=settings)


@router.post(
    "/api/v1/smt/transform",
    response_model=TransformResponse,
    tags=["smt"],
)
async def transform_content(
    payload: TransformRequest,
    service: SMTService = Depends(get_service),
) -> TransformResponse:
    return await service.transform(payload)
