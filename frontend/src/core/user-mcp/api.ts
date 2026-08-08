import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

/**
 * Per-user MCP server registry API (``/api/user/mcp``).
 *
 * Every user manages their own MCP servers; the runtime loads tools only
 * from these rows, so user A's servers are never visible to user B. All
 * requests go through the CSRF-protected ``fetcher`` wrapper -- state
 * changes must NOT use a raw ``fetch`` (mirroring the user-models
 * "no bare fetch" convention).
 */

export type MCPTransport = "stdio" | "sse" | "http";

export interface UserMCPServer {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  transport: MCPTransport;
  command: string | null;
  args: string[] | null;
  /** Always masked to "***" by the gateway; real values never round-trip. */
  env: Record<string, string> | null;
  env_set: boolean;
  url: string | null;
  tool_name_prefix: boolean;
  tool_call_timeout: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserMCPServerCreatePayload {
  name: string;
  display_name?: string | null;
  description?: string | null;
  transport: MCPTransport;
  command?: string | null;
  args?: string[] | null;
  env?: Record<string, string> | null;
  url?: string | null;
  tool_name_prefix?: boolean;
  tool_call_timeout?: number | null;
}

export interface UserMCPServerUpdatePayload {
  display_name?: string | null;
  description?: string | null;
  transport?: MCPTransport;
  command?: string | null;
  args?: string[] | null;
  /** Replace the whole env map (secrets never round-trip through GET). */
  set_env?: Record<string, string> | null;
  clear_env?: boolean;
  url?: string | null;
  tool_name_prefix?: boolean;
  tool_call_timeout?: number | null;
}

async function readErrorDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  const error = (await response.json().catch(() => ({}))) as {
    detail?: unknown;
  };
  return typeof error.detail === "string" ? error.detail : fallback;
}

export async function loadUserMCPServers(): Promise<UserMCPServer[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/user/mcp`);
  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to load MCP servers"),
    );
  }
  const data = (await response.json()) as { servers: UserMCPServer[] };
  return data.servers ?? [];
}

export async function createUserMCPServer(
  payload: UserMCPServerCreatePayload,
): Promise<UserMCPServer> {
  const response = await fetch(`${getBackendBaseURL()}/api/user/mcp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to register MCP server"),
    );
  }
  return response.json() as Promise<UserMCPServer>;
}

export async function updateUserMCPServer(
  name: string,
  payload: UserMCPServerUpdatePayload,
): Promise<UserMCPServer> {
  const response = await fetch(`${getBackendBaseURL()}/api/user/mcp/${name}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to update MCP server"),
    );
  }
  return response.json() as Promise<UserMCPServer>;
}

export async function deleteUserMCPServer(name: string): Promise<void> {
  const response = await fetch(`${getBackendBaseURL()}/api/user/mcp/${name}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to delete MCP server"),
    );
  }
}
