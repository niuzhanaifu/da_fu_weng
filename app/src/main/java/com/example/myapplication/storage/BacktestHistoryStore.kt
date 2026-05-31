package com.example.myapplication.storage

import android.content.Context
import com.example.myapplication.market.BacktestHistoryEntry
import com.example.myapplication.market.BacktestResult
import com.example.myapplication.market.BacktestTrade
import com.example.myapplication.market.EquityPoint
import com.example.myapplication.market.MarketBoard
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

object BacktestHistoryStore {
    private const val DIR_NAME = "backtest-history"

    fun loadAll(context: Context): List<BacktestHistoryEntry> {
        val dir = File(context.filesDir, DIR_NAME)
        if (!dir.exists()) return emptyList()
        return dir.listFiles { file -> file.extension == "json" }
            ?.mapNotNull { file -> runCatching { JSONObject(file.readText(Charsets.UTF_8)).toEntry() }.getOrNull() }
            ?.sortedByDescending { it.createdAt }
            .orEmpty()
    }

    fun save(context: Context, entry: BacktestHistoryEntry) {
        val dir = File(context.filesDir, DIR_NAME).apply { mkdirs() }
        File(dir, "${entry.id}.json").writeText(entry.toJson().toString(), Charsets.UTF_8)
    }

    fun delete(context: Context, id: String) {
        File(File(context.filesDir, DIR_NAME), "$id.json").delete()
    }

    fun clear(context: Context) {
        File(context.filesDir, DIR_NAME).deleteRecursively()
    }

    private fun BacktestHistoryEntry.toJson(): JSONObject {
        return JSONObject()
            .put("id", id)
            .put("created_at", createdAt)
            .put("strategy_id", strategyId)
            .put("strategy_name", strategyName)
            .put("start_date", startDate)
            .put("end_date", endDate)
            .put("holding_days", holdingDays)
            .put("initial_capital", initialCapital)
            .put("volume_ratio_min", volumeRatioMin)
            .put("board", board?.let { if (it == MarketBoard.ChiNext) "chinext" else "main" })
            .put("result", result.toJson())
    }

    private fun BacktestResult.toJson(): JSONObject {
        return JSONObject()
            .put("initial_capital", initialCapital)
            .put("final_capital", finalCapital)
            .put("total_trades", totalTrades)
            .put("win_rate", winRate)
            .put("total_return_percent", totalReturnPercent)
            .put("max_drawdown_percent", maxDrawdownPercent)
            .put("trades", JSONArray(trades.map { it.toJson() }))
            .put("equity_curve", JSONArray(equityCurve.map { it.toJson() }))
    }

    private fun BacktestTrade.toJson(): JSONObject {
        return JSONObject()
            .put("code", code)
            .put("name", name)
            .put("board", if (board == MarketBoard.ChiNext) "chinext" else "main")
            .put("buy_date", buyDate)
            .put("sell_date", sellDate)
            .put("buy_price", buyPrice)
            .put("sell_price", sellPrice)
            .put("shares", shares)
            .put("position_amount", positionAmount)
            .put("profit_amount", profitAmount)
            .put("stop_loss_price", stopLossPrice)
            .put("return_percent", returnPercent)
            .put("exit_reason", exitReason)
    }

    private fun EquityPoint.toJson(): JSONObject {
        return JSONObject()
            .put("trade_date", date)
            .put("capital", capital)
    }

    private fun JSONObject.toEntry(): BacktestHistoryEntry {
        return BacktestHistoryEntry(
            id = getString("id"),
            createdAt = getString("created_at"),
            strategyId = getString("strategy_id"),
            strategyName = getString("strategy_name"),
            startDate = getString("start_date"),
            endDate = getString("end_date"),
            holdingDays = getInt("holding_days"),
            initialCapital = getDouble("initial_capital"),
            volumeRatioMin = if (has("volume_ratio_min") && !isNull("volume_ratio_min")) optDouble("volume_ratio_min") else null,
            board = optString("board").toBoardOrNull(),
            result = getJSONObject("result").toResult()
        )
    }

    private fun JSONObject.toResult(): BacktestResult {
        val tradesArray = getJSONArray("trades")
        val trades = buildList {
            for (index in 0 until tradesArray.length()) {
                add(tradesArray.getJSONObject(index).toTrade())
            }
        }
        val curveArray = optJSONArray("equity_curve")
        val equityCurve = buildList {
            if (curveArray != null) {
                for (index in 0 until curveArray.length()) {
                    val item = curveArray.getJSONObject(index)
                    add(EquityPoint(date = item.getString("trade_date"), capital = item.getDouble("capital")))
                }
            }
        }
        return BacktestResult(
            initialCapital = getDouble("initial_capital"),
            finalCapital = getDouble("final_capital"),
            totalTrades = getInt("total_trades"),
            winRate = getDouble("win_rate"),
            totalReturnPercent = getDouble("total_return_percent"),
            maxDrawdownPercent = getDouble("max_drawdown_percent"),
            trades = trades,
            equityCurve = equityCurve
        )
    }

    private fun JSONObject.toTrade(): BacktestTrade {
        return BacktestTrade(
            code = getString("code"),
            name = getString("name"),
            board = if (getString("board") == "chinext") MarketBoard.ChiNext else MarketBoard.Main,
            buyDate = getString("buy_date"),
            sellDate = getString("sell_date"),
            buyPrice = getDouble("buy_price"),
            sellPrice = getDouble("sell_price"),
            shares = optInt("shares", 0),
            positionAmount = optDouble("position_amount", 0.0),
            profitAmount = optDouble("profit_amount", 0.0),
            stopLossPrice = getDouble("stop_loss_price"),
            returnPercent = getDouble("return_percent"),
            exitReason = getString("exit_reason")
        )
    }

    private fun String.toBoardOrNull(): MarketBoard? {
        return when (this) {
            "main" -> MarketBoard.Main
            "chinext" -> MarketBoard.ChiNext
            else -> null
        }
    }
}
