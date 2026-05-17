package com.example.myapplication.storage

import android.content.Context
import com.example.myapplication.market.DailyCandle
import com.example.myapplication.market.DailyPickGroup
import com.example.myapplication.market.MarketBoard
import com.example.myapplication.market.MinuteTrade
import com.example.myapplication.market.SelectionStrategy
import com.example.myapplication.market.StockPick
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

object SelectionCache {
    private const val DIR_NAME = "selection-cache"

    fun load(context: Context, strategy: SelectionStrategy, indicatorIds: Set<String>): DailyPickGroup? {
        val file = cacheFile(context, strategy, indicatorIds)
        if (!file.exists()) return null
        return runCatching { JSONObject(file.readText(Charsets.UTF_8)).toDailyPickGroup() }.getOrNull()
    }

    fun save(context: Context, strategy: SelectionStrategy, indicatorIds: Set<String>, group: DailyPickGroup) {
        val dir = File(context.filesDir, DIR_NAME).apply { mkdirs() }
        val file = File(dir, fileName(strategy, indicatorIds))
        file.writeText(group.toJson().toString(), Charsets.UTF_8)
    }

    fun clear(context: Context) {
        File(context.filesDir, DIR_NAME).deleteRecursively()
    }

    private fun cacheFile(context: Context, strategy: SelectionStrategy, indicatorIds: Set<String>): File {
        return File(File(context.filesDir, DIR_NAME), fileName(strategy, indicatorIds))
    }

    private fun fileName(strategy: SelectionStrategy, indicatorIds: Set<String>): String {
        val key = indicatorIds.sorted().joinToString(separator = "_").ifBlank { "none" }
        return "selection-${strategy.id}-$key.json"
    }

    private fun DailyPickGroup.toJson(): JSONObject {
        return JSONObject()
            .put("date", date)
            .put("picks", JSONArray(picks.map { it.toJson() }))
    }

    private fun StockPick.toJson(): JSONObject {
        return JSONObject()
            .put("code", code)
            .put("name", name)
            .put("board", if (board == MarketBoard.ChiNext) "chinext" else "main")
            .put("date", date)
            .put("concept", concept)
            .put("close", close)
            .put("change_percent", changePercent)
            .put("volume_ratio", volumeRatio)
            .put("turnover_rate", turnoverRate)
            .put("sealed_amount_wan", sealedAmountWan)
            .put("stop_loss_price", stopLossPrice)
            .put("limit_shape", limitShape)
            .put("limit_shape_label", limitShapeLabel)
            .put("latest_trade_date", latestTradeDate)
            .put("latest_close", latestClose)
            .put("next_open", nextOpen)
            .put("future_closes", JSONArray(futureCloses))
            .put("minute_trades", JSONArray(minuteTrades.map { it.toJson() }))
            .put("daily_candles", JSONArray(dailyCandles.map { it.toJson() }))
    }

    private fun MinuteTrade.toJson(): JSONObject {
        return JSONObject()
            .put("minute", minute)
            .put("price", price)
            .put("volume", volume)
    }

    private fun DailyCandle.toJson(): JSONObject {
        return JSONObject()
            .put("date", date)
            .put("open", open)
            .put("high", high)
            .put("low", low)
            .put("close", close)
    }

    private fun JSONObject.toDailyPickGroup(): DailyPickGroup {
        val picksArray = getJSONArray("picks")
        val picks = buildList {
            for (index in 0 until picksArray.length()) {
                add(picksArray.getJSONObject(index).toStockPick())
            }
        }
        return DailyPickGroup(date = getString("date"), picks = picks)
    }

    private fun JSONObject.toStockPick(): StockPick {
        val cachedClose = getDouble("close")
        return StockPick(
            code = getString("code"),
            name = getString("name"),
            board = if (getString("board") == "chinext") MarketBoard.ChiNext else MarketBoard.Main,
            date = getString("date"),
            concept = optString("concept"),
            close = cachedClose,
            changePercent = getDouble("change_percent"),
            volumeRatio = getDouble("volume_ratio"),
            turnoverRate = getDouble("turnover_rate"),
            sealedAmountWan = getDouble("sealed_amount_wan"),
            stopLossPrice = getDouble("stop_loss_price"),
            limitShape = optString("limit_shape"),
            limitShapeLabel = optString("limit_shape_label"),
            latestTradeDate = optString("latest_trade_date").ifBlank { null },
            latestClose = if (isNull("latest_close")) null else getDouble("latest_close"),
            minuteTrades = optJSONArray("minute_trades").toMinuteTrades(),
            nextOpen = optDouble("next_open", cachedClose),
            futureCloses = optJSONArray("future_closes").toDoubleList(),
            dailyCandles = optJSONArray("daily_candles").toDailyCandles()
        )
    }

    private fun JSONArray?.toMinuteTrades(): List<MinuteTrade> {
        if (this == null) return emptyList()
        return buildList {
            for (index in 0 until length()) {
                val item = getJSONObject(index)
                add(
                    MinuteTrade(
                        minute = item.getString("minute"),
                        price = item.getDouble("price"),
                        volume = item.optInt("volume", 0)
                    )
                )
            }
        }
    }

    private fun JSONArray?.toDailyCandles(): List<DailyCandle> {
        if (this == null) return emptyList()
        return buildList {
            for (index in 0 until length()) {
                val item = getJSONObject(index)
                add(
                    DailyCandle(
                        date = item.getString("date"),
                        open = item.getDouble("open"),
                        high = item.getDouble("high"),
                        low = item.getDouble("low"),
                        close = item.getDouble("close")
                    )
                )
            }
        }
    }

    private fun JSONArray?.toDoubleList(): List<Double> {
        if (this == null) return emptyList()
        return buildList {
            for (index in 0 until length()) {
                add(getDouble(index))
            }
        }
    }
}
