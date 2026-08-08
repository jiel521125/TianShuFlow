"use client";

import { KeyRoundIcon, LoaderCircleIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";
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
import {
  useCreateUserModel,
  useDeleteUserModel,
  useUpdateUserModel,
  useUserModelProviders,
  useUserModels,
} from "@/core/models/user-hooks";
import type { UserModel, UserModelProvider } from "@/core/models/types";
import { cn } from "@/lib/utils";

import { SettingsSection } from "./settings-section";

/** Mirrors the backend's ``_MODEL_NAME_PATTERN`` in user_models router. */
const MODEL_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

interface FormState {
  name: string;
  displayName: string;
  description: string;
  provider: string;
  apiKey: string;
  baseUrl: string;
  model: string;
  supportsThinking: boolean;
  supportsReasoningEffort: boolean;
  contextWindow: string;
  enabled: boolean;
}

function formFromModel(model: UserModel): FormState {
  return {
    name: model.name,
    displayName: model.display_name ?? "",
    description: model.description ?? "",
    provider: model.provider,
    apiKey: "",
    baseUrl: model.base_url ?? "",
    model: model.model,
    supportsThinking: model.supports_thinking,
    supportsReasoningEffort: model.supports_reasoning_effort,
    contextWindow:
      model.context_window != null ? String(model.context_window) : "",
    enabled: model.enabled,
  };
}

function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label className="text-sm font-medium">{label}</label>
      {children}
      {hint && !error && (
        <p className="text-muted-foreground text-xs">{hint}</p>
      )}
      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}

