'use client';

import { useState, useEffect, useRef } from 'react';
import {
  BotIcon,
  Code2Icon,
  SendIcon,
  FileIcon,
  GitBranchIcon,
  Loader2Icon,
  CheckCircleIcon,
  XCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

export interface WorkflowExecutionEvent {
  event_type: string;
  data: {
    execution_id?: string;
    workflow_id?: string;
    node_id?: string;
    node_type?: string;
    success?: boolean;
    output?: unknown;
    error?: string;
    duration_ms?: number;
    results?: Record<string, unknown>;
    node_count?: number;
    execution_steps?: number;
  };
  execution_id?: string;
  timestamp?: number;
}

export interface WorkflowExecutionState {
  executionId: string;
  workflowId: string;
  workflowName?: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  events: WorkflowExecutionEvent[];
  currentNodeId?: string;
  finalOutput?: unknown;
  errorMessage?: string;
}

interface WorkflowExecutionDisplayProps {
  state: WorkflowExecutionState;
  onComplete?: (output: unknown) => void;
}

const nodeTypeIcons: Record<string, typeof BotIcon> = {
  agent: BotIcon,
  code: Code2Icon,
  input: SendIcon,
  output: FileIcon,
  condition: GitBranchIcon,
};

const nodeTypeColors: Record<string, string> = {
  agent: 'text-indigo-500 bg-indigo-50',
  code: 'text-emerald-500 bg-emerald-50',
  input: 'text-amber-500 bg-amber-50',
  output: 'text-rose-500 bg-rose-50',
  condition: 'text-violet-500 bg-violet-50',
};

const nodeTypeLabels: Record<string, string> = {
  agent: 'Agent',
  code: 'Code',
  input: 'Input',
  output: 'Output',
  condition: 'Condition',
};

export function WorkflowExecutionDisplay({
  state,
  onComplete,
}: WorkflowExecutionDisplayProps) {
  const [expanded, setExpanded] = useState(true);
  const [completedNotified, setCompletedNotified] = useState(false);
  const eventsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.events.length]);

  useEffect(() => {
    if (state.status === 'completed' && !completedNotified) {
      setCompletedNotified(true);
      if (onComplete) {
        onComplete(state.finalOutput);
      }
    }
  }, [state.status, state.finalOutput, completedNotified, onComplete]);

  const statusConfig = {
    running: {
      icon: Loader2Icon,
      label: '执行中...',
      className: 'text-blue-600 bg-blue-50 border-blue-200',
      iconAnimate: 'animate-spin',
    },
    completed: {
      icon: CheckCircleIcon,
      label: '执行完成',
      className: 'text-green-600 bg-green-50 border-green-200',
      iconAnimate: '',
    },
    failed: {
      icon: XCircleIcon,
      label: '执行失败',
      className: 'text-red-600 bg-red-50 border-red-200',
      iconAnimate: '',
    },
    cancelled: {
      icon: XCircleIcon,
      label: '已取消',
      className: 'text-gray-600 bg-gray-50 border-gray-200',
      iconAnimate: '',
    },
  };

  const config = statusConfig[state.status];
  const StatusIcon = config.icon;

  const getNodeStatus = (nodeId: string): 'pending' | 'running' | 'completed' | 'failed' => {
    if (state.currentNodeId === nodeId) return 'running';
    const completedEvent = state.events.find(
      (e) =>
        (e.event_type === 'node_completed' || e.event_type === 'node_failed') &&
        e.data.node_id === nodeId,
    );
    if (completedEvent) {
      return completedEvent.event_type === 'node_completed' ? 'completed' : 'failed';
    }
    return 'pending';
  };

  const startedNodes = new Set(
    state.events.filter((e) => e.event_type === 'node_started').map((e) => e.data.node_id),
  );
  const completedNodes = new Set(
    state.events
      .filter((e) => e.event_type === 'node_completed')
      .map((e) => e.data.node_id),
  );

  const formatOutput = (output: unknown): string => {
    if (output === null || output === undefined) return '';
    if (typeof output === 'string') return output;
    try {
      return JSON.stringify(output, null, 2);
    } catch {
      return String(output);
    }
  };

  const renderNodeOutput = (event: WorkflowExecutionEvent) => {
    if (!event.data.output) return null;
    const output = event.data.output;
    const formatted = formatOutput(output);
    if (formatted.length > 200) {
      return (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700">
            查看输出 ({formatted.length} chars)
          </summary>
          <pre className="mt-1 max-h-[200px] overflow-auto rounded bg-gray-50 p-2 text-xs">
            {formatted}
          </pre>
        </details>
      );
    }
    return (
      <pre className="mt-1 max-h-[100px] overflow-auto rounded bg-gray-50 p-2 text-xs">
        {formatted}
      </pre>
    );
  };

  const renderEvent = (event: WorkflowExecutionEvent, index: number) => {
    const nodeId = event.data.node_id;
    const nodeType = event.data.node_type;
    const Icon = nodeType ? nodeTypeIcons[nodeType] || BotIcon : BotIcon;
    const colorClass = nodeType ? nodeTypeColors[nodeType] || 'text-gray-500 bg-gray-50' : '';
    const label = nodeType ? nodeTypeLabels[nodeType] || nodeType : '';

    switch (event.event_type) {
      case 'workflow_started':
        return (
          <div key={index} className="flex items-center gap-2 py-1">
            <div className="flex size-6 items-center justify-center rounded bg-blue-100">
              <Loader2Icon className="size-3 animate-spin text-blue-600" />
            </div>
            <span className="text-sm text-gray-600">工作流开始执行</span>
          </div>
        );
      case 'workflow_completed':
        return (
          <div key={index} className="flex items-center gap-2 py-1">
            <div className="flex size-6 items-center justify-center rounded bg-green-100">
              <CheckCircleIcon className="size-3 text-green-600" />
            </div>
            <span className="text-sm font-medium text-green-600">工作流执行完成</span>
            {event.data.duration_ms && (
              <span className="text-xs text-gray-400">
                ({(event.data.duration_ms / 1000).toFixed(2)}s)
              </span>
            )}
          </div>
        );
      case 'workflow_failed':
        return (
          <div key={index} className="flex items-start gap-2 py-1">
            <div className="flex size-6 items-center justify-center rounded bg-red-100">
              <XCircleIcon className="size-3 text-red-600" />
            </div>
            <div>
              <span className="text-sm font-medium text-red-600">工作流执行失败</span>
              {event.data.error && (
                <p className="mt-0.5 text-xs text-red-500">{event.data.error}</p>
              )}
            </div>
          </div>
        );
      case 'node_started':
        return (
          <div key={index} className="flex items-center gap-2 py-1 pl-4">
            <div className={cn('flex size-5 items-center justify-center rounded', colorClass)}>
              <Icon className="size-3" />
            </div>
            <span className="text-sm text-gray-500">
              执行节点: <span className="font-medium">{label}</span>
            </span>
            <Loader2Icon className="size-3 animate-spin text-blue-400" />
          </div>
        );
      case 'node_completed':
        return (
          <div key={index} className="py-1 pl-4">
            <div className="flex items-center gap-2">
              <div className={cn('flex size-5 items-center justify-center rounded', colorClass)}>
                <Icon className="size-3" />
              </div>
              <span className="text-sm text-gray-600">
                节点 <span className="font-medium">{label}</span> 完成
              </span>
              {event.data.duration_ms && (
                <span className="text-xs text-gray-400">
                  ({event.data.duration_ms}ms)
                </span>
              )}
              <CheckCircleIcon className="size-3 text-green-500" />
            </div>
            {renderNodeOutput(event)}
          </div>
        );
      case 'node_failed':
        return (
          <div key={index} className="py-1 pl-4">
            <div className="flex items-start gap-2">
              <div className={cn('flex size-5 items-center justify-center rounded', colorClass)}>
                <Icon className="size-3" />
              </div>
              <div>
                <span className="text-sm text-red-600">
                  节点 <span className="font-medium">{label}</span> 失败
                </span>
                {event.data.error && (
                  <p className="mt-0.5 text-xs text-red-500">{event.data.error}</p>
                )}
              </div>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  const finalOutputDisplay = Boolean(
    state.status === 'completed' && state.finalOutput,
  );

  return (
    <div className="rounded-xl border-2 border-purple-200 bg-gradient-to-br from-purple-50 to-indigo-50 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium',
              config.className,
            )}
          >
            <StatusIcon className={cn('size-3.5', config.iconAnimate)} />
            {config.label}
          </div>
          {state.workflowName && (
            <span className="text-sm font-medium text-gray-700">
              {state.workflowName}
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setExpanded(!expanded)}
          className="h-6 p-1"
        >
          {expanded ? (
            <ChevronUpIcon className="size-4" />
          ) : (
            <ChevronDownIcon className="size-4" />
          )}
        </Button>
      </div>

      {/* Progress bar */}
      {state.status === 'running' && (
        <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-purple-100">
          <div className="h-full animate-pulse bg-gradient-to-r from-purple-400 to-indigo-400 transition-all"
            style={{
              width: `${startedNodes.size > 0 ? (completedNodes.size / startedNodes.size) * 100 : 0}%`,
            }}
          />
        </div>
      )}

      {/* Events timeline */}
      {expanded && (
        <div className="max-h-[300px] space-y-1 overflow-y-auto border-l-2 border-purple-100 pl-4">
          {state.events.map((event, index) => renderEvent(event, index))}
          <div ref={eventsEndRef} />
        </div>
      )}

      {/* Final output */}
      {finalOutputDisplay && (
        <div className="mt-3 rounded-lg border border-green-200 bg-white p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-green-700">
            <CheckCircleIcon className="size-4" />
            工作流最终输出
          </div>
          <pre className="max-h-[150px] overflow-auto rounded bg-gray-50 p-3 text-sm">
            {formatOutput(state.finalOutput)}
          </pre>
        </div>
      )}

      {/* Error display */}
      {state.status === 'failed' && state.errorMessage && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3">
          <div className="flex items-center gap-2 text-sm font-medium text-red-700">
            <XCircleIcon className="size-4" />
            执行失败
          </div>
          <p className="mt-1 text-sm text-red-600">{state.errorMessage}</p>
        </div>
      )}
    </div>
  );
}

