package com.example.myapplication.network

import com.example.myapplication.market.BacktestResult
import com.example.myapplication.market.BacktestExperimentItem
import com.example.myapplication.market.BacktestExperimentResult
import com.example.myapplication.market.BacktestTrade
import com.example.myapplication.market.DailyPickGroup
import com.example.myapplication.market.EquityPoint
import com.example.myapplication.market.MarketBoard
import com.example.myapplication.market.MinuteTrade
import com.example.myapplication.market.SelectionStrategy
import com.example.myapplication.market.StockPick
import com.example.myapplication.market.TradeBook
import com.example.myapplication.market.TradePosition
import com.example.myapplication.market.TradeStats
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

    suspend fun runBacktest(
        strategyId: String,
        startDate: String?,
        endDate: String?,
        holdingDays: Int,
        takeProfitPercent: Double,
        volumeRatioMin: Double?,
        allowBelowMarketMa25: Boolean,
        board: MarketBoard?,
        maxPositionsPerDay: Int = 3
    ): BacktestResult = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("strategy_id", strategyId)
            put("holding_days", holdingDays)
            put("max_positions_per_day", maxPositionsPerDay)
            board?.let { put("board", if (it == MarketBoard.ChiNext) "chinext" else "main") }
            put("take_profit_percent", takeProfitPercent)
            volumeRatioMin?.let { put("volume_ratio_min", it) }
            put("allow_below_market_ma25", allowBelowMarketMa25)
            if (!startDate.isNullOrBlank()) put("start_date", startDate)
            if (!endDate.isNullOrBlank()) put("end_date", endDate)
        }
        postJson("/api/v1/backtests", payload, readTimeoutMs = 300_000).toBacktestResult()
    }

    suspend fun runBacktestExperiments(
        startDate: String?,
        endDate: String?,
        holdingDays: Int,
        takeProfitPercent: Double,
        volumeRatioMin: Double?,
        allowBelowMarketMa25: Boolean,
        board: MarketBoard?,
        maxPositionsPerDay: Int = 3
    ): BacktestExperimentResult = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("strategy_id", "old_cat")
            put("holding_days", holdingDays)
            put("max_positions_per_day", maxPositionsPerDay)
            put("take_profit_percent", takeProfitPercent)
            volumeRatioMin?.let { put("volume_ratio_min", it) }
            put("allow_below_market_ma25", allowBelowMarketMa25)
            board?.let { put("board", if (it == MarketBoard.ChiNext) "chinext" else "main") }
            if (!startDate.isNullOrBlank()) put("start_date", startDate)
            if (!endDate.isNullOrBlank()) put("end_date", endDate)
        }
        postJson("/api/v1/backtests/experiments", payload, readTimeoutMs = 300_000).toExperimentResult()
    }

    suspend fun runSelection(
        tradeDate: String?,
        strategy: SelectionStrategy,
        indicatorIds: Set<String>
    ): DailyPickGroup = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            if (!tradeDate.isNullOrBlank()) put("trade_date", tradeDate)
            put("strategy_id", strategy.id)
            put("indicator_ids", JSONArray(indicatorIds.sorted()))
        }
        postJson("/api/v1/selections/run", payload).toDailyPickGroup()
    }

    suspend fun fetchTradeBook(): TradeBook = withContext(Dispatchers.IO) {
        getJson("/api/v1/trades").toTradeBook()
    }

    suspend fun recordBuy(
        pick: StockPick,
        buyPrice: Double,
        shares: Int,
        buyDate: String
    ): TradePosition = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("code", pick.code)
            put("name", pick.name)
            put("board", if (pick.board == MarketBoard.ChiNext) "chinext" else "main")
            put("source_trade_date", pick.date)
            put("buy_date", buyDate)
            put("buy_price", buyPrice)
            put("shares", shares)
            put("stop_loss_price", pick.stopLossPrice)
        }
        postJson("/api/v1/trades/buy", payload).toTradePosition()
    }

    suspend fun recordSell(
        tradeId: Int,
        sellPrice: Double,
        shares: Int,
        sellDate: String
    ): TradePosition = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("sell_date", sellDate)
            put("sell_price", sellPrice)
            put("shares", shares)
        }
        postJson("/api/v1/trades/$tradeId/sell", payload).toTradePosition()
    }

    private fun getJson(path: String, readTimeoutMs: Int = 15_000): JSONObject {
        val connection = (URL("$BASE_URL$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 8000
            readTimeout = readTimeoutMs
            setRequestProperty("Accept", "application/json")
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

    private fun JSONObject.toExperimentResult(): BacktestExperimentResult {
        val itemArray = getJSONArray("items")
        val items = buildList {
            for (index in 0 until itemArray.length()) {
                val item = itemArray.getJSONObject(index)
                add(
                    BacktestExperimentItem(
                        strategyId = item.getString("strategy_id"),
                        strategyName = item.getString("strategy_name"),
                        description = item.optString("description"),
                        result = item.getJSONObject("result").toBacktestResult()
                    )
                )
            }
        }
        return BacktestExperimentResult(items = items)
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
                        limitShape = item.optString("limit_shape"),
                        limitShapeLabel = item.optString("limit_shape_label"),
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

    private fun JSONObject.toTradeBook(): TradeBook {
        return TradeBook(
            openPositions = getJSONArray("open_positions").toTradePositions(),
            history = getJSONArray("history").toTradePositions(),
            stats = getJSONObject("stats").let { stats ->
                TradeStats(
                    holdingCount = stats.optInt("holding_count", 0),
                    totalTrades = stats.optInt("total_trades", 0),
                    winRate = stats.optDouble("win_rate", 0.0),
                    totalProfitAmount = stats.optDouble("total_profit_amount", 0.0)
                )
            }
        )
    }

    private fun JSONArray.toTradePositions(): List<TradePosition> {
        return buildList {
            for (index in 0 until length()) {
                add(getJSONObject(index).toTradePosition())
            }
        }
    }

    private fun JSONObject.toTradePosition(): TradePosition {
        return TradePosition(
            id = getInt("id"),
            code = getString("code"),
            name = getString("name"),
            board = getString("board").toMarketBoard(),
            sourceTradeDate = getString("source_trade_date"),
            buyDate = getString("buy_date"),
            buyPrice = getDouble("buy_price"),
            buyShares = getInt("buy_shares"),
            stopLossPrice = getDouble("stop_loss_price"),
            latestTradeDate = if (isNull("latest_trade_date")) null else getString("latest_trade_date"),
            latestClose = if (isNull("latest_close")) null else getDouble("latest_close"),
            stopLossLossPercent = optDouble("stop_loss_loss_percent", 0.0),
            unrealizedProfitAmount = optDouble("unrealized_profit_amount", 0.0),
            unrealizedProfitPercent = optDouble("unrealized_profit_percent", 0.0),
            status = getString("status"),
            sellSignal = optBoolean("sell_signal", false),
            sellDate = if (isNull("sell_date")) null else getString("sell_date"),
            sellPrice = if (isNull("sell_price")) null else getDouble("sell_price"),
            sellShares = if (isNull("sell_shares")) null else getInt("sell_shares"),
            profitAmount = if (isNull("profit_amount")) null else getDouble("profit_amount")
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
