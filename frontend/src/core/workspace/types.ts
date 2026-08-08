/** Types for the per-user workspace (personal space) module. */

export interface UserWorkspace {
  id: string;
  name: string;
  description: string | null;
  is_default: boolean;
  folder_count: number;
  file_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface WorkspaceFolder {
  id: string;
  workspace_id: string;
  name: string;
  sort_order: number;
  file_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export type FileStorageStatus = "embedded" | "cloud";

export interface WorkspaceFile {
  id: string;
  folder_id: string;
  workspace_id: string;
  name: string;
  extension: string | null;
  mime_type: string | null;
  size_bytes: number;
  storage_status: FileStorageStatus;
  content_ref: string | null;
  /** Present only in the detail payload. */
  content?: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface WorkspaceListResponse {
  workspaces: UserWorkspace[];
  count: number;
}

export interface WorkspaceDetailResponse {
  workspace: UserWorkspace;
  folders: WorkspaceFolder[];
}

export interface FolderResponse {
  folder: WorkspaceFolder;
}

export interface FileResponse {
  file: WorkspaceFile;
}

export interface FileListResponse {
  files: WorkspaceFile[];
  count: number;
}
