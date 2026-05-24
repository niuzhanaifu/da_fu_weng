import sqlite3
import unittest
from unittest.mock import patch

from stock_server import repository
from stock_server.backtest import run_backtest
from stock_server.schemas import BacktestRequest, DailyQuoteIn, MarketBoard, MinuteTrade
from stock_server.service import BACKTEST_PROFILES, build_backtest_picks, run_backtest_experiment, run_selection_group


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

    def test_selection_aligned_backtest_filters_t_plus_one_close_and_buys_t_plus_two_open(self):
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
                quote("2024-05-14", previous_close=11.3, open_price=12.0, high=12.2, low=11.8, close=12.1),
                quote("2024-05-15", previous_close=12.1, open_price=12.1, high=12.4, low=11.9, close=12.3),
            ],
        )

        aligned_profile = BACKTEST_PROFILES["old_cat_selection_aligned"]
        aligned_picks = build_backtest_picks(
            conn,
            start_date="2024-05-10",
            end_date="2024-05-10",
            indicator_ids=["volume", "seal", "close"],
            holding_days=1,
            profile=aligned_profile,
        )
        aligned_result = run_backtest(
            aligned_picks,
            holding_days=1,
            take_profit_percent=50.0,
            strategy_id=aligned_profile.engine_strategy_id,
        )

        self.assertEqual([pick.trade_date for pick in aligned_picks], ["2024-05-10"])
        self.assertEqual(aligned_result.total_trades, 1)
        self.assertEqual(aligned_result.trades[0].buy_date, "2024-05-14")
        self.assertEqual(aligned_result.trades[0].buy_price, 12.0)

        old_cat_profile = BACKTEST_PROFILES["old_cat"]
        old_cat_picks = build_backtest_picks(
            conn,
            start_date="2024-05-10",
            end_date="2024-05-10",
            indicator_ids=["volume", "seal", "close"],
            holding_days=1,
            profile=old_cat_profile,
        )
        old_cat_result = run_backtest(
            old_cat_picks,
            holding_days=1,
            take_profit_percent=50.0,
            strategy_id=old_cat_profile.engine_strategy_id,
        )

        self.assertEqual(old_cat_result.total_trades, 0)

    def test_selection_aligned_backtest_filters_t_plus_one_close_above_threshold(self):
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
                quote("2024-05-14", previous_close=11.6, open_price=11.7, high=11.9, low=11.5, close=11.8),
                quote("2024-05-15", previous_close=11.8, open_price=11.8, high=12.0, low=11.6, close=11.9),
            ],
        )

        picks = build_backtest_picks(
            conn,
            start_date="2024-05-10",
            end_date="2024-05-10",
            indicator_ids=["volume", "seal", "close"],
            holding_days=1,
            profile=BACKTEST_PROFILES["old_cat_selection_aligned"],
        )

        self.assertEqual(picks, [])

    def test_backtest_experiment_excludes_b1_single_entry_strategy(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)

        with patch("stock_server.service.ensure_quotes_for_backtest"):
            result = run_backtest_experiment(
                conn,
                BacktestRequest(start_date="2024-05-10", end_date="2024-05-10"),
            )

        strategy_ids = {item.strategy_id for item in result.items}
        self.assertIn("old_cat", strategy_ids)
        self.assertIn("old_cat_selection_aligned", strategy_ids)
        self.assertNotIn("b1", strategy_ids)


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
