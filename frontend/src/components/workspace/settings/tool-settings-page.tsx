"use client";

import { PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/core/i18n/hooks";
import {
  useCreateUserMCPServer,
  useDeleteUserMCPServer,
  useUpdateUserMCPServer,
  useUserMCPServers,
} from "@/core/user-mcp/hooks";
import type {
  UserMCPServer,
  UserMCPServerCreatePayload,
  UserMCPServerUpdatePayload,
} from "@/core/user-mcp/api";
import {
  useResetUserSettings,
  useUpdateUserSettings,
  useUserSettings,
} from "@/core/user-settings/hooks";
import { cn } from "@/lib/utils";

import { SettingsSection } from "./settings-section";
import {
  UserMCPServerDialog,
  type UserMCPServerDialogMode,
} from "./user-mcp-server-dialog";
import { UserPrefsCard } from "./user-prefs-card";

const TRANSPORT_BADGE: Record<string, string> = {
  stdio: "stdio",
  sse: "sse",
  http: "http",
};

/**
 * Settings → Tools: the signed-in user's OWN MCP server registry.
 *
 * The server list is per-user (``/api/user/mcp``); there is no admin-only
 * global section here, and the "inherit" toggle refers to the user's own full
 * server set -- system-global ``extensions_config.json`` servers never leak
 * into a user session.
 */
export function ToolSettingsPage() {
  const { t } = useI18n();
  const { servers, isLoading, error } = useUserMCPServers();
  const createServer = useCreateUserMCPServer();
  const updateServer = useUpdateUserMCPServer();
  const deleteServer = useDeleteUserMCPServer();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<UserMCPServerDialogMode>("create");
  const [editing, setEditing] = useState<UserMCPServer | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);

  // Per-user preference layer ("千人千面"): "inherit" means all of the
  // user's own registered servers; switching it off activates the per-server
  // allowlist below.
  const {
    settings,
    isLoading: prefsLoading,
    error: prefsError,
  } = useUserSettings();
  const updatePrefs = useUpdateUserSettings();
  const resetPrefs = useResetUserSettings();
  const inheritGlobal = settings?.tools.inherit_global ?? true;
  const enabledServers = settings?.tools.enabled_servers ?? [];
  const prefsSaving = updatePrefs.isPending || resetPrefs.isPending;

  const serverNames = servers.map((server) => server.name);
  const hasServers = serverNames.length > 0;
  const prefsItems = servers.map((server) => ({
    id: server.name,
    label: server.display_name || server.name,
    description: server.description ?? undefined,
  }));
  const submitting =
    createServer.isPending || updateServer.isPending || deleteServer.isPending;

  const handleInheritChange = (inherit: boolean) => {
    const value = inherit
      ? { inherit_global: inherit }
      : {
          inherit_global: inherit,
          enabled_servers:
            enabledServers.length > 0 ? enabledServers : serverNames,
        };
    updatePrefs.mutate(
      { section: "tools", value },
      {
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : t.settings.userPrefs.saveFailed,
          ),
      },
    );
  };

  const handleToggle = (id: string, checked: boolean) => {
    const next = checked
      ? [...enabledServers, id]
      : enabledServers.filter((item) => item !== id);
    updatePrefs.mutate(
      { section: "tools", value: { enabled_servers: next } },
      {
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : t.settings.userPrefs.saveFailed,
          ),
      },
    );
  };

  const handleReset = () => {
    resetPrefs.mutate("tools", {
      onSuccess: () => toast.success(t.settings.userPrefs.resetSuccess),
      onError: (err) =>
        toast.error(
          err instanceof Error ? err.message : t.settings.userPrefs.resetFailed,
        ),
    });
  };

  const openCreate = () => {
    setDialogMode("create");
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (server: UserMCPServer) => {
    setDialogMode("edit");
    setEditing(server);
    setDialogOpen(true);
  };

  const handleSave = (
    name: string,
    payload: UserMCPServerCreatePayload | UserMCPServerUpdatePayload,
  ) => {
    if (dialogMode === "create") {
      createServer.mutate(payload as UserMCPServerCreatePayload, {
        onSuccess: () => {
          setDialogOpen(false);
          toast.success(t.settings.tools.addServerTitle);
        },
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : t.settings.tools.saveFailed,
          ),
      });
      return;
    }
    updateServer.mutate(
      { name, payload: payload as UserMCPServerUpdatePayload },
      {
        onSuccess: () => {
          setDialogOpen(false);
          toast.success(t.settings.tools.editServerTitle);
        },
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : t.settings.tools.saveFailed,
          ),
      },
    );
  };

  const handleDeleteServer = (name: string) => {
    setConfirmingDelete(null);
    deleteServer.mutate(name, {
      onSuccess: () => toast.success(t.settings.tools.deleteSuccess),
      onError: (err) =>
        toast.error(
          err instanceof Error ? err.message : t.settings.tools.deleteFailed,
        ),
    });
  };

  return (
    <SettingsSection
      title={
        <div className="flex items-center justify-between gap-2">
          <span>{t.settings.tools.title}</span>
          {!isLoading ? (
            <Button size="sm" onClick={openCreate}>
              <PlusIcon />
              {t.settings.tools.addServer}
            </Button>
          ) : null}
        </div>
      }
      description={t.settings.tools.description}
    >
      {/* The per-user preference card only makes sense when the user has
          registered at least one MCP server; hide it otherwise so it never
          sits in the middle of an empty page. */}
      {prefsError ? (
        <div className="text-destructive text-sm">
          {t.settings.userPrefs.loadFailed}
        </div>
      ) : hasServers ? (
        <UserPrefsCard
          items={prefsItems}
          inheritGlobal={inheritGlobal}
          enabled={enabledServers}
          onInheritChange={handleInheritChange}
          onToggle={handleToggle}
          onReset={handleReset}
          pending={prefsSaving || prefsLoading}
        />
      ) : null}
      {isLoading ? (
        <div className="text-muted-foreground text-sm">{t.common.loading}</div>
      ) : error ? (
        <div>Error: {error.message}</div>
      ) : (
        <UserMCPServerList
          servers={servers}
          confirmingDelete={confirmingDelete}
          deleting={deleteServer.isPending}
          onConfirmDelete={setConfirmingDelete}
          onDelete={handleDeleteServer}
          onEdit={openEdit}
        />
      )}
      <UserMCPServerDialog
        open={dialogOpen}
        submitting={submitting}
        mode={dialogMode}
        existingNames={serverNames}
        initial={editing}
        onOpenChange={setDialogOpen}
        onSave={handleSave}
      />
    </SettingsSection>
  );
}

