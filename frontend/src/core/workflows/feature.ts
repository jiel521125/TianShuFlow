import { useQuery } from '@tanstack/react-query';

import { fetchWorkflowsApiEnabled } from '@/core/features/api';

const WORKFLOWS_API_ENABLED_QUERY_KEY = ['features', 'workflows_api'];

export function useWorkflowsApiEnabled() {
  const query = useQuery<boolean>({
    queryKey: WORKFLOWS_API_ENABLED_QUERY_KEY,
    queryFn: fetchWorkflowsApiEnabled,
    staleTime: 60 * 1000,
  });
  return {
    enabled: query.data ?? false,
    isLoading: query.isLoading,
    error: query.error,
  };
}
