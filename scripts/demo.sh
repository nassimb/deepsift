#!/usr/bin/env bash
# One-command DEEPSIFT demo: install → (try to) fetch real NASA data → start API + UI.
# If the PDS download fails, the pipeline uses the bundled real-data sample (LOCAL NASA SAMPLE).
set -euo pipefail
cd "$(dirname "$0")/.."

API_PORT="${DEEPSIFT_API_PORT:-8787}"
WEB_PORT="${DEEPSIFT_WEB_PORT:-3000}"
SOLS="${DEEPSIFT_SOLS:-232-251}"

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 1; }
command -v npm >/dev/null || { echo "Node.js/npm is required"; exit 1; }

[ -f .env ] && set -a && . ./.env && set +a

echo "▸ python deps";  uv sync --quiet
echo "▸ web deps";     (cd apps/web && npm install --silent --no-audit --no-fund)

if [ ! -f data/raw/manifest.json ] && [ "${DEEPSIFT_SKIP_FETCH:-0}" != "1" ]; then
  echo "▸ fetching MSL REMS + RAD sols $SOLS from the NASA PDS (≈230 MB, once)…"
  if ! uv run python scripts/fetch_nasa.py --sols "$SOLS"; then
    echo "  PDS download failed — the pipeline will use data/fixtures (LOCAL NASA SAMPLE, sols 238–243)."
  fi
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "▸ pipeline API on :$API_PORT"
PYTHONPATH=services/pipeline uv run uvicorn deepsift.api.app:app --port "$API_PORT" --log-level warning &
echo "▸ web UI on :$WEB_PORT"
(cd apps/web && NEXT_PUBLIC_DEEPSIFT_API="http://localhost:$API_PORT" npx next dev -p "$WEB_PORT") &

for _ in $(seq 1 90); do
  curl -sf "http://localhost:$API_PORT/api/status" | grep -q '"online":true' && break
  sleep 1
done
echo
echo "  DEEPSIFT ready → http://localhost:$WEB_PORT/control"
echo "  engine: $( [ -n "${TYPESAFE_API_KEY:-}" ] && echo 'Jev (TYPESAFE_API_KEY present)' || echo 'mock heuristic (no TYPESAFE_API_KEY)')"
(command -v open >/dev/null && open "http://localhost:$WEB_PORT/control") || true
wait
