/** Minimal fake `McpServer` that just records what `registerTool` was called with. */
export interface RegisteredTool {
  name: string;
  config: {
    title?: string;
    description?: string;
    inputSchema?: unknown;
    annotations?: { readOnlyHint?: boolean; destructiveHint?: boolean };
  };
  handler: (args: any) => Promise<any>;
}

export class FakeMcpServer {
  readonly tools = new Map<string, RegisteredTool>();

  registerTool(
    name: string,
    config: RegisteredTool["config"],
    handler: RegisteredTool["handler"]
  ): void {
    this.tools.set(name, { name, config, handler });
  }

  get(name: string): RegisteredTool {
    const tool = this.tools.get(name);
    if (!tool) throw new Error(`tool not registered: ${name}`);
    return tool;
  }
}
