"use client";

import {
  CheckIcon,
  FolderIcon,
  GitBranchIcon,
  LibraryIcon,
  LoaderCircleIcon,
  Loader2Icon,
  TerminalIcon,
  Undo2Icon,
  XIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuItem,
  PromptInputActionMenuTrigger,
} from "@/components/ai-elements/prompt-input";
import {
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useI18n } from "@/core/i18n/hooks";
import {
  runGitOperation,
  type GitOperationDoneEvent,
} from "@/core/git/api";
import { useThreadWorkspaceBinding } from "@/core/threads/hooks";
import type { WorkspaceFolderBinding } from "@/core/threads/utils";
import { useWorkspaceDetail, useWorkspaces } from "@/core/workspace/hooks";
import { cn } from "@/lib/utils";

export type GitOperationAction = "pull" | "push";

export type GitOperationInfo = {
  action: GitOperationAction;
  folderId: string;
  folderName: string;
};

type GitActionMenuProps = {
  threadId: string;
  binding: WorkspaceFolderBinding | null;
  /** Whether the backend thread exists yet (false = brand-new conversation). */
  threadReady: boolean;
  disabled?: boolean;
  onPendingBind?: (binding: WorkspaceFolderBinding | null) => void;
  onOperationStart?: (info: GitOperationInfo) => void;
};

/**
 * Input-toolbar Git control (pull / push) for the bound workspace folder.
 *
 * - Bound folder → pull/push starts immediately against that folder.
 * - First pull without a binding → the menu opens a workspace/folder picker
 *   (same two-level pattern as ThreadWorkspaceBinding); the chosen folder is
 *   bound first, then the pull starts against it.
 * - The actual SSE streaming is rendered by ``GitOperationPanel`` (the caller
 *   passes ``onOperationStart`` info down to it), so the panel and this menu
 *   never run two parallel streams.
 */
