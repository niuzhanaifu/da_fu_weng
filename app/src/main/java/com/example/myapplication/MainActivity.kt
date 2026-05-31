package com.example.myapplication

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.platform.LocalContext
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.myapplication.logging.AppLogger
import com.example.myapplication.market.BacktestHistoryEntry
import com.example.myapplication.market.BacktestExperimentItem
import com.example.myapplication.market.BacktestExperimentResult
import com.example.myapplication.market.BacktestResult
import com.example.myapplication.market.BacktestStrategy
import com.example.myapplication.market.BacktestTrade
import com.example.myapplication.market.DailyCandle
import com.example.myapplication.market.DailyPickGroup
import com.example.myapplication.market.EquityPoint
import com.example.myapplication.market.IndicatorCatalog
import com.example.myapplication.market.MarketBoard
import com.example.myapplication.market.SampleMarketData
import com.example.myapplication.market.SelectionStrategy
import com.example.myapplication.market.StockPick
import com.example.myapplication.market.StockSelectionEngine
import com.example.myapplication.market.TradeBook
import com.example.myapplication.market.TradePosition
import com.example.myapplication.market.asPercent
import com.example.myapplication.market.asPrice
import com.example.myapplication.network.MarketApiClient
import com.example.myapplication.storage.BacktestHistoryStore
import com.example.myapplication.storage.SelectionCache
import com.example.myapplication.ui.theme.MyApplicationTheme
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlin.math.max
import kotlin.math.roundToInt

private val PageBackground = Color(0xFFF5F7FA)
private val Panel = Color.White
private val Ink = Color(0xFF17202A)
private val Muted = Color(0xFF6B7280)
private val RiseRed = Color(0xFFD92323)
private val FallGreen = Color(0xFF167A54)
private val ChiNextBlue = Color(0xFF1266D6)
private val ActionBlue = Color(0xFF0B4F8A)

@Composable
private fun ActionButtonColors() = ButtonDefaults.buttonColors(
    containerColor = Color.White,
    contentColor = ActionBlue,
    disabledContainerColor = Color(0xFFE5E7EB),
    disabledContentColor = Muted
)

private enum class PickBoardFilter(val label: String) {
    All("全部"),
    Main("主板"),
    ChiNext("创业板")
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        AppLogger.install(applicationContext)
        AppLogger.i("MainActivity", "onCreate savedState=${savedInstanceState != null}")
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MyApplicationTheme(dynamicColor = false) {
                StockApp()
            }
        }
    }

    override fun onDestroy() {
        AppLogger.i("MainActivity", "onDestroy finishing=$isFinishing")
        super.onDestroy()
    }
}

@Composable
fun StockApp() {
    val context = LocalContext.current
    var selectedTab by remember { mutableIntStateOf(0) }
    var selectedStock by remember { mutableStateOf<StockPick?>(null) }
    var selectedBuyPick by remember { mutableStateOf<StockPick?>(null) }
    var enabledIndicators by remember { mutableStateOf(setOf("volume", "seal", "close")) }
    var selectedSelectionStrategy by remember { mutableStateOf(SelectionStrategy.OldCatBuy) }
    val cachedGroup = remember { SelectionCache.load(context, selectedSelectionStrategy, enabledIndicators) }
    var selectedPickDate by remember { mutableStateOf(cachedGroup?.date ?: todayDateString()) }
    val localGroups = remember {
        StockSelectionEngine.selectDailyGroups(
            history = SampleMarketData.stockDays(),
            enabledIndicatorIds = setOf("volume", "seal", "close")
        )
    }
    var groups by remember { mutableStateOf(cachedGroup?.let { listOf(it) } ?: localGroups) }

    LaunchedEffect(selectedTab) {
        AppLogger.i("StockApp", "tab changed index=$selectedTab")
    }

    if (selectedStock != null) {
        StockDetailPage(
            pick = selectedStock!!,
            onBack = {
                AppLogger.d("StockDetail", "back from ${selectedStock?.code}")
                selectedStock = null
            }
        )
        return
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = PageBackground,
        bottomBar = {
            NavigationBar(containerColor = Panel) {
                listOf("选股", "回测", "指标", "交易").forEachIndexed { index, label ->
                    NavigationBarItem(
                        selected = selectedTab == index,
                        onClick = {
                            AppLogger.d("Navigation", "click tab=$label index=$index")
                            selectedTab = index
                        },
                        icon = { Text(label.take(1), fontWeight = FontWeight.Bold) },
                        label = { Text(label) }
                    )
                }
            }
        }
    ) { innerPadding ->
        Surface(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding),
            color = PageBackground
        ) {
            when (selectedTab) {
                0 -> PickGroupsPage(
                    groups = groups,
                    selectedDate = selectedPickDate,
                    onSelectedDateChange = { selectedPickDate = it },
                    enabledIndicators = enabledIndicators,
                    selectedStrategy = selectedSelectionStrategy,
                    onSelectedStrategyChange = {
                        selectedSelectionStrategy = it
                        val nextCachedGroup = SelectionCache.load(context, it, enabledIndicators)
                        selectedPickDate = nextCachedGroup?.date ?: selectedPickDate
                        groups = nextCachedGroup?.let { cached -> listOf(cached) } ?: emptyList()
                    },
                    onSelectionResult = { group ->
                        SelectionCache.save(context, selectedSelectionStrategy, enabledIndicators, group)
                        selectedPickDate = group.date
                        groups = listOf(group)
                    },
                    onStockClick = { selectedStock = it },
                    onBuyClick = { selectedBuyPick = it }
                )
                1 -> BacktestPage(groups)
                2 -> IndicatorsPage(
                    enabledIndicators = enabledIndicators,
                    onChange = {
                        enabledIndicators = it
                        val nextCachedGroup = SelectionCache.load(context, selectedSelectionStrategy, it)
                        selectedPickDate = nextCachedGroup?.date ?: todayDateString()
                        groups = nextCachedGroup?.let { cachedGroup -> listOf(cachedGroup) } ?: emptyList()
                    },
                    onClearData = { groups = emptyList() }
                )
                else -> TradingPage()
            }
        }
    }

    selectedBuyPick?.let { pick ->
        BuyTradeDialog(
            pick = pick,
            onDismiss = { selectedBuyPick = null },
            onSaved = {
                selectedBuyPick = null
                selectedTab = 3
            }
        )
    }
}

@Composable
private fun PickGroupsPage(
    groups: List<DailyPickGroup>,
    selectedDate: String,
    onSelectedDateChange: (String) -> Unit,
    enabledIndicators: Set<String>,
    selectedStrategy: SelectionStrategy,
    onSelectedStrategyChange: (SelectionStrategy) -> Unit,
    onSelectionResult: (DailyPickGroup) -> Unit,
    onStockClick: (StockPick) -> Unit,
    onBuyClick: (StockPick) -> Unit
) {
    val group = groups.firstOrNull { it.date == selectedDate }
    var boardFilter by remember { mutableStateOf(PickBoardFilter.All) }
    val visiblePicks = group?.picks.orEmpty().filter { pick ->
        when (boardFilter) {
            PickBoardFilter.All -> true
            PickBoardFilter.Main -> pick.board == MarketBoard.Main
            PickBoardFilter.ChiNext -> pick.board == MarketBoard.ChiNext
        }
    }
    var isSelecting by remember { mutableStateOf(false) }
    var selectionError by remember { mutableStateOf<String?>(null) }
    var selectionRequest by remember { mutableIntStateOf(0) }

    LaunchedEffect(selectionRequest) {
        if (selectionRequest == 0) return@LaunchedEffect
        isSelecting = true
        selectionError = null
        try {
            val result = MarketApiClient.runSelection(
                tradeDate = selectedDate,
                strategy = selectedStrategy,
                indicatorIds = enabledIndicators
            )
            onSelectedDateChange(result.date)
            onSelectionResult(result)
            AppLogger.i("Selection", "server selection completed date=${result.date} strategy=${selectedStrategy.id} picks=${result.picks.size} indicators=${enabledIndicators.sorted()}")
        } catch (error: Exception) {
            selectionError = error.message ?: "服务端选股失败"
            AppLogger.e("Selection", "server selection failed", error)
        } finally {
            isSelecting = false
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            AppHeader(
                title = "大富翁选股",
                subtitle = "收盘后筛选主板与创业板涨停股，并标注分时成交均价止损位"
            )
        }
        item {
            CalendarDateSelector(
                title = "交易日期",
                value = selectedDate,
                onSelected = {
                    AppLogger.d("PickGroups", "calendar date selected=$it")
                    onSelectedDateChange(it)
                }
            )
        }
        item {
            SelectionActionCard(
                indicators = enabledIndicators,
                selectedDate = selectedDate,
                selectedStrategy = selectedStrategy,
                onSelectedStrategyChange = onSelectedStrategyChange,
                isSelecting = isSelecting,
                onRun = { selectionRequest += 1 }
            )
        }
        selectionError?.let { message ->
            item { ErrorState("服务端选股失败：$message") }
        }
        group?.let { current ->
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MetricCard("主板", "${current.mainCount}只", FallGreen, Modifier.weight(1f))
                    MetricCard("创业板", "${current.chiNextCount}只", ChiNextBlue, Modifier.weight(1f))
                    MetricCard("分时均线止损", current.averageStopLoss.asPrice(), RiseRed, Modifier.weight(1f))
                }
            }
            item {
                PickBoardFilterTabs(
                    selected = boardFilter,
                    onSelected = { boardFilter = it }
                )
            }
            items(visiblePicks) { pick ->
                StockPickCard(
                    pick = pick,
                    onBuyClick = { onBuyClick(pick) },
                    onClick = {
                        AppLogger.d("PickGroups", "open stock ${pick.code}")
                        onStockClick(pick)
                    }
                )
            }
            if (visiblePicks.isEmpty()) {
                item { EmptyState("当前分类没有选股结果。") }
            }
        }
        if (group == null) {
            item {
                EmptyState("请选择日期后点击开始选股，APP 会向服务端请求该交易日的真实行情。")
            }
        }
    }
}

