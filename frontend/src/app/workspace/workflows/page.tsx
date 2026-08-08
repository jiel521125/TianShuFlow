'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  WorkflowIcon,
  PlusIcon,
  SearchIcon,
  PencilIcon,
  Trash2Icon,
  PlayIcon,
  CopyIcon,
  MoreHorizontalIcon,
  BotIcon,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useI18n } from '@/core/i18n/hooks';
import {
  useWorkflows,
  useDeleteWorkflow,
  useCopyWorkflow,
} from '@/core/workflows/hooks';

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  return d.toLocaleString();
}

export default function WorkflowsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const { data: workflowsData, isLoading } = useWorkflows(search);
  const deleteMutation = useDeleteWorkflow();
  const copyMutation = useCopyWorkflow();

  const workflows = workflowsData?.workflows ?? [];

  const handleDelete = async () => {
    if (!deleteId) return;
    await deleteMutation.mutateAsync(deleteId);
    setDeleteId(null);
  };

  const handleCopy = async (id: string) => {
    await copyMutation.mutateAsync({ id });
  };

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2">
            <WorkflowIcon className="size-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">{t.workflow.title}</h1>
            <p className="text-sm text-muted-foreground">
              {t.workflow.list}
            </p>
          </div>
        </div>
        <Link href="/workspace/workflows/new">
          <Button>
            <PlusIcon className="size-4" />
            {t.workflow.create}
          </Button>
        </Link>
      </div>

      <div className="relative">
        <SearchIcon className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder={t.common.search}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      ) : workflows.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 rounded-lg border border-dashed p-12">
          <WorkflowIcon className="size-12 text-muted-foreground" />
          <div className="text-center">
            <h3 className="text-lg font-medium">{t.workflow.noWorkflows}</h3>
            <p className="text-sm text-muted-foreground">
              {t.workflow.noWorkflowsDescription}
            </p>
          </div>
          <Link href="/workspace/workflows/new">
            <Button>
              <PlusIcon className="size-4" />
              {t.workflow.createFirst}
            </Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {workflows.map((wf) => (
            <Card
              key={wf.id}
              className="group hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => router.push(`/workspace/workflows/${wf.id}`)}
            >
              <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
                <div className="flex items-center gap-2">
                  <BotIcon className="size-4 text-primary" />
                  <CardTitle className="text-sm font-medium line-clamp-1">
                    {wf.name}
                  </CardTitle>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" size="icon" className="size-8 opacity-0 group-hover:opacity-100">
                      <MoreHorizontalIcon className="size-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={(e) => { e.stopPropagation(); router.push(`/workspace/workflows/${wf.id}`); }}>
                      <PencilIcon className="size-4" /> Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleCopy(wf.id); }}>
                      <CopyIcon className="size-4" /> {t.workflow.copy}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={(e) => { e.stopPropagation(); setDeleteId(wf.id); }}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2Icon className="size-4" /> {t.common.delete}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground line-clamp-2 min-h-[2rem]">
                  {wf.description || 'No description'}
                </p>
                <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{wf.definition.nodes.length} nodes</span>
                  <span>{formatDate(wf.updated_at)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!deleteId} onOpenChange={(open) => !open && setDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t.common.delete}</DialogTitle>
            <DialogDescription>
              {t.workflow.deleteConfirm}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteId(null)}>{t.common.cancel}</Button>
            <Button variant="destructive" onClick={handleDelete}>
              {t.common.delete}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
