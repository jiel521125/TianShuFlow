"use client";

import { useMemo, useState } from "react";
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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useUpdateAgent } from "@/core/agents";
import type { Agent, ReasoningEffort } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";
import { useModels } from "@/core/models/hooks";

import {
  DEFAULT_MODEL_VALUE,
  INHERIT_VALUE,
  MAX_AGENT_OUTPUT_TOKENS,
  parseAgentModelSettingsDraft,
  resolveEffectiveModel,
  selectionToThinkingEnabled,
  thinkingEnabledToSelection,
} from "./agent-settings-dialog-helpers";

const REASONING_EFFORTS: ReasoningEffort[] = ["low", "medium", "high"];

interface AgentSettingsDialogProps {
  agent: Agent;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Edits a custom agent's full configuration across two tabs:
 *
 * 1. **SOUL & 描述** — The agent's description and SOUL (system prompt),
 *    which defines its role, personality, and behavioral instructions.
 *    This is the most important configuration for fine-tuning agent behavior.
 *
 * 2. **模型设置** — Default model plus per-agent temperature / max_tokens
 *    overrides and thinking / reasoning defaults.
 *
 * Persists through `PUT /api/agents/{name}`; changes take effect on the
 * agent's next run.
 */
export function AgentSettingsDialog({
  agent,
  open,
  onOpenChange,
}: AgentSettingsDialogProps) {
  const { t } = useI18n();
  const { models } = useModels();
  const updateAgent = useUpdateAgent();

  // --- SOUL & Description state ---
  const [description, setDescription] = useState(agent.description ?? "");
  const [soul, setSoul] = useState(agent.soul ?? "");

  // --- Model settings state ---
  const [model, setModel] = useState(agent.model ?? DEFAULT_MODEL_VALUE);
  const [temperature, setTemperature] = useState(
    agent.model_settings?.temperature != null
      ? String(agent.model_settings.temperature)
      : "",
  );
  const [maxTokens, setMaxTokens] = useState(
    agent.model_settings?.max_tokens != null
      ? String(agent.model_settings.max_tokens)
      : "",
  );
  const [thinking, setThinking] = useState(
    thinkingEnabledToSelection(agent.thinking_enabled),
  );
  const [reasoningEffort, setReasoningEffort] = useState(
    agent.reasoning_effort ?? INHERIT_VALUE,
  );

  const selectedModel = useMemo(
    () => resolveEffectiveModel(models, model),
    [models, model],
  );
  const supportsThinking = selectedModel?.supports_thinking ?? false;
  const supportsReasoningEffort =
    selectedModel?.supports_reasoning_effort ?? false;

  async function handleSave() {
    const parsedSettings = parseAgentModelSettingsDraft({
      temperature,
      maxTokens,
    });
    if (!parsedSettings.ok) {
      toast.error(
        parsedSettings.error === "temperature"
          ? t.agents.settingsInvalidTemperature
          : t.agents.settingsInvalidMaxTokens,
      );
      return;
    }

    try {
      await updateAgent.mutateAsync({
        name: agent.name,
        request: {
          description: description || null,
          soul: soul || null,
          model: model === DEFAULT_MODEL_VALUE ? null : model,
          model_settings: parsedSettings.modelSettings,
          thinking_enabled: supportsThinking
            ? selectionToThinkingEnabled(thinking)
            : null,
          reasoning_effort:
            supportsReasoningEffort && reasoningEffort !== INHERIT_VALUE
              ? (reasoningEffort as ReasoningEffort)
              : null,
        },
      });
      toast.success(t.agents.settingsSaved);
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {t.agents.settingsTitle} — {agent.name}
          </DialogTitle>
          <DialogDescription>{t.agents.settingsDescription}</DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="soul" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="soul">SOUL &amp; 描述</TabsTrigger>
            <TabsTrigger value="model">模型设置</TabsTrigger>
          </TabsList>

          {/* --- Tab 1: SOUL & Description --- */}
          <TabsContent value="soul" className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">描述</label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="简要描述这个 Agent 的用途..."
              />
              <p className="text-muted-foreground text-xs">
                显示在 Agent 卡片上，帮助用户快速了解 Agent 的用途
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">
                SOUL（系统提示词）
              </label>
              <textarea
                className="h-72 w-full resize-y rounded-md border bg-background px-3 py-2 font-mono text-sm leading-relaxed focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                value={soul}
                onChange={(e) => setSoul(e.target.value)}
                placeholder={`你是一个专业的...\n\n工作准则：\n1. ...\n2. ...\n3. ...`}
                spellCheck={false}
              />
              <div className="flex items-center justify-between">
                <p className="text-muted-foreground text-xs">
                  定义 Agent 的角色、行为规范和输出格式。支持 Markdown 语法。
                </p>
                <span className="text-muted-foreground text-xs tabular-nums">
                  {soul.length} 字符
                </span>
              </div>
            </div>

            {agent.soul && agent.soul !== soul && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs"
                onClick={() => setSoul(agent.soul ?? "")}
              >
                ↺ 恢复原始 SOUL
              </Button>
            )}
          </TabsContent>

          {/* --- Tab 2: Model Settings --- */}
          <TabsContent value="model" className="space-y-4 py-2">
            {/* Default model */}
            <div className="space-y-1.5">
              <span className="text-sm font-medium">
                {t.agents.settingsModel}
              </span>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={DEFAULT_MODEL_VALUE}>
                    {t.agents.settingsModelDefault}
                  </SelectItem>
                  {models.map((m) => (
                    <SelectItem key={m.name} value={m.name}>
                      {m.display_name || m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Temperature */}
            <div className="space-y-1.5">
              <span className="text-sm font-medium">
                {t.agents.settingsTemperature}
              </span>
              <Input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={temperature}
                placeholder={t.agents.settingsInherit}
                onChange={(e) => setTemperature(e.target.value)}
              />
              <p className="text-muted-foreground text-xs">
                {t.agents.settingsTemperatureHint}
              </p>
            </div>

            {/* Max output tokens */}
            <div className="space-y-1.5">
              <span className="text-sm font-medium">
                {t.agents.settingsMaxTokens}
              </span>
              <Input
                type="number"
                min={1}
                max={MAX_AGENT_OUTPUT_TOKENS}
                step={1}
                value={maxTokens}
                placeholder={t.agents.settingsMaxTokensPlaceholder}
                onChange={(e) => setMaxTokens(e.target.value)}
              />
            </div>

            {/* Thinking mode */}
            {supportsThinking && (
              <div className="space-y-1.5">
                <span className="text-sm font-medium">
                  {t.agents.settingsThinking}
                </span>
                <Select
                  value={thinking}
                  onValueChange={(value) => setThinking(value as typeof thinking)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={INHERIT_VALUE}>
                      {t.agents.settingsInherit}
                    </SelectItem>
                    <SelectItem value="on">
                      {t.agents.settingsThinkingOn}
                    </SelectItem>
                    <SelectItem value="off">
                      {t.agents.settingsThinkingOff}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Reasoning effort */}
            {supportsReasoningEffort && (
              <div className="space-y-1.5">
                <span className="text-sm font-medium">
                  {t.agents.settingsReasoningEffort}
                </span>
                <Select
                  value={reasoningEffort}
                  onValueChange={setReasoningEffort}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={INHERIT_VALUE}>
                      {t.agents.settingsInherit}
                    </SelectItem>
                    {REASONING_EFFORTS.map((effort) => (
                      <SelectItem key={effort} value={effort}>
                        {effort}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={updateAgent.isPending}
          >
            {t.common.cancel}
          </Button>
          <Button onClick={handleSave} disabled={updateAgent.isPending}>
            {updateAgent.isPending ? t.common.loading : t.common.save}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
