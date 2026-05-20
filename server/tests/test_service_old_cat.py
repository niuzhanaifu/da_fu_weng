import sqlite3
import unittest

from stock_server import repository
from stock_server.schemas import DailyQuoteIn, MarketBoard, MinuteTrade
from stock_server.service import run_selection_group


class OldCatSelectionTest(unittest.TestCase):
    def test_t_plus_one_close_selects_previous_day_limit_up_without_t_plus_two_data(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        repository.upsert_daily_quotes(
            conn,
            [
                quote("2024-05-09", previous_close=10.0, open_price=10.0, high=10.2, low=9.9, close=10.0),
                quote(
                    "2024-05-10",
                    previous_close=10.0,
                    open_price=10.2,
                    high=11.0,
                    low=10.2,
                    close=11.0,
                    minute_trades=[MinuteTrade(minute="10:00", price=11.0, volume=1000)],
                ),
                quote("2024-05-13", previous_close=11.0, open_price=11.2, high=11.4, low=11.0, close=11.3),
            ],
        )

        group = run_selection_group(conn, None, ["volume", "seal", "close"], "old_cat_buy")

        self.assertEqual(group.trade_date, "2024-05-13")
        self.assertEqual([pick.trade_date for pick in group.picks], ["2024-05-10"])
        self.assertEqual(group.picks[0].future_dates, ["2024-05-13"])
        self.assertEqual(group.picks[0].future_closes, [11.3])

    def test_t_plus_one_close_above_threshold_is_filtered_out(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        repository.upsert_daily_quotes(
            conn,
            [
                quote("2024-05-09", previous_close=10.0, open_price=10.0, high=10.2, low=9.9, close=10.0),
                quote(
                    "2024-05-10",
                    previous_close=10.0,
                    open_price=10.2,
                    high=11.0,
                    low=10.2,
                    close=11.0,
                    minute_trades=[MinuteTrade(minute="10:00", price=11.0, volume=1000)],
                ),
                quote("2024-05-13", previous_close=11.0, open_price=11.2, high=11.8, low=11.0, close=11.6),
            ],
        )

        group = run_selection_group(conn, None, ["volume", "seal", "close"], "old_cat_buy")

        self.assertEqual(group.trade_date, "2024-05-13")
        self.assertEqual(group.picks, [])


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


def quote(
    trade_date: str,
    previous_close: float,
    open_price: float,
    high: float,
    low: float,
    close: float,
    minute_trades: list[MinuteTrade] | None = None,
) -> DailyQuoteIn:
    return DailyQuoteIn(
        trade_date=trade_date,
        code="600000",
        name="Sample Equity",
        board=MarketBoard.main,
        previous_close=previous_close,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume_ratio=2.0,
        turnover_rate=10.0,
        total_mv_wan=100000.0,
        sealed_amount_wan=6000.0,
        minute_trades=minute_trades or [MinuteTrade(minute="15:00", price=close, volume=1000)],
    )


if __name__ == "__main__":
    unittest.main()
