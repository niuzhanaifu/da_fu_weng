package com.example.myapplication.market

import kotlin.math.max
import kotlin.math.min

enum class MarketBoard(val label: String, val limitUpRate: Double) {
    Main("主板", 0.10),
    ChiNext("创业板", 0.20)
}

data class MinuteTrade(
    val minute: String,
    val price: Double,
    val volume: Int
)

data class DailyCandle(
    val date: String,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double
)

data class StockDay(
    val code: String,
    val name: String,
    val board: MarketBoard,
    val date: String,
    val concept: String,
    val previousClose: Double,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volumeRatio: Double,
    val turnoverRate: Double,
    val sealedAmountWan: Double,
    val minuteTrades: List<MinuteTrade>,
    val nextOpen: Double,
    val futureCloses: List<Double>,
    val dailyCandles: List<DailyCandle>
) {
    val changePercent: Double
        get() = ((close - previousClose) / previousClose) * 100.0
}

data class IndicatorOption(
    val id: String,
    val name: String,
    val description: String
)

data class StockPick(
    val code: String,
    val name: String,
    val board: MarketBoard,
    val date: String,
    val concept: String,
    val close: Double,
    val changePercent: Double,
    val volumeRatio: Double,
    val turnoverRate: Double,
    val sealedAmountWan: Double,
    val stopLossPrice: Double,
    val limitShape: String = "",
    val limitShapeLabel: String = "",
    val latestTradeDate: String? = null,
    val latestClose: Double? = null,
    val minuteTrades: List<MinuteTrade>,
    val nextOpen: Double,
    val futureCloses: List<Double>,
    val dailyCandles: List<DailyCandle>
)

data class DailyPickGroup(
    val date: String,
    val picks: List<StockPick>
) {
    val mainCount: Int = picks.count { it.board == MarketBoard.Main }
    val chiNextCount: Int = picks.count { it.board == MarketBoard.ChiNext }
    val averageStopLoss: Double = picks.map { it.stopLossPrice }.averageOrZero()
}

enum class SelectionStrategy(
    val id: String,
    val title: String,
    val description: String
) {
    OldCatBuy(
        id = "old_cat_buy",
        title = "老猫买入",
        description = "T+1 收盘后回看上一交易日首板早上封板、非 ST、非一字板候选，按 T+1 涨幅筛出待观察标的。"
    ),
    FirstLimitUp(
        id = "limit_up_first",
        title = "首板涨停",
        description = "选择当日涨停的非连板股票，标注涨停类型与分时均线止损。"
    )
}

data class BacktestTrade(
    val code: String,
    val name: String,
    val board: MarketBoard,
    val buyDate: String,
    val sellDate: String,
    val buyPrice: Double,
    val sellPrice: Double,
    val shares: Int = 0,
    val positionAmount: Double = 0.0,
    val profitAmount: Double = 0.0,
    val stopLossPrice: Double,
    val returnPercent: Double,
    val exitReason: String
)

data class EquityPoint(
    val date: String,
    val capital: Double
)

data class BacktestResult(
    val initialCapital: Double = 0.0,
    val finalCapital: Double = 0.0,
    val totalTrades: Int,
    val winRate: Double,
    val totalReturnPercent: Double,
    val maxDrawdownPercent: Double,
    val trades: List<BacktestTrade>,
    val equityCurve: List<EquityPoint> = emptyList()
)

data class BacktestHistoryEntry(
    val id: String,
    val createdAt: String,
    val strategyId: String,
    val strategyName: String,
    val startDate: String,
    val endDate: String,
    val holdingDays: Int,
    val initialCapital: Double,
    val board: MarketBoard?,
    val result: BacktestResult
)

data class BacktestExperimentItem(
    val strategyId: String,
    val strategyName: String,
    val description: String,
    val result: BacktestResult
)

data class BacktestExperimentResult(
    val items: List<BacktestExperimentItem>
)

data class TradePosition(
    val id: Int,
    val code: String,
    val name: String,
    val board: MarketBoard,
    val sourceTradeDate: String,
    val buyDate: String,
    val buyPrice: Double,
    val buyShares: Int,
    val stopLossPrice: Double,
    val latestTradeDate: String?,
    val latestClose: Double?,
    val stopLossLossPercent: Double,
    val unrealizedProfitAmount: Double,
    val unrealizedProfitPercent: Double,
    val status: String,
    val sellSignal: Boolean,
    val sellDate: String?,
    val sellPrice: Double?,
    val sellShares: Int?,
    val profitAmount: Double?
)

data class TradeStats(
    val holdingCount: Int,
    val totalTrades: Int,
    val winRate: Double,
    val totalProfitAmount: Double
)

data class TradeBook(
    val openPositions: List<TradePosition>,
    val history: List<TradePosition>,
    val stats: TradeStats
)

enum class BacktestStrategy(
    val id: String,
    val title: String,
    val description: String
) {
    OldCat(
        id = "old_cat",
        title = "老猫战法",
        description = "只做首板且早上封板，排除 ST 和一字板；涨停日后第 2 个交易日开盘若相对涨停日收盘价涨幅不超过 5% 则买入；触及分时均线止损线时按收盘价卖出，止盈率可设置。"
    ),
    B1(
        id = "b1",
        title = "B1 战法",
        description = "J<13，收盘价贴近知行短期线或多空线，明显缩量且日线呈 N 型上涨结构；排除 ST 和市值小于 50 亿标的。"
    )
}

