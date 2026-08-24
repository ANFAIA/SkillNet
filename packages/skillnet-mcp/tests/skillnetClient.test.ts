import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SkillNetClient } from "../src/skillnetClient.js";
import { SkillNetApiError } from "../src/errors.js";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("SkillNetClient", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const client = () =>
    new SkillNetClient({ apiUrl: "http://api.internal:8000", apiKey: "sn_test_secret" });

  it("sends the API key as a Bearer token and never elsewhere", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    await client().listSkills();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://api.internal:8000/ext/v1/skills");
    expect(init.headers.authorization).toBe("Bearer sn_test_secret");
  });

  it("list_skills forwards category/search as query params", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([{ id: "1", name: "Ventas", skills: [] }]));
    await client().listSkills({ category: "Ventas", search: "dev" });

    const [url] = fetchMock.mock.calls[0];
    const parsed = new URL(String(url));
    expect(parsed.searchParams.get("category")).toBe("Ventas");
    expect(parsed.searchParams.get("search")).toBe("dev");
  });

  it("who_knows returns the parsed response on success", async () => {
    const payload = { skill: "python", employees: [{ user_id: "u1", full_name: "Juan", level: "high", source: "manual" }] };
    fetchMock.mockResolvedValueOnce(jsonResponse(payload));

    const result = await client().whoKnows({ skill: "python" });
    expect(result).toEqual(payload);
  });

  it("create_course POSTs the body and uses the long timeout budget", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ course_id: "c1", warnings: [] }));
    const c = new SkillNetClient({
      apiUrl: "http://api.internal:8000",
      apiKey: "sn_test_secret",
      createCourseTimeoutMs: 600_000,
    });

    await c.createCourse({ title: "Onboarding" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://api.internal:8000/ext/v1/courses/full");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ title: "Onboarding" });
  });

  it("raises a SkillNetApiError carrying the API's error envelope, not raw internals", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: "not_found", message: "Skill 'blockchain' not found in this organization" },
        404
      )
    );

    await expect(client().whoKnows({ skill: "blockchain" })).rejects.toMatchObject({
      status: 404,
      message: expect.stringContaining("blockchain"),
    });
  });

  it("raises a generic, safe error when the response has no JSON body", async () => {
    fetchMock.mockResolvedValueOnce(new Response("plain text failure", { status: 500 }));

    let caught: unknown;
    try {
      await client().getGap();
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(SkillNetApiError);
    expect((caught as SkillNetApiError).status).toBe(500);
  });

  it("never includes the API key in a thrown error's message", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ error: "forbidden", message: "nope" }, 403));

    let caught: unknown;
    try {
      await client().getUserSkills("u1");
    } catch (error) {
      caught = error;
    }
    expect(String((caught as Error).message)).not.toContain("sn_test_secret");
  });

  it("aborts the request once the configured timeout elapses", async () => {
    fetchMock.mockImplementation((_url: unknown, init: { signal: AbortSignal }) => {
      return new Promise((_resolve, reject) => {
        init.signal.addEventListener("abort", () => reject(new Error("aborted")));
      });
    });

    const fastClient = new SkillNetClient({
      apiUrl: "http://api.internal:8000",
      apiKey: "sn_test_secret",
      requestTimeoutMs: 5,
    });

    await expect(fastClient.listSkills()).rejects.toThrow();
  });
});
