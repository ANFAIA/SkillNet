/** Environment-driven configuration. Read once at process start. */

export interface McpConfig {
  /** Base URL of the SkillNet FastAPI backend, e.g. http://localhost:8000. */
  apiUrl: string;
  /**
   * Fallback SkillNet API key, used only when an incoming MCP request carries no
   * `Authorization` header of its own (the common case for a local stdio-style client
   * pointed at a single-tenant instance). A per-request `Authorization` header always
   * takes priority — see `resolveApiKey` in `http.ts`.
   */
  defaultApiKey: string | undefined;
  /** Port the Streamable HTTP transport listens on. */
  port: number;
  /** Timeout (ms) for ordinary read calls against /ext/v1. */
  requestTimeoutMs: number;
  /** Timeout (ms) for `create_course`, which runs the full authoring pipeline server-side. */
  createCourseTimeoutMs: number;
}

function readConfig(env: NodeJS.ProcessEnv): McpConfig {
  const apiUrl = env.SKILLNET_API_URL?.trim();
  if (!apiUrl) {
    throw new Error(
      "SKILLNET_API_URL is required (base URL of the SkillNet API, e.g. http://localhost:8000)"
    );
  }
  return {
    apiUrl: apiUrl.replace(/\/+$/, ""),
    defaultApiKey: env.SKILLNET_API_KEY?.trim() || undefined,
    port: Number.parseInt(env.MCP_HTTP_PORT ?? "3001", 10),
    requestTimeoutMs: Number.parseInt(env.SKILLNET_REQUEST_TIMEOUT_MS ?? "30000", 10),
    createCourseTimeoutMs: Number.parseInt(
      env.SKILLNET_CREATE_COURSE_TIMEOUT_MS ?? "600000",
      10
    ),
  };
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): McpConfig {
  return readConfig(env);
}
