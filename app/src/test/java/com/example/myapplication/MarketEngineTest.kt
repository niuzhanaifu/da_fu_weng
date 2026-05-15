package com.example.myapplication

import com.example.myapplication.market.BacktestEngine
import com.example.myapplication.market.BacktestStrategy
import com.example.myapplication.market.SampleMarketData
import com.example.myapplication.market.StockSelectionEngine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MarketEngineTest {
    @Test
    fun selectorGroupsLimitUpStocksByDate() {
        val groups = StockSelectionEngine.selectDailyGroups(
            history = SampleMarketData.stockDays(),
            enabledIndicatorIds = setOf("volume", "seal", "close")
        )

        assertEquals("2026-05-14", groups.first().date)
        assertTrue(groups.all { it.picks.isNotEmpty() })
        assertTrue(groups.first().picks.any { it.code == "600536" })
    }

    @Test
    fun backtestProducesTradesAndRiskMetrics() {
        val groups = StockSelectionEngine.selectDailyGroups(
            history = SampleMarketData.stockDays(),
            enabledIndicatorIds = setOf("volume", "seal", "close")
        )
        val result = BacktestEngine.run(
            groups = groups,
            holdingDays = 3
        )

        assertTrue(result.totalTrades > 0)
        assertEquals(result.totalTrades, result.trades.size)
        assertTrue(result.maxDrawdownPercent >= 0.0)
    }

    @Test
    fun backtestUsesOldCatStrategy() {
        val groups = StockSelectionEngine.selectDailyGroups(
            history = SampleMarketData.stockDays(),
            enabledIndicatorIds = setOf("volume", "seal", "close")
        )
        val result = BacktestEngine.run(
            groups = groups,
            holdingDays = 3,
            strategy = BacktestStrategy.OldCat
        )

        assertTrue(result.trades.isNotEmpty())
        assertTrue(result.trades.all { it.exitReason.contains(BacktestStrategy.OldCat.title) })
    }
}