// Custom hook for managing workflow execution state
export function useWorkflowExecution() {
  const [executionState, setExecutionState] = useState<WorkflowExecutionState | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  const startExecution = (workflowId: string, workflowName: string) => {
    const executionId = `exec-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setExecutionState({
      executionId,
      workflowId,
      workflowName,
      status: 'running',
      events: [],
    });
    setIsExecuting(true);
    return executionId;
  };

  const addEvent = (event: WorkflowExecutionEvent) => {
    setExecutionState((prev) => {
      if (!prev) return prev;
      const newState = { ...prev, events: [...prev.events, event] };

      if (event.event_type === 'workflow_completed') {
        newState.status = 'completed';
        newState.finalOutput = event.data.results;
      } else if (event.event_type === 'workflow_failed') {
        newState.status = 'failed';
        newState.errorMessage = event.data.error;
      } else if (event.event_type === 'workflow_cancelled') {
        newState.status = 'cancelled';
      } else if (event.event_type === 'node_started') {
        newState.currentNodeId = event.data.node_id;
      }

      return newState;
    });
  };

  const reset = () => {
    setExecutionState(null);
    setIsExecuting(false);
  };

  return {
    executionState,
    isExecuting,
    startExecution,
    addEvent,
    reset,
    setIsExecuting,
  };
}

// SSE event stream handler
export function handleWorkflowSSEEvent(
  eventType: string,
  data: Record<string, unknown>,
): WorkflowExecutionEvent {
  return {
    event_type: eventType,
    data: data as WorkflowExecutionEvent['data'],
    execution_id: data.execution_id as string | undefined,
    timestamp: Date.now(),
  };
}