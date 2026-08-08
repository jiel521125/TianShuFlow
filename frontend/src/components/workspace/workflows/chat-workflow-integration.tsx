'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { WorkflowSelector } from './workflow-selector';
import {
  WorkflowExecutionDisplay,
  useWorkflowExecution,
  type WorkflowExecutionState,
} from './workflow-execution-display';
import { useExecuteWorkflow } from '@/core/workflows/hooks';
import type { Workflow } from '@/core/workflows/types';

interface ChatWorkflowIntegrationProps {
  threadId: string;
  className?: string;
  onWorkflowResult?: (result: unknown) => void;
}

export function ChatWorkflowIntegration({
  threadId,
  className = '',
  onWorkflowResult,
}: ChatWorkflowIntegrationProps) {
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const { execute } = useExecuteWorkflow();
  const {
    executionState,
    isExecuting,
    startExecution,
    addEvent,
    reset,
    setIsExecuting,
  } = useWorkflowExecution();

  const handleSelectWorkflow = useCallback((workflow: Workflow | null) => {
    setSelectedWorkflow(workflow);
    if (workflow) {
      toast.success(`已选择工作流: ${workflow.name}`);
    }
  }, []);

  const executeSelectedWorkflow = useCallback(async (userMessage: string) => {
    if (!selectedWorkflow) return null;

    const executionId = startExecution(selectedWorkflow.id, selectedWorkflow.name || '工作流');

    try {
      await execute(selectedWorkflow.id, {
        inputs: {
          message: userMessage,
          user_input: userMessage,
          query: userMessage,
        },
      }, (event) => {
        addEvent({
          event_type: event.event_type,
          data: event.data as WorkflowExecutionState['events'][0]['data'],
          execution_id: event.data.execution_id as string,
          timestamp: Date.now(),
        });
      });

      setIsExecuting(false);
    } catch (error) {
      setIsExecuting(false);
      toast.error(error instanceof Error ? error.message : '工作流执行失败');
    }
  }, [selectedWorkflow, execute, startExecution, addEvent, setIsExecuting]);

  const handleClear = useCallback(() => {
    reset();
  }, [reset]);

  return {
    selectedWorkflow,
    isExecuting,
    executionState,
    executeSelectedWorkflow,
    handleClear,
    WorkflowSelector: (
      <WorkflowSelector
        selectedWorkflowId={selectedWorkflow?.id}
        onSelect={handleSelectWorkflow}
        className={className}
      />
    ),
    ExecutionDisplay: executionState && (
      <WorkflowExecutionDisplay
        state={executionState}
        onComplete={(output) => {
          toast.success('工作流执行完成');
          onWorkflowResult?.(output);
        }}
      />
    ),
  };
}

// Custom hook for chat-workflow integration
export function useChatWorkflowIntegration(threadId: string) {
  const integration = ChatWorkflowIntegration({ threadId });
  
  return {
    selectedWorkflow: integration.selectedWorkflow,
    isExecuting: integration.isExecuting,
    executionState: integration.executionState,
    executeWorkflow: integration.executeSelectedWorkflow,
    clearExecution: integration.handleClear,
    WorkflowSelector: integration.WorkflowSelector,
    ExecutionDisplay: integration.ExecutionDisplay,
  };
}