function ModelFormDialog({
  editing,
  providers,
  submitting,
  onClose,
  onSubmit,
}: {
  editing: UserModel | null;
  providers: UserModelProvider[];
  submitting: boolean;
  onClose: () => void;
  onSubmit: (values: FormState) => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<FormState>(
    editing
      ? formFromModel(editing)
      : { ...emptyForm(), provider: providers[0]?.id ?? "" },
  );
  const [errors, setErrors] = useState<Record<string, string>>({});

  const isEdit = editing !== null;
  const selectedProvider = providers.find((p) => p.id === form.provider);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const nextErrors: Record<string, string> = {};
    const name = form.name.trim();
    const model = form.model.trim();
    if (!name) {
      nextErrors.name = t.settings.models.nameRequired;
    } else if (!MODEL_NAME_PATTERN.test(name)) {
      nextErrors.name = t.settings.models.invalidName;
    }
    if (!form.provider) {
      nextErrors.provider = t.settings.models.providerRequired;
    }
    if (!model) {
      nextErrors.model = t.settings.models.modelRequired;
    }
    if (selectedProvider?.requires_base_url && !form.baseUrl.trim()) {
      nextErrors.baseUrl = t.settings.models.baseUrlRequired;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    onSubmit(form);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto sm:max-w-lg"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle>
            {isEdit ? t.settings.models.editModel : t.settings.models.addModel}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field
            label={t.settings.models.name}
            hint={isEdit ? undefined : t.settings.models.nameHint}
            error={errors.name}
          >
            <Input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder={t.settings.models.namePlaceholder}
              disabled={isEdit}
              required
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t.settings.models.displayName}>
              <Input
                value={form.displayName}
                onChange={(e) => set("displayName", e.target.value)}
                placeholder={t.settings.models.displayNamePlaceholder}
              />
            </Field>
            <Field
              label={t.settings.models.provider}
              error={errors.provider}
            >
              <Select
                value={form.provider}
                onValueChange={(value) => {
                  set("provider", value);
                  const provider = providers.find((p) => p.id === value);
                  if (
                    provider?.requires_base_url &&
                    !form.baseUrl.trim() &&
                    provider.default_base_url
                  ) {
                    set("baseUrl", provider.default_base_url);
                  }
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t.settings.models.provider} />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.id} value={provider.id}>
                      {provider.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>

          <Field
            label={t.settings.models.modelId}
            error={errors.model}
          >
            <Input
              value={form.model}
              onChange={(e) => set("model", e.target.value)}
              placeholder={t.settings.models.modelIdPlaceholder}
              required
            />
          </Field>

          <Field
            label={t.settings.models.apiKey}
            hint={isEdit && editing.api_key_set ? t.settings.models.apiKeySetHint : undefined}
          >
            <Input
              type="password"
              value={form.apiKey}
              onChange={(e) => set("apiKey", e.target.value)}
              placeholder={t.settings.models.apiKeyPlaceholder}
              autoComplete="off"
            />
          </Field>

          <Field
            label={t.settings.models.baseUrl}
            error={errors.baseUrl}
          >
            <Input
              value={form.baseUrl}
              onChange={(e) => set("baseUrl", e.target.value)}
              placeholder={t.settings.models.baseUrlPlaceholder}
            />
          </Field>

          <Field label={t.settings.models.description}>
            <Textarea
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              rows={2}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex items-center justify-between gap-4">
              <span className="text-sm font-medium">
                {t.settings.models.supportsThinking}
              </span>
              <Switch
                checked={form.supportsThinking}
                onCheckedChange={(checked) => set("supportsThinking", checked)}
              />
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-sm font-medium">
                {t.settings.models.supportsReasoningEffort}
              </span>
              <Switch
                checked={form.supportsReasoningEffort}
                onCheckedChange={(checked) =>
                  set("supportsReasoningEffort", checked)
                }
              />
            </div>
            <Field
              label={t.settings.models.contextWindow}
              className="sm:col-span-2"
            >
              <Input
                type="number"
                min={1}
                value={form.contextWindow}
                onChange={(e) => set("contextWindow", e.target.value)}
                placeholder={t.settings.models.contextWindowPlaceholder}
              />
            </Field>
          </div>

          <div className="flex items-center justify-between gap-4">
            <span className="text-sm font-medium">
              {t.settings.models.enabled}
            </span>
            <Switch
              checked={form.enabled}
              onCheckedChange={(checked) => set("enabled", checked)}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={submitting}
            >
              {t.settings.models.cancel}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && (
                <LoaderCircleIcon className="animate-spin" />
              )}
              {isEdit ? t.settings.models.update : t.settings.models.create}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function emptyForm(): FormState {
  return {
    name: "",
    displayName: "",
    description: "",
    provider: "",
    apiKey: "",
    baseUrl: "",
    model: "",
    supportsThinking: false,
    supportsReasoningEffort: false,
    contextWindow: "",
    enabled: true,
  };
}

export function ModelsSettingsPage() {
  const { t } = useI18n();
  const { models, isLoading, error } = useUserModels();
  const { providers, isLoading: providersLoading } = useUserModelProviders();
  const createMutation = useCreateUserModel();
  const updateMutation = useUpdateUserModel();
  const deleteMutation = useDeleteUserModel();

  const [formOpen, setFormOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<UserModel | null>(null);
  const [deletingModel, setDeletingModel] = useState<UserModel | null>(null);

  const openCreate = () => {
    setEditingModel(null);
    setFormOpen(true);
  };

  const openEdit = (model: UserModel) => {
    setEditingModel(model);
    setFormOpen(true);
  };

  const handleSubmit = (values: FormState) => {
    const contextWindow = values.contextWindow.trim()
      ? Number(values.contextWindow)
      : null;
    if (editingModel) {
      updateMutation.mutate(
        {
          name: editingModel.name,
          input: {
            display_name: values.displayName.trim() || null,
            description: values.description.trim() || null,
            set_api_key: values.apiKey.trim() || undefined,
            set_base_url: values.baseUrl.trim() || undefined,
            model: values.model.trim(),
            supports_thinking: values.supportsThinking,
            supports_reasoning_effort: values.supportsReasoningEffort,
            context_window: contextWindow,
            enabled: values.enabled,
          },
        },
        {
          onSuccess: () => {
            setFormOpen(false);
            toast.success(t.settings.models.updateSuccess);
          },
          onError: (err) => {
            toast.error(
              err instanceof Error
                ? err.message
                : t.settings.models.saveFailed,
            );
          },
        },
      );
      return;
    }
    createMutation.mutate(
      {
        name: values.name.trim(),
        display_name: values.displayName.trim() || null,
        description: values.description.trim() || null,
        provider: values.provider,
        api_key: values.apiKey.trim() || null,
        base_url: values.baseUrl.trim() || null,
        model: values.model.trim(),
        supports_thinking: values.supportsThinking,
        supports_reasoning_effort: values.supportsReasoningEffort,
        context_window: contextWindow,
        enabled: values.enabled,
      },
      {
        onSuccess: () => {
          setFormOpen(false);
          toast.success(t.settings.models.createSuccess);
        },
        onError: (err) => {
          toast.error(
            err instanceof Error
              ? err.message
              : t.settings.models.saveFailed,
          );
        },
      },
    );
  };

  const handleDelete = (model: UserModel) => {
    deleteMutation.mutate(model.name, {
      onSuccess: () => {
        setDeletingModel(null);
        toast.success(t.settings.models.deleteSuccess);
      },
      onError: (err) => {
        toast.error(
          err instanceof Error
            ? err.message
            : t.settings.models.deleteFailed,
        );
      },
    });
  };

  const loading = isLoading || providersLoading;

  return (
    <SettingsSection
      title={t.settings.models.title}
      description={t.settings.models.description}
    >
      <div className="flex items-center justify-between">
        <Button type="button" size="sm" onClick={openCreate} disabled={loading}>
          <PlusIcon className="size-4" />
          {t.settings.models.addModel}
        </Button>
      </div>

      <div className="mt-4">
        {loading ? (
          <div className="text-muted-foreground text-sm">{t.common.loading}</div>
        ) : error ? (
          <div className="text-destructive text-sm">
            {t.settings.models.loadFailed}
          </div>
        ) : models.length === 0 ? (
          <div className="text-muted-foreground text-sm">
            {t.settings.models.empty}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {models.map((model) => (
              <Item key={model.id} variant="outline" className="w-full">
                <ItemMedia variant="icon" className="bg-background">
                  <KeyRoundIcon className="size-4" />
                </ItemMedia>
                <ItemContent className="min-w-0">
                  <ItemTitle className="w-full">
                    <span className="truncate">
                      {model.display_name ?? model.name}
                    </span>
                    <Badge variant="outline">{model.provider}</Badge>
                    <Badge
                      variant={model.enabled ? "default" : "outline"}
                      className={cn(
                        !model.enabled && "text-muted-foreground",
                      )}
                    >
                      {model.enabled
                        ? t.settings.models.enabledBadge
                        : t.settings.models.disabledBadge}
                    </Badge>
                  </ItemTitle>
                  <ItemDescription className="line-clamp-none">
                    {model.model}
                    {model.api_key_set
                      ? ` · ${t.settings.models.keyConfigured}`
                      : ` · ${t.settings.models.keyMissing}`}
                    {model.base_url ? ` · ${model.base_url}` : ""}
                  </ItemDescription>
                </ItemContent>
                <ItemActions className="ml-auto">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => openEdit(model)}
                  >
                    {t.settings.models.editModel}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setDeletingModel(model)}
                  >
                    <Trash2Icon className="size-4" />
                    {t.settings.models.deleteModel}
                  </Button>
                </ItemActions>
              </Item>
            ))}
          </div>
        )}
      </div>

      {formOpen && (
        <ModelFormDialog
          key={editingModel?.id ?? "new"}
          editing={editingModel}
          providers={providers}
          submitting={createMutation.isPending || updateMutation.isPending}
          onClose={() => setFormOpen(false)}
          onSubmit={handleSubmit}
        />
      )}

      <Dialog
        open={deletingModel !== null}
        onOpenChange={(open) => !open && setDeletingModel(null)}
      >
        <DialogContent aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>{t.settings.models.deleteConfirmTitle}</DialogTitle>
            <DialogDescription>
              {deletingModel
                ? t.settings.models.deleteConfirmDescription(
                    deletingModel.display_name ?? deletingModel.name,
                  )
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeletingModel(null)}
              disabled={deleteMutation.isPending}
            >
              {t.settings.models.cancel}
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => deletingModel && handleDelete(deletingModel)}
            >
              {deleteMutation.isPending && (
                <LoaderCircleIcon className="animate-spin" />
              )}
              {t.settings.models.deleteModel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsSection>
  );
}
