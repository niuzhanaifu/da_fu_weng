from __future__ import annotations

import json
import sqlite3
from typing import Iterable

from .schemas import DailyCandleOut, DailyQuoteIn, MarketBoard, MinuteTrade, StockPickOut


def upsert_daily_quotes(conn: sqlite3.Connection, quotes: Iterable[DailyQuoteIn]) -> int:
    count = 0
    for quote in quotes:
        conn.execute(
            """
            INSERT INTO daily_quotes (
                trade_date, code, name, board, concept, previous_close, open, high, low, close,
                volume_ratio, turnover_rate, sealed_amount_wan, next_open, future_closes_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(trade_date, code) DO UPDATE SET
                name=excluded.name,
                board=excluded.board,
                concept=excluded.concept,
                previous_close=excluded.previous_close,
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume_ratio=excluded.volume_ratio,
                turnover_rate=excluded.turnover_rate,
                sealed_amount_wan=excluded.sealed_amount_wan,
                next_open=excluded.next_open,
                future_closes_json=excluded.future_closes_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                quote.trade_date,
                quote.code,
                quote.name,
                quote.board.value,
                quote.concept,
                quote.previous_close,
                quote.open,
                quote.high,
                quote.low,
                quote.close,
                quote.volume_ratio,
                quote.turnover_rate,
                quote.sealed_amount_wan,
                quote.next_open,
                json.dumps(quote.future_closes, ensure_ascii=False),
            ),
        )
        conn.execute(
            "DELETE FROM minute_trades WHERE trade_date = ? AND code = ?",
            (quote.trade_date, quote.code),
        )
        conn.executemany(
            """
            INSERT INTO minute_trades (trade_date, code, minute, price, volume)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (quote.trade_date, quote.code, trade.minute, trade.price, trade.volume)
                for trade in quote.minute_trades
            ],
        )
        count += 1
    conn.commit()
    return count


def upsert_market_index_quotes(conn: sqlite3.Connection, quotes: Iterable[tuple[str, str, float]]) -> int:
    count = 0
    for trade_date, code, close in quotes:
        conn.execute(
            """
            INSERT INTO market_index_quotes (trade_date, code, close)
            VALUES (?, ?, ?)
            ON CONFLICT(trade_date, code) DO UPDATE SET
                close=excluded.close
            """,
            (trade_date, code, close),
        )
        count += 1
    conn.commit()
    return count


def load_quotes(conn: sqlite3.Connection, trade_date: str) -> list[DailyQuoteIn]:
    rows = conn.execute(
        """
        SELECT * FROM daily_quotes
        WHERE trade_date = ?
        ORDER BY board, sealed_amount_wan DESC
        """,
        (trade_date,),
    ).fetchall()
    minute_rows = conn.execute(
        """
        SELECT code, minute, price, volume
        FROM minute_trades
        WHERE trade_date = ?
        ORDER BY code, minute
        """,
        (trade_date,),
    ).fetchall()
    minutes_by_code: dict[str, list[MinuteTrade]] = {}
    for item in minute_rows:
        minutes_by_code.setdefault(item["code"], []).append(
            MinuteTrade(minute=item["minute"], price=item["price"], volume=item["volume"])
        )

    return [row_to_quote(row, minutes_by_code.get(row["code"], [])) for row in rows]


def count_quotes(conn: sqlite3.Connection, trade_date: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM daily_quotes WHERE trade_date = ?",
        (trade_date,),
    ).fetchone()
    return int(row["count"]) if row else 0


def latest_quote_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(trade_date) AS trade_date FROM daily_quotes").fetchone()
    return row["trade_date"] if row else None


def latest_quote_date_on_or_before(conn: sqlite3.Connection, trade_date: str) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(trade_date) AS trade_date
        FROM daily_quotes
        WHERE trade_date <= ?
        """,
        (trade_date,),
    ).fetchone()
    return row["trade_date"] if row else None


def previous_quote_date(conn: sqlite3.Connection, trade_date: str) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(trade_date) AS trade_date
        FROM daily_quotes
        WHERE trade_date < ?
        """,
        (trade_date,),
    ).fetchone()
    return row["trade_date"] if row else None


