from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/healthz")
async def get_healthz() -> dict[str, bool]:
    return {"ok": True}