export function GitActionMenu({
  threadId,
  binding,
  threadReady,
  disabled = false,
  onPendingBind,
  onOperationStart,
}: GitActionMenuProps) {
  const { t } = useI18n();
  const { bind } = useThreadWorkspaceBinding(threadId);
  const [open, setOpen] = useState(false);
  const [pickerMode, setPickerMode] = useState<GitOperationAction | null>(null);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(
    null,
  );

  const { data: workspaces, isLoading: spacesLoading } = useWorkspaces();
  const { data: detail, isLoading: detailLoading } =
    useWorkspaceDetail(selectedWorkspaceId);
  const folders = detail?.folders ?? [];

  // Reset the two-level picker whenever the menu closes.
  useEffect(() => {
    if (!open) {
      setPickerMode(null);
      setSelectedWorkspaceId(null);
    }
  }, [open]);

  const start = (action: GitOperationAction, folder: { id: string; name: string }) => {
    setOpen(false);
    onOperationStart?.({
      action,
      folderId: folder.id,
      folderName: folder.name,
    });
  };

  const handlePull = () => {
    if (binding) {
      start("pull", { id: binding.folderId, name: binding.folderName });
      return;
    }
    setPickerMode("pull");
  };

  const handlePush = () => {
    if (binding) {
      start("push", { id: binding.folderId, name: binding.folderName });
      return;
    }
    toast.error(t.gitToolbar.pushWithoutBinding);
    setOpen(false);
  };

  const handlePickFolder = async (folderId: string, folderName: string) => {
    const workspace = workspaces?.find((ws) => ws.id === selectedWorkspaceId);
    if (!workspace || pickerMode === null) return;
    const next: WorkspaceFolderBinding = {
      workspaceId: workspace.id,
      folderId,
      workspaceName: workspace.name,
      folderName,
    };
    if (threadReady) {
      // Persist the binding on the real thread, then start the operation.
      try {
        await bind.mutateAsync(next);
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : String(error),
        );
        return;
      }
    } else {
      // Brand-new conversation: stage the binding so the page applies it once
      // the thread exists, then run the pull against the chosen folder.
      onPendingBind?.(next);
    }
    start(pickerMode, { id: folderId, name: folderName });
  };

  const triggerLabel = binding
    ? t.gitToolbar.triggerBound(binding.folderName)
    : t.gitToolbar.trigger;

  return (
    <PromptInputActionMenu open={open} onOpenChange={setOpen}>
      <PromptInputActionMenuTrigger
        aria-label={triggerLabel}
        className={cn(
          "gap-1! px-2!",
          binding && "bg-accent text-accent-foreground hover:bg-accent/80",
        )}
        data-testid="git-action-menu-trigger"
        disabled={disabled}
      >
        <GitBranchIcon className="size-3" />
        {binding && (
          <span className="max-w-24 truncate text-xs font-normal">
            {binding.folderName}
          </span>
        )}
      </PromptInputActionMenuTrigger>

      <PromptInputActionMenuContent className="w-80">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-muted-foreground text-xs">
            {pickerMode === null
              ? binding
                ? t.gitToolbar.boundFolder(binding.folderName)
                : t.gitToolbar.selectAction
              : pickerMode === "pull"
                ? t.gitToolbar.choosePullFolder
                : t.gitToolbar.choosePushFolder}
          </DropdownMenuLabel>

          {pickerMode === null ? (
            <>
              <PromptInputActionMenuItem
                className="text-muted-foreground/65"
                onSelect={(e) => {
                  // When no folder is bound yet, keep the menu open so the
                  // workspace/folder picker can appear (Radix closes the menu
                  // by default on select, which would reset pickerMode).
                  if (!binding) e.preventDefault();
                  void handlePull();
                }}
              >
                <GitBranchIcon className="mr-2 size-4" />
                <div className="flex flex-col">
                  <span className="font-medium">{t.gitToolbar.pull}</span>
                  <span className="text-muted-foreground text-xs">
                    {t.gitToolbar.pullDescription}
                  </span>
                </div>
              </PromptInputActionMenuItem>
              <PromptInputActionMenuItem
                className="text-muted-foreground/65"
                onSelect={() => {
                  void handlePush();
                }}
              >
                <GitBranchIcon className="mr-2 size-4" />
                <div className="flex flex-col">
                  <span className="font-medium">{t.gitToolbar.push}</span>
                  <span className="text-muted-foreground text-xs">
                    {t.gitToolbar.pushDescription}
                  </span>
                </div>
              </PromptInputActionMenuItem>
            </>
          ) : selectedWorkspaceId === null ? (
            spacesLoading ? (
              <div className="text-muted-foreground flex items-center justify-center gap-2 px-3 py-6 text-sm">
                <LoaderCircleIcon className="size-4 animate-spin" />
                {t.common.loading}
              </div>
            ) : !workspaces || workspaces.length === 0 ? (
              <div className="border-muted text-muted-foreground rounded-lg border border-dashed px-4 py-6 text-center text-sm">
                <p>{t.threadWorkspace.noWorkspaces}</p>
                <PromptInputActionMenuItem
                  asChild
                  className="mt-3 justify-center"
                >
                  <Link href="/workspace/workspace">
                    <LibraryIcon />
                    {t.threadWorkspace.createWorkspace}
                  </Link>
                </PromptInputActionMenuItem>
              </div>
            ) : (
              workspaces.map((ws) => (
                <PromptInputActionMenuItem
                  key={ws.id}
                  className="text-muted-foreground/65"
                  onSelect={(e) => {
                    e.preventDefault();
                    setSelectedWorkspaceId(ws.id);
                  }}
                >
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-1 font-bold">
                      <LibraryIcon className="mr-2 size-4" />
                      <span className="truncate">{ws.name}</span>
                    </div>
                    <div className="pl-7 text-xs">
                      {t.threadWorkspace.selectFolder}
                    </div>
                  </div>
                </PromptInputActionMenuItem>
              ))
            )
          ) : (
            <>
              <PromptInputActionMenuItem
                className="text-muted-foreground/65"
                onSelect={(e) => {
                  e.preventDefault();
                  setSelectedWorkspaceId(null);
                }}
              >
                <Undo2Icon className="mr-2 size-4" />
                {t.threadWorkspace.backToWorkspaces}
              </PromptInputActionMenuItem>
              <DropdownMenuSeparator />
              {detailLoading ? (
                <div className="text-muted-foreground flex items-center justify-center gap-2 px-3 py-4 text-sm">
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  {t.common.loading}
                </div>
              ) : folders.length === 0 ? (
                <div className="text-muted-foreground px-3 py-6 text-center text-sm">
                  {t.threadWorkspace.noFolders}
                </div>
              ) : (
                folders.map((folder) => (
                  <PromptInputActionMenuItem
                    key={folder.id}
                    className="text-muted-foreground/65"
                    onSelect={() =>
                      void handlePickFolder(folder.id, folder.name)
                    }
                  >
                    <div className="flex items-center gap-1 font-bold">
                      <FolderIcon
                        className={cn(
                          "mr-2 size-4",
                          binding?.folderId === folder.id &&
                            "text-accent-foreground",
                        )}
                      />
                      <span className="truncate">{folder.name}</span>
                    </div>
                    {binding?.folderId === folder.id ? (
                      <CheckIcon className="ml-auto size-4" />
                    ) : (
                      <div className="ml-auto size-4" />
                    )}
                  </PromptInputActionMenuItem>
                ))
              )}
            </>
          )}
        </DropdownMenuGroup>
      </PromptInputActionMenuContent>
    </PromptInputActionMenu>
  );
}

