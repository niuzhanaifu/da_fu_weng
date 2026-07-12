import random
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from stock_server import repository
from stock_server.schemas import BacktestRequest, DailyQuoteIn, MarketBoard, MinuteTrade
from stock_server.service import BACKTEST_PROFILES, build_backtest_picks, run_saved_backtest


class UltraShortBacktestTest(unittest.TestCase):
    def test_ultra_short_selects_candidate_and_ignores_volume_ratio_override(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        dates = date_strings("2024-01-01", 130)
        repository.upsert_daily_quotes(conn, ultra_short_quotes(dates))

        picks = build_backtest_picks(
            conn,
            start_date=dates[121],
            end_date=dates[121],
            indicator_ids=["volume", "seal", "close"],
            holding_days=1,
            profile=BACKTEST_PROFILES["ultra_short"],
            volume_ratio_min=99.0,
        )

        self.assertEqual([pick.trade_date for pick in picks], [dates[121]])
        self.assertEqual(picks[0].limit_shape, "ultra_short")
        self.assertEqual(picks[0].future_dates[:3], dates[122:125])
        self.assertEqual(picks[0].volume_ratio, 0.1)

    def test_ultra_short_requires_second_volume_breakout_condition(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        dates = date_strings("2024-01-01", 130)
        repository.upsert_daily_quotes(conn, ultra_short_quotes(dates, candidate_volume=900))

        picks = build_backtest_picks(
            conn,
            start_date=dates[121],
            end_date=dates[121],
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["ultra_short"],
        )

        self.assertEqual(picks, [])

    def test_ultra_short_backtest_uses_fixed_three_day_ten_percent_exit(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        dates = date_strings("2024-01-01", 130)
        repository.upsert_daily_quotes(conn, ultra_short_quotes(dates))

        with patch("stock_server.service.ensure_quotes_for_backtest"):
            result = run_saved_backtest(
                conn,
                BacktestRequest(
                    strategy_id="ultra_short",
                    start_date=dates[121],
                    end_date=dates[121],
                    holding_days=1,
                    take_profit_percent=30.0,
                    volume_ratio_min=99.0,
                ),
            )

        self.assertEqual(result.total_trades, 1)
        trade = result.trades[0]
        self.assertEqual(trade.buy_date, dates[122])
        self.assertEqual(trade.sell_date, dates[124])
        self.assertIn("收益达到10%止盈", trade.exit_reason)
        self.assertAlmostEqual(trade.return_percent, 10.0, places=6)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE daily_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            board TEXT NOT NULL,
            concept TEXT NOT NULL DEFAULT '',
            previous_close REAL NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume_ratio REAL NOT NULL DEFAULT 0,
            turnover_rate REAL NOT NULL DEFAULT 0,
            total_mv_wan REAL NOT NULL DEFAULT 0,
            sealed_amount_wan REAL NOT NULL DEFAULT 0,
            next_open REAL,
            future_closes_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, code)
        );

        CREATE TABLE minute_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            code TEXT NOT NULL,
            minute TEXT NOT NULL,
            price REAL NOT NULL,
            volume INTEGER NOT NULL DEFAULT 0,
            UNIQUE(trade_date, code, minute)
        );
        """
    )


def ultra_short_quotes(dates: list[str], candidate_volume: int = 4739) -> list[DailyQuoteIn]:
    random_source = random.Random(0)
    quotes: list[DailyQuoteIn] = []
    previous_close = 10.0
    for trade_date in dates[:120]:
        drift = 1.0 + 0.0015 + random_source.uniform(-0.012, 0.014)
        close = max(5.0, previous_close * drift)
        amplitude = random_source.uniform(0.01, 0.05)
        open_price = previous_close * (1.0 + random_source.uniform(-0.015, 0.015))
        high = max(open_price, close) * (1.0 + amplitude * random_source.random())
        low = min(open_price, close) * (1.0 - amplitude * random_source.random())
        volume = random_source.randint(800, 1500)
        turnover_rate = random_source.uniform(1.0, 8.0)
        quotes.append(quote(trade_date, previous_close, open_price, high, low, close, volume, turnover_rate))
        previous_close = close

    for index, trade_date in enumerate(dates[120:126], start=120):
        if index == 120:
            open_price = previous_close * 0.99
            close = previous_close * random_source.uniform(0.96, 0.99)
            high = max(open_price, close) * 1.01
            low = min(open_price, close) * 0.98
            volume = random_source.randint(700, 1100)
            turnover_rate = 2.0
        elif index == 121:
            open_price = previous_close * random_source.uniform(0.99, 1.01)
            close = previous_close * random_source.uniform(1.045, 1.075)
            high = close * random_source.uniform(1.0, 1.02)
            low = min(open_price, previous_close) * random_source.uniform(0.99, 1.0)
            volume = candidate_volume
            turnover_rate = random_source.uniform(1.2, 8.0)
        else:
            open_price = previous_close * random_source.uniform(0.99, 1.03)
            close = open_price * random_source.uniform(0.98, 1.08)
            high = max(open_price, close) * 1.02
            low = min(open_price, close) * 0.98
            volume = random_source.randint(900, 1800)
            turnover_rate = 2.0
        quotes.append(quote(trade_date, previous_close, open_price, high, low, close, volume, turnover_rate))
        previous_close = close
    return quotes


def quote(
    trade_date: str,
    previous_close: float,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    turnover_rate: float,
) -> DailyQuoteIn:
    return DailyQuoteIn(
        trade_date=trade_date,
        code="600001",
        name="Sample Equity",
        board=MarketBoard.main,
        previous_close=previous_close,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume_ratio=0.1,
        turnover_rate=turnover_rate,
        total_mv_wan=100000.0,
        sealed_amount_wan=0.0,
        minute_trades=[MinuteTrade(minute="daily", price=close, volume=volume)],
    )


def date_strings(start_date: str, count: int) -> list[str]:
    current = datetime.strptime(start_date, "%Y-%m-%d")
    return [(current + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(count)]


if __name__ == "__main__":
    unittest.main()