function UserMCPServerList({
  servers,
  confirmingDelete,
  deleting,
  onConfirmDelete,
  onDelete,
  onEdit,
}: {
  servers: UserMCPServer[];
  confirmingDelete: string | null;
  deleting: boolean;
  onConfirmDelete: (name: string | null) => void;
  onDelete: (name: string) => void;
  onEdit: (server: UserMCPServer) => void;
}) {
  const { t } = useI18n();
  if (servers.length === 0) {
    return (
      <div className="text-muted-foreground text-sm">
        {t.settings.tools.empty}
      </div>
    );
  }
  return (
    <div className="flex w-full flex-col gap-4">
      {servers.map((server) => {
        const isConfirming = confirmingDelete === server.name;
        const label = server.display_name || server.name;
        return (
          <Item className="w-full" variant="outline" key={server.name}>
            <ItemContent>
              <ItemTitle>
                <div className="flex items-center gap-2">
                  <div>{label}</div>
                  <Badge
                    variant="outline"
                    className={cn(
                      "rounded-full px-2 py-0 text-[10px] font-normal",
                    )}
                  >
                    {TRANSPORT_BADGE[server.transport] ?? server.transport}
                  </Badge>
                </div>
              </ItemTitle>
              <ItemDescription className="line-clamp-4">
                {server.description}
              </ItemDescription>
            </ItemContent>
            <ItemActions>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={deleting}
                title={t.common.edit}
                onClick={() => onEdit(server)}
              >
                <PencilIcon />
              </Button>
              {isConfirming ? (
                <>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    disabled={deleting}
                    onClick={() => onDelete(server.name)}
                  >
                    {t.common.confirm}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={deleting}
                    onClick={() => onConfirmDelete(null)}
                  >
                    {t.common.cancel}
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={deleting}
                  title={t.settings.tools.deleteServer}
                  onClick={() => onConfirmDelete(server.name)}
                >
                  <Trash2Icon />
                </Button>
              )}
            </ItemActions>
          </Item>
        );
      })}
    </div>
  );
}
