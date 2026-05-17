# 服务端部署与常用命令

服务端部署在 Linux 上，通过 `systemd` 常驻运行。服务器只长期保存下载的股票行情数据，主要是 `daily_quotes` 和 `minute_trades`。选股结果和回测结果都只实时返回给 APP，不保存到服务端数据库。

## 一键部署

首次部署或更新部署：

```bash
cd ~/codebase/da_fu_weng/server
chmod +x deploy.sh
DAFUWENG_ADMIN_TOKEN='替换成你的管理口令' TUSHARE_TOKEN='替换成你的TushareToken' ./deploy.sh
```

命令说明：

- `cd ~/codebase/da_fu_weng/server`：进入服务器上的服务端目录。
- `chmod +x deploy.sh`：给部署脚本增加可执行权限；如果 Git 已经记录了可执行权限，后续通常不需要再执行。
- `DAFUWENG_ADMIN_TOKEN='...'`：设置管理接口口令，用于保护导入数据、同步数据等管理接口。
- `TUSHARE_TOKEN='...'`：设置 Tushare Token，用于下载真实 A 股日线数据。
- `./deploy.sh`：执行部署脚本。脚本会自动拉取最新代码、安装依赖、初始化数据库、写入 systemd 服务、安装每天 17:00 的同步任务并重启服务。

以后更新代码并重启服务：

```bash
cd ~/codebase/da_fu_weng/server
./deploy.sh
```

命令说明：

- `./deploy.sh`：默认会先执行 `git pull` 拉取最新代码，然后更新依赖、初始化数据库并重启 `dafuweng-stock` 服务。

只重启服务，不拉取代码：

```bash
cd ~/codebase/da_fu_weng/server
AUTO_PULL=0 ./deploy.sh
```

命令说明：

- `AUTO_PULL=0`：关闭自动拉代码，适合只想重新应用配置或重启服务时使用。

## 服务检查

检查服务是否启动：

```bash
curl http://14.103.183.47:8000/health
```

命令说明：访问健康检查接口，返回 `{"status":"ok"}` 说明服务可用。

查看支持的回测战法：

```bash
curl http://14.103.183.47:8000/api/v1/backtest-strategies
```

命令说明：查看服务端当前支持哪些战法，当前只有 `old_cat` 老猫战法。

运行一次回测测试：

```bash
curl -X POST http://14.103.183.47:8000/api/v1/backtests \
  -H 'Content-Type: application/json' \
  -d '{"strategy_id":"old_cat","holding_days":3,"max_positions_per_day":3}'
```

命令说明：调用回测接口。回测结果只返回给客户端，不会保存到服务端数据库。

## 日志查看

查看 systemd 运行日志：

```bash
sudo journalctl -u dafuweng-stock -f
```

命令说明：实时查看 `dafuweng-stock` 服务的 systemd 日志。

查看服务端业务日志：

```bash
tail -f ~/codebase/da_fu_weng/server/logs/server.log
```

命令说明：实时查看服务端业务日志，包括启动、回测、选股、Tushare 同步等信息。

查看访问日志：

```bash
tail -f ~/codebase/da_fu_weng/server/logs/access.log
```

命令说明：实时查看 HTTP 请求访问日志。

日志文件会按大小滚动：

- `logs/server.log`
- `logs/server.log.1` 到 `logs/server.log.10`
- `logs/access.log`
- `logs/access.log.1` 到 `logs/access.log.10`

## 服务重启

重启服务：

```bash
sudo systemctl restart dafuweng-stock
```

命令说明：重启后端服务。

查看服务状态：

```bash
sudo systemctl status dafuweng-stock
```

命令说明：查看服务是否正在运行，以及最近的错误信息。

## Tushare 数据同步

同步某一天数据：

```bash
cd ~/codebase/da_fu_weng/server
. .venv/bin/activate
set -a && . .env && set +a
python -m stock_server.jobs sync-tushare --start-date 2026-05-15 --end-date 2026-05-15
```

命令说明：

- `. .venv/bin/activate`：启用 Python 虚拟环境。
- `set -a && . .env && set +a`：读取 `.env` 中的 `TUSHARE_TOKEN`、管理口令等环境变量。
- `python -m stock_server.jobs sync-tushare --start-date ... --end-date ...`：从 Tushare 下载指定日期范围内的日线数据并保存到 SQLite。

