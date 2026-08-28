# Configuration reference

Every environment variable SkillNet reads, what it defaults to, and — the part that is easy
to get wrong — whether setting it in `.env` actually changes anything.

## The rule that explains most surprises

**`.env` never reaches a container by itself.** `.dockerignore` keeps it out of the image, and
no service in any compose file declares `env_file:`. The API's `pydantic-settings` does say
`env_file=".env"`, but inside the container there is no such file to read.

So a variable takes effect in Docker only if the service that needs it lists it in its
`environment:` block, as `VAR: ${VAR:-default}`. Compose reads `.env` from the repo root at
`docker compose up` time and interpolates it there. That indirection is why a setting can be
real in `src/config.py`, documented, spelled correctly in your `.env`, and still do nothing.

The **Reachable in Docker** column below records exactly that, per variable:

| Value | Meaning |
|---|---|
| Yes | Listed in a service's `environment:` block; your `.env` value wins. |
| Overlay only | Only reaches the container under the named optional compose overlay or profile. |
| **No** | No compose file passes it. Setting it in `.env` does nothing under Docker. |
| Fixed by compose | Compose sets a literal value; a `.env` entry is ignored. |

A **No** variable still works when the API runs outside Docker (`uv run uvicorn …`), because
then `pydantic-settings` really does read `.env`. Only the Docker path drops it.

---

## Required

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `SECRET_KEY` | dev placeholder | Signs session cookies and derives the key that encrypts per-org provider credentials. | Yes |
| `POSTGRES_PASSWORD` | none — compose refuses to start | Database password. **Letters, digits, `-` and `_` only.** | Yes |
| `LLM_API_KEY` | empty | Provider key for generation, tutoring and evaluation. Empty means courses generate empty. | Yes |

`POSTGRES_PASSWORD` is interpolated into `postgresql+asyncpg://user:PASSWORD@db:5432/db`
without escaping. A `@`, `:`, `/`, `#` or `?` splits that URL, and the resulting connection
error never mentions the password.

## Models and providers

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `LLM_MODEL` | `gpt-4o-mini` | Main model id in litellm form, `provider/model`. No prefix means OpenAI. | Yes |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Endpoint for OpenAI-compatible providers. Leave empty for the provider litellm already knows. | Yes |
| `LLM_GENERATION_MODEL` | falls back to `LLM_MODEL` | Overrides the model used for course generation only. | Yes |
| `LLM_TUTOR_MODEL` | falls back to `LLM_MODEL` | Overrides the model used by the in-course tutor. | Yes |
| `LLM_EVAL_MODEL` | falls back to `LLM_MODEL` | Overrides the model used to evaluate learner answers. | Yes |
| `LLM_RUNTIME_FAST_MODEL` | falls back to `LLM_MODEL` | Fast tier of the v2 runtime router for dynamic courses. | Yes |
| `LLM_RUNTIME_HEAVY_MODEL` | falls back to `LLM_MODEL` | Heavy tier of the v2 runtime router for dynamic courses. | Yes |
| `GEMINI_API_KEY` | empty | Read by litellm for `gemini/*` model ids. Not a field in `src/config.py`. | Yes |
| `VISION_MODEL` | empty | Multimodal model that describes images inside uploaded PDFs. Empty disables it silently. | Yes |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model for RAG. Must return 768 dimensions — see below. | Yes |
| `EMBEDDING_BASE_URL` | `https://api.openai.com/v1` | Endpoint when embeddings come from a different provider than generation. | Yes |
| `EMBEDDING_API_KEY` | empty | Key when embeddings come from a different account than generation. | Yes |
| `EMBEDDING_DIMENSIONS` | `768` | Dimensions requested from the provider. Must match the column. **Do not set.** | Yes |

### The 768-dimension contract

`document_chunks.embedding` is `vector(768)`, pinned by hand in migration 0008. The ORM
declares `Vector()` with no size on purpose, so the database is the only place that number
lives. `EMBEDDING_DIMENSIONS` does not *decide* the schema — it tells the provider how many
dimensions to return, and it has to agree with the column or every chunk insert fails.

`services/embedding_check.py` compares the two at startup and reports the result in
`GET /health`, because otherwise the mismatch first appears inside an ingestion `except`.

Three cases:

