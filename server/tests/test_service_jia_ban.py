import sqlite3
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from stock_server.backtest import RANK_MODE_STOP_LOSS_LOSS, run_backtest
from stock_server.schemas import BacktestRequest, DailyQuoteIn, MarketBoard, StockPickOut
from stock_server.service import BACKTEST_PROFILES, build_backtest_picks, run_backtest_experiment


class JiaBanBacktestTest(unittest.TestCase):
    def test_jia_ban_selector_keeps_bottom_line_candidate(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        rows = sandwich_history("600000")
        rows.extend(
            [
                quote("2024-05-01", previous_close=10.6, open_price=10.4, high=10.4, low=10.0, close=10.1),
                quote("2024-05-02", previous_close=10.1, open_price=10.2, high=10.5, low=10.1, close=10.3),
                quote("2024-05-03", previous_close=10.3, open_price=10.4, high=11.1, low=10.2, close=10.9),
                quote("2024-05-06", previous_close=10.9, open_price=10.8, high=10.9, low=10.5, close=10.7),
            ]
        )
        from stock_server import repository

        repository.upsert_daily_quotes(conn, rows)

        picks = build_backtest_picks(
            conn,
            start_date="2024-05-01",
            end_date="2024-05-01",
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["jia_ban"],
        )

        self.assertEqual([pick.code for pick in picks], ["600000"])
        self.assertEqual(picks[0].limit_shape, "jia_ban")
        self.assertEqual(picks[0].stop_loss_price, 10.0)

    def test_jia_ban_selector_filters_t_day_drop_over_7_percent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        rows = sandwich_history("600000")
        rows.append(quote("2024-05-01", previous_close=11.0, open_price=10.5, high=10.5, low=10.0, close=10.1))
        from stock_server import repository

        repository.upsert_daily_quotes(conn, rows)

        picks = build_backtest_picks(
            conn,
            start_date="2024-05-01",
            end_date="2024-05-01",
            indicator_ids=[],
            holding_days=3,
            profile=BACKTEST_PROFILES["jia_ban"],
        )

        self.assertEqual(picks, [])

    def test_jia_ban_strategy_uses_requested_take_profit_percent(self):
        result = run_backtest(
            picks=[
                stock_pick(
                    "600000",
                    stop_loss_price=10.0,
                    future_opens=[10.2, 10.4, 10.8],
                    future_highs=[10.5, 11.1, 10.9],
                    future_lows=[10.1, 10.2, 10.5],
                    future_closes=[10.4, 10.9, 10.7],
                )
            ],
            holding_days=3,
            take_profit_percent=6.0,
            strategy_id="jia_ban",
        )

        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.trades[0].sell_date, "2024-03-05")
        self.assertAlmostEqual(result.trades[0].sell_price, 10.2 * 1.06)
        self.assertIn("6%", result.trades[0].exit_reason)

    def test_jia_ban_strategy_uses_close_when_stop_price_above_day_high(self):
        result = run_backtest(
            picks=[
                stock_pick(
                    "600000",
                    stop_loss_price=10.0,
                    future_opens=[10.2, 10.1, 10.0],
                    future_highs=[10.4, 9.9, 10.1],
                    future_lows=[10.1, 9.6, 9.8],
                    future_closes=[10.3, 9.7, 10.0],
                )
            ],
            holding_days=3,
            take_profit_percent=50.0,
            strategy_id="jia_ban",
        )

        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.trades[0].sell_date, "2024-03-05")
        self.assertEqual(result.trades[0].sell_price, 9.7)
        self.assertIn("收盘价", result.trades[0].exit_reason)

    def test_jia_ban_strategy_does_not_stop_loss_on_buy_day(self):
        result = run_backtest(
            picks=[
                stock_pick(
                    "600000",
                    stop_loss_price=10.0,
                    future_opens=[10.2, 10.2, 10.3],
                    future_highs=[10.4, 10.4, 10.5],
                    future_lows=[9.5, 10.1, 9.6],
                    future_closes=[10.3, 10.2, 10.4],
                )
            ],
            holding_days=3,
            take_profit_percent=50.0,
            strategy_id="jia_ban",
        )

        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.trades[0].sell_date, "2024-03-06")
        self.assertEqual(result.trades[0].sell_price, 10.4)
        self.assertIn("持有3个交易日", result.trades[0].exit_reason)

    def test_jia_ban_strategy_uses_requested_holding_days(self):
        result = run_backtest(
            picks=[
                stock_pick(
                    "600000",
                    stop_loss_price=10.0,
                    future_opens=[10.2, 10.2, 10.3, 10.4],
                    future_highs=[10.4, 10.5, 10.6, 10.7],
                    future_lows=[10.1, 10.1, 10.1, 10.1],
                    future_closes=[10.3, 10.4, 10.5, 10.6],
                    future_dates=["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07"],
                )
            ],
            holding_days=4,
            take_profit_percent=50.0,
            strategy_id="jia_ban",
        )

        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.trades[0].sell_date, "2024-03-07")
        self.assertEqual(result.trades[0].sell_price, 10.6)
        self.assertIn("持有4个交易日", result.trades[0].exit_reason)

    def test_jia_ban_ranks_by_lowest_stop_loss_loss_and_caps_to_three(self):
        picks = [
            stock_pick("600000", stop_loss_price=9.8),
            stock_pick("600001", stop_loss_price=9.5),
            stock_pick("600002", stop_loss_price=9.7),
            stock_pick("600003", stop_loss_price=9.0),
        ]

        result = run_backtest(
            picks=picks,
            holding_days=3,
            take_profit_percent=50.0,
            strategy_id="jia_ban",
            max_positions_per_day=3,
            rank_mode=RANK_MODE_STOP_LOSS_LOSS,
        )

        self.assertEqual(result.total_trades, 3)
        self.assertEqual({trade.code for trade in result.trades}, {"600000", "600001", "600002"})

    def test_backtest_experiment_includes_jia_ban(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)

        with patch("stock_server.service.ensure_quotes_for_backtest"):
            result = run_backtest_experiment(
                conn,
                BacktestRequest(start_date="2024-03-01", end_date="2024-03-01"),
            )

        self.assertIn("jia_ban", {item.strategy_id for item in result.items})


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


