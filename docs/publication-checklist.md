# DEEPSIFT — publication checklist (v1 research release)

Work through this in order. Nothing in the repository publishes or deploys automatically.

## Repository

- [x] GitHub repo created: `https://github.com/nassimb/deepsift` (currently **private**; default branch `uat`)
- [ ] Decide the default branch (`main` recommended for the public repo)
- [ ] Licence chosen and `LICENSE` added (code), plus a data-provenance `NOTICE` (NASA PDS sources)
- [ ] Decide on the three tracked run logs (`artifacts/validation_run.log`, `data/fetch_split.log`, `data/fetch_split2.log`): keep or untrack
- [ ] Accept, or rewrite with a new identity, the commit author e-mail visible in public history
- [ ] Repo made public
- [ ] Repo URL inserted: replace `{{GITHUB_URL}}` in the files listed under *Placeholders* below

## Site

- [ ] Production site deployed (Vercel: root `apps/web`, `NEXT_PUBLIC_DEEPSIFT_PUBLIC_RELEASE=1`, `NEXT_PUBLIC_SITE_URL=<domain>`; see `docs/deployment.md`)
- [ ] Demo URL inserted: replace `{{DEMO_URL}}`
- [ ] All placeholders removed. `git grep -nE "\{\{[A-Z_]+\}\}"` returns only `{{NAME}}` / `{{SENDER}}` in `docs/outreach-note.md`, which are filled per e-mail
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

## Placeholders to replace (at the time of writing)

| file | placeholders |
|---|---|
| `docs/deepsift-one-pager.md` (and its PDF: re-run `uvx --with markdown python scripts/build_public_pdfs.py`) | `{{DEMO_URL}}` ×2, `{{GITHUB_URL}}` ×1 |
| `docs/launch-post-x.md` | `{{DEMO_URL}}`, `{{GITHUB_URL}}` |
| `docs/launch-post-linkedin.md` | `{{DEMO_URL}}`, `{{GITHUB_URL}}` |
| `docs/launch-post-hn.md` | `{{DEMO_URL}}`, `{{GITHUB_URL}}` |
| `docs/launch-video-shotlist.md` | `{{GITHUB_URL}}` |
| `docs/media-package.md` | `{{DEMO_URL}}`, `{{GITHUB_URL}}` (in the instructions) |
| `docs/outreach-note.md` | `{{DEMO_URL}}`, `{{GITHUB_URL}}`, plus `{{NAME}}` / `{{SENDER}}` per e-mail |
| `docs/release/github-release-notes-v1.md` | `{{DEMO_URL}}` ×3 |
| `scripts/check_public_claims.py` → `docs/public-claims-checklist.md` | mentions the placeholders in the manual-check text (update the wording once filled) |
