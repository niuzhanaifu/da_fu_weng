import unittest
from types import SimpleNamespace
from unittest.mock import patch

from stock_server.schemas import MarketBoard
from stock_server.tushare_provider import fetch_daily_quotes_for_date, fetch_daily_quotes_range


class TushareProviderTest(unittest.TestCase):
    def test_fetch_daily_quotes_for_date_maps_daily_close_and_vwap(self):
        basics = {"000001.SZ": {"name": "Ping An Bank", "industry": "Bank"}}

        def fake_call_tushare(token, api_name, params, fields):
            if api_name == "daily":
                return [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": "20240510",
                        "open": 10.1,
                        "high": 11.0,
                        "low": 10.0,
                        "close": 10.8,
                        "pre_close": 10.0,
                        "vol": 1000.0,
                        "amount": 1080.0,
                    }
                ]
            if api_name == "daily_basic":
                return [{"ts_code": "000001.SZ", "turnover_rate": 5.2, "volume_ratio": 2.1}]
            return []

        with patch("stock_server.tushare_provider.call_tushare", side_effect=fake_call_tushare):
            quotes = fetch_daily_quotes_for_date("token", basics, "20240510")

        self.assertEqual(len(quotes), 1)
        quote = quotes[0]
        self.assertEqual(quote.trade_date, "2024-05-10")
        self.assertEqual(quote.code, "000001")
        self.assertEqual(quote.board, MarketBoard.main)
        self.assertEqual(quote.close, 10.8)
        self.assertEqual(quote.minute_trades[0].price, 10.8)

    def test_fetch_daily_quotes_range_uses_qfq_prices(self):
        def fake_call_tushare(token, api_name, params, fields):
            if api_name == "stock_basic":
                return [{"ts_code": "000001.SZ", "symbol": "000001", "name": "Ping An Bank", "market": "主板", "industry": "Bank"}]
            if api_name == "trade_cal":
                return [
                    {"cal_date": "20240509", "is_open": "1"},
                    {"cal_date": "20240510", "is_open": "1"},
                ]
            if api_name == "daily":
                if params["trade_date"] == "20240509":
                    return [
                        {
                            "ts_code": "000001.SZ",
                            "trade_date": "20240509",
                            "open": 9.8,
                            "high": 10.2,
                            "low": 9.7,
                            "close": 10.0,
                            "pre_close": 9.5,
                            "vol": 1000.0,
                            "amount": 1000.0,
                        }
                    ]
                return [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": "20240510",
                        "open": 5.0,
                        "high": 5.8,
                        "low": 4.9,
                        "close": 5.5,
                        "pre_close": 10.0,
                        "vol": 1000.0,
                        "amount": 550.0,
                    }
                ]
            if api_name == "daily_basic":
                return [{"ts_code": "000001.SZ", "turnover_rate": 5.2, "volume_ratio": 2.1, "total_mv": 100000.0}]
            if api_name == "adj_factor":
                factor = 1.0 if params["trade_date"] == "20240509" else 2.0
                return [{"ts_code": "000001.SZ", "trade_date": params["trade_date"], "adj_factor": factor}]
            return []

        fake_settings = SimpleNamespace(tushare_token="token", tushare_timeout_seconds=30)
        with (
            patch("stock_server.tushare_provider.call_tushare", side_effect=fake_call_tushare),
            patch("stock_server.tushare_provider.settings", fake_settings),
        ):
            quotes = fetch_daily_quotes_range("2024-05-09", "2024-05-10")

        self.assertEqual([quote.trade_date for quote in quotes], ["2024-05-09", "2024-05-10"])
        self.assertAlmostEqual(quotes[0].open, 4.9)
        self.assertAlmostEqual(quotes[0].high, 5.1)
        self.assertAlmostEqual(quotes[0].low, 4.85)
        self.assertAlmostEqual(quotes[0].close, 5.0)
        self.assertAlmostEqual(quotes[0].previous_close, 4.75)
        self.assertAlmostEqual(quotes[0].minute_trades[0].price, 5.0)
        self.assertAlmostEqual(quotes[1].open, 5.0)
        self.assertAlmostEqual(quotes[1].close, 5.5)
        self.assertAlmostEqual(quotes[1].previous_close, 5.0)


if __name__ == "__main__":
    unittest.main()
