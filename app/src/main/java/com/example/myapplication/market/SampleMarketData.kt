package com.example.myapplication.market

object SampleMarketData {
    fun stockDays(): List<StockDay> = listOf(
        day(
            code = "600536",
            name = "中国软件",
            board = MarketBoard.Main,
            date = "2026-05-14",
            concept = "国产软件",
            previousClose = 42.10,
            close = 46.31,
            volumeRatio = 2.8,
            turnoverRate = 12.4,
            sealedAmountWan = 18300.0,
            minutes = listOf(43.2, 44.6, 45.1, 45.9, 46.31, 46.31, 46.31),
            nextOpen = 46.95,
            futureCloses = listOf(48.2, 49.6, 47.8, 50.1, 51.3)
        ),
        day(
            code = "601012",
            name = "隆基绿能",
            board = MarketBoard.Main,
            date = "2026-05-14",
            concept = "光伏设备",
            previousClose = 18.60,
            close = 20.46,
            volumeRatio = 2.1,
            turnoverRate = 6.8,
            sealedAmountWan = 9200.0,
            minutes = listOf(19.0, 19.6, 20.1, 20.46, 20.42, 20.46, 20.46),
            nextOpen = 20.30,
            futureCloses = listOf(20.0, 19.4, 19.1, 20.2, 20.7)
        ),
        day(
            code = "300750",
            name = "宁德时代",
            board = MarketBoard.ChiNext,
            date = "2026-05-14",
            concept = "动力电池",
            previousClose = 210.40,
            close = 252.48,
            volumeRatio = 2.4,
            turnoverRate = 8.2,
            sealedAmountWan = 12800.0,
            minutes = listOf(221.0, 230.4, 239.5, 246.0, 252.48, 251.9, 252.48),
            nextOpen = 256.00,
            futureCloses = listOf(261.2, 248.0, 241.5, 254.1, 266.4)
        ),
        day(
            code = "300308",
            name = "中际旭创",
            board = MarketBoard.ChiNext,
            date = "2026-05-14",
            concept = "光模块",
            previousClose = 101.20,
            close = 121.44,
            volumeRatio = 1.6,
            turnoverRate = 18.9,
            sealedAmountWan = 7600.0,
            minutes = listOf(108.0, 113.5, 118.2, 121.44, 120.8, 121.44, 121.44),
            nextOpen = 119.80,
            futureCloses = listOf(116.7, 112.9, 118.2, 121.0, 123.2)
        ),
        day(
            code = "000977",
            name = "浪潮信息",
            board = MarketBoard.Main,
            date = "2026-05-13",
            concept = "服务器",
            previousClose = 41.80,
            close = 45.98,
            volumeRatio = 3.2,
            turnoverRate = 16.1,
            sealedAmountWan = 21400.0,
            minutes = listOf(42.9, 43.7, 44.5, 45.2, 45.98, 45.98, 45.98),
            nextOpen = 46.50,
            futureCloses = listOf(47.8, 48.3, 46.4, 49.1, 50.0)
        ),
        day(
            code = "600519",
            name = "贵州茅台",
            board = MarketBoard.Main,
            date = "2026-05-13",
            concept = "白酒",
            previousClose = 1601.0,
            close = 1761.1,
            volumeRatio = 1.9,
            turnoverRate = 4.2,
            sealedAmountWan = 6100.0,
            minutes = listOf(1648.0, 1691.5, 1722.0, 1754.0, 1761.1, 1759.0, 1761.1),
            nextOpen = 1748.0,
            futureCloses = listOf(1722.4, 1698.0, 1715.5, 1738.2, 1768.0)
        ),
        day(
            code = "300033",
            name = "同花顺",
            board = MarketBoard.ChiNext,
            date = "2026-05-13",
            concept = "金融科技",
            previousClose = 72.40,
            close = 86.88,
            volumeRatio = 2.7,
            turnoverRate = 10.8,
            sealedAmountWan = 16400.0,
            minutes = listOf(76.8, 80.6, 83.4, 85.2, 86.88, 86.88, 86.88),
            nextOpen = 88.10,
            futureCloses = listOf(90.4, 92.0, 89.5, 93.8, 95.1)
        ),
        day(
            code = "002230",
            name = "科大讯飞",
            board = MarketBoard.Main,
            date = "2026-05-12",
            concept = "人工智能",
            previousClose = 47.30,
            close = 52.03,
            volumeRatio = 2.5,
            turnoverRate = 9.7,
            sealedAmountWan = 13400.0,
            minutes = listOf(48.6, 49.8, 50.5, 51.3, 52.03, 52.03, 52.03),
            nextOpen = 52.60,
            futureCloses = listOf(53.5, 55.0, 54.2, 56.4, 57.0)
        ),
        day(
            code = "300760",
            name = "迈瑞医疗",
            board = MarketBoard.ChiNext,
            date = "2026-05-12",
            concept = "医疗器械",
            previousClose = 61.80,
            close = 74.16,
            volumeRatio = 2.2,
            turnoverRate = 7.6,
            sealedAmountWan = 9800.0,
            minutes = listOf(65.2, 68.1, 70.6, 72.4, 74.16, 73.9, 74.16),
            nextOpen = 73.50,
            futureCloses = listOf(72.1, 70.8, 75.2, 76.0, 78.4)
        ),
        day(
            code = "600030",
            name = "中信证券",
            board = MarketBoard.Main,
            date = "2026-05-12",
            concept = "券商",
            previousClose = 22.90,
            close = 25.19,
            volumeRatio = 1.5,
            turnoverRate = 3.7,
            sealedAmountWan = 4200.0,
            minutes = listOf(23.4, 24.0, 24.6, 25.19, 25.0, 25.19, 25.19),
            nextOpen = 25.00,
            futureCloses = listOf(24.4, 23.8, 24.2, 25.1, 25.6)
        )
    )

