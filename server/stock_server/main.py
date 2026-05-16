from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from . import __version__
from .config import settings
from .db import get_db, init_db
from .logging_config import configure_logging
from .repository import load_daily_candles, upsert_daily_quotes
from .sample_data import sample_quotes
from .schemas import (
    BacktestRequest,
    BacktestResultOut,
    DailyCandleOut,
    DailyGroupOut,
    DailyQuoteIn,
    IndicatorOption,
    SelectionRequest,
    SelectionRunOut,
)
from .service import DEFAULT_INDICATORS, get_group, run_daily_selection, run_saved_backtest, run_selection_group, sync_tushare_quotes
from .strategy import INDICATORS
from .tushare_provider import TushareError, fetch_daily_quotes

import logging

logger = logging.getLogger("stock_server")


def create_app() -> FastAPI:
    configure_logging()
    init_db()
    app = FastAPI(title="Da Fu Weng Stock Server", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/indicators", response_model=list[IndicatorOption])
    def indicators() -> list[IndicatorOption]:
        return INDICATORS

    @app.get("/api/v1/backtest-strategies")
    def backtest_strategies() -> list[dict[str, str]]:
        return [
            {
                "id": "old_cat",
                "name": "老猫战法",
                "description": "排除一字涨停板；涨停后第三个交易日开盘检查，若相对涨停日收盘价涨幅不超过 5% 则按纪律买入，分时均线作为止损价；买入后涨幅达到 10% 强制平仓。",
            }
        ]

    @app.post("/api/v1/admin/quotes", response_model=dict[str, int])
    def import_quotes(
        quotes: list[DailyQuoteIn],
        _: Annotated[None, Depends(require_admin)],
        conn=Depends(get_db),
    ) -> dict[str, int]:
        count = upsert_daily_quotes(conn, quotes)
        logger.info("imported quotes count=%s", count)
        return {"count": count}

    @app.post("/api/v1/admin/seed-sample", response_model=dict[str, int])
    def seed_sample(
        _: Annotated[None, Depends(require_admin)],
        conn=Depends(get_db),
    ) -> dict[str, int]:
        count = upsert_daily_quotes(conn, sample_quotes())
        logger.info("seeded sample quotes count=%s", count)
        return {"count": count}

    @app.post("/api/v1/admin/import-tushare", response_model=dict[str, int])
    def import_tushare(
        _: Annotated[None, Depends(require_admin)],
        trade_date: str = Query(...),
        conn=Depends(get_db),
    ) -> dict[str, int]:
        try:
            quotes = fetch_daily_quotes(trade_date)
        except TushareError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        count = upsert_daily_quotes(conn, quotes)
        logger.info("imported tushare quotes trade_date=%s count=%s", trade_date, count)
        return {"count": count}

    @app.post("/api/v1/admin/sync-tushare", response_model=dict[str, int | str])
    def sync_tushare(
        _: Annotated[None, Depends(require_admin)],
        start_date: str = Query(...),
        end_date: str = Query(...),
        conn=Depends(get_db),
    ) -> dict[str, int | str]:
        try:
            count = sync_tushare_quotes(conn, start_date, end_date)
        except TushareError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info("synced tushare quotes start_date=%s end_date=%s count=%s", start_date, end_date, count)
        return {"start_date": start_date, "end_date": end_date, "count": count}

    @app.post("/api/v1/admin/run-daily-selection", response_model=SelectionRunOut)
    def run_selection(
        _: Annotated[None, Depends(require_admin)],
        trade_date: str | None = Query(default=None),
        indicator_ids: list[str] | None = Query(default=None),
        conn=Depends(get_db),
    ) -> SelectionRunOut:
        try:
            result = run_daily_selection(conn, trade_date, indicator_ids or DEFAULT_INDICATORS)
        except (ValueError, TushareError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info(
            "selection run trade_date=%s run_id=%s picks=%s indicators=%s",
            result.trade_date,
            result.run_id,
            result.pick_count,
            result.indicator_ids,
        )
        return result

    @app.get("/api/v1/groups/latest", response_model=DailyGroupOut)
    def latest_group(conn=Depends(get_db)) -> DailyGroupOut:
        group = get_group(conn)
        if not group:
            raise HTTPException(status_code=404, detail="No selection run found.")
        return group

    @app.get("/api/v1/groups/{trade_date}", response_model=DailyGroupOut)
    def group_by_date(trade_date: str, conn=Depends(get_db)) -> DailyGroupOut:
        group = get_group(conn, trade_date)
        if not group:
            raise HTTPException(status_code=404, detail="No selection run found for date.")
        return group

    @app.post("/api/v1/selections/run", response_model=DailyGroupOut)
    def run_public_selection(request: SelectionRequest, conn=Depends(get_db)) -> DailyGroupOut:
        try:
            group = run_selection_group(conn, request.trade_date, request.indicator_ids)
        except (ValueError, TushareError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info(
            "public selection trade_date=%s indicators=%s picks=%s",
            group.trade_date,
            group.indicator_ids,
            len(group.picks),
        )
        return group

    @app.get("/api/v1/stocks/{code}/candles", response_model=list[DailyCandleOut])
    def stock_candles(
        code: str,
        start_date: str | None = Query(default=None),
        end_date: str | None = Query(default=None),
        limit: int = Query(default=120, ge=1, le=500),
        conn=Depends(get_db),
    ) -> list[DailyCandleOut]:
        candles = load_daily_candles(conn, code, start_date, end_date, limit)
        if not candles:
            raise HTTPException(status_code=404, detail="No candles found for stock.")
        return candles

    @app.post("/api/v1/backtests", response_model=BacktestResultOut)
    def backtest(request: BacktestRequest, conn=Depends(get_db)) -> BacktestResultOut:
        started_at = time.perf_counter()
        try:
            result = run_saved_backtest(conn, request)
        except (ValueError, TushareError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "backtest strategy=%s start_date=%s end_date=%s board=%s trades=%s win_rate=%.2f return=%.2f max_drawdown=%.2f elapsed_ms=%s",
            request.strategy_id,
            request.start_date,
            request.end_date,
            request.board.value if request.board else "all",
            result.total_trades,
            result.win_rate,
            result.total_return_percent,
            result.max_drawdown_percent,
            elapsed_ms,
        )
        return result

    return app


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


app = create_app()
