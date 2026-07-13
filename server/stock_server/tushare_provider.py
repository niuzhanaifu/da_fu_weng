from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Iterator
from urllib import request

from .config import settings
from .schemas import DailyQuoteIn, MarketBoard, MinuteTrade


logger = logging.getLogger("stock_server.tushare")
TUSHARE_API_URL = "http://api.tushare.pro"


class TushareError(RuntimeError):
    pass


def fetch_daily_quotes(trade_date: str) -> list[DailyQuoteIn]:
    return fetch_daily_quotes_range(trade_date, trade_date)


def fetch_daily_quotes_range(start_date: str, end_date: str) -> list[DailyQuoteIn]:
    quotes: list[DailyQuoteIn] = []
    for _, _, _, daily_quotes in fetch_daily_quote_batches(start_date, end_date):
        quotes.extend(daily_quotes)

    logger.info(
        "fetched tushare daily quotes start_date=%s end_date=%s count=%s",
        start_date,
        end_date,
        len(quotes),
    )
    return quotes


def fetch_daily_quote_batches(
    start_date: str,
    end_date: str,
    progress: Callable[[str], None] | None = None,
) -> Iterator[tuple[str, int, int, list[DailyQuoteIn]]]:
    token = settings.tushare_token.strip()
    if not token:
        raise TushareError("TUSHARE_TOKEN is not configured.")

    basics = stock_basics(token)
    ts_dates = open_trade_dates(token, to_tushare_date(start_date), to_tushare_date(end_date))
    latest_adj_factor_by_code: dict[str, tuple[str, float]] = {}
    total_dates = len(ts_dates)

    for index, ts_date in enumerate(ts_dates, start=1):
        if progress is not None:
            progress(f"scan adj_factor {index}/{total_dates} {from_tushare_date(ts_date)}")
        factor_rows = fetch_adj_factors_for_date(token, ts_date)
        for item in factor_rows:
            ts_code = str(item["ts_code"])
            adj_factor = as_float(item.get("adj_factor"))
            if adj_factor <= 0:
                continue
            latest = latest_adj_factor_by_code.get(ts_code)
            if latest is None or ts_date >= latest[0]:
                latest_adj_factor_by_code[ts_code] = (ts_date, adj_factor)

    previous_close_by_code: dict[str, float] = {}
    for index, ts_date in enumerate(ts_dates, start=1):
        if progress is not None:
            progress(f"fetch daily {index}/{total_dates} {from_tushare_date(ts_date)}")
        daily_rows, daily_basic_by_code = fetch_daily_payload_for_date(token, ts_date)
        adj_factors = adj_factor_map_for_date(token, ts_date, daily_rows)
        quotes = daily_rows_to_quotes(
            basics,
            ts_date,
            daily_rows,
            daily_basic_by_code,
            adj_factors,
            latest_adj_factor_by_code,
        )
        normalize_previous_close_with_state(quotes, previous_close_by_code)
        logger.info(
            "fetched tushare qfq daily quotes trade_date=%s count=%s progress=%s/%s",
            from_tushare_date(ts_date),
            len(quotes),
            index,
            total_dates,
        )
        yield from_tushare_date(ts_date), index, total_dates, quotes


def fetch_market_index_quotes_range(start_date: str, end_date: str) -> list[tuple[str, str, float]]:
    token = settings.tushare_token.strip()
    if not token:
        raise TushareError("TUSHARE_TOKEN is not configured.")

    rows = call_tushare(
        token,
        "index_daily",
        {
            "ts_code": "000001.SH",
            "start_date": to_tushare_date(start_date),
            "end_date": to_tushare_date(end_date),
        },
        "ts_code,trade_date,close",
    )
    quotes = [
        (from_tushare_date(str(row["trade_date"])), str(row["ts_code"]), as_float(row.get("close")))
        for row in rows
    ]
    logger.info("fetched tushare index quotes start_date=%s end_date=%s count=%s", start_date, end_date, len(quotes))
    return quotes


def fetch_daily_quotes_for_date(
    token: str,
    basics: dict[str, dict[str, Any]],
    ts_date: str,
) -> list[DailyQuoteIn]:
    daily_rows, daily_basic_by_code = fetch_daily_payload_for_date(token, ts_date)
    quotes = daily_rows_to_quotes(
        basics,
        ts_date,
        daily_rows,
        daily_basic_by_code,
        adj_factors={},
        latest_adj_factor_by_code={},
    )
    logger.info("fetched tushare daily quotes trade_date=%s count=%s", from_tushare_date(ts_date), len(quotes))
    return quotes