object IndicatorCatalog {
    val options = listOf(
        IndicatorOption(
            id = "volume",
            name = "量比放大",
            description = "量比大于 1.8，过滤成交活跃度不足的涨停。"
        ),
        IndicatorOption(
            id = "seal",
            name = "封单强度",
            description = "封单金额不低于 5000 万，保留封板更稳定的标的。"
        ),
        IndicatorOption(
            id = "turnover",
            name = "换手确认",
            description = "换手率位于 4% 到 28%，避开极端缩量或过度分歧。"
        ),
        IndicatorOption(
            id = "close",
            name = "收盘强势",
            description = "收盘价贴近最高价，确认尾盘没有明显开板回落。"
        )
    )
}

object StockSelectionEngine {
    fun selectDailyGroups(
        history: List<StockDay>,
        enabledIndicatorIds: Set<String>
    ): List<DailyPickGroup> {
        return history
            .filter { it.board == MarketBoard.Main || it.board == MarketBoard.ChiNext }
            .filter { it.isLimitUp() }
            .filter { it.matchesIndicators(enabledIndicatorIds) }
            .groupBy { it.date }
            .map { (date, days) ->
                DailyPickGroup(
                    date = date,
                    picks = days.sortedWith(compareBy<StockDay> { it.board.ordinal }.thenByDescending { it.sealedAmountWan })
                        .map { it.toPick() }
                )
            }
            .sortedByDescending { it.date }
    }

    private fun StockDay.toPick(): StockPick {
        return StockPick(
            code = code,
            name = name,
            board = board,
            date = date,
            concept = concept,
            close = close,
            changePercent = changePercent,
            volumeRatio = volumeRatio,
            turnoverRate = turnoverRate,
            sealedAmountWan = sealedAmountWan,
            stopLossPrice = minuteTrades.vwapOrAverage(),
            minuteTrades = minuteTrades,
            nextOpen = nextOpen,
            futureCloses = futureCloses,
            dailyCandles = dailyCandles
        )
    }

    private fun StockDay.isLimitUp(): Boolean {
        val expected = previousClose * (1.0 + board.limitUpRate)
        return close >= expected - 0.02 && close >= high - 0.02
    }

    private fun StockDay.matchesIndicators(ids: Set<String>): Boolean {
        return ids.all { id ->
            when (id) {
                "volume" -> volumeRatio >= 1.8
                "seal" -> sealedAmountWan >= 5000.0
                "turnover" -> turnoverRate in 4.0..28.0
                "close" -> close >= high * 0.995
                else -> true
            }
        }
    }
}

object BacktestEngine {
    fun run(
        groups: List<DailyPickGroup>,
        holdingDays: Int,
        strategy: BacktestStrategy = BacktestStrategy.OldCat,
        startDate: String? = null,
        endDate: String? = null
    ): BacktestResult {
        val filteredGroups = groups.filter { group ->
            (startDate == null || group.date >= startDate) &&
                (endDate == null || group.date <= endDate)
        }
        val trades = filteredGroups
            .flatMap { group -> group.picks.map { group.date to it } }
            .filter { (_, pick) -> pick.nextOpen <= pick.close * 1.03 }
            .map { (date, pick) -> simulateTrade(date, pick, holdingDays, strategy) }

        if (trades.isEmpty()) {
            return BacktestResult(
                totalTrades = 0,
                winRate = 0.0,
                totalReturnPercent = 0.0,
                maxDrawdownPercent = 0.0,
                trades = emptyList()
            )
        }

        var equity = 1.0
        var peak = 1.0
        var maxDrawdown = 0.0
        trades.forEach { trade ->
            equity *= 1.0 + trade.returnPercent / 100.0
            peak = max(peak, equity)
            maxDrawdown = max(maxDrawdown, (peak - equity) / peak * 100.0)
        }

        return BacktestResult(
            totalTrades = trades.size,
            winRate = trades.count { it.returnPercent > 0.0 }.toDouble() / trades.size * 100.0,
            totalReturnPercent = (equity - 1.0) * 100.0,
            maxDrawdownPercent = maxDrawdown,
            trades = trades.sortedByDescending { it.buyDate }
        )
    }

    private fun simulateTrade(
        buyDate: String,
        pick: StockPick,
        holdingDays: Int,
        strategy: BacktestStrategy
    ): BacktestTrade {
        val buyPrice = pick.nextOpen
        val stopLossPrice = pick.stopLossPrice
        val closes = pick.futureCloses.take(max(1, holdingDays))
        var sellPrice = closes.lastOrNull() ?: pick.close
        var sellIndex = min(max(1, holdingDays), max(1, pick.futureCloses.size)) - 1
        var reason = "${strategy.title}：持有到期"

        closes.forEachIndexed { index, close ->
            if (reason.endsWith("持有到期") && close <= stopLossPrice) {
                sellPrice = close
                sellIndex = index
                reason = "${strategy.title}：分时均价止损"
            }
        }

        val returnPercent = (sellPrice - buyPrice) / buyPrice * 100.0
        return BacktestTrade(
            code = pick.code,
            name = pick.name,
            board = pick.board,
            buyDate = buyDate,
            sellDate = "T+${sellIndex + 1}",
            buyPrice = buyPrice,
            sellPrice = sellPrice,
            stopLossPrice = stopLossPrice,
            returnPercent = returnPercent,
            exitReason = reason
        )
    }
}

fun Double.asPrice(): String = String.format("%.2f", this)

fun Double.asPercent(): String = String.format("%.2f%%", this)

private fun List<Double>.averageOrZero(): Double {
    return if (isEmpty()) 0.0 else average()
}

private fun List<MinuteTrade>.vwapOrAverage(): Double {
    if (isEmpty()) return 0.0
    val totalVolume = sumOf { it.volume }
    return if (totalVolume > 0) {
        sumOf { it.price * it.volume } / totalVolume
    } else {
        map { it.price }.average()
    }
}
