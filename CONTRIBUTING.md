# Contributing to SkillNet

Thanks for taking the time. This page is short on purpose: it says what is specific to this
repository and links to the files that already explain the rest.

## Get it running first

[`RUNNING.md`](RUNNING.md) is the whole answer — five steps and one decision (API key, local
model, or neither). Do not reconstruct the commands from anywhere else; the seed step is easy
to miss and without it you log in to an empty dashboard and think something is broken.

The keyless path is the fastest way to a working checkout: set `LLM_MODEL=fixture/local` and
`EMBEDDING_MODEL=fixture/local` in your `.env`, and every model call is served from recorded
fixtures. Enough to click through the interface and run the whole stack; not enough to author
a real course.

## Developing the frontend

**Do not rebuild the `web` container for UI work.** The container on `:3000` is the production
nginx build, and rebuilding it for a CSS tweak is minutes per change. Run the API in Docker and
Vite on the host:

```bash
docker compose -f docker-compose.yml -f docker/compose/dev.yml up -d db api
pnpm --dir apps/skillnet-web install    # first time only
pnpm --dir apps/skillnet-web dev        # http://localhost:5173, hot reload
```

Open **5173**, not 3000. Vite proxies `/api` to the dockerized API. Rebuild the `web` container
only to check the real production bundle.

## Before you open a pull request

Run what CI runs. Neither command needs a database or an API key:

```bash
# Backend, from apps/skillnet-api/
uv run ruff check src tests
uv run pytest -m "not integration"

# Frontend, from apps/skillnet-web/
pnpm lint
pnpm test
pnpm build
```

`uv run pytest -m integration` is the other suite. It needs a live PostgreSQL, and it **empties
`document_chunks`** as a side effect — the downgrade in `test_migration_0005` passes through a
migration that changes the vector dimension, and 768-component vectors cannot survive a return
to a 384 column. Re-run the seed afterwards.

## Conventions

[`AGENTS.md`](AGENTS.md) is the reference: stack, repo layout, code conventions and the
boundaries of what not to touch. The short version:

- Commit format: `type: description` — `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Branch from `main`, PR into `main`, no force push to `main`.
- TypeScript on the frontend, Python on the backend. Ruff for Python, Prettier for TS.
- All LLM calls go through litellm. Never hardcode a provider.
- Tailwind utilities and the tokens in `docs/design/design-system.md`. No inline styles.

## Reporting a bug

Open an issue with the template. It asks for the output of
`curl http://localhost:3000/api/v1/health` and for which row of `RUNNING.md` step 2 you chose
(API key, local model, or fixtures), because between them they explain most reports:

- `database` not `connected` — usually a password containing `@`, `:`, `/` or `#`, which splits
  the connection URL.
- `embeddings.status: mismatch` — the one misconfiguration that fails silently. Documents look
  ingested but nothing retrieves them.
- Blank course screens on `fixture/local` — expected. There is no recording for that prompt.

**Never paste your `.env`.** It contains your API key, your database password and your
`SECRET_KEY`.

## Security

Do not open a public issue for a vulnerability. See [`SECURITY.md`](SECURITY.md).

## License

By contributing you agree that your contributions are licensed under the
[Apache 2.0](LICENSE) license that covers the project.
