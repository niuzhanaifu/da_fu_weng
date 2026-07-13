import sqlite3
import unittest
from unittest.mock import patch

from stock_server import repository
from stock_server.schemas import DailyQuoteIn, MarketBoard, MinuteTrade
from stock_server.service import sync_tushare_quotes


class TushareSyncTest(unittest.TestCase):
    def test_sync_tushare_quotes_writes_each_daily_batch(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        batches = [
            ("2024-05-09", 1, 2, [quote("2024-05-09", code="600001", close=10.0)]),
            ("2024-05-10", 2, 2, [quote("2024-05-10", code="600002", close=11.0)]),
        ]
        progress: list[str] = []

        with (
            patch("stock_server.service.fetch_daily_quote_batches", return_value=iter(batches)),
            patch("stock_server.service.fetch_market_index_quotes_range", return_value=[]),
        ):
            count = sync_tushare_quotes(conn, "2024-05-09", "2024-05-10", progress=progress.append)

        self.assertEqual(count, 2)
        self.assertEqual(repository.count_quotes(conn, "2024-05-09"), 1)
        self.assertEqual(repository.count_quotes(conn, "2024-05-10"), 1)
        self.assertIn("wrote daily_quotes 1/2 2024-05-09 rows=1 total=1", progress)
        self.assertIn("wrote daily_quotes 2/2 2024-05-10 rows=1 total=2", progress)


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


def quote(trade_date: str, code: str, close: float) -> DailyQuoteIn:
    return DailyQuoteIn(
        trade_date=trade_date,
        code=code,
        name="Sample Equity",
        board=MarketBoard.main,
        previous_close=close - 0.1,
        open=close,
        high=close,
        low=close,
        close=close,
        volume_ratio=1.0,
        turnover_rate=1.0,
        total_mv_wan=100000.0,
        sealed_amount_wan=0.0,
        minute_trades=[MinuteTrade(minute="daily", price=close, volume=1000)],
    )


if __name__ == "__main__":
    unittest.main()
