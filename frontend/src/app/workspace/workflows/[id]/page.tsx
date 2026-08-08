'use client';

import { useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeftIcon,
  SaveIcon,
  PlayIcon,
  Loader2Icon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ZapIcon,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { WorkflowCanvas } from '@/components/workspace/workflows/workflow-canvas';
import { useI18n } from '@/core/i18n/hooks';
import {
  useWorkflow,
  useCreateWorkflow,
  useUpdateWorkflow,
} from '@/core/workflows/hooks';
import { executeWorkflow } from '@/core/workflows/api';
import type {
  WorkflowDefinition,
  Workflow as WorkflowType,
  SSEEvent,
} from '@/core/workflows/types';

function defaultDefinition(): WorkflowDefinition {
  return {
    nodes: [
      {
        id: 'node-input-1',
        type: 'input',
        name: 'Input',
        config: { input_key: 'topic', default_value: '' },
        position: { x: 100, y: 200 },
      },
      {
        id: 'node-agent-1',
        type: 'agent',
        name: 'Researcher Agent',
        config: { agent_name: 'researcher', prompt_template: 'Research: {topic}' },
        position: { x: 400, y: 200 },
      },
      {
        id: 'node-agent-2',
        type: 'agent',
        name: 'Analyst Agent',
        config: { agent_name: 'analyst', prompt_template: 'Analyze: {researcher_output}' },
        position: { x: 700, y: 200 },
      },
      {
        id: 'node-output-1',
        type: 'output',
        name: 'Report Output',
        config: { output_key: 'report' },
        position: { x: 1000, y: 200 },
      },
    ],
    edges: [
      { id: 'edge-1', source: 'node-input-1', target: 'node-agent-1' },
      { id: 'edge-2', source: 'node-agent-1', target: 'node-agent-2' },
      { id: 'edge-3', source: 'node-agent-2', target: 'node-output-1' },
    ],
  };
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const statusMap: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string; icon: typeof ClockIcon }> = {
    pending: { variant: 'outline', label: t.workflow.status.pending, icon: ClockIcon },
    running: { variant: 'secondary', label: t.workflow.status.running, icon: Loader2Icon },
    completed: { variant: 'default', label: t.workflow.status.completed, icon: CheckCircleIcon },
    failed: { variant: 'destructive', label: t.workflow.status.failed, icon: XCircleIcon },
    cancelled: { variant: 'outline', label: t.workflow.status.cancelled, icon: XCircleIcon },
  };
  const info = statusMap[status] ?? statusMap.pending!;
  const Icon = info.icon!;
  return (
    <Badge variant={info.variant} className="gap-1">
      <Icon className="size-3" /> {info.label}
    </Badge>
  );
}

export default function WorkflowDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { t } = useI18n();
  const workflowId = params.id as string;
  const isNew = workflowId === 'new';

  const { data: existingWorkflow, isLoading } = useWorkflow(
    isNew ? '' : workflowId,
  );
  const createMutation = useCreateWorkflow();
  const updateMutation = useUpdateWorkflow();

  const [name, setName] = useState(existingWorkflow?.name ?? 'New Workflow');
  const [description, setDescription] = useState(existingWorkflow?.description ?? '');
  const [definition, setDefinition] = useState<WorkflowDefinition>(
    existingWorkflow?.definition ?? defaultDefinition(),
  );
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionEvents, setExecutionEvents] = useState<SSEEvent[]>([]);

  const handleSave = useCallback(
    async (def: WorkflowDefinition) => {
      setDefinition(def);
      try {
        if (isNew) {
          const wf = await createMutation.mutateAsync({
            name,
            description,
            definition: def,
          });
          router.push(`/workspace/workflows/${wf.id}`);
        } else {
          await updateMutation.mutateAsync({
            id: workflowId,
            request: { name, description, definition: def },
          });
        }
      } catch (err) {
        console.error('Save failed:', err);
      }
    },
    [isNew, name, description, createMutation, updateMutation, workflowId, router],
  );

  const handleExecute = useCallback(
    async (def: WorkflowDefinition) => {
      setDefinition(def);
      if (isNew) {
        const wf = await createMutation.mutateAsync({
          name,
          description,
          definition: def,
        });
        router.push(`/workspace/workflows/${wf.id}`);
        return;
      }

      setIsExecuting(true);
      setExecutionEvents([]);

      try {
        const response = await executeWorkflow(workflowId, {
          inputs: { topic: 'Test topic' },
        });

        if (!response.body) {
          throw new Error('No response body');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;
            const dataStr = trimmed.slice(6);
            if (dataStr === '[DONE]') continue;

            try {
              const event = JSON.parse(dataStr) as SSEEvent;
              setExecutionEvents((prev) => [...prev, event]);
            } catch {
              // ignore parse errors
            }
          }
        }
      } catch (err) {
        console.error('Execution failed:', err);
      } finally {
        setIsExecuting(false);
      }
    },
    [isNew, name, description, workflowId, createMutation, router],
  );

  if (isLoading && !isNew) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2Icon className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/workspace/workflows">
            <Button variant="ghost" size="icon">
              <ArrowLeftIcon className="size-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-xl font-bold">
              {isNew ? t.workflow.create : existingWorkflow?.name ?? t.workflow.title}
            </h1>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => handleSave(definition)}
            disabled={createMutation.isPending || updateMutation.isPending}
          >
            <SaveIcon className="size-4" />
            {createMutation.isPending || updateMutation.isPending ? 'Saving...' : t.common.save}
          </Button>
          {!isNew && (
            <Button
              onClick={() => handleExecute(definition)}
              disabled={isExecuting}
            >
              {isExecuting ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <PlayIcon className="size-4" />
              )}
              {isExecuting ? 'Running...' : t.workflow.execute}
            </Button>
          )}
        </div>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Workflow Info</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">
                  Name
                </label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t.workflow.namePlaceholder}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">
                  Description
                </label>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t.workflow.descriptionPlaceholder}
                  rows={3}
                />
              </div>
            </CardContent>
          </Card>

          {isExecuting || executionEvents.length > 0 ? (
            <Card className="flex-1 overflow-hidden">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <ZapIcon className="size-4 text-yellow-500" />
                  {t.workflow.execution}
                  {isExecuting && (
                    <Badge variant="secondary">
                      <Loader2Icon className="size-3 animate-spin" />
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <ScrollArea className="h-full">
                  <div className="p-4 space-y-2">
                    {executionEvents.map((event, idx) => (
                      <div
                        key={idx}
                        className="rounded border p-2 text-xs font-mono bg-muted/30"
                      >
                        <div className="font-semibold text-primary">
                          {event.event}
                        </div>
                        <pre className="mt-1 whitespace-pre-wrap break-all text-[10px]">
                          {JSON.stringify(event.data, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="min-h-0">
          <WorkflowCanvas
            initialDefinition={definition}
            workflowId={!isNew ? workflowId : undefined}
            onSave={handleSave}
            onExecute={!isNew ? handleExecute : undefined}
            height="calc(100vh - 180px)"
          />
        </div>
      </div>
    </div>
  );
}
