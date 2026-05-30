from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

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
from .tushare_provider import TushareError, fetch_daily_quotes_range, fetch_market_index_quotes_range


DEFAULT_INDICATORS = ["volume", "seal", "close"]
FULL_DAILY_QUOTE_MIN_COUNT = 1000
DEFAULT_SYNC_DAYS = 92
B1_MIN_TOTAL_MV_WAN = 500000.0
B1_MIN_HISTORY_DAYS = 114
B1_LOOKBACK_DAYS = 180
B1_J_THRESHOLD = 13.0
B1_LINE_PROXIMITY_MAX = 0.035
B1_VOLUME_PREVIOUS_RATIO_MAX = 0.85
B1_VOLUME_AVG_RATIO_MAX = 0.75
B1_N_SHAPE_LOOKBACK_DAYS = 60
JIA_BAN_LOOKBACK_DAYS = 120
JIA_BAN_MIN_HISTORY_DAYS = 60
JIA_BAN_LINE_TOLERANCE = 0.02
JIA_BAN_MAX_T_DAY_DROP_PERCENT = 7.0


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
        description="三个月箱体内有顶有底，允许 2% 突破；T 日收盘接近底部线且跌幅不超过 7%，T+1 开盘买入；跌破底部线止损，止盈率和持有天数按回测参数执行。",
        first_limit_only=False,
        exclude_st=True,
        engine_strategy_id="jia_ban",
        rank_mode=RANK_MODE_STOP_LOSS_LOSS,
        selector="jia_ban",
        lookback_days=JIA_BAN_LOOKBACK_DAYS,
        min_history_days=JIA_BAN_MIN_HISTORY_DAYS,
        max_positions_per_day=3,
    ),
    "b1": BacktestProfile(
        id="b1",
        name="B1 战法",
        description="B1 选股：J<13，收盘价贴近知行短期线或多空线，当天相对前几日明显缩量，且日线呈 N 型上涨结构；排除 ST 和市值小于 50 亿标的；买卖规则沿用老猫战法，并按趋势线止损率排序。",
        first_limit_only=False,
        exclude_st=True,
        min_total_mv_wan=B1_MIN_TOTAL_MV_WAN,
        rank_mode=RANK_MODE_STOP_LOSS_LOSS,
        selector="b1",
        lookback_days=B1_LOOKBACK_DAYS,
        min_history_days=B1_MIN_HISTORY_DAYS,
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
    excluded_profile_ids = {"b1", "old_cat_timely_stop_loss"}
    experiment_profiles = [profile for profile in BACKTEST_PROFILES.values() if profile.id not in excluded_profile_ids]
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
) -> list[StockPickOut]:
    if profile is not None and profile.selector == "b1":
        return build_b1_backtest_picks(conn, start_date, end_date, holding_days, board, profile)
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
        )

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


def build_old_cat_selection_aligned_backtest_picks(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
    indicator_ids: Sequence[str],
    holding_days: int,
    board: str | None,
    profile: BacktestProfile,
    allow_below_market_ma25: bool,
) -> list[StockPickOut]:
    picks: list[StockPickOut] = []
    for trade_date in repository.quote_dates_between(conn, start_date, end_date):
        if not allow_below_market_ma25 and not market_above_ma25(conn, trade_date):
            continue
        snapshots = select_limit_up(repository.load_quotes(conn, trade_date), indicator_ids)
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
    quotes_by_code: dict[str, list[DailyQuoteIn]] = {}
    for trade_date in repository.quote_dates_on_or_before(conn, end_date):
        for quote in repository.load_quotes(conn, trade_date):
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

    lower_limit = bottom_line * (1.0 - JIA_BAN_LINE_TOLERANCE)
    upper_limit = top_line * (1.0 + JIA_BAN_LINE_TOLERANCE)
    if any(item.low < lower_limit or item.high > upper_limit for item in history):
        return False

    bottom_touches = sum(1 for item in history if item.low <= bottom_line * (1.0 + JIA_BAN_LINE_TOLERANCE))
    top_touches = sum(1 for item in history if item.high >= top_line * (1.0 - JIA_BAN_LINE_TOLERANCE))
    if bottom_touches < 2 or top_touches < 2:
        return False

    return lower_limit <= quote.close <= bottom_line * (1.0 + JIA_BAN_LINE_TOLERANCE)


def jia_ban_snapshot(quote: DailyQuoteIn, history: Sequence[DailyQuoteIn]) -> PickSnapshot:
    bottom_line = min(item.low for item in history)
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
    )


def build_b1_backtest_picks(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
    holding_days: int,
    board: str | None,
    profile: BacktestProfile,
) -> list[StockPickOut]:
    quotes_by_code: dict[str, list[DailyQuoteIn]] = {}
    for trade_date in repository.quote_dates_on_or_before(conn, end_date):
        for quote in repository.load_quotes(conn, trade_date):
            if board and quote.board.value != board:
                continue
            quotes_by_code.setdefault(quote.code, []).append(quote)

    snapshots: list[PickSnapshot] = []
    for quotes in quotes_by_code.values():
        snapshots.extend(b1_snapshots_for_code(quotes, start_date, end_date, profile))

    snapshots.sort(key=lambda item: (item.trade_date, item.board.value, item.code))
    return [snapshot_to_pick(conn, snapshot, holding_days) for snapshot in snapshots]


