/**
 * Workflow-related type definitions for the frontend.
 */

export type NodeType = 'agent' | 'code' | 'input' | 'output' | 'condition';

export interface WorkflowNodePosition {
  x: number;
  y: number;
}

export interface WorkflowNode {
  id: string;
  type: NodeType;
  name: string;
  config: Record<string, unknown>;
  input_mapping?: Record<string, unknown>;
  position?: WorkflowNodePosition;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
}

export interface WorkflowDefinition {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  definition: WorkflowDefinition;
  input_schema: Record<string, unknown>;
  output_schema?: Record<string, unknown> | null;
  is_template: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowListResponse {
  total: number;
  workflows: Workflow[];
}

export interface WorkflowCreateRequest {
  name: string;
  description?: string;
  definition: WorkflowDefinition;
  input_schema?: Record<string, unknown> | null;
}

export interface WorkflowUpdateRequest {
  name?: string | null;
  description?: string | null;
  definition?: WorkflowDefinition | null;
  input_schema?: Record<string, unknown> | null;
}

export interface ValidationErrorInfo {
  code: string;
  message: string;
  node_id?: string | null;
  edge_id?: string | null;
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationErrorInfo[];
  warnings: string[];
  topology?: {
    node_count: number;
    edge_count: number;
    has_cycle: boolean;
    entry_nodes: string[];
    exit_nodes: string[];
    parallel_groups: string[][];
  } | null;
}

export interface WorkflowExecuteRequest {
  inputs: Record<string, unknown>;
}

export interface WorkflowCopyRequest {
  name?: string;
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  inputs: Record<string, unknown>;
  outputs?: Record<string, unknown> | null;
  error_message: string;
  started_at: string;
  completed_at?: string | null;
}

export interface WorkflowExecutionStep {
  id: string;
  node_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  input_data?: Record<string, unknown> | null;
  output_data?: Record<string, unknown> | null;
  error_message: string;
  duration_ms: number;
  started_at: string;
  completed_at?: string | null;
}

export interface WorkflowExecutionDetail extends WorkflowExecution {
  steps: WorkflowExecutionStep[];
}

export interface WorkflowExecutionListResponse {
  total: number;
  executions: WorkflowExecution[];
}

export type SSEEventType =
  | 'workflow_started'
  | 'node_started'
  | 'node_completed'
  | 'node_failed'
  | 'workflow_completed'
  | 'workflow_failed'
  | 'workflow_cancelled';

export interface SSEEvent {
  event: SSEEventType;
  data: Record<string, unknown>;
}
