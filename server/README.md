# 大富翁选股服务端

这是给安卓 App 使用的独立服务端，部署在 Linux 上即可。当前实现重点是把服务端职责先跑通：

- 存储每日行情和分时成交数据
- 收盘后按策略筛选主板、创业板涨停股
- 实时计算每日选股结果，选股结果和回测结果不落库
- 计算涨停当日分时成交均价作为止损价
- 提供回测接口
- 提供安卓端可直接调用的 JSON API

当前已接入 Tushare。服务端读取 `TUSHARE_TOKEN`，在选股请求指定日期且本地没有完整行情时，会自动拉取当天历史日线并保存。判断标准是当天 `daily_quotes` 数量不少于 1000 条；满足这个条件时，每日选股只读本地数据库，不会再请求 Tushare。日线同步不会调用 `stk_mins`，避免触发 Tushare 分钟线低频限制；涨停当日成交均价用日线 `amount / vol` 换算得到。

服务端只长期保存下载的股票行情数据：

- `daily_quotes`：日线行情
- `minute_trades`：当前主要用于保存由日线成交额/成交量换算出的均价点

以下数据不会长期保存：

- APP 发起的选股结果
- 回测交易明细
- 回测资金曲线

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

上面每条命令说明：

- `cd server`：进入服务端目录。
- `python3 -m venv .venv`：创建 Python 虚拟环境。
- `source .venv/bin/activate`：启用虚拟环境。
- `pip install -r requirements.txt`：安装 FastAPI、Uvicorn、Pydantic 等服务端依赖。
- `cp .env.example .env`：复制环境变量模板。
- `export DAFUWENG_ADMIN_TOKEN=change-me`：设置管理接口令牌，本地临时运行时使用。
- `export TUSHARE_TOKEN=your-token`：设置 Tushare Token，本地临时运行时使用。
- `python -m stock_server.jobs init-db`：初始化 SQLite 数据库和表结构。
- `python -m stock_server.jobs seed-sample`：写入示例行情，方便没有真实数据时调试。
- `python -m stock_server.jobs run-daily-selection --date 2026-05-14`：按指定日期试跑一次选股，只输出结果，不保存选股结果。
- `uvicorn stock_server.main:app --host 0.0.0.0 --port 8000`：启动 HTTP 服务。

访问：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/indicators
curl http://127.0.0.1:8000/api/v1/backtest-strategies
curl http://127.0.0.1:8000/api/v1/groups/latest
curl "http://127.0.0.1:8000/api/v1/stocks/600536/candles?limit=120"
```

上面每条命令说明：

- `curl http://127.0.0.1:8000/health`：检查服务是否启动成功。
- `curl http://127.0.0.1:8000/api/v1/indicators`：查看 APP 可选择的选股指标。
- `curl http://127.0.0.1:8000/api/v1/backtest-strategies`：查看当前支持的回测战法。
- `curl http://127.0.0.1:8000/api/v1/groups/latest`：读取旧版已保存选股分组；新逻辑不再保存选股结果，正常应使用 `/api/v1/selections/run`。
- `curl "http://127.0.0.1:8000/api/v1/stocks/600536/candles?limit=120"`：读取某只股票最近 120 根日 K 线。

指定日期触发服务端选股：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/selections/run \
  -H "Content-Type: application/json" \
  -d '{"trade_date":"2026-05-15","strategy_id":"old_cat_buy","indicator_ids":["volume","seal","close"]}'
```

命令说明：

- `POST /api/v1/selections/run`：按指定日期、选股战法和指标实时选股，结果直接返回给 APP，不保存到服务端数据库。
- `strategy_id`：选股战法 ID，可填 `old_cat_buy` 或 `limit_up_first`。
- 如果 `2026-05-15` 本地行情完整，服务端只读本地 SQLite，不请求 Tushare。
- 如果 `2026-05-15` 本地行情不存在或少于 1000 条，服务端会调用 Tushare 日线接口补齐当天数据。

回测：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/backtests \
  -H "Content-Type: application/json" \
  -d '{"strategy_id":"old_cat","holding_days":3,"initial_capital":100000,"max_positions_per_day":3,"board":"main","start_date":"2026-02-15","end_date":"2026-05-15"}'
```

命令说明：

- `POST /api/v1/backtests`：运行回测，结果直接返回，不保存回测结果。
- `strategy_id`：回测战法 ID，正式战法是 `old_cat`，策略对比接口会额外返回多个老猫对照策略。
- `holding_days`：买入后最多持有交易日数量。
- `initial_capital`：初始资金。
- `max_positions_per_day`：每日最多买入股票数量，当前 APP 默认 3。
- `board`：回测板块，可填 `main`、`chinext`，不填表示全部。
- `start_date` / `end_date`：回测区间。

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

命令说明：从 CSV 文件导入行情数据，会写入 `daily_quotes` 和 `minute_trades`。

