export interface Model {
  id: string;
  name: string;
  model: string;
  display_name: string;
  description?: string | null;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
}

/** A provider entry from ``GET /api/user/models/providers``. */
export interface UserModelProvider {
  id: string;
  class_path: string;
  requires_base_url: boolean;
  api_key_kwarg: string;
  default_base_url: string | null;
}

/** A user-defined model row from ``GET /api/user/models``. */
export interface UserModel {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  provider: string;
  /** True when an api_key is stored server-side (the key itself is never returned). */
  api_key_set: boolean;
  base_url: string | null;
  model: string;
  parameters: Record<string, unknown>;
  supports_thinking: boolean;
  supports_reasoning_effort: boolean;
  context_window: number | null;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface TokenUsageSettings {
  enabled: boolean;
}

export interface ModelsResponse {
  models: Model[];
  token_usage: TokenUsageSettings;
}
