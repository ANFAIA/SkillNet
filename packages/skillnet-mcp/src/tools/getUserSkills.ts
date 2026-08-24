import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { SkillNetClient } from "../skillnetClient.js";
import { describeError } from "../errors.js";

const inputSchema = {
  user_id: z
    .string()
    .min(1)
    .describe("The employee's SkillNet user id (UUID)."),
};

export function registerGetUserSkills(server: McpServer, client: SkillNetClient): void {
  server.registerTool(
    "get_user_skills",
    {
      title: "Get an employee's skills",
      description:
        "Get the complete skill profile for one employee: every skill they have, its " +
        "level, how it was assessed, and when. Use this when someone asks 'what does " +
        "X know?' or 'show me X's skill profile'. Requires the employee's user id — " +
        "use who_knows or the SkillNet admin panel to find it if you only have a name.",
      inputSchema,
      annotations: { readOnlyHint: true },
    },
    async (args) => {
      try {
        const skills = await client.getUserSkills(args.user_id);
        const counts = { low: 0, medium: 0, high: 0 };
        for (const s of skills) {
          if (s.level in counts) counts[s.level as keyof typeof counts] += 1;
        }
        const text =
          skills.length === 0
            ? "This employee has no recorded skills yet."
            : `${skills.length} skill(s) (${counts.high} high, ${counts.medium} medium, ` +
              `${counts.low} low):\n` +
              skills.map((s) => `- ${s.skill_name}: ${s.level}`).join("\n");
        return {
          content: [{ type: "text", text }],
          structuredContent: { skills, summary: { ...counts, total: skills.length } },
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
