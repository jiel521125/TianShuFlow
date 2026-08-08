"use client";

import { LoaderCircleIcon } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import type {
  MCPTransport,
  UserMCPServer,
  UserMCPServerCreatePayload,
  UserMCPServerUpdatePayload,
} from "@/core/user-mcp/api";

const ENV_LINE_RE = /^[A-Za-z_][A-Za-z0-9_]*=.+/;

export type UserMCPServerDialogMode = "create" | "edit";

type UserMCPServerDialogProps = {
  open: boolean;
  submitting: boolean;
  mode: UserMCPServerDialogMode;
  existingNames: string[];
  /** Edit mode seed; the env values are masked ("***") by the gateway. */
  initial?: UserMCPServer | null;
  onOpenChange: (open: boolean) => void;
  onSave: (
    name: string,
    payload: UserMCPServerCreatePayload | UserMCPServerUpdatePayload,
  ) => void;
};

function parseEnvLines(text: string): Record<string, string> | null {
  const env: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    if (!ENV_LINE_RE.test(trimmed)) {
      return null;
    }
    const eq = trimmed.indexOf("=");
    env[trimmed.slice(0, eq)] = trimmed.slice(eq + 1);
  }
  return env;
}

/**
 * Create / edit dialog for the signed-in user's OWN MCP servers
 * (``/api/user/mcp``). Unlike the admin-facing global MCP dialog there is no
 * per-server ``enabled`` flag -- enabling/disabling a server happens through
 * the per-user ``tools`` override (inherit + enabled_servers) instead.
 */
