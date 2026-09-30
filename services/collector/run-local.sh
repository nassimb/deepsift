#!/bin/sh
# Start the Live Observatory collector locally in the background (logs → live_observatory/data/collector.log).
cd "$(dirname "$0")/../.." || exit 1
mkdir -p live_observatory/data
[ -f live_observatory/data/admin_token ] || (openssl rand -hex 24 | tr -d '\n' > live_observatory/data/admin_token && chmod 600 live_observatory/data/admin_token)
COLLECTOR_ADMIN_TOKEN="$(cat live_observatory/data/admin_token)" nohup node --disable-warning=ExperimentalWarning --disable-warning=MODULE_TYPELESS_PACKAGE_JSON \
  services/collector/collector.ts >> live_observatory/data/collector.log 2>&1 &
echo "collector started (pid $!) — http://127.0.0.1:8790/status"
