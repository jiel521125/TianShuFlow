/**
 * Workflow API client for frontend-backend communication.
 */

import { fetch } from '@/core/api/fetcher';
import { getBackendBaseURL } from '@/core/config';
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

export async function listWorkflows(
  search = '',
  offset = 0,
  limit = 20,
): Promise<WorkflowListResponse> {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  params.set('offset', String(offset));
  params.set('limit', String(limit));

  const res = await fetch(`${getBackendBaseURL()}/api/workflows?${params.toString()}`);
  if (!res.ok) throw new Error(`Failed to list workflows: ${res.statusText}`);
  return res.json() as Promise<WorkflowListResponse>;
}

export async function getWorkflow(id: string): Promise<Workflow> {
  const res = await fetch(`${getBackendBaseURL()}/api/workflows/${id}`);
  if (!res.ok) throw new Error(`Workflow '${id}' not found`);
  return res.json() as Promise<Workflow>;
}

export async function createWorkflow(
  request: WorkflowCreateRequest,
): Promise<Workflow> {
  const res = await fetch(`${getBackendBaseURL()}/api/workflows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = err.detail;
    if (typeof detail === 'object' && detail !== null && 'errors' in detail) {
      throw new Error(JSON.stringify(detail));
    }
    throw new Error(`Failed to create workflow: ${res.statusText}`);
  }
  return res.json() as Promise<Workflow>;
}

export async function updateWorkflow(
  id: string,
  request: WorkflowUpdateRequest,
): Promise<Workflow> {
  const res = await fetch(`${getBackendBaseURL()}/api/workflows/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(
      `Failed to update workflow: ${JSON.stringify(err.detail ?? res.statusText)}`,
    );
  }
  return res.json() as Promise<Workflow>;
}

export async function deleteWorkflow(id: string): Promise<void> {
  const res = await fetch(`${getBackendBaseURL()}/api/workflows/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete workflow: ${res.statusText}`);
}

export async function copyWorkflow(
  id: string,
  request?: WorkflowCopyRequest,
): Promise<Workflow> {
  const res = await fetch(`${getBackendBaseURL()}/api/workflows/${id}/copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request ?? {}),
  });
  if (!res.ok) throw new Error(`Failed to copy workflow: ${res.statusText}`);
  return res.json() as Promise<Workflow>;
}

export async function validateWorkflow(
  definition: WorkflowCreateRequest['definition'],
): Promise<ValidationResult> {
  const res = await fetch(`${getBackendBaseURL()}/api/workflows/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ definition }),
  });
  if (!res.ok) throw new Error(`Validation failed: ${res.statusText}`);
  return res.json() as Promise<ValidationResult>;
}

export async function executeWorkflow(
  id: string,
  request: WorkflowExecuteRequest,
): Promise<Response> {
  return fetch(`${getBackendBaseURL()}/api/workflows/${id}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
}

/**
 * Execute a workflow from the chat interface.
 * The user's chat message becomes the input to the workflow,
 * and execution events are streamed back via SSE.
 */
export async function executeWorkflowFromChat(
  workflowId: string,
  message: string,
  threadId: string,
): Promise<Response> {
  return fetch(
    `${getBackendBaseURL()}/api/chat/workflows/${workflowId}/execute`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, thread_id: threadId }),
    },
  );
}

export async function listExecutions(
  workflowId: string,
  offset = 0,
  limit = 20,
): Promise<WorkflowExecutionListResponse> {
  const params = new URLSearchParams();
  params.set('offset', String(offset));
  params.set('limit', String(limit));
  const res = await fetch(
    `${getBackendBaseURL()}/api/workflows/${workflowId}/executions?${params.toString()}`,
  );
  if (!res.ok) throw new Error(`Failed to list executions: ${res.statusText}`);
  return res.json() as Promise<WorkflowExecutionListResponse>;
}

export async function getExecution(
  executionId: string,
): Promise<WorkflowExecutionDetail> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/workflows/executions/${executionId}`,
  );
  if (!res.ok) throw new Error(`Execution '${executionId}' not found`);
  return res.json() as Promise<WorkflowExecutionDetail>;
}

export async function cancelExecution(
  executionId: string,
): Promise<WorkflowExecution> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/workflows/executions/${executionId}/cancel`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(`Failed to cancel execution: ${res.statusText}`);
  return res.json() as Promise<WorkflowExecution>;
}
