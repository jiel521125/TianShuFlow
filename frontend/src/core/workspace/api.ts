import { fetch as csrfFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "../config";

import type {
  FileListResponse,
  FileResponse,
  FolderResponse,
  UserWorkspace,
  WorkspaceDetailResponse,
  WorkspaceFile,
  WorkspaceFolder,
  WorkspaceListResponse,
} from "./types";

async function send<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  // csrfFetch injects X-CSRF-Token on state-changing methods and sends
  // credentials, so the gateway's CSRFMiddleware accepts these requests.
  const res = await csrfFetch(`${getBackendBaseURL()}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = (await res.json().catch(() => null)) as unknown;
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new Error(
      typeof detail === "string" ? detail : `Request failed (${res.status})`,
    );
  }
  return data as T;
}

// --------------------------------------------------------------------------
// Workspaces
// --------------------------------------------------------------------------

export function loadWorkspaces(): Promise<WorkspaceListResponse> {
  return send("GET", "/api/workspaces");
}

export function createWorkspace(body: {
  name: string;
  description?: string | null;
}): Promise<{ workspace: UserWorkspace }> {
  return send("POST", "/api/workspaces", body);
}

export function updateWorkspace(
  workspaceId: string,
  body: { name?: string; description?: string | null },
): Promise<{ workspace: UserWorkspace }> {
  return send("PATCH", `/api/workspaces/${workspaceId}`, body);
}

export function deleteWorkspace(workspaceId: string): Promise<void> {
  return send("DELETE", `/api/workspaces/${workspaceId}`);
}

export function loadWorkspaceDetail(
  workspaceId: string,
): Promise<WorkspaceDetailResponse> {
  return send("GET", `/api/workspaces/${workspaceId}`);
}

// --------------------------------------------------------------------------
// Folders
// --------------------------------------------------------------------------

export function createFolder(
  workspaceId: string,
  body: { name: string },
): Promise<FolderResponse> {
  return send("POST", `/api/workspaces/${workspaceId}/folders`, body);
}

export function updateFolder(
  workspaceId: string,
  folderId: string,
  body: { name?: string; sort_order?: number },
): Promise<FolderResponse> {
  return send(
    "PATCH",
    `/api/workspaces/${workspaceId}/folders/${folderId}`,
    body,
  );
}

export function deleteFolder(
  workspaceId: string,
  folderId: string,
): Promise<void> {
  return send("DELETE", `/api/workspaces/${workspaceId}/folders/${folderId}`);
}

// --------------------------------------------------------------------------
// Files
// --------------------------------------------------------------------------

function filesPath(workspaceId: string, folderId: string): string {
  return `/api/workspaces/${workspaceId}/folders/${folderId}/files`;
}

export function listFiles(
  workspaceId: string,
  folderId: string,
): Promise<FileListResponse> {
  return send("GET", filesPath(workspaceId, folderId));
}

export function createFile(
  workspaceId: string,
  folderId: string,
  body: { name: string; content?: string },
): Promise<FileResponse> {
  return send("POST", filesPath(workspaceId, folderId), body);
}

export function loadFile(
  workspaceId: string,
  folderId: string,
  fileId: string,
): Promise<FileResponse> {
  return send("GET", `${filesPath(workspaceId, folderId)}/${fileId}`);
}

export function updateFile(
  workspaceId: string,
  folderId: string,
  fileId: string,
  body: { name?: string; content?: string },
): Promise<FileResponse> {
  return send(
    "PATCH",
    `${filesPath(workspaceId, folderId)}/${fileId}`,
    body,
  );
}

export function deleteFile(
  workspaceId: string,
  folderId: string,
  fileId: string,
): Promise<void> {
  return send("DELETE", `${filesPath(workspaceId, folderId)}/${fileId}`);
}

// Convenience re-export so page components can reference folder type names
// without reaching into the API module.
export type { WorkspaceFile, WorkspaceFolder };
