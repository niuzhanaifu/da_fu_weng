from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from . import repository
from .backtest import run_backtest
from .schemas import (
    BacktestExperimentItemOut,
    BacktestExperimentOut,
    BacktestRequest,
    BacktestResultOut,
    DailyGroupOut,
    MarketBoard,
    SelectionRunOut,
    StockPickOut,
)
from .strategy import PickSnapshot
from .strategy import select_limit_up
from .tushare_provider import TushareError, fetch_daily_quotes_range, fetch_market_index_quotes_range


DEFAULT_INDICATORS = ["volume", "seal", "close"]
FULL_DAILY_QUOTE_MIN_COUNT = 1000
DEFAULT_SYNC_DAYS = 92


@dataclass(frozen=True)
class BacktestProfile:
    id: str
    name: str
    description: str
    first_limit_only: bool
    exclude_st: bool = True
    limit_shapes: set[str] | None = None
    engine_strategy_id: str = "old_cat"


BACKTEST_PROFILES: dict[str, BacktestProfile] = {
    "old_cat": BacktestProfile(
        id="old_cat",
        name="老猫战法",
        description="首板、非一字板；第三个交易日开盘涨幅不超过 5% 买入；10% 止盈，分时均线止损。",
        first_limit_only=True,
        exclude_st=True,
    ),
    "old_cat_all_limit": BacktestProfile(
        id="old_cat_all_limit",
        name="老猫对照：全部涨停",
        description="不限制首板，只排除一字板；其余买卖规则与老猫战法一致。",
        first_limit_only=False,
        exclude_st=True,
    ),
    "old_cat_morning_first": BacktestProfile(
        id="old_cat_morning_first",
        name="老猫对照：首板早盘",
        description="只做首板且涨停形态为早上封板；其余买卖规则与老猫战法一致。",
        first_limit_only=True,
        exclude_st=True,
        limit_shapes={"morning"},
    ),
    "old_cat_clean_first": BacktestProfile(
        id="old_cat_clean_first",
        name="老猫对照：首板非炸板",
        description="只做首板，排除炸板回封；其余买卖规则与老猫战法一致。",
        first_limit_only=True,
        exclude_st=True,
        limit_shapes={"morning", "afternoon"},
    ),
}


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
    return SelectionRunOut(
        trade_date=selected_date,
        run_id=0,
        generated_at=current_timestamp(),
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
    selected_date = trade_date or repository.latest_quote_date(conn)
    if not selected_date:
        raise ValueError("No daily quotes available.")

    indicators = list(indicator_ids or DEFAULT_INDICATORS)
    ensure_quotes_for_date(conn, selected_date)
    snapshots = select_limit_up(repository.load_quotes(conn, selected_date), indicators)
    snapshots = apply_backtest_profile(conn, snapshots, BACKTEST_PROFILES["old_cat"])
    picks = [snapshot_to_pick(conn, snapshot, holding_days=3) for snapshot in snapshots]
    return DailyGroupOut(
        trade_date=selected_date,
        generated_at=current_timestamp(),
        indicator_ids=indicators,
        main_count=sum(1 for pick in picks if pick.board.value == "main"),
        chinext_count=sum(1 for pick in picks if pick.board.value == "chinext"),
        picks=picks,
    )


def run_saved_backtest(conn: sqlite3.Connection, request: BacktestRequest) -> BacktestResultOut:
    profile = BACKTEST_PROFILES.get(request.strategy_id)
    if profile is None:
        raise ValueError(f"Unsupported backtest strategy: {request.strategy_id}")
    ensure_quotes_for_backtest(conn, request.start_date, request.end_date)
    picks = build_backtest_picks(
        conn,
        request.start_date,
        request.end_date,
        DEFAULT_INDICATORS,
        request.holding_days,
        request.board.value if request.board else None,
        profile,
        request.allow_below_market_ma25,
    )
    return run_backtest(
        picks=picks,
        holding_days=request.holding_days,
        take_profit_percent=request.take_profit_percent,
        strategy_id=profile.engine_strategy_id,
        initial_capital=request.initial_capital,
        max_positions_per_day=request.max_positions_per_day,
    )


def run_backtest_experiment(conn: sqlite3.Connection, request: BacktestRequest) -> BacktestExperimentOut:
    ensure_quotes_for_backtest(conn, request.start_date, request.end_date)
    items: list[BacktestExperimentItemOut] = []
    for profile in BACKTEST_PROFILES.values():
        picks = build_backtest_picks(
            conn,
            request.start_date,
            request.end_date,
            DEFAULT_INDICATORS,
            request.holding_days,
            request.board.value if request.board else None,
            profile,
            request.allow_below_market_ma25,
        )
        result = run_backtest(
            picks=picks,
            holding_days=request.holding_days,
            take_profit_percent=request.take_profit_percent,
            strategy_id=profile.engine_strategy_id,
            initial_capital=request.initial_capital,
            max_positions_per_day=request.max_positions_per_day,
        )
        items.append(
            BacktestExperimentItemOut(
                strategy_id=profile.id,
                strategy_name=profile.name,
                description=profile.description,
                result=result,
            )
        )
    return BacktestExperimentOut(
        start_date=request.start_date,
        end_date=request.end_date,
        board=request.board,
        items=sorted(items, key=lambda item: item.result.total_return_percent, reverse=True),
    )


def sync_tushare_quotes(conn: sqlite3.Connection, start_date: str, end_date: str) -> int:
    quotes = fetch_daily_quotes_range(start_date, end_date)
    if not quotes:
        raise ValueError(f"No Tushare quotes found from {start_date} to {end_date}.")
    count = repository.upsert_daily_quotes(conn, quotes)
    try:
        repository.upsert_market_index_quotes(conn, fetch_market_index_quotes_range(start_date, end_date))
    except TushareError:
        # 指数数据只用于大盘 25 日均线过滤，缺失时不影响个股行情同步。
        pass
    return count


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
    board: str | None = None,
    profile: BacktestProfile | None = None,
    allow_below_market_ma25: bool = True,
) -> list[StockPickOut]:
    picks: list[StockPickOut] = []
    for trade_date in repository.quote_dates_between(conn, start_date, end_date):
        if not allow_below_market_ma25 and not market_above_ma25(conn, trade_date):
            continue
        snapshots = select_limit_up(repository.load_quotes(conn, trade_date), indicator_ids)
        if board:
            snapshots = [snapshot for snapshot in snapshots if snapshot.board.value == board]
        if profile is not None:
            snapshots = apply_backtest_profile(conn, snapshots, profile)
        picks.extend(snapshot_to_pick(conn, snapshot, holding_days) for snapshot in snapshots)
    return picks


