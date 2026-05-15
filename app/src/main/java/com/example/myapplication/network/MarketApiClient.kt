package com.example.myapplication.network

import com.example.myapplication.market.BacktestResult
import com.example.myapplication.market.BacktestTrade
import com.example.myapplication.market.MarketBoard
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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
        holdingDays: Int
    ): BacktestResult = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("strategy_id", "old_cat")
            put("holding_days", holdingDays)
            put("take_profit_percent", 6.0)
            if (!startDate.isNullOrBlank()) put("start_date", startDate)
            if (!endDate.isNullOrBlank()) put("end_date", endDate)
        }
        postJson("/api/v1/backtests", payload).toBacktestResult()
    }

    private fun postJson(path: String, payload: JSONObject): JSONObject {
        val connection = (URL("$BASE_URL$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 8000
            readTimeout = 15000
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
                        stopLossPrice = item.getDouble("stop_loss_price"),
                        returnPercent = item.getDouble("return_percent"),
                        exitReason = item.getString("exit_reason")
                    )
                )
            }
        }
        return BacktestResult(
            totalTrades = getInt("total_trades"),
            winRate = getDouble("win_rate"),
            totalReturnPercent = getDouble("total_return_percent"),
            maxDrawdownPercent = getDouble("max_drawdown_percent"),
            trades = trades
        )
    }

    private fun String.toMarketBoard(): MarketBoard {
        return if (this == "chinext") MarketBoard.ChiNext else MarketBoard.Main
    }
}
