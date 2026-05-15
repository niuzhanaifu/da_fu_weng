# Server Deploy

The service is designed to run on Linux with systemd.

## One-command deploy

Clone the repo on the server, then run:

```bash
cd /opt/dafuweng/server
chmod +x deploy.sh
DAFUWENG_ADMIN_TOKEN='replace-with-a-strong-token' TUSHARE_TOKEN='replace-with-your-tushare-token' ./deploy.sh
```

Defaults:

- App directory: current `server` directory
- Host: `0.0.0.0`
- Port: `8000`
- DB: `server/data/dafuweng.sqlite3`
- systemd service: `dafuweng-stock`
- `SEED_SAMPLE=0` by default. Set `SEED_SAMPLE=1` to seed sample data and run sample selection
- Installs a weekday 17:00 cron job to sync the current trade date and run daily selection

Deploy without sample data:

```bash
SEED_SAMPLE=0 DAFUWENG_ADMIN_TOKEN='replace-with-a-strong-token' ./deploy.sh
```

Verify:

```bash
curl http://14.103.183.47:8000/health
curl http://14.103.183.47:8000/api/v1/backtest-strategies
curl -X POST http://14.103.183.47:8000/api/v1/backtests \
  -H 'Content-Type: application/json' \
  -d '{"strategy_id":"old_cat","holding_days":3}'
```

Logs:

```bash
sudo journalctl -u dafuweng-stock -f
tail -f /opt/dafuweng/server/logs/server.log
```

Restart:

```bash
sudo systemctl restart dafuweng-stock
sudo systemctl status dafuweng-stock
```

## Firewall

Open TCP port `8000` in the cloud security group and the server firewall.

Ubuntu ufw example:

```bash
sudo ufw allow 8000/tcp
sudo ufw reload
```

## Update deployment

`deploy.sh` pulls the latest git code by default, then updates dependencies, initializes the database and restarts the systemd service:

```bash
cd /opt/dafuweng/server
./deploy.sh
```

To restart without pulling code:

```bash
cd /opt/dafuweng/server
AUTO_PULL=0 ./deploy.sh
```

The script preserves an existing `.env` token. To change it:

```bash
DAFUWENG_ADMIN_TOKEN='new-strong-token' ./deploy.sh
```

Runtime log files are written with size-based rotation:

- `logs/server.log`
- `logs/server.log.1` ... `logs/server.log.10`
- `logs/access.log`
- `logs/access.log.1` ... `logs/access.log.10`

## Tushare data

Set `TUSHARE_TOKEN` in `server/.env` or pass it into `deploy.sh`. After deployment, importing one trade date can be tested with:

Daily sync uses Tushare `daily` and `daily_basic` only. It does not call `stk_mins`, because minute data is heavily rate-limited.

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/import-tushare?trade_date=2026-05-15" \
  -H "X-Admin-Token: your-admin-token"
```

The public selection endpoint also imports from Tushare automatically when local quotes for the requested date are missing:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/selections/run \
  -H "Content-Type: application/json" \
  -d '{"trade_date":"2026-05-15","indicator_ids":["volume","seal","close"]}'
```

For backtesting, preload about three months of daily data so the server does not download during each run:

```bash
cd /opt/dafuweng/server
. .venv/bin/activate
python -m stock_server.jobs sync-tushare --start-date 2026-02-15 --end-date 2026-05-15
```

`deploy.sh` installs this daily cron automatically:

```cron
0 17 * * 1-5 cd /opt/dafuweng/server && . .venv/bin/activate && set -a && . .env && set +a && python -m stock_server.jobs sync-tushare --start-date $(date +\%F) --end-date $(date +\%F) && python -m stock_server.jobs run-daily-selection --date $(date +\%F) >> logs/cron.log 2>&1
```
