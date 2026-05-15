from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from . import __version__
from .config import settings
from .db import get_db, init_db
from .repository import load_daily_candles, upsert_daily_quotes
from .sample_data import sample_quotes
from .schemas import (
    BacktestRequest,
    BacktestResultOut,
    DailyCandleOut,
    DailyGroupOut,
    DailyQuoteIn,
    IndicatorOption,
    SelectionRunOut,
)
from .service import DEFAULT_INDICATORS, get_group, run_daily_selection, run_saved_backtest
from .strategy import INDICATORS

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
                "description": "涨停板次日开盘 1 分钟后，如果价格相对涨停日收盘价涨幅不超过 3% 就买入；止损价为涨停板当天的成交分时均价。",
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

    @app.post("/api/v1/admin/run-daily-selection", response_model=SelectionRunOut)
    def run_selection(
        _: Annotated[None, Depends(require_admin)],
        trade_date: str | None = Query(default=None),
        indicator_ids: list[str] | None = Query(default=None),
        conn=Depends(get_db),
    ) -> SelectionRunOut:
        try:
            result = run_daily_selection(conn, trade_date, indicator_ids or DEFAULT_INDICATORS)
        except ValueError as exc:
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
        try:
            result = run_saved_backtest(conn, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info(
            "backtest strategy=%s trades=%s win_rate=%.2f return=%.2f max_drawdown=%.2f",
            request.strategy_id,
            result.total_trades,
            result.win_rate,
            result.total_return_percent,
            result.max_drawdown_percent,
        )
        return result

    return app


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def configure_logging() -> None:
    if logger.handlers:
        return
    Path("logs").mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler("logs/server.log", maxBytes=5 * 1024 * 1024, backupCount=10)
    file_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[stream_handler, file_handler])


app = create_app()
