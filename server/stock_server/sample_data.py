from __future__ import annotations

from .schemas import DailyQuoteIn, MarketBoard, MinuteTrade


def sample_quotes() -> list[DailyQuoteIn]:
    return [
        _quote("2026-05-14", "600536", "中国软件", MarketBoard.main, "国产软件", 42.10, 46.31, 2.8, 12.4, 18300, [43.2, 44.6, 45.1, 45.9, 46.31, 46.31, 46.31], 46.95, [48.2, 49.6, 47.8, 50.1, 51.3]),
        _quote("2026-05-14", "601012", "隆基绿能", MarketBoard.main, "光伏设备", 18.60, 20.46, 2.1, 6.8, 9200, [19.0, 19.6, 20.1, 20.46, 20.42, 20.46, 20.46], 20.30, [20.0, 19.4, 19.1, 20.2, 20.7]),
        _quote("2026-05-14", "300750", "宁德时代", MarketBoard.chinext, "动力电池", 210.40, 252.48, 2.4, 8.2, 12800, [221.0, 230.4, 239.5, 246.0, 252.48, 251.9, 252.48], 256.0, [261.2, 248.0, 241.5, 254.1, 266.4]),
        _quote("2026-05-13", "000977", "浪潮信息", MarketBoard.main, "服务器", 41.80, 45.98, 3.2, 16.1, 21400, [42.9, 43.7, 44.5, 45.2, 45.98, 45.98, 45.98], 46.50, [47.8, 48.3, 46.4, 49.1, 50.0]),
        _quote("2026-05-13", "300033", "同花顺", MarketBoard.chinext, "金融科技", 72.40, 86.88, 2.7, 10.8, 16400, [76.8, 80.6, 83.4, 85.2, 86.88, 86.88, 86.88], 88.10, [90.4, 92.0, 89.5, 93.8, 95.1]),
        _quote("2026-05-12", "002230", "科大讯飞", MarketBoard.main, "人工智能", 47.30, 52.03, 2.5, 9.7, 13400, [48.6, 49.8, 50.5, 51.3, 52.03, 52.03, 52.03], 52.60, [53.5, 55.0, 54.2, 56.4, 57.0]),
        _quote("2026-05-12", "300760", "迈瑞医疗", MarketBoard.chinext, "医疗器械", 61.80, 74.16, 2.2, 7.6, 9800, [65.2, 68.1, 70.6, 72.4, 74.16, 73.9, 74.16], 73.50, [72.1, 70.8, 75.2, 76.0, 78.4]),
    ]


def _quote(
    trade_date: str,
    code: str,
    name: str,
    board: MarketBoard,
    concept: str,
    previous_close: float,
    close: float,
    volume_ratio: float,
    turnover_rate: float,
    sealed_amount_wan: float,
    minute_prices: list[float],
    next_open: float,
    future_closes: list[float],
) -> DailyQuoteIn:
    minutes = ["09:35", "10:00", "10:30", "11:00", "13:30", "14:30", "14:57"]
    return DailyQuoteIn(
        trade_date=trade_date,
        code=code,
        name=name,
        board=board,
        concept=concept,
        previous_close=previous_close,
        open=minute_prices[0],
        high=close,
        low=min(minute_prices),
        close=close,
        volume_ratio=volume_ratio,
        turnover_rate=turnover_rate,
        sealed_amount_wan=sealed_amount_wan,
        next_open=next_open,
        future_closes=future_closes,
        minute_trades=[
            MinuteTrade(minute=minutes[index], price=price, volume=900 + index * 180)
            for index, price in enumerate(minute_prices)
        ],
    )
