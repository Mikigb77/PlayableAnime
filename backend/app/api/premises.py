from fastapi import APIRouter

from app.premises import SEED_PREMISES, Premise

router = APIRouter(prefix="/v1/premises", tags=["premises"])


@router.get("")
async def list_premises() -> list[Premise]:
    return SEED_PREMISES
