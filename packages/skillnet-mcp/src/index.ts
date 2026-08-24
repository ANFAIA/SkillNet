import { loadConfig } from "./config.js";
import { startHttpServer } from "./http.js";

export { createSkillNetMcpServer } from "./server.js";
export { SkillNetClient } from "./skillnetClient.js";
export { loadConfig } from "./config.js";

function main(): void {
  const config = loadConfig();
  startHttpServer(config);
}

main();
