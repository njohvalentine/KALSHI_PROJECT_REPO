"""Market data endpoints for the web app. Login required."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth import require_user
from app.kalshi import KalshiClient, KalshiError, KalshiNotFound

router = APIRouter(prefix="/api", tags=["markets"], dependencies=[Depends(require_user)])


def get_kalshi(request: Request) -> KalshiClient:
    return request.app.state.kalshi


@router.get("/markets")
def list_markets(
    kalshi: Annotated[KalshiClient, Depends(get_kalshi)],
    status: str | None = Query(default="open", max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, max_length=500),
):
    try:
        return kalshi.list_markets(status=status, limit=limit, cursor=cursor)
    except KalshiError as exc:
        raise HTTPException(status_code=502, detail=f"Kalshi request failed: {exc}") from exc


@router.get("/markets/{ticker}")
def get_market(ticker: str, kalshi: Annotated[KalshiClient, Depends(get_kalshi)]):
    try:
        return kalshi.get_market(ticker)
    except KalshiNotFound as exc:
        raise HTTPException(status_code=404, detail="Market not found") from exc
    except KalshiError as exc:
        raise HTTPException(status_code=502, detail=f"Kalshi request failed: {exc}") from exc
