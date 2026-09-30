# DEEPSIFT collector on a Raspberry Pi (M4 — prepared, not deployed)

Runs `services/collector` 24/7 under systemd. The full API (incl. token-protected admin) stays on `127.0.0.1:8790`;
only the **read-only listener** `127.0.0.1:8791` (bearer-token protected, `/healthz` open) is ever exposed, through
**Tailscale Funnel**. No change to deepsift.space DNS.

```
NASA/NOAA/JPL ──► Pi: collector ──► SQLite /var/lib/deepsift-observatory (WAL)
                        │  127.0.0.1:8790  full API + POST /admin/refresh (admin token) — never exposed
                        └─ 127.0.0.1:8791  read-only allow-list (read token)
                                 ▲
                   Tailscale Funnel https://<pi>.<tailnet>.ts.net  (TLS, port 443)
                                 ▲
             Vercel /api/live/collector/* (server-side, adds COLLECTOR_READ_TOKEN) ◄── browsers
```

## Requirements

- Raspberry Pi 4/5 (3B+ works) on **64-bit** Raspberry Pi OS (Bookworm or later); a USB SSD is better than the SD card
  for a 24/7 SQLite writer (the collector writes a few KB every 5 s; ~10 MB/day stored).
- **Node.js ≥ 24** (built-in `node:sqlite` and TypeScript type stripping; no npm install needed):
  `curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash - && sudo apt-get install -y nodejs git`
- Correct clock (systemd-timesyncd is on by default) — all timestamps are UTC.

## Install (on the Pi)

```bash
git clone --filter=blob:none --sparse https://github.com/nassimb/deepsift.git /tmp/deepsift-kit
git -C /tmp/deepsift-kit sparse-checkout set services/collector
sudo sh /tmp/deepsift-kit/services/collector/deploy/raspberry-pi/install.sh
```

`install.sh` (idempotent): checks Node ≥ 24 · creates the `deepsift` system user · sparse checkout of only
`services/collector` + `apps/web/lib/observatory` into `/opt/deepsift` (root-owned, read-only for the service) ·
`/var/lib/deepsift-observatory` (0750, the only writable path) · `/etc/deepsift/collector.env` with **fresh random
tokens** (0640 root:deepsift) · systemd units + journald cap · enables and starts the service and the backup timer ·
prints `/healthz`. It opens **no** port and configures **no** tunnel.

## Operations

| what | how |
|---|---|
| production start command | `node services/collector/collector.ts` (from `/opt/deepsift`, env from `/etc/deepsift/collector.env`) |
| status | `systemctl status deepsift-collector` · `curl -s 127.0.0.1:8790/healthz` · `curl -s 127.0.0.1:8790/metrics` |
| logs | `journalctl -u deepsift-collector -f` (journald rotation: 200 MB total, 20 MB files, 30 days) |
| restart / stop | `sudo systemctl restart deepsift-collector` — SIGTERM → WAL checkpoint + close ("stopped cleanly") |
| crash | `Restart=always`, 5 s; unlimited retries (`StartLimitIntervalSec=0`); fatal errors exit non-zero on purpose |
| reboot | `WantedBy=multi-user.target`, `After=network-online.target` → starts on boot |
| force refresh (host only) | ``curl -X POST -H "Authorization: Bearer $(sudo grep ^COLLECTOR_ADMIN_TOKEN /etc/deepsift/collector.env \| cut -d= -f2)" "http://127.0.0.1:8790/admin/refresh?source=dsn"`` |
| update code | `sudo git -C /opt/deepsift pull --ff-only && sudo systemctl restart deepsift-collector` |
| retention | automatic, hourly (see docs/observatory.md) |
| metrics | `/metrics`: uptime, SQLite size, events, SSE clients, RSS, per-source lag and last-hour polls/errors/latency/new events/dedupe drops; 5-min snapshots in `collector_metrics` |

## Backups

- **Nightly** (`deepsift-collector-backup.timer`, 03:30 + ≤ 15 min jitter, catches up after downtime): `backup.ts` runs
  `VACUUM INTO` (consistent while the collector runs), then `PRAGMA integrity_check`, keeps 7 copies in
  `/var/lib/deepsift-observatory/backups/`. Run now: `sudo systemctl start deepsift-collector-backup`.
- **Off-device** (recommended, optional): copy the newest file elsewhere, e.g. `scp` from your Mac or `rclone` to a
  drive you own. Backups contain only public-source metadata — no secrets.
- **Restore**: `sudo systemctl stop deepsift-collector`, copy a backup over
  `/var/lib/deepsift-observatory/observatory.sqlite` (remove any `-wal`/`-shm`), `chown deepsift:deepsift`, start.

## Secure HTTPS for Vercel (recommended: Tailscale Funnel)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                                   # log in (free Personal plan)
# enable HTTPS + Funnel for the tailnet in the admin console once, then expose ONLY the read-only listener:
sudo tailscale funnel --bg --https=443 http://127.0.0.1:8791
tailscale funnel status                             # → https://<pi-name>.<tailnet>.ts.net
curl -s https://<pi-name>.<tailnet>.ts.net/healthz  # 200; any data route without the read token → 401; /admin → 404
```

Never funnel port 8790. Vercel (server-side only):

| variable | value |
|---|---|
| `LIVE_COLLECTOR_URL` | `https://<pi-name>.<tailnet>.ts.net` |
| `COLLECTOR_READ_TOKEN` | the `COLLECTOR_READ_TOKEN` from the Pi's env file (type: sensitive) |
| `COLLECTOR_ADMIN_TOKEN` | **not needed on Vercel** — force refresh stays on the Pi (the admin API is never tunneled) |

Rollback: `sudo tailscale funnel --https=443 off` (or remove `LIVE_COLLECTOR_URL` on Vercel) → the page returns to Tier 0.