- `text-embedding-3-small` / `-large` accept a `dimensions` parameter and truncate for you.
  SkillNet sends it, so they return 768. Nothing to do.
- A model whose native output is already 768 — `nomic-embed-text`, `multilingual-e5-base`,
  `paraphrase-multilingual` — also fits. Nothing to do.
- Any other dimension (`multilingual-e5-small` is 384, `e5-large` is 1024) needs a migration
  of the column and a re-ingestion of every document. That is not a `.env` edit.

## Owner account and workspace

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `ADMIN_EMAIL` | empty | Headless bootstrap: creates the owner on first start. Blank selects the `/setup` wizard. | Yes |
| `ADMIN_PASSWORD` | empty | Password for that owner. Ships blank; this repo contains no usable password. | Yes |
| `ORG_NAME` | `SkillNet` | Name of the organization created on first start. | Yes |
| `WORKSPACE_MODE` | `organization` | `organization` or `individual`. Read only when the organization is first created. | Yes |
| `SETUP_WINDOW_MINUTES` | `30` | Minutes the public `/setup` endpoint stays open after a boot with no owner. `0` removes the limit. | Yes |
| `ONBOARDING_ENABLED` | `true` | Forces the onboarding wizard for learners without a completed profile. | Yes |

`/setup` has to be public — it is how the first account gets created — so until an owner
exists, whoever reaches it first becomes the owner. That is fine on `localhost` and not fine
behind a tunnel started before the account. When the window closes, restart the `api`
container for another one, or use the `X-Setup-Token` printed in the API log at startup.

## Serving, sessions and exposure

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `PORT` | `3000` | Host port the `web` service publishes. Not used by `docker-compose.dokploy.yml`. | Yes |
| `COOKIE_SECURE` | `false` base, `true` in the exposure overlays | Marks the session cookie `Secure`. See the precedence note below. | Yes |
| `SESSION_LIFETIME_SECONDS` | `604800` (7 days) | How long a session cookie stays valid. | Yes |
| `COOKIE_NAME` | `skillnet_session` | Name of the session cookie. | **No** |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON array of allowed origins. Rarely needed: the bundled nginx makes the SPA same-origin. | Yes |
| `FORWARDED_ALLOW_IPS` | `*` | Proxies uvicorn trusts for `X-Forwarded-*`. `*` is safe only because `api` publishes no port. | Yes |
| `ENVIRONMENT` | `production` in compose | `production` turns on the `SECRET_KEY` strength checks. | Yes |
| `LOG_LEVEL` | `info` | uvicorn/application log level. | Yes |
| `DEBUG` | `false` | `true` exposes Swagger at `/api/docs`; it is hidden otherwise. | Yes |
| `MAX_UPLOAD_SIZE_MB` | `50` | Upload ceiling in the API. nginx caps bodies at a fixed 55m independently. | Yes |
| `UPLOAD_DIR` | `./uploads` | Where uploads are written. | Fixed by compose (`/data/uploads`) |
| `DATABASE_URL` | local Postgres | SQLAlchemy URL. | Fixed by compose (built from `POSTGRES_*`) |
| `POSTGRES_USER` | `skillnet` | Database role, used by `db` and by the URL compose builds. | Yes |
| `POSTGRES_DB` | `skillnet` | Database name, same. | Yes |
| `DOMAIN` | none | Public hostname Caddy requests a certificate for. Required by the caddy overlay. | Overlay only (`caddy.yml`) |
| `CADDY_EMAIL` | none | Let's Encrypt account address. Required — an empty value is a Caddyfile parse error. | Overlay only (`caddy.yml`) |
| `CLOUDFLARE_TUNNEL_TOKEN` | none | Token for a named tunnel from the Cloudflare Zero Trust dashboard. | Overlay only (`cloudflared.yml`) |

### `COOKIE_SECURE` and the exposure overlays

`docker-compose.yml` reads `${COOKIE_SECURE:-false}`, because the default stack speaks plain
HTTP on `localhost` and a `Secure` cookie would never be sent back.

The three exposure overlays — `docker/compose/caddy.yml`, `cloudflared.yml` and
`quicktunnel.yml` — all read `${COOKIE_SECURE:-true}`, because each of them puts real TLS in
front.

