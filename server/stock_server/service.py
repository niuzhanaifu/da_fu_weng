from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Sequence

from . import repository
from .backtest import run_backtest
from .schemas import BacktestRequest, BacktestResultOut, DailyGroupOut, SelectionRunOut, StockPickOut
from .strategy import PickSnapshot
from .strategy import select_limit_up
from .tushare_provider import fetch_daily_quotes_range


DEFAULT_INDICATORS = ["volume", "seal", "close"]
FULL_DAILY_QUOTE_MIN_COUNT = 1000
DEFAULT_SYNC_DAYS = 92


def run_daily_selection(
    conn: sqlite3.Connection,
    trade_date: str | None,
    indicator_ids: Sequence[str] | None = None,
) -> SelectionRunOut:
    selected_date = trade_date or repository.latest_quote_date(conn)
    if not selected_date:
        raise ValueError("No daily quotes available.")

    indicators = list(indicator_ids or DEFAULT_INDICATORS)
    ensure_quotes_for_date(conn, selected_date)
    quotes = repository.load_quotes(conn, selected_date)
    if not quotes:
        raise ValueError(f"No daily quotes found for {selected_date}.")

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
    ensure_quotes_for_backtest(conn, request.start_date, request.end_date)
    picks = build_backtest_picks(conn, request.start_date, request.end_date, DEFAULT_INDICATORS, request.holding_days)
    return run_backtest(
        picks=picks,
        holding_days=request.holding_days,
        take_profit_percent=request.take_profit_percent,
        strategy_id=request.strategy_id,
        initial_capital=request.initial_capital,
        max_positions_per_day=request.max_positions_per_day,
    )


def sync_tushare_quotes(conn: sqlite3.Connection, start_date: str, end_date: str) -> int:
    quotes = fetch_daily_quotes_range(start_date, end_date)
    if not quotes:
        raise ValueError(f"No Tushare quotes found from {start_date} to {end_date}.")
    return repository.upsert_daily_quotes(conn, quotes)


def ensure_quotes_for_date(conn: sqlite3.Connection, trade_date: str) -> None:
    if repository.count_quotes(conn, trade_date) >= FULL_DAILY_QUOTE_MIN_COUNT:
        return
    sync_tushare_quotes(conn, trade_date, trade_date)


def ensure_quotes_for_backtest(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
) -> None:
    selected_end = end_date or repository.latest_quote_date(conn)
    if not selected_end:
        return
    start = start_date or date_days_before(selected_end, DEFAULT_SYNC_DAYS)
    dates = repository.quote_dates_between(conn, start, selected_end)
    if dates and repository.count_quotes(conn, dates[-1]) >= FULL_DAILY_QUOTE_MIN_COUNT:
        return
    try:
        sync_tushare_quotes(conn, start, selected_end)
    except ValueError:
        return


def build_backtest_picks(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
    indicator_ids: Sequence[str],
    holding_days: int,
) -> list[StockPickOut]:
    picks: list[StockPickOut] = []
    for trade_date in repository.quote_dates_between(conn, start_date, end_date):
        snapshots = select_limit_up(repository.load_quotes(conn, trade_date), indicator_ids)
        picks.extend(snapshot_to_pick(conn, snapshot, holding_days) for snapshot in snapshots)
    return picks


def snapshot_to_pick(
    conn: sqlite3.Connection,
    snapshot: PickSnapshot,
    holding_days: int,
) -> StockPickOut:
    future_bars = repository.future_bars(conn, snapshot.code, snapshot.trade_date, holding_days)
    next_open = future_bars[0]["open"] if future_bars else None
    return StockPickOut(
        trade_date=snapshot.trade_date,
        code=snapshot.code,
        name=snapshot.name,
        board=snapshot.board,
        board_label=snapshot.board.label,
        concept=snapshot.concept,
        close=snapshot.close,
        change_percent=snapshot.change_percent,
        volume_ratio=snapshot.volume_ratio,
        turnover_rate=snapshot.turnover_rate,
        sealed_amount_wan=snapshot.sealed_amount_wan,
        stop_loss_price=snapshot.stop_loss_price,
        next_open=next_open,
        future_closes=[bar["close"] for bar in future_bars],
        future_dates=[bar["trade_date"] for bar in future_bars],
        recent_3day_change_percent=repository.recent_change_percent(conn, snapshot.code, snapshot.trade_date),
        minute_trades=[],
    )


def date_days_before(trade_date: str, days: int) -> str:
    date = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=days)
    return date.strftime("%Y-%m-%d")