def sandwich_history(code: str) -> list[DailyQuoteIn]:
    start = date(2024, 1, 1)
    rows: list[DailyQuoteIn] = []
    for index in range(120):
        trade_date = (start + timedelta(days=index)).isoformat()
        high = 12.0 if index in (10, 90) else 11.4
        low = 10.0 if index in (5, 80) else 10.3
        rows.append(
            quote(
                trade_date,
                previous_close=11.0,
                open_price=11.0,
                high=high,
                low=low,
                close=11.0,
                code=code,
            )
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
        minute_trades=[],
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
        trade_date="2024-03-01",
        code=code,
        name=f"Sample {code}",
        board=MarketBoard.main,
        board_label=MarketBoard.main.label,
        concept="",
        close=10.1,
        change_percent=-3.0,
        volume_ratio=1.0,
        turnover_rate=10.0,
        total_mv_wan=100000.0,
        sealed_amount_wan=0.0,
        stop_loss_price=stop_loss_price,
        limit_shape="jia_ban",
        limit_shape_label="夹板战法",
        latest_trade_date=None,
        latest_close=None,
        next_open=10.2,
        future_closes=future_closes or [10.1, 10.2, 10.3],
        future_highs=future_highs or [10.3, 10.4, 10.5],
        future_lows=future_lows or [10.1, 10.1, 10.1],
        future_opens=future_opens or [10.0, 10.1, 10.2],
        future_dates=future_dates or ["2024-03-04", "2024-03-05", "2024-03-06"],
        recent_3day_change_percent=0.0,
        recent_5day_change_percent=0.0,
        minute_trades=[],
    )


if __name__ == "__main__":
    unittest.main()
