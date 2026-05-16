package com.example.myapplication.network

import com.example.myapplication.market.BacktestResult
import com.example.myapplication.market.BacktestTrade
import com.example.myapplication.market.DailyPickGroup
import com.example.myapplication.market.EquityPoint
import com.example.myapplication.market.MarketBoard
import com.example.myapplication.market.MinuteTrade
import com.example.myapplication.market.StockPick
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

object MarketApiClient {
    private const val BASE_URL = "http://14.103.183.47:8000"

    suspend fun runOldCatBacktest(
        startDate: String?,
        endDate: String?,
        holdingDays: Int,
        initialCapital: Double,
        board: MarketBoard?,
        maxPositionsPerDay: Int = 3
    ): BacktestResult = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("strategy_id", "old_cat")
            put("holding_days", holdingDays)
            put("initial_capital", initialCapital)
            put("max_positions_per_day", maxPositionsPerDay)
            board?.let { put("board", if (it == MarketBoard.ChiNext) "chinext" else "main") }
            put("take_profit_percent", 6.0)
            if (!startDate.isNullOrBlank()) put("start_date", startDate)
            if (!endDate.isNullOrBlank()) put("end_date", endDate)
        }
        postJson("/api/v1/backtests", payload, readTimeoutMs = 120_000).toBacktestResult()
    }

    suspend fun runSelection(
        tradeDate: String?,
        indicatorIds: Set<String>
    ): DailyPickGroup = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            if (!tradeDate.isNullOrBlank()) put("trade_date", tradeDate)
            put("indicator_ids", JSONArray(indicatorIds.sorted()))
        }
        postJson("/api/v1/selections/run", payload).toDailyPickGroup()
    }

    private fun postJson(path: String, payload: JSONObject, readTimeoutMs: Int = 15_000): JSONObject {
        val connection = (URL("$BASE_URL$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 8000
            readTimeout = readTimeoutMs
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "application/json")
        }

        OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { writer ->
            writer.write(payload.toString())
        }

        val statusCode = connection.responseCode
        val stream = if (statusCode in 200..299) connection.inputStream else connection.errorStream
        val body = BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
        connection.disconnect()

        if (statusCode !in 200..299) {
            throw IllegalStateException("服务端返回 $statusCode：$body")
        }
        return JSONObject(body)
    }

    private fun JSONObject.toBacktestResult(): BacktestResult {
        val tradeArray = getJSONArray("trades")
        val trades = buildList {
            for (index in 0 until tradeArray.length()) {
                val item = tradeArray.getJSONObject(index)
                add(
                    BacktestTrade(
                        code = item.getString("code"),
                        name = item.getString("name"),
                        board = item.getString("board").toMarketBoard(),
                        buyDate = item.getString("buy_date"),
                        sellDate = item.getString("sell_date"),
                        buyPrice = item.getDouble("buy_price"),
                        sellPrice = item.getDouble("sell_price"),
                        shares = item.optInt("shares", 0),
                        positionAmount = item.optDouble("position_amount", 0.0),
                        profitAmount = item.optDouble("profit_amount", 0.0),
                        stopLossPrice = item.getDouble("stop_loss_price"),
                        returnPercent = item.getDouble("return_percent"),
                        exitReason = item.getString("exit_reason")
                    )
                )
            }
        }
        val equityArray = optJSONArray("equity_curve")
        val equityCurve = buildList {
            if (equityArray != null) {
                for (index in 0 until equityArray.length()) {
                    val item = equityArray.getJSONObject(index)
                    add(EquityPoint(date = item.getString("trade_date"), capital = item.getDouble("capital")))
                }
            }
        }
        return BacktestResult(
            initialCapital = optDouble("initial_capital", 0.0),
            finalCapital = optDouble("final_capital", 0.0),
            totalTrades = getInt("total_trades"),
            winRate = getDouble("win_rate"),
            totalReturnPercent = getDouble("total_return_percent"),
            maxDrawdownPercent = getDouble("max_drawdown_percent"),
            trades = trades,
            equityCurve = equityCurve
        )
    }

    private fun JSONObject.toDailyPickGroup(): DailyPickGroup {
        val pickArray = getJSONArray("picks")
        val picks = buildList {
            for (index in 0 until pickArray.length()) {
                val item = pickArray.getJSONObject(index)
                add(
                    StockPick(
                        code = item.getString("code"),
                        name = item.getString("name"),
                        board = item.getString("board").toMarketBoard(),
                        date = item.getString("trade_date"),
                        concept = item.optString("concept"),
                        close = item.getDouble("close"),
                        changePercent = item.getDouble("change_percent"),
                        volumeRatio = item.getDouble("volume_ratio"),
                        turnoverRate = item.getDouble("turnover_rate"),
                        sealedAmountWan = item.getDouble("sealed_amount_wan"),
                        stopLossPrice = item.getDouble("stop_loss_price"),
                        latestTradeDate = item.optString("latest_trade_date").ifBlank { null },
                        latestClose = if (item.isNull("latest_close")) null else item.getDouble("latest_close"),
                        minuteTrades = item.optJSONArray("minute_trades").toMinuteTrades(),
                        nextOpen = if (item.isNull("next_open")) item.getDouble("close") else item.getDouble("next_open"),
                        futureCloses = item.optJSONArray("future_closes").toDoubleList(),
                        dailyCandles = emptyList()
                    )
                )
            }
        }
        return DailyPickGroup(
            date = getString("trade_date"),
            picks = picks
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

    private fun JSONArray?.toDoubleList(): List<Double> {
        if (this == null) return emptyList()
        return buildList {
            for (index in 0 until length()) {
                add(getDouble(index))
            }
        }
    }

    private fun String.toMarketBoard(): MarketBoard {
        return if (this == "chinext") MarketBoard.ChiNext else MarketBoard.Main
    }
}
