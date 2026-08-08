'use client';

import { useMemo } from 'react';
import { BotIcon, WorkflowIcon } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useListWorkflows } from '@/core/workflows/hooks';
import type { Workflow } from '@/core/workflows/types';

interface WorkflowSelectorProps {
  selectedWorkflowId?: string | null;
  onSelect: (workflow: Workflow | null) => void;
  className?: string;
}

export function WorkflowSelector({
  selectedWorkflowId,
  onSelect,
  className = '',
}: WorkflowSelectorProps) {
  const { data, isLoading } = useListWorkflows();
  const workflows = data?.workflows;

  const selectedWorkflow = useMemo(
    () => workflows?.find((w) => w.id === selectedWorkflowId) ?? null,
    [workflows, selectedWorkflowId],
  );

  if (isLoading) {
    return (
      <div
        className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm text-gray-500 ${className}`}
      >
        <WorkflowIcon className="size-3.5 animate-spin" />
        Loading...
      </div>
    );
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={`gap-1.5 ${selectedWorkflow ? 'border-purple-300 bg-purple-50 text-purple-700' : ''} ${className}`}
        >
          <WorkflowIcon className="size-3.5" />
          {selectedWorkflow ? (
            <>
              <span className="max-w-[120px] truncate">{selectedWorkflow.name}</span>
            </>
          ) : (
            '工作流'
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>选择工作流</DialogTitle>
          <DialogDescription>
            选择一个工作流来处理您的消息，工作流将按照定义的节点顺序执行
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-4">
          {selectedWorkflow && (
            <div className="flex items-center gap-2 rounded-lg border border-purple-200 bg-purple-50 p-3">
              <WorkflowIcon className="size-4 text-purple-600" />
              <div className="flex-1">
                <div className="text-sm font-medium text-purple-900">
                  当前选择: {selectedWorkflow.name}
                </div>
                <div className="text-xs text-purple-600">
                  {selectedWorkflow.description || '无描述'}
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onSelect(null)}
              >
                清除
              </Button>
            </div>
          )}
          <div className="max-h-[300px] space-y-2 overflow-y-auto">
            {workflows && workflows.length > 0 ? (
              workflows.map((workflow) => (
                <button
                  key={workflow.id}
                  onClick={() => {
                    onSelect(workflow);
                  }}
                  className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-all hover:border-purple-300 hover:bg-purple-50 ${
                    selectedWorkflowId === workflow.id
                      ? 'border-purple-400 bg-purple-50'
                      : 'border-gray-200 bg-white'
                  }`}
                >
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-purple-100 to-indigo-100">
                    <BotIcon className="size-5 text-purple-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-sm font-medium">{workflow.name}</div>
                    <div className="truncate text-xs text-gray-500">
                      {workflow.description || '无描述'}
                    </div>
                  </div>
                  <div className="text-xs text-gray-400">
                    {workflow.definition?.nodes?.length ?? 0} 节点
                  </div>
                </button>
              ))
            ) : (
              <div className="py-8 text-center">
                <WorkflowIcon className="mx-auto mb-2 size-8 text-gray-300" />
                <p className="text-sm text-gray-500">暂无工作流</p>
                <a
                  href="/workspace/workflows"
                  className="mt-2 text-xs text-purple-600 hover:underline"
                >
                  创建一个工作流 →
                </a>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}