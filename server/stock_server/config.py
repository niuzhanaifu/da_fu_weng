from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("DAFUWENG_DB_PATH", "./data/dafuweng.sqlite3")
    admin_token: str = os.getenv("DAFUWENG_ADMIN_TOKEN", "change-me")
    host: str = os.getenv("DAFUWENG_HOST", "0.0.0.0")
    port: int = int(os.getenv("DAFUWENG_PORT", "8000"))
    tushare_token: str = os.getenv("TUSHARE_TOKEN", "")
    tushare_fetch_minutes: bool = os.getenv("TUSHARE_FETCH_MINUTES", "1") != "0"
    tushare_timeout_seconds: int = int(os.getenv("TUSHARE_TIMEOUT_SECONDS", "30"))


settings = Settings()
