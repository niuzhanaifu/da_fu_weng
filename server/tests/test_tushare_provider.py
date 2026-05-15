import unittest
from unittest.mock import patch

from stock_server.schemas import MarketBoard
from stock_server.tushare_provider import fetch_daily_quotes_for_date


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


if __name__ == "__main__":
    unittest.main()
