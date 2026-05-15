from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from .config import settings


def connect() -> sqlite3.Connection:
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                board TEXT NOT NULL,
                concept TEXT NOT NULL DEFAULT '',
                previous_close REAL NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume_ratio REAL NOT NULL DEFAULT 0,
                turnover_rate REAL NOT NULL DEFAULT 0,
                sealed_amount_wan REAL NOT NULL DEFAULT 0,
                next_open REAL,
                future_closes_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(trade_date, code)
            );

            CREATE TABLE IF NOT EXISTS minute_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                code TEXT NOT NULL,
                minute TEXT NOT NULL,
                price REAL NOT NULL,
                volume INTEGER NOT NULL DEFAULT 0,
                UNIQUE(trade_date, code, minute)
            );

            CREATE TABLE IF NOT EXISTS selection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                indicator_ids_json TEXT NOT NULL,
                generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS stock_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES selection_runs(id) ON DELETE CASCADE,
                trade_date TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                board TEXT NOT NULL,
                concept TEXT NOT NULL DEFAULT '',
                close REAL NOT NULL,
                change_percent REAL NOT NULL,
                volume_ratio REAL NOT NULL,
                turnover_rate REAL NOT NULL,
                sealed_amount_wan REAL NOT NULL,
                stop_loss_price REAL NOT NULL,
                next_open REAL,
                future_closes_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE INDEX IF NOT EXISTS idx_daily_quotes_date ON daily_quotes(trade_date);
            CREATE INDEX IF NOT EXISTS idx_minute_trades_quote ON minute_trades(trade_date, code);
            CREATE INDEX IF NOT EXISTS idx_selection_runs_date ON selection_runs(trade_date, generated_at);
            CREATE INDEX IF NOT EXISTS idx_stock_picks_date ON stock_picks(trade_date);
            """
        )
