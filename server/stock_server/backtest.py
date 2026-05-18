from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .schemas import BacktestResultOut, BacktestTradeOut, EquityPointOut, StockPickOut


LOT_SIZE = 100
RANK_MODE_RECENT_5DAY_CHANGE = "recent_5day_change"
RANK_MODE_STOP_LOSS_LOSS = "stop_loss_loss"


class BacktestStrategy(Protocol):
    id: str

    def simulate_trade(self, pick: StockPickOut, holding_days: int, take_profit_percent: float) -> BacktestTradeOut | None:
        ...


@dataclass(frozen=True)
class OldCatStrategy:
    id: str = "old_cat"

    def simulate_trade(self, pick: StockPickOut, holding_days: int, take_profit_percent: float) -> BacktestTradeOut | None:
        if len(pick.future_opens) < 3 or len(pick.future_closes) < 3 or len(pick.future_dates) < 3:
            return None

        buy_price = pick.future_opens[1]
        if buy_price is None or buy_price <= 0:
            return None
        if buy_price > pick.close * 1.05:
            return None

        sell_window_end = 2 + max(1, holding_days)
        future_closes = pick.future_closes[2:sell_window_end]
        future_highs = pick.future_highs[2 : 2 + len(future_closes)]
        future_lows = pick.future_lows[2 : 2 + len(future_closes)]
        future_dates = pick.future_dates[2 : 2 + len(future_closes)]
        if not future_closes:
            return None

        sell_price = future_closes[-1]
        sell_index = len(future_closes) - 1
        exit_reason = "老猫战法：持有到期"
        take_profit_price = buy_price * (1.0 + take_profit_percent / 100.0)

        for index, close in enumerate(future_closes):
            low = future_lows[index] if index < len(future_lows) else close
            if low <= pick.stop_loss_price:
                high = future_highs[index] if index < len(future_highs) else close
                sell_price = pick.stop_loss_price if pick.stop_loss_price <= high else close
                sell_index = index
                exit_reason = "老猫战法：分时均价止损" if pick.stop_loss_price <= high else "老猫战法：全天低于止损线"
                break
            high = future_highs[index] if index < len(future_highs) else close
            if high >= take_profit_price:
                sell_price = take_profit_price
                sell_index = index
                exit_reason = f"老猫战法：涨幅达到{take_profit_percent:.0f}%强制平仓"
                break

        return BacktestTradeOut(
            code=pick.code,
            name=pick.name,
            board=pick.board,
            buy_date=pick.future_dates[1],
            sell_date=future_dates[sell_index] if sell_index < len(future_dates) else f"T+{sell_index + 1}",
            buy_price=buy_price,
            sell_price=sell_price,
            stop_loss_price=pick.stop_loss_price,
            return_percent=(sell_price - buy_price) / buy_price * 100.0,
            exit_reason=exit_reason,
        )


STRATEGIES: dict[str, BacktestStrategy] = {
    "old_cat": OldCatStrategy(),
}


@dataclass
class OpenPosition:
    trade: BacktestTradeOut
    shares: int

    @property
    def sell_value(self) -> float:
        return self.trade.sell_price * self.shares

    @property
    def profit_amount(self) -> float:
        return (self.trade.sell_price - self.trade.buy_price) * self.shares


@dataclass(frozen=True)
class PlannedTrade:
    trade: BacktestTradeOut
    rank_value: float


