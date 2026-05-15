from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .db import connect, init_db
from .repository import upsert_daily_quotes
from .sample_data import sample_quotes
from .schemas import DailyQuoteIn, MarketBoard, MinuteTrade
from .service import DEFAULT_INDICATORS, run_daily_selection
from .tushare_provider import fetch_daily_quotes


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m stock_server.jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db")
    subparsers.add_parser("seed-sample")

    daily = subparsers.add_parser("run-daily-selection")
    daily.add_argument("--date", dest="trade_date", default=None)
    daily.add_argument("--indicators", default=",".join(DEFAULT_INDICATORS))

    tushare_parser = subparsers.add_parser("import-tushare")
    tushare_parser.add_argument("--date", dest="trade_date", required=True)

    csv_parser = subparsers.add_parser("import-csv")
    csv_parser.add_argument("path")

    args = parser.parse_args()
    init_db()

    if args.command == "init-db":
        print("database initialized")
        return

    with connect() as conn:
        if args.command == "seed-sample":
            count = upsert_daily_quotes(conn, sample_quotes())
            print(f"seeded {count} quotes")
        elif args.command == "run-daily-selection":
            indicators = [item for item in args.indicators.split(",") if item]
            result = run_daily_selection(conn, args.trade_date, indicators)
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        elif args.command == "import-tushare":
            quotes = fetch_daily_quotes(args.trade_date)
            count = upsert_daily_quotes(conn, quotes)
            print(f"imported {count} tushare quotes")
        elif args.command == "import-csv":
            quotes = load_quotes_from_csv(Path(args.path))
            count = upsert_daily_quotes(conn, quotes)
            print(f"imported {count} quotes")


def load_quotes_from_csv(path: Path) -> list[DailyQuoteIn]:
    quotes: list[DailyQuoteIn] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            quotes.append(
                DailyQuoteIn(
                    trade_date=row["trade_date"],
                    code=row["code"],
                    name=row["name"],
                    board=MarketBoard(row["board"]),
                    concept=row.get("concept", ""),
                    previous_close=float(row["previous_close"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume_ratio=float(row.get("volume_ratio") or 0),
                    turnover_rate=float(row.get("turnover_rate") or 0),
                    sealed_amount_wan=float(row.get("sealed_amount_wan") or 0),
                    next_open=float(row["next_open"]) if row.get("next_open") else None,
                    future_closes=parse_float_list(row.get("future_closes", "")),
                    minute_trades=parse_minute_trades(row.get("minute_trades", "")),
                )
            )
    return quotes


def parse_float_list(raw: str) -> list[float]:
    if not raw:
        return []
    return [float(item) for item in raw.split("|") if item]


def parse_minute_trades(raw: str) -> list[MinuteTrade]:
    if not raw:
        return []
    trades: list[MinuteTrade] = []
    for item in raw.split("|"):
        if not item:
            continue
        minute, price, volume = item.split(":")
        trades.append(MinuteTrade(minute=minute, price=float(price), volume=int(volume)))
    return trades


if __name__ == "__main__":
    main()
