from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class MarketBoard(str, Enum):
    main = "main"
    chinext = "chinext"

    @property
    def label(self) -> str:
        return "主板" if self is MarketBoard.main else "创业板"

    @property
    def limit_up_rate(self) -> float:
        return 0.10 if self is MarketBoard.main else 0.20


class MinuteTrade(BaseModel):
    minute: str
    price: float
    volume: int = 0


class DailyQuoteIn(BaseModel):
    trade_date: str
    code: str
    name: str
    board: MarketBoard
    concept: str = ""
    previous_close: float
    open: float
    high: float
    low: float
    close: float
    volume_ratio: float = 0
    turnover_rate: float = 0
    sealed_amount_wan: float = 0
    next_open: Optional[float] = None
    future_closes: List[float] = Field(default_factory=list)
    minute_trades: List[MinuteTrade] = Field(default_factory=list)


class IndicatorOption(BaseModel):
    id: str
    name: str
    description: str


class SelectionStrategyOption(BaseModel):
    id: str
    name: str
    description: str


class StockPickOut(BaseModel):
    trade_date: str
    code: str
    name: str
    board: MarketBoard
    board_label: str
    concept: str
    close: float
    change_percent: float
    volume_ratio: float
    turnover_rate: float
    sealed_amount_wan: float
    stop_loss_price: float
    limit_shape: str = ""
    limit_shape_label: str = ""
    latest_trade_date: Optional[str] = None
    latest_close: Optional[float] = None
    next_open: Optional[float]
    future_closes: List[float]
    future_highs: List[float] = Field(default_factory=list)
    future_opens: List[float] = Field(default_factory=list)
    future_dates: List[str] = Field(default_factory=list)
    recent_3day_change_percent: float = 0.0
    recent_5day_change_percent: float = 0.0
    minute_trades: List[MinuteTrade] = Field(default_factory=list)


class DailyCandleOut(BaseModel):
    trade_date: str
    code: str
    name: str
    board: MarketBoard
    open: float
    high: float
    low: float
    close: float
    previous_close: float


class DailyGroupOut(BaseModel):
    trade_date: str
    generated_at: str
    indicator_ids: List[str]
    main_count: int
    chinext_count: int
    picks: List[StockPickOut]


class SelectionRequest(BaseModel):
    trade_date: Optional[str] = None
    strategy_id: str = "old_cat_buy"
    indicator_ids: List[str] = Field(default_factory=lambda: ["volume", "seal", "close"])


class BacktestRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    strategy_id: str = Field(default="old_cat")
    board: Optional[MarketBoard] = None
    initial_capital: float = Field(default=100000.0, ge=0.0)
    max_positions_per_day: int = Field(default=3, ge=1, le=20)
    holding_days: int = Field(default=3, ge=1, le=10)
    take_profit_percent: float = Field(default=10.0, ge=0.1, le=50.0)
    allow_below_market_ma25: bool = True


class BacktestTradeOut(BaseModel):
    code: str
    name: str
    board: MarketBoard
    buy_date: str
    sell_date: str
    buy_price: float
    sell_price: float
    shares: int = 0
    position_amount: float = 0.0
    profit_amount: float = 0.0
    partial_sell_date: Optional[str] = None
    partial_sell_price: Optional[float] = None
    partial_sell_ratio: float = 0.0
    stop_loss_price: float
    return_percent: float
    exit_reason: str


class EquityPointOut(BaseModel):
    trade_date: str
    capital: float


class BacktestResultOut(BaseModel):
    initial_capital: float = 0.0
    final_capital: float = 0.0
    total_trades: int
    win_rate: float
    total_return_percent: float
    max_drawdown_percent: float
    trades: List[BacktestTradeOut]
    equity_curve: List[EquityPointOut] = Field(default_factory=list)


class BacktestExperimentItemOut(BaseModel):
    strategy_id: str
    strategy_name: str
    description: str
    result: BacktestResultOut


class BacktestExperimentOut(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    board: Optional[MarketBoard] = None
    items: List[BacktestExperimentItemOut]


class SelectionRunOut(BaseModel):
    trade_date: str
    run_id: int
    generated_at: str
    pick_count: int
    indicator_ids: List[str]
