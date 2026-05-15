# 大富翁选股服务端

这是给安卓 App 使用的独立服务端，部署在 Linux 上即可。当前实现重点是把服务端职责先跑通：

- 存储每日行情和分时成交数据
- 收盘后按策略筛选主板、创业板涨停股
- 保存每日选股分组
- 计算涨停当日分时成交均价作为止损价
- 提供回测接口
- 提供安卓端可直接调用的 JSON API

当前已接入 Tushare。服务端读取 `TUSHARE_TOKEN`，在选股请求指定日期且本地没有行情时，会自动拉取历史日线并保存。默认不批量拉取 `stk_mins` 分钟线，避免触发 Tushare 低频接口限制；涨停当日成交均价优先用日线 `amount / vol` 换算得到，需要分钟线止损时再设置 `TUSHARE_FETCH_MINUTES=1`。

## 本地启动

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export DAFUWENG_ADMIN_TOKEN=change-me
export TUSHARE_TOKEN=your-token
python -m stock_server.jobs init-db
python -m stock_server.jobs seed-sample
python -m stock_server.jobs run-daily-selection --date 2026-05-14
uvicorn stock_server.main:app --host 0.0.0.0 --port 8000
```

访问：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/indicators
curl http://127.0.0.1:8000/api/v1/backtest-strategies
curl http://127.0.0.1:8000/api/v1/groups/latest
curl "http://127.0.0.1:8000/api/v1/stocks/600536/candles?limit=120"
```

指定日期触发服务端选股：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/selections/run \
  -H "Content-Type: application/json" \
  -d '{"trade_date":"2026-05-15","indicator_ids":["volume","seal","close"]}'
```

回测：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/backtests \
  -H "Content-Type: application/json" \
  -d '{"strategy_id":"old_cat","holding_days":3}'
```

## 导入行情

HTTP 写入：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/quotes \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: change-me" \
  -d '[{
    "trade_date":"2026-05-14",
    "code":"600536",
    "name":"中国软件",
    "board":"main",
    "concept":"国产软件",
    "previous_close":42.10,
    "open":43.20,
    "high":46.31,
    "low":43.20,
    "close":46.31,
    "volume_ratio":2.8,
    "turnover_rate":12.4,
    "sealed_amount_wan":18300,
    "next_open":46.95,
    "future_closes":[48.2,49.6,47.8],
    "minute_trades":[
      {"minute":"09:35","price":43.2,"volume":900},
      {"minute":"10:00","price":44.6,"volume":1080},
      {"minute":"14:57","price":46.31,"volume":1980}
    ]
  }]'
```

CSV 导入：

```bash
python -m stock_server.jobs import-csv data/sample_quotes.csv
```

Tushare 导入：

```bash
python -m stock_server.jobs import-tushare --date 2026-05-15
```

同步一个区间的历史日线：

```bash
python -m stock_server.jobs sync-tushare --start-date 2026-02-15 --end-date 2026-05-15
```

同步逻辑会拉取 `trade_cal`、`daily` 和 `daily_basic`，把主板、创业板历史日线落到 SQLite。选股和回测优先使用本地数据库；只有指定日期本地数据不存在或明显不完整时，才会补拉最近约三个月数据。

CSV 字段见 `data/sample_quotes.csv`。其中：

- `board` 使用 `main` 或 `chinext`
- `future_closes` 用 `|` 分隔
- `minute_trades` 格式为 `minute:price:volume|minute:price:volume`

## 每日收盘任务

行情入库后执行：

```bash
python -m stock_server.jobs run-daily-selection --date 2026-05-14
```

或用 HTTP 触发：

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/run-daily-selection?trade_date=2026-05-14&indicator_ids=volume&indicator_ids=seal&indicator_ids=close" \
  -H "X-Admin-Token: change-me"
```

部署脚本会自动安装 crontab，交易日 17:00 同步当天数据并执行当天选股：

```cron
0 17 * * 1-5 cd /opt/dafuweng/server && . .venv/bin/activate && set -a && . .env && set +a && python -m stock_server.jobs sync-tushare --start-date $(date +\%F) --end-date $(date +\%F) && python -m stock_server.jobs run-daily-selection --date $(date +\%F) >> logs/cron.log 2>&1
```

## systemd 部署

复制项目到 `/opt/dafuweng` 后：

```bash
sudo cp systemd/dafuweng-stock.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dafuweng-stock
sudo systemctl status dafuweng-stock
```

服务日志：

```bash
journalctl -u dafuweng-stock -f
tail -f /opt/dafuweng/server/logs/server.log
```

## 主要接口

- `GET /health`
- `GET /api/v1/indicators`
- `GET /api/v1/backtest-strategies`
- `GET /api/v1/groups/latest`
- `GET /api/v1/groups/{trade_date}`
- `POST /api/v1/selections/run`
- `GET /api/v1/stocks/{code}/candles`
- `POST /api/v1/backtests`
- `POST /api/v1/admin/quotes`
- `POST /api/v1/admin/seed-sample`
- `POST /api/v1/admin/sync-tushare`
- `POST /api/v1/admin/run-daily-selection`

## 老猫战法

服务端当前只保留 `old_cat`，也就是“老猫战法”：

- 涨停板次日开盘 1 分钟后观察价格
- 当前数据结构先使用 `next_open` 承载该价格；接真实行情后建议写入次日 `09:31` 价格
- 如果该价格相对涨停日收盘价涨幅不超过 3%，买入
- 止损价为涨停板当天的成交分时均价
- 触发止损则卖出，否则持有到请求里的 `holding_days` 后卖出