@Composable
private fun StockDetailPage(
    pick: StockPick,
    onBack: () -> Unit
) {
    var selectedIndex by remember(pick.code) { mutableIntStateOf((pick.dailyCandles.size - 1).coerceAtLeast(0)) }
    val selectedCandle = pick.dailyCandles.getOrNull(selectedIndex)

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(PageBackground),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFF111827)),
                shape = RoundedCornerShape(8.dp)
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = onBack) {
                            Text("返回", color = Color.White)
                        }
                        Column(Modifier.weight(1f), horizontalAlignment = Alignment.End) {
                            Text("${pick.name} ${pick.code}", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                            Text("${pick.concept} · ${pick.board.label}", color = Color(0xFFCBD5E1), fontSize = 12.sp)
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        QuoteCell("收盘", pick.close.asPrice(), RiseRed, Modifier.weight(1f))
                        QuoteCell("涨幅", pick.changePercent.asPercent(), RiseRed, Modifier.weight(1f))
                        QuoteCell("分时均线止损", pick.stopLossPrice.asPrice(), FallGreen, Modifier.weight(1f))
                    }
                    if (pick.limitShapeLabel.isNotBlank()) {
                        Text("涨停形态：${pick.limitShapeLabel}", color = Color(0xFFCBD5E1), fontSize = 12.sp)
                    }
                }
            }
        }
        item {
            ElevatedCard(
                colors = CardDefaults.elevatedCardColors(containerColor = Panel),
                shape = RoundedCornerShape(8.dp)
            ) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("日 K 线", color = Ink, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        selectedCandle?.let {
                            Text(it.date, color = Muted, fontSize = 12.sp)
                        }
                    }
                    DailyKLineChart(
                        candles = pick.dailyCandles,
                        selectedIndex = selectedIndex,
                        onSelected = { selectedIndex = it }
                    )
                    selectedCandle?.let {
                        CandleInfo(it)
                    }
                }
            }
        }
        item {
            ElevatedCard(
                colors = CardDefaults.elevatedCardColors(containerColor = Panel),
                shape = RoundedCornerShape(8.dp)
            ) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("量比 ${pick.volumeRatio.asPrice()}", color = Muted, fontSize = 12.sp)
                        Text("换手 ${pick.turnoverRate.asPercent()}", color = Muted, fontSize = 12.sp)
                        Text("封单 ${pick.sealedAmountWan.roundToInt()}万", color = Muted, fontSize = 12.sp)
                    }
                    IntradayStopChart(pick)
                }
            }
        }
    }
}

@Composable
private fun SelectionActionCard(
    indicators: Set<String>,
    selectedDate: String,
    selectedStrategy: SelectionStrategy,
    onSelectedStrategyChange: (SelectionStrategy) -> Unit,
    isSelecting: Boolean,
    onRun: () -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("服务端选股", color = Ink, fontWeight = FontWeight.Bold)
                    Text("日期 $selectedDate / 指标 ${indicators.sorted().joinToString()}", color = Muted, fontSize = 12.sp)
                }
                if (isSelecting) {
                    CircularProgressIndicator(modifier = Modifier.size(26.dp), strokeWidth = 3.dp)
                } else {
                    Button(
                        onClick = onRun,
                        colors = ActionButtonColors()
                    ) {
                        Text("开始选股")
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SelectionStrategy.values().forEach { strategy ->
                    Surface(
                        modifier = Modifier
                            .weight(1f)
                            .clickable(enabled = !isSelecting) { onSelectedStrategyChange(strategy) },
                        color = if (selectedStrategy == strategy) Color(0xFFEFF6FF) else Color(0xFFF8FAFC),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(
                                strategy.title,
                                color = if (selectedStrategy == strategy) ChiNextBlue else Ink,
                                fontWeight = FontWeight.Bold
                            )
                            Text(strategy.description, color = Muted, fontSize = 11.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PickBoardFilterTabs(
    selected: PickBoardFilter,
    onSelected: (PickBoardFilter) -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            PickBoardFilter.values().forEach { filter ->
                Surface(
                    modifier = Modifier
                        .weight(1f)
                        .clickable { onSelected(filter) },
                    color = if (selected == filter) Color(0xFFEFF6FF) else Color(0xFFF8FAFC),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text(
                        filter.label,
                        modifier = Modifier.padding(vertical = 10.dp),
                        color = if (selected == filter) ChiNextBlue else Muted,
                        fontWeight = if (selected == filter) FontWeight.Bold else FontWeight.Normal
                    )
                }
            }
        }
    }
}

@Composable
private fun ClearDataCard(
    message: String?,
    onClear: () -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("清除本地数据", color = Ink, fontWeight = FontWeight.Bold)
                Text(message ?: "清除 App 本地日志和缓存，减少手机空间占用。", color = Muted, fontSize = 12.sp)
            }
            TextButton(onClick = onClear) {
                Text("清除")
            }
        }
    }
}

