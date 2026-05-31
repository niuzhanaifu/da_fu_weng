import sqlite3
import unittest
from unittest.mock import patch

from stock_server.backtest import RANK_MODE_STOP_LOSS_LOSS, run_backtest
from stock_server.schemas import BacktestRequest, DailyQuoteIn, MarketBoard, MinuteTrade, StockPickOut
from stock_server.service import BACKTEST_PROFILES, build_backtest_picks, run_backtest_experiment


class OldCatLimit2BacktestTest(unittest.TestCase):
    def test_selector_keeps_second_board_signal(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        from stock_server import repository

        repository.upsert_daily_quotes(conn, limit2_pattern_rows())

        picks = build_backtest_picks(
            conn,
            start_date="2024-03-11",
            end_date="2024-03-11",
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["old_cat_limit2"],
        )

        self.assertEqual([pick.code for pick in picks], ["600000"])
        self.assertEqual(picks[0].trade_date, "2024-03-11")
        self.assertEqual(picks[0].limit_shape, "old_cat_limit2")
        self.assertEqual(picks[0].stop_loss_price, 10.2)

    def test_selector_filters_pullback_below_first_open(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        rows = limit2_pattern_rows()
        rows[6] = quote("2024-03-07", 11.0, 10.7, 10.9, 10.1, 10.7, volume=1200)
        from stock_server import repository

        repository.upsert_daily_quotes(conn, rows)

        picks = build_backtest_picks(
            conn,
            start_date="2024-03-11",
            end_date="2024-03-11",
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["old_cat_limit2"],
        )

        self.assertEqual(picks, [])

    def test_selector_requires_continuous_pullback_shrinking_volume(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        rows = limit2_pattern_rows()
        rows[7] = quote("2024-03-08", 10.7, 10.6, 10.9, 10.3, 10.5, volume=1300)
        from stock_server import repository

        repository.upsert_daily_quotes(conn, rows)

        picks = build_backtest_picks(
            conn,
            start_date="2024-03-11",
            end_date="2024-03-11",
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["old_cat_limit2"],
        )

        self.assertEqual(picks, [])

    def test_selector_requires_second_board_volume_breakout(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        rows = limit2_pattern_rows()
        rows[8] = quote("2024-03-11", 10.5, 10.8, 11.55, 10.8, 11.55, volume=800)
        from stock_server import repository

        repository.upsert_daily_quotes(conn, rows)

        picks = build_backtest_picks(
            conn,
            start_date="2024-03-11",
            end_date="2024-03-11",
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["old_cat_limit2"],
        )

        self.assertEqual(picks, [])

    def test_strategy_uses_requested_take_profit_percent(self):
        result = run_backtest(
            picks=[
                stock_pick(
                    "600000",
                    stop_loss_price=10.2,
                    future_opens=[11.6, 11.7, 11.8],
                    future_highs=[12.6, 12.7, 12.8],
                    future_lows=[11.4, 11.5, 11.6],
                    future_closes=[12.2, 12.3, 12.4],
                )
            ],
            holding_days=3,
            take_profit_percent=8.0,
            strategy_id="old_cat_limit2",
        )

        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.trades[0].sell_date, "2024-03-12")
        self.assertAlmostEqual(result.trades[0].sell_price, 11.6 * 1.08)

    def test_strategy_stops_at_close_when_first_open_breaks(self):
        result = run_backtest(
            picks=[
                stock_pick(
                    "600000",
                    stop_loss_price=10.2,
                    future_opens=[11.6, 11.0, 10.5],
                    future_highs=[11.8, 11.2, 10.7],
                    future_lows=[11.4, 10.1, 10.3],
                    future_closes=[11.5, 10.0, 10.4],
                )
            ],
            holding_days=3,
            take_profit_percent=50.0,
            strategy_id="old_cat_limit2",
        )

        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.trades[0].sell_date, "2024-03-13")
        self.assertEqual(result.trades[0].sell_price, 10.0)

    def test_strategy_ranks_by_lowest_stop_loss_loss_and_caps_to_three(self):
        picks = [
            stock_pick("600000", stop_loss_price=10.8),
            stock_pick("600001", stop_loss_price=10.7),
            stock_pick("600002", stop_loss_price=10.6),
            stock_pick("600003", stop_loss_price=9.0),
        ]

        result = run_backtest(
            picks=picks,
            holding_days=3,
            take_profit_percent=50.0,
            strategy_id="old_cat_limit2",
            max_positions_per_day=3,
            rank_mode=RANK_MODE_STOP_LOSS_LOSS,
        )

        self.assertEqual(result.total_trades, 3)
        self.assertEqual({trade.code for trade in result.trades}, {"600000", "600001", "600002"})

    def test_backtest_experiment_includes_old_cat_limit2(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)

        with patch("stock_server.service.ensure_quotes_for_backtest"):
            result = run_backtest_experiment(
                conn,
                BacktestRequest(start_date="2024-03-01", end_date="2024-03-01"),
            )

        self.assertIn("old_cat_limit2", {item.strategy_id for item in result.items})


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


def limit2_pattern_rows() -> list[DailyQuoteIn]:
    rows = [
        quote("2024-02-28", 9.9, 10.0, 10.2, 9.9, 10.0, volume=1000),
        quote("2024-02-29", 10.0, 10.0, 10.2, 9.9, 10.0, volume=1000),
        quote("2024-03-01", 10.0, 10.0, 10.2, 9.9, 10.0, volume=1000),
        quote("2024-03-04", 10.0, 10.0, 10.2, 9.9, 10.0, volume=1000),
        quote("2024-03-05", 10.0, 10.0, 10.2, 9.9, 10.0, volume=1000),
        quote("2024-03-06", 10.0, 10.2, 11.0, 10.2, 11.0, volume=2000),
    ]
    rows.extend(
        [
            quote("2024-03-07", 11.0, 10.8, 10.95, 10.35, 10.7, volume=1200),
            quote("2024-03-08", 10.7, 10.6, 10.9, 10.3, 10.5, volume=900),
            quote("2024-03-11", 10.5, 10.8, 11.55, 10.8, 11.55, volume=1300),
            quote("2024-03-12", 11.55, 11.6, 12.4, 11.4, 12.2, volume=1800),
            quote("2024-03-13", 12.2, 12.3, 12.5, 12.0, 12.4, volume=1600),
            quote("2024-03-14", 12.4, 12.4, 12.6, 12.1, 12.3, volume=1500),
        ]
    )
    return rows


def quote(
    trade_date: str,
    previous_close: float,
    open_price: float,
    high: float,
    low: float,
    close: float,
    code: str = "600000",
    volume: int = 1000,
) -> DailyQuoteIn:
    return DailyQuoteIn(
        trade_date=trade_date,
        code=code,
        name="Sample Equity",
        board=MarketBoard.main,
        previous_close=previous_close,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume_ratio=1.0,
        turnover_rate=10.0,
        total_mv_wan=100000.0,
        sealed_amount_wan=0.0,
        minute_trades=[MinuteTrade(minute="daily", price=close, volume=volume)],
    )


def stock_pick(
    code: str,
    stop_loss_price: float,
    future_opens: list[float] | None = None,
    future_highs: list[float] | None = None,
    future_lows: list[float] | None = None,
    future_closes: list[float] | None = None,
    future_dates: list[str] | None = None,
) -> StockPickOut:
    return StockPickOut(
        trade_date="2024-03-11",
        code=code,
        name=f"Sample {code}",
        board=MarketBoard.main,
        board_label=MarketBoard.main.label,
        concept="",
        close=11.55,
        change_percent=10.0,
        volume_ratio=1.0,
        turnover_rate=10.0,
        total_mv_wan=100000.0,
        sealed_amount_wan=0.0,
        stop_loss_price=stop_loss_price,
        limit_shape="old_cat_limit2",
        limit_shape_label="老猫涨停2对比",
        latest_trade_date=None,
        latest_close=None,
        next_open=11.6,
        future_closes=future_closes or [11.7, 11.8, 11.9],
        future_highs=future_highs or [11.8, 11.9, 12.0],
        future_lows=future_lows or [11.5, 11.6, 11.7],
        future_opens=future_opens or [11.6, 11.7, 11.8],
        future_dates=future_dates or ["2024-03-12", "2024-03-13", "2024-03-14"],
        recent_3day_change_percent=0.0,
        recent_5day_change_percent=0.0,
        minute_trades=[],
    )


if __name__ == "__main__":
    unittest.main()
