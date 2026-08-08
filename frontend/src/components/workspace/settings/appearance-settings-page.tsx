"use client";

import { MonitorSmartphoneIcon, MoonIcon, RotateCcwIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useMemo, type ComponentType, type SVGProps } from "react";
import { toast } from "sonner";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { enUS, isLocale, zhCN, type Locale } from "@/core/i18n";
import { useI18n } from "@/core/i18n/hooks";
import type { AppearanceSettings } from "@/core/user-settings/types";
import {
  useResetUserSettings,
  useUpdateUserSettings,
  useUserSettings,
} from "@/core/user-settings/hooks";
import { cn } from "@/lib/utils";

import { SettingsSection } from "./settings-section";

const languageOptions: { value: Locale; label: string }[] = [
  { value: "en-US", label: enUS.locale.localName },
  { value: "zh-CN", label: zhCN.locale.localName },
];

export function AppearanceSettingsPage() {
  const { t, locale, changeLocale } = useI18n();
  const { theme, setTheme, systemTheme } = useTheme();
  const currentTheme = (theme ?? "system") as "system" | "light" | "dark";

  // Per-user settings from the database ("千人千面"): the backend value
  // is authoritative; localStorage/cookie remain instant-render caches.
  const { settings, isLoading } = useUserSettings();
  const updateSettings = useUpdateUserSettings();
  const resetSettings = useResetUserSettings();
  const appearance = settings?.appearance;
  const saving = updateSettings.isPending || resetSettings.isPending;

  useEffect(() => {
    if (appearance) {
      setTheme(appearance.theme);
      if (isLocale(appearance.locale)) {
        changeLocale(appearance.locale);
      }
    }
    // Sync only when the server value arrives or changes; deliberately
    // excludes setTheme/changeLocale (those are the apply side).
  }, [appearance, setTheme, changeLocale]);

  const handleThemeChange = (value: "system" | "light" | "dark") => {
    setTheme(value);
    if (!appearance) return;
    updateSettings.mutate(
      { section: "appearance", value: { theme: value } },
      {
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : t.settings.userPrefs.saveFailed,
          ),
      },
    );
  };

  const handleLocaleChange = (value: Locale) => {
    changeLocale(value);
    if (!appearance) return;
    updateSettings.mutate(
      { section: "appearance", value: { locale: value } },
      {
        onError: (err) =>
          toast.error(
            err instanceof Error ? err.message : t.settings.userPrefs.saveFailed,
          ),
      },
    );
  };

  const handleReset = () => {
    resetSettings.mutate("appearance", {
      onSuccess: (response) => {
        const effective = response.effective as AppearanceSettings;
        setTheme(effective.theme);
        if (isLocale(effective.locale)) {
          changeLocale(effective.locale);
        }
        toast.success(t.settings.userPrefs.resetSuccess);
      },
      onError: (err) =>
        toast.error(
          err instanceof Error ? err.message : t.settings.userPrefs.resetFailed,
        ),
    });
  };

  const themeOptions = useMemo(
    () => [
      {
        id: "system",
        label: t.settings.appearance.system,
        description: t.settings.appearance.systemDescription,
        icon: MonitorSmartphoneIcon,
      },
      {
        id: "light",
        label: t.settings.appearance.light,
        description: t.settings.appearance.lightDescription,
        icon: SunIcon,
      },
      {
        id: "dark",
        label: t.settings.appearance.dark,
        description: t.settings.appearance.darkDescription,
        icon: MoonIcon,
      },
    ],
    [
      t.settings.appearance.dark,
      t.settings.appearance.darkDescription,
      t.settings.appearance.light,
      t.settings.appearance.lightDescription,
      t.settings.appearance.system,
      t.settings.appearance.systemDescription,
    ],
  );

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-4">
        <p className="text-muted-foreground text-sm">
          {isLoading ? t.common.loading : t.settings.userPrefs.description}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleReset}
          disabled={saving}
        >
          <RotateCcwIcon className="size-4" />
          {t.settings.userPrefs.reset}
        </Button>
      </div>

      <SettingsSection
        title={t.settings.appearance.themeTitle}
        description={t.settings.appearance.themeDescription}
      >
        <div className="grid gap-3 lg:grid-cols-3">
          {themeOptions.map((option) => (
            <ThemePreviewCard
              key={option.id}
              icon={option.icon}
              label={option.label}
              description={option.description}
              active={currentTheme === option.id}
              mode={option.id as "system" | "light" | "dark"}
              systemTheme={systemTheme}
              onSelect={handleThemeChange}
            />
          ))}
        </div>
      </SettingsSection>

      <Separator />

      <SettingsSection
        title={t.settings.appearance.languageTitle}
        description={t.settings.appearance.languageDescription}
      >
        <Select
          value={locale}
          onValueChange={(value) => {
            if (isLocale(value)) {
              handleLocaleChange(value);
            }
          }}
        >
          <SelectTrigger className="w-[220px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {languageOptions.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </SettingsSection>
    </div>
  );
}

function ThemePreviewCard({
  icon: Icon,
  label,
  description,
  active,
  mode,
  systemTheme,
  onSelect,
}: {
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  label: string;
  description: string;
  active: boolean;
  mode: "system" | "light" | "dark";
  systemTheme?: string;
  onSelect: (mode: "system" | "light" | "dark") => void;
}) {
  const previewMode =
    mode === "system" ? (systemTheme === "dark" ? "dark" : "light") : mode;
  return (
    <button
      type="button"
      onClick={() => onSelect(mode)}
      className={cn(
        "group flex h-full flex-col gap-3 rounded-lg border p-4 text-left transition-all",
        active
          ? "border-primary ring-primary/30 shadow-sm ring-2"
          : "hover:border-border hover:shadow-sm",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="bg-muted rounded-md p-2">
          <Icon className="size-4" />
        </div>
        <div className="space-y-1">
          <div className="text-sm leading-none font-semibold">{label}</div>
          <p className="text-muted-foreground text-xs leading-snug">
            {description}
          </p>
        </div>
      </div>
      <div
        className={cn(
          "relative overflow-hidden rounded-md border text-xs transition-colors",
          previewMode === "dark"
            ? "border-neutral-800 bg-neutral-900 text-neutral-200"
            : "border-slate-200 bg-white text-slate-900",
        )}
      >
        <div className="border-border/50 flex items-center gap-2 border-b px-3 py-2">
          <div
            className={cn(
              "h-2 w-2 rounded-full",
              previewMode === "dark" ? "bg-emerald-400" : "bg-emerald-500",
            )}
          />
          <div className="h-2 w-10 rounded-full bg-current/20" />
          <div className="h-2 w-6 rounded-full bg-current/15" />
        </div>
        <div className="grid grid-cols-[1fr_240px] gap-3 px-3 py-3">
          <div className="space-y-2">
            <div className="h-3 w-3/4 rounded-full bg-current/15" />
            <div className="h-3 w-1/2 rounded-full bg-current/10" />
            <div className="h-[90px] rounded-md border border-current/10 bg-current/5" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-md bg-current/10" />
              <div className="space-y-2">
                <div className="h-2 w-14 rounded-full bg-current/15" />
                <div className="h-2 w-10 rounded-full bg-current/10" />
              </div>
            </div>
            <div className="flex flex-col gap-1 rounded-md border border-dashed border-current/15 p-2">
              <div className="h-2 w-3/5 rounded-full bg-current/15" />
              <div className="h-2 w-2/5 rounded-full bg-current/10" />
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}
