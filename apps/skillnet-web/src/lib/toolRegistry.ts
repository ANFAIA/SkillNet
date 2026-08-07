/**
 * Tool registry — a simple map of named functions the AI agent can invoke
 * via `action` SSE events during a chat stream.
 *
 * Register tools at app startup:
 *
 *   registerTool('set_locale', ({ locale }) => { i18n.changeLanguage(locale) })
 *
 * The chat parser calls `executeTool` when it receives an `action` event.
 */

type ToolFn = (args: Record<string, unknown>) => void | Promise<void>

const registry = new Map<string, ToolFn>()

/** Register a frontend tool the AI agent can call. */
export function registerTool(name: string, fn: ToolFn): void {
  registry.set(name, fn)
}

/** Unregister a previously registered tool. */
export function unregisterTool(name: string): void {
  registry.delete(name)
}

/**
 * Execute a registered tool by name. Called by SSE parsers when they
 * receive an `action` event. Silently warns if the tool is unknown.
 */
export async function executeTool(
  tool: string,
  args: Record<string, unknown>,
): Promise<void> {
  const fn = registry.get(tool)
  if (!fn) {
    console.warn(`[toolRegistry] Unknown tool: "${tool}"`)
    return
  }
  try {
    await fn(args)
  } catch (err) {
    console.error(`[toolRegistry] Error executing tool "${tool}":`, err)
  }
}
