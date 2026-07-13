import random
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from stock_server import repository
from stock_server.backtest import run_backtest
from stock_server.schemas import BacktestRequest, DailyQuoteIn, MarketBoard, MinuteTrade, StockPickOut
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

    def test_ultra_short_requires_previous_day_macd_green_before_turning_red(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema(conn)
        dates = date_strings("2024-01-01", 130)
        repository.upsert_daily_quotes(conn, ultra_short_quotes_with_positive_previous_macd(dates))

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

    def test_ultra_short_buy_day_stop_loss_sells_next_trading_day_open(self):
        pick = stock_pick(
            future_opens=[10.0, 9.7, 9.5],
            future_highs=[10.2, 9.9, 9.8],
            future_lows=[9.8, 9.4, 9.3],
            future_closes=[9.9, 9.5, 9.4],
        )

        result = run_backtest(
            [pick],
            holding_days=3,
            take_profit_percent=10.0,
            strategy_id="ultra_short",
        )

        self.assertEqual(result.total_trades, 1)
        trade = result.trades[0]
        self.assertEqual(trade.buy_date, "2024-05-13")
        self.assertEqual(trade.sell_date, "2024-05-14")
        self.assertEqual(trade.sell_price, 9.7)
        self.assertEqual(trade.stop_loss_price, 10.0)
        self.assertIn("次交易日止损", trade.exit_reason)

    def test_ultra_short_ignores_buy_day_take_profit_signal(self):
        pick = stock_pick(
            future_opens=[10.0, 10.2, 10.1],
            future_highs=[11.3, 10.6, 10.4],
            future_lows=[10.0, 10.0, 10.0],
            future_closes=[10.8, 10.4, 10.2],
        )

        result = run_backtest(
            [pick],
            holding_days=3,
            take_profit_percent=10.0,
            strategy_id="ultra_short",
        )

        self.assertEqual(result.total_trades, 1)
        trade = result.trades[0]
        self.assertEqual(trade.buy_date, "2024-05-13")
        self.assertEqual(trade.sell_date, "2024-05-15")
        self.assertEqual(trade.sell_price, 10.2)
        self.assertIn("持有3个交易日", trade.exit_reason)


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
            if index == 122:
                low = open_price
            volume = random_source.randint(900, 1800)
            turnover_rate = 2.0
        quotes.append(quote(trade_date, previous_close, open_price, high, low, close, volume, turnover_rate))
        previous_close = close
    return quotes


def ultra_short_quotes_with_positive_previous_macd(dates: list[str]) -> list[DailyQuoteIn]:
    quotes = ultra_short_quotes(dates)
    previous = quotes[120]
    close = previous.previous_close
    quotes[120] = previous.model_copy(
        update={
            "open": previous.previous_close,
            "high": previous.previous_close * 1.01,
            "low": previous.previous_close * 0.99,
            "close": close,
        }
    )
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


def stock_pick(
    future_opens: list[float],
    future_highs: list[float],
    future_lows: list[float],
    future_closes: list[float],
) -> StockPickOut:
    return StockPickOut(
        trade_date="2024-05-10",
        code="600001",
        name="Sample Equity",
        board=MarketBoard.main,
        board_label="主板",
        concept="",
        close=9.8,
        change_percent=0.0,
        volume_ratio=0.1,
        turnover_rate=2.0,
        total_mv_wan=100000.0,
        sealed_amount_wan=0.0,
        stop_loss_price=0.0,
        next_open=future_opens[0],
        future_closes=future_closes,
        future_highs=future_highs,
        future_lows=future_lows,
        future_opens=future_opens,
        future_dates=["2024-05-13", "2024-05-14", "2024-05-15"],
        recent_3day_change_percent=0.0,
        recent_5day_change_percent=0.0,
        minute_trades=[],
    )


def date_strings(start_date: str, count: int) -> list[str]:
    current = datetime.strptime(start_date, "%Y-%m-%d")
    return [(current + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(count)]


if __name__ == "__main__":
    unittest.main()
