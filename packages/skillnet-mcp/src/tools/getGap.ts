import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { SkillNetClient } from "../skillnetClient.js";
import { describeError } from "../errors.js";

const inputSchema = {
  skill: z
    .string()
    .optional()
    .describe("Look at gaps for this specific skill only. Omit to see all gaps."),
  min_level: z
    .enum(["low", "medium", "high"])
    .optional()
    .describe("Minimum level considered 'covered'. Defaults to 'medium'."),
  threshold: z
    .number()
    .min(0)
    .max(1)
    .optional()
    .describe(
      "Coverage ratio (0-1) below which a skill counts as a gap. Defaults to 0.5."
    ),
};

export function registerGetGap(server: McpServer, client: SkillNetClient): void {
  server.registerTool(
    "get_gap",
    {
      title: "Analyze skill gaps",
      description:
        "Analyze skill gaps in the organization: skills the company needs but where " +
        "too few employees are covered at the minimum level. Use this when someone " +
        "asks 'what skills are we missing?' or 'who needs training in X?'. Returns " +
        "each gap's severity (critical/warning/moderate) and the coverage ratio.",
      inputSchema,
      annotations: { readOnlyHint: true },
    },
    async (args) => {
      try {
        const result = await client.getGap(args);
        const text =
          result.gaps.length === 0
            ? "No skill gaps detected."
            : result.gaps
                .map(
                  (g) =>
                    `- ${g.skill.name} (${g.gap_severity}): ${g.users_at_level}/${g.total_users} ` +
                    `covered (${Math.round(g.coverage_ratio * 100)}%)`
                )
                .join("\n");
        return {
          content: [{ type: "text", text }],
          structuredContent: result,
        };
      } catch (error) {
        return {
          content: [{ type: "text", text: describeError(error) }],
          isError: true,
        };
      }
    }
  );
}