@Composable
private fun BacktestPage(groups: List<DailyPickGroup>) {
    val context = LocalContext.current
    var holdingDays by remember { mutableIntStateOf(3) }
    var maxPositionsPerDay by remember { mutableIntStateOf(3) }
    var takeProfitText by remember { mutableStateOf("10") }
    var volumeRatioText by remember { mutableStateOf("2") }
    var allowBelowMarketMa25 by remember { mutableStateOf(true) }
    var boardFilter by remember { mutableStateOf(PickBoardFilter.All) }
    var selectedStrategy by remember { mutableStateOf(BacktestStrategy.OldCat) }
    var startDate by remember { mutableStateOf(dateMonthsBefore(todayDateString(), 3)) }
    var endDate by remember { mutableStateOf(todayDateString()) }
    var runRequest by remember { mutableIntStateOf(0) }
    var experimentRequest by remember { mutableIntStateOf(0) }
    var isRunning by remember { mutableStateOf(false) }
    var isExperimentRunning by remember { mutableStateOf(false) }
    var showDoneDialog by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<BacktestResult?>(null) }
    var experimentResult by remember { mutableStateOf<BacktestExperimentResult?>(null) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var experimentError by remember { mutableStateOf<String?>(null) }
    var history by remember { mutableStateOf(BacktestHistoryStore.loadAll(context)) }
    var selectedHistoryId by remember { mutableStateOf<String?>(null) }
    val normalizedStart = minOf(startDate, endDate)
    val normalizedEnd = maxOf(startDate, endDate)

    LaunchedEffect(runRequest) {
        if (runRequest == 0) return@LaunchedEffect
        isRunning = true
        showDoneDialog = false
        errorMessage = null
        val takeProfitPercent = takeProfitText.toDoubleOrNull() ?: 10.0
        val volumeRatioMin = volumeRatioText.toDoubleOrNull()
        AppLogger.i("Backtest", "started remote strategy=${selectedStrategy.id} range=$normalizedStart..$normalizedEnd holdingDays=$holdingDays maxPositions=$maxPositionsPerDay")
        delay(350)
        try {
            val board = when (boardFilter) {
                PickBoardFilter.All -> null
                PickBoardFilter.Main -> MarketBoard.Main
                PickBoardFilter.ChiNext -> MarketBoard.ChiNext
            }
            val currentResult = MarketApiClient.runBacktest(
                strategyId = selectedStrategy.id,
                startDate = normalizedStart.ifEmpty { null },
                endDate = normalizedEnd.ifEmpty { null },
                holdingDays = holdingDays,
                takeProfitPercent = takeProfitPercent,
                volumeRatioMin = volumeRatioMin,
                allowBelowMarketMa25 = allowBelowMarketMa25,
                board = board,
                maxPositionsPerDay = maxPositionsPerDay
            )
            result = currentResult
            val entry = BacktestHistoryEntry(
                id = "backtest-${System.currentTimeMillis()}",
                createdAt = nowDateTimeString(),
                strategyId = selectedStrategy.id,
                strategyName = selectedStrategy.title,
                startDate = normalizedStart,
                endDate = normalizedEnd,
                holdingDays = holdingDays,
                initialCapital = currentResult.initialCapital,
                volumeRatioMin = volumeRatioMin,
                board = board,
                result = currentResult
            )
            BacktestHistoryStore.save(context, entry)
            history = BacktestHistoryStore.loadAll(context)
            selectedHistoryId = entry.id
            showDoneDialog = true
            AppLogger.i("Backtest", "remote finished trades=${currentResult.totalTrades} savedHistory=${entry.id}")
        } catch (error: Exception) {
            result = null
            errorMessage = error.message ?: "服务端请求失败"
            AppLogger.e("Backtest", "remote failed", error)
        } finally {
            isRunning = false
        }
    }

    LaunchedEffect(experimentRequest) {
        if (experimentRequest == 0) return@LaunchedEffect
        isExperimentRunning = true
        experimentError = null
        val takeProfitPercent = takeProfitText.toDoubleOrNull() ?: 10.0
        val volumeRatioMin = volumeRatioText.toDoubleOrNull()
        delay(350)
        try {
            experimentResult = MarketApiClient.runBacktestExperiments(
                startDate = normalizedStart.ifEmpty { null },
                endDate = normalizedEnd.ifEmpty { null },
                holdingDays = holdingDays,
                takeProfitPercent = takeProfitPercent,
                volumeRatioMin = volumeRatioMin,
                allowBelowMarketMa25 = allowBelowMarketMa25,
                board = when (boardFilter) {
                    PickBoardFilter.All -> null
                    PickBoardFilter.Main -> MarketBoard.Main
                    PickBoardFilter.ChiNext -> MarketBoard.ChiNext
                },
                maxPositionsPerDay = maxPositionsPerDay
            )
            AppLogger.i("Backtest", "experiment finished items=${experimentResult?.items?.size}")
        } catch (error: Exception) {
            experimentResult = null
            experimentError = error.message ?: "服务端策略实验失败"
            AppLogger.e("Backtest", "experiment failed", error)
        } finally {
            isExperimentRunning = false
        }
    }

    if (showDoneDialog) {
        AlertDialog(
            onDismissRequest = { showDoneDialog = false },
            title = { Text("回测结束") },
            text = { Text("回测已经完成，结果和每日操作已更新。") },
            confirmButton = {
                TextButton(onClick = { showDoneDialog = false }) {
                    Text("知道了")
                }
            }
        )
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            AppHeader(
                title = "战法回测",
                subtitle = "进入回测会显示进度；完成后查看收益、交易明细和每日操作"
            )
        }
        item {
            StrategyControls(
                selectedStrategy = selectedStrategy,
                onSelectedStrategy = { selectedStrategy = it }
            )
        }
        item {
            DateRangeControls(
                startDate = startDate,
                endDate = endDate,
                onStartDate = {
                    AppLogger.d("Backtest", "startDate changed=$it")
                    startDate = it
                },
                onEndDate = {
                    AppLogger.d("Backtest", "endDate changed=$it")
                    endDate = it
                }
            )
        }
        item {
            PickBoardFilterTabs(
                selected = boardFilter,
                onSelected = { boardFilter = it }
            )
        }
        item {
            BacktestControls(
                holdingDays = holdingDays,
                maxPositionsPerDay = maxPositionsPerDay,
                takeProfitText = takeProfitText,
                volumeRatioText = volumeRatioText,
                allowBelowMarketMa25 = allowBelowMarketMa25,
                onHoldingDays = {
                    AppLogger.d("Backtest", "holdingDays changed=$it")
                    holdingDays = it
                },
                onMaxPositionsPerDay = { maxPositionsPerDay = it },
                onTakeProfit = { takeProfitText = it },
                onVolumeRatio = { volumeRatioText = it },
                onAllowBelowMarketMa25 = { allowBelowMarketMa25 = it },
                isRunning = isRunning,
                onRun = { runRequest += 1 }
            )
        }
        item {
            BacktestExperimentCard(
                result = experimentResult,
                error = experimentError,
                isRunning = isExperimentRunning,
                onRun = { experimentRequest += 1 },
                onOpen = { item ->
                    selectedHistoryId = null
                    result = item.result
                }
            )
        }
        item {
            BacktestHistoryList(
                history = history,
                selectedId = selectedHistoryId,
                onOpen = { entry ->
                    selectedHistoryId = entry.id
                    result = entry.result
                    startDate = entry.startDate
                    endDate = entry.endDate
                    holdingDays = entry.holdingDays
                    volumeRatioText = entry.volumeRatioMin?.let { trimDoubleText(it) } ?: "2"
                    selectedStrategy = BacktestStrategy.values().firstOrNull { it.id == entry.strategyId } ?: BacktestStrategy.OldCat
                    boardFilter = when (entry.board) {
                        MarketBoard.Main -> PickBoardFilter.Main
                        MarketBoard.ChiNext -> PickBoardFilter.ChiNext
                        null -> PickBoardFilter.All
                    }
                },
                onDelete = { entry ->
                    BacktestHistoryStore.delete(context, entry.id)
                    history = BacktestHistoryStore.loadAll(context)
                    if (selectedHistoryId == entry.id) {
                        selectedHistoryId = null
                        result = null
                    }
                }
            )
        }
        if (isRunning) {
            item { BacktestProgressCard() }
        }
        errorMessage?.let { message ->
            item { ErrorState("服务端回测失败：$message") }
        }
        result?.let { current ->
            item { BacktestSummary(current) }
            item { EquityCurveChart(current.equityCurve) }
            item { DailyOperations(current.trades) }
            items(current.trades.sortedByDescending { it.profitAmount }) { trade ->
                TradeCard(trade)
            }
        }
    }
}