The `:-` default only applies when the variable is **unset**. An active `COOKIE_SECURE=` line
in `.env` therefore wins over all three overlays, including a `false` you copied from an
example and forgot. That is why `.env.example` ships the line commented out: leave it that
way unless you specifically mean to override an overlay.

## Sign in with Google

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | empty | OAuth client id. Empty disables the whole feature; `/auth/google/*` answers 404. | Yes |
| `GOOGLE_CLIENT_SECRET` | empty | OAuth client secret. Same: empty disables the feature. | Yes |
| `GOOGLE_REDIRECT_URI` | empty | Callback URL, matched verbatim by Google. Empty derives it from the request. | Yes |
| `GOOGLE_POST_LOGIN_PATH` | `/` | Path the browser lands on after a successful sign-in. A path, never a URL. | Yes |
| `GOOGLE_LOGIN_ERROR_PATH` | `/login` | Path for a refused sign-in, carrying a `google_error` query parameter. | Yes |

### What Google may do, by workspace mode

The credentials turn the feature on. What it is *allowed* to do comes from the organization's
`workspace_mode`, not from configuration (`src/services/google_oauth.py`):

- **organization** — Google only **signs in** people who already have an account created by an
  administrator. An uninvited address is refused and no account is created. SkillNet scopes
  data per organization, so open registration would be a side door into a company's data.
- **individual** — Google may also **create** the account, because in a one-person workspace
  there is nobody to do the inviting.

In both modes Google must report the address as verified. An unverified one is refused:
matching on a claim Google does not stand behind would hand the matching account to whoever
typed the address.

Get the credentials at <https://console.cloud.google.com/apis/credentials> → "Create
credentials" → "OAuth client ID" → "Web application". For the default local stack the redirect
URI is `http://localhost:3000/api/v1/auth/google/callback`; Google compares the whole string,
trailing slash included.

## Text to speech

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `TTS_PROVIDER` | `disabled` | `openai`, `elevenlabs`, `google`, `azure`, or `disabled`. | Yes |
| `TTS_API_KEY` | empty | Key for that provider. | Yes |
| `TTS_VOICE` | empty | Voice id. Empty selects the provider default (Azure: `es-ES-ElviraNeural`). | Yes |
| `TTS_LANGUAGE` | `es` | Synthesis language. | Yes |
| `TTS_TIMEOUT_SECONDS` | `30` | Per-request timeout for synthesis. | Yes |
| `TTS_AZURE_REGION` | empty | Azure Speech region. Never inferred, so sovereign clouds keep working. | Yes |
| `TTS_AZURE_ENDPOINT` | empty | Full Azure synthesis endpoint URL. Also never inferred. | Yes |
| `TTS_CACHE_DIR` | `data/tts_cache` | Content-addressed cache of synthesized audio. | Yes (compose points it at the `tts_cache` volume) |

Without a working key the two consumers degrade differently. The mascot's live voice
(`POST /api/v1/tts/synthesize`) hard-fails with 500 and does **not** fall back to the offline
voice; the frontend swallows it, so the learner simply gets no audio. Podcast generation falls
back ElevenLabs → Azure → offline eSpeak NG, so a podcast is always produced, only robotic.

Media is baked at seed time and stored content-addressed: learners hear whatever voice was
generated when the seed ran, not a per-user render.

## Images and media artifacts

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `OPENROUTER_API_KEY` | empty | Key litellm uses for `openrouter/*` models, which is the default image engine. | Yes |
| `IMAGE_API_KEY` | empty | The image provider's own key, when the image account is not the text account. | Yes |
| `IMAGE_MODEL` | `openrouter/google/gemini-2.5-flash-image` | Primary image model for posters, infographics and slide art. | Yes |
| `IMAGE_FALLBACK_MODEL` | `gpt-image-1` | Per-call fallback, billed against `LLM_API_KEY`. | Yes |
| `MEDIA_ASSETS_DIR` | `data/media_assets` | Where generated mp3/png/mp4 are stored, keyed by content hash. | Yes (compose points it at the `media_assets` volume) |
| `SOURCE_IMAGES_DIR` | `data/source_images` | Where images extracted from an uploaded document are stored. | Yes (compose points it at `/data/uploads/source_images`, inside the existing `uploads` volume, so there is no fourth volume to get wrong) |
| `PODCAST_SCRIPT_MODEL` | empty → `LLM_MODEL` | Model for the podcast script agent. | **No** |
| `PODCAST_DIALOGUE_MODEL` | `eleven_v3` | ElevenLabs Text-to-Dialogue model for the two-host voice path. | **No** |
| `PODCAST_VOICE_A` | ElevenLabs "Sarah" | First podcast host voice id. | **No** |
| `PODCAST_VOICE_B` | ElevenLabs "Antoni" | Second podcast host voice id. | **No** |
| `SLIDES_MODEL` | empty → `LLM_MODEL` | Model for the slide-deck content agent. | **No** |
| `INFOGRAPHIC_MODEL` | empty → `LLM_MODEL` | Model for the infographic content agent. | **No** |
| `VIDEO_NARRATION_MODEL` | `gpt-4o-mini` | Model that writes one narration line per slide for video overviews. | **No** |