Tushare 导入：

```bash
python -m stock_server.jobs import-tushare --date 2026-05-15
```

命令说明：从 Tushare 拉取某一天 A 股日线数据，并保存到本地 SQLite。

同步一个区间的历史日线：

```bash
python -m stock_server.jobs sync-tushare --start-date 2026-02-15 --end-date 2026-05-15
```

命令说明：从 Tushare 拉取一个区间内的历史日线，并保存到本地 SQLite。同步逻辑会拉取 `trade_cal`、`daily` 和 `daily_basic`，把主板、创业板历史日线落到 SQLite。

清理旧的服务端选股快照：

```bash
python -m stock_server.jobs clear-derived-data
```

命令说明：删除旧版本保存过的 `selection_runs` 和 `stock_picks`，并执行 SQLite 空间回收。这个命令不会删除 `daily_quotes` 和 `minute_trades`，因此不会删除已下载的股票行情数据。

CSV 字段见 `data/sample_quotes.csv`。其中：

- `board` 使用 `main` 或 `chinext`
- `future_closes` 用 `|` 分隔
- `minute_trades` 格式为 `minute:price:volume|minute:price:volume`

## 每日收盘任务

行情入库后执行：

```bash
python -m stock_server.jobs run-daily-selection --date 2026-05-14
```

命令说明：按指定日期实时计算选股结果并打印到终端。当前版本不会保存选股结果，只用于验证当天选股逻辑是否正常。

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
- `GET /api/v1/selection-strategies`
- `GET /api/v1/backtest-strategies`
- `GET /api/v1/groups/latest`
- `GET /api/v1/groups/{trade_date}`
- `POST /api/v1/selections/run`
- `GET /api/v1/stocks/{code}/candles`
- `POST /api/v1/backtests`
- `POST /api/v1/backtests/experiments`
- `POST /api/v1/admin/quotes`
- `POST /api/v1/admin/seed-sample`
- `POST /api/v1/admin/sync-tushare`
- `POST /api/v1/admin/run-daily-selection`

## 老猫战法

`old_cat` 是当前正式使用的“老猫战法”：

- 选涨停板时排除一字板
- 排除 ST 和退市风险股票
- 只做首板且涨停形态为早上封板
- 涨停日后的第 1 个交易日不买
- 涨停日后的第 2 个交易日开盘检查价格
- 如果该开盘价相对涨停日收盘价涨幅不超过 5%，按纪律买入
- 止损价为涨停板当天的分时均线止损价
- 单日最多买入 3 只股票
- 超过 3 只候选时，按最近 5 个交易日累计涨幅从小到大排序买入
- 资金不足买入 100 股时不买，不做虚假交易
- 买入后涨幅达到 APP 设置的止盈率时强制平仓，默认 10%
- 买入当天不能卖出，最早从买入后的下一个交易日检查止损、止盈和持有到期
- 选股结果会标注涨停形态：早上封板、下午封板、炸板涨停
- 回测结果只返回给 APP，不保存到服务端

按当前老猫战法执行某日选股时，服务端会回看上一个交易日涨停股。例如执行 `2026-05-14` 的选股，会筛选 `2026-05-13` 的首板早盘涨停，并判断是否满足老猫战法的买入候选条件。选股和回测使用同一套服务端 profile。

选股日期和候选日期都按本地行情表里的交易日处理。比如选股日是周一 `2026-05-11`，老猫买入会自动回看上一个开盘日 `2026-05-08`，不会请求周日 `2026-05-10` 的 Tushare 数据。

## 选股战法

APP 触发 `/api/v1/selections/run` 时通过 `strategy_id` 选择服务端战法：

- `old_cat_buy`：老猫买入。回看上一交易日首板早上封板、非 ST、非一字板候选，按老猫买入条件筛选。
- `limit_up_first`：首板涨停。选择选股当日涨停的非连板股票，排除一字板和 ST，并标注涨停类型与分时均线止损。

## 策略对比

APP 触发 `/api/v1/backtests/experiments` 时，服务端会同时跑多组互不重复的老猫对照策略：

- `old_cat`：正式老猫战法，首板、早上封板、非 ST、非一字板；超过 3 只时按最近 5 个交易日累计涨幅最低优先买入。
- `old_cat_stop_loss_rank`：选股条件与正式老猫战法一致；超过 3 只时按“买入价到分时均线止损价的亏损比例”从低到高排序，止损只亏 0.5% 的优先级高于止损要亏 3% 的。
- `old_cat_afternoon_first`：只做首板且涨停形态为下午封板；买卖规则与老猫战法一致。
- `old_cat_resealed_first`：只做首板且涨停形态为炸板回封；买卖规则与老猫战法一致。
- `old_cat_half_take_profit`：选股条件与正式老猫战法一致；达到 APP 设置的止盈率时卖一半，剩余仓位持有到期。
