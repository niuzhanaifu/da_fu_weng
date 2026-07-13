from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

from .db import connect, init_db
from .repository import clear_selection_results, upsert_daily_quotes
from .sample_data import sample_quotes
from .schemas import DailyQuoteIn, MarketBoard, MinuteTrade
from .service import DEFAULT_INDICATORS, run_daily_selection, sync_tushare_quotes
from .tushare_provider import fetch_daily_quotes


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m stock_server.jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db")
    subparsers.add_parser("seed-sample")
    subparsers.add_parser("clear-derived-data")

    daily = subparsers.add_parser("run-daily-selection")
    daily.add_argument("--date", dest="trade_date", default=None)
    daily.add_argument("--indicators", default=",".join(DEFAULT_INDICATORS))

    tushare_parser = subparsers.add_parser("import-tushare")
    tushare_parser.add_argument("--date", dest="trade_date", required=True)

    sync_parser = subparsers.add_parser("sync-tushare")
    sync_parser.add_argument("--start-date", required=True)
    sync_parser.add_argument("--end-date", required=True)

    diagnose_parser = subparsers.add_parser("diagnose-volume-ratio")
    diagnose_parser.add_argument("--start-date", default="2026-06-02")
    diagnose_parser.add_argument("--end-date", default=None)
    diagnose_parser.add_argument("--threshold", type=float, default=2.0)
    diagnose_parser.add_argument("--limit", type=int, default=50)

    repair_parser = subparsers.add_parser("repair-volume-ratio")
    repair_parser.add_argument("--start-date", default=None)
    repair_parser.add_argument("--end-date", default=None)
    repair_parser.add_argument("--lookback-days", type=int, default=10)

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
        elif args.command == "clear-derived-data":
            count = clear_selection_results(conn)
            print(f"cleared {count} saved selection rows")
        elif args.command == "run-daily-selection":
            indicators = [item for item in args.indicators.split(",") if item]
            result = run_daily_selection(conn, args.trade_date, indicators)
            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        elif args.command == "import-tushare":
            quotes = fetch_daily_quotes(args.trade_date)
            count = upsert_daily_quotes(conn, quotes)
            print(f"imported {count} tushare quotes")
        elif args.command == "sync-tushare":
            count = sync_tushare_quotes(conn, args.start_date, args.end_date, progress=print)
            print(f"synced {count} tushare quotes")
        elif args.command == "diagnose-volume-ratio":
            diagnose_volume_ratio(conn, args.start_date, args.end_date, args.threshold, args.limit)
        elif args.command == "repair-volume-ratio":
            repair_volume_ratio(conn, args.start_date, args.end_date, args.lookback_days)
        elif args.command == "import-csv":
            quotes = load_quotes_from_csv(Path(args.path))
            count = upsert_daily_quotes(conn, quotes)
            print(f"imported {count} quotes")


def repair_volume_ratio(
    conn,
    start_date: str | None,
    end_date: str | None,
    lookback_days: int,
) -> None:
    selected_end = end_date or (date.today() - timedelta(days=1)).isoformat()
    selected_start = start_date or (
        date.fromisoformat(selected_end) - timedelta(days=max(lookback_days - 1, 0))
    ).isoformat()
    count = sync_tushare_quotes(conn, selected_start, selected_end)
    print(f"repaired volume_ratio by syncing {count} tushare quotes from {selected_start} to {selected_end}")


def diagnose_volume_ratio(conn, start_date: str, end_date: str | None, threshold: float, limit: int) -> None:
    params: list[object] = [start_date]
    end_filter = ""
    if end_date:
        end_filter = " AND trade_date <= ?"
        params.append(end_date)

    print(f"date range: {start_date}..{end_date or 'latest'}")
    print(f"volume ratio threshold: > {threshold}")

    print("\n=== daily volume_ratio coverage ===")
    coverage_sql = f"""
        SELECT
            trade_date,
            COUNT(*) AS total,
            SUM(CASE WHEN volume_ratio IS NULL OR volume_ratio <= 0 THEN 1 ELSE 0 END) AS no_ratio,
            SUM(CASE WHEN volume_ratio > 0 THEN 1 ELSE 0 END) AS has_ratio,
            SUM(CASE WHEN volume_ratio > ? THEN 1 ELSE 0 END) AS ratio_gt_threshold,
            ROUND(AVG(CASE WHEN volume_ratio > 0 THEN volume_ratio END), 3) AS avg_ratio,
            ROUND(MAX(volume_ratio), 3) AS max_ratio
        FROM daily_quotes
        WHERE trade_date >= ?{end_filter}
        GROUP BY trade_date
        ORDER BY trade_date
    """
    print_rows(conn.execute(coverage_sql, [threshold, *params]).fetchall())

    print("\n=== limit-up non-one-word candidates ===")
    candidates_sql = f"""
        SELECT
            trade_date,
            COUNT(*) AS limit_candidates,
            SUM(CASE WHEN volume_ratio IS NULL OR volume_ratio <= 0 THEN 1 ELSE 0 END) AS no_ratio,
            SUM(CASE WHEN volume_ratio > 0 THEN 1 ELSE 0 END) AS has_ratio,
            SUM(CASE WHEN volume_ratio > ? THEN 1 ELSE 0 END) AS ratio_gt_threshold,
            ROUND(AVG(CASE WHEN volume_ratio > 0 THEN volume_ratio END), 3) AS avg_ratio,
            ROUND(MAX(volume_ratio), 3) AS max_ratio
        FROM daily_quotes
        WHERE trade_date >= ?{end_filter}
            AND board IN ('main', 'chinext')
            AND close >= previous_close * CASE WHEN board = 'chinext' THEN 1.20 ELSE 1.10 END - 0.02
            AND close >= high - 0.02
            AND NOT (
                ABS(open - close) <= 0.01
                AND ABS(high - close) <= 0.01
                AND ABS(low - close) <= 0.01
            )
        GROUP BY trade_date
        ORDER BY trade_date
    """
    print_rows(conn.execute(candidates_sql, [threshold, *params]).fetchall())

    print("\n=== blocked by volume_ratio threshold ===")
    blocked_sql = f"""
        SELECT
            trade_date,
            code,
            name,
            board,
            ROUND(volume_ratio, 3) AS volume_ratio,
            ROUND(turnover_rate, 3) AS turnover_rate,
            ROUND(sealed_amount_wan, 1) AS sealed_amount_wan,
            ROUND(close, 3) AS close
        FROM daily_quotes
        WHERE trade_date >= ?{end_filter}
            AND board IN ('main', 'chinext')
            AND close >= previous_close * CASE WHEN board = 'chinext' THEN 1.20 ELSE 1.10 END - 0.02
            AND close >= high - 0.02
            AND NOT (
                ABS(open - close) <= 0.01
                AND ABS(high - close) <= 0.01
                AND ABS(low - close) <= 0.01
            )
            AND (volume_ratio IS NULL OR volume_ratio <= ?)
        ORDER BY trade_date DESC, volume_ratio DESC, sealed_amount_wan DESC
        LIMIT ?
    """
    print_rows(conn.execute(blocked_sql, [*params, threshold, limit]).fetchall())

    print("\nHow to read:")
    print("- no_ratio high: volume_ratio is missing or stored as 0.")
    print("- has_ratio normal but ratio_gt_threshold low: data exists, but does not pass the threshold.")
    print("- blocked rows are limit-up candidates that failed only this volume_ratio check.")


def print_rows(rows) -> None:
    if not rows:
        print("(no rows)")
        return
    for row in rows:
        print(dict(row))


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
