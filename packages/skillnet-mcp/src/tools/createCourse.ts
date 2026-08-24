import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { SkillNetClient } from "../skillnetClient.js";
import { describeError } from "../errors.js";

const inputSchema = {
  title: z.string().min(1).max(300).describe("Title of the course to create."),
  document_id: z
    .string()
    .optional()
    .describe(
      "Optional id of an already-processed document (status='ready') to ground the " +
        "course schema on. Without it, the course is synthesized from the title alone."
    ),
  intent_density: z
    .number()
    .int()
    .min(1)
    .max(5)
    .optional()
    .describe("Depth of the generated course, 1 (shallow) to 5 (deep). Defaults to 3."),
  enroll_user_id: z
    .string()
    .optional()
    .describe("Optional employee user id to enroll in the course once it's ready."),
  generate_artifacts: z
    .array(z.enum(["podcast", "infographic"]))
    .optional()
    .describe("Media artifacts to generate for the first nodes, e.g. ['podcast']."),
  artifact_node_limit: z
    .number()
    .int()
    .min(0)
    .max(10)
    .optional()
    .describe("Max number of nodes to generate artifacts for. Defaults to 1."),
};

export function registerCreateCourse(server: McpServer, client: SkillNetClient): void {
  server.registerTool(
    "create_course",
    {
      title: "Create a course",
      description:
        "Create a full dynamic SkillNet course end to end in one call: propose the " +
        "schema, generate the knowledge packs (with automatic retries), review every " +
        "node, validate the course, and warm the first renders. Optionally enroll an " +
        "employee and generate artifacts (podcast, infographic). This can take several " +
        "minutes on a real LLM provider, and it can succeed partially — some knowledge " +
        "packs may still be generating in the background when this returns. Check " +
        "'packs_all_ready' and 'warnings' in the result rather than assuming full success.",
      inputSchema,
      annotations: { readOnlyHint: false, destructiveHint: false },
    },
    async (args) => {
      try {
        const result = await client.createCourse(args);
        const lines: string[] = [
          `Course '${result.title}' created (id ${result.course_id}).`,
          `Schema: ${result.schema_status}, ${result.node_count} node(s).`,
          `Knowledge packs: ${result.packs_summary}` +
            (result.packs_all_ready ? "" : " — not all ready yet, generation continues in the background."),
          `Validated: ${result.validated ? "yes" : "no"}.`,
        ];
        if (result.enrolled_user_id) {
          lines.push(`Enrolled user: ${result.enrolled_user_id}.`);
        }
        if (result.artifacts?.length) {
          lines.push(
            `Artifacts requested: ${result.artifacts
              .map((a) => `${a.kind} (${a.status})`)
              .join(", ")}.`
          );
        }
        if (result.warnings?.length) {
          lines.push(`Warnings: ${result.warnings.join("; ")}`);
        }
        return {
          content: [{ type: "text", text: lines.join("\n") }],
          structuredContent: result,
          // Not an MCP protocol error even when the course only partially converged —
          // the call succeeded and returned honest, structured partial-success data.
          // A caller that wants to treat "not fully ready" as failure should inspect
          // packs_all_ready / validated / warnings above.
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
