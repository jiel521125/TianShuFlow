"use client";

import {
  CheckIcon,
  FolderIcon,
  FolderPlusIcon,
  LibraryIcon,
  LoaderCircleIcon,
  Undo2Icon,
  UnlinkIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
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
import { useThreadWorkspaceBinding } from "@/core/threads/hooks";
import type { WorkspaceFolderBinding } from "@/core/threads/utils";
import { useWorkspaceDetail, useWorkspaces } from "@/core/workspace/hooks";
import { cn } from "@/lib/utils";

/**
 * Input-toolbar control that binds a conversation to a workspace folder (project).
 * Uses the same action-menu pattern as the mode selector. The binding is
 * persisted in thread metadata (`tianshu_workspace_*` keys), which is what
 * lets conversation-produced documents be archived under the chosen folder
 * and lets the conversation load documents from that folder.
 */
export function ThreadWorkspaceBinding({
  threadId,
  disabled = false,
  threadReady,
  onPendingBind,
}: {
  threadId: string;
  disabled?: boolean;
  /**
   * Whether the backend thread exists yet. In a brand-new conversation the
   * thread id is a client-side placeholder until the first message creates it
   * (issue #2746), so the binding can only be staged and applied on creation.
   */
  threadReady: boolean;
  /** Receives a staged binding while `threadReady` is false; the page applies
   * it to the real thread once the backend creates it. */
  onPendingBind?: (binding: WorkspaceFolderBinding | null) => void;
}) {
  const { t } = useI18n();
  const { binding, bind, unbind } = useThreadWorkspaceBinding(threadId);
  const [open, setOpen] = useState(false);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(
    null,
  );
  // While the thread doesn't exist yet, show the chosen folder on the trigger
  // even though it is not persisted; clear it once the thread is created and
  // the real binding (from thread metadata) takes over.
  const [pendingSelection, setPendingSelection] =
    useState<WorkspaceFolderBinding | null>(null);

  const effectiveBinding = binding ?? pendingSelection;

  useEffect(() => {
    if (threadReady) {
      setPendingSelection(null);
    }
  }, [threadReady]);

  const { data: workspaces, isLoading: spacesLoading } = useWorkspaces();
  const pickWorkspaceId =
    selectedWorkspaceId ?? effectiveBinding?.workspaceId ?? null;
  const { data: detail, isLoading: detailLoading } =
    useWorkspaceDetail(pickWorkspaceId);
  const folders = detail?.folders ?? [];

  const closeMenu = () => {
    setOpen(false);
    setSelectedWorkspaceId(null);
  };

  const handleBind = (folderId: string, folderName: string) => {
    const workspace = workspaces?.find((ws) => ws.id === pickWorkspaceId);
    if (!workspace) {
      return;
    }
    const next: WorkspaceFolderBinding = {
      workspaceId: workspace.id,
      folderId,
      workspaceName: workspace.name,
      folderName,
    };
    if (!threadReady) {
      // The thread doesn't exist yet; stage the choice and let the page apply
      // it once the first message creates the thread.
      setPendingSelection(next);
      onPendingBind?.(next);
      toast.success(t.threadWorkspace.boundOnCreate);
      closeMenu();
      return;
    }
    bind
      .mutateAsync(next)
      .then(() => {
        toast.success(t.threadWorkspace.boundTo(workspace.name, folderName));
        closeMenu();
      })
      .catch((error) => {
        toast.error(
          error instanceof Error ? error.message : t.userWorkspace.updateFailed,
        );
      });
  };

  const handleUnbind = () => {
    if (!threadReady) {
      setPendingSelection(null);
      onPendingBind?.(null);
      closeMenu();
      return;
    }
    unbind
      .mutateAsync()
      .then(() => {
        toast.success(t.threadWorkspace.unbind);
        closeMenu();
      })
      .catch((error) => {
        toast.error(
          error instanceof Error ? error.message : t.userWorkspace.updateFailed,
        );
      });
  };

  const label = effectiveBinding
    ? t.threadWorkspace.boundTo(
        effectiveBinding.workspaceName,
        effectiveBinding.folderName,
      )
    : t.threadWorkspace.bind;

  return (
    <PromptInputActionMenu open={open} onOpenChange={setOpen}>
      <PromptInputActionMenuTrigger
        aria-label={label}
        className={cn(
          "gap-1! px-2!",
          effectiveBinding &&
            "bg-accent text-accent-foreground hover:bg-accent/80",
        )}
        data-testid="thread-workspace-binding-trigger"
        disabled={disabled || bind.isPending || unbind.isPending}
      >
        {effectiveBinding ? (
          <FolderIcon className="size-3" />
        ) : (
          <FolderPlusIcon className="size-3" />
        )}
        {effectiveBinding && (
          <span className="max-w-24 truncate text-xs font-normal">
            {effectiveBinding.folderName}
          </span>
        )}
      </PromptInputActionMenuTrigger>

      <PromptInputActionMenuContent className="w-80">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-muted-foreground text-xs">
            {t.threadWorkspace.selectWorkspaceFolder}
          </DropdownMenuLabel>

          {spacesLoading ? (
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
          ) : pickWorkspaceId ? (
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
                    className={cn(
                      binding?.folderId === folder.id
                        ? "text-accent-foreground"
                        : "text-muted-foreground/65",
                    )}
                    disabled={bind.isPending}
                    onSelect={() => handleBind(folder.id, folder.name)}
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
          ) : (
            workspaces.map((ws) => (
              <PromptInputActionMenuItem
                key={ws.id}
                className={cn(
                  ws.id === binding?.workspaceId
                    ? "text-accent-foreground"
                    : "text-muted-foreground/65",
                )}
                onSelect={(e) => {
                  e.preventDefault();
                  setSelectedWorkspaceId(ws.id);
                }}
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-1 font-bold">
                    <LibraryIcon
                      className={cn(
                        "mr-2 size-4",
                        ws.id === binding?.workspaceId &&
                          "text-accent-foreground",
                      )}
                    />
                    <span className="truncate">{ws.name}</span>
                  </div>
                  <div className="pl-7 text-xs">
                    {t.threadWorkspace.selectFolder}
                  </div>
                </div>
                {ws.id === binding?.workspaceId ? (
                  <CheckIcon className="ml-auto size-4" />
                ) : (
                  <div className="ml-auto size-4" />
                )}
              </PromptInputActionMenuItem>
            ))
          )}

          {binding && (
            <>
              <DropdownMenuSeparator />
              <PromptInputActionMenuItem
                className="text-destructive"
                disabled={unbind.isPending}
                onSelect={handleUnbind}
              >
                {unbind.isPending ? (
                  <LoaderCircleIcon className="mr-2 size-4 animate-spin" />
                ) : (
                  <UnlinkIcon className="mr-2 size-4" />
                )}
                {t.threadWorkspace.unbind}
              </PromptInputActionMenuItem>
            </>
          )}
        </DropdownMenuGroup>
      </PromptInputActionMenuContent>
    </PromptInputActionMenu>
  );
}