@Composable
private fun IndicatorsPage(
    enabledIndicators: Set<String>,
    onChange: (Set<String>) -> Unit,
    onClearData: () -> Unit
) {
    val context = LocalContext.current
    var clearMessage by remember { mutableStateOf<String?>(null) }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            AppHeader(
                title = "选股指标",
                subtitle = "指标开关会实时影响每日涨停分组与回测样本"
            )
        }
        item {
            EmptyState("日志文件位置：${AppLogger.logDirectoryPath()}/debug-00.log。每次启动都会滚动一个新切片，最多保留 debug-00.log 到 debug-09.log。")
        }
        item {
            ClearDataCard(
                message = clearMessage,
                onClear = {
                    SelectionCache.clear(context)
                    BacktestHistoryStore.clear(context)
                    AppLogger.clearLocalData(context)
                    onClearData()
                    clearMessage = "本地日志和缓存已清除。"
                }
            )
        }
        items(IndicatorCatalog.options) { option ->
            ElevatedCard(
                colors = CardDefaults.elevatedCardColors(containerColor = Panel),
                shape = RoundedCornerShape(8.dp)
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(option.name, color = Ink, fontWeight = FontWeight.Bold)
                        Text(option.description, color = Muted, fontSize = 13.sp, lineHeight = 18.sp)
                    }
                    Switch(
                        checked = option.id in enabledIndicators,
                        onCheckedChange = { checked ->
                            AppLogger.i("Indicators", "toggle id=${option.id} checked=$checked")
                            onChange(
                                if (checked) enabledIndicators + option.id
                                else enabledIndicators - option.id
                            )
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun BuyTradeDialog(
    pick: StockPick,
    onDismiss: () -> Unit,
    onSaved: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var buyPriceText by remember(pick.code) { mutableStateOf((pick.latestClose ?: pick.nextOpen).asPrice()) }
    var lotsText by remember(pick.code) { mutableStateOf("1") }
    var isSaving by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    val buyPrice = buyPriceText.toDoubleOrNull()
    val lots = lotsText.toIntOrNull()

    AlertDialog(
        onDismissRequest = { if (!isSaving) onDismiss() },
        title = { Text("记录买入") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${pick.name} ${pick.code}", color = Ink, fontWeight = FontWeight.Bold)
                Text("止损线 ${pick.stopLossPrice.asPrice()} / 选股日 ${pick.date}", color = Muted, fontSize = 12.sp)
                OutlinedTextField(
                    value = buyPriceText,
                    onValueChange = { raw -> buyPriceText = raw.filter { it.isDigit() || it == '.' }.take(8) },
                    label = { Text("买入价") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = lotsText,
                    onValueChange = { raw -> lotsText = raw.filter { it.isDigit() }.take(6) },
                    label = { Text("买入手数") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth()
                )
                errorMessage?.let { Text(it, color = FallGreen, fontSize = 12.sp) }
            }
        },
        confirmButton = {
            Button(
                enabled = !isSaving && buyPrice != null && lots != null && buyPrice > 0.0 && lots > 0,
                colors = ActionButtonColors(),
                onClick = {
                    val price = buyPrice ?: return@Button
                    val count = lots ?: return@Button
                    isSaving = true
                    errorMessage = null
                    scope.launch {
                        try {
                            MarketApiClient.recordBuy(
                                pick = pick,
                                buyPrice = price,
                                shares = count * 100,
                                buyDate = todayDateString()
                            )
                            onSaved()
                        } catch (error: Exception) {
                            errorMessage = error.message ?: "买入记录保存失败"
                        } finally {
                            isSaving = false
                        }
                    }
                }
            ) {
                Text(if (isSaving) "保存中" else "保存")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isSaving,
                colors = ButtonDefaults.textButtonColors(contentColor = ActionBlue)
            ) {
                Text("取消")
            }
        }
    )
}

@Composable
private fun SellTradeDialog(
    position: TradePosition,
    onDismiss: () -> Unit,
    onSaved: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var sellPriceText by remember(position.id) { mutableStateOf((position.latestClose ?: position.buyPrice).asPrice()) }
    var sharesText by remember(position.id) { mutableStateOf(position.buyShares.toString()) }
    var isSaving by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    val sellPrice = sellPriceText.toDoubleOrNull()
    val shares = sharesText.toIntOrNull()

    AlertDialog(
        onDismissRequest = { if (!isSaving) onDismiss() },
        title = { Text("记录卖出") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("${position.name} ${position.code}", color = Ink, fontWeight = FontWeight.Bold)
                Text("买入 ${position.buyPrice.asPrice()} / 持仓 ${position.buyShares}", color = Muted, fontSize = 12.sp)
                OutlinedTextField(
                    value = sellPriceText,
                    onValueChange = { raw -> sellPriceText = raw.filter { it.isDigit() || it == '.' }.take(8) },
                    label = { Text("卖出价") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = sharesText,
                    onValueChange = { raw -> sharesText = raw.filter { it.isDigit() }.take(8) },
                    label = { Text("成交股数") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth()
                )
                errorMessage?.let { Text(it, color = FallGreen, fontSize = 12.sp) }
            }
        },
        confirmButton = {
            Button(
                enabled = !isSaving && sellPrice != null && shares != null && sellPrice > 0.0 && shares > 0,
                colors = ActionButtonColors(),
                onClick = {
                    val price = sellPrice ?: return@Button
                    val count = shares ?: return@Button
                    isSaving = true
                    errorMessage = null
                    scope.launch {
                        try {
                            MarketApiClient.recordSell(
                                tradeId = position.id,
                                sellPrice = price,
                                shares = count,
                                sellDate = todayDateString()
                            )
                            onSaved()
                        } catch (error: Exception) {
                            errorMessage = error.message ?: "卖出记录保存失败"
                        } finally {
                            isSaving = false
                        }
                    }
                }
            ) {
                Text(if (isSaving) "保存中" else "保存")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isSaving,
                colors = ButtonDefaults.textButtonColors(contentColor = ActionBlue)
            ) {
                Text("取消")
            }
        }
    )
}

@Composable
private fun TradingPage() {
    var refreshRequest by remember { mutableIntStateOf(0) }
    var adviceDate by remember { mutableStateOf(todayDateString()) }
    var tradeBook by remember { mutableStateOf<TradeBook?>(null) }
    var dailyAdviceGroup by remember { mutableStateOf<DailyPickGroup?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var isAdviceLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var adviceErrorMessage by remember { mutableStateOf<String?>(null) }
    var sellingPosition by remember { mutableStateOf<TradePosition?>(null) }
    var buyingAdvicePick by remember { mutableStateOf<StockPick?>(null) }
    var historyExpanded by remember { mutableStateOf(false) }
    var selectedHistoryDate by remember { mutableStateOf(todayDateString()) }
    var showAllHistory by remember { mutableStateOf(false) }

    LaunchedEffect(refreshRequest, adviceDate) {
        isLoading = true
        isAdviceLoading = true
        errorMessage = null
        adviceErrorMessage = null
        try {
            tradeBook = MarketApiClient.fetchTradeBook()
        } catch (error: Exception) {
            errorMessage = error.message ?: "交易记录加载失败"
        } finally {
            isLoading = false
        }
        try {
            dailyAdviceGroup = MarketApiClient.runSelection(
                tradeDate = adviceDate,
                strategy = SelectionStrategy.OldCatBuy,
                indicatorIds = setOf("volume", "seal", "close")
            )
        } catch (error: Exception) {
            dailyAdviceGroup = null
            adviceErrorMessage = error.message ?: "每日建议加载失败"
        } finally {
            isAdviceLoading = false
        }
    }

    sellingPosition?.let { position ->
        SellTradeDialog(
            position = position,
            onDismiss = { sellingPosition = null },
            onSaved = {
                sellingPosition = null
                refreshRequest += 1
            }
        )
    }
    buyingAdvicePick?.let { pick ->
        BuyTradeDialog(
            pick = pick,
            onDismiss = { buyingAdvicePick = null },
            onSaved = {
                buyingAdvicePick = null
                refreshRequest += 1
            }
        )
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            AppHeader(
                title = "交易",
                subtitle = "老猫战法买入后记录持仓，跟踪最新收盘价、止损线、止损亏损率和卖出信号。"
            )
        }
        if (isLoading) {
            item { BacktestProgressCard() }
        }
        errorMessage?.let { message ->
            item { ErrorState("交易记录加载失败：$message") }
        }
        item {
            DailyOperationAdviceCard(
                tradeBook = tradeBook,
                adviceGroup = dailyAdviceGroup,
                isLoading = isAdviceLoading,
                errorMessage = adviceErrorMessage,
                selectedDate = adviceDate,
                onSelectedDateChange = { adviceDate = it },
                onBuyClick = { buyingAdvicePick = it }
            )
        }
        tradeBook?.let { book ->
            item { TradeStatsCards(book) }
            item { Text("当前持仓", color = Ink, fontWeight = FontWeight.Bold) }
            if (book.openPositions.isEmpty()) {
                item { EmptyState("暂无持仓。请在选股结果中点击买入后记录。") }
            } else {
                items(book.openPositions) { position ->
                    TradePositionCard(
                        position = position,
                        onSell = { sellingPosition = position }
                    )
                }
            }
            tradeHistoryItems(
                book = book,
                expanded = historyExpanded,
                selectedDate = selectedHistoryDate,
                showAll = showAllHistory,
                onExpandedChange = { historyExpanded = it },
                onSelectedDateChange = {
                    selectedHistoryDate = it
                    showAllHistory = false
                    historyExpanded = true
                },
                onShowAll = {
                    showAllHistory = true
                    historyExpanded = true
                }
            )
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.tradeHistoryItems(
    book: TradeBook,
    expanded: Boolean,
    selectedDate: String,
    showAll: Boolean,
    onExpandedChange: (Boolean) -> Unit,
    onSelectedDateChange: (String) -> Unit,
    onShowAll: () -> Unit
) {
    val today = todayDateString()
    val todayHistory = book.history.filter { it.matchesTradeDate(today) }
    val olderHistory = book.history.filterNot { it.matchesTradeDate(today) }
    val visibleOlderHistory = if (showAll) olderHistory else olderHistory.filter { it.matchesTradeDate(selectedDate) }

    item { Text("当日交易", color = Ink, fontWeight = FontWeight.Bold) }
    if (todayHistory.isEmpty()) {
        item { EmptyState("今日暂无已完成交易。") }
    } else {
        items(todayHistory, key = { it.id }) { position ->
            TradePositionCard(position = position, onSell = null)
        }
    }

    item {
        TradeHistoryControlCard(
            totalCount = olderHistory.size,
            visibleCount = visibleOlderHistory.size,
            expanded = expanded,
            selectedDate = selectedDate,
            showAll = showAll,
            onExpandedChange = onExpandedChange,
            onSelectedDateChange = onSelectedDateChange,
            onShowAll = onShowAll
        )
    }
    if (book.history.isEmpty()) {
        item { EmptyState("暂无历史交易。卖出持仓后会自动进入历史交易。") }
    } else if (expanded) {
        if (visibleOlderHistory.isEmpty()) {
            item {
                EmptyState(if (showAll) "暂无其他历史交易。" else "$selectedDate 暂无历史交易。")
            }
        } else {
            items(visibleOlderHistory, key = { it.id }) { position ->
                TradePositionCard(position = position, onSell = null)
            }
        }
    }
}

@Composable
private fun TradeHistoryControlCard(
    totalCount: Int,
    visibleCount: Int,
    expanded: Boolean,
    selectedDate: String,
    showAll: Boolean,
    onExpandedChange: (Boolean) -> Unit,
    onSelectedDateChange: (String) -> Unit,
    onShowAll: () -> Unit
) {
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("其他历史交易", color = Ink, fontWeight = FontWeight.Bold)
                    Text(
                        if (showAll) "全部展示 $visibleCount / $totalCount 笔" else "$selectedDate 展示 $visibleCount / $totalCount 笔",
                        color = Muted,
                        fontSize = 12.sp
                    )
                }
                TextButton(onClick = { onExpandedChange(!expanded) }) {
                    Text(if (expanded) "收起" else "展开")
                }
            }
            CalendarDateSelector(
                title = "历史日期",
                value = selectedDate,
                onSelected = onSelectedDateChange
            )
            Button(
                onClick = onShowAll,
                modifier = Modifier.fillMaxWidth(),
                colors = ActionButtonColors()
            ) {
                Text("全部展示")
            }
        }
    }
}

private fun TradePosition.matchesTradeDate(date: String): Boolean {
    return buyDate == date || sellDate == date
}

@Composable
private fun DailyOperationAdviceCard(
    tradeBook: TradeBook?,
    adviceGroup: DailyPickGroup?,
    isLoading: Boolean,
    errorMessage: String?,
    selectedDate: String,
    onSelectedDateChange: (String) -> Unit,
    onBuyClick: (StockPick) -> Unit
) {
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("每日建议操作", color = Ink, fontWeight = FontWeight.Bold)
                    Text(
                        "按老猫买入条件生成，数据以服务端最新收盘行情为准",
                        color = Muted,
                        fontSize = 12.sp
                    )
                }
                adviceGroup?.let {
                    Text(it.date, color = Muted, fontSize = 12.sp)
                }
            }
            CalendarDateSelector(
                title = "建议日期",
                value = selectedDate,
                onSelected = onSelectedDateChange
            )

            when {
                isLoading -> {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp, color = ActionBlue)
                        Text("正在生成建议", color = Muted, fontSize = 12.sp)
                    }
                }
                errorMessage != null -> {
                    Text("建议加载失败：$errorMessage", color = FallGreen, fontSize = 12.sp)
                }
                else -> {
                    val sellSignals = tradeBook?.openPositions.orEmpty().filter { it.sellSignal }
                    if (sellSignals.isEmpty() && adviceGroup?.picks.orEmpty().isEmpty()) {
                        Text("今日暂无建议操作", color = Muted, fontSize = 13.sp)
                    }
                    sellSignals.forEach { position ->
                        DailySellAdviceRow(position)
                    }
                    adviceGroup?.picks.orEmpty().forEach { pick ->
                        DailyBuyAdviceRow(pick = pick, onBuyClick = { onBuyClick(pick) })
                    }
                }
            }
        }
    }
}

