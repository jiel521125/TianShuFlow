import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createUserModel,
  deleteUserModel,
  loadUserModelProviders,
  loadUserModels,
  updateUserModel,
  type UserModelCreateInput,
  type UserModelUpdateInput,
} from "./user-api";

export const userModelsQueryKey = ["userModels"] as const;
export const userModelProvidersQueryKey = ["userModelProviders"] as const;

export function useUserModels() {
  const { data, isLoading, error } = useQuery({
    queryKey: userModelsQueryKey,
    queryFn: () => loadUserModels(),
  });
  return { models: data ?? [], isLoading, error };
}

export function useUserModelProviders() {
  const { data, isLoading, error } = useQuery({
    queryKey: userModelProvidersQueryKey,
    queryFn: () => loadUserModelProviders(),
  });
  return { providers: data ?? [], isLoading, error };
}

function useInvalidateModelQueries() {
  const queryClient = useQueryClient();
  return () => {
    // The chat input box reads the merged list via useModels (["models"]),
    // so a CRUD change must refresh it in addition to the user rows.
    void queryClient.invalidateQueries({ queryKey: userModelsQueryKey });
    void queryClient.invalidateQueries({ queryKey: ["models"] });
  };
}

export function useCreateUserModel() {
  const invalidate = useInvalidateModelQueries();
  return useMutation({
    mutationFn: (input: UserModelCreateInput) => createUserModel(input),
    onSuccess: invalidate,
  });
}

export function useUpdateUserModel() {
  const invalidate = useInvalidateModelQueries();
  return useMutation({
    mutationFn: ({
      name,
      input,
    }: {
      name: string;
      input: UserModelUpdateInput;
    }) => updateUserModel(name, input),
    onSuccess: invalidate,
  });
}

export function useDeleteUserModel() {
  const invalidate = useInvalidateModelQueries();
  return useMutation({
    mutationFn: (name: string) => deleteUserModel(name),
    onSuccess: invalidate,
  });
}
