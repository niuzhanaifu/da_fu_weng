from __future__ import annotations

import json
import sqlite3
from typing import Sequence

from . import repository
from .backtest import run_backtest
from .schemas import BacktestRequest, BacktestResultOut, DailyGroupOut, SelectionRunOut
from .strategy import select_limit_up
from .tushare_provider import fetch_daily_quotes


DEFAULT_INDICATORS = ["volume", "seal", "close"]


def run_daily_selection(
    conn: sqlite3.Connection,
    trade_date: str | None,
    indicator_ids: Sequence[str] | None = None,
) -> SelectionRunOut:
    selected_date = trade_date or repository.latest_quote_date(conn)
    if not selected_date:
        raise ValueError("No daily quotes available.")

    indicators = list(indicator_ids or DEFAULT_INDICATORS)
    quotes = repository.load_quotes(conn, selected_date)
    if not quotes:
        imported = fetch_daily_quotes(selected_date)
        if not imported:
            raise ValueError(f"No Tushare quotes found for {selected_date}.")
        repository.upsert_daily_quotes(conn, imported)
        quotes = repository.load_quotes(conn, selected_date)

    picks = select_limit_up(quotes, indicators)
    run_id, generated_at = repository.save_selection_run(conn, selected_date, indicators, picks)
    return SelectionRunOut(
        trade_date=selected_date,
        run_id=run_id,
        generated_at=generated_at,
        pick_count=len(picks),
        indicator_ids=indicators,
    )


def get_group(conn: sqlite3.Connection, trade_date: str | None = None) -> DailyGroupOut | None:
    run = repository.latest_run_for_date(conn, trade_date)
    if not run:
        return None
    picks = repository.load_picks_for_run(conn, int(run["id"]))
    return DailyGroupOut(
        trade_date=run["trade_date"],
        generated_at=run["generated_at"],
        indicator_ids=json.loads(run["indicator_ids_json"]),
        main_count=sum(1 for pick in picks if pick.board.value == "main"),
        chinext_count=sum(1 for pick in picks if pick.board.value == "chinext"),
        picks=picks,
    )


def run_selection_group(
    conn: sqlite3.Connection,
    trade_date: str | None,
    indicator_ids: Sequence[str] | None = None,
) -> DailyGroupOut:
    run = run_daily_selection(conn, trade_date, indicator_ids)
    group = get_group(conn, run.trade_date)
    if group is None:
        raise ValueError("Selection completed but no group was saved.")
    return group


def run_saved_backtest(conn: sqlite3.Connection, request: BacktestRequest) -> BacktestResultOut:
    picks = repository.load_picks_for_backtest(conn, request.start_date, request.end_date)
    return run_backtest(
        picks=picks,
        holding_days=request.holding_days,
        take_profit_percent=request.take_profit_percent,
        strategy_id=request.strategy_id,
    )
