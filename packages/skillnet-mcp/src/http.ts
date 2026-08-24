import { createServer as createHttpServer, type IncomingMessage, type ServerResponse } from "node:http";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { createSkillNetMcpServer } from "./server.js";
import type { McpConfig } from "./config.js";

/**
 * Extracts the SkillNet API key to use for this MCP connection.
 *
 * Prefers the request's own `Authorization: Bearer <key>` (or a bare `X-Api-Key`
 * header) — the normal case for a remote client, each with its own SkillNet API key
 * and its own scopes. Falls back to `SKILLNET_API_KEY` from the environment, for a
 * single-tenant / local setup where the operator configured one key for the whole
 * server. Never logs or echoes whatever it resolves.
 */
export function resolveApiKey(req: IncomingMessage, config: McpConfig): string | undefined {
  const auth = req.headers["authorization"];
  if (typeof auth === "string" && auth.toLowerCase().startsWith("bearer ")) {
    const token = auth.slice(7).trim();
    if (token) return token;
  }
  const apiKeyHeader = req.headers["x-api-key"];
  if (typeof apiKeyHeader === "string" && apiKeyHeader.trim()) {
    return apiKeyHeader.trim();
  }
  return config.defaultApiKey;
}

function sendJsonError(res: ServerResponse, status: number, message: string): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(
    JSON.stringify({
      jsonrpc: "2.0",
      error: { code: -32001, message },
      id: null,
    })
  );
}

/**
 * Starts the Streamable HTTP listener. Stateless by design: every request gets its
 * own `McpServer` + transport bound to the API key resolved for that request, so two
 * clients (or the same client rotating keys) never share tool state or credentials.
 */
export function startHttpServer(config: McpConfig): ReturnType<typeof createHttpServer> {
  const httpServer = createHttpServer((req, res) => {
    void handleRequest(req, res, config);
  });
  httpServer.listen(config.port, () => {
    // eslint-disable-next-line no-console
    console.log(`skillnet-mcp listening on http://0.0.0.0:${config.port}/mcp`);
  });
  return httpServer;
}

async function handleRequest(
  req: IncomingMessage,
  res: ServerResponse,
  config: McpConfig
): Promise<void> {
  if (req.url !== "/mcp" && req.url !== "/") {
    res.writeHead(404).end();
    return;
  }
  if (req.method !== "POST" && req.method !== "GET" && req.method !== "DELETE") {
    res.writeHead(405).end();
    return;
  }

  const apiKey = resolveApiKey(req, config);
  if (!apiKey) {
    sendJsonError(
      res,
      401,
      "Missing SkillNet API key: send it as 'Authorization: Bearer <key>' or configure " +
        "SKILLNET_API_KEY on the server."
    );
    return;
  }

  const server = createSkillNetMcpServer({
    apiUrl: config.apiUrl,
    apiKey,
    requestTimeoutMs: config.requestTimeoutMs,
    createCourseTimeoutMs: config.createCourseTimeoutMs,
  });
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });

  res.on("close", () => {
    void transport.close();
    void server.close();
  });

  try {
    await server.connect(transport);
    await transport.handleRequest(req, res);
  } catch (error) {
    if (!res.headersSent) {
      sendJsonError(res, 500, "Internal MCP server error.");
    }
    // eslint-disable-next-line no-console
    console.error("skillnet-mcp request failed:", error instanceof Error ? error.message : error);
  }
}
