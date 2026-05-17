from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .schemas import DailyQuoteIn, IndicatorOption, MarketBoard, MinuteTrade


INDICATORS = [
    IndicatorOption(
        id="volume",
        name="量比放大",
        description="量比大于 1.8，过滤成交活跃度不足的涨停。",
    ),
    IndicatorOption(
        id="seal",
        name="封单强度",
        description="封单金额不低于 5000 万，保留封板更稳定的标的。",
    ),
    IndicatorOption(
        id="turnover",
        name="换手确认",
        description="换手率位于 4% 到 28%，避开极端缩量或过度分歧。",
    ),
    IndicatorOption(
        id="close",
        name="收盘强势",
        description="收盘价贴近最高价，确认尾盘没有明显开板回落。",
    ),
]


@dataclass(frozen=True)
class PickSnapshot:
    trade_date: str
    code: str
    name: str
    board: MarketBoard
    concept: str
    close: float
    change_percent: float
    volume_ratio: float
    turnover_rate: float
    total_mv_wan: float
    sealed_amount_wan: float
    stop_loss_price: float
    limit_shape: str
    limit_shape_label: str
    next_open: float | None
    future_closes: list[float]


def select_limit_up(quotes: Iterable[DailyQuoteIn], indicator_ids: Sequence[str]) -> list[PickSnapshot]:
    ids = set(indicator_ids)
    result: list[PickSnapshot] = []
    for quote in quotes:
        if quote.board not in (MarketBoard.main, MarketBoard.chinext):
            continue
        if not is_limit_up(quote):
            continue
        if is_one_word_limit_up(quote):
            continue
        if not matches_indicators(quote, ids):
            continue
        result.append(to_pick(quote))

    return sorted(result, key=lambda pick: (pick.board.value, -pick.sealed_amount_wan))


def is_limit_up(quote: DailyQuoteIn) -> bool:
    expected = quote.previous_close * (1.0 + quote.board.limit_up_rate)
    return quote.close >= expected - 0.02 and quote.close >= quote.high - 0.02


def is_one_word_limit_up(quote: DailyQuoteIn) -> bool:
    return (
        abs(quote.open - quote.close) <= 0.01
        and abs(quote.high - quote.close) <= 0.01
        and abs(quote.low - quote.close) <= 0.01
    )


def matches_indicators(quote: DailyQuoteIn, indicator_ids: set[str]) -> bool:
    for indicator_id in indicator_ids:
        if indicator_id == "volume" and quote.volume_ratio < 1.8:
            return False
        if indicator_id == "seal" and 0.0 < quote.sealed_amount_wan < 5000.0:
            return False
        if indicator_id == "turnover" and not 4.0 <= quote.turnover_rate <= 28.0:
            return False
        if indicator_id == "close" and quote.close < quote.high * 0.995:
            return False
    return True


def to_pick(quote: DailyQuoteIn) -> PickSnapshot:
    shape, shape_label = limit_shape(quote)
    return PickSnapshot(
        trade_date=quote.trade_date,
        code=quote.code,
        name=quote.name,
        board=quote.board,
        concept=quote.concept,
        close=quote.close,
        change_percent=(quote.close - quote.previous_close) / quote.previous_close * 100.0,
        volume_ratio=quote.volume_ratio,
        turnover_rate=quote.turnover_rate,
        total_mv_wan=quote.total_mv_wan,
        sealed_amount_wan=quote.sealed_amount_wan,
        stop_loss_price=stop_loss_price(quote),
        limit_shape=shape,
        limit_shape_label=shape_label,
        next_open=quote.next_open,
        future_closes=quote.future_closes,
    )


def minute_vwap(minute_trades: Sequence[MinuteTrade]) -> float:
    if not minute_trades:
        return 0.0
    total_volume = sum(trade.volume for trade in minute_trades)
    if total_volume > 0:
        return sum(trade.price * trade.volume for trade in minute_trades) / total_volume
    return sum(trade.price for trade in minute_trades) / len(minute_trades)


def stop_loss_price(quote: DailyQuoteIn) -> float:
    vwap = minute_vwap(quote.minute_trades)
    if vwap > 0:
        return vwap
    return (quote.open + quote.high + quote.low + quote.close) / 4.0


def limit_shape(quote: DailyQuoteIn) -> tuple[str, str]:
    limit_price = quote.previous_close * (1.0 + quote.board.limit_up_rate)
    limit_minutes = [
        trade.minute
        for trade in quote.minute_trades
        if minute_to_int(trade.minute) is not None and trade.price >= limit_price - 0.02
    ]
    if limit_minutes:
        first = min(limit_minutes, key=lambda item: minute_to_int(item) or 0)
        first_value = minute_to_int(first) or 0
        broke_after_limit = any(
            (minute_to_int(trade.minute) or 0) > first_value and trade.price < limit_price - 0.02
            for trade in quote.minute_trades
            if minute_to_int(trade.minute) is not None
        )
        if broke_after_limit:
            return "resealed", "炸板涨停"
        if first_value < 11 * 60 + 30:
            return "morning", "早上封板"
        return "afternoon", "下午封板"

    if quote.open >= limit_price - 0.02 and quote.low < limit_price - 0.02:
        return "resealed", "炸板涨停"
    if quote.low <= quote.previous_close * (1.0 + quote.board.limit_up_rate * 0.45):
        return "afternoon", "下午封板"
    return "morning", "早上封板"


def minute_to_int(value: str) -> int | None:
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None