@Composable
private fun DailySellAdviceRow(position: TradePosition) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF8FAFC)),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${position.name} ${position.code}", color = Ink, fontWeight = FontWeight.Bold)
                    Text("最新收盘 ${position.latestClose?.asPrice() ?: "暂无"} / 止损线 ${position.stopLossPrice.asPrice()}", color = Muted, fontSize = 12.sp)
                }
                Text("建议卖出", color = FallGreen, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun DailyBuyAdviceRow(
    pick: StockPick,
    onBuyClick: () -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF8FAFC)),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("${pick.name} ${pick.code}", color = Ink, fontWeight = FontWeight.Bold)
                    Text("老猫买入候选：T+2 开盘关注", color = Muted, fontSize = 12.sp)
                }
                Text("建议关注", color = RiseRed, fontWeight = FontWeight.Bold)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                QuoteCell("选股日收盘", pick.close.asPrice(), RiseRed, Modifier.weight(1f))
                QuoteCell("止损线", pick.stopLossPrice.asPrice(), FallGreen, Modifier.weight(1f))
                QuoteCell("止损率", pick.stopLossRateLabel(), if (pick.isBelowStopLoss()) FallGreen else RiseRed, Modifier.weight(1f))
            }
            Button(
                onClick = onBuyClick,
                modifier = Modifier.fillMaxWidth(),
                colors = ActionButtonColors()
            ) {
                Text("记录买入")
            }
        }
    }
}

@Composable
private fun TradeStatsCards(book: TradeBook) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("持仓", "${book.stats.holdingCount}", Ink, Modifier.weight(1f))
            MetricCard("历史交易", "${book.stats.totalTrades}", Ink, Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("累计盈亏", book.stats.totalProfitAmount.asPrice(), profitColor(book.stats.totalProfitAmount), Modifier.weight(1f))
            MetricCard("胜率", book.stats.winRate.asPercent(), RiseRed, Modifier.weight(1f))
        }
    }
}

@Composable
private fun TradePositionCard(
    position: TradePosition,
    onSell: (() -> Unit)?
) {
    val statusLabel = when {
        position.status == "closed" -> "已卖出"
        position.sellSignal -> "卖出"
        else -> "持有"
    }
    val statusColor = when {
        position.status == "closed" -> Muted
        position.sellSignal -> FallGreen
        else -> RiseRed
    }
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("${position.name} ${position.code}", color = Ink, fontWeight = FontWeight.Bold)
                    Text("${position.buyDate} 买入 / ${position.board.label}", color = Muted, fontSize = 12.sp)
                }
                Text(statusLabel, color = statusColor, fontWeight = FontWeight.Bold)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                QuoteCell("买入价", position.buyPrice.asPrice(), Ink, Modifier.weight(1f))
                QuoteCell("最新收盘", position.latestClose?.asPrice() ?: "暂无", RiseRed, Modifier.weight(1f))
                QuoteCell("止损线", position.stopLossPrice.asPrice(), FallGreen, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                QuoteCell("止损亏损率", position.stopLossLossPercent.asPercent(), FallGreen, Modifier.weight(1f))
                QuoteCell("浮动盈亏", position.unrealizedProfitAmount.asPrice(), profitColor(position.unrealizedProfitAmount), Modifier.weight(1f))
                QuoteCell("持仓", "${position.buyShares}股", Ink, Modifier.weight(1f))
            }
            position.latestTradeDate?.let {
                Text("行情日期 $it", color = Muted, fontSize = 12.sp)
            }
            if (position.status == "closed") {
                Text(
                    "卖出 ${position.sellDate.orEmpty()} / ${position.sellPrice?.asPrice() ?: "--"} / 盈亏 ${(position.profitAmount ?: 0.0).asPrice()}",
                    color = profitColor(position.profitAmount ?: 0.0),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
            }
            onSell?.let {
                Button(
                    onClick = it,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ActionButtonColors()
                ) {
                    Text("卖出")
                }
            }
        }
    }
}

