# skillnet-mcp

An MCP (Model Context Protocol) server for SkillNet. It is a thin Streamable HTTP
wrapper over the existing external API (`/ext/v1`) — it never talks to PostgreSQL
directly and never duplicates business logic. Every tool call is a plain HTTP request
to the SkillNet backend, authenticated with a SkillNet API key.

See `docs/design/mcp-external-api.md` (sections 8.8 and 8.9) in the repo root for the
design this implements.

## Tools

| Tool | Read-only | Wraps |
|------|-----------|-------|
| `list_skills` | yes | `GET /ext/v1/skills` |
| `who_knows` | yes | `GET /ext/v1/skills/who-knows` |
| `get_gap` | yes | `GET /ext/v1/skills/gaps` |
| `get_user_skills` | yes | `GET /ext/v1/users/{id}/skills` |
| `create_course` | no | `POST /ext/v1/courses/full` |

`verify_skill` is intentionally **not** exposed as a tool in this version — see
`src/server.ts` for why.

## Scopes required

The SkillNet API key used to connect must carry:

- `skills:read` and `users:read` for the read-only tools.
- `courses:write` for `create_course`.

An API key missing a scope gets a `403` back from `/ext/v1`, which surfaces as a tool
error — the model never gets a silent wrong answer.

## Running it

```bash
cd packages/skillnet-mcp
npm install
cp .env.example .env   # then set SKILLNET_API_URL, optionally SKILLNET_API_KEY
npm run build
npm start
```

The server listens on `http://0.0.0.0:3001/mcp` (Streamable HTTP; **no SSE
transport**). Requests without their own `Authorization` header fall back to
`SKILLNET_API_KEY` from the environment, if set.

### Via Docker Compose

From the repo root:

```bash
docker compose --profile mcp up -d --build mcp
```

This builds the image from `packages/skillnet-mcp/Dockerfile` and starts it on
`127.0.0.1:3001`, pointed at the `api` service over the compose network. Set
`SKILLNET_MCP_API_KEY` in your `.env` to give it a default key (see
`docker-compose.yml`'s `mcp` service).

## Connecting an MCP client

Any client that speaks MCP over Streamable HTTP can connect. Point it at
`http://<host>:3001/mcp` and send the SkillNet API key as a bearer token:

```
Authorization: Bearer sn_your_real_key_here
```

Example with the TypeScript SDK's client:

```ts
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const transport = new StreamableHTTPClientTransport(
  new URL("http://localhost:3001/mcp"),
  { requestInit: { headers: { authorization: "Bearer sn_your_real_key_here" } } }
);
const client = new Client({ name: "example-client", version: "1.0.0" });
await client.connect(transport);
const tools = await client.listTools();
```

Or with `mcp-remote` for a client that only supports stdio (e.g. an older Claude
Desktop):

```json
{
  "mcpServers": {
    "skillnet": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://localhost:3001/mcp",
        "--header",
        "Authorization: Bearer sn_your_real_key_here"
      ]
    }
  }
}
```

## Getting a SkillNet API key

Create one from the admin panel (`/admin/settings/api-keys`) with, at minimum,
`skills:read` and `users:read` scopes for the read-only tools, plus `courses:write` if
`create_course` is needed. Keys can carry an expiry (`expires_at`); an expired or
scope-missing key is rejected by `/ext/v1` with a `403`.

## Development

```bash
npm install
npm run typecheck   # tsc --noEmit
npm run build       # tsc -> dist/
npm test            # vitest, all HTTP calls mocked — never hits a real server
```

## Design notes / limitations

- Stateless per request: each HTTP request gets its own `McpServer` instance bound to
  the API key resolved for that request (its own `Authorization` header, or the
  server's `SKILLNET_API_KEY` fallback). No session state, no shared credentials
  across connections.
- No OAuth, no MCP "Apps" UI, no connector directory listing — out of scope for this
  version. See `docs/design/mcp-external-api.md` 8.8.6–8.8.8 for what that would take.
- `create_course` can take minutes and can return honestly incomplete results
  (`packs_all_ready: false`, non-empty `warnings`) — that's the real behaviour of
  `POST /ext/v1/courses/full`, not a bug in this wrapper.
