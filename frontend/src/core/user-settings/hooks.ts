import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  loadUserSettings,
  resetUserSettings,
  updateUserSettings,
} from "./api";
import type {
  SettingsSection,
  SettingsSectionResponse,
  UserSettingsMap,
  UserSettingsResponse,
  UserSettingsValue,
} from "./types";

export const userSettingsQueryKey = ["userSettings"] as const;

export function useUserSettings() {
  const { data, isLoading, error } = useQuery({
    queryKey: userSettingsQueryKey,
    queryFn: () => loadUserSettings(),
    // Settings are read on page load; refetch on window focus keeps
    // multi-tab edits in sync without hammering the API.
    refetchOnWindowFocus: true,
  });
  return {
    settings: data?.effective,
    defaults: data?.defaults,
    values: data?.values,
    isLoading,
    error,
  };
}

function applySectionResponse(
  old: UserSettingsResponse | undefined,
  section: SettingsSection,
  response: SettingsSectionResponse,
): UserSettingsResponse {
  const base: UserSettingsResponse = old ?? {
    defaults: {} as UserSettingsMap,
    values: {},
    effective: {} as UserSettingsMap,
  };
  const values = { ...base.values };
  if (response.value === null) {
    delete values[section];
  } else {
    (values as Record<SettingsSection, UserSettingsValue | undefined>)[
      section
    ] = response.value as UserSettingsValue;
  }
  return {
    ...base,
    values,
    effective: {
      ...base.effective,
      [section]: response.effective as UserSettingsValue,
    } as UserSettingsMap,
  };
}

export function useUpdateUserSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      section,
      value,
    }: {
      section: SettingsSection;
      value: Partial<UserSettingsValue>;
    }) => updateUserSettings(section, value),
    onSuccess: (response) => {
      queryClient.setQueryData(userSettingsQueryKey, (old) =>
        applySectionResponse(
          old as UserSettingsResponse | undefined,
          response.section,
          response,
        ),
      );
    },
  });
}

export function useResetUserSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (section: SettingsSection) => resetUserSettings(section),
    onSuccess: (response) => {
      queryClient.setQueryData(userSettingsQueryKey, (old) =>
        applySectionResponse(
          old as UserSettingsResponse | undefined,
          response.section,
          response,
        ),
      );
    },
  });
}