def quote_dates_between(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT trade_date
        FROM daily_quotes
        WHERE (? IS NULL OR trade_date >= ?)
          AND (? IS NULL OR trade_date <= ?)
        ORDER BY trade_date ASC
        """,
        (start_date, start_date, end_date, end_date),
    ).fetchall()
    return [row["trade_date"] for row in rows]


def future_prices(
    conn: sqlite3.Connection,
    code: str,
    trade_date: str,
    limit: int,
) -> tuple[float | None, list[float]]:
    rows = conn.execute(
        """
        SELECT open, close
        FROM daily_quotes
        WHERE code = ?
          AND trade_date > ?
        ORDER BY trade_date ASC
        LIMIT ?
        """,
        (code, trade_date, max(1, limit)),
    ).fetchall()
    next_open = rows[0]["open"] if rows else None
    future_closes = [row["close"] for row in rows]
    return next_open, future_closes


def future_bars(
    conn: sqlite3.Connection,
    code: str,
    trade_date: str,
    limit: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT trade_date, open, high, close
        FROM daily_quotes
        WHERE code = ?
          AND trade_date > ?
        ORDER BY trade_date ASC
        LIMIT ?
        """,
        (code, trade_date, max(1, limit)),
    ).fetchall()


def latest_quote_for_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT trade_date, close
        FROM daily_quotes
        WHERE code = ?
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        (code,),
    ).fetchone()


def previous_quote_for_code(conn: sqlite3.Connection, code: str, trade_date: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT board, previous_close, high, close
        FROM daily_quotes
        WHERE code = ?
          AND trade_date < ?
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        (code, trade_date),
    ).fetchone()


def market_index_above_ma25(conn: sqlite3.Connection, code: str, trade_date: str) -> bool:
    rows = conn.execute(
        """
        SELECT close
        FROM market_index_quotes
        WHERE code = ?
          AND trade_date <= ?
        ORDER BY trade_date DESC
        LIMIT 25
        """,
        (code, trade_date),
    ).fetchall()
    if len(rows) < 25:
        return True
    latest = rows[0]["close"]
    ma25 = sum(row["close"] for row in rows) / len(rows)
    return latest >= ma25


def recent_change_percent(
    conn: sqlite3.Connection,
    code: str,
    trade_date: str,
    days: int = 3,
) -> float:
    rows = conn.execute(
        """
        SELECT close
        FROM daily_quotes
        WHERE code = ?
          AND trade_date <= ?
        ORDER BY trade_date DESC
        LIMIT ?
        """,
        (code, trade_date, days + 1),
    ).fetchall()
    if len(rows) < 2:
        return 0.0
    latest = rows[0]["close"]
    base = rows[-1]["close"]
    if base <= 0:
        return 0.0
    return (latest - base) / base * 100.0


def clear_selection_results(conn: sqlite3.Connection) -> int:
    pick_count = conn.execute("SELECT COUNT(*) AS count FROM stock_picks").fetchone()["count"]
    run_count = conn.execute("SELECT COUNT(*) AS count FROM selection_runs").fetchone()["count"]
    conn.execute("DELETE FROM stock_picks")
    conn.execute("DELETE FROM selection_runs")
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    return int(pick_count) + int(run_count)


