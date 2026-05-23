import sqlite3
import unittest
from datetime import datetime, timedelta

from stock_server import repository
from stock_server.schemas import DailyQuoteIn, MarketBoard, MinuteTrade
from stock_server.service import BACKTEST_PROFILES, build_backtest_picks


class B1BacktestSelectionTest(unittest.TestCase):
    def test_b1_selects_shrinking_volume_candidate_and_uses_trend_stop_loss(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        dates = date_strings("2024-01-01", 122)
        candidate_date = dates[119]
        repository.upsert_daily_quotes(conn, b1_n_shape_quotes(dates, total_mv_wan=600000.0))

        picks = build_backtest_picks(
            conn,
            start_date=candidate_date,
            end_date=candidate_date,
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["b1"],
        )

        self.assertEqual([pick.trade_date for pick in picks], [candidate_date])
        self.assertEqual(picks[0].limit_shape, "b1")
        self.assertGreater(picks[0].stop_loss_price, 0.0)
        self.assertLess(picks[0].stop_loss_price, picks[0].close)
        self.assertEqual(picks[0].future_dates[:2], dates[120:122])

    def test_b1_filters_market_value_below_50b(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        dates = date_strings("2024-01-01", 122)
        candidate_date = dates[119]
        repository.upsert_daily_quotes(conn, b1_n_shape_quotes(dates, total_mv_wan=499999.0))

        picks = build_backtest_picks(
            conn,
            start_date=candidate_date,
            end_date=candidate_date,
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["b1"],
        )

        self.assertEqual(picks, [])

    def test_b1_requires_significant_volume_shrink(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        dates = date_strings("2024-01-01", 122)
        candidate_date = dates[119]
        repository.upsert_daily_quotes(
            conn,
            b1_n_shape_quotes(dates, total_mv_wan=600000.0, candidate_volume=1650),
        )

        picks = build_backtest_picks(
            conn,
            start_date=candidate_date,
            end_date=candidate_date,
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["b1"],
        )

        self.assertEqual(picks, [])

    def test_b1_requires_n_shape_uptrend(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        dates = date_strings("2024-01-01", 122)
        candidate_date = dates[119]
        repository.upsert_daily_quotes(conn, flat_quotes(dates, total_mv_wan=600000.0))

        picks = build_backtest_picks(
            conn,
            start_date=candidate_date,
            end_date=candidate_date,
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["b1"],
        )

        self.assertEqual(picks, [])


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
    close: float,
    high: float,
    low: float,
    volume: int,
    total_mv_wan: float,
) -> DailyQuoteIn:
    return DailyQuoteIn(
        trade_date=trade_date,
        code="600001",
        name="Sample Equity",
        board=MarketBoard.main,
        previous_close=previous_close,
        open=close,
        high=high,
        low=low,
        close=close,
        volume_ratio=0.8,
        turnover_rate=10.0,
        total_mv_wan=total_mv_wan,
        sealed_amount_wan=0.0,
        minute_trades=[MinuteTrade(minute="daily", price=close, volume=volume)],
    )


def b1_n_shape_quotes(
    dates: list[str],
    total_mv_wan: float,
    candidate_volume: int = 900,
) -> list[DailyQuoteIn]:
    quotes = []
    previous_close = 7.0
    for index, trade_date in enumerate(dates):
        if index < 60:
            close = 7.0 + index * 0.01
        elif index < 85:
            close = 7.6 + (index - 60) * 0.07
        elif index < 105:
            close = 9.3 - (index - 85) * 0.04
        elif index < 116:
            close = 8.5 + (index - 105) * 0.08
        elif index < 120:
            close = 8.75 - (index - 116) * 0.04
        else:
            close = 8.8 + (index - 120) * 0.05

        high = close + 0.12
        low = close - 0.12
        if 111 <= index <= 119:
            high = max(high, 9.7)
            low = min(low, 8.45)
        volume = candidate_volume if index == 119 else 1800
        quotes.append(
            quote(
                trade_date=trade_date,
                previous_close=previous_close,
                close=close,
                high=high,
                low=low,
                volume=volume,
                total_mv_wan=total_mv_wan,
            )
        )
        previous_close = close
    return quotes


def flat_quotes(dates: list[str], total_mv_wan: float) -> list[DailyQuoteIn]:
    quotes = []
    previous_close = 8.0
    for index, trade_date in enumerate(dates):
        close = 8.0
        high = 8.1
        low = 7.9
        if 111 <= index <= 119:
            close = 8.2
            high = 9.7
            low = 8.0
        quotes.append(
            quote(
                trade_date=trade_date,
                previous_close=previous_close,
                close=close,
                high=high,
                low=low,
                volume=900 if index == 119 else 1800,
                total_mv_wan=total_mv_wan,
            )
        )
        previous_close = close
    return quotes


def date_strings(start_date: str, count: int) -> list[str]:
    current = datetime.strptime(start_date, "%Y-%m-%d")
    return [(current + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(count)]


if __name__ == "__main__":
    unittest.main()