@Composable
private fun StockPickCard(
    pick: StockPick,
    onBuyClick: () -> Unit,
    onClick: () -> Unit
) {
    val stopLossRateLabel = pick.stopLossRateLabel()
    val stopLossRateColor = if (pick.isBelowStopLoss()) FallGreen else RiseRed
    ElevatedCard(
        modifier = Modifier.clickable(onClick = onClick),
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${pick.name} ${pick.code}", color = Ink, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    Text("${pick.concept} · ${pick.board.label}", color = Muted, fontSize = 12.sp)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(pick.changePercent.asPercent(), color = RiseRed, fontWeight = FontWeight.Bold)
                    Text("进入", color = Muted, fontSize = 12.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                QuoteCell("收盘", pick.close.asPrice(), RiseRed, Modifier.weight(1f))
                QuoteCell("分时均线止损", pick.stopLossPrice.asPrice(), FallGreen, Modifier.weight(1f))
                QuoteCell("封单", "${pick.sealedAmountWan.roundToInt()}万", Ink, Modifier.weight(1f))
            }
            if (pick.limitShapeLabel.isNotBlank()) {
                Text("涨停形态：${pick.limitShapeLabel}", color = Muted, fontSize = 12.sp)
            }
            pick.latestClose?.let { latest ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    QuoteCell("最新收盘", latest.asPrice(), RiseRed, Modifier.weight(1f))
                    QuoteCell("止损率", stopLossRateLabel, stopLossRateColor, Modifier.weight(1f))
                }
                Text("行情日期 ${pick.latestTradeDate.orEmpty().ifBlank { "--" }}", color = Muted, fontSize = 12.sp)
                if (pick.isBelowStopLoss()) {
                    Text("最新收盘已低于止损价", color = FallGreen, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
            Button(
                onClick = onBuyClick,
                modifier = Modifier.fillMaxWidth(),
                colors = ActionButtonColors()
            ) {
                Text("买入")
            }
        }
    }
}

private fun StockPick.stopLossRateLabel(): String {
    val latest = latestClose ?: return "暂无"
    if (latest <= 0.0 || stopLossPrice <= 0.0) return "暂无"
    if (latest < stopLossPrice) return "跌破止损"
    return ((latest - stopLossPrice) / latest * 100.0).asPercent()
}

private fun StockPick.isBelowStopLoss(): Boolean {
    val latest = latestClose ?: return false
    return latest > 0.0 && stopLossPrice > 0.0 && latest < stopLossPrice
}

@Composable
private fun DailyKLineChart(
    candles: List<DailyCandle>,
    selectedIndex: Int,
    onSelected: (Int) -> Unit
) {
    if (candles.isEmpty()) {
        EmptyState("暂无 K 线数据")
        return
    }
    val minPrice = candles.minOf { it.low }
    val maxPrice = candles.maxOf { it.high }
    val range = max(0.01, maxPrice - minPrice)

    Canvas(
        modifier = Modifier
            .fillMaxWidth()
            .height(240.dp)
            .pointerInput(candles) {
                detectTapGestures { offset ->
                    val step = size.width / candles.size
                    val index = (offset.x / step).toInt().coerceIn(0, candles.lastIndex)
                    onSelected(index)
                }
            }
    ) {
        val chartHeight = size.height
        val step = size.width / candles.size
        val candleWidth = (step * 0.52f).coerceAtLeast(5.dp.toPx())

        repeat(4) { index ->
            val y = chartHeight * (index + 1) / 5f
            drawLine(
                color = Color(0xFFE5E7EB),
                start = Offset(0f, y),
                end = Offset(size.width, y),
                strokeWidth = 1.dp.toPx()
            )
        }

        candles.forEachIndexed { index, candle ->
            val centerX = step * index + step / 2f
            val openY = chartHeight - ((candle.open - minPrice) / range * chartHeight).toFloat()
            val closeY = chartHeight - ((candle.close - minPrice) / range * chartHeight).toFloat()
            val highY = chartHeight - ((candle.high - minPrice) / range * chartHeight).toFloat()
            val lowY = chartHeight - ((candle.low - minPrice) / range * chartHeight).toFloat()
            val color = if (candle.close >= candle.open) RiseRed else FallGreen
            val top = minOf(openY, closeY)
            val bottom = maxOf(openY, closeY)

            if (index == selectedIndex) {
                drawLine(
                    color = Color(0xFF111827),
                    start = Offset(centerX, 0f),
                    end = Offset(centerX, chartHeight),
                    strokeWidth = 1.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f))
                )
            }
            drawLine(
                color = color,
                start = Offset(centerX, highY),
                end = Offset(centerX, lowY),
                strokeWidth = 1.5.dp.toPx()
            )
            drawRect(
                color = color,
                topLeft = Offset(centerX - candleWidth / 2f, top),
                size = Size(candleWidth, max(2.dp.toPx(), bottom - top))
            )
        }
    }
}

@Composable
private fun CandleInfo(candle: DailyCandle) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF8FAFC)),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("选中日期：${candle.date}", color = Ink, fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("开 ${candle.open.asPrice()}", color = Muted, fontSize = 12.sp)
                Text("高 ${candle.high.asPrice()}", color = Muted, fontSize = 12.sp)
                Text("低 ${candle.low.asPrice()}", color = Muted, fontSize = 12.sp)
                Text("收 ${candle.close.asPrice()}", color = profitColor(candle.close - candle.open), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun IntradayStopChart(pick: StockPick) {
    val prices = pick.minuteTrades.map { it.price }
    val minPrice = minOf(prices.minOrNull() ?: pick.stopLossPrice, pick.stopLossPrice)
    val maxPrice = maxOf(prices.maxOrNull() ?: pick.stopLossPrice, pick.stopLossPrice)
    val range = max(0.01, maxPrice - minPrice)

    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("分时均价止损", color = Ink, fontWeight = FontWeight.Bold)
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(72.dp)
        ) {
            val xStep = if (prices.size <= 1) size.width else size.width / (prices.size - 1)
            val points = prices.mapIndexed { index, price ->
                Offset(
                    x = index * xStep,
                    y = size.height - ((price - minPrice) / range * size.height).toFloat()
                )
            }
            val stopY = size.height - ((pick.stopLossPrice - minPrice) / range * size.height).toFloat()

            drawLine(
                color = RiseRed,
                start = Offset(0f, stopY),
                end = Offset(size.width, stopY),
                strokeWidth = 2.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 8f))
            )
            points.zipWithNext().forEach { (start, end) ->
                drawLine(
                    color = Color(0xFF1F2937),
                    start = start,
                    end = end,
                    strokeWidth = 3.dp.toPx(),
                    cap = StrokeCap.Round
                )
            }
            points.forEach { point ->
                drawCircle(color = RiseRed, radius = 3.5.dp.toPx(), center = point)
            }
        }
        Text("红色虚线：涨停当日成交分时均价 ${pick.stopLossPrice.asPrice()}", color = Muted, fontSize = 12.sp)
    }
}

@Composable
private fun DateRangeControls(
    startDate: String,
    endDate: String,
    onStartDate: (String) -> Unit,
    onEndDate: (String) -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("回测区间", color = Ink, fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CalendarDateSelector("开始", startDate, onStartDate, Modifier.weight(1f))
                CalendarDateSelector("结束", endDate, onEndDate, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun StrategyControls(
    selectedStrategy: BacktestStrategy,
    onSelectedStrategy: (BacktestStrategy) -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("回测战法", color = Ink, fontWeight = FontWeight.Bold)
            BacktestStrategy.values().forEach { strategy ->
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onSelectedStrategy(strategy) },
                    color = if (selectedStrategy == strategy) Color(0xFFEFF6FF) else Color(0xFFF8FAFC),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(
                                strategy.title,
                                color = if (selectedStrategy == strategy) ChiNextBlue else Ink,
                                fontWeight = FontWeight.Bold
                            )
                            Text(strategy.description, color = Muted, fontSize = 12.sp, lineHeight = 17.sp)
                        }
                        Text(if (selectedStrategy == strategy) "已选择" else "选择", color = Muted, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun BacktestControls(
    holdingDays: Int,
    maxPositionsPerDay: Int,
    takeProfitText: String,
    volumeRatioText: String,
    allowBelowMarketMa25: Boolean,
    onHoldingDays: (Int) -> Unit,
    onMaxPositionsPerDay: (Int) -> Unit,
    onTakeProfit: (String) -> Unit,
    onVolumeRatio: (String) -> Unit,
    onAllowBelowMarketMa25: (Boolean) -> Unit,
    isRunning: Boolean,
    onRun: () -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("交易参数", color = Ink, fontWeight = FontWeight.Bold)
            Text("初始资金：100000 元", color = Muted, fontSize = 13.sp)
            OutlinedTextField(
                value = takeProfitText,
                onValueChange = { raw -> onTakeProfit(raw.filter { it.isDigit() || it == '.' }.take(5)) },
                label = { Text("止盈率 %") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = volumeRatioText,
                onValueChange = { raw -> onVolumeRatio(raw.filter { it.isDigit() || it == '.' }.take(4)) },
                label = { Text("回测量比放大") },
                supportingText = { Text("默认按量比大于 2 过滤，选股页也使用同一阈值") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth()
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("大盘跌破 25 日均线仍允许买入", color = Ink, fontWeight = FontWeight.Bold)
                    Text("关闭后，服务端有指数数据时会过滤弱势大盘环境。", color = Muted, fontSize = 12.sp)
                }
                Switch(
                    checked = allowBelowMarketMa25,
                    onCheckedChange = onAllowBelowMarketMa25
                )
            }
            Text("最大持有天数：$holdingDays 个工作日", color = Muted, fontSize = 13.sp)
            Slider(
                value = holdingDays.toFloat(),
                onValueChange = { onHoldingDays(it.roundToInt().coerceIn(1, 10)) },
                valueRange = 1f..10f,
                steps = 8
            )
            Text("同时买入数量：$maxPositionsPerDay 只", color = Muted, fontSize = 13.sp)
            Slider(
                value = maxPositionsPerDay.toFloat(),
                onValueChange = { onMaxPositionsPerDay(it.roundToInt().coerceIn(1, 10)) },
                valueRange = 1f..10f,
                steps = 8
            )
            Button(
                onClick = onRun,
                enabled = !isRunning &&
                    (takeProfitText.toDoubleOrNull() ?: 0.0) > 0.0 &&
                    (volumeRatioText.toDoubleOrNull() ?: 0.0) > 0.0,
                modifier = Modifier.fillMaxWidth(),
                colors = ActionButtonColors()
            ) {
                Text(if (isRunning) "回测中" else "开始回测")
            }
        }
    }
}

@Composable
private fun BacktestProgressCard() {
    Card(
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            CircularProgressIndicator(modifier = Modifier.size(28.dp), strokeWidth = 3.dp)
            Column {
                Text("正在回测", color = Ink, fontWeight = FontWeight.Bold)
                Text("正在按选定区间生成交易和每日操作", color = Muted, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun BacktestExperimentCard(
    result: BacktestExperimentResult?,
    error: String?,
    isRunning: Boolean,
    onRun: () -> Unit,
    onOpen: (BacktestExperimentItem) -> Unit
) {
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("策略实验", color = Ink, fontWeight = FontWeight.Bold)
                    Text("服务端一次回测多套老猫变体，按收益率排序。", color = Muted, fontSize = 12.sp)
                }
                if (isRunning) {
                    CircularProgressIndicator(modifier = Modifier.size(26.dp), strokeWidth = 3.dp)
                } else {
                    Button(
                        onClick = onRun,
                        colors = ActionButtonColors()
                    ) {
                        Text("开始实验")
                    }
                }
            }
            error?.let {
                Text("策略实验失败：$it", color = FallGreen, fontSize = 12.sp)
            }
            result?.items?.forEach { item ->
                BacktestExperimentRow(item = item, onOpen = { onOpen(item) })
            }
        }
    }
}

@Composable
private fun BacktestExperimentRow(
    item: BacktestExperimentItem,
    onOpen: () -> Unit
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Color(0xFFF8FAFC),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(item.strategyName, color = Ink, fontWeight = FontWeight.Bold)
                Text(item.description, color = Muted, fontSize = 12.sp, lineHeight = 17.sp)
                Text(
                    "收益 ${item.result.totalReturnPercent.asPercent()} · 回撤 ${item.result.maxDrawdownPercent.asPercent()} · 胜率 ${item.result.winRate.asPercent()} · ${item.result.totalTrades}笔",
                    color = profitColor(item.result.totalReturnPercent),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
            }
            TextButton(
                onClick = onOpen,
                colors = ButtonDefaults.textButtonColors(contentColor = ActionBlue)
            ) {
                Text("查看")
            }
        }
    }
}

@Composable
private fun BacktestHistoryList(
    history: List<BacktestHistoryEntry>,
    selectedId: String?,
    onOpen: (BacktestHistoryEntry) -> Unit,
    onDelete: (BacktestHistoryEntry) -> Unit
) {
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("历史回测", color = Ink, fontWeight = FontWeight.Bold)
            if (history.isEmpty()) {
                Text("暂无本地回测记录。每次回测完成后会自动保存到手机本地。", color = Muted, fontSize = 13.sp)
            } else {
                history.forEach { entry ->
                    BacktestHistoryRow(
                        entry = entry,
                        selected = entry.id == selectedId,
                        onOpen = { onOpen(entry) },
                        onDelete = { onDelete(entry) }
                    )
                }
            }
        }
    }
}

