import { fetch as csrfFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

/**
 * Git integration API (GitHub / Gitee).
 *
 * - ``/api/git/config``           -- per-user PAT tokens (masked outbound)
 * - ``/api/folders/{id}/git``     -- folder → repository binding
 * - ``/api/git/pull`` ``/push``   -- SSE streams with command logs
 *
 * Tokens are write-only: GET never returns a plaintext token, only a
 * ``configured`` flag. State changes go through the CSRF-protected
 * ``csrfFetch`` wrapper (no bare ``fetch``).
 */

export type GitProvider = "github" | "gitee";

export interface GitConfigStatus {
  github: { configured: boolean };
  gitee: { configured: boolean };
}

export interface FolderGitBinding {
  folder_id: string;
  provider: GitProvider | null;
  repo_url: string | null;
  repo_name: string | null;
  git_updated_at: string | null;
}

/** One line of the operation log streamed from the gateway. */
export interface GitOperationLogEvent {
  line: string;
}

/** Terminal event; ``ok`` false carries the user-facing error message. */
export interface GitOperationDoneEvent {
  ok: boolean;
  message: string;
  updated?: number;
  pushed?: number;
  committed?: boolean;
}

export type GitOperationEvent = GitOperationLogEvent | GitOperationDoneEvent;

async function send<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
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
// Config
// --------------------------------------------------------------------------

export function loadGitConfig(): Promise<GitConfigStatus> {
  return send("GET", "/api/git/config");
}

export function saveGitConfig(body: {
  github_token?: string | null;
  gitee_token?: string | null;
}): Promise<GitConfigStatus> {
  return send("PUT", "/api/git/config", body);
}

// --------------------------------------------------------------------------
// Folder binding
// --------------------------------------------------------------------------

export function loadFolderGitBinding(
  folderId: string,
): Promise<FolderGitBinding> {
  return send("GET", `/api/folders/${folderId}/git`);
}

export function bindFolderGit(
  folderId: string,
  body: { provider: GitProvider; repo_url: string },
): Promise<FolderGitBinding> {
  return send("PUT", `/api/folders/${folderId}/git`, body);
}

// --------------------------------------------------------------------------
// Pull / Push (SSE)
// --------------------------------------------------------------------------

/**
 * Run a git operation (pull/push) and stream its progress.
 *
 * Returns an async generator of events: ``{kind: "log", line}`` for each
 * command output line and ``{kind: "done", ok, message, ...}`` for the
 * terminal event. Throws on transport errors.
 */
export async function* runGitOperation(
  action: "pull" | "push",
  folderId: string,
  signal?: AbortSignal,
): AsyncGenerator<
  { kind: "log"; line: string } | { kind: "done" } & GitOperationDoneEvent
> {
  const res = await csrfFetch(
    `${getBackendBaseURL()}/api/git/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_id: folderId }),
      signal,
    },
  );
  if (!res.ok || !res.body) {
    const detail = (await res.json().catch(() => null)) as { detail?: unknown };
    throw new Error(
      typeof detail?.detail === "string"
        ? detail.detail
        : `Request failed (${res.status})`,
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line; parse one at a time.
      let sepIndex: number;
      while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        const event = parseSseFrame(frame);
        if (!event) continue;
        if (event.kind === "done") {
          yield event;
          // Drain any trailing buffered frames (defensive).
          reader.cancel().catch(() => undefined);
          return;
        }
        yield event;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseFrame(frame: string): (
  | { kind: "log"; line: string }
  | ({ kind: "done" } & GitOperationDoneEvent)
) | null {
  let eventName = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      data += line.slice("data:".length).trim();
    }
  }
  if (!data) return null;
  if (eventName === "log") {
    const parsed = JSON.parse(data) as { line?: string };
    return { kind: "log", line: parsed.line ?? "" };
  }
  if (eventName === "done") {
    const parsed = JSON.parse(data) as GitOperationDoneEvent;
    return { kind: "done", ...parsed };
  }
  return null;
}
