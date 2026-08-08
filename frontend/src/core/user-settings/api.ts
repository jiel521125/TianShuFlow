import { fetch as csrfFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "../config";

import type {
  SettingsSection,
  SettingsSectionResponse,
  UserSettingsResponse,
  UserSettingsValue,
} from "./types";

async function send<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  // csrfFetch injects X-CSRF-Token on state-changing methods and sends
  // credentials, so the gateway's CSRFMiddleware accepts these requests.
  const res = await csrfFetch(`${getBackendBaseURL()}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = (await res.json().catch(() => null)) as unknown;
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new Error(
      typeof detail === "string" ? detail : `Request failed (${res.status})`,
    );
  }
  return data as T;
}

/** Load defaults + overrides + effective values for all settings sections. */
export function loadUserSettings(): Promise<UserSettingsResponse> {
  return send("GET", "/api/user/settings");
}

/** Merge *value* over the user's override for a section and persist it. */
export function updateUserSettings(
  section: SettingsSection,
  value: Partial<UserSettingsValue>,
): Promise<SettingsSectionResponse> {
  return send("PUT", `/api/user/settings/${section}`, value);
}

/** Reset a section to its server-side default. */
export function resetUserSettings(
  section: SettingsSection,
): Promise<SettingsSectionResponse> {
  return send("DELETE", `/api/user/settings/${section}`);
}