@Composable
private fun BacktestHistoryRow(
    entry: BacktestHistoryEntry,
    selected: Boolean,
    onOpen: () -> Unit,
    onDelete: () -> Unit
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = if (selected) Color(0xFFFFF1F2) else Color(0xFFF8FAFC),
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    "${entry.strategyName} ${entry.startDate} 至 ${entry.endDate}",
                    color = Ink,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    "${entry.createdAt} · ${entry.board?.label ?: "全部"} · 持有${entry.holdingDays}个工作日 · ${entry.result.totalTrades}笔",
                    color = Muted,
                    fontSize = 12.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    "累计收益 ${entry.result.totalReturnPercent.asPercent()} / 期末资金 ${entry.result.finalCapital.asPrice()}",
                    color = profitColor(entry.result.totalReturnPercent),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
            }
            TextButton(
                onClick = onOpen,
                colors = ButtonDefaults.textButtonColors(contentColor = ActionBlue)
            ) {
                Text("查看")
            }
            TextButton(onClick = onDelete) {
                Text("删除", color = FallGreen)
            }
        }
    }
}

@Composable
private fun BacktestSummary(result: BacktestResult) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("交易数", "${result.totalTrades}", Ink, Modifier.weight(1f))
            MetricCard("胜率", result.winRate.asPercent(), RiseRed, Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("累计收益", result.totalReturnPercent.asPercent(), profitColor(result.totalReturnPercent), Modifier.weight(1f))
            MetricCard("最大回撤", result.maxDrawdownPercent.asPercent(), FallGreen, Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("初始资金", result.initialCapital.asPrice(), Ink, Modifier.weight(1f))
            MetricCard("期末资金", result.finalCapital.asPrice(), profitColor(result.finalCapital - result.initialCapital), Modifier.weight(1f))
        }
    }
}

@Composable
private fun EquityCurveChart(points: List<EquityPoint>) {
    var selectedIndex by remember(points) { mutableIntStateOf(points.lastIndex.coerceAtLeast(0)) }
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("资金走势", color = Ink, fontWeight = FontWeight.Bold)
            if (points.size < 2) {
                Text("暂无足够数据绘制资金曲线。", color = Muted, fontSize = 13.sp)
                return@Column
            }
            val minCapital = points.minOf { it.capital }
            val maxCapital = points.maxOf { it.capital }
            val range = max(1.0, maxCapital - minCapital)
            val selectedPoint = points.getOrNull(selectedIndex)
            Canvas(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(180.dp)
                    .pointerInput(points) {
                        detectTapGestures { offset ->
                            selectedIndex = curveIndexForOffset(offset.x, size.width, points.lastIndex)
                        }
                    }
                    .pointerInput(points) {
                        detectDragGestures(
                            onDragStart = { offset ->
                                selectedIndex = curveIndexForOffset(offset.x, size.width, points.lastIndex)
                            },
                            onDrag = { change, _ ->
                                selectedIndex = curveIndexForOffset(change.position.x, size.width, points.lastIndex)
                            }
                        )
                    }
            ) {
                repeat(4) { index ->
                    val y = size.height * (index + 1) / 5f
                    drawLine(
                        color = Color(0xFFE5E7EB),
                        start = Offset(0f, y),
                        end = Offset(size.width, y),
                        strokeWidth = 1.dp.toPx()
                    )
                }
                val step = size.width / (points.size - 1)
                val chartPoints = points.mapIndexed { index, point ->
                    Offset(
                        x = index * step,
                        y = size.height - ((point.capital - minCapital) / range * size.height).toFloat()
                    )
                }
                chartPoints.zipWithNext().forEach { (start, end) ->
                    drawLine(
                        color = ChiNextBlue,
                        start = start,
                        end = end,
                        strokeWidth = 3.dp.toPx(),
                        cap = StrokeCap.Round
                    )
                }
                chartPoints.getOrNull(selectedIndex)?.let { point ->
                    drawLine(
                        color = RiseRed,
                        start = Offset(point.x, 0f),
                        end = Offset(point.x, size.height),
                        strokeWidth = 1.5.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f))
                    )
                    drawCircle(color = RiseRed, radius = 4.dp.toPx(), center = point)
                }
            }
            selectedPoint?.let {
                Text("${it.date} 余额 ${it.capital.asPrice()}", color = Ink, fontWeight = FontWeight.Bold, fontSize = 13.sp)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(points.first().date, color = Muted, fontSize = 12.sp, modifier = Modifier.weight(1f))
                Text(points.last().date, color = Muted, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun DailyOperations(trades: List<BacktestTrade>) {
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("每日操作", color = Ink, fontWeight = FontWeight.Bold)
            if (trades.isEmpty()) {
                Text("当前区间没有交易。", color = Muted, fontSize = 13.sp)
            } else {
                val operationDates = (trades.map { it.buyDate } + trades.map { it.sellDate }).distinct().sortedDescending()
                operationDates.forEach { date ->
                    val buys = trades.filter { it.buyDate == date }
                    val sells = trades.filter { it.sellDate == date }
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(date, color = Ink, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        buys.forEach { trade ->
                            Text(
                                "买入 ${trade.name} ${trade.code}，${trade.shares}股，买入价 ${trade.buyPrice.asPrice()}，买入额 ${trade.positionAmount.asPrice()}",
                                color = Muted,
                                fontSize = 12.sp,
                                lineHeight = 18.sp
                            )
                        }
                        sells.forEach { trade ->
                            Text(
                                "卖出 ${trade.name} ${trade.code}，${trade.shares}股，卖出价 ${trade.sellPrice.asPrice()}，盈亏 ${trade.profitAmount.asPrice()}",
                                color = profitColor(trade.profitAmount),
                                fontSize = 12.sp,
                                lineHeight = 18.sp
                            )
                        }
                    }
                    HorizontalDivider(color = Color(0xFFE5E7EB))
                }
            }
        }
    }
}