def apply_backtest_profile(
    conn: sqlite3.Connection,
    snapshots: Sequence[PickSnapshot],
    profile: BacktestProfile,
) -> list[PickSnapshot]:
    filtered = list(snapshots)
    if profile.exclude_st:
        filtered = [snapshot for snapshot in filtered if not is_st_stock(snapshot.name)]
    if profile.limit_shapes is not None:
        filtered = [snapshot for snapshot in filtered if snapshot.limit_shape in profile.limit_shapes]
    if profile.first_limit_only:
        filtered = [snapshot for snapshot in filtered if is_first_limit_up(conn, snapshot)]
    return filtered


def is_first_limit_up(conn: sqlite3.Connection, snapshot: PickSnapshot) -> bool:
    previous = repository.previous_quote_for_code(conn, snapshot.code, snapshot.trade_date)
    if previous is None:
        return True
    board = MarketBoard(previous["board"])
    expected = previous["previous_close"] * (1.0 + board.limit_up_rate)
    return not (previous["close"] >= expected - 0.02 and previous["close"] >= previous["high"] - 0.02)


def is_st_stock(name: str) -> bool:
    normalized = name.upper().replace(" ", "")
    return "ST" in normalized or "退" in normalized


def market_above_ma25(conn: sqlite3.Connection, trade_date: str) -> bool:
    return repository.market_index_above_ma25(conn, "000001.SH", trade_date)


def snapshot_to_pick(
    conn: sqlite3.Connection,
    snapshot: PickSnapshot,
    holding_days: int,
) -> StockPickOut:
    future_bars = repository.future_bars(conn, snapshot.code, snapshot.trade_date, holding_days + 2)
    next_open = future_bars[0]["open"] if future_bars else None
    latest = repository.latest_quote_for_code(conn, snapshot.code)
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
        limit_shape=snapshot.limit_shape,
        limit_shape_label=snapshot.limit_shape_label,
        latest_trade_date=latest["trade_date"] if latest else None,
        latest_close=latest["close"] if latest else None,
        next_open=next_open,
        future_closes=[bar["close"] for bar in future_bars],
        future_highs=[bar["high"] for bar in future_bars],
        future_opens=[bar["open"] for bar in future_bars],
        future_dates=[bar["trade_date"] for bar in future_bars],
        recent_3day_change_percent=repository.recent_change_percent(conn, snapshot.code, snapshot.trade_date, 3),
        recent_5day_change_percent=repository.recent_change_percent(conn, snapshot.code, snapshot.trade_date, 5),
        minute_trades=[],
    )


def date_days_before(trade_date: str, days: int) -> str:
    date = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=days)
    return date.strftime("%Y-%m-%d")


def current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