补最近三个月数据：

```bash
cd ~/codebase/da_fu_weng/server
. .venv/bin/activate
set -a && . .env && set +a
python -m stock_server.jobs sync-tushare --start-date $(date -d '3 months ago' +%F) --end-date $(date +%F)
```

命令说明：从当前日期往前补三个月行情。适合首次部署后先把回测需要的数据补齐。

补最近一年数据：

```bash
cd ~/codebase/da_fu_weng/server
. .venv/bin/activate
set -a && . .env && set +a
python -m stock_server.jobs sync-tushare --start-date $(date -d '1 year ago' +%F) --end-date $(date +%F)
```

命令说明：从当前日期往前补一年行情。重复执行会覆盖更新同一天同一只股票的数据，不会插入重复行情。

## 每日自动同步

`deploy.sh` 会安装每天 17:00 的定时任务：

```cron
0 17 * * 1-5 cd ~/codebase/da_fu_weng/server && . .venv/bin/activate && set -a && . .env && set +a && python -m stock_server.jobs sync-tushare --start-date $(date +\%F) --end-date $(date +\%F) && python -m stock_server.jobs run-daily-selection --date $(date +\%F) >> logs/cron.log 2>&1
```

命令说明：

- `0 17 * * 1-5`：周一到周五每天 17:00 执行。
- `sync-tushare --start-date $(date +%F) --end-date $(date +%F)`：同步当天行情。
- `run-daily-selection --date $(date +%F)`：试跑当天选股并把结果写入日志；当前版本不会保存选股结果。
- `>> logs/cron.log 2>&1`：把定时任务输出追加到 `logs/cron.log`，方便排查。

## 选股接口

按指定日期实时选股：

```bash
curl -X POST http://14.103.183.47:8000/api/v1/selections/run \
  -H 'Content-Type: application/json' \
  -d '{"trade_date":"2026-05-15","indicator_ids":["volume","seal","close"]}'
```

命令说明：

- 服务端会先检查本地 `daily_quotes` 是否已经有 `2026-05-15` 的完整行情。
- 如果当天行情数量不少于 1000 条，只读本地数据库，不请求 Tushare。
- 如果当天行情不存在或明显不完整，服务端会请求 Tushare 日线接口补齐当天数据。
- 选股结果直接返回给 APP，不保存到服务器。

## 回测接口

按区间运行老猫战法回测：

```bash
curl -X POST http://14.103.183.47:8000/api/v1/backtests \
  -H 'Content-Type: application/json' \
  -d '{"strategy_id":"old_cat","start_date":"2026-02-15","end_date":"2026-05-15","holding_days":3,"max_positions_per_day":3,"board":"main"}'
```

命令说明：

- `strategy_id`：战法 ID，当前只有 `old_cat`。
- `start_date` / `end_date`：回测区间。
- `holding_days`：最多持有交易日数量。
- 初始资金：默认 100000 元，APP 不再提供输入。
- `max_positions_per_day`：每天最多同时买入数量，APP 默认 3，可由用户选择。
- `board`：可选 `main` 主板、`chinext` 创业板；不传表示全部。
- 回测结果只返回给 APP，不写入数据库。

## 清理旧派生数据

清理以前版本保存过的选股快照：

```bash
cd ~/codebase/da_fu_weng/server
. .venv/bin/activate
set -a && . .env && set +a
python -m stock_server.jobs clear-derived-data
```

命令说明：

- 删除旧表里的 `selection_runs` 和 `stock_picks` 数据。
- 不删除 `daily_quotes` 和 `minute_trades`。
- 会执行 SQLite `VACUUM`，尽量回收数据库文件空间。

## 防火墙

开放 8000 端口：

```bash
sudo ufw allow 8000/tcp
sudo ufw reload
```

命令说明：

- `sudo ufw allow 8000/tcp`：允许外部访问服务端 8000 端口。
- `sudo ufw reload`：重新加载防火墙规则。

云服务器还需要在云厂商安全组里放开 TCP 8000 端口。
