"use client";

import { BellIcon, RotateCcwIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import {
  useResetUserSettings,
  useUpdateUserSettings,
  useUserSettings,
} from "@/core/user-settings/hooks";

import { SettingsSection } from "./settings-section";

export function NotificationSettingsPage() {
  const { t } = useI18n();
  const { permission, isSupported, requestPermission, showNotification } =
    useNotification();

  // Per-user notification preference, stored in the database.
  const { settings, isLoading } = useUserSettings();
  const updateSettings = useUpdateUserSettings();
  const resetSettings = useResetUserSettings();
  const enabled = settings?.notification.enabled ?? true;
  const saving = updateSettings.isPending || resetSettings.isPending;

  const handleRequestPermission = async () => {
    await requestPermission();
  };

  const handleTestNotification = () => {
    showNotification(t.settings.notification.testTitle, {
      body: t.settings.notification.testBody,
    });
  };

  const handleEnableNotification = (next: boolean) => {
    updateSettings.mutate(
      { section: "notification", value: { enabled: next } },
      {
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : t.settings.userPrefs.saveFailed,
          ),
      },
    );
  };

  const handleReset = () => {
    resetSettings.mutate("notification", {
      onSuccess: () => toast.success(t.settings.userPrefs.resetSuccess),
      onError: (err) =>
        toast.error(
          err instanceof Error ? err.message : t.settings.userPrefs.resetFailed,
        ),
    });
  };

  if (!isSupported) {
    return (
      <SettingsSection
        title={t.settings.notification.title}
        description={t.settings.notification.description}
      >
        <p className="text-muted-foreground text-sm">
          {t.settings.notification.notSupported}
        </p>
      </SettingsSection>
    );
  }

  return (
    <SettingsSection
      title={t.settings.notification.title}
      description={
        <div className="flex items-center gap-2">
          <div>{t.settings.notification.description}</div>
          <div>
            <Switch
              aria-label={t.settings.notification.title}
              disabled={permission !== "granted" || saving}
              checked={permission === "granted" && enabled}
              onCheckedChange={handleEnableNotification}
            />
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground text-sm">
          {isLoading ? t.common.loading : t.settings.userPrefs.description}
        </p>
        {permission === "default" && (
          <Button onClick={handleRequestPermission} variant="default">
            <BellIcon className="mr-2 size-4" />
            {t.settings.notification.requestPermission}
          </Button>
        )}

        {permission === "denied" && (
          <p className="text-muted-foreground rounded-md border border-amber-200 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/50">
            {t.settings.notification.deniedHint}
          </p>
        )}

        {permission === "granted" && enabled && (
          <div className="flex flex-col gap-4">
            <Button onClick={handleTestNotification} variant="outline">
              <BellIcon className="mr-2 size-4" />
              {t.settings.notification.testButton}
            </Button>
          </div>
        )}

        <Button
          variant="ghost"
          size="sm"
          className="self-start"
          onClick={handleReset}
          disabled={saving}
        >
          <RotateCcwIcon className="size-4" />
          {t.settings.userPrefs.reset}
        </Button>
      </div>
    </SettingsSection>
  );
}
