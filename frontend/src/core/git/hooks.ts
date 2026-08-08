import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  loadGitConfig,
  saveGitConfig,
  type GitConfigStatus,
} from "./api";

export const gitConfigQueryKey = ["gitConfig"] as const;

export function useGitConfig() {
  return useQuery({
    queryKey: gitConfigQueryKey,
    queryFn: () => loadGitConfig(),
  });
}

export function useSaveGitConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      github_token?: string | null;
      gitee_token?: string | null;
    }) => saveGitConfig(body),
    onSuccess: (status: GitConfigStatus) => {
      queryClient.setQueryData(gitConfigQueryKey, status);
    },
  });
}
