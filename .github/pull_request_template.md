<!-- Keep it short. The diff says what changed; this says why. -->

## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## Checks

<!-- These are the same commands CI runs. Neither needs a database or an API key. -->

- [ ] `uv run ruff check src tests` and `uv run pytest -m "not integration"` (from `apps/skillnet-api/`)
- [ ] `pnpm lint`, `pnpm test` and `pnpm build` (from `apps/skillnet-web/`)
- [ ] Touched a migration, the compose files or `.env.example`? A clean `docker compose up -d --build` still comes up and `/api/v1/health` is green.

## Notes for the reviewer

<!-- Anything not obvious from the diff: a trade-off you made, something you left out on
     purpose, a decision you would like a second opinion on. Delete if there is nothing. -->