`MEDIA_ASSETS_DIR`, `TTS_CACHE_DIR` and `SOURCE_IMAGES_DIR` default to paths relative to the
working directory, which inside a container is the image filesystem. Compose overrides all
three to `/data/...` so the named volumes hold them; without that, every `--build` threw the
generated media away. The same defect hit `SOURCE_IMAGES_DIR` on the Dokploy deploy for a
while, because the key was missing from that file's `environment:` block: every picture
extracted from an uploaded document was discarded on the next redeploy. Silently — which is
what the rule at the top of this page is about, and what
`apps/skillnet-api/tests/test_compose_env_parity.py` exists to catch.

Without an image key the capability is refused up front with a reason, rather than accepted
and failed later.

## Provider retries and reasoning models

None of these reach the container. They are listed because they are real settings that work
outside Docker, and because the gap is worth knowing before you spend an afternoon on it.

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `LLM_MAX_ATTEMPTS` | `5` | Attempts before a provider call gives up. Read only by `src/llm/client.py`. | **No** |
| `LLM_RETRY_BASE_SECONDS` | `4.0` | Backoff base, used only when the provider does not say how long to wait. | **No** |
| `LLM_RETRY_MAX_WAIT_SECONDS` | `90.0` | Ceiling on one wait. Above a minute a TPM window has already reset. | **No** |
| `LLM_REASONING_EFFORT` | `low` | `none`, `low`, `medium`, `high`. `none` never sends the parameter. | **No** |
| `LLM_REASONING_TOKEN_HEADROOM` | `2048` | Extra completion budget for a reasoning model, on top of what the call site asked for. | **No** |

A reasoning model bills its chain of thought against the same `max_tokens` as the answer, so
without headroom it can spend the whole budget thinking and return empty content, which the
runtime reads as an invalid program.

## Dynamic courses and the render pipeline

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `ADAPTIVE_EPISODES` | `false` | Generates each dynamic node as a grounded domain episode instead of the legacy screen formula. | Yes |
| `MULTI_AGENT_RENDER` | `false` | Uses four specialized agents instead of one monolithic generation call. | Yes |
| `SEMANTIC_ROUTER` | `false` | Adds a short classification call in front of the deterministic content-function rules. | Yes |
| `RENDER_ALLOW_REACTIVE` | `false` | Allows OpenUI's reactive layer. Cost of switching it on: `docs/design/openui-adoption.md` §3. | **No** |
| `RUNTIME_COMPONENT_SHORTLIST` | `true` | Exposes only the 3-5 renderer-safe candidates to the generation prompt. | **No** |
| `RENDER_CACHE_SWEEP` | `true` | Deletes, at startup, a bounded batch of cached screens that a prompt-version bump made unreachable. | Yes |

Bumping `PROMPT_VERSION` invalidates every cached render, but invalidating is not
deleting: the rows stay in `node_renders` and nothing will ever compute their key again.
`RENDER_CACHE_SWEEP` reclaims them 500 rows per boot, and only rows that **nothing**
references — no view, no attempt, no pinned learner state, no extracted activity. What is
left after that filter is a screen that was generated and that nobody ever opened. Set it
to `false` to keep every row; see `apps/skillnet-api/src/services/render_retention.py`.

A course is served by v2 when it has `delivery_mode='dynamic'` **and**
`schema_status='validated'`. There is no global flag;
`src/services/course_delivery.resolve_delivery` is the single decision point.

## Running on a local model