    private fun day(
        code: String,
        name: String,
        board: MarketBoard,
        date: String,
        concept: String,
        previousClose: Double,
        close: Double,
        volumeRatio: Double,
        turnoverRate: Double,
        sealedAmountWan: Double,
        minutes: List<Double>,
        nextOpen: Double,
        futureCloses: List<Double>
    ): StockDay {
        val open = minutes.first()
        return StockDay(
            code = code,
            name = name,
            board = board,
            date = date,
            concept = concept,
            previousClose = previousClose,
            open = open,
            high = close,
            low = minutes.minOrNull() ?: close,
            close = close,
            volumeRatio = volumeRatio,
            turnoverRate = turnoverRate,
            sealedAmountWan = sealedAmountWan,
            minuteTrades = minutes.mapIndexed { index, price ->
                MinuteTrade(
                    minute = listOf("09:35", "10:00", "10:30", "11:00", "13:30", "14:30", "14:57")[index],
                    price = price,
                    volume = 900 + index * 180
                )
            },
            nextOpen = nextOpen,
            futureCloses = futureCloses,
            dailyCandles = buildCandles(date, previousClose, open, close, futureCloses)
        )
    }

    private fun buildCandles(
        date: String,
        previousClose: Double,
        open: Double,
        close: Double,
        futureCloses: List<Double>
    ): List<DailyCandle> {
        val closes = listOf(
            previousClose * 0.94,
            previousClose * 0.97,
            previousClose * 1.01,
            previousClose,
            close
        ) + futureCloses
        return closes.mapIndexed { index, itemClose ->
            val itemOpen = if (index == 4) open else itemClose * (if (index % 2 == 0) 0.985 else 1.012)
            val high = maxOf(itemOpen, itemClose) * 1.018
            val low = minOf(itemOpen, itemClose) * 0.982
            DailyCandle(
                date = if (index == 4) date else "T${index - 4}",
                open = itemOpen,
                high = high,
                low = low,
                close = itemClose
            )
        }
    }
}