export function UserMCPServerDialog({
  open,
  submitting,
  mode,
  existingNames,
  initial,
  onOpenChange,
  onSave,
}: UserMCPServerDialogProps) {
  const { t } = useI18n();
  const isEdit = mode === "edit";

  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [type, setType] = useState<MCPTransport>("stdio");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [envText, setEnvText] = useState("");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [toolNamePrefix, setToolNamePrefix] = useState(true);
  const [timeoutText, setTimeoutText] = useState("");
  const [clearEnv, setClearEnv] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setName(initial?.name ?? "");
    setDisplayName(initial?.display_name ?? "");
    setType(initial?.transport ?? "stdio");
    setCommand(initial?.command ?? "");
    setArgsText((initial?.args ?? []).join("\n"));
    setEnvText("");
    setUrl(initial?.url ?? "");
    setDescription(initial?.description ?? "");
    setToolNamePrefix(initial?.tool_name_prefix ?? true);
    setTimeoutText(
      initial?.tool_call_timeout != null ? String(initial.tool_call_timeout) : "",
    );
    setClearEnv(false);
    setError(null);
  }, [open, initial]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!isEdit && !trimmedName) {
      setError(t.settings.tools.form.nameError);
      return;
    }
    if (!isEdit && existingNames.includes(trimmedName)) {
      setError(t.settings.tools.form.nameDuplicate);
      return;
    }
    if (type === "stdio" && !command.trim()) {
      setError(t.settings.tools.form.commandRequired);
      return;
    }
    if (type !== "stdio" && !url.trim()) {
      setError(t.settings.tools.form.urlRequired);
      return;
    }

    const args = argsText
      .split("\n")
      .map((arg) => arg.trim())
      .filter(Boolean);

    const envTextTrimmed = envText.trim();
    let setEnv: Record<string, string> | null = null;
    if (envTextTrimmed) {
      const parsed = parseEnvLines(envTextTrimmed);
      if (parsed === null) {
        setError(t.settings.tools.form.envInvalid);
        return;
      }
      setEnv = parsed;
    }

    const timeout = timeoutText.trim()
      ? Number(timeoutText.trim())
      : null;

    setError(null);

    if (isEdit) {
      const payload: UserMCPServerUpdatePayload = {
        display_name: displayName.trim() || null,
        description: description.trim() || null,
        transport: type,
        command: type === "stdio" ? command.trim() : null,
        args: type === "stdio" ? args : null,
        url: type !== "stdio" ? url.trim() : null,
        tool_name_prefix: toolNamePrefix,
        tool_call_timeout: timeout,
      };
      // Secrets never round-trip through GET; only send env changes
      // explicitly. ``set_env`` replaces the whole map, ``clear_env`` wipes it.
      if (clearEnv) {
        payload.clear_env = true;
      } else if (setEnv !== null) {
        payload.set_env = setEnv;
      }
      onSave(name, payload);
      return;
    }

    const payload: UserMCPServerCreatePayload = {
      name: trimmedName,
      display_name: displayName.trim() || null,
      description: description.trim() || null,
      transport: type,
      command: type === "stdio" ? command.trim() : null,
      args: type === "stdio" ? args : null,
      env: type === "stdio" ? setEnv : null,
      url: type !== "stdio" ? url.trim() : null,
      tool_name_prefix: toolNamePrefix,
      tool_call_timeout: timeout,
    };
    onSave(trimmedName, payload);
  };

  const isStdio = type === "stdio";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>
              {isEdit
                ? t.settings.tools.editServerTitle
                : t.settings.tools.addServerTitle}
            </DialogTitle>
            <DialogDescription>{t.settings.tools.description}</DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <label
                htmlFor="user-mcp-server-name"
                className="text-sm leading-none font-medium"
              >
                {t.settings.tools.form.name}
              </label>
              <Input
                id="user-mcp-server-name"
                value={name}
                readOnly={isEdit}
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                placeholder={t.settings.tools.form.namePlaceholder}
                onChange={(event) => setName(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="user-mcp-server-display-name"
                className="text-sm leading-none font-medium"
              >
                {t.settings.tools.form.displayName}
              </label>
              <Input
                id="user-mcp-server-display-name"
                value={displayName}
                autoComplete="off"
                placeholder={t.settings.tools.form.displayNamePlaceholder}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="user-mcp-server-type"
                className="text-sm leading-none font-medium"
              >
                {t.settings.tools.form.type}
              </label>
              <Select
                value={type}
                onValueChange={(value) => setType(value as MCPTransport)}
              >
                <SelectTrigger id="user-mcp-server-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="stdio">
                    {t.settings.tools.form.typeStdio}
                  </SelectItem>
                  <SelectItem value="sse">
                    {t.settings.tools.form.typeSse}
                  </SelectItem>
                  <SelectItem value="http">
                    {t.settings.tools.form.typeHttp}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {isStdio ? (
              <>
                <div className="space-y-1.5">
                  <label
                    htmlFor="user-mcp-server-command"
                    className="text-sm leading-none font-medium"
                  >
                    {t.settings.tools.form.command}
                  </label>
                  <Input
                    id="user-mcp-server-command"
                    value={command}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder={t.settings.tools.form.commandPlaceholder}
                    onChange={(event) => setCommand(event.target.value)}
                  />
                  <p className="text-muted-foreground text-xs">
                    {t.settings.tools.form.commandHint}
                  </p>
                </div>
                <div className="space-y-1.5">
                  <label
                    htmlFor="user-mcp-server-args"
                    className="text-sm leading-none font-medium"
                  >
                    {t.settings.tools.form.args}
                  </label>
                  <Textarea
                    id="user-mcp-server-args"
                    value={argsText}
                    rows={4}
                    spellCheck={false}
                    placeholder={t.settings.tools.form.argsPlaceholder}
                    onChange={(event) => setArgsText(event.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <label
                    htmlFor="user-mcp-server-env"
                    className="text-sm leading-none font-medium"
                  >
                    {t.settings.tools.form.env}
                  </label>
                  <Textarea
                    id="user-mcp-server-env"
                    value={envText}
                    rows={3}
                    spellCheck={false}
                    autoComplete="off"
                    autoCorrect="off"
                    autoCapitalize="none"
                    placeholder={t.settings.tools.form.envPlaceholder}
                    onChange={(event) => setEnvText(event.target.value)}
                  />
                  {isEdit && initial?.env_set ? (
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-muted-foreground text-xs">
                        {t.settings.tools.form.envSetHint}
                      </p>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground h-auto px-1 text-xs hover:text-destructive"
                        disabled={clearEnv}
                        onClick={() => {
                          setEnvText("");
                          setClearEnv(true);
                        }}
                      >
                        {t.settings.tools.form.clearEnv}
                      </Button>
                    </div>
                  ) : null}
                </div>
              </>
            ) : (
              <div className="space-y-1.5">
                <label
                  htmlFor="user-mcp-server-url"
                  className="text-sm leading-none font-medium"
                >
                  {t.settings.tools.form.url}
                </label>
                <Input
                  id="user-mcp-server-url"
                  type="url"
                  value={url}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={t.settings.tools.form.urlPlaceholder}
                  onChange={(event) => setUrl(event.target.value)}
                />
              </div>
            )}

            <div className="space-y-1.5">
              <label
                htmlFor="user-mcp-server-description"
                className="text-sm leading-none font-medium"
              >
                {t.settings.tools.form.description}
              </label>
              <Input
                id="user-mcp-server-description"
                value={description}
                placeholder={t.settings.tools.form.descriptionPlaceholder}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>

            <div className="space-y-1.5 rounded-lg border p-3">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 space-y-0.5">
                  <div className="text-sm font-medium">
                    {t.settings.tools.form.toolNamePrefix}
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {t.settings.tools.form.toolNamePrefixHint}
                  </div>
                </div>
                <Switch
                  checked={toolNamePrefix}
                  onCheckedChange={setToolNamePrefix}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="user-mcp-server-timeout"
                className="text-sm leading-none font-medium"
              >
                {t.settings.tools.form.toolCallTimeout}
              </label>
              <Input
                id="user-mcp-server-timeout"
                type="number"
                min={0}
                step="any"
                value={timeoutText}
                autoComplete="off"
                placeholder={t.settings.tools.form.toolCallTimeoutPlaceholder}
                onChange={(event) => setTimeoutText(event.target.value)}
              />
            </div>

            {error ? (
              <div className="text-destructive text-sm">{error}</div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={submitting}
              onClick={() => onOpenChange(false)}
            >
              {t.common.cancel}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? <LoaderCircleIcon className="animate-spin" /> : null}
              {t.common.save}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
