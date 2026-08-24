/**
 * Turns a failed call to /ext/v1 into a message safe to hand back to an MCP client.
 *
 * Never includes the `Authorization` header or the raw API key — only the SkillNet
 * error envelope (`error` / `message` / `details`, see docs/design/mcp-external-api.md
 * 8.1.6) or, failing that, the HTTP status and a generic description.
 */
export class SkillNetApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown
  ) {
    super(message);
    this.name = "SkillNetApiError";
  }
}

export async function toApiError(response: Response): Promise<SkillNetApiError> {
  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch {
    parsed = undefined;
  }

  if (isErrorEnvelope(parsed)) {
    const suffix = parsed.details ? ` (${safeStringify(parsed.details)})` : "";
    return new SkillNetApiError(
      `SkillNet API error [${parsed.error}]: ${parsed.message}${suffix}`,
      response.status,
      parsed
    );
  }

  return new SkillNetApiError(
    describeStatus(response.status),
    response.status,
    parsed
  );
}

function isErrorEnvelope(
  value: unknown
): value is { error: string; message: string; details?: unknown } {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    "message" in value &&
    typeof (value as { message?: unknown }).message === "string"
  );
}

function describeStatus(status: number): string {
  switch (status) {
    case 401:
      return "The SkillNet API rejected the credential (401 unauthorized).";
    case 403:
      return "The SkillNet API key lacks the required scope for this call (403 forbidden).";
    case 404:
      return "The requested resource was not found in SkillNet (404).";
    case 422:
      return "SkillNet rejected the request as invalid (422).";
    case 429:
      return "Rate limit exceeded on the SkillNet API (429). Retry later.";
    default:
      return `SkillNet API request failed with status ${status}.`;
  }
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** Formats any thrown error into a plain string, safe for a tool's error content. */
export function describeError(error: unknown): string {
  if (error instanceof SkillNetApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    // Fetch network errors, JSON parse errors, etc. Their .message never carries the
    // Authorization header (Node's fetch does not echo request headers in errors).
    return `SkillNet request failed: ${error.message}`;
  }
  return "SkillNet request failed with an unknown error.";
}
