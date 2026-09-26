# Deploying the public DEEPSIFT site

The public research site is the Next.js app in `apps/web`, built as **fully static pages**. It needs no API keys, no Python
service and no local files. Every research number comes from the committed `apps/web/data/release.json` (built by
`scripts/build_release_data.py` from frozen artifacts), and figures come from `apps/web/public/figures/`.

## Vercel settings

| setting | value |
|---|---|
| Framework preset | Next.js |
| Root directory | `apps/web` |
| Install command | `npm install` (default) |
| Build command | `next build` (default) |
| Output | default (`.next`) |
| Node.js | 20.x or newer |

## Environment variables

| variable | value | purpose |
|---|---|---|
| `NEXT_PUBLIC_DEEPSIFT_PUBLIC_RELEASE` | `1` | Public release mode. The browser never contacts a pipeline API (no `localhost` requests), local research tools are hidden from navigation and show a "LOCAL RESEARCH TOOL" notice, and the homepage links to the static Phase 1–2 archive. |
| `NEXT_PUBLIC_SITE_URL` | `https://<production domain>` | Absolute URLs for the Open Graph and Twitter preview images. |

**Do not set** `OPENROUTER_API_KEY`, `TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY` or `NEXT_PUBLIC_DEEPSIFT_API` on the
public deployment. None is needed.

## Routes

| class | routes | notes |
|---|---|---|
| PUBLIC CORE | `/`, `/final-test`, `/research`, `/reproducibility`, `/limitations` | Static; frozen release data only. The replay only animates stored frames. |
| HIDDEN (for now) | `/telemetry` | Phase 1–2 homepage archive. In public mode it returns 404 and is not linked; locally it is unchanged. Re-enable by removing the `notFound()` guard in `apps/web/app/telemetry/page.tsx`. |
| LOCAL / RESEARCH ONLY | `/control`, `/study`, `/blackout`, `/experiments`, `/explorer`, `/audit`, `/config`, `/review` | Need the FastAPI pipeline (`npm run demo`). In public mode they render a notice instead of calling the API, and are hidden from navigation. Kept for the historical record. |

## Local full stack (not for public deployment)

Run `npm run demo`. It starts the API on `:8787` and the UI; public mode is off by default.
