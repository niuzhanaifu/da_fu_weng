from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Sequence

from . import repository
from .backtest import RANK_MODE_RECENT_5DAY_CHANGE, RANK_MODE_STOP_LOSS_LOSS, rank_daily_picks, run_backtest
from .schemas import (
    BacktestExperimentItemOut,
    BacktestExperimentOut,
    BacktestRequest,
    BacktestResultOut,
    DailyGroupOut,
    DailyQuoteIn,
    MarketBoard,
    SelectionRunOut,
    StockPickOut,
    TradeBookOut,
    TradeBuyRequest,
    TradePositionOut,
    TradeSellRequest,
    TradeStatsOut,
)
from .strategy import PickSnapshot
from .strategy import select_limit_up
from .tushare_provider import TushareError, fetch_daily_quote_batches, fetch_market_index_quotes_range


DEFAULT_INDICATORS = ["volume", "seal", "close"]
FULL_DAILY_QUOTE_MIN_COUNT = 1000
DEFAULT_SYNC_DAYS = 92
JIA_BAN_LOOKBACK_DAYS = 240
JIA_BAN_MIN_HISTORY_DAYS = 120
JIA_BAN_LINE_TOLERANCE = 0.02
JIA_BAN_MAX_BOX_AMPLITUDE = 0.15
JIA_BAN_MAX_T_DAY_DROP_PERCENT = 7.0
OLD_CAT_LIMIT2_LOOKBACK_DAYS = 30
OLD_CAT_LIMIT2_FIRST_BOARD_VOLUME_LOOKBACK = 5
OLD_CAT_LIMIT2_FIRST_BOARD_VOLUME_RATIO = 1.2
OLD_CAT_LIMIT2_PULLBACK_MAX_DROP_PERCENT = 5.0
OLD_CAT_LIMIT2_PULLBACK_VOLUME_RATIO = 0.70
OLD_CAT_LIMIT2_PULLBACK_MAX_BODY_PERCENT = 3.0
ULTRA_SHORT_LOOKBACK_DAYS = 360
ULTRA_SHORT_MIN_HISTORY_DAYS = 114
ULTRA_SHORT_LONG_WINDOW = 21
ULTRA_SHORT_YELLOW_WINDOWS = (14, 28, 57, 114)
ULTRA_SHORT_TURNOVER_MIN = 0.99


@dataclass(frozen=True)
class BacktestProfile:
    id: str
    name: str
    description: str
    first_limit_only: bool
    exclude_st: bool = True
    limit_shapes: set[str] | None = None
    min_total_mv_wan: float | None = None
    max_position_allocation_fraction: float | None = None
    engine_strategy_id: str = "old_cat"
    rank_mode: str = RANK_MODE_RECENT_5DAY_CHANGE
    selector: str = "limit_up"
    max_t_plus_one_close_gain_percent: float = 5.0
    lookback_days: int = 0
    min_history_days: int = 0
    max_positions_per_day: int | None = None


@dataclass(frozen=True)
class SelectionProfile:
    id: str
    name: str
    description: str


BACKTEST_PROFILES: dict[str, BacktestProfile] = {
    "old_cat": BacktestProfile(
        id="old_cat",
        name="老猫战法",
        description="首板且早上封板、非 ST、非一字板；涨停日后第 2 个交易日开盘涨幅不超过 5% 买入；止盈率可设置，触及分时均线止损线时按收盘价卖出。",
        first_limit_only=True,
        exclude_st=True,
        limit_shapes={"morning"},
    ),
    "old_cat_selection_aligned": BacktestProfile(
        id="old_cat_selection_aligned",
        name="老猫对照：选股口径对齐",
        description="T 日首板早上封板、非 ST、非一字板；按 T+1 收盘相对 T 日收盘涨幅不超过 5% 过滤；T+2 开盘价买入。",
        first_limit_only=True,
        exclude_st=True,
        limit_shapes={"morning"},
        engine_strategy_id="old_cat_selection_aligned",
        selector="old_cat_selection_aligned",
    ),
    "old_cat_selection_aligned_8pct": BacktestProfile(
        id="old_cat_selection_aligned_8pct",
        name="老猫对照：选股口径对齐 8%",
        description="T 日首板早上封板、非 ST、非一字板；按 T+1 收盘相对 T 日收盘涨幅不超过 8% 过滤；T+2 开盘价买入。",
        first_limit_only=True,
        exclude_st=True,
        limit_shapes={"morning"},
        engine_strategy_id="old_cat_selection_aligned",
        selector="old_cat_selection_aligned",
        max_t_plus_one_close_gain_percent=8.0,
    ),
    "old_cat_timely_stop_loss": BacktestProfile(
        id="old_cat_timely_stop_loss",
        name="老猫对照：止损价卖出",
        description="选股和买入条件与老猫战法一致；触及分时均线止损线时按止损价卖出。",
        first_limit_only=True,
        exclude_st=True,
        limit_shapes={"morning"},
        engine_strategy_id="old_cat_timely_stop_loss",
    ),
    "old_cat_stop_loss_rank": BacktestProfile(
        id="old_cat_stop_loss_rank",
        name="老猫对照：止损率排序",
        description="选股条件与老猫战法一致；超过 3 只候选时，优先买入到分时均线止损亏损比例最低的股票。",
        first_limit_only=True,
        exclude_st=True,
        limit_shapes={"morning"},
        rank_mode=RANK_MODE_STOP_LOSS_LOSS,
    ),
    "jia_ban": BacktestProfile(
        id="jia_ban",
        name="夹板战法",
        description="近 120 个交易日构建六个月箱体，箱体振幅不超过 15%；T 日收盘回踩下轨且成交量为阶段地量，跌幅不超过 7%；T+1 开盘买入，反弹到上轨或达到回测止盈率卖出，跌破下轨止损。",
        first_limit_only=False,
        exclude_st=True,
        engine_strategy_id="jia_ban",
        rank_mode=RANK_MODE_STOP_LOSS_LOSS,
        selector="jia_ban",
        lookback_days=JIA_BAN_LOOKBACK_DAYS,
        min_history_days=JIA_BAN_MIN_HISTORY_DAYS,
        max_positions_per_day=3,
    ),
    "old_cat_limit2": BacktestProfile(
        id="old_cat_limit2",
        name="老猫涨停2对比",
        description="第一板放量涨停后连续 2 个交易日缩量夹板回调，回调不跌破第一板开盘价、不再涨停且单日跌幅不超 5%；随后第二板放量涨停确认，次日开盘买入，跌破第一板开盘价止损，止盈率和持有天数沿用 APP 参数。",
        first_limit_only=False,
        exclude_st=True,
        engine_strategy_id="old_cat_limit2",
        rank_mode=RANK_MODE_STOP_LOSS_LOSS,
        selector="old_cat_limit2",
        lookback_days=OLD_CAT_LIMIT2_LOOKBACK_DAYS,
        min_history_days=OLD_CAT_LIMIT2_FIRST_BOARD_VOLUME_LOOKBACK,
        max_positions_per_day=3,
    ),
    "ultra_short": BacktestProfile(
        id="ultra_short",
        name="超短战法",
        description="同时满足 ZXB1 砖形图共振、长阳放量和 MACD 绿柱后翻红条件；T+1 开盘买入，买入当天不能卖出；收益达到 10% 或持有满 3 个交易日卖出，跌破买入日开盘价止损；忽略 APP 量比阈值。",
        first_limit_only=False,
        exclude_st=True,
        engine_strategy_id="ultra_short",
        selector="ultra_short",
        lookback_days=ULTRA_SHORT_LOOKBACK_DAYS,
        min_history_days=ULTRA_SHORT_MIN_HISTORY_DAYS,
    ),
}

