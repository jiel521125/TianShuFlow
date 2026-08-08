/**
 * React Query hooks for workflow management.
 */

import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  cancelExecution,
  copyWorkflow,
  createWorkflow,
  deleteWorkflow,
  executeWorkflow,
  getExecution,
  getWorkflow,
  listExecutions,
  listWorkflows,
  updateWorkflow,
  validateWorkflow,
} from './api';
import type {
  ValidationResult,
  Workflow,
  WorkflowCopyRequest,
  WorkflowCreateRequest,
  WorkflowExecution,
  WorkflowExecutionDetail,
  WorkflowExecutionListResponse,
  WorkflowExecuteRequest,
  WorkflowListResponse,
  WorkflowUpdateRequest,
} from './types';

const WORKFLOWS_QUERY_KEY = ['workflows'] as const;
const WORKFLOW_QUERY_KEY = (id: string) => ['workflows', id] as const;
const EXECUTIONS_QUERY_KEY = (workflowId: string) =>
  ['workflows', workflowId, 'executions'] as const;
const EXECUTION_QUERY_KEY = (executionId: string) =>
  ['workflows', 'executions', executionId] as const;

export function useWorkflows(search = '', offset = 0, limit = 20) {
  return useQuery<WorkflowListResponse>({
    queryKey: [...WORKFLOWS_QUERY_KEY, search, offset, limit],
    queryFn: () => listWorkflows(search, offset, limit),
  });
}

export function useWorkflow(id: string) {
  return useQuery<Workflow>({
    queryKey: WORKFLOW_QUERY_KEY(id),
    queryFn: () => getWorkflow(id),
    enabled: !!id,
  });
}

export function useCreateWorkflow() {
  const queryClient = useQueryClient();
  return useMutation<Workflow, Error, WorkflowCreateRequest>({
    mutationFn: createWorkflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WORKFLOWS_QUERY_KEY });
    },
  });
}

export function useUpdateWorkflow() {
  const queryClient = useQueryClient();
  return useMutation<
    Workflow,
    Error,
    { id: string; request: WorkflowUpdateRequest }
  >({
    mutationFn: ({ id, request }) => updateWorkflow(id, request),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: WORKFLOW_QUERY_KEY(variables.id),
      });
      queryClient.invalidateQueries({ queryKey: WORKFLOWS_QUERY_KEY });
    },
  });
}

export function useDeleteWorkflow() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: deleteWorkflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WORKFLOWS_QUERY_KEY });
    },
  });
}

export function useCopyWorkflow() {
  const queryClient = useQueryClient();
  return useMutation<
    Workflow,
    Error,
    { id: string; request?: WorkflowCopyRequest }
  >({
    mutationFn: ({ id, request }) => copyWorkflow(id, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WORKFLOWS_QUERY_KEY });
    },
  });
}

export function useValidateWorkflow() {
  return useMutation<
    ValidationResult,
    Error,
    { definition: WorkflowCreateRequest['definition'] }
  >({
    mutationFn: ({ definition }) => validateWorkflow(definition),
  });
}

export function useExecutions(workflowId: string, offset = 0, limit = 20) {
  return useQuery<WorkflowExecutionListResponse>({
    queryKey: EXECUTIONS_QUERY_KEY(workflowId),
    queryFn: () => listExecutions(workflowId, offset, limit),
    enabled: !!workflowId,
  });
}

export function useExecution(executionId: string) {
  return useQuery<WorkflowExecutionDetail>({
    queryKey: EXECUTION_QUERY_KEY(executionId),
    queryFn: () => getExecution(executionId),
    enabled: !!executionId,
  });
}

export function useInvalidateWorkflows() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: WORKFLOWS_QUERY_KEY });
  };
}

// Hook for listing all workflows (for selector use)
export function useListWorkflows() {
  return useQuery<WorkflowListResponse>({
    queryKey: [...WORKFLOWS_QUERY_KEY, '', 0, 100],
    queryFn: () => listWorkflows('', 0, 100),
  });
}

// Hook for executing a workflow with SSE streaming
export function useExecuteWorkflow() {
  const queryClient = useQueryClient();
  
  const execute = useCallback(async (
    id: string,
    request: WorkflowExecuteRequest,
    onEvent: (event: { event_type: string; data: Record<string, unknown> }) => void,
  ) => {
    const response = await executeWorkflow(id, request);
    if (!response.ok) {
      throw new Error(`Failed to execute workflow: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmedLine = line.trim();
        if (trimmedLine.startsWith('event:')) {
          const eventType = trimmedLine.slice(6).trim();
          const dataLine = lines.find((l) => l.trim().startsWith('data:'));
          if (dataLine) {
            const dataStr = dataLine.slice(5).trim();
            try {
              const data = JSON.parse(dataStr);
              onEvent({ event_type: eventType, data });
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    }

    // Invalidate caches after execution
    queryClient.invalidateQueries({ queryKey: WORKFLOWS_QUERY_KEY });
  }, [queryClient]);

  return { execute };
}

// Hook for cancelling an execution
export function useCancelExecution() {
  const queryClient = useQueryClient();
  return useMutation<WorkflowExecution, Error, string>({
    mutationFn: cancelExecution,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WORKFLOWS_QUERY_KEY });
    },
  });
}
