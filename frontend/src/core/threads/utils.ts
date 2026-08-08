import type { Message } from "@langchain/langgraph-sdk";

import type { AgentThread, AgentThreadContext } from "./types";

// Namespaced to match other internal metadata keys (``tianshu_sidecar``,
// ``tianshu_branch``) so it cannot collide with a future feature or a
// client-supplied key. Keep in sync with the backend thread_meta constant and
// the E2E mock-api constant.
export const THREAD_PINNED_METADATA_KEY = "tianshu_pinned";

// Thread ↔ workspace folder binding metadata keys. Follows the same
// ``tianshu_`` namespacing as THREAD_PINNED_METADATA_KEY so it cannot collide
// with a future feature or a client-supplied key.
export const THREAD_WORKSPACE_ID_KEY = "tianshu_workspace_id";
export const THREAD_WORKSPACE_FOLDER_ID_KEY = "tianshu_workspace_folder_id";
export const THREAD_WORKSPACE_NAME_KEY = "tianshu_workspace_name";
export const THREAD_WORKSPACE_FOLDER_NAME_KEY = "tianshu_workspace_folder_name";

export type WorkspaceFolderBinding = {
  workspaceId: string;
  folderId: string;
  workspaceName: string;
  folderName: string;
};

export function workspaceFolderBindingOfThread(
  thread: Pick<AgentThread, "metadata">,
): WorkspaceFolderBinding | null {
  const metadata = thread.metadata;
  if (!metadata) {
    return null;
  }
  const workspaceId = metadata[THREAD_WORKSPACE_ID_KEY];
  const folderId = metadata[THREAD_WORKSPACE_FOLDER_ID_KEY];
  if (
    typeof workspaceId !== "string" ||
    typeof folderId !== "string" ||
    workspaceId.length === 0 ||
    folderId.length === 0
  ) {
    return null;
  }
  const workspaceName = metadata[THREAD_WORKSPACE_NAME_KEY];
  const folderName = metadata[THREAD_WORKSPACE_FOLDER_NAME_KEY];
  return {
    workspaceId,
    folderId,
    workspaceName:
      typeof workspaceName === "string" && workspaceName.length > 0
        ? workspaceName
        : workspaceId,
    folderName:
      typeof folderName === "string" && folderName.length > 0
        ? folderName
        : folderId,
  };
}

export type ChannelThreadSource = {
  type: "im_channel";
  provider: string;
  label: string;
};

type ThreadRouteTarget =
  | string
  | {
      thread_id: string;
      context?: Pick<AgentThreadContext, "agent_name"> | null;
      metadata?: Record<string, unknown> | null;
    };

export function pathOfThread(
  thread: ThreadRouteTarget,
  context?: Pick<AgentThreadContext, "agent_name"> | null,
) {
  const threadId = typeof thread === "string" ? thread : thread.thread_id;
  const encodedThreadId = encodeURIComponent(threadId);
  let agentName: string | undefined;
  if (typeof thread === "string") {
    agentName = context?.agent_name;
  } else {
    agentName = thread.context?.agent_name;
    if (!agentName) {
      const metaAgent = thread.metadata?.agent_name;
      if (typeof metaAgent === "string") {
        agentName = metaAgent;
      }
    }
  }

  return agentName
    ? `/workspace/agents/${encodeURIComponent(agentName)}/chats/${encodedThreadId}`
    : `/workspace/chats/${encodedThreadId}`;
}

export function textOfMessage(message: Message) {
  if (typeof message.content === "string") {
    return message.content;
  } else if (Array.isArray(message.content)) {
    // Flat join ("") for single-line consumers (input box, titles); the rendered
    // body uses extractContentFromMessage, which joins multi-part content with "\n".
    const text = message.content
      .map((part) =>
        typeof part === "string" ? part : part.type === "text" ? part.text : "",
      )
      .join("");
    return text.length > 0 ? text : null;
  }
  return null;
}

export function titleOfThread(thread: AgentThread) {
  return thread.values?.title ?? "Untitled";
}

export function isThreadPinned(thread: Pick<AgentThread, "metadata">) {
  return thread.metadata?.[THREAD_PINNED_METADATA_KEY] === true;
}

export function sortPinnedThreads<T extends Pick<AgentThread, "metadata">>(
  threads: readonly T[],
) {
  return threads
    .map((thread, index) => ({ thread, index }))
    .sort((left, right) => {
      const pinnedDiff =
        Number(isThreadPinned(right.thread)) -
        Number(isThreadPinned(left.thread));
      return pinnedDiff || left.index - right.index;
    })
    .map(({ thread }) => thread);
}

const CHANNEL_PROVIDER_LABELS: Record<string, string> = {
  dingtalk: "DingTalk",
  discord: "Discord",
  feishu: "Feishu",
  slack: "Slack",
  telegram: "Telegram",
  wechat: "WeChat",
  wecom: "WeCom",
};

function labelOfChannelProvider(provider: string) {
  return CHANNEL_PROVIDER_LABELS[provider] ?? provider;
}

export function channelSourceOfThread(
  thread: Pick<AgentThread, "metadata">,
): ChannelThreadSource | null {
  const source = thread.metadata?.channel_source;
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    return null;
  }

  if (Reflect.get(source, "type") !== "im_channel") {
    return null;
  }

  const provider = Reflect.get(source, "provider");
  if (typeof provider !== "string" || provider.trim().length === 0) {
    return null;
  }

  const normalizedProvider = provider.trim().toLowerCase();
  return {
    type: "im_channel",
    provider: normalizedProvider,
    label: labelOfChannelProvider(normalizedProvider),
  };
}
