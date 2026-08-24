import { describe, it, expect } from "vitest";
import { loadConfig } from "../src/config.js";

describe("loadConfig", () => {
  it("requires SKILLNET_API_URL", () => {
    expect(() => loadConfig({} as NodeJS.ProcessEnv)).toThrow(/SKILLNET_API_URL/);
  });

  it("strips a trailing slash from the API URL", () => {
    const config = loadConfig({ SKILLNET_API_URL: "http://localhost:8000/" } as NodeJS.ProcessEnv);
    expect(config.apiUrl).toBe("http://localhost:8000");
  });

  it("applies documented defaults", () => {
    const config = loadConfig({ SKILLNET_API_URL: "http://localhost:8000" } as NodeJS.ProcessEnv);
    expect(config.port).toBe(3001);
    expect(config.defaultApiKey).toBeUndefined();
    expect(config.requestTimeoutMs).toBe(30000);
    expect(config.createCourseTimeoutMs).toBe(600000);
  });

  it("reads overrides from the environment", () => {
    const config = loadConfig({
      SKILLNET_API_URL: "http://localhost:8000",
      SKILLNET_API_KEY: "sn_default",
      MCP_HTTP_PORT: "4000",
      SKILLNET_REQUEST_TIMEOUT_MS: "1000",
      SKILLNET_CREATE_COURSE_TIMEOUT_MS: "2000",
    } as NodeJS.ProcessEnv);
    expect(config.defaultApiKey).toBe("sn_default");
    expect(config.port).toBe(4000);
    expect(config.requestTimeoutMs).toBe(1000);
    expect(config.createCourseTimeoutMs).toBe(2000);
  });
});
