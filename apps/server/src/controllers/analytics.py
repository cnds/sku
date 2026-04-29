from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from schemas import LeaderboardEntry, LeaderboardType, ProductAnalysisResult, TimeWindow
from services.analysis import ProductAnalysisService

router = APIRouter()

BOARD_QUERY = Query()
WINDOW_QUERY = Query()


@router.get("/api/leaderboard")
async def get_leaderboard(
    shop_id: str,
    board: Annotated[LeaderboardType, BOARD_QUERY] = LeaderboardType.BLACK,
    window: Annotated[TimeWindow, WINDOW_QUERY] = TimeWindow.HOURS_24,
) -> list[LeaderboardEntry]:
    return await ProductAnalysisService().get_leaderboard(
        board=board,
        shop_id=shop_id,
        window=window,
    )


@router.get("/api/products/{product_id}/analysis")
async def get_product_analysis(
    product_id: str,
    request: Request,
    shop_id: str,
    window: Annotated[TimeWindow, WINDOW_QUERY] = TimeWindow.HOURS_24,
) -> ProductAnalysisResult:
    return await ProductAnalysisService(
        settings=request.app.state.settings,
    ).get_product_analysis(
        product_id=product_id,
        shop_id=shop_id,
        window=window,
    )
