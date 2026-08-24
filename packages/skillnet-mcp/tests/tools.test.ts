import { describe, it, expect, vi } from "vitest";
import { FakeMcpServer } from "./testHarness.js";
import { registerListSkills } from "../src/tools/listSkills.js";
import { registerWhoKnows } from "../src/tools/whoKnows.js";
import { registerGetGap } from "../src/tools/getGap.js";
import { registerGetUserSkills } from "../src/tools/getUserSkills.js";
import { registerCreateCourse } from "../src/tools/createCourse.js";
import { SkillNetApiError } from "../src/errors.js";
import type { SkillNetClient } from "../src/skillnetClient.js";

function fakeClient(overrides: Partial<SkillNetClient> = {}): SkillNetClient {
  return overrides as SkillNetClient;
}

describe("list_skills", () => {
  it("is read-only and reports totals on success", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      listSkills: vi.fn().mockResolvedValue([
        { id: "1", name: "Ventas", skills: [{ id: "a", name: "devoluciones" }] },
      ]),
    });
    registerListSkills(server as any, client);

    const tool = server.get("list_skills");
    expect(tool.config.annotations?.readOnlyHint).toBe(true);

    const result = await tool.handler({});
    expect(result.isError).toBeUndefined();
    expect(result.structuredContent.total_skills).toBe(1);
    expect(result.content[0].text).toContain("devoluciones");
  });

  it("surfaces API errors without throwing out of the tool", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      listSkills: vi.fn().mockRejectedValue(new SkillNetApiError("boom", 500, {})),
    });
    registerListSkills(server as any, client);

    const result = await server.get("list_skills").handler({});
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain("boom");
  });
});

describe("who_knows", () => {
  it("readOnlyHint is set and results are summarized", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      whoKnows: vi.fn().mockResolvedValue({
        skill: "python",
        employees: [{ user_id: "u1", full_name: "Juan Garcia", level: "high", source: "manual" }],
      }),
    });
    registerWhoKnows(server as any, client);

    const tool = server.get("who_knows");
    expect(tool.config.annotations?.readOnlyHint).toBe(true);
    const result = await tool.handler({ skill: "python" });
    expect(result.content[0].text).toContain("Juan Garcia");
    expect(result.structuredContent.employees).toHaveLength(1);
  });

  it("handles zero results gracefully", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      whoKnows: vi.fn().mockResolvedValue({ skill: "rust", employees: [] }),
    });
    registerWhoKnows(server as any, client);

    const result = await server.get("who_knows").handler({ skill: "rust" });
    expect(result.content[0].text).toContain("No one");
  });

  it("propagates errors as tool errors, not exceptions", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      whoKnows: vi.fn().mockRejectedValue(new Error("network down")),
    });
    registerWhoKnows(server as any, client);

    const result = await server.get("who_knows").handler({ skill: "python" });
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain("network down");
  });
});

describe("get_gap", () => {
  it("is read-only and lists gap severities", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      getGap: vi.fn().mockResolvedValue({
        gaps: [
          {
            skill: { id: "s1", name: "python" },
            total_users: 12,
            users_at_level: 2,
            coverage_ratio: 0.17,
            gap_severity: "critical",
          },
        ],
      }),
    });
    registerGetGap(server as any, client);

    const tool = server.get("get_gap");
    expect(tool.config.annotations?.readOnlyHint).toBe(true);
    const result = await tool.handler({});
    expect(result.content[0].text).toContain("critical");
  });

  it("reports an error result on failure", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({ getGap: vi.fn().mockRejectedValue(new Error("timeout")) });
    registerGetGap(server as any, client);

    const result = await server.get("get_gap").handler({});
    expect(result.isError).toBe(true);
  });
});

describe("get_user_skills", () => {
  it("is read-only and summarizes levels", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      getUserSkills: vi.fn().mockResolvedValue([
        { skill_id: "s1", skill_name: "devoluciones", level: "high", source: "checkpoint" },
        { skill_id: "s2", skill_name: "html_css", level: "medium", source: "manual" },
      ]),
    });
    registerGetUserSkills(server as any, client);

    const tool = server.get("get_user_skills");
    expect(tool.config.annotations?.readOnlyHint).toBe(true);
    const result = await tool.handler({ user_id: "u1" });
    expect(result.structuredContent.summary).toEqual({ low: 0, medium: 1, high: 1, total: 2 });
  });

  it("reports an error result on failure", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      getUserSkills: vi.fn().mockRejectedValue(new SkillNetApiError("not found", 404, {})),
    });
    registerGetUserSkills(server as any, client);

    const result = await server.get("get_user_skills").handler({ user_id: "missing" });
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain("not found");
  });
});

describe("create_course", () => {
  it("is not read-only and not marked destructive", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      createCourse: vi.fn().mockResolvedValue({
        course_id: "c1",
        title: "Onboarding",
        schema_status: "validated",
        node_count: 5,
        packs_ready: 5,
        packs_all_ready: true,
        packs_summary: "5/5 nodes ready",
        validated: true,
        enrolled_user_id: null,
        artifacts: [],
        warnings: [],
      }),
    });
    registerCreateCourse(server as any, client);

    const tool = server.get("create_course");
    expect(tool.config.annotations?.readOnlyHint).toBe(false);
    expect(tool.config.annotations?.destructiveHint).toBe(false);
  });

  it("surfaces partial success and warnings honestly instead of a flat success", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      createCourse: vi.fn().mockResolvedValue({
        course_id: "c1",
        title: "Higiene",
        schema_status: "validated",
        node_count: 8,
        packs_ready: 6,
        packs_all_ready: false,
        packs_summary: "6/8 nodes ready",
        validated: true,
        enrolled_user_id: null,
        artifacts: [],
        warnings: ["only 6/8 knowledge packs reached ready within the timeout"],
      }),
    });
    registerCreateCourse(server as any, client);

    const result = await server.get("create_course").handler({ title: "Higiene" });
    expect(result.isError).toBeUndefined();
    expect(result.content[0].text).toContain("not all ready yet");
    expect(result.content[0].text).toContain("Warnings:");
    expect(result.content[0].text).toContain("only 6/8 knowledge packs");
    expect(result.structuredContent.warnings).toHaveLength(1);
  });

  it("reports create_course failures as tool errors", async () => {
    const server = new FakeMcpServer();
    const client = fakeClient({
      createCourse: vi.fn().mockRejectedValue(new SkillNetApiError("courses:write required", 403, {})),
    });
    registerCreateCourse(server as any, client);

    const result = await server.get("create_course").handler({ title: "X" });
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain("courses:write");
  });
});