def latest_run_for_date(conn: sqlite3.Connection, trade_date: str | None = None) -> sqlite3.Row | None:
    if trade_date:
        return conn.execute(
            """
            SELECT * FROM selection_runs
            WHERE trade_date = ?
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (trade_date,),
        ).fetchone()
    return conn.execute(
        """
        SELECT * FROM selection_runs
        ORDER BY trade_date DESC, generated_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()


def load_picks_for_run(conn: sqlite3.Connection, run_id: int) -> list[StockPickOut]:
    rows = conn.execute(
        """
        SELECT * FROM stock_picks
        WHERE run_id = ?
        ORDER BY board, sealed_amount_wan DESC
        """,
        (run_id,),
    ).fetchall()
    return [row_to_pick(conn, row) for row in rows]


def load_picks_for_backtest(
    conn: sqlite3.Connection,
    start_date: str | None,
    end_date: str | None,
) -> list[StockPickOut]:
    sql = """
        SELECT sp.*
        FROM stock_picks sp
        JOIN (
            SELECT trade_date, MAX(id) AS run_id
            FROM selection_runs
            GROUP BY trade_date
        ) latest ON latest.run_id = sp.run_id
        WHERE (? IS NULL OR sp.trade_date >= ?)
          AND (? IS NULL OR sp.trade_date <= ?)
        ORDER BY sp.trade_date ASC, sp.board, sp.sealed_amount_wan DESC
    """
    rows = conn.execute(sql, (start_date, start_date, end_date, end_date)).fetchall()
    return [row_to_pick(conn, row) for row in rows]


def load_daily_candles(
    conn: sqlite3.Connection,
    code: str,
    start_date: str | None,
    end_date: str | None,
    limit: int,
) -> list[DailyCandleOut]:
    rows = conn.execute(
        """
        SELECT trade_date, code, name, board, open, high, low, close, previous_close
        FROM daily_quotes
        WHERE code = ?
          AND (? IS NULL OR trade_date >= ?)
          AND (? IS NULL OR trade_date <= ?)
        ORDER BY trade_date DESC
        LIMIT ?
        """,
        (code, start_date, start_date, end_date, end_date, limit),
    ).fetchall()
    return [
        DailyCandleOut(
            trade_date=row["trade_date"],
            code=row["code"],
            name=row["name"],
            board=MarketBoard(row["board"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            previous_close=row["previous_close"],
        )
        for row in rows
    ][::-1]


def row_to_quote(row: sqlite3.Row, minute_trades: list[MinuteTrade]) -> DailyQuoteIn:
    return DailyQuoteIn(
        trade_date=row["trade_date"],
        code=row["code"],
        name=row["name"],
        board=MarketBoard(row["board"]),
        concept=row["concept"],
        previous_close=row["previous_close"],
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume_ratio=row["volume_ratio"],
        turnover_rate=row["turnover_rate"],
        sealed_amount_wan=row["sealed_amount_wan"],
        next_open=row["next_open"],
        future_closes=json.loads(row["future_closes_json"]),
        minute_trades=minute_trades,
    )


def row_to_pick(conn: sqlite3.Connection, row: sqlite3.Row) -> StockPickOut:
    minute_rows = conn.execute(
        """
        SELECT minute, price, volume
        FROM minute_trades
        WHERE trade_date = ? AND code = ?
        ORDER BY minute
        """,
        (row["trade_date"], row["code"]),
    ).fetchall()
    board = MarketBoard(row["board"])
    latest = latest_quote_for_code(conn, row["code"])
    return StockPickOut(
        trade_date=row["trade_date"],
        code=row["code"],
        name=row["name"],
        board=board,
        board_label=board.label,
        concept=row["concept"],
        close=row["close"],
        change_percent=row["change_percent"],
        volume_ratio=row["volume_ratio"],
        turnover_rate=row["turnover_rate"],
        sealed_amount_wan=row["sealed_amount_wan"],
        stop_loss_price=row["stop_loss_price"],
        limit_shape=row["limit_shape"] if "limit_shape" in row.keys() else "",
        limit_shape_label=row["limit_shape_label"] if "limit_shape_label" in row.keys() else "",
        latest_trade_date=latest["trade_date"] if latest else None,
        latest_close=latest["close"] if latest else None,
        next_open=row["next_open"],
        future_closes=json.loads(row["future_closes_json"]),
        future_highs=[],
        future_opens=[],
        future_dates=[],
        recent_3day_change_percent=0.0,
        recent_5day_change_percent=0.0,
        minute_trades=[
            MinuteTrade(minute=item["minute"], price=item["price"], volume=item["volume"])
            for item in minute_rows
        ],
    )
