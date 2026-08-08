"use client";

import { LoaderCircleIcon, WrenchIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
} from "@/components/ai-elements/prompt-input";
import {
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import { useUserMCPServers } from "@/core/user-mcp/hooks";
import {
  useUpdateUserSettings,
  useUserSettings,
} from "@/core/user-settings/hooks";
import { cn } from "@/lib/utils";

import { Tooltip } from "./tooltip";

/**
 * Input-toolbar control for the current user's own MCP servers.
 *
 * Sits alongside the mode selector in the chat input toolbar (in both the
 * welcome / new-conversation state and regular conversations, which share the
 * same InputBox). The list comes from the signed-in user's own registry
 * (``/api/user/mcp``), so user A never sees user B's servers. The "inherit"
 * switch refers to the user's OWN full server set ("用户自己的全局"), not the
 * system-global ``extensions_config.json`` config. The backend replaces global
 * MCP tools with the user's own at agent build time, then applies the per-user
 * ``tools`` override (inherit + enabled_servers), so only allowed servers'
 * tools reach the model.
 */
export function MCPToolsMenu({ disabled = false }: { disabled?: boolean }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const { servers, isLoading: serversLoading } = useUserMCPServers();
  const { settings, isLoading: prefsLoading } = useUserSettings();
  const updatePrefs = useUpdateUserSettings();

  const serverNames = servers.map((server) => server.name);
  const inheritGlobal = settings?.tools.inherit_global ?? true;
  const enabledServers = settings?.tools.enabled_servers ?? [];
  const pending = updatePrefs.isPending || prefsLoading;
  const totalCount = serverNames.length;

  const handleUpdate = (value: {
    inherit_global?: boolean;
    enabled_servers?: string[];
  }) => {
    updatePrefs.mutate(
      { section: "tools", value },
      {
        onError: (err) =>
          toast.error(
            err instanceof Error
              ? err.message
              : t.settings.userPrefs.saveFailed,
          ),
      },
    );
  };

  const handleInheritChange = (inherit: boolean) => {
    handleUpdate(
      inherit
        ? { inherit_global: true }
        : {
            inherit_global: false,
            // Switching off inheritance with an empty override would silently
            // disable every MCP server; default the list to all servers
            // instead (matching the Settings → Tools page).
            enabled_servers:
              enabledServers.length > 0 ? enabledServers : serverNames,
          },
    );
  };

  const handleToggle = (name: string, checked: boolean) => {
    handleUpdate({
      enabled_servers: checked
        ? [...enabledServers, name]
        : enabledServers.filter((item) => item !== name),
    });
  };

  return (
    <Tooltip content={t.settings.mcpTools.title}>
      <PromptInputActionMenu open={open} onOpenChange={setOpen}>
        <PromptInputActionMenuTrigger
          aria-label={t.settings.mcpTools.title}
          className={cn(
            "gap-1! px-2!",
            !inheritGlobal &&
              "bg-accent text-accent-foreground hover:bg-accent/80",
          )}
          data-testid="mcp-tools-trigger"
          disabled={disabled}
        >
          <WrenchIcon className="size-3" />
        </PromptInputActionMenuTrigger>

        <PromptInputActionMenuContent className="w-80">
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-muted-foreground text-xs">
              {t.settings.mcpTools.title}
            </DropdownMenuLabel>

            <div className="flex items-center justify-between gap-4 px-3 py-2">
              <div className="min-w-0 space-y-0.5">
                <div className="text-sm font-medium">
                  {t.settings.userPrefs.inheritGlobal}
                </div>
                <div className="text-muted-foreground text-xs">
                  {t.settings.userPrefs.inheritGlobalHint}
                </div>
              </div>
              <Switch
                checked={inheritGlobal}
                disabled={pending}
                onCheckedChange={handleInheritChange}
              />
            </div>
            <DropdownMenuSeparator />

            {serversLoading || prefsLoading ? (
              <div className="text-muted-foreground flex items-center justify-center gap-2 px-3 py-6 text-sm">
                <LoaderCircleIcon className="size-4 animate-spin" />
                {t.common.loading}
              </div>
            ) : totalCount === 0 ? (
              <div className="text-muted-foreground px-3 py-6 text-center text-sm">
                {t.settings.tools.empty}
              </div>
            ) : inheritGlobal ? (
              <div className="text-muted-foreground px-3 py-3 text-xs">
                {t.settings.mcpTools.followingGlobal}
              </div>
            ) : (
              <div className="divide-border bg-card divide-y overflow-hidden rounded-lg border">
                {serverNames.map((name) => (
                  <div
                    key={name}
                    className="flex items-center justify-between gap-4 px-3 py-2.5"
                  >
                    <div className="min-w-0 space-y-0.5">
                      <div className="truncate text-sm">{name}</div>
                    </div>
                    <Switch
                      checked={enabledServers.includes(name)}
                      disabled={pending}
                      onCheckedChange={(value) => handleToggle(name, value)}
                    />
                  </div>
                ))}
              </div>
            )}
          </DropdownMenuGroup>
        </PromptInputActionMenuContent>
      </PromptInputActionMenu>
    </Tooltip>
  );
}
