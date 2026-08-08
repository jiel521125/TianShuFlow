"use client";

import { RotateCcwIcon, UserRoundIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

export interface UserPrefsItem {
  id: string;
  label: string;
  description?: string;
}

/**
 * Per-user preference card ("个性化偏好") shared by the
 * channels / integrations / tools settings pages.
 *
 * Default semantics (matching the backend): ``inherit_global=true``
 * follows the admin-managed global configuration as-is; switching it
 * off activates the per-user enabled list below.
 */
export function UserPrefsCard({
  items,
  inheritGlobal,
  enabled,
  onInheritChange,
  onToggle,
  onReset,
  pending,
  className,
}: {
  items: UserPrefsItem[];
  inheritGlobal: boolean;
  enabled: string[];
  onInheritChange: (inherit: boolean) => void;
  onToggle: (id: string, enabled: boolean) => void;
  onReset: () => void;
  pending: boolean;
  className?: string;
}) {
  const { t } = useI18n();
  return (
    <div
      className={cn(
        "mb-4 rounded-xl border bg-card p-5 shadow-sm",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
            <UserRoundIcon className="size-4.5" />
          </div>
          <div className="space-y-0.5">
            <div className="text-sm font-semibold">
              {t.settings.userPrefs.title}
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed">
              {t.settings.userPrefs.description}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-foreground"
          onClick={onReset}
          disabled={pending}
          title={t.settings.userPrefs.reset}
        >
          <RotateCcwIcon className="size-4" />
          {t.settings.userPrefs.reset}
        </Button>
      </div>

      {/* Inherit-global toggle */}
      <div className="mt-4 flex items-center justify-between gap-4 rounded-lg bg-muted/50 px-4 py-3">
        <div className="space-y-0.5">
          <div className="text-sm font-medium">
            {t.settings.userPrefs.inheritGlobal}
          </div>
          <p className="text-muted-foreground text-xs">
            {t.settings.userPrefs.inheritGlobalHint}
          </p>
        </div>
        <Switch
          checked={inheritGlobal}
          onCheckedChange={onInheritChange}
          disabled={pending}
        />
      </div>

      {/* Per-user enabled list */}
      {!inheritGlobal && (
        <div className="mt-3">
          {items.length === 0 ? (
            <p className="text-muted-foreground rounded-lg border border-dashed px-4 py-6 text-center text-sm">
              {t.settings.tools.empty}
            </p>
          ) : (
            <ul className="divide-y divide-border overflow-hidden rounded-lg border bg-card">
              {items.map((item) => {
                const checked = enabled.includes(item.id);
                return (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-4 px-4 py-2.5"
                  >
                    <div className="min-w-0 space-y-0.5">
                      <div className="truncate text-sm">{item.label}</div>
                      {item.description ? (
                        <div className="text-muted-foreground truncate text-xs">
                          {item.description}
                        </div>
                      ) : null}
                    </div>
                    <Switch
                      checked={checked}
                      disabled={pending}
                      onCheckedChange={(value) => onToggle(item.id, value)}
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