def fetch_daily_payload_for_date(
    token: str,
    ts_date: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    daily_rows = call_tushare(
        token,
        "daily",
        {"trade_date": ts_date},
        "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
    )
    basic_rows = call_tushare(
        token,
        "daily_basic",
        {"trade_date": ts_date},
        "ts_code,turnover_rate,volume_ratio,total_mv",
    )
    daily_basic_by_code = {item["ts_code"]: item for item in basic_rows}
    if daily_rows and len(daily_basic_by_code) < len(daily_rows) * 0.8:
        raise TushareError(
            f"daily_basic returned too few rows for {from_tushare_date(ts_date)}: "
            f"{len(daily_basic_by_code)}/{len(daily_rows)}"
        )
    volume_ratio_count = sum(1 for item in basic_rows if as_float(item.get("volume_ratio")) > 0)
    if daily_rows and volume_ratio_count < len(daily_rows) * 0.8:
        raise TushareError(
            f"daily_basic volume_ratio returned too few valid rows for {from_tushare_date(ts_date)}: "
            f"{volume_ratio_count}/{len(daily_rows)}"
        )

    return daily_rows, daily_basic_by_code


def daily_rows_to_quotes(
    basics: dict[str, dict[str, Any]],
    ts_date: str,
    daily_rows: list[dict[str, Any]],
    daily_basic_by_code: dict[str, dict[str, Any]],
    adj_factors: dict[tuple[str, str], float],
    latest_adj_factor_by_code: dict[str, tuple[str, float]],
) -> list[DailyQuoteIn]:
    quotes: list[DailyQuoteIn] = []
    for row in daily_rows:
        ts_code = row["ts_code"]
        board = board_for_ts_code(ts_code)
        if board is None:
            continue

        multiplier = qfq_multiplier(ts_code, ts_date, adj_factors, latest_adj_factor_by_code)
        close = adjusted_price(row.get("close"), multiplier)
        daily_basic = daily_basic_by_code.get(ts_code, {})
        stock = basics.get(ts_code, {})
        quotes.append(
            DailyQuoteIn(
                trade_date=from_tushare_date(row["trade_date"]),
                code=ts_code.split(".")[0],
                name=str(stock.get("name") or ts_code.split(".")[0]),
                board=board,
                concept=str(stock.get("industry") or ""),
                previous_close=adjusted_price(row.get("pre_close"), multiplier),
                open=adjusted_price(row.get("open"), multiplier),
                high=adjusted_price(row.get("high"), multiplier),
                low=adjusted_price(row.get("low"), multiplier),
                close=close,
                volume_ratio=as_float(daily_basic.get("volume_ratio")),
                turnover_rate=as_float(daily_basic.get("turnover_rate")),
                total_mv_wan=as_float(daily_basic.get("total_mv")),
                sealed_amount_wan=0.0,
                next_open=None,
                future_closes=[],
                minute_trades=daily_vwap_trade(row, multiplier),
            )
        )
    return quotes


def fetch_adj_factors_for_date(token: str, ts_date: str) -> list[dict[str, Any]]:
    rows = call_tushare(
        token,
        "adj_factor",
        {"trade_date": ts_date},
        "ts_code,trade_date,adj_factor",
    )
    if not rows:
        raise TushareError(f"adj_factor returned no rows for {from_tushare_date(ts_date)}")
    return rows


def adj_factor_map_for_date(
    token: str,
    ts_date: str,
    daily_rows: list[dict[str, Any]],
) -> dict[tuple[str, str], float]:
    factor_rows = fetch_adj_factors_for_date(token, ts_date)
    factor_by_code = {str(item["ts_code"]): as_float(item.get("adj_factor")) for item in factor_rows}
    supported_daily_rows = [row for row in daily_rows if board_for_ts_code(str(row["ts_code"])) is not None]
    factor_count = sum(1 for row in supported_daily_rows if factor_by_code.get(str(row["ts_code"]), 0.0) > 0)
    if supported_daily_rows and factor_count < len(supported_daily_rows) * 0.8:
        raise TushareError(
            f"adj_factor returned too few valid rows for {from_tushare_date(ts_date)}: "
            f"{factor_count}/{len(supported_daily_rows)}"
        )
    return {
        (ts_code, ts_date): adj_factor
        for ts_code, adj_factor in factor_by_code.items()
        if adj_factor > 0.0
    }


def qfq_multiplier(
    ts_code: str,
    ts_date: str,
    adj_factors: dict[tuple[str, str], float],
    latest_adj_factor_by_code: dict[str, tuple[str, float]],
) -> float:
    adj_factor = adj_factors.get((ts_code, ts_date))
    latest = latest_adj_factor_by_code.get(ts_code)
    if not adj_factor or not latest or latest[1] <= 0:
        return 1.0
    return adj_factor / latest[1]


def adjusted_price(raw: Any, multiplier: float) -> float:
    return as_float(raw) * multiplier


def normalize_previous_close(quotes: list[DailyQuoteIn]) -> list[DailyQuoteIn]:
    normalize_previous_close_with_state(quotes, {})
    return quotes


def normalize_previous_close_with_state(
    quotes: list[DailyQuoteIn],
    previous_close_by_code: dict[str, float],
) -> None:
    sorted_quotes = sorted(quotes, key=lambda item: (item.code, item.trade_date))
    for quote in sorted_quotes:
        previous_close = previous_close_by_code.get(quote.code)
        if previous_close is not None:
            quote.previous_close = previous_close
        previous_close_by_code[quote.code] = quote.close


def open_trade_dates(token: str, start_date: str, end_date: str) -> list[str]:
    try:
        rows = call_tushare(
            token,
            "trade_cal",
            {"exchange": "", "start_date": start_date, "end_date": end_date, "is_open": "1"},
            "cal_date,is_open",
        )
    except TushareError as exc:
        logger.warning("tushare trade_cal unavailable, fallback to calendar days: %s", exc)
        return calendar_dates(start_date, end_date)
    return [str(row["cal_date"]) for row in rows if str(row.get("is_open")) == "1"]


def stock_basics(token: str) -> dict[str, dict[str, Any]]:
    rows = call_tushare(
        token,
        "stock_basic",
        {"list_status": "L"},
        "ts_code,symbol,name,market,industry",
    )
    return {item["ts_code"]: item for item in rows}


def fetch_limits(token: str, ts_date: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    limit_price_rows = call_tushare(
        token,
        "stk_limit",
        {"trade_date": ts_date},
        "ts_code,trade_date,up_limit,down_limit",
    )
    for row in limit_price_rows:
        result[row["ts_code"]] = {"up_limit": as_float(row.get("up_limit"))}

    try:
        limit_pool_rows = call_tushare(
            token,
            "limit_list_d",
            {"trade_date": ts_date, "limit_type": "U"},
            "ts_code,trade_date,limit,fd_amount",
        )
    except TushareError as exc:
        logger.warning("tushare limit_list_d unavailable, fallback to stk_limit only: %s", exc)
        limit_pool_rows = []

    for row in limit_pool_rows:
        item = result.setdefault(row["ts_code"], {})
        item["is_up"] = str(row.get("limit") or "U").upper() == "U"
        item["fd_amount"] = as_float(row.get("fd_amount"))
    return result


def fetch_minutes_for_limit_up(token: str, ts_code: str, ts_date: str) -> list[MinuteTrade]:
    if not settings.tushare_fetch_minutes:
        return []
    try:
        rows = call_tushare(
            token,
            "stk_mins",
            {
                "ts_code": ts_code,
                "freq": "1min",
                "start_date": f"{from_tushare_date(ts_date)} 09:00:00",
                "end_date": f"{from_tushare_date(ts_date)} 15:30:00",
            },
            "ts_code,trade_time,close,vol",
        )
    except TushareError as exc:
        logger.warning("tushare stk_mins unavailable for %s %s: %s", ts_code, ts_date, exc)
        return []

    trades: list[MinuteTrade] = []
    for row in rows:
        trade_time = str(row.get("trade_time") or "")
        if not trade_time.startswith(from_tushare_date(ts_date)):
            continue
        minute = trade_time[-8:-3] if len(trade_time) >= 8 else trade_time
        trades.append(
            MinuteTrade(
                minute=minute,
                price=as_float(row.get("close")),
                volume=int(as_float(row.get("vol"))),
            )
        )
    return sorted(trades, key=lambda item: item.minute)


def call_tushare(token: str, api_name: str, params: dict[str, Any], fields: str) -> list[dict[str, Any]]:
    payload = json.dumps(
        {
            "api_name": api_name,
            "token": token,
            "params": params,
            "fields": fields,
        }
    ).encode("utf-8")
    http_request = request.Request(
        TUSHARE_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=settings.tushare_timeout_seconds) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if parsed.get("code") != 0:
        raise TushareError(f"{api_name} failed: {parsed.get('msg') or body}")

    data = parsed.get("data") or {}
    response_fields = data.get("fields") or []
    items = data.get("items") or []
    return [dict(zip(response_fields, item)) for item in items]


def board_for_ts_code(ts_code: str) -> MarketBoard | None:
    code = ts_code.split(".")[0]
    if code.startswith(("300", "301")):
        return MarketBoard.chinext
    if code.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
        return MarketBoard.main
    return None


def is_limit_close(close: float, up_limit: float | None) -> bool:
    if not up_limit:
        return False
    return close >= up_limit - 0.02


def sealed_amount_wan(raw: float | None) -> float:
    if not raw:
        return 0.0
    return raw / 10000.0 if raw > 100000.0 else raw


def daily_vwap_trade(row: dict[str, Any], price_multiplier: float = 1.0) -> list[MinuteTrade]:
    volume_hands = as_float(row.get("vol"))
    amount_thousand_yuan = as_float(row.get("amount"))
    if volume_hands <= 0 or amount_thousand_yuan <= 0:
        return []
    price = amount_thousand_yuan * 10.0 / volume_hands * price_multiplier
    return [MinuteTrade(minute="daily", price=price, volume=int(volume_hands))]


def is_limit_up_row(row: dict[str, Any], board: MarketBoard) -> bool:
    previous_close = as_float(row.get("pre_close"))
    close = as_float(row.get("close"))
    high = as_float(row.get("high"))
    expected = previous_close * (1.0 + board.limit_up_rate)
    return close >= expected - 0.02 and close >= high - 0.02


def as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def to_tushare_date(trade_date: str) -> str:
    return trade_date.replace("-", "")


def from_tushare_date(trade_date: str) -> str:
    return f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"


def calendar_dates(start_date: str, end_date: str) -> list[str]:
    current = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    dates: list[str] = []
    while current <= end:
        dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return dates