def run_backtest(
    picks: Sequence[StockPickOut],
    holding_days: int,
    take_profit_percent: float,
    strategy_id: str = "old_cat",
    initial_capital: float = 100000.0,
    max_positions_per_day: int = 3,
    rank_mode: str = RANK_MODE_RECENT_5DAY_CHANGE,
    max_position_allocation_fraction: float | None = None,
) -> BacktestResultOut:
    strategy = STRATEGIES.get(strategy_id)
    if strategy is None:
        raise ValueError(f"Unsupported backtest strategy: {strategy_id}")

    cash = initial_capital
    open_positions: list[OpenPosition] = []
    closed_trades: list[BacktestTradeOut] = []
    equity = initial_capital
    peak = initial_capital
    max_drawdown = 0.0
    equity_curve: list[EquityPointOut] = []

    picks_by_date = group_picks_by_date(picks)
    planned_trades_by_date: dict[str, list[PlannedTrade]] = {}
    for trade_date, day_picks in picks_by_date.items():
        for pick in rank_daily_picks(day_picks):
            trade = strategy.simulate_trade(
                pick,
                holding_days=holding_days,
                take_profit_percent=take_profit_percent,
            )
            if trade is not None:
                planned_trades_by_date.setdefault(trade.buy_date, []).append(
                    PlannedTrade(
                        trade=trade,
                        rank_value=trade_rank_value(pick, trade, rank_mode),
                    )
                )

    all_dates = sorted(
        set(picks_by_date.keys())
        | set(planned_trades_by_date.keys())
        | {date for pick in picks for date in pick.future_dates}
    )
    for trade_date in all_dates:
        candidates = [
            planned.trade
            for planned in rank_planned_trades(planned_trades_by_date.get(trade_date, []))[:max_positions_per_day]
        ]
        if candidates:
            total_assets = cash + sum(position.trade.buy_price * position.shares for position in open_positions)
            allocation = position_allocation(cash, total_assets, len(candidates), max_position_allocation_fraction)
            for trade in candidates:
                shares = affordable_lot_shares(allocation, trade.buy_price)
                if shares <= 0 or cash < shares * trade.buy_price:
                    continue
                cash -= shares * trade.buy_price
                trade.shares = shares
                trade.position_amount = shares * trade.buy_price
                open_positions.append(OpenPosition(trade=trade, shares=shares))

        cash, sold = close_due_positions(cash, open_positions, trade_date)
        closed_trades.extend(sold)

        equity = cash + sum(position.trade.buy_price * position.shares for position in open_positions)
        equity_curve.append(EquityPointOut(trade_date=trade_date, capital=equity))
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)

    for position in open_positions:
        position.trade.profit_amount = position.profit_amount
        closed_trades.append(position.trade)
        cash += position.sell_value

    final_capital = cash
    if all_dates:
        final_point = EquityPointOut(trade_date=all_dates[-1], capital=final_capital)
        if equity_curve and equity_curve[-1].trade_date == final_point.trade_date:
            equity_curve[-1] = final_point
        else:
            equity_curve.append(final_point)
    total_return_percent = ((final_capital - initial_capital) / initial_capital * 100.0) if initial_capital > 0 else 0.0
    if not closed_trades:
        return BacktestResultOut(
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_trades=0,
            win_rate=0.0,
            total_return_percent=total_return_percent,
            max_drawdown_percent=max_drawdown,
            trades=[],
            equity_curve=equity_curve,
        )

    return BacktestResultOut(
        initial_capital=initial_capital,
        final_capital=final_capital,
        total_trades=len(closed_trades),
        win_rate=sum(1 for trade in closed_trades if trade.return_percent > 0.0) / len(closed_trades) * 100.0,
        total_return_percent=total_return_percent,
        max_drawdown_percent=max_drawdown,
        trades=sorted(closed_trades, key=lambda item: item.buy_date, reverse=True),
        equity_curve=equity_curve,
    )


def group_picks_by_date(picks: Sequence[StockPickOut]) -> dict[str, list[StockPickOut]]:
    result: dict[str, list[StockPickOut]] = {}
    for pick in picks:
        result.setdefault(pick.trade_date, []).append(pick)
    return result


def rank_daily_picks(picks: Sequence[StockPickOut]) -> list[StockPickOut]:
    return sorted(picks, key=lambda item: (item.recent_5day_change_percent, item.code))


def rank_planned_trades(planned_trades: Sequence[PlannedTrade]) -> list[PlannedTrade]:
    return sorted(planned_trades, key=lambda item: (item.rank_value, item.trade.code))


def trade_rank_value(pick: StockPickOut, trade: BacktestTradeOut, rank_mode: str) -> float:
    if rank_mode == RANK_MODE_RECENT_5DAY_CHANGE:
        return pick.recent_5day_change_percent
    if rank_mode == RANK_MODE_STOP_LOSS_LOSS:
        return stop_loss_loss_percent(trade)
    raise ValueError(f"Unsupported backtest rank mode: {rank_mode}")


def stop_loss_loss_percent(trade: BacktestTradeOut) -> float:
    if trade.buy_price <= 0 or trade.stop_loss_price <= 0:
        return float("inf")
    return max(0.0, (trade.buy_price - trade.stop_loss_price) / trade.buy_price * 100.0)


def close_due_positions(
    cash: float,
    open_positions: list[OpenPosition],
    trade_date: str,
) -> tuple[float, list[BacktestTradeOut]]:
    remaining: list[OpenPosition] = []
    sold: list[BacktestTradeOut] = []
    for position in open_positions:
        if position.trade.sell_date <= trade_date:
            position.trade.profit_amount = position.profit_amount
            cash += position.sell_value
            sold.append(position.trade)
        else:
            remaining.append(position)
    open_positions[:] = remaining
    return cash, sold


def position_allocation(
    cash: float,
    total_assets: float,
    candidate_count: int,
    max_fraction: float | None,
) -> float:
    if candidate_count <= 0:
        return 0.0
    allocation = cash / candidate_count
    if max_fraction is not None:
        allocation = min(allocation, total_assets * max_fraction)
    return allocation


def affordable_lot_shares(allocation: float, buy_price: float) -> int:
    if buy_price <= 0:
        return 0
    lots = int(allocation // (buy_price * LOT_SIZE))
    return lots * LOT_SIZE
