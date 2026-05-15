# Server Deploy

The service is designed to run on Linux with systemd.

## One-command deploy

Clone the repo on the server, then run:

```bash
cd /opt/dafuweng/server
chmod +x deploy.sh
DAFUWENG_ADMIN_TOKEN='replace-with-a-strong-token' ./deploy.sh
```

Defaults:

- App directory: current `server` directory
- Host: `0.0.0.0`
- Port: `8000`
- DB: `server/data/dafuweng.sqlite3`
- systemd service: `dafuweng-stock`
- `SEED_SAMPLE=1` seeds sample data and runs sample selection

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

```bash
cd /opt/dafuweng
git pull
cd server
./deploy.sh
```
