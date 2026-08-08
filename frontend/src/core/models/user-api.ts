import { fetch as csrfFetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "../config";
import { isStaticWebsiteOnly } from "../static-mode";

import type { UserModel, UserModelProvider } from "./types";

const EMPTY_USER_MODELS: UserModel[] = [];
const EMPTY_PROVIDERS: UserModelProvider[] = [];

interface UserModelsResponse {
  models: UserModel[];
}

interface UserModelProvidersResponse {
  providers: UserModelProvider[];
}

async function getJson<T>(path: string, fallback: T): Promise<T> {
  if (isStaticWebsiteOnly()) {
    return fallback;
  }
  const res = await csrfFetch(`${getBackendBaseURL()}${path}`);
  return (await res.json()) as T;
}

export async function loadUserModels(): Promise<UserModel[]> {
  const data = await getJson<UserModelsResponse>("/api/user/models", {
    models: EMPTY_USER_MODELS,
  });
  return data.models ?? EMPTY_USER_MODELS;
}

export async function loadUserModelProviders(): Promise<UserModelProvider[]> {
  const data = await getJson<UserModelProvidersResponse>(
    "/api/user/models/providers",
    { providers: EMPTY_PROVIDERS },
  );
  return data.providers ?? EMPTY_PROVIDERS;
}

export interface UserModelCreateInput {
  name: string;
  display_name?: string | null;
  description?: string | null;
  provider: string;
  api_key?: string | null;
  base_url?: string | null;
  model: string;
  parameters?: Record<string, unknown>;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  context_window?: number | null;
  enabled?: boolean;
}

export interface UserModelUpdateInput {
  display_name?: string | null;
  description?: string | null;
  set_api_key?: string | null;
  clear_api_key?: boolean;
  set_base_url?: string | null;
  clear_base_url?: boolean;
  model?: string | null;
  parameters?: Record<string, unknown> | null;
  supports_thinking?: boolean | null;
  supports_reasoning_effort?: boolean | null;
  context_window?: number | null;
  enabled?: boolean | null;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  // csrfFetch injects X-CSRF-Token on state-changing methods and sends
  // credentials, so the gateway's CSRFMiddleware accepts these requests.
  const res = await csrfFetch(`${getBackendBaseURL()}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json();
  if (!res.ok) {
    const detail =
      (data as { detail?: unknown } | null)?.detail ??
      (data as { message?: unknown } | null)?.message ??
      `Request failed with status ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

export async function createUserModel(input: UserModelCreateInput): Promise<UserModel> {
  return send<UserModel>("POST", "/api/user/models", input);
}

export async function updateUserModel(
  name: string,
  input: UserModelUpdateInput,
): Promise<UserModel> {
  return send<UserModel>("PATCH", `/api/user/models/${encodeURIComponent(name)}`, input);
}

export async function deleteUserModel(name: string): Promise<void> {
  return send<void>("DELETE", `/api/user/models/${encodeURIComponent(name)}`);
}