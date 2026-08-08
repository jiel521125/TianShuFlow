import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createUserMCPServer,
  deleteUserMCPServer,
  loadUserMCPServers,
  updateUserMCPServer,
  type UserMCPServer,
  type UserMCPServerCreatePayload,
  type UserMCPServerUpdatePayload,
} from "./api";

export const userMcpQueryKey = ["userMcp"] as const;

export function useUserMCPServers() {
  const { data, isLoading, error } = useQuery({
    queryKey: userMcpQueryKey,
    queryFn: () => loadUserMCPServers(),
  });
  return { servers: data ?? [], isLoading, error };
}

export function useCreateUserMCPServer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserMCPServerCreatePayload) =>
      createUserMCPServer(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userMcpQueryKey }),
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });
}

export function useUpdateUserMCPServer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      payload,
    }: {
      name: string;
      payload: UserMCPServerUpdatePayload;
    }) => updateUserMCPServer(name, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userMcpQueryKey }),
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });
}

export function useDeleteUserMCPServer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => deleteUserMCPServer(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userMcpQueryKey }),
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });
}

export function useUserMCPServer(name: string | null): UserMCPServer | undefined {
  const { servers } = useUserMCPServers();
  if (!name) return undefined;
  return servers.find((server) => server.name === name);
}
