# DEEPSIFT — publication checklist (v1 research release)

Work through this in order. Nothing in the repository publishes or deploys automatically.

## Repository

- [x] GitHub repo created: `https://github.com/nassimb/deepsift` (public; default branch `main`; `uat` kept)
- [x] GitHub default branch set to `main`
- [x] Licence chosen and `LICENSE` added (Apache-2.0, code only), plus a data-provenance `NOTICE` (NASA PDS sources)
- [x] Three run logs untracked (kept locally); `*.log` ignored
- [x] History left unchanged (every commit and tag preserved); future commits use the GitHub noreply address (repo-local git config)
- [x] Repo made public
- [x] Repo URL inserted (https://github.com/nassimb/deepsift)

## Site

- [x] Production site deployed: https://deepsift.space (Vercel: root `apps/web`, `NEXT_PUBLIC_DEEPSIFT_PUBLIC_RELEASE=1`, `NEXT_PUBLIC_SITE_URL=https://deepsift.space`)
- [x] Demo URL inserted (https://deepsift.space)
- [x] All link placeholders removed (only the per-e-mail NAME / SENDER fields remain in `docs/outreach-note.md`)
- [ ] Replay loads: `/final-test` plays, SEND ALL/POSITION toggle works, 12 traverses selectable
- [ ] Mobile homepage checked (390 px: no horizontal scroll)
- [ ] Social preview checked (Open Graph and Twitter card show the held-out result image, absolute URLs)
- [ ] No request to `localhost` or `:8787` from any page (browser devtools, network tab)

## Checks (run from the repository root)

- [ ] Secret scan clean: `uvx detect-secrets scan --disable-plugin HexHighEntropyString $(git ls-files)`, plus a full-history grep for key formats
- [ ] Build passes: `cd apps/web && NEXT_PUBLIC_DEEPSIFT_PUBLIC_RELEASE=1 npx next build`
- [ ] Public claims check passes: `uv run python scripts/check_public_claims.py` → 52/52
- [ ] Science integrity check passes: `uv run python scripts/release_integrity.py --verify` → INTACT
- [ ] Tests pass: `uv run pytest -q` (in `services/pipeline`) · `npx tsc --noEmit` · `npx eslint .`

## Release and outreach

- [ ] Paper links work: README, `/research` and one-pager links resolve on GitHub and on the site
- [ ] Release created on tag `deepsift-v1-research`, with notes from `docs/release/github-release-notes-v1.md`; attach `release/deepsift-v1-research.zip` or its files (`uv run python scripts/assemble_release_assets.py`)
- [ ] Video recorded (`docs/launch-video-shotlist.md`), no NASA logo, numbers re-checked
- [ ] Outreach links checked (`docs/outreach-note.md`, launch posts): every link opens, no placeholder left

## Links (final)

- Site: https://deepsift.space
- Repository: https://github.com/nassimb/deepsift
- No double-brace link placeholder remains. `docs/outreach-note.md` keeps only its per-e-mail NAME / SENDER fields.
