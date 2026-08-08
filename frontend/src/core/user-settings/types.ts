/** Per-user settings ("千人千面") types. */

export type SettingsSection =
  | "appearance"
  | "notification"
  | "channels"
  | "integrations"
  | "tools";

export interface AppearanceSettings {
  theme: "system" | "light" | "dark";
  locale: "en-US" | "zh-CN";
}

export interface NotificationSettings {
  enabled: boolean;
}

export interface ChannelsSettings {
  inherit_global: boolean;
  enabled_channels: string[];
}

export interface IntegrationsSettings {
  inherit_global: boolean;
  enabled_integrations: string[];
}

export interface ToolsSettings {
  inherit_global: boolean;
  enabled_servers: string[];
}

export type UserSettingsValue =
  | AppearanceSettings
  | NotificationSettings
  | ChannelsSettings
  | IntegrationsSettings
  | ToolsSettings;

/** Section -> concrete value shape (keeps property access type-safe). */
export type UserSettingsMap = {
  appearance: AppearanceSettings;
  notification: NotificationSettings;
  channels: ChannelsSettings;
  integrations: IntegrationsSettings;
  tools: ToolsSettings;
};

export interface SettingsSectionResponse {
  section: SettingsSection;
  /** Server-side default (single source of truth). */
  default: UserSettingsValue;
  /** User override, or null when the section uses the default. */
  value: UserSettingsValue | null;
  /** default ∪ value */
  effective: UserSettingsValue;
}

export interface UserSettingsResponse {
  defaults: UserSettingsMap;
  values: Partial<UserSettingsMap>;
  effective: UserSettingsMap;
}