// ---------------------------------------------------------------------------
// Live operation log panel (rendered above the input box)
// ---------------------------------------------------------------------------

export type GitLogLine = {
  id: number;
  text: string;
};

/**
 * Panel that streams a git operation's SSE logs above the composer.
 * ``info`` triggers a fresh run; callers pass ``onLog``/``onDone`` from the
 * same GitActionMenu instance so the panel and the toolbar share one stream.
 */
export function GitOperationPanel({
  info,
  onClose,
}: {
  info: GitOperationInfo;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [lines, setLines] = useState<GitLogLine[]>([]);
  const [done, setDone] = useState<GitOperationDoneEvent | null>(null);
  const nextIdRef = useRef(0);
  const [streamError, setStreamError] = useState<string | null>(null);

  useEffect(() => {
    setLines([]);
    setDone(null);
    setStreamError(null);
    const controller = new AbortController();

    const stream = async () => {
      try {
        for await (const event of runGitOperation(
          info.action,
          info.folderId,
          controller.signal,
        )) {
          if (event.kind === "log") {
            setLines((current) => [
              ...current,
              { id: nextIdRef.current++, text: event.line },
            ]);
          } else {
            setDone(event);
          }
        }
      } catch (error) {
        // A clean abort (StrictMode remount / panel close) is not an error.
        if (controller.signal.aborted) return;
        setStreamError(
          error instanceof Error ? error.message : String(error),
        );
      }
    };
    void stream();

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info.folderId, info.action]);

  const running = !done && !streamError;
  const heading =
    info.action === "pull"
      ? t.gitToolbar.pullingFolder(info.folderName)
      : t.gitToolbar.pushingFolder(info.folderName);

  return (
    <div className="border-border bg-card text-card-foreground rounded-xl border p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {running ? (
            <Loader2Icon className="text-primary size-4 animate-spin" />
          ) : done?.ok ? (
            <CheckIcon className="size-4 text-emerald-600" />
          ) : (
            <XIcon className="text-destructive size-4" />
          )}
          <TerminalIcon className="text-muted-foreground size-4 shrink-0" />
          <span className="truncate text-sm font-medium">{heading}</span>
        </div>
        <button
          type="button"
          aria-label={t.common.close}
          className="text-muted-foreground hover:text-foreground shrink-0 cursor-pointer rounded p-1 transition-colors"
          onClick={onClose}
        >
          <XIcon className="size-4" />
        </button>
      </div>
      <div className="bg-muted/50 text-muted-foreground max-h-48 overflow-y-auto rounded-md p-2 font-mono text-xs leading-5">
        {lines.map((line) => (
          <div key={line.id} className="whitespace-pre-wrap break-all">
            {line.text}
          </div>
        ))}
        {running && <div className="animate-pulse">…</div>}
        {done && (
          <div
            className={cn(
              "mt-1 font-medium",
              done.ok ? "text-emerald-600" : "text-destructive",
            )}
          >
            {done.message}
          </div>
        )}
        {streamError && (
          <div className="text-destructive mt-1 font-medium">{streamError}</div>
        )}
      </div>
    </div>
  );
}
