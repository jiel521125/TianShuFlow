"use client";

import type { Message } from "@langchain/langgraph-sdk";
import {
  FileTextIcon,
  FolderOpenIcon,
  LoaderCircleIcon,
  XIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n } from "@/core/i18n/hooks";
import { loadArtifactContent } from "@/core/artifacts/loader";
import { useThreadWorkspaceBinding } from "@/core/threads/hooks";
import type { WorkspaceFolderBinding } from "@/core/threads/utils";
import { createFile, loadFile } from "@/core/workspace/api";
import {
  useFiles,
  type WorkspaceFile,
} from "@/core/workspace/hooks";
import { cn } from "@/lib/utils";

export type LoadedWorkspaceDoc = {
  id: string;
  name: string;
  content: string;
};

function escapeXmlAttribute(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/**
 * Builds a hidden human message carrying the loaded workspace document bodies.
 * Injected as an additional input message so the documents act as reference
 * context for the user's next message without cluttering the visible history
 * (same pattern as sidecar conversation quotes).
 */
export function buildWorkspaceDocumentsHiddenMessage(
  docs: LoadedWorkspaceDoc[],
): Message {
  return {
    type: "human",
    content: [
      {
        type: "text",
        text: [
          docs.length === 1
            ? "The user loaded the following workspace document into this conversation."
            : `The user loaded the following ${docs.length} workspace documents into this conversation.`,
          "Use the <workspace_document> blocks as reference material for the user's next message.",
          "",
          ...docs.flatMap((doc, index) => [
            `<workspace_document index="${index + 1}" name="${escapeXmlAttribute(
              doc.name,
            )}">`,
            doc.content,
            "</workspace_document>",
            "",
          ]),
        ].join("\n"),
      },
    ],
    additional_kwargs: {
      hide_from_ui: true,
      workspace_documents: true,
      loaded_workspace_document_count: docs.length,
    },
  } as Message;
}

/**
 * Builds a hidden human message that declares the conversation's bound
 * workspace folder. Attached to every submitted message (in addition to any
 * user-loaded document bodies) so the agent always knows which folder "this
 * folder" refers to and that produced documents are archived back into it.
 */
export function buildWorkspaceBindingContextMessage(
  binding: WorkspaceFolderBinding,
  fileNames: string[],
): Message {
  const fileList = fileNames.length
    ? [
        "The bound folder currently contains these documents:",
        "",
        ...fileNames.map((name) => `- ${name}`),
        "",
        "You can ask the user to load the full content of any of these documents as reference.",
      ]
    : ["The bound folder currently contains no documents."];
  return {
    type: "human",
    content: [
      {
        type: "text",
        text: [
          "This conversation is bound to a workspace folder.",
          `- Workspace: ${binding.workspaceName}`,
          `- Folder: ${binding.folderName}`,
          'When the user says "this folder", they mean the folder above.',
          "Documents you produce for the user will be automatically archived into this folder after your reply.",
          "",
          ...fileList,
        ].join("\n"),
      },
    ],
    additional_kwargs: {
      hide_from_ui: true,
      workspace_binding: true,
    },
  } as Message;
}

// Text-like artifact extensions that are safe to archive into the user's
// workspace folder. Binary artifacts (images, archives, ...) are skipped.
const ARCHIVE_TEXT_EXTENSIONS = new Set([
  "md",
  "markdown",
  "txt",
  "html",
  "htm",
  "css",
  "js",
  "mjs",
  "cjs",
  "ts",
  "tsx",
  "jsx",
  "json",
  "csv",
  "tsv",
  "yaml",
  "yml",
  "xml",
  "svg",
  "py",
  "sh",
  "bash",
  "sql",
  "log",
  "ini",
  "conf",
  "toml",
  "env",
]);

export function isArchiveableArtifact(filepath: string): boolean {
  const name = filepath.split("/").pop() ?? filepath;
  if (!name || name.startsWith(".")) {
    return false;
  }
  const dot = name.lastIndexOf(".");
  if (dot <= 0) {
    return false;
  }
  return ARCHIVE_TEXT_EXTENSIONS.has(name.slice(dot + 1).toLowerCase());
}

/**
 * Archives conversation artifacts into the bound workspace folder.
 * Skips artifacts that already exist in the folder (case-insensitive name
 * match) and non-text files. Returns the names of successfully archived
 * documents. Any per-file failure is swallowed so one bad file never blocks
 * the rest.
 */
export async function archiveArtifactsToFolder({
  threadId,
  artifactPaths,
  binding,
  existingNames,
  isMock = false,
}: {
  threadId: string;
  artifactPaths: readonly string[];
  binding: WorkspaceFolderBinding;
  existingNames: readonly string[];
  isMock?: boolean;
}): Promise<string[]> {
  const existing = new Set(existingNames.map((name) => name.toLowerCase()));
  const archived: string[] = [];
  for (const filepath of artifactPaths) {
    if (!isArchiveableArtifact(filepath)) {
      continue;
    }
    const name = filepath.split("/").pop() ?? filepath;
    if (existing.has(name.toLowerCase())) {
      continue;
    }
    try {
      const { content } = await loadArtifactContent({
        filepath,
        threadId,
        isMock,
        full: true,
      });
      await createFile(binding.workspaceId, binding.folderId, {
        name,
        content,
      });
      existing.add(name.toLowerCase());
      archived.push(name);
    } catch {
      // Skip files that fail to load or that race another archived copy.
    }
  }
  return archived;
}

function WorkspaceDocumentPickerDialog({
  open,
  onOpenChange,
  threadId,
  onLoad,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  threadId: string;
  onLoad: (docs: LoadedWorkspaceDoc[]) => void;
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  // Read the binding inside the dialog so the list refreshes whenever the
  // conversation's folder binding changes.
  const { binding } = useThreadWorkspaceBinding(threadId);
  const { data: files, isLoading: filesLoading } = useFiles(
    binding?.workspaceId ?? null,
    binding?.folderId ?? null,
  );

  const toggle = (fileId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(fileId)) {
        next.delete(fileId);
      } else {
        next.add(fileId);
      }
      return next;
    });
  };

  const handleLoad = async () => {
    if (!binding || selected.size === 0) {
      return;
    }
    setLoading(true);
    try {
      const docs: LoadedWorkspaceDoc[] = [];
      for (const file of files ?? []) {
        if (!selected.has(file.id)) {
          continue;
        }
        const res = await loadFile(
          binding.workspaceId,
          binding.folderId,
          file.id,
        );
        docs.push({
          id: file.id,
          name: file.name,
          content: res.file.content ?? "",
        });
      }
      onLoad(docs);
      setSelected(new Set());
      onOpenChange(false);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t.threadWorkspace.loadFailed,
      );
    } finally {
      setLoading(false);
    }
  };

  const availableFiles: WorkspaceFile[] = files ?? [];

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onOpenChange(false)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t.threadWorkspace.loadDocuments}</DialogTitle>
          <DialogDescription>
            {t.threadWorkspace.documentContextHint}
          </DialogDescription>
        </DialogHeader>

        {filesLoading ? (
          <div className="text-muted-foreground flex items-center justify-center gap-2 py-8 text-sm">
            <LoaderCircleIcon className="size-4 animate-spin" />
            {t.common.loading}
          </div>
        ) : availableFiles.length === 0 ? (
          <p className="text-muted-foreground rounded-md border border-dashed px-3 py-8 text-center text-sm">
            {t.threadWorkspace.emptyDocuments}
          </p>
        ) : (
          <ScrollArea className="max-h-72">
            <div className="space-y-1">
              {availableFiles.map((file) => {
                const isSelected = selected.has(file.id);
                return (
                  <button
                    key={file.id}
                    type="button"
                    onClick={() => toggle(file.id)}
                    className={cn(
                      "hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                      isSelected
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    <FileTextIcon className="size-3.5 shrink-0" />
                    <span className="truncate">{file.name}</span>
                  </button>
                );
              })}
            </div>
          </ScrollArea>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setSelected(new Set());
              onOpenChange(false);
            }}
            disabled={loading}
          >
            {t.common.cancel}
          </Button>
          <Button
            type="button"
            disabled={loading || selected.size === 0}
            onClick={() => void handleLoad()}
          >
            {loading ? <LoaderCircleIcon className="animate-spin" /> : null}
            {t.threadWorkspace.load}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Rendered inside the composer header when the conversation is bound to a
 * workspace folder. Shows already-loaded documents as removable chips and a
 * button to pick more documents from the bound folder.
 */
export function WorkspaceDocumentsSummary({
  threadId,
  docs,
  onDocsChange,
}: {
  threadId: string;
  docs: LoadedWorkspaceDoc[];
  onDocsChange: (docs: LoadedWorkspaceDoc[]) => void;
}) {
  const { t } = useI18n();
  const [pickerOpen, setPickerOpen] = useState(false);

  return (
    <>
      {docs.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {docs.map((doc) => (
            <span
              key={doc.id}
              className="bg-muted text-muted-foreground flex h-7 max-w-52 items-center gap-1.5 rounded-full py-0 pr-1 pl-2.5 text-xs font-medium"
            >
              <FileTextIcon className="size-3 shrink-0" />
              <span className="truncate">{doc.name}</span>
              <button
                type="button"
                aria-label={t.threadWorkspace.remove}
                className="hover:bg-muted-foreground/20 focus-visible:ring-primary/40 flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors focus-visible:ring-2 focus-visible:outline-none"
                onClick={() =>
                  onDocsChange(docs.filter((item) => item.id !== doc.id))
                }
              >
                <XIcon className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-1.5">
        <Button
          type="button"
          variant="outline"
          size="sm"
          data-testid="workspace-documents-load-trigger"
          onClick={() => setPickerOpen(true)}
        >
          <FolderOpenIcon className="size-3.5" />
          {t.threadWorkspace.loadDocuments}
        </Button>
        {docs.length > 0 && (
          <span className="text-muted-foreground text-xs">
            {t.threadWorkspace.loadedCount(docs.length)}
          </span>
        )}
      </div>

      <WorkspaceDocumentPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        threadId={threadId}
        onLoad={(loaded) => {
          onDocsChange(loaded);
          toast.success(t.threadWorkspace.loadedCount(loaded.length));
        }}
      />
    </>
  );
}
