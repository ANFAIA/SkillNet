# Security Policy

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private reporting instead:
[Security → Report a vulnerability](https://github.com/ANFAIA/SkillNet/security/advisories/new)
on this repository.

Please include what you did, what happened, and what you expected — plus the version or commit
you tested. A proof of concept helps, but a clear description is enough to start.

SkillNet is maintained by a small team, so expect a first reply in days rather than hours. Only
the current `main` branch receives security fixes; there are no maintained older releases.

## Before you deploy this anywhere real

The defaults in this repository are tuned so that `docker compose up` works immediately for
someone exploring the project. Several of them are **not** safe for a real deployment. All of
them are documented next to the setting in `.env.example`; collected here because they matter
together.

**Credentials.** `.env.example` ships with a working demo owner account,
`admin@skillnet.dev` / `admin123`. Change both before anyone else can reach the instance, or
leave `ADMIN_EMAIL` and `ADMIN_PASSWORD` blank and create the owner through the `/setup` wizard
on first boot. Generate your own `SECRET_KEY` and `POSTGRES_PASSWORD` — never reuse an example.

**Cookies.** `COOKIE_SECURE` defaults to `false` so the stack works over plain HTTP on
`localhost`. Session cookies then travel unencrypted. Set it to `true` as soon as there is real
TLS in front, whether that is the Caddy overlay or a Cloudflare Tunnel.

**Published ports.** A default `docker compose up -d` publishes only port 3000; the API and the
database stay on the internal network. Every optional port in the repo binds to `127.0.0.1` on
purpose. Docker publishes ports with DNAT rules that **bypass the host firewall**, so changing
one of those to `0.0.0.0` on a shared network exposes it to everyone on that network — a
`0.0.0.0:5432` is PostgreSQL open to the LAN, with no firewall in the way.

**API keys.** Your LLM, embedding, TTS and image keys live in `.env`, which is gitignored. Do
not paste it into an issue, a pull request, or a bug report. If you need to show configuration,
redact the values.

**Uploads.** Documents learners and admins upload are stored on the host and processed by the
model provider you configured. Whatever you feed SkillNet is sent to that provider under their
terms — worth knowing before uploading anything confidential to a hosted API. The keyless
`fixture/local` mode and the Ollama overlay make no external calls at all.

## Scope

In scope: authentication and session handling, cross-organization data isolation, the external
`/ext/v1` API and its key scopes, the A2A and MCP servers, file upload handling, and injection
of any kind.

Out of scope: anything that requires an attacker to already have valid administrator
credentials, the deliberately weak demo defaults listed above, and the content a language model
generates (SkillNet does not claim its generated courses are factually correct).
