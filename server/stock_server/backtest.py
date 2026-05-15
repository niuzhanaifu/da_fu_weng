from __future__ import annotations

from typing import Sequence

from .schemas import BacktestResultOut, BacktestTradeOut, StockPickOut


def run_backtest(
    picks: Sequence[StockPickOut],
    holding_days: int,
    take_profit_percent: float,
    strategy_id: str = "old_cat",
) -> BacktestResultOut:
    if strategy_id != "old_cat":
        raise ValueError(f"Unsupported backtest strategy: {strategy_id}")

    trades = [
        simulate_old_cat_trade(pick, holding_days=holding_days)
        for pick in picks
        if pick.next_open is not None
    ]
    trades = [trade for trade in trades if trade is not None]
    if not trades:
        return BacktestResultOut(
            total_trades=0,
            win_rate=0.0,
            total_return_percent=0.0,
            max_drawdown_percent=0.0,
            trades=[],
        )

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for trade in trades:
        equity *= 1.0 + trade.return_percent / 100.0
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)

    return BacktestResultOut(
        total_trades=len(trades),
        win_rate=sum(1 for trade in trades if trade.return_percent > 0.0) / len(trades) * 100.0,
        total_return_percent=(equity - 1.0) * 100.0,
        max_drawdown_percent=max_drawdown,
        trades=sorted(trades, key=lambda item: item.buy_date, reverse=True),
    )


def simulate_old_cat_trade(
    pick: StockPickOut,
    holding_days: int,
) -> BacktestTradeOut | None:
    """
    老猫战法：
    1. 涨停板次日开盘 1 分钟后观察价格。
       当前数据结构用 next_open 承载这个价格；接真实行情后应写入次日 09:31 价格。
    2. 如果该价格相对涨停板当天收盘价涨幅不超过 3%，买入。
    3. 止损价为涨停板当天的成交分时均价。
    4. 触发止损则卖出，否则持有到配置天数卖出。
    """
    buy_price = pick.next_open if pick.next_open is not None else pick.close
    if buy_price > pick.close * 1.03:
        return None

    future_closes = pick.future_closes[: max(1, holding_days)]
    if not future_closes:
        future_closes = [pick.close]

    sell_price = future_closes[-1]
    sell_index = len(future_closes) - 1
    exit_reason = "老猫战法：持有到期"

    for index, close in enumerate(future_closes):
        if close <= pick.stop_loss_price:
            sell_price = close
            sell_index = index
            exit_reason = "老猫战法：分时均价止损"
            break

    return BacktestTradeOut(
        code=pick.code,
        name=pick.name,
        board=pick.board,
        buy_date=pick.trade_date,
        sell_date=f"T+{sell_index + 1}",
        buy_price=buy_price,
        sell_price=sell_price,
        stop_loss_price=pick.stop_loss_price,
        return_percent=(sell_price - buy_price) / buy_price * 100.0,
        exit_reason=exit_reason,
    )
