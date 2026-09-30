#!/bin/sh
# DEEPSIFT collector — Raspberry Pi installer (prepared for M4; run on the Pi as root: sudo sh install.sh).
# Idempotent. Does NOT open any port to the internet and does NOT configure a tunnel.
set -eu
REPO=https://github.com/nassimb/deepsift.git
APP=/opt/deepsift
DATA=/var/lib/deepsift-observatory
HERE="$(cd "$(dirname "$0")" && pwd)"

node -e 'const [a,b]=process.versions.node.split(".").map(Number); if (a<24) { console.error("Node >= 24 required (node:sqlite + TypeScript type stripping), found "+process.versions.node); process.exit(1) }'
id deepsift >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin deepsift
install -d -o deepsift -g deepsift -m 750 "$DATA" "$DATA/backups"
install -d -o root -g deepsift -m 750 /etc/deepsift

# code: sparse, blob-filtered checkout — only the collector and its shared adapters (~100 KB), read-only for the service
if [ ! -d "$APP/.git" ]; then
  git clone --filter=blob:none --sparse "$REPO" "$APP"
  git -C "$APP" sparse-checkout set services/collector apps/web/lib/observatory live_observatory
else
  git -C "$APP" pull --ff-only
fi
chown -R root:root "$APP"

if [ ! -f /etc/deepsift/collector.env ]; then
  sed -e "s/COLLECTOR_ADMIN_TOKEN=.*/COLLECTOR_ADMIN_TOKEN=$(openssl rand -hex 32)/" \
      -e "s/COLLECTOR_READ_TOKEN=.*/COLLECTOR_READ_TOKEN=$(openssl rand -hex 32)/" "$HERE/collector.env.example" > /etc/deepsift/collector.env
  chown root:deepsift /etc/deepsift/collector.env && chmod 640 /etc/deepsift/collector.env
  echo "created /etc/deepsift/collector.env with fresh tokens (read them with: sudo cat /etc/deepsift/collector.env)"
fi

install -m 644 "$HERE/deepsift-collector.service" "$HERE/deepsift-collector-backup.service" "$HERE/deepsift-collector-backup.timer" /etc/systemd/system/
install -d /etc/systemd/journald.conf.d && install -m 644 "$HERE/journald-deepsift.conf" /etc/systemd/journald.conf.d/deepsift.conf
systemctl restart systemd-journald
systemctl daemon-reload
systemctl enable --now deepsift-collector.service deepsift-collector-backup.timer
sleep 8
curl -fsS http://127.0.0.1:8790/healthz && echo && echo "collector healthy — local only (no tunnel configured)"
