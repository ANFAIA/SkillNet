import { describe, it, expect } from "vitest";
import type { IncomingMessage } from "node:http";
import { resolveApiKey } from "../src/http.js";
import type { McpConfig } from "../src/config.js";

function fakeConfig(defaultApiKey?: string): McpConfig {
  return {
    apiUrl: "http://localhost:8000",
    defaultApiKey,
    port: 3001,
    requestTimeoutMs: 30000,
    createCourseTimeoutMs: 600000,
  };
}

function fakeRequest(headers: Record<string, string>): IncomingMessage {
  return { headers } as unknown as IncomingMessage;
}

describe("resolveApiKey", () => {
  it("prefers a Bearer Authorization header over the configured default", () => {
    const req = fakeRequest({ authorization: "Bearer sn_from_request" });
    expect(resolveApiKey(req, fakeConfig("sn_default"))).toBe("sn_from_request");
  });

  it("accepts a case-insensitive Bearer prefix", () => {
    const req = fakeRequest({ authorization: "bearer sn_from_request" });
    expect(resolveApiKey(req, fakeConfig())).toBe("sn_from_request");
  });

  it("falls back to X-Api-Key when there is no Authorization header", () => {
    const req = fakeRequest({ "x-api-key": "sn_header_key" });
    expect(resolveApiKey(req, fakeConfig())).toBe("sn_header_key");
  });

  it("falls back to the configured default when the request carries no credential", () => {
    const req = fakeRequest({});
    expect(resolveApiKey(req, fakeConfig("sn_default"))).toBe("sn_default");
  });

  it("returns undefined when neither the request nor the config has a key", () => {
    const req = fakeRequest({});
    expect(resolveApiKey(req, fakeConfig())).toBeUndefined();
  });

  it("ignores a non-Bearer Authorization header and falls through", () => {
    const req = fakeRequest({ authorization: "Basic abc123" });
    expect(resolveApiKey(req, fakeConfig("sn_default"))).toBe("sn_default");
  });
});