@Composable
private fun TradeCard(trade: BacktestTrade) {
    ElevatedCard(
        colors = CardDefaults.elevatedCardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${trade.name} ${trade.code}", fontWeight = FontWeight.Bold, color = Ink)
                    Text("${trade.buyDate} 买入 / ${trade.sellDate} 卖出", color = Muted, fontSize = 12.sp)
                }
                Text(
                    trade.returnPercent.asPercent(),
                    color = profitColor(trade.returnPercent),
                    fontWeight = FontWeight.Bold
                )
            }
            HorizontalDivider(color = Color(0xFFE5E7EB))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("买 ${trade.buyPrice.asPrice()}", color = Muted, fontSize = 12.sp)
                Text("卖 ${trade.sellPrice.asPrice()}", color = Muted, fontSize = 12.sp)
                Text("分时均线止损 ${trade.stopLossPrice.asPrice()}", color = Muted, fontSize = 12.sp)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("${trade.shares}股", color = Muted, fontSize = 12.sp)
                Text("买入额 ${trade.positionAmount.asPrice()}", color = Muted, fontSize = 12.sp)
                Text("盈亏 ${trade.profitAmount.asPrice()}", color = profitColor(trade.profitAmount), fontSize = 12.sp)
            }
            Text(trade.exitReason, color = Ink, fontSize = 13.sp)
        }
    }
}

@Composable
private fun CalendarDateSelector(
    title: String,
    value: String,
    onSelected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var showCalendar by remember { mutableStateOf(false) }
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .clickable { showCalendar = true },
        color = Panel,
        shape = RoundedCornerShape(8.dp),
        tonalElevation = 1.dp
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text(title, color = Muted, fontSize = 12.sp)
                Text(value, color = Ink, fontWeight = FontWeight.Bold)
            }
            Text("选择", color = ChiNextBlue, fontSize = 13.sp, fontWeight = FontWeight.Bold)
        }
    }

    if (showCalendar) {
        CalendarDialog(
            selectedDate = value,
            onDismiss = { showCalendar = false },
            onSelected = {
                showCalendar = false
                onSelected(it)
            }
        )
    }
}

@Composable
private fun CalendarDialog(
    selectedDate: String,
    onDismiss: () -> Unit,
    onSelected: (String) -> Unit
) {
    val initial = remember(selectedDate) { calendarFromDate(selectedDate) }
    var year by remember(selectedDate) { mutableIntStateOf(initial.get(Calendar.YEAR)) }
    var month by remember(selectedDate) { mutableIntStateOf(initial.get(Calendar.MONTH)) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Panel,
        titleContentColor = Ink,
        textContentColor = Ink,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = {
                    if (month == Calendar.JANUARY) {
                        year -= 1
                        month = Calendar.DECEMBER
                    } else {
                        month -= 1
                    }
                }) { Text("<") }
                Text(
                    "%04d-%02d".format(year, month + 1),
                    modifier = Modifier.weight(1f),
                    color = Ink,
                    fontWeight = FontWeight.Bold
                )
                TextButton(onClick = {
                    if (month == Calendar.DECEMBER) {
                        year += 1
                        month = Calendar.JANUARY
                    } else {
                        month += 1
                    }
                }) { Text(">") }
            }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row {
                    listOf("日", "一", "二", "三", "四", "五", "六").forEach { label ->
                        Text(label, modifier = Modifier.weight(1f), color = Muted, fontSize = 12.sp)
                    }
                }
                calendarCells(year, month).chunked(7).forEach { week ->
                    Row {
                        week.forEach { day ->
                            if (day == null) {
                                Spacer(
                                    Modifier
                                        .weight(1f)
                                        .height(42.dp)
                                )
                            } else {
                                val date = formatDate(year, month, day)
                                val isSelected = date == selectedDate
                                Box(
                                    modifier = Modifier
                                        .weight(1f)
                                        .height(42.dp),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Surface(
                                        modifier = Modifier
                                            .size(36.dp)
                                            .clickable { onSelected(date) },
                                        shape = CircleShape,
                                        color = if (isSelected) RiseRed else Color.Transparent
                                    ) {
                                        Box(contentAlignment = Alignment.Center) {
                                            Text(
                                                day.toString(),
                                                color = if (isSelected) Color.White else Ink,
                                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onSelected(todayDateString()) }) {
                Text("今天")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("取消")
            }
        }
    )
}

@Composable
private fun DateDropdown(
    title: String,
    value: String,
    options: List<String>,
    onSelected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var expanded by remember { mutableStateOf(false) }
    Box(modifier) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(enabled = options.isNotEmpty()) { expanded = true },
            color = Panel,
            shape = RoundedCornerShape(8.dp),
            tonalElevation = 1.dp
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text(title, color = Muted, fontSize = 12.sp)
                    Text(value.ifEmpty { "暂无日期" }, color = Ink, fontWeight = FontWeight.Bold)
                }
                Text("▼", color = Muted, fontSize = 12.sp)
            }
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false }
        ) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        expanded = false
                        onSelected(option)
                    }
                )
            }
        }
    }
}

private fun todayDateString(): String {
    return SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Calendar.getInstance().time)
}

private fun curveIndexForOffset(x: Float, width: Int, lastIndex: Int): Int {
    if (lastIndex <= 0 || width <= 0) return 0
    val step = width.toFloat() / lastIndex
    return (x / step).roundToInt().coerceIn(0, lastIndex)
}

private fun nowDateTimeString(): String {
    return SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
}

private fun dateMonthsBefore(value: String, months: Int): String {
    val calendar = calendarFromDate(value)
    calendar.add(Calendar.MONTH, -months)
    return SimpleDateFormat("yyyy-MM-dd", Locale.US).format(calendar.time)
}

private fun calendarFromDate(value: String): Calendar {
    val calendar = Calendar.getInstance()
    runCatching {
        SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(value)
    }.getOrNull()?.let { calendar.time = it }
    return calendar
}

private fun calendarCells(year: Int, month: Int): List<Int?> {
    val calendar = Calendar.getInstance().apply {
        set(Calendar.YEAR, year)
        set(Calendar.MONTH, month)
        set(Calendar.DAY_OF_MONTH, 1)
    }
    val offset = calendar.get(Calendar.DAY_OF_WEEK) - Calendar.SUNDAY
    val maxDay = calendar.getActualMaximum(Calendar.DAY_OF_MONTH)
    return List(offset) { null } + (1..maxDay).toList()
}

private fun formatDate(year: Int, month: Int, day: Int): String {
    return "%04d-%02d-%02d".format(year, month + 1, day)
}

private fun trimDoubleText(value: Double): String {
    val raw = "%.2f".format(value)
    return raw.trimEnd('0').trimEnd('.')
}

@Composable
private fun AppHeader(title: String, subtitle: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF14213D)),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(38.dp)
                        .background(RiseRed, CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Text("富", color = Color.White, fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.width(10.dp))
                Column {
                    Text(title, color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                    Text("A 股涨停战法工具", color = Color(0xFFBFD7EA), fontSize = 12.sp)
                }
            }
            Text(subtitle, color = Color(0xFFE5E7EB), fontSize = 13.sp, lineHeight = 19.sp)
        }
    }
}

@Composable
private fun MetricCard(label: String, value: String, accent: Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(label, color = Muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(value, color = accent, fontWeight = FontWeight.Bold, fontSize = 18.sp)
        }
    }
}

@Composable
private fun QuoteCell(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, color = Muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(value, color = color, fontWeight = FontWeight.Bold, maxLines = 1)
    }
}

@Composable
private fun EmptyState(message: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(8.dp)
    ) {
        Text(
            text = message,
            modifier = Modifier.padding(18.dp),
            color = Muted,
            lineHeight = 20.sp
        )
    }
}

@Composable
private fun ErrorState(message: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF1F2)),
        shape = RoundedCornerShape(8.dp)
    ) {
        Text(
            text = message,
            modifier = Modifier.padding(18.dp),
            color = Color(0xFF9F1239),
            lineHeight = 20.sp
        )
    }
}

private fun profitColor(value: Double): Color {
    return if (value >= 0.0) RiseRed else FallGreen
}

@Preview(showBackground = true)
@Composable
private fun StockAppPreview() {
    MyApplicationTheme(dynamicColor = false) {
        StockApp()
    }
}
