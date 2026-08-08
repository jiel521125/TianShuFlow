'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeftIcon,
  SaveIcon,
  Loader2Icon,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { WorkflowCanvas } from '@/components/workspace/workflows/workflow-canvas';
import { useI18n } from '@/core/i18n/hooks';
import { useCreateWorkflow } from '@/core/workflows/hooks';
import type { WorkflowDefinition } from '@/core/workflows/types';

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

export default function WorkflowNewPage() {
  const { t } = useI18n();
  const router = useRouter();
  const createMutation = useCreateWorkflow();

  const [name, setName] = useState('New Workflow');
  const [description, setDescription] = useState('');
  const [definition, setDefinition] = useState<WorkflowDefinition>(defaultDefinition());

  const handleSave = useCallback(
    async (def: WorkflowDefinition) => {
      setDefinition(def);
      try {
        const wf = await createMutation.mutateAsync({
          name,
          description,
          definition: def,
        });
        router.push(`/workspace/workflows/${wf.id}`);
      } catch (err) {
        console.error('Create failed:', err);
      }
    },
    [name, description, createMutation, router],
  );

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
            <h1 className="text-xl font-bold">{t.workflow.create}</h1>
          </div>
        </div>
        <Button
          onClick={() => handleSave(definition)}
          disabled={createMutation.isPending}
        >
          {createMutation.isPending ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <SaveIcon className="size-4" />
          )}
          {createMutation.isPending ? 'Creating...' : t.workflow.create}
        </Button>
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
        </div>

        <div className="min-h-0">
          <WorkflowCanvas
            initialDefinition={definition}
            onSave={handleSave}
            height="calc(100vh - 180px)"
          />
        </div>
      </div>
    </div>
  );
}