def b1_snapshots_for_code(
    quotes: Sequence[DailyQuoteIn],
    start_date: str | None,
    end_date: str | None,
    profile: BacktestProfile,
) -> list[PickSnapshot]:
    sorted_quotes = sorted(quotes, key=lambda item: item.trade_date)
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    volumes: list[int] = []
    ema10: float | None = None
    zxdq: float | None = None
    k_value: float | None = None
    d_value: float | None = None
    result: list[PickSnapshot] = []

    for quote in sorted_quotes:
        closes.append(quote.close)
        highs.append(quote.high)
        lows.append(quote.low)

        ema10 = ema(quote.close, ema10, 10)
        zxdq = ema(ema10, zxdq, 10)

        rsv = b1_rsv(closes, highs, lows, 9)
        if rsv is not None:
            k_value = tdx_sma(rsv, k_value, 3, 1)
            d_value = tdx_sma(k_value, d_value, 3, 1)

        current_volume = quote_volume(quote)
        recent_volumes = volumes[-5:]
        if (
            in_date_range(quote.trade_date, start_date, end_date)
            and len(closes) >= B1_MIN_HISTORY_DAYS
            and k_value is not None
            and d_value is not None
            and zxdq is not None
            and matches_b1_conditions(quote, closes, zxdq, k_value, d_value, recent_volumes, current_volume, profile)
        ):
            zxdkx = b1_zxdkx(closes)
            if zxdkx is not None:
                result.append(b1_snapshot(quote, zxdq, zxdkx))

        volumes.append(current_volume)

    return result


def matches_b1_conditions(
    quote: DailyQuoteIn,
    closes: Sequence[float],
    zxdq: float,
    k_value: float,
    d_value: float,
    recent_volumes: Sequence[int],
    current_volume: int,
    profile: BacktestProfile,
) -> bool:
    if quote.board not in (MarketBoard.main, MarketBoard.chinext):
        return False
    if profile.exclude_st and is_st_stock(quote.name):
        return False
    if profile.min_total_mv_wan is not None and quote.total_mv_wan < profile.min_total_mv_wan:
        return False
    zxdkx = b1_zxdkx(closes)
    if zxdkx is None:
        return False
    j_value = 3.0 * k_value - 2.0 * d_value
    return (
        j_value < B1_J_THRESHOLD
        and is_price_near_b1_line(quote.close, zxdq, zxdkx)
        and is_significant_shrinking_volume(quote, recent_volumes, current_volume)
        and has_n_shape_uptrend(closes)
    )


def b1_snapshot(quote: DailyQuoteIn, zxdq: float, zxdkx: float) -> PickSnapshot:
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
        stop_loss_price=b1_stop_loss_price(quote.close, zxdq, zxdkx),
        limit_shape="b1",
        limit_shape_label="B1选股",
        next_open=quote.next_open,
        future_closes=quote.future_closes,
    )


def b1_rsv(closes: Sequence[float], highs: Sequence[float], lows: Sequence[float], n: int) -> float | None:
    if len(closes) < n:
        return None
    highest = max(highs[-n:])
    lowest = min(lows[-n:])
    rng = highest - lowest
    if rng == 0:
        return 50.0
    return (closes[-1] - lowest) / rng * 100.0


def b1_zxdkx(closes: Sequence[float]) -> float | None:
    windows = [14, 28, 57, B1_MIN_HISTORY_DAYS]
    if len(closes) < max(windows):
        return None
    return sum(simple_ma(closes, window) for window in windows) / len(windows)


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


def quote_volume(quote: DailyQuoteIn) -> int:
    return sum(max(0, trade.volume) for trade in quote.minute_trades)


def is_price_near_b1_line(close: float, zxdq: float, zxdkx: float) -> bool:
    return any(is_price_near_support_line(close, line) for line in (zxdq, zxdkx))


def is_price_near_support_line(close: float, line: float) -> bool:
    if close <= 0.0 or line <= 0.0:
        return False
    return line <= close <= line * (1.0 + B1_LINE_PROXIMITY_MAX)


def is_significant_shrinking_volume(quote: DailyQuoteIn, recent_volumes: Sequence[int], current_volume: int) -> bool:
    valid_volumes = [volume for volume in recent_volumes if volume > 0]
    if current_volume > 0 and valid_volumes:
        previous_volume = valid_volumes[-1]
        if current_volume > previous_volume * B1_VOLUME_PREVIOUS_RATIO_MAX:
            return False
        if len(valid_volumes) >= 3:
            average_volume = sum(valid_volumes) / len(valid_volumes)
            return current_volume <= average_volume * B1_VOLUME_AVG_RATIO_MAX
        return True
    return 0.0 < quote.volume_ratio <= B1_VOLUME_AVG_RATIO_MAX


def has_n_shape_uptrend(closes: Sequence[float]) -> bool:
    if len(closes) < B1_N_SHAPE_LOOKBACK_DAYS:
        return False
    recent_closes = closes[-20:]
    prior_closes = closes[-B1_N_SHAPE_LOOKBACK_DAYS:-20]
    if not recent_closes or not prior_closes:
        return False

    current_ma20 = simple_ma(closes, 20)
    current_ma60 = simple_ma(closes, B1_N_SHAPE_LOOKBACK_DAYS)
    previous_ma60 = simple_ma(closes[:-20], B1_N_SHAPE_LOOKBACK_DAYS)
    if current_ma20 <= current_ma60 or current_ma60 <= previous_ma60:
        return False

    prior_low = min(prior_closes)
    prior_high = max(prior_closes)
    recent_low = min(recent_closes)
    recent_high = max(recent_closes)
    return recent_low >= prior_low * 1.03 and recent_high >= prior_high * 0.98


def b1_stop_loss_price(close: float, zxdq: float, zxdkx: float) -> float:
    valid_lines = [line for line in (zxdq, zxdkx) if 0.0 < line < close]
    if valid_lines:
        return max(valid_lines)
    fallback_lines = [line for line in (zxdq, zxdkx) if line > 0.0]
    return min(fallback_lines) if fallback_lines else close


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
