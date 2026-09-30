# live_observatory/

Runtime namespace of the DEEPSIFT Live Data Observatory — operational data only, never science.

- `data/` (gitignored): `observatory.sqlite` (+ WAL), `collector.log`, `admin_token`.
- Collector code: `services/collector/`. Shared adapters: `apps/web/lib/observatory/`. Docs: `docs/observatory.md`.

Nothing here is read by any DEEPSIFT experiment, and nothing from `artifacts/`, `data/manifests/`, `config/` or the
release data is written here.
