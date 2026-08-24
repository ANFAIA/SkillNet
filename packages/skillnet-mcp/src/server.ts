import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { SkillNetClient, type SkillNetClientOptions } from "./skillnetClient.js";
import { registerListSkills } from "./tools/listSkills.js";
import { registerWhoKnows } from "./tools/whoKnows.js";
import { registerGetGap } from "./tools/getGap.js";
import { registerGetUserSkills } from "./tools/getUserSkills.js";
import { registerCreateCourse } from "./tools/createCourse.js";

/**
 * Builds one MCP server instance wired to a SkillNet API key.
 *
 * `verify_skill` is deliberately not registered here: it is the one write endpoint
 * that exists on `/ext/v1`, and this MVP does not expose it as a model-callable tool.
 * See docs/design/mcp-external-api.md 8.8.4 for why (a model should not be able to
 * change what an employee is recorded as knowing without a human in the loop).
 */
export function createSkillNetMcpServer(clientOptions: SkillNetClientOptions): McpServer {
  const server = new McpServer({
    name: "skillnet-mcp",
    version: "0.1.0",
  });

  const client = new SkillNetClient(clientOptions);

  registerListSkills(server, client);
  registerWhoKnows(server, client);
  registerGetGap(server, client);
  registerGetUserSkills(server, client);
  registerCreateCourse(server, client);

  return server;
}