Used by `docker/compose/ollama.yml`, which is an overlay rather than a profile because it has
to rewrite `api`'s environment, and a profile cannot do that.

```bash
docker compose -f docker-compose.yml -f docker/compose/ollama.yml up -d --build
```

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `OLLAMA_LLM_MODEL` | `qwen2.5:7b-instruct` | Chat model pulled by the `ollama` service and given to `api` as `ollama_chat/…`. | Overlay only (`ollama.yml`) |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model, given to `api` as `ollama/…`. Outputs 768 dimensions, so no migration. | Overlay only (`ollama.yml`) |

The two prefixes differ on purpose. `ollama_chat/…` and `ollama/…` are litellm's native Ollama
providers: litellm appends `/api/chat` or `/api/embeddings` itself, so the base URL carries no
`/v1`. Mixing a `/v1` base with an `ollama/` prefix produces a 404.

On CPU this is slow — roughly 185 s to render one lesson screen with a 7B model, measured
2026-07-27. Useful offline; not comfortable for real use.

## Optional services

| Variable | Default | What it does | Reachable in Docker |
|---|---|---|---|
| `A2A_INTERNAL_API_KEY` | empty | Key the A2A server uses to call `/ext/v1`. Auto-created in the database on startup if set. | Yes |
| `A2A_AUTH_KEY` | empty | Bearer token external agents must present. The server refuses to start without it. | Profile only (`--profile a2a`) |
| `A2A_LLM_MODEL` | `gpt-4o-mini` | Model for the A2A orchestrator. | Profile only (`--profile a2a`) |
| `A2A_PORT` | `5000` | Host port for the A2A server, published on `127.0.0.1` only. | Profile only (`--profile a2a`) |
| `A2A_AGENT_URL` | `http://localhost:5000` | URL the agent card advertises to callers. | Profile only (`--profile a2a`) |
| `SKILLNET_MCP_PORT` | `3001` | Host port for the MCP server, published on `127.0.0.1` only. | Profile only (`--profile mcp`) |
| `SKILLNET_MCP_API_KEY` | empty | Default SkillNet key for MCP clients that send no `Authorization` of their own. | Profile only (`--profile mcp`) |
| `API_FIXTURES_PORT` | `8001` | Host port for the keyless `api-fixtures` service. | Profile only (`--profile fixtures`) |

`api-fixtures` shares `SECRET_KEY` and the database with `api`, so it is not a sandbox — its
session cookies are valid against the real API. It is published on `127.0.0.1` for that
reason. The bundled nginx proxies to `api` unconditionally, so the SPA never uses it: to run
the whole stack keyless, set `LLM_MODEL=fixture/local` and `EMBEDDING_MODEL=fixture/local`
instead.

## Do not set

These are in `src/config.py` and in some compose files, and setting them in `.env` is either
inert or a way to break the install. They are deliberately absent from `.env.example`.

| Variable | Why not |
|---|---|
| `RENDER_BACKEND` | Typed `Literal["openui"]`, and the backend registry has exactly one entry. Nothing else is valid. |
| `EMBEDDING_DIMENSIONS` | Must be 768. Changing it is a migration plus a re-ingestion; compose already defaults it. |
| `LLM_FIXTURE_DIR` | Path inside the installed package (`src/llm/fixture_data`) so fixtures ship in the image. |
| `LLM_FIXTURE_MODE` | `replay` (default) or `record`. Developer-only: `record` calls the real provider and writes pairs to disk. |
| `RUNTIME_SELECTION_STRATEGY` | Research dial. `top5/v1` is the runtime behaviour; the other strategies are forced to shadow. |
| `RUNTIME_SELECTION_EXECUTION` | Research dial, paired with the above. `live` is the shipped value. |
| `DATABASE_URL` | Compose builds it from `POSTGRES_*`. A `.env` value is ignored under Docker. |
| `UPLOAD_DIR` | Compose fixes it to `/data/uploads`, the mounted volume. A `.env` value is ignored. |

## Related

- [`RUNNING.md`](../../RUNNING.md) — the five steps to start the project.
- [`docker-deployment.md`](docker-deployment.md) — the services and what each one does.
- [`security.md`](security.md) — the threat model behind the defaults above.
- [`tuning.md`](tuning.md) — generation-quality dials, most of which are code, not env vars.
