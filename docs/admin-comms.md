# Private comms console (`/admin/comms`)

A private, zero-cost editorial assistant for communicating DEEPSIFT on X. It suggests what to post, drafts it from
verified facts only, checks every claim, and opens X's own composer. **It never publishes anything.**

## Access

- GitHub OAuth via Auth.js (`apps/web/auth.ts`). Only GitHub user `nassimb` with account id `3143068` is allowed
  (`apps/web/lib/admin/access.ts`); any other signed-in GitHub account gets **403**; no session → `/admin/login`.
- Enforced server-side in `apps/web/proxy.ts` (before rendering) and again in `app/admin/comms/layout.tsx`.
- Not linked from any public page, not in any sitemap, `noindex` + `Cache-Control: private, no-store`.
- Secrets are server-only env vars: `AUTH_SECRET`, `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET` (see `docs/deployment.md`).
  Missing any of them → `/admin/*` returns 503.
- Local use: create a second GitHub OAuth App with callback `http://localhost:3300/api/auth/callback/github` and put the
  three variables in `apps/web/.env.local`.

## Zero cost

No X API, no Metricool/Buffer/Hootsuite, no paid scheduler, no database, no LLM API. Content is deterministic:
curated templates (`lib/comms/library.ts`) over `VERIFIED_FACTS` (`lib/comms/facts.ts`).

**Editorial state is stored locally in this browser in v1** (`localStorage`, key `deepsift-comms-v1`): status, planned
date, scheduled date/time, posted status, X URL, notes, manual results, qualified replies, text revisions. Use
**EXPORT COMMS DATA / IMPORT COMMS DATA** (JSON) to back up or move between browsers.

## Workflow

draft → claim check → APPROVE (only if PASS) → OPEN IN X (`https://x.com/intent/tweet?text=…`, X's official web intent;
threads use `in_reply_to`) → publish or schedule **in X** (native scheduler) → MARK SCHEDULED / MARK POSTED here.

The workflow is manual by design: DEEPSIFT Comms is a private scientific communication assistant, not a social media bot.
There is no X API, X developer app, X OAuth, access/refresh token, media upload, server-side scheduler, cron or post queue,
and none should be added. MARK SCHEDULED records the date/time you set in X; MARK POSTED records (all optional) the post
URL, publication date/time and notes, then manual views, likes, replies, reposts, bookmarks, link clicks and qualified
replies — stored as entered, never verified through any X API. A test (`test_manual_only_no_social_automation_infrastructure`)
fails if automation infrastructure appears.

## Pages

| route | what |
|---|---|
| `/admin/comms` | What should I post today? — recommendation + 3 alternatives, mode (all / technical-research / space fan), queue, export/import |
| `/admin/comms/library` | All seed ideas (41), filter by category/audience |
| `/admin/comms/calendar` | Week view, cadence Mon result · Tue negative · Wed Mission Control · Thu engineering/method · Fri question; PLAN THIS WEEK |
| `/admin/comms/history` | Every item with ids, dates, X URL, visual, claims, status, notes, log |
| `/admin/comms/review` | Weekly review (planned, completed, categories, repeated claims, audiences, unused ideas) + manual performance by category |
| `/admin/comms/assets` | Approved existing visuals (figures, release media, Navcam previews, PDFs, pages to capture) |

## Scientific safety

- `VERIFIED_FACTS` (45 facts): each has source file + field, safe wording, scope, limitations, forbidden wording, and
  evidence re-checked against the frozen files by `apps/web/tests/comms-facts.test.ts`.
- Claim checker (`lib/comms/claims.ts`): every number must be licensed by a fact; headline numbers need held-out /
  Curiosity Navcam / archived-replay context; rejects NASA/JPL endorsement or validation, flight readiness, deployment,
  live data or rover control, preserved scientific value, onboard-stream reconstruction, discovery, AI superiority,
  mission gains beyond the replay, causal over-claims and hype. Negated mentions ("not NASA-reviewed") are allowed.
- Shareability check: transparent YES/NO factors with suggestions — never a "viral score".
- Recommendation: transparent points for cadence, repetition, unused facts, audience variety and visuals, each shown as a reason.

## Extending

Add an idea to `IDEAS` in `lib/comms/library.ts` (unique id, pillar, audience, three hooks, body, facts, visual), then
`cd apps/web && npm test` — every hook variant and every thread post must pass the claim checker.
