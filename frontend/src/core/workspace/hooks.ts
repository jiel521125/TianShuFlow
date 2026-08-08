import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  createFile,
  createFolder,
  createWorkspace,
  deleteFile,
  deleteFolder,
  deleteWorkspace,
  listFiles,
  loadFile,
  loadWorkspaceDetail,
  loadWorkspaces,
  updateFile,
  updateFolder,
  updateWorkspace,
} from "./api";
import type {
  UserWorkspace,
  WorkspaceFile,
  WorkspaceFolder,
} from "./types";

const WORKSPACES_KEY = ["workspaces"] as const;

function detailKey(workspaceId: string) {
  return ["workspaces", workspaceId] as const;
}

function filesKey(workspaceId: string, folderId: string) {
  return ["workspaces", workspaceId, "folders", folderId, "files"] as const;
}

function fileKey(workspaceId: string, folderId: string, fileId: string) {
  return [...filesKey(workspaceId, folderId), fileId] as const;
}

// --------------------------------------------------------------------------
// Queries
// --------------------------------------------------------------------------

export function useWorkspaces() {
  return useQuery({
    queryKey: WORKSPACES_KEY,
    queryFn: async () => {
      const res = await loadWorkspaces();
      return res.workspaces;
    },
  });
}

export function useWorkspaceDetail(workspaceId: string | null) {
  return useQuery({
    queryKey: detailKey(workspaceId ?? "none"),
    queryFn: async () => {
      const res = await loadWorkspaceDetail(workspaceId!);
      return res;
    },
    enabled: Boolean(workspaceId),
  });
}

export function useFiles(workspaceId: string | null, folderId: string | null) {
  return useQuery({
    queryKey: filesKey(workspaceId ?? "none", folderId ?? "none"),
    queryFn: async () => {
      const res = await listFiles(workspaceId!, folderId!);
      return res.files;
    },
    enabled: Boolean(workspaceId && folderId),
  });
}

export function useFileDetail(
  workspaceId: string | null,
  folderId: string | null,
  fileId: string | null,
) {
  return useQuery({
    queryKey: fileKey(workspaceId ?? "none", folderId ?? "none", fileId ?? "none"),
    queryFn: async () => {
      const res = await loadFile(workspaceId!, folderId!, fileId!);
      return res.file;
    },
    enabled: Boolean(workspaceId && folderId && fileId),
  });
}

// --------------------------------------------------------------------------
// Mutations
// --------------------------------------------------------------------------

export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createWorkspace,
    onSuccess: () => void qc.invalidateQueries({ queryKey: WORKSPACES_KEY }),
  });
}

export function useUpdateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: { id: string; name?: string; description?: string | null }) =>
      updateWorkspace(id, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: WORKSPACES_KEY });
      void qc.invalidateQueries({ queryKey: detailKey(vars.id) });
    },
  });
}

export function useDeleteWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteWorkspace,
    onSuccess: () => void qc.invalidateQueries({ queryKey: WORKSPACES_KEY }),
  });
}

export function useCreateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ workspaceId, name }: { workspaceId: string; name: string }) =>
      createFolder(workspaceId, { name }),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: WORKSPACES_KEY });
      void qc.invalidateQueries({ queryKey: detailKey(vars.workspaceId) });
    },
  });
}

export function useUpdateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      workspaceId,
      folderId,
      ...body
    }: {
      workspaceId: string;
      folderId: string;
      name?: string;
      sort_order?: number;
    }) => updateFolder(workspaceId, folderId, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: detailKey(vars.workspaceId) });
    },
  });
}

export function useDeleteFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ workspaceId, folderId }: { workspaceId: string; folderId: string }) =>
      deleteFolder(workspaceId, folderId),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: WORKSPACES_KEY });
      void qc.invalidateQueries({ queryKey: detailKey(vars.workspaceId) });
    },
  });
}

export function useCreateFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      workspaceId,
      folderId,
      ...body
    }: {
      workspaceId: string;
      folderId: string;
      name: string;
      content?: string;
    }) => createFile(workspaceId, folderId, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: filesKey(vars.workspaceId, vars.folderId) });
      void qc.invalidateQueries({ queryKey: detailKey(vars.workspaceId) });
      void qc.invalidateQueries({ queryKey: WORKSPACES_KEY });
    },
  });
}

export function useUpdateFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      workspaceId,
      folderId,
      fileId,
      ...body
    }: {
      workspaceId: string;
      folderId: string;
      fileId: string;
      name?: string;
      content?: string;
    }) => updateFile(workspaceId, folderId, fileId, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({
        queryKey: fileKey(vars.workspaceId, vars.folderId, vars.fileId),
      });
      void qc.invalidateQueries({
        queryKey: filesKey(vars.workspaceId, vars.folderId),
      });
      void qc.invalidateQueries({ queryKey: detailKey(vars.workspaceId) });
      void qc.invalidateQueries({ queryKey: WORKSPACES_KEY });
    },
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      workspaceId,
      folderId,
      fileId,
    }: {
      workspaceId: string;
      folderId: string;
      fileId: string;
    }) => deleteFile(workspaceId, folderId, fileId),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({
        queryKey: filesKey(vars.workspaceId, vars.folderId),
      });
      void qc.invalidateQueries({ queryKey: detailKey(vars.workspaceId) });
      void qc.invalidateQueries({ queryKey: WORKSPACES_KEY });
    },
  });
}

export type { UserWorkspace, WorkspaceFile, WorkspaceFolder };