SELECTION_PROFILES: dict[str, SelectionProfile] = {
    "old_cat_buy": SelectionProfile(
        id="old_cat_buy",
        name="老猫买入",
        description="T+1 收盘后回看上一交易日首板早上封板、非 ST、非一字板候选，按 T+1 涨幅筛出待观察标的。",
    ),
    "limit_up_first": SelectionProfile(
        id="limit_up_first",
        name="首板涨停",
        description="选择选股当日涨停的非连板股票，排除一字板和 ST，并标注涨停类型与分时均线止损。",
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
    strategy_id: str = "old_cat_buy",
) -> DailyGroupOut:
    selected_date = resolve_trade_date(conn, trade_date)
    if not selected_date:
        raise ValueError("No daily quotes available.")
    if strategy_id not in SELECTION_PROFILES:
        raise ValueError(f"Unsupported selection strategy: {strategy_id}")

    indicators = list(indicator_ids or DEFAULT_INDICATORS)
    if strategy_id == "old_cat_buy":
        picks = run_old_cat_selection(conn, selected_date, indicators)
    else:
        picks = run_first_limit_selection(conn, selected_date, indicators)
    return DailyGroupOut(
        trade_date=selected_date,
        generated_at=current_timestamp(),
        indicator_ids=indicators,
        main_count=sum(1 for pick in picks if pick.board.value == "main"),
        chinext_count=sum(1 for pick in picks if pick.board.value == "chinext"),
        picks=picks,
    )


def run_old_cat_selection(
    conn: sqlite3.Connection,
    selected_date: str,
    indicators: Sequence[str],
) -> list[StockPickOut]:
    candidate_date = repository.previous_quote_date(conn, selected_date)
    if not candidate_date:
        raise ValueError(f"No previous trading day quotes found before {selected_date}.")
    snapshots = select_limit_up(repository.load_quotes(conn, candidate_date), indicators)
    snapshots = apply_backtest_profile(conn, snapshots, BACKTEST_PROFILES["old_cat"])
    picks = [
        pick
        for pick in (snapshot_to_pick(conn, snapshot, holding_days=3) for snapshot in snapshots)
        if is_old_cat_buy_candidate(pick, selected_date)
    ]
    return rank_daily_picks(picks)


def run_first_limit_selection(
    conn: sqlite3.Connection,
    selected_date: str,
    indicators: Sequence[str],
) -> list[StockPickOut]:
    snapshots = select_limit_up(repository.load_quotes(conn, selected_date), indicators)
    snapshots = apply_backtest_profile(
        conn,
        snapshots,
        BacktestProfile(
            id="limit_up_first",
            name="首板涨停",
            description="当日首板涨停。",
            first_limit_only=True,
            exclude_st=True,
        ),
    )
    return [snapshot_to_pick(conn, snapshot, holding_days=3) for snapshot in snapshots]


def run_saved_backtest(conn: sqlite3.Connection, request: BacktestRequest) -> BacktestResultOut:
    profile = BACKTEST_PROFILES.get(request.strategy_id)
    if profile is None:
        raise ValueError(f"Unsupported backtest strategy: {request.strategy_id}")
    ensure_quotes_for_backtest(conn, request.start_date, request.end_date, profile.lookback_days, profile.min_history_days)
    picks = build_backtest_picks(
        conn,
        request.start_date,
        request.end_date,
        DEFAULT_INDICATORS,
        request.holding_days,
        request.board.value if request.board else None,
        profile,
        request.allow_below_market_ma25,
        backtest_volume_ratio_min(profile, request.volume_ratio_min),
    )
    return run_backtest(
        picks=picks,
        holding_days=request.holding_days,
        take_profit_percent=request.take_profit_percent,
        strategy_id=profile.engine_strategy_id,
        initial_capital=request.initial_capital,
        max_positions_per_day=effective_max_positions_per_day(request.max_positions_per_day, profile),
        rank_mode=profile.rank_mode,
        max_position_allocation_fraction=profile.max_position_allocation_fraction,
    )


def run_backtest_experiment(conn: sqlite3.Connection, request: BacktestRequest) -> BacktestExperimentOut:
    experiment_profile_ids = ("old_cat", "old_cat_selection_aligned")
    experiment_profiles = [BACKTEST_PROFILES[profile_id] for profile_id in experiment_profile_ids]
    max_lookback_days = max((profile.lookback_days for profile in experiment_profiles), default=0)
    max_min_history_days = max((profile.min_history_days for profile in experiment_profiles), default=0)
    ensure_quotes_for_backtest(conn, request.start_date, request.end_date, max_lookback_days, max_min_history_days)
    items: list[BacktestExperimentItemOut] = []
    for profile in experiment_profiles:
        picks = build_backtest_picks(
            conn,
            request.start_date,
            request.end_date,
            DEFAULT_INDICATORS,
            request.holding_days,
            request.board.value if request.board else None,
            profile,
            request.allow_below_market_ma25,
            backtest_volume_ratio_min(profile, request.volume_ratio_min),
        )
        result = run_backtest(
            picks=picks,
            holding_days=request.holding_days,
            take_profit_percent=request.take_profit_percent,
            strategy_id=profile.engine_strategy_id,
            initial_capital=request.initial_capital,
            max_positions_per_day=effective_max_positions_per_day(request.max_positions_per_day, profile),
            rank_mode=profile.rank_mode,
            max_position_allocation_fraction=profile.max_position_allocation_fraction,
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


def effective_max_positions_per_day(requested: int, profile: BacktestProfile) -> int:
    if profile.max_positions_per_day is None:
        return requested
    return min(requested, profile.max_positions_per_day)


def backtest_volume_ratio_min(profile: BacktestProfile, requested: float | None) -> float | None:
    return requested if profile.id == "old_cat" else None


def get_trade_book(conn: sqlite3.Connection) -> TradeBookOut:
    open_positions, history = repository.load_trade_records(conn)
    return TradeBookOut(
        open_positions=open_positions,
        history=history,
        stats=trade_stats(open_positions, history),
    )


def record_buy(conn: sqlite3.Connection, request: TradeBuyRequest) -> TradePositionOut:
    buy_date = request.buy_date or current_date()
    return repository.create_trade_record(conn, request, buy_date)


def record_sell(conn: sqlite3.Connection, trade_id: int, request: TradeSellRequest) -> TradePositionOut:
    sell_date = request.sell_date or current_date()
    return repository.close_trade_record(conn, trade_id, request, sell_date)


def trade_stats(open_positions: Sequence[TradePositionOut], history: Sequence[TradePositionOut]) -> TradeStatsOut:
    total_profit = sum(item.profit_amount or 0.0 for item in history)
    total_trades = len(history)
    win_rate = (
        sum(1 for item in history if (item.profit_amount or 0.0) > 0.0) / total_trades * 100.0
        if total_trades
        else 0.0
    )
    return TradeStatsOut(
        holding_count=len(open_positions),
        total_trades=total_trades,
        win_rate=win_rate,
        total_profit_amount=total_profit,
    )


def sync_tushare_quotes(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    progress: Callable[[str], None] | None = None,
) -> int:
    count = 0
    for trade_date, index, total, quotes in fetch_daily_quote_batches(start_date, end_date, progress=progress):
        if not quotes:
            continue
        count += repository.upsert_daily_quotes(conn, quotes)
        if progress is not None:
            progress(f"wrote daily_quotes {index}/{total} {trade_date} rows={len(quotes)} total={count}")
    if count <= 0:
        raise ValueError(f"No Tushare quotes found from {start_date} to {end_date}.")
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


def resolve_trade_date(conn: sqlite3.Connection, trade_date: str | None) -> str | None:
    if not trade_date:
        return repository.latest_quote_date(conn)
    if repository.count_quotes(conn, trade_date) >= FULL_DAILY_QUOTE_MIN_COUNT:
        return trade_date
    try:
        ensure_quotes_for_date(conn, trade_date)
    except ValueError:
        pass
    if repository.count_quotes(conn, trade_date) >= FULL_DAILY_QUOTE_MIN_COUNT:
        return trade_date
    return repository.latest_quote_date_on_or_before(conn, trade_date)


def ensure_quotes_for_backtest(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
    lookback_days: int = 0,
    min_history_days: int = 0,
) -> None:
    selected_end = end_date or repository.latest_quote_date(conn)
    if not selected_end:
        return
    base_start = start_date or date_days_before(selected_end, DEFAULT_SYNC_DAYS)
    start = date_days_before(base_start, lookback_days) if lookback_days > 0 else base_start
    dates = repository.quote_dates_between(conn, start, selected_end)
    if (
        dates
        and repository.count_quotes(conn, dates[-1]) >= FULL_DAILY_QUOTE_MIN_COUNT
        and (lookback_days <= 0 or len(dates) >= min_history_days)
    ):
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
    volume_ratio_min: float | None = None,
) -> list[StockPickOut]:
    if profile is not None and profile.selector == "ultra_short":
        return build_ultra_short_backtest_picks(
            conn,
            start_date,
            end_date,
            holding_days,
            board,
            profile,
            allow_below_market_ma25,
        )
    if profile is not None and profile.selector == "jia_ban":
        return build_jia_ban_backtest_picks(
            conn,
            start_date,
            end_date,
            holding_days,
            board,
            profile,
            allow_below_market_ma25,
        )
    if profile is not None and profile.selector == "old_cat_limit2":
        return build_old_cat_limit2_backtest_picks(
            conn,
            start_date,
            end_date,
            holding_days,
            board,
            profile,
            allow_below_market_ma25,
        )
    if profile is not None and profile.selector == "old_cat_selection_aligned":
        return build_old_cat_selection_aligned_backtest_picks(
            conn,
            start_date,
            end_date,
            indicator_ids,
            holding_days,
            board,
            profile,
            allow_below_market_ma25,
            volume_ratio_min,
        )

    picks: list[StockPickOut] = []
    for trade_date in repository.quote_dates_between(conn, start_date, end_date):
        if not allow_below_market_ma25 and not market_above_ma25(conn, trade_date):
            continue
        snapshots = select_limit_up(repository.load_quotes(conn, trade_date), indicator_ids, volume_ratio_min)
        if board:
            snapshots = [snapshot for snapshot in snapshots if snapshot.board.value == board]
        if profile is not None:
            snapshots = apply_backtest_profile(conn, snapshots, profile)
        picks.extend(snapshot_to_pick(conn, snapshot, holding_days) for snapshot in snapshots)
    return picks


def build_old_cat_selection_aligned_backtest_picks(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
    indicator_ids: Sequence[str],
    holding_days: int,
    board: str | None,
    profile: BacktestProfile,
    allow_below_market_ma25: bool,
    volume_ratio_min: float | None = None,
) -> list[StockPickOut]:
    picks: list[StockPickOut] = []
    for trade_date in repository.quote_dates_between(conn, start_date, end_date):
        if not allow_below_market_ma25 and not market_above_ma25(conn, trade_date):
            continue
        snapshots = select_limit_up(repository.load_quotes(conn, trade_date), indicator_ids, volume_ratio_min)
        if board:
            snapshots = [snapshot for snapshot in snapshots if snapshot.board.value == board]
        snapshots = apply_backtest_profile(conn, snapshots, profile)
        for snapshot in snapshots:
            pick = snapshot_to_pick(conn, snapshot, holding_days)
            if is_old_cat_selection_aligned_candidate(pick, profile.max_t_plus_one_close_gain_percent):
                picks.append(pick)
    return picks


def build_jia_ban_backtest_picks(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
    holding_days: int,
    board: str | None,
    profile: BacktestProfile,
    allow_below_market_ma25: bool,
) -> list[StockPickOut]:
    selected_end = end_date or repository.latest_quote_date(conn)
    if not selected_end:
        return []
    selected_start = start_date or date_days_before(selected_end, DEFAULT_SYNC_DAYS)
    load_start = date_days_before(selected_start, profile.lookback_days) if profile.lookback_days > 0 else selected_start

    quotes_by_code: dict[str, list[DailyQuoteIn]] = {}
    for quote in repository.load_daily_quotes_between(conn, load_start, selected_end, include_minute_trades=True):
        if board and quote.board.value != board:
            continue
        quotes_by_code.setdefault(quote.code, []).append(quote)

    snapshots: list[PickSnapshot] = []
    for quotes in quotes_by_code.values():
        snapshots.extend(jia_ban_snapshots_for_code(quotes, start_date, end_date, profile))

    if not allow_below_market_ma25:
        snapshots = [snapshot for snapshot in snapshots if market_above_ma25(conn, snapshot.trade_date)]

    snapshots.sort(key=lambda item: (item.trade_date, item.board.value, item.code))
    pick_holding_days = max(holding_days, 1)
    return [snapshot_to_pick(conn, snapshot, pick_holding_days) for snapshot in snapshots]


def jia_ban_snapshots_for_code(
    quotes: Sequence[DailyQuoteIn],
    start_date: str | None,
    end_date: str | None,
    profile: BacktestProfile,
) -> list[PickSnapshot]:
    sorted_quotes = sorted(quotes, key=lambda item: item.trade_date)
    result: list[PickSnapshot] = []
    for index, quote in enumerate(sorted_quotes):
        if not in_date_range(quote.trade_date, start_date, end_date):
            continue
        history = sorted_quotes[max(0, index - JIA_BAN_MIN_HISTORY_DAYS) : index]
        if matches_jia_ban_conditions(quote, history, profile):
            result.append(jia_ban_snapshot(quote, history))
    return result


def matches_jia_ban_conditions(
    quote: DailyQuoteIn,
    history: Sequence[DailyQuoteIn],
    profile: BacktestProfile,
) -> bool:
    if quote.board not in (MarketBoard.main, MarketBoard.chinext):
        return False
    if profile.exclude_st and is_st_stock(quote.name):
        return False
    if len(history) < JIA_BAN_MIN_HISTORY_DAYS:
        return False
    if quote.previous_close <= 0:
        return False

    day_change_percent = (quote.close - quote.previous_close) / quote.previous_close * 100.0
    if day_change_percent < -JIA_BAN_MAX_T_DAY_DROP_PERCENT:
        return False

    top_line = max(item.high for item in history)
    bottom_line = min(item.low for item in history)
    if bottom_line <= 0 or top_line <= bottom_line:
        return False
    if (top_line - bottom_line) / bottom_line > JIA_BAN_MAX_BOX_AMPLITUDE:
        return False

    lower_limit = bottom_line * (1.0 - JIA_BAN_LINE_TOLERANCE)
    if not lower_limit <= quote.close <= bottom_line * (1.0 + JIA_BAN_LINE_TOLERANCE):
        return False

    current_volume = quote_volume(quote)
    history_volumes = [quote_volume(item) for item in history]
    valid_history_volumes = [volume for volume in history_volumes if volume > 0]
    if current_volume <= 0 or not valid_history_volumes:
        return False
    return current_volume <= min(valid_history_volumes)


def jia_ban_snapshot(quote: DailyQuoteIn, history: Sequence[DailyQuoteIn]) -> PickSnapshot:
    bottom_line = min(item.low for item in history)
    top_line = max(item.high for item in history)
    return PickSnapshot(
        trade_date=quote.trade_date,
        code=quote.code,
        name=quote.name,
        board=quote.board,
        concept=quote.concept,
        close=quote.close,
        change_percent=(quote.close - quote.previous_close) / quote.previous_close * 100.0 if quote.previous_close > 0 else 0.0,
        volume_ratio=quote.volume_ratio,
        turnover_rate=quote.turnover_rate,
        total_mv_wan=quote.total_mv_wan,
        sealed_amount_wan=quote.sealed_amount_wan,
        stop_loss_price=bottom_line,
        limit_shape="jia_ban",
        limit_shape_label="夹板战法",
        next_open=quote.next_open,
        future_closes=quote.future_closes,
        target_price=top_line,
    )


def build_old_cat_limit2_backtest_picks(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
    holding_days: int,
    board: str | None,
    profile: BacktestProfile,
    allow_below_market_ma25: bool,
) -> list[StockPickOut]:
    selected_end = end_date or repository.latest_quote_date(conn)
    if not selected_end:
        return []
    selected_start = start_date or date_days_before(selected_end, DEFAULT_SYNC_DAYS)
    load_start = date_days_before(selected_start, profile.lookback_days) if profile.lookback_days > 0 else selected_start

    quotes_by_code: dict[str, list[DailyQuoteIn]] = {}
    for quote in repository.load_daily_quotes_between(conn, load_start, selected_end, include_minute_trades=True):
        if board and quote.board.value != board:
            continue
        quotes_by_code.setdefault(quote.code, []).append(quote)

    snapshots: list[PickSnapshot] = []
    for quotes in quotes_by_code.values():
        snapshots.extend(old_cat_limit2_snapshots_for_code(quotes, start_date, end_date, profile))

    if not allow_below_market_ma25:
        snapshots = [snapshot for snapshot in snapshots if market_above_ma25(conn, snapshot.trade_date)]

    snapshots.sort(key=lambda item: (item.trade_date, item.board.value, item.code))
    pick_holding_days = max(holding_days, 1)
    return [snapshot_to_pick(conn, snapshot, pick_holding_days) for snapshot in snapshots]


def old_cat_limit2_snapshots_for_code(
    quotes: Sequence[DailyQuoteIn],
    start_date: str | None,
    end_date: str | None,
    profile: BacktestProfile,
) -> list[PickSnapshot]:
    sorted_quotes = sorted(quotes, key=lambda item: item.trade_date)
    result: list[PickSnapshot] = []
    start_index = OLD_CAT_LIMIT2_FIRST_BOARD_VOLUME_LOOKBACK + 3
    for second_index in range(start_index, len(sorted_quotes)):
        second_board = sorted_quotes[second_index]
        if not in_date_range(second_board.trade_date, start_date, end_date):
            continue
        first_index = second_index - 3
        first_board = sorted_quotes[first_index]
        pullbacks = sorted_quotes[first_index + 1 : second_index]
        first_history = sorted_quotes[first_index - OLD_CAT_LIMIT2_FIRST_BOARD_VOLUME_LOOKBACK : first_index]
        previous_quote = sorted_quotes[first_index - 1]
        if matches_old_cat_limit2_conditions(first_board, pullbacks, second_board, first_history, previous_quote, profile):
            result.append(old_cat_limit2_snapshot(first_board, second_board))
    return result


def matches_old_cat_limit2_conditions(
    first_board: DailyQuoteIn,
    pullbacks: Sequence[DailyQuoteIn],
    second_board: DailyQuoteIn,
    first_history: Sequence[DailyQuoteIn],
    previous_quote: DailyQuoteIn,
    profile: BacktestProfile,
) -> bool:
    if first_board.board not in (MarketBoard.main, MarketBoard.chinext):
        return False
    if profile.exclude_st and is_st_stock(first_board.name):
        return False
    if len(pullbacks) != 2 or len(first_history) < OLD_CAT_LIMIT2_FIRST_BOARD_VOLUME_LOOKBACK:
        return False
    if old_cat_limit2_is_limit_up(previous_quote):
        return False
    if not old_cat_limit2_is_limit_up(first_board) or not old_cat_limit2_is_limit_up(second_board):
        return False

    first_volume = quote_volume(first_board)
    history_volumes = [quote_volume(item) for item in first_history]
    valid_history_volumes = [volume for volume in history_volumes if volume > 0]
    if first_volume <= 0 or len(valid_history_volumes) < OLD_CAT_LIMIT2_FIRST_BOARD_VOLUME_LOOKBACK:
        return False
    if first_volume < (sum(valid_history_volumes) / len(valid_history_volumes)) * OLD_CAT_LIMIT2_FIRST_BOARD_VOLUME_RATIO:
        return False

    if first_board.open <= 0 or first_board.close <= first_board.open:
        return False

    pullback_volumes = [quote_volume(item) for item in pullbacks]
    if any(volume <= 0 or volume >= first_volume * OLD_CAT_LIMIT2_PULLBACK_VOLUME_RATIO for volume in pullback_volumes):
        return False
    if pullback_volumes[1] >= pullback_volumes[0]:
        return False

    for quote in pullbacks:
        if old_cat_limit2_is_limit_up(quote):
            return False
        if old_cat_limit2_daily_change_percent(quote) < -OLD_CAT_LIMIT2_PULLBACK_MAX_DROP_PERCENT:
            return False
        if quote.low < first_board.open - 0.02 or quote.high > first_board.close + 0.02:
            return False
        if quote.previous_close <= 0:
            return False
        body_percent = abs(quote.close - quote.open) / quote.previous_close * 100.0
        if body_percent > OLD_CAT_LIMIT2_PULLBACK_MAX_BODY_PERCENT:
            return False

    second_volume = quote_volume(second_board)
    return second_volume > pullback_volumes[-1]


def old_cat_limit2_snapshot(first_board: DailyQuoteIn, second_board: DailyQuoteIn) -> PickSnapshot:
    return PickSnapshot(
        trade_date=second_board.trade_date,
        code=second_board.code,
        name=second_board.name,
        board=second_board.board,
        concept=second_board.concept,
        close=second_board.close,
        change_percent=old_cat_limit2_daily_change_percent(second_board),
        volume_ratio=second_board.volume_ratio,
        turnover_rate=second_board.turnover_rate,
        total_mv_wan=second_board.total_mv_wan,
        sealed_amount_wan=second_board.sealed_amount_wan,
        stop_loss_price=first_board.open,
        limit_shape="old_cat_limit2",
        limit_shape_label="老猫涨停2对比",
        next_open=second_board.next_open,
        future_closes=second_board.future_closes,
    )


def old_cat_limit2_is_limit_up(quote: DailyQuoteIn) -> bool:
    if quote.previous_close <= 0:
        return False
    expected = quote.previous_close * (1.0 + quote.board.limit_up_rate)
    return quote.close >= expected - 0.02 and quote.close >= quote.high - 0.02


def old_cat_limit2_daily_change_percent(quote: DailyQuoteIn) -> float:
    if quote.previous_close <= 0:
        return 0.0
    return (quote.close - quote.previous_close) / quote.previous_close * 100.0


def build_ultra_short_backtest_picks(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
    holding_days: int,
    board: str | None,
    profile: BacktestProfile,
    allow_below_market_ma25: bool,
) -> list[StockPickOut]:
    selected_end = end_date or repository.latest_quote_date(conn)
    if not selected_end:
        return []
    selected_start = start_date or date_days_before(selected_end, DEFAULT_SYNC_DAYS)
    load_start = date_days_before(selected_start, profile.lookback_days) if profile.lookback_days > 0 else selected_start

    quotes_by_code: dict[str, list[DailyQuoteIn]] = {}
    for quote in repository.load_daily_quotes_between(conn, load_start, selected_end, include_minute_trades=True):
        if board and quote.board.value != board:
            continue
        quotes_by_code.setdefault(quote.code, []).append(quote)

    snapshots: list[PickSnapshot] = []
    for quotes in quotes_by_code.values():
        snapshots.extend(ultra_short_snapshots_for_code(quotes, start_date, end_date, profile))

    if not allow_below_market_ma25:
        snapshots = [snapshot for snapshot in snapshots if market_above_ma25(conn, snapshot.trade_date)]

    snapshots.sort(key=lambda item: (item.trade_date, item.board.value, item.code))
    return [snapshot_to_pick(conn, snapshot, max(holding_days, 1)) for snapshot in snapshots]


def ultra_short_snapshots_for_code(
    quotes: Sequence[DailyQuoteIn],
    start_date: str | None,
    end_date: str | None,
    profile: BacktestProfile,
) -> list[PickSnapshot]:
    sorted_quotes = sorted(quotes, key=lambda item: item.trade_date)
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[int] = []
    white_lines: list[float | None] = []
    yellow_lines: list[float | None] = []
    bbi_values: list[float | None] = []
    short_values: list[float | None] = []
    long_values: list[float | None] = []
    j_values: list[float | None] = []
    rsi_values: list[float | None] = []
    brick_values: list[float | None] = []
    macd_dif_values: list[float] = []
    macd_dea_values: list[float] = []
    macd_values: list[float] = []
    exists_b_values: list[bool] = []
    cross_close_yellow_values: list[bool] = []

    ema10: float | None = None
    zxdq: float | None = None
    k_value: float | None = None
    d_value: float | None = None
    rsi_gain_sma: float | None = None
    rsi_abs_sma: float | None = None
    var1_sma: float | None = None
    var4_sma: float | None = None
    var5_sma: float | None = None
    macd_fast: float | None = None
    macd_slow: float | None = None
    macd_signal: float | None = None
    result: list[PickSnapshot] = []

    for quote in sorted_quotes:
        opens.append(quote.open)
        highs.append(quote.high)
        lows.append(quote.low)
        closes.append(quote.close)
        volumes.append(quote_volume(quote))

        ema10 = ema(quote.close, ema10, 10)
        zxdq = ema(ema10, zxdq, 10)
        white_lines.append(zxdq)
        yellow_lines.append(ultra_short_yellow_line(closes))
        bbi_values.append(ultra_short_bbi(closes))
        short_values.append(ultra_short_price_line(closes, lows, 3))
        long_values.append(ultra_short_price_line(closes, lows, ULTRA_SHORT_LONG_WINDOW))

        brick, var1_sma, var4_sma, var5_sma = ultra_short_brick_value(
            closes,
            highs,
            lows,
            var1_sma,
            var4_sma,
            var5_sma,
        )
        brick_values.append(brick)

        rsv = kdj_rsv(closes, highs, lows, 9)
        if rsv is not None:
            k_value = tdx_sma(rsv, k_value, 3, 1)
            d_value = tdx_sma(k_value, d_value, 3, 1)
        j_values.append(3.0 * k_value - 2.0 * d_value if k_value is not None and d_value is not None else None)

        macd_fast, macd_slow, macd_signal, macd_dif, macd_value = macd_indicators(
            quote.close,
            macd_fast,
            macd_slow,
            macd_signal,
        )
        macd_dif_values.append(macd_dif)
        macd_dea_values.append(macd_signal)
        macd_values.append(macd_value)

        previous_close = ref_value(closes, 1)
        gain = max(quote.close - previous_close, 0.0) if previous_close is not None else 0.0
        change_abs = abs(quote.close - previous_close) if previous_close is not None else 0.0
        rsi_gain_sma = tdx_sma(gain, rsi_gain_sma, 3, 1)
        rsi_abs_sma = tdx_sma(change_abs, rsi_abs_sma, 3, 1)
        rsi_values.append((rsi_gain_sma / rsi_abs_sma * 100.0) if rsi_abs_sma and rsi_abs_sma > 0 else 0.0)

        previous_yellow = ref_value(yellow_lines, 1)
        current_yellow = last_value(yellow_lines)
        previous_close_for_cross = ref_value(closes, 1)
        cross_close_yellow_values.append(
            current_yellow is not None
            and previous_yellow is not None
            and previous_close_for_cross is not None
            and quote.close > current_yellow
            and previous_close_for_cross <= previous_yellow
        )

        exists_b_values.append(
            ultra_short_exists_b(
                quote,
                opens,
                highs,
                lows,
                closes,
                volumes,
                white_lines,
                yellow_lines,
                bbi_values,
                short_values,
                long_values,
                j_values,
                rsi_values,
                cross_close_yellow_values,
                profile,
            )
        )

        if (
            in_date_range(quote.trade_date, start_date, end_date)
            and len(closes) >= ULTRA_SHORT_MIN_HISTORY_DAYS
            and ultra_short_matches_conditions(
                quote,
                opens,
                highs,
                lows,
                closes,
                volumes,
                white_lines,
                yellow_lines,
                short_values,
                long_values,
                j_values,
                rsi_values,
                brick_values,
                macd_dif_values,
                macd_dea_values,
                macd_values,
                exists_b_values,
                profile,
            )
        ):
            result.append(ultra_short_snapshot(quote))

    return result


def ultra_short_matches_conditions(
    quote: DailyQuoteIn,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[int],
    white_lines: Sequence[float | None],
    yellow_lines: Sequence[float | None],
    short_values: Sequence[float | None],
    long_values: Sequence[float | None],
    j_values: Sequence[float | None],
    rsi_values: Sequence[float | None],
    brick_values: Sequence[float | None],
    macd_dif_values: Sequence[float],
    macd_dea_values: Sequence[float],
    macd_values: Sequence[float],
    exists_b_values: Sequence[bool],
    profile: BacktestProfile,
) -> bool:
    if quote.board not in (MarketBoard.main, MarketBoard.chinext):
        return False
    if profile.exclude_st and is_st_stock(quote.name):
        return False
    return ultra_short_condition1(
        quote,
        opens,
        highs,
        lows,
        closes,
        volumes,
        white_lines,
        yellow_lines,
        short_values,
        long_values,
        j_values,
        rsi_values,
        brick_values,
        exists_b_values,
    ) and ultra_short_condition2(
        quote,
        opens,
        highs,
        closes,
        volumes,
        white_lines,
    ) and is_macd_turning_red(macd_values) and is_macd_underwater(macd_dif_values, macd_dea_values)


def ultra_short_condition1(
    quote: DailyQuoteIn,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[int],
    white_lines: Sequence[float | None],
    yellow_lines: Sequence[float | None],
    short_values: Sequence[float | None],
    long_values: Sequence[float | None],
    j_values: Sequence[float | None],
    rsi_values: Sequence[float | None],
    brick_values: Sequence[float | None],
    exists_b_values: Sequence[bool],
) -> bool:
    white_line = last_value(white_lines)
    yellow_line = last_value(yellow_lines)
    previous_yellow = ref_value(yellow_lines, 1)
    previous_close = ref_value(closes, 1)
    if white_line is None or yellow_line is None or previous_yellow is None or previous_close is None:
        return False

    yellow_column, x_momentum = ultra_short_momentum(opens, highs, closes, volumes, j_values, rsi_values)
    brick = last_value(brick_values)
    previous_brick = ref_value(brick_values, 1)
    length = (brick - previous_brick) if brick is not None and previous_brick is not None else 0.0
    strong_red = ultra_short_strong_red(brick_values)

    trend_condition = (
        white_line >= yellow_line * 0.995
        and yellow_line >= previous_yellow * 0.997
        and quote.close >= yellow_line * 0.997
    )

    upper_shadow_base = quote.high - min(quote.low, previous_close)
    upper_shadow_condition = (
        (quote.close >= quote.open or quote.close > previous_close)
        and upper_shadow_base > 0
        and (1.0 - (quote.high - quote.close) / upper_shadow_base) > 0.618
    )
    turnover_condition = quote.turnover_rate >= ULTRA_SHORT_TURNOVER_MIN
    previous_long = ref_value(long_values, 1)
    previous_short = ref_value(short_values, 1)
    current_long = last_value(long_values)
    current_short = last_value(short_values)

    resonance1 = (
        strong_red
        and (yellow_column >= 7.5 or x_momentum >= 7.5)
        and (
            exists_last(exists_b_values, 2)
            or (
                previous_long is not None
                and previous_short is not None
                and previous_long > 85.0
                and previous_short < 30.0
            )
        )
    )
    resonance2 = (
        strong_red
        and (yellow_column >= 10.0 or x_momentum >= 10.0)
        and (
            (
                count_last_predicate(
                    [long_short_spread(long_values, short_values, index) for index in range(len(long_values))],
                    4,
                    lambda value: value is not None and value > 60.0,
                )
                > 0
                and current_long is not None
                and current_short is not None
                and current_long > 98.0
                and current_short > 98.0
            )
            or (yellow_column > 20.0 and quote.close > white_line)
            or yellow_column > 30.0
            or (yellow_column + length) > 50.0
            or x_momentum > 40.0
        )
    )
    return (resonance1 or resonance2) and upper_shadow_condition and trend_condition and turnover_condition


def ultra_short_condition2(
    quote: DailyQuoteIn,
    opens: Sequence[float],
    highs: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[int],
    white_lines: Sequence[float | None],
) -> bool:
    previous_close = ref_value(closes, 1)
    if previous_close is None or previous_close <= 0:
        return False
    average_volume = simple_ma_at(volumes, 20)
    zxdq = last_value(white_lines)
    if average_volume is None or zxdq is None:
        return False
    wick_base = max(quote.open, quote.close)
    wick = (quote.high - wick_base) / wick_base if wick_base > 0 else 1.0
    return (
        quote.close >= quote.open
        and (quote.close / previous_close - 1.0) * 100.0 > 4.0
        and wick < 0.03
        and volumes[-1] > 1.5 * average_volume
        and quote.close < zxdq * 1.15
    )


def ultra_short_exists_b(
    quote: DailyQuoteIn,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[int],
    white_lines: Sequence[float | None],
    yellow_lines: Sequence[float | None],
    bbi_values: Sequence[float | None],
    short_values: Sequence[float | None],
    long_values: Sequence[float | None],
    j_values: Sequence[float | None],
    rsi_values: Sequence[float | None],
    cross_close_yellow_values: Sequence[bool],
    profile: BacktestProfile,
) -> bool:
    if quote.board not in (MarketBoard.main, MarketBoard.chinext):
        return False
    if profile.exclude_st and is_st_stock(quote.name):
        return False

    white_line = last_value(white_lines)
    yellow_line = last_value(yellow_lines)
    bbi = last_value(bbi_values)
    j_value = last_value(j_values)
    rsi = last_value(rsi_values)
    previous_close = ref_value(closes, 1)
    previous_yellow = ref_value(yellow_lines, 1)
    if (
        white_line is None
        or yellow_line is None
        or bbi is None
        or j_value is None
        or rsi is None
        or previous_close is None
        or previous_close <= 0
        or previous_yellow is None
    ):
        return False

    amplitude_range, relax_factor = ultra_short_amplitude_settings(quote.code, closes)
    daily_amplitude = (quote.high - quote.low) / quote.low * 100.0 if quote.low > 0 else 0.0
    daily_change = abs(quote.close - previous_close) / previous_close * 100.0 * relax_factor
    up_doji = quote.close > previous_close and (abs(quote.close - quote.open) / quote.open * 100.0 * relax_factor) < 1.8

    current_short = last_value(short_values)
    current_long = last_value(long_values)
    if current_short is None or current_long is None:
        return False
    single_needle_flags = [
        (short is not None and long is not None and ((short <= 20.0 and long >= 75.0) or (long - short) >= 70.0))
        for short, long in zip(short_values, long_values)
    ]
    treasure_basin = (
        count_last_predicate(long_values, 8, lambda value: value is not None and value >= 75.0) >= 6
        and count_last_predicate(short_values, 7, lambda value: value is not None and value <= 70.0) >= 4
        and count_last_predicate(short_values, 8, lambda value: value is not None and value <= 50.0) >= 1
    )
    double_halberd = (
        every_last_predicate(long_values, 8, lambda value: value is not None and value >= 75.0)
        and count_last_predicate(short_values, 6, lambda value: value is not None and value <= 50.0) >= 2
        and count_last_predicate(short_values, 7, lambda value: value is not None and value <= 20.0) >= 1
    )
    red_fat_green_thin = (
        count_last_indexed(len(closes), 15, lambda index: closes[index] >= opens[index]) > 7
        or count_last_indexed(len(closes), 11, lambda index: index > 0 and closes[index] > closes[index - 1]) > 5
    )

    vday = hhvbars(volumes, 40)
    volume_day_close = ref_value(closes, vday)
    volume_day_previous_close = ref_value(closes, vday + 1)
    volume_day_open = ref_value(opens, vday)
    not_big_green_bar = True
    if volume_day_close is not None and volume_day_previous_close is not None and volume_day_open is not None:
        not_big_green_bar = volume_day_close >= volume_day_previous_close or volume_day_close >= volume_day_open
    big_green_bar = not not_big_green_bar
    big_green_bar_far = vday >= 15 and big_green_bar
    not_big_green_or_far = not_big_green_bar or big_green_bar_far

    shrink = volume_lt_hhv_ratio(volumes, 20, 0.416) or volume_lt_hhv_ratio(volumes, 50, 1.0 / 3.0)
    pullback_shrink = volume_lt_hhv_ratio(volumes, 20, 0.45) or volume_lt_hhv_ratio(volumes, 50, 1.0 / 3.0)
    moderate_shrink = volume_lt_hhv_ratio(volumes, 20, 0.618) or volume_lt_hhv_ratio(volumes, 50, 1.0 / 3.0)
    super_shrink = volume_lt_hhv_ratio(volumes, 30, 0.25) or volume_lt_hhv_ratio(volumes, 50, 1.0 / 6.0)

    recent_amplitude = percent_range(highs, lows, 20)
    recent_alt_amplitude = percent_mixed_range(highs, lows, 12, 14)
    recent_anomaly = recent_amplitude >= 15.0 or recent_alt_amplitude >= 11.0
    far_amplitude = percent_range(highs, lows, 50)
    far_anomaly = far_amplitude >= 30.0
    super_anomaly = recent_amplitude >= 60.0
    wash_anomaly = count_last_predicate(single_needle_flags, 10, bool) >= 2 or treasure_basin or double_halberd

    uptrend = white_line >= yellow_line * 0.999 and (
        quote.close >= yellow_line or (quote.close > yellow_line * 0.975 and quote.close > quote.open)
    )
    strong_trend = (
        every_ge_ref(yellow_lines, 13, 0.999)
        and ref_value(white_lines, 1) is not None
        and white_line >= (ref_value(white_lines, 1) or 0.0)
        and every_pair_last(white_lines, yellow_lines, 20, lambda white, yellow: white > yellow)
        and every_ge_ref(white_lines, 11, 1.0)
        and red_fat_green_thin
    )
    super_bull = (
        (every_ge_ref(bbi_values, 20, 0.999) or count_ge_ref(bbi_values, 25, 1.0) >= 23)
        and (recent_amplitude >= 30.0 or far_amplitude > 80.0)
        and barslast(cross_close_yellow_values) > 12
    )

    distance_white = abs(quote.close - white_line) / quote.close * 100.0 if quote.close > 0 else 100.0
    low_distance_white = abs(quote.low - white_line) / white_line * 100.0 if white_line > 0 else 100.0
    distance_bbi = abs(quote.close - bbi) / quote.close * 100.0 if quote.close > 0 else 100.0
    low_distance_bbi = abs(quote.low - bbi) / bbi * 100.0 if bbi > 0 else 100.0
    pullback_white = (
        (quote.close >= white_line and distance_white <= 2.0)
        or (quote.close < white_line and distance_white < 0.8)
        or (
            quote.close >= bbi
            and distance_bbi < 2.5
            and low_distance_bbi < 1.0
            and distance_white <= 3.0
            and daily_change < 1.0
            and quote.close > previous_close
        )
    )
    white_support = quote.close >= white_line and distance_white < 1.5
    strong_pullback_not_break = (
        (low_distance_white < 1.0 or low_distance_bbi < 0.5)
        and quote.close > white_line
        and distance_white <= 3.5
    )

    distance_yellow = abs(quote.close - yellow_line) / yellow_line * 100.0 if yellow_line > 0 else 100.0
    pullback_yellow = (
        quote.close >= yellow_line and (distance_yellow <= 1.5 or (distance_yellow <= 2.0 and daily_change < 1.0))
    ) or (quote.close < yellow_line and distance_yellow <= 0.8)

    rsi_j_values = [sum_pair(rsi_item, j_item) for rsi_item, j_item in zip(rsi_values, j_values)]
    previous_rsi = ref_value(rsi_values, 1)
    previous_j = ref_value(j_values, 1)
    rsi_j = rsi + j_value

    oversold_shrink_turn_b = (
        uptrend
        and previous_rsi is not None
        and previous_j is not None
        and (rsi - 15.0) >= previous_rsi
        and (previous_rsi < 20.0 or previous_j < 14.0)
        and daily_amplitude < (amplitude_range + 0.5)
        and (daily_change < 2.3 or (up_doji and daily_change < 4.0))
        and not_big_green_or_far
        and (recent_anomaly or far_anomaly or wash_anomaly)
        and quote.close >= yellow_line
    )
    oversold_shrink_b = (
        uptrend
        and (j_value < 14.0 or rsi < 23.0)
        and (rsi_j < 55.0 or is_last_llv(j_values, 20))
        and daily_amplitude < amplitude_range
        and (daily_change < 2.5 or up_doji)
        and not_big_green_or_far
        and (shrink or (moderate_shrink and daily_change < 1.0))
        and (recent_anomaly or far_anomaly or wash_anomaly)
    )
    original_shrink_signal = (
        white_line > yellow_line
        and quote.close >= yellow_line * 0.99
        and yellow_line >= previous_yellow
        and (j_value < 13.0 or rsi < 21.0)
        and min_last(rsi_j_values, 15) is not None
        and rsi_j < (min_last(rsi_j_values, 15) or 0.0) * 1.5
        and moderate_shrink
        and not_big_green_or_far
        and (
            abs(quote.close - quote.open) * 100.0 / quote.open < 1.5
            or (
                super_shrink
                or (moderate_shrink and volumes[-1] < (min_last(volumes, 20) or 0.0) * 1.1 and is_last_llv(j_values, 20))
            )
            or (moderate_shrink and (distance_white < 1.8 or distance_bbi < 1.5 or distance_yellow < 2.8))
        )
        and (recent_anomaly or far_anomaly or wash_anomaly)
    )
    oversold_super_shrink_b = (
        uptrend
        and (j_value < 14.0 or rsi < 23.0)
        and rsi_j < 60.0
        and far_amplitude >= 45.0
        and (
            daily_amplitude < amplitude_range
            or (super_anomaly and daily_amplitude < amplitude_range + 3.2 and quote.close > quote.open and quote.close > white_line)
        )
        and ((quote.close < quote.open and volumes[-1] < (ref_value(volumes, 1) or 0) and quote.close >= yellow_line) or quote.close >= quote.open)
        and (daily_change < 2.0 or up_doji)
        and not_big_green_or_far
        and super_shrink
        and (recent_anomaly or far_anomaly or wash_anomaly)
    )
    pullback_white_b = (
        strong_trend
        and (j_value < 30.0 or rsi < 40.0 or wash_anomaly)
        and rsi_j < 70.0
        and (daily_amplitude < amplitude_range + 0.5 or distance_white < 1.0 or distance_bbi < 1.0)
        and pullback_white
        and (daily_change < 2.0 or (daily_change < 5.0 and white_support))
        and not_big_green_or_far
        and pullback_shrink
        and (recent_anomaly or far_anomaly or wash_anomaly)
        and quote.low <= previous_close
    )
    pullback_super_b = (
        super_bull
        and (j_value < 35.0 or rsi < 45.0 or wash_anomaly)
        and rsi_j < 80.0
        and is_last_llv(rsi_j_values, 25)
        and daily_amplitude < amplitude_range + 1.0
        and (daily_change < 2.5 or distance_white < 2.0)
        and strong_pullback_not_break
        and not_big_green_or_far
        and (recent_anomaly or far_anomaly or wash_anomaly)
        and moderate_shrink
    )
    pullback_yellow_b = (
        white_line >= yellow_line
        and quote.close >= yellow_line * 0.975
        and (j_value < 13.0 or rsi < 18.0)
        and pullback_yellow
        and not_big_green_or_far
        and (shrink or (moderate_shrink and (is_last_llv(j_values, 20) or is_last_llv(rsi_values, 14))))
        and yellow_line >= previous_yellow * 0.997
        and simple_ma_at(closes, 60) is not None
        and simple_ma_at(closes[:-1], 60) is not None
        and (simple_ma_at(closes, 60) or 0.0) >= (simple_ma_at(closes[:-1], 60) or 0.0)
        and recent_amplitude >= 11.9
        and far_amplitude >= 19.5
    )

    return (
        oversold_shrink_turn_b
        or oversold_shrink_b
        or original_shrink_signal
        or oversold_super_shrink_b
        or pullback_white_b
        or pullback_super_b
        or pullback_yellow_b
    )


def ultra_short_snapshot(quote: DailyQuoteIn) -> PickSnapshot:
    return PickSnapshot(
        trade_date=quote.trade_date,
        code=quote.code,
        name=quote.name,
        board=quote.board,
        concept=quote.concept,
        close=quote.close,
        change_percent=(quote.close - quote.previous_close) / quote.previous_close * 100.0 if quote.previous_close > 0 else 0.0,
        volume_ratio=quote.volume_ratio,
        turnover_rate=quote.turnover_rate,
        total_mv_wan=quote.total_mv_wan,
        sealed_amount_wan=quote.sealed_amount_wan,
        stop_loss_price=quote.close,
        limit_shape="ultra_short",
        limit_shape_label="超短战法",
        next_open=quote.next_open,
        future_closes=quote.future_closes,
    )


def ultra_short_yellow_line(closes: Sequence[float]) -> float | None:
    if len(closes) < max(ULTRA_SHORT_YELLOW_WINDOWS):
        return None
    return sum(simple_ma(closes, window) for window in ULTRA_SHORT_YELLOW_WINDOWS) / len(ULTRA_SHORT_YELLOW_WINDOWS)


def ultra_short_bbi(closes: Sequence[float]) -> float | None:
    windows = (3, 6, 12, 24)
    if len(closes) < max(windows):
        return None
    return sum(simple_ma(closes, window) for window in windows) / len(windows)


def ultra_short_price_line(closes: Sequence[float], lows: Sequence[float], window: int) -> float | None:
    highest_close = max_last(closes, window)
    lowest_low = min_last(lows, window)
    if highest_close is None or lowest_low is None:
        return None
    spread = highest_close - lowest_low
    if spread == 0:
        return 50.0
    return (closes[-1] - lowest_low) / spread * 100.0


def ultra_short_brick_value(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    var1_sma: float | None,
    var4_sma: float | None,
    var5_sma: float | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    highest_high = max_last(highs, 4)
    lowest_low = min_last(lows, 4)
    if highest_high is None or lowest_low is None:
        return None, var1_sma, var4_sma, var5_sma
    spread = highest_high - lowest_low
    if spread == 0:
        var1a = -40.0
        var3a = 50.0
    else:
        var1a = (highest_high - closes[-1]) / spread * 100.0 - 90.0
        var3a = (closes[-1] - lowest_low) / spread * 100.0
    var1_sma = tdx_sma(var1a, var1_sma, 4, 1)
    var4_sma = tdx_sma(var3a, var4_sma, 6, 1)
    var5_sma = tdx_sma(var4_sma, var5_sma, 6, 1)
    var6a = (var5_sma + 100.0) - (var1_sma + 100.0)
    return (var6a - 4.0 if var6a > 4.0 else 0.0), var1_sma, var4_sma, var5_sma


def ultra_short_momentum(
    opens: Sequence[float],
    highs: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[int],
    j_values: Sequence[float | None],
    rsi_values: Sequence[float | None],
) -> tuple[float, float]:
    current_j = last_value(j_values)
    previous_j = ref_value(j_values, 1)
    two_back_j = ref_value(j_values, 2)
    current_rsi = last_value(rsi_values)
    previous_rsi = ref_value(rsi_values, 1)
    two_back_rsi = ref_value(rsi_values, 2)
    previous_close = ref_value(closes, 1)
    previous_volume = ref_value(volumes, 1)
    if (
        current_j is None
        or previous_j is None
        or two_back_j is None
        or current_rsi is None
        or previous_rsi is None
        or two_back_rsi is None
        or previous_close is None
        or previous_volume is None
        or previous_volume <= 0
    ):
        return 0.0, 0.0

    n1 = current_j - previous_j
    n2 = current_rsi - previous_rsi
    previous_n1 = previous_j - two_back_j
    previous_n2 = previous_rsi - two_back_rsi
    volume_ratio = volumes[-1] / previous_volume
    volume_coeff = (1.0 - 5.0 * (previous_volume - volumes[-1]) / previous_volume) * 0.8 if volumes[-1] < previous_volume * 0.99 else 1.0
    multiple_volume_coeff = 1.4 if volume_ratio >= 4.0 else 0.1 * volume_ratio + 1.0
    multiple_volume_bonus = (
        multiple_volume_coeff
        if closes[-1] > opens[-1] and closes[-1] > previous_close and volumes[-1] > previous_volume * 1.8
        else 1.0
    )

    shadow_coeff = 1.0
    shadow_base = highs[-1] - min(opens[-1], previous_close)
    if closes[-1] > previous_close and closes[-1] > opens[-1] and shadow_base > 0:
        shadow_coeff = (0.75 - (highs[-1] - closes[-1]) / shadow_base) * 1.3

    yellow_column = (n1 + n2) / 2.0 * shadow_coeff * multiple_volume_bonus
    x_momentum = 0.0
    if closes[-1] > opens[-1] and closes[-1] > previous_close and (n1 + n2) > (previous_n1 + previous_n2):
        x_momentum = (
            ((n1 + n2) - (previous_n1 + previous_n2))
            / 2.0
            * shadow_coeff
            * volume_coeff
            * multiple_volume_bonus
        )
    return yellow_column, x_momentum


def ultra_short_strong_red(brick_values: Sequence[float | None]) -> bool:
    brick = last_value(brick_values)
    previous_brick = ref_value(brick_values, 1)
    two_back_brick = ref_value(brick_values, 2)
    if brick is None or previous_brick is None or two_back_brick is None:
        return False
    today_red = brick > previous_brick
    yesterday_green = previous_brick <= two_back_brick
    red_length = brick - previous_brick if today_red else 0.0
    yesterday_green_length = two_back_brick - previous_brick if yesterday_green else 0.0
    ratio = red_length / yesterday_green_length if yesterday_green_length > 0 else 0.0
    return today_red and yesterday_green and ratio > 0.666


def ultra_short_amplitude_settings(code: str, closes: Sequence[float]) -> tuple[float, float]:
    relaxed_code = code.startswith(("68", "30", "4", "8", "9"))
    recent_limit_move = any(
        closes[index - 1] > 0 and closes[index] / closes[index - 1] > 1.15
        for index in range(max(1, len(closes) - 199), len(closes))
    )
    return (8.0, 0.9) if relaxed_code or recent_limit_move else (5.0, 1.0)


def percent_range(highs: Sequence[float], lows: Sequence[float], window: int) -> float:
    highest = max_last(highs, window)
    lowest = min_last(lows, window)
    if highest is None or lowest is None or lowest <= 0:
        return 0.0
    return (highest - lowest) / lowest * 100.0


def percent_mixed_range(highs: Sequence[float], lows: Sequence[float], high_window: int, low_window: int) -> float:
    highest = max_last(highs, high_window)
    lowest = min_last(lows, low_window)
    if highest is None or lowest is None or lowest <= 0:
        return 0.0
    return (highest - lowest) / lowest * 100.0


def volume_lt_hhv_ratio(volumes: Sequence[int], window: int, ratio: float) -> bool:
    highest = max_last(volumes, window)
    return highest is not None and volumes[-1] < highest * ratio


def long_short_spread(
    long_values: Sequence[float | None],
    short_values: Sequence[float | None],
    index: int,
) -> float | None:
    long_value = long_values[index]
    short_value = short_values[index]
    return long_value - short_value if long_value is not None and short_value is not None else None


def sum_pair(first: float | None, second: float | None) -> float | None:
    return first + second if first is not None and second is not None else None


def last_value(values: Sequence[float | int | bool | None]) -> Any:
    return values[-1] if values else None


def ref_value(values: Sequence[float | int | bool | None], offset: int) -> Any:
    if offset < 0 or len(values) <= offset:
        return None
    return values[-1 - offset]


def max_last(values: Sequence[float | int | None], window: int) -> float | int | None:
    valid = [value for value in values[-window:] if value is not None]
    return max(valid) if valid else None


def min_last(values: Sequence[float | int | None], window: int) -> float | int | None:
    valid = [value for value in values[-window:] if value is not None]
    return min(valid) if valid else None


def simple_ma_at(values: Sequence[float | int], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def hhvbars(values: Sequence[int], window: int) -> int:
    recent = list(values[-window:])
    if not recent:
        return 0
    highest = max(recent)
    for offset, value in enumerate(reversed(recent)):
        if value == highest:
            return offset
    return 0


def count_last_predicate(values: Sequence, window: int, predicate) -> int:
    return sum(1 for value in values[-window:] if predicate(value))


def every_last_predicate(values: Sequence, window: int, predicate) -> bool:
    return len(values) >= window and all(predicate(value) for value in values[-window:])


def count_last_indexed(length: int, window: int, predicate) -> int:
    start = max(0, length - window)
    return sum(1 for index in range(start, length) if predicate(index))


def exists_last(values: Sequence[bool], window: int) -> bool:
    return any(values[-window:])


def every_ge_ref(values: Sequence[float | None], window: int, multiplier: float) -> bool:
    if len(values) <= window:
        return False
    for offset in range(window):
        current = ref_value(values, offset)
        previous = ref_value(values, offset + 1)
        if current is None or previous is None or current < previous * multiplier:
            return False
    return True


def count_ge_ref(values: Sequence[float | None], window: int, multiplier: float) -> int:
    if len(values) <= 1:
        return 0
    count = 0
    for offset in range(min(window, len(values) - 1)):
        current = ref_value(values, offset)
        previous = ref_value(values, offset + 1)
        if current is not None and previous is not None and current >= previous * multiplier:
            count += 1
    return count


def every_pair_last(first_values: Sequence[float | None], second_values: Sequence[float | None], window: int, predicate) -> bool:
    if len(first_values) < window or len(second_values) < window:
        return False
    for first, second in zip(first_values[-window:], second_values[-window:]):
        if first is None or second is None or not predicate(first, second):
            return False
    return True


def barslast(values: Sequence[bool]) -> int:
    for offset, value in enumerate(reversed(values)):
        if value:
            return offset
    return 1_000_000


def is_last_llv(values: Sequence[float | None], window: int) -> bool:
    current = last_value(values)
    lowest = min_last(values, window)
    return current is not None and lowest is not None and current <= lowest + 1e-9


def kdj_rsv(closes: Sequence[float], highs: Sequence[float], lows: Sequence[float], n: int) -> float | None:
    if len(closes) < n:
        return None
    highest = max(highs[-n:])
    lowest = min(lows[-n:])
    rng = highest - lowest
    if rng == 0:
        return 50.0
    return (closes[-1] - lowest) / rng * 100.0


def simple_ma(values: Sequence[float], window: int) -> float:
    return sum(values[-window:]) / window


def ema(value: float, previous: float | None, period: int) -> float:
    if previous is None:
        return value
    alpha = 2.0 / (period + 1.0)
    return value * alpha + previous * (1.0 - alpha)


def tdx_sma(value: float, previous: float | None, period: int, weight: int) -> float:
    if previous is None:
        return value
    return (weight * value + (period - weight) * previous) / period


def macd_histogram(
    close: float,
    fast_ema: float | None,
    slow_ema: float | None,
    signal_ema: float | None,
) -> tuple[float, float, float, float]:
    fast, slow, signal, _dif, histogram = macd_indicators(close, fast_ema, slow_ema, signal_ema)
    return fast, slow, signal, histogram


def macd_indicators(
    close: float,
    fast_ema: float | None,
    slow_ema: float | None,
    signal_ema: float | None,
) -> tuple[float, float, float, float, float]:
    fast = ema(close, fast_ema, 12)
    slow = ema(close, slow_ema, 26)
    dif = fast - slow
    signal = ema(dif, signal_ema, 9)
    return fast, slow, signal, dif, (dif - signal) * 2.0


def is_macd_turning_red(macd_values: Sequence[float]) -> bool:
    if len(macd_values) < 2:
        return False
    return macd_values[-1] > 0.0 and macd_values[-2] < 0.0


def is_macd_underwater(macd_dif_values: Sequence[float], macd_dea_values: Sequence[float]) -> bool:
    if not macd_dif_values or not macd_dea_values:
        return False
    return macd_dif_values[-1] < 0.0 and macd_dea_values[-1] < 0.0


def quote_volume(quote: DailyQuoteIn) -> int:
    return sum(max(0, trade.volume) for trade in quote.minute_trades)


def in_date_range(trade_date: str, start_date: str | None, end_date: str | None) -> bool:
    return (start_date is None or trade_date >= start_date) and (end_date is None or trade_date <= end_date)


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
    if profile.min_total_mv_wan is not None:
        filtered = [snapshot for snapshot in filtered if snapshot.total_mv_wan >= profile.min_total_mv_wan]
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


def is_old_cat_buy_candidate(pick: StockPickOut, decision_date: str) -> bool:
    if len(pick.future_dates) < 1 or len(pick.future_closes) < 1:
        return False
    if pick.future_dates[0] != decision_date:
        return False
    decision_close = pick.future_closes[0]
    return decision_close > 0 and decision_close <= pick.close * 1.05


def is_old_cat_selection_aligned_candidate(pick: StockPickOut, max_gain_percent: float = 5.0) -> bool:
    if len(pick.future_closes) < 1:
        return False
    decision_close = pick.future_closes[0]
    return decision_close > 0 and decision_close <= pick.close * (1.0 + max_gain_percent / 100.0)


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
        total_mv_wan=snapshot.total_mv_wan,
        sealed_amount_wan=snapshot.sealed_amount_wan,
        stop_loss_price=snapshot.stop_loss_price,
        target_price=snapshot.target_price,
        limit_shape=snapshot.limit_shape,
        limit_shape_label=snapshot.limit_shape_label,
        latest_trade_date=latest["trade_date"] if latest else None,
        latest_close=latest["close"] if latest else None,
        next_open=next_open,
        future_closes=[bar["close"] for bar in future_bars],
        future_highs=[bar["high"] for bar in future_bars],
        future_lows=[bar["low"] for bar in future_bars],
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


def current_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")
