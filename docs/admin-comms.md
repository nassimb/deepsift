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

**Images:** X's web intent cannot carry attachments (and the X API is not used), so OPEN IN X first copies the post's
recommended image to the clipboard as PNG (`lib/comms/clipboardImage.ts`; JPEGs converted in memory), then opens the
composer — press ⌘V / Ctrl+V there to attach it. For threads the image goes with post 1. Every image also has
Download and Copy image buttons (a stereo pair has two).

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
| `/admin/comms/reply` | Reply Lab — paste someone's X post; get topic, DEEPSIFT relevance (STRONG/MODERATE/WEAK/NONE), what you can add, promotional risk, a NATURAL reply by default (never names DEEPSIFT), TECHNICAL and DEEPSIFT-CONNECTION options, 7 styles, expert question, link recommendation (default NONE), facts used, claim check; OPEN IN X opens the reply composer (`in_reply_to`), nothing is posted |
| `/admin/comms/library` | All seed ideas (41), filter by category/audience |
| `/admin/comms/calendar` | Week view, cadence Mon result · Tue negative · Wed Mission Control · Thu engineering/method · Fri question; PLAN THIS WEEK |
| `/admin/comms/history` | Every item with ids, dates, X URL, visual, claims, status, notes, log |
| `/admin/comms/review` | Weekly review (planned, completed, categories, repeated claims, audiences, unused ideas) + manual performance by category |
| `/admin/comms/assets` | Approved existing visuals (figures, release media, Navcam previews, PDFs, pages to capture). Every image has a **PNG/JPEG download to attach on X — never SVG** (X does not accept SVG). `apps/web/public/share/*.png` are byte-identical copies of the frozen `docs/figures/*.png` and `artifacts/public/media/*.png` (checked by `tests/comms-assets.test.ts`). |

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

## Reply Lab (`/admin/comms/reply`, `lib/comms/reply.ts`)

Goal: add value to the original conversation — not mention DEEPSIFT as often as possible. Deterministic, no model, no API.

Order of work — **topic first, project second**:

1. **Original topic**: the post's domain (planetary geology, astrobiology, astrophysics, meteorology, launch, policy,
   instrumentation, rover engineering, operations, communications, autonomy, AI/ML, robotics, science news).
2. **DEEPSIFT relevance**: DIRECT (downlink, onboard prioritization/selection, onboard autonomy, onboard compute, stereo
   handling, compression) · ADJACENT (autonomy validation, ML generalization, rover image data, rover operations, mission
   data pipelines, or a claim DEEPSIFT evidence contradicts) · WEAK (same broad domain only — e.g. Mars geology, water
   history, weather, exoplanets, launches) · NONE. Mars, NASA, JPL, rover, Curiosity, Perseverance, space, science and AI
   **never create a connection on their own**, and a science subject DEEPSIFT has no evidence about caps relevance.
3. **A · Natural reply** — written from the post's own subject, never uses DEEPSIFT, never invents article content (it
   asks about the claim instead of asserting findings). **B · Curious question** about the subject. **C · Technical**
   only when the pasted text has technical substance. **D · DEEPSIFT-related** only for DIRECT/ADJACENT (or an explicit
   project-connection override on WEAK, shown with a warning).
4. **Should DEEPSIFT be mentioned?** YES only when it materially improves the reply: DIRECT, or ADJACENT with a concrete
   finding/limitation (not a "here's what I built" point), and not when your recent replies already mention it too often.
   Otherwise the recommended reply is the project-free one.

Checks on every (edited) reply: claim checker; no hashtags, @mentions or automatic link; overclaims (NASA/JPL uses
DEEPSIFT, real operations, universally optimal, all missions, AI useless, live data, promotional phrasing, institutional
roles, "this proves…" about an article you haven't pasted); **PROJECT_INSERTION** (reply relies on your experiment
under a WEAK/NONE post) → FAIL. Plus: **promotional risk**, **"Would this reply make sense if I had never built
DEEPSIFT?"**, a **conversation-value test** (reacts to the subject / adds information / meaningful question / clarifies /
relevant experience / invites discussion — none → DON'T REPLY), link recommendation (default NONE), **recent project
mentions** ("N of last 10 replies mentioned DEEPSIFT", warning above ~30%), and repetition protection.
Regression test: the Perseverance volcanic-water headline → PLANETARY GEOLOGY, WEAK, no mention.

**Limitation:** it matches topics, not arguments. It can't summarize an arbitrary post, answer the author's specific
point, detect sarcasm or read the article behind a headline; always read the post and edit the reply. A language model
would help exactly there — none is used, and adding one needs explicit approval.
