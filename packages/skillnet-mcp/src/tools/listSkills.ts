import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { SkillNetClient } from "../skillnetClient.js";
import { describeError } from "../errors.js";

const inputSchema = {
  category: z
    .string()
    .optional()
    .describe("Filter to skills in this category name only."),
  search: z
    .string()
    .optional()
    .describe("Filter to skills whose name matches this search term."),
};

export function registerListSkills(server: McpServer, client: SkillNetClient): void {
  server.registerTool(
    "list_skills",
    {
      title: "List skills",
      description:
        "List every skill tracked by this SkillNet organization, grouped by category. " +
        "Use this first to see what skills exist before calling who_knows, get_gap, or " +
        "get_user_skills with a specific skill name.",
      inputSchema,
      annotations: { readOnlyHint: true },
    },
    async (args) => {
      try {
        const categories = await client.listSkills(args);
        const totalSkills = categories.reduce((sum, c) => sum + c.skills.length, 0);
        const summary = categories
          .map((c) => `${c.name}: ${c.skills.map((s) => s.name).join(", ")}`)
          .join("\n");
        return {
          content: [
            {
              type: "text",
              text:
                totalSkills === 0
                  ? "No skills found for this organization."
                  : `${totalSkills} skill(s) across ${categories.length} categor${
                      categories.length === 1 ? "y" : "ies"
                    }:\n${summary}`,
            },
          ],
          structuredContent: { categories, total_skills: totalSkills },
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
