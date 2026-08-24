import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { SkillNetClient } from "../skillnetClient.js";
import { describeError } from "../errors.js";

const inputSchema = {
  skill: z.string().min(1).describe("Name of the skill to search for, e.g. 'python'."),
  min_level: z
    .enum(["low", "medium", "high"])
    .optional()
    .describe("Minimum skill level to include. Defaults to 'low' (any level)."),
};

export function registerWhoKnows(server: McpServer, client: SkillNetClient): void {
  server.registerTool(
    "who_knows",
    {
      title: "Who knows a skill",
      description:
        "Find employees who have a specific skill at or above a minimum level. " +
        "Use this when someone asks 'who can do X?' or 'who knows X?'. Returns each " +
        "matching employee's level, how the level was assessed (checkpoint vs manual), " +
        "and when it was last assessed.",
      inputSchema,
      annotations: { readOnlyHint: true },
    },
    async (args) => {
      try {
        const result = await client.whoKnows(args);
        const text =
          result.employees.length === 0
            ? `No one in this organization has '${result.skill}' at or above the requested level.`
            : `${result.employees.length} employee(s) know '${result.skill}':\n` +
              result.employees
                .map((e) => `- ${e.full_name}: ${e.level} (source: ${e.source})`)
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
