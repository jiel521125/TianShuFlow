"use client";

import {
  ArrowLeftIcon,
  EyeIcon,
  FilePlusIcon,
  FileTextIcon,
  FolderIcon,
  FolderPlusIcon,
  LibraryIcon,
  LoaderCircleIcon,
  PencilIcon,
  PlusIcon,
  SaveIcon,
  Trash2Icon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item";
import { Textarea } from "@/components/ui/textarea";
import { MarkdownContent } from "@/components/workspace/messages/markdown-content";
import { useI18n } from "@/core/i18n/hooks";
import {
  useCreateFile,
  useCreateFolder,
  useCreateWorkspace,
  useDeleteFile,
  useDeleteFolder,
  useDeleteWorkspace,
  useFileDetail,
  useFiles,
  useUpdateFile,
  useUpdateFolder,
  useUpdateWorkspace,
  useWorkspaceDetail,
  useWorkspaces,
} from "@/core/workspace/hooks";
import type { WorkspaceFile, WorkspaceFolder, UserWorkspace } from "@/core/workspace/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Shared dialogs
// ---------------------------------------------------------------------------

function CreateNameDialog({
  open,
  onOpenChange,
  title,
  descriptionText,
  nameLabel,
  namePlaceholder,
  showDescription = false,
  defaultName = "",
  submitLabel,
  submitting,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  descriptionText?: string;
  nameLabel: string;
  namePlaceholder: string;
  showDescription?: boolean;
  defaultName?: string;
  submitLabel: string;
  submitting: boolean;
  onSubmit: (name: string, description?: string) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (open) {
      setName(defaultName);
      setDescription("");
    }
  }, [open, defaultName]);

  const canSubmit = name.trim().length > 0 && !submitting;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {descriptionText ? <DialogDescription>{descriptionText}</DialogDescription> : null}
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{nameLabel}</label>
            <Input
              value={name}
              placeholder={namePlaceholder}
              autoFocus
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && canSubmit) {
                  onSubmit(name.trim(), showDescription ? description.trim() : undefined);
                }
              }}
            />
          </div>
          {showDescription ? (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t.userWorkspace.descriptionLabel}</label>
              <Input
                value={description}
                placeholder={t.userWorkspace.descriptionPlaceholder}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {t.common.cancel}
          </Button>
          <Button
            type="button"
            disabled={!canSubmit}
            onClick={() => onSubmit(name.trim(), showDescription ? description.trim() : undefined)}
          >
            {submitting ? <LoaderCircleIcon className="animate-spin" /> : null}
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type DeleteTarget = {
  kind: "workspace" | "folder" | "file";
  id: string;
  workspaceId?: string;
  folderId?: string;
  name?: string;
};

function ConfirmDeleteDialog({
  target,
  onClose,
}: {
  target: DeleteTarget;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const deleteWorkspace = useDeleteWorkspace();
  const deleteFolder = useDeleteFolder();
  const deleteFile = useDeleteFile();

  const isPending =
    deleteWorkspace.isPending || deleteFolder.isPending || deleteFile.isPending;

  const message =
    target.kind === "workspace"
      ? t.userWorkspace.deleteWorkspaceConfirm
      : target.kind === "folder"
        ? t.userWorkspace.deleteFolderConfirm
        : t.userWorkspace.deleteFileConfirm;

  const confirm = () => {
    if (target.kind === "workspace") {
      void deleteWorkspace
        .mutateAsync(target.id)
        .then(onClose)
        .catch((error) => {
          toast.error(error instanceof Error ? error.message : t.userWorkspace.deleteFailed);
        });
      return;
    }
    if (target.kind === "folder") {
      void deleteFolder
        .mutateAsync({ workspaceId: target.workspaceId!, folderId: target.id })
        .then(onClose)
        .catch((error) => {
          toast.error(error instanceof Error ? error.message : t.userWorkspace.deleteFailed);
        });
      return;
    }
    void deleteFile
      .mutateAsync({
        workspaceId: target.workspaceId!,
        folderId: target.folderId!,
        fileId: target.id,
      })
      .then(onClose)
      .catch((error) => {
        toast.error(error instanceof Error ? error.message : t.userWorkspace.deleteFailed);
      });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t.userWorkspace.delete}</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            {t.common.cancel}
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={isPending}
            onClick={confirm}
          >
            {isPending ? <LoaderCircleIcon className="animate-spin" /> : <Trash2Icon />}
            {t.userWorkspace.delete}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Space list view
// ---------------------------------------------------------------------------

function WorkspaceListView({
  onOpen,
  onDelete,
  onRename,
}: {
  onOpen: (id: string) => void;
  onDelete: (target: DeleteTarget) => void;
  onRename: (target: DeleteTarget) => void;
}) {
  const { t } = useI18n();
  const { data: workspaces, isLoading, error } = useWorkspaces();
  const createWorkspace = useCreateWorkspace();
  const [dialogOpen, setDialogOpen] = useState(false);

  if (isLoading) {
    return <div className="text-muted-foreground py-10 text-center text-sm">{t.common.loading}</div>;
  }
  if (error) {
    return <div className="text-destructive py-10 text-center text-sm">{t.userWorkspace.loadFailed}</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">{t.userWorkspace.title}</h2>
          <p className="text-muted-foreground text-sm">{t.settings.description}</p>
        </div>
        <Button type="button" onClick={() => setDialogOpen(true)}>
          <PlusIcon />
          {t.userWorkspace.newWorkspace}
        </Button>
      </div>

      {!workspaces || workspaces.length === 0 ? (
        <div className="border-muted text-muted-foreground rounded-lg border border-dashed px-4 py-12 text-center">
          <p className="font-medium">{t.userWorkspace.emptyTitle}</p>
          <p className="mx-auto mt-1 max-w-md text-sm">{t.userWorkspace.emptyDescription}</p>
          <Button type="button" className="mt-4" onClick={() => setDialogOpen(true)}>
            <PlusIcon />
            {t.userWorkspace.newWorkspace}
          </Button>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((ws) => (
            <button
              key={ws.id}
              type="button"
              onClick={() => onOpen(ws.id)}
              className="group border-border hover:border-primary/50 hover:bg-accent/50 flex flex-col gap-2 rounded-lg border bg-card p-4 text-left transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-md">
                    <LibraryIcon className="size-4" />
                  </span>
                  <span className="truncate font-medium">{ws.name}</span>
                </div>
                {ws.is_default ? (
                  <Badge variant="outline">{t.userWorkspace.defaultBadge}</Badge>
                ) : null}
              </div>
              {ws.description ? (
                <p className="text-muted-foreground line-clamp-2 text-xs">
                  {ws.description}
                </p>
              ) : null}
              <div className="mt-auto flex items-center justify-between pt-1">
                <span className="text-muted-foreground text-xs">
                  {ws.folder_count} · {t.userWorkspace.fileCount(ws.file_count)}
                </span>
                <span
                  className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100"
                  role="presentation"
                  onClick={(event) => event.stopPropagation()}
                >
                  <PencilIcon
                    className="text-muted-foreground size-3.5"
                    onClick={() =>
                      onRename({ kind: "workspace", id: ws.id, name: ws.name })
                    }
                  />
                  <Trash2Icon
                    className="text-muted-foreground size-3.5"
                    onClick={() => onDelete({ kind: "workspace", id: ws.id })}
                  />
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      <CreateNameDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={t.userWorkspace.newWorkspace}
        nameLabel={t.userWorkspace.nameLabel}
        namePlaceholder={t.userWorkspace.namePlaceholder}
        showDescription
        submitLabel={t.userWorkspace.newWorkspace}
        submitting={createWorkspace.isPending}
        onSubmit={(name, description) => {
          void createWorkspace
            .mutateAsync({ name, description })
            .then(() => setDialogOpen(false))
            .catch((error) => {
              toast.error(error instanceof Error ? error.message : t.userWorkspace.createFailed);
            });
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Folder list view (inside a workspace)
// ---------------------------------------------------------------------------

function WorkspaceDetailView({
  workspaceId,
  onBack,
  onOpenFolder,
  onDelete,
  onRename,
}: {
  workspaceId: string;
  onBack: () => void;
  onOpenFolder: (folderId: string) => void;
  onDelete: (target: DeleteTarget) => void;
  onRename: (target: DeleteTarget) => void;
}) {
  const { t } = useI18n();
  const { data, isLoading, error } = useWorkspaceDetail(workspaceId);
  const createFolder = useCreateFolder();
  const [dialogOpen, setDialogOpen] = useState(false);

  if (isLoading) {
    return <div className="text-muted-foreground py-10 text-center text-sm">{t.common.loading}</div>;
  }
  if (error || !data) {
    return <div className="text-destructive py-10 text-center text-sm">{t.userWorkspace.loadFailed}</div>;
  }

  const folders: WorkspaceFolder[] = data.folders;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeftIcon />
            {t.userWorkspace.back}
          </Button>
          <div>
            <h2 className="text-lg font-semibold">{data.workspace.name}</h2>
            <p className="text-muted-foreground text-sm">
              {t.userWorkspace.projects} · {t.userWorkspace.fileCount(data.workspace.file_count)}
            </p>
          </div>
        </div>
        <Button type="button" onClick={() => setDialogOpen(true)}>
          <FolderPlusIcon />
          {t.userWorkspace.newFolder}
        </Button>
      </div>

      {folders.length === 0 ? (
        <div className="border-muted text-muted-foreground rounded-lg border border-dashed px-4 py-12 text-center text-sm">
          {t.userWorkspace.emptyProjects}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {folders.map((folder) => (
            <button
              key={folder.id}
              type="button"
              onClick={() => onOpenFolder(folder.id)}
              className="group border-border hover:border-primary/50 hover:bg-accent/50 flex flex-col gap-2 rounded-lg border bg-card p-4 text-left transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="bg-muted flex size-8 shrink-0 items-center justify-center rounded-md">
                  <FolderIcon className="text-muted-foreground size-4" />
                </span>
                <span className="truncate font-medium">{folder.name}</span>
              </div>
              <div className="mt-auto flex items-center justify-between pt-1">
                <span className="text-muted-foreground text-xs">
                  {t.userWorkspace.fileCount(folder.file_count)}
                </span>
                <span
                  className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100"
                  role="presentation"
                  onClick={(event) => event.stopPropagation()}
                >
                  <PencilIcon
                    className="text-muted-foreground size-3.5"
                    onClick={() =>
                      onRename({
                        kind: "folder",
                        id: folder.id,
                        workspaceId,
                        name: folder.name,
                      })
                    }
                  />
                  <Trash2Icon
                    className="text-muted-foreground size-3.5"
                    onClick={() =>
                      onDelete({
                        kind: "folder",
                        id: folder.id,
                        workspaceId,
                      })
                    }
                  />
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      <CreateNameDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={t.userWorkspace.newFolder}
        nameLabel={t.userWorkspace.nameLabel}
        namePlaceholder={t.userWorkspace.namePlaceholder}
        submitLabel={t.userWorkspace.newFolder}
        submitting={createFolder.isPending}
        onSubmit={(name) => {
          void createFolder
            .mutateAsync({ workspaceId, name })
            .then(() => setDialogOpen(false))
            .catch((error) => {
              toast.error(error instanceof Error ? error.message : t.userWorkspace.createFailed);
            });
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// File list view (inside a folder)
// ---------------------------------------------------------------------------

function FolderFilesView({
  workspaceId,
  folderId,
  onBack,
  onOpenFile,
  onDelete,
}: {
  workspaceId: string;
  folderId: string;
  onBack: () => void;
  onOpenFile: (fileId: string) => void;
  onDelete: (target: DeleteTarget) => void;
}) {
  const { t } = useI18n();
  const { data: workspaceData } = useWorkspaceDetail(workspaceId);
  const { data: files, isLoading, error } = useFiles(workspaceId, folderId);
  const createFile = useCreateFile();
  const [dialogOpen, setDialogOpen] = useState(false);

  if (isLoading) {
    return <div className="text-muted-foreground py-10 text-center text-sm">{t.common.loading}</div>;
  }
  if (error) {
    return <div className="text-destructive py-10 text-center text-sm">{t.userWorkspace.loadFailed}</div>;
  }

  const folderName = workspaceData?.folders.find((f) => f.id === folderId)?.name;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeftIcon />
            {t.userWorkspace.back}
          </Button>
          <div>
            <h2 className="text-lg font-semibold">{folderName ?? t.userWorkspace.projects}</h2>
            <p className="text-muted-foreground text-sm">{t.userWorkspace.documents}</p>
          </div>
        </div>
        <Button type="button" onClick={() => setDialogOpen(true)}>
          <FilePlusIcon />
          {t.userWorkspace.newDocument}
        </Button>
      </div>

      {!files || files.length === 0 ? (
        <div className="border-muted text-muted-foreground rounded-lg border border-dashed px-4 py-12 text-center text-sm">
          {t.userWorkspace.emptyDocuments}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {files.map((file) => (
            <Item
              key={file.id}
              variant="outline"
              className="w-full items-start"
            >
              <ItemMedia variant="icon" className="bg-background">
                <FileTextIcon className="size-4" />
              </ItemMedia>
              <ItemContent className="min-w-0">
                <ItemTitle>
                  <span className="truncate">{file.name}</span>
                </ItemTitle>
                <ItemDescription className="line-clamp-none">
                  {new Date(file.updated_at ?? file.created_at ?? 0).toLocaleString()} ·{" "}
                  {file.size_bytes} B
                </ItemDescription>
              </ItemContent>
              <ItemActions className="ml-auto">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onOpenFile(file.id)}
                >
                  {t.userWorkspace.edit}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  onClick={() =>
                    onDelete({
                      kind: "file",
                      id: file.id,
                      workspaceId,
                      folderId,
                    })
                  }
                >
                  <Trash2Icon />
                </Button>
              </ItemActions>
            </Item>
          ))}
        </div>
      )}

      <CreateNameDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={t.userWorkspace.newDocument}
        nameLabel={t.userWorkspace.nameLabel}
        namePlaceholder={t.userWorkspace.documentNamePlaceholder}
        defaultName="untitled.md"
        submitLabel={t.userWorkspace.newDocument}
        submitting={createFile.isPending}
        onSubmit={(name) => {
          void createFile
            .mutateAsync({ workspaceId, folderId, name })
            .then(() => setDialogOpen(false))
            .catch((error) => {
              toast.error(error instanceof Error ? error.message : t.userWorkspace.createFailed);
            });
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Document editor (markdown)
// ---------------------------------------------------------------------------

function DocumentEditor({
  workspaceId,
  folderId,
  fileId,
  onBack,
  onRename,
  onDelete,
}: {
  workspaceId: string;
  folderId: string;
  fileId: string;
  onBack: () => void;
  onRename: (target: DeleteTarget) => void;
  onDelete: (target: DeleteTarget) => void;
}) {
  const { t } = useI18n();
  const { data: file, isLoading, error } = useFileDetail(workspaceId, folderId, fileId);
  const updateFile = useUpdateFile();
  const [draft, setDraft] = useState<string>("");
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (file && !hydrated) {
      setDraft(file.content ?? "");
      setHydrated(true);
    }
  }, [file, hydrated]);

  const dirty = file !== undefined && draft !== (file.content ?? "");

  if (isLoading) {
    return <div className="text-muted-foreground py-10 text-center text-sm">{t.common.loading}</div>;
  }
  if (error || !file) {
    return <div className="text-destructive py-10 text-center text-sm">{t.userWorkspace.loadFileFailed}</div>;
  }

  const save = () => {
    void updateFile
      .mutateAsync({ workspaceId, folderId, fileId, content: draft })
      .then(() => toast.success(t.userWorkspace.saved))
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : t.userWorkspace.saveFailed);
      });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeftIcon />
            {t.userWorkspace.back}
          </Button>
          <span className="truncate font-medium">{file.name}</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            title={t.userWorkspace.rename}
            onClick={() =>
              onRename({ kind: "file", id: fileId, workspaceId, folderId, name: file.name })
            }
          >
            <PencilIcon />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="text-destructive"
            onClick={() => onDelete({ kind: "file", id: fileId, workspaceId, folderId })}
          >
            <Trash2Icon />
          </Button>
          <Button type="button" size="sm" disabled={!dirty || updateFile.isPending} onClick={save}>
            {updateFile.isPending ? (
              <LoaderCircleIcon className="animate-spin" />
            ) : (
              <SaveIcon />
            )}
            {updateFile.isPending ? t.userWorkspace.saving : t.userWorkspace.save}
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-1 rounded-md bg-muted p-1">
        {(["write", "preview"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              mode === m ? "bg-background shadow-sm" : "text-muted-foreground",
            )}
          >
            {m === "write" ? <PencilIcon className="size-3.5" /> : <EyeIcon className="size-3.5" />}
            {m === "write" ? t.userWorkspace.write : t.userWorkspace.preview}
          </button>
        ))}
      </div>

      {mode === "write" ? (
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t.userWorkspace.emptyDocument}
          className="min-h-[50vh] w-full resize-y font-mono text-sm leading-relaxed"
        />
      ) : (
        <div className="rounded-lg border bg-card p-4">
          <MarkdownContent content={draft} isLoading={false} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root manager
// ---------------------------------------------------------------------------

export function WorkspaceManager() {
  const { t } = useI18n();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [fileId, setFileId] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<DeleteTarget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  const updateWorkspace = useUpdateWorkspace();
  const updateFolder = useUpdateFolder();
  const updateFile = useUpdateFile();

  const renameSubmitting =
    updateWorkspace.isPending || updateFolder.isPending || updateFile.isPending;

  const backToFolders = () => setFolderId(null);
  const backToFiles = () => setFileId(null);

  return (
    <div className="w-full">
      {fileId && folderId && workspaceId ? (
        <DocumentEditor
          workspaceId={workspaceId}
          folderId={folderId}
          fileId={fileId}
          onBack={backToFiles}
          onRename={setRenameTarget}
          onDelete={setDeleteTarget}
        />
      ) : folderId && workspaceId ? (
        <FolderFilesView
          workspaceId={workspaceId}
          folderId={folderId}
          onBack={backToFolders}
          onOpenFile={setFileId}
          onDelete={setDeleteTarget}
        />
      ) : workspaceId ? (
        <WorkspaceDetailView
          workspaceId={workspaceId}
          onBack={() => setWorkspaceId(null)}
          onOpenFolder={setFolderId}
          onDelete={setDeleteTarget}
          onRename={setRenameTarget}
        />
      ) : (
        <WorkspaceListView
          onOpen={setWorkspaceId}
          onDelete={setDeleteTarget}
          onRename={setRenameTarget}
        />
      )}

      {renameTarget ? (
        <CreateNameDialog
          open
          onOpenChange={(open) => !open && setRenameTarget(null)}
          title={t.userWorkspace.rename}
          nameLabel={t.userWorkspace.nameLabel}
          namePlaceholder={t.userWorkspace.namePlaceholder}
          defaultName={renameTarget.name ?? (renameTarget.kind === "file" ? "untitled.md" : "")}
          submitLabel={t.userWorkspace.rename}
          submitting={renameSubmitting}
          onSubmit={(name) => {
            if (renameTarget.kind === "workspace") {
              void updateWorkspace
                .mutateAsync({ id: renameTarget.id, name })
                .then(() => setRenameTarget(null))
                .catch((error) => {
                  toast.error(error instanceof Error ? error.message : t.userWorkspace.updateFailed);
                });
              return;
            }
            if (renameTarget.kind === "folder") {
              void updateFolder
                .mutateAsync({
                  workspaceId: renameTarget.workspaceId!,
                  folderId: renameTarget.id,
                  name,
                })
                .then(() => setRenameTarget(null))
                .catch((error) => {
                  toast.error(error instanceof Error ? error.message : t.userWorkspace.updateFailed);
                });
              return;
            }
            void updateFile
              .mutateAsync({
                workspaceId: renameTarget.workspaceId!,
                folderId: renameTarget.folderId!,
                fileId: renameTarget.id,
                name,
              })
              .then(() => setRenameTarget(null))
              .catch((error) => {
                toast.error(error instanceof Error ? error.message : t.userWorkspace.updateFailed);
              });
          }}
        />
      ) : null}

      {deleteTarget ? (
        <ConfirmDeleteDialog
          target={deleteTarget}
          onClose={() => {
            setDeleteTarget(null);
            if (deleteTarget.kind === "workspace") {
              setWorkspaceId(null);
            } else if (deleteTarget.kind === "folder") {
              setFolderId(null);
            } else if (deleteTarget.kind === "file") {
              setFileId(null);
            }
          }}
        />
      ) : null}
    </div>
  );
}

export type { DeleteTarget, UserWorkspace, WorkspaceFile, WorkspaceFolder };
