/**
 * Minimal types and registration helper for WebMCP (`navigator.modelContext`), the W3C
 * Web Machine Learning Community Group draft that lets a page expose tools to AI agents
 * running in the browser. https://webmachinelearning.github.io/webmcp/
 *
 * The API is still a draft and only some browsers ship it, so registration is a no-op
 * when it is missing.
 */

export type WebMcpTool = {
  name: string;
  title?: string;
  description: string;
  /** JSON Schema for the tool's input object. */
  inputSchema?: Record<string, unknown>;
  annotations?: { readOnlyHint?: boolean };
  execute: (input: Record<string, unknown>, options: { signal: AbortSignal }) => unknown;
};

type ModelContext = {
  registerTool: (tool: WebMcpTool, options?: { signal?: AbortSignal }) => Promise<void> | void;
  /** Earlier previews unregistered by name instead of through the registration signal. */
  unregisterTool?: (name: string) => void;
};

declare global {
  interface Navigator {
    modelContext?: ModelContext;
  }
}

/** Registers `tools` until `signal` aborts. */
export function registerWebMcpTools(tools: WebMcpTool[], signal: AbortSignal) {
  const modelContext = typeof navigator === "undefined" ? undefined : navigator.modelContext;
  if (!modelContext?.registerTool) return;

  for (const tool of tools) {
    Promise.resolve()
      .then(() => (signal.aborted ? undefined : modelContext.registerTool(tool, { signal })))
      .catch((error: unknown) => console.warn(`WebMCP: could not register "${tool.name}".`, error));
  }
  signal.addEventListener(
    "abort",
    () => {
      for (const tool of tools) {
        try {
          modelContext.unregisterTool?.(tool.name);
        } catch {
          // Already removed through the signal.
        }
      }
    },
    { once: true },
  );
}
