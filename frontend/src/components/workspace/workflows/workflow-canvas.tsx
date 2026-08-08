'use client';

import '@xyflow/react/dist/style.css';

import { useCallback, useRef, useState, useMemo, useEffect } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type NodeTypes,
} from '@xyflow/react';
import {
  BotIcon,
  Code2Icon,
  SendIcon,
  FileIcon,
  GitBranchIcon,
  PlayIcon,
  SaveIcon,
  Trash2Icon,
  Settings2Icon,
  ChevronDownIcon,
  ChevronRightIcon,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useI18n } from '@/core/i18n/hooks';
import { useAgents } from '@/core/agents/hooks';
import type {
  WorkflowDefinition,
  WorkflowNode,
  NodeType,
} from '@/core/workflows/types';

type WorkflowNodeData = {
  nodeType: NodeType;
  config: Record<string, unknown>;
  label: string;
};

const nodeTypeMeta: Record<
  NodeType,
  { label: string; color: string; icon: typeof BotIcon; description: string }
> = {
  agent: { label: 'Agent', color: '#6366f1', icon: BotIcon, description: 'AI Agent 处理节点' },
  code: { label: 'Code', color: '#10b981', icon: Code2Icon, description: 'Python 代码执行' },
  input: { label: 'Input', color: '#f59e0b', icon: SendIcon, description: '输入数据节点' },
  output: { label: 'Output', color: '#ef4444', icon: FileIcon, description: '输出结果节点' },
  condition: { label: 'Condition', color: '#8b5cf6', icon: GitBranchIcon, description: '条件判断节点' },
};

function createNode(type: NodeType, position?: { x: number; y: number }): Node<WorkflowNodeData> {
  const id = `node-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const meta = nodeTypeMeta[type];
  const defaultConfigs: Record<NodeType, Record<string, unknown>> = {
    agent: { agent_name: '', system_prompt: '', model: 'minimax-m3' },
    code: { code: 'output = {"result": "Hello World"}' },
    input: { input_key: 'input', default_value: '' },
    output: { output_key: 'output', description: '' },
    condition: { expression: 'inputs.get("value", 0) > 0', true_branch: '', false_branch: '' },
  };
  return {
    id,
    type: 'workflowNode',
    position: position ?? { x: 250, y: 200 },
    data: {
      nodeType: type,
      config: defaultConfigs[type],
      label: `${meta.label} Node`,
    },
  };
}

function nodeToWorkflow(node: Node<WorkflowNodeData>): WorkflowNode {
  return {
    id: node.id,
    type: node.data.nodeType,
    name: node.data.label,
    config: node.data.config,
    position: node.position ? { x: node.position.x, y: node.position.y } : undefined,
  };
}

function getNodeSummary(data: WorkflowNodeData): string {
  const config = data.config;
  switch (data.nodeType) {
    case 'agent':
      return config.agent_name ? `Agent: ${String(config.agent_name)}` : '未配置 Agent';
    case 'code':
      const code = String(config.code || '');
      return code ? code.slice(0, 40) + (code.length > 40 ? '...' : '') : '未编写代码';
    case 'input':
      const key = String(config.input_key || 'input');
      return `输入: ${key}`;
    case 'output':
      const outKey = String(config.output_key || 'output');
      return `输出: ${outKey}`;
    case 'condition':
      const expr = String(config.expression || '');
      return expr ? `条件: ${expr.slice(0, 30)}` : '未设置条件';
    default:
      return '';
  }
}

/**
 * Custom React Flow node component for workflow nodes.
 * Defined at module level (not inside the component) to avoid
 * the React Flow warning about recreating nodeTypes on each render.
 */
function WorkflowNodeComponent({ data, selected }: { data: WorkflowNodeData; selected: boolean }) {
  const meta = nodeTypeMeta[data.nodeType];
  const Icon = meta.icon;
  const isInput = data.nodeType === 'input';
  const isOutput = data.nodeType === 'output';
  const summary = getNodeSummary(data);
  return (
    <div
      className={`rounded-xl border-2 bg-white p-3 shadow-md transition-all ${
        selected ? 'shadow-lg ring-2 ring-offset-1' : 'hover:shadow-lg'
      }`}
      style={{
        minWidth: 180,
        borderColor: selected ? meta.color : undefined,
        ['--tw-ring-color' as string]: meta.color,
      }}
    >
      {!isInput && (
        <Handle
          type="target"
          position={Position.Left}
          style={{ width: 10, height: 10, background: meta.color, border: '2px solid white' }}
        />
      )}
      <div className="flex items-center gap-2">
        <div
          className="flex size-7 items-center justify-center rounded-lg"
          style={{ backgroundColor: `${meta.color}20` }}
        >
          <Icon className="size-4" style={{ color: meta.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold truncate">{data.label}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide">{meta.label}</div>
        </div>
      </div>
      {summary && (
        <div className="mt-2 rounded-md bg-gray-50 px-2 py-1 text-xs text-gray-600 truncate border border-gray-100">
          {summary}
        </div>
      )}
      {!isOutput && (
        <Handle
          type="source"
          position={Position.Right}
          style={{ width: 10, height: 10, background: meta.color, border: '2px solid white' }}
        />
      )}
    </div>
  );
}

/** nodeTypes defined at module level — stable reference across renders. */
const nodeTypesConfig: NodeTypes = {
  workflowNode: WorkflowNodeComponent,
};

export interface WorkflowCanvasProps {
  initialDefinition?: WorkflowDefinition;
  workflowId?: string;
  onSave: (definition: WorkflowDefinition) => void;
  /**
   * Called when the canvas's internal Execute button is pressed.
   * The page-level handler may choose to stream execution events into
   * the canvas via `initialExecutionEvents`.
   */
  onExecute?: (definition: WorkflowDefinition) => Promise<void> | void;
  readOnly?: boolean;
  height?: string;
}

/** A single SSE event from the workflow execution API. */
export interface ExecutionEvent {
  event: string;
  data: Record<string, unknown>;
}

function WorkflowCanvasInner({
  initialDefinition,
  workflowId,
  onSave,
  onExecute,
  readOnly = false,
  height = '600px',
}: WorkflowCanvasProps) {
  const { t } = useI18n();
  const { agents } = useAgents();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { fitView } = useReactFlow();
  const [configOpen, setConfigOpen] = useState(true);

  // Right-panel tab: 'config' shows node properties, 'execution' shows
  // step-by-step workflow execution log with real-time streaming.
  const [rightTab, setRightTab] = useState<'config' | 'execution'>('config');
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionEvents, setExecutionEvents] = useState<ExecutionEvent[]>([]);
  const [executionError, setExecutionError] = useState<string | null>(null);

  const initialNodes: Node<WorkflowNodeData>[] = useMemo(() => {
    if (!initialDefinition) return [];
    return initialDefinition.nodes.map((n) => ({
      id: n.id,
      type: 'workflowNode',
      position: n.position ? { x: n.position.x, y: n.position.y } : { x: 0, y: 0 },
      data: {
        nodeType: n.type,
        config: n.config || {},
        label: n.name,
      },
    }));
  }, [initialDefinition]);

  const initialEdges: Edge[] = useMemo(() => {
    if (!initialDefinition) return [];
    return initialDefinition.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label ?? undefined,
    }));
  }, [initialDefinition]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNode, setSelectedNode] = useState<Node<WorkflowNodeData> | null>(null);

  /**
   * Auto-backfill SOUL.md for any Agent node that references a known agent
   * but has an empty system_prompt. Runs whenever the agent registry changes
   * (initial load, agent created/updated). Preserves any user customizations
   * already entered in the node config.
   */
  useEffect(() => {
    if (agents.length === 0) return;
    setNodes((prevNodes) => {
      let mutated = false;
      const next = prevNodes.map((n) => {
        if (n.data.nodeType !== 'agent') return n;
        const cfg = n.data.config as Record<string, unknown>;
        const agentName = cfg.agent_name as string | undefined;
        if (!agentName) return n;
        const agent = agents.find((a) => a.name === agentName);
        if (!agent) return n;
        const currentSoul = (cfg.system_prompt as string | undefined) || '';
        if (currentSoul) return n; // user already has SOUL — don't overwrite
        if (!agent.soul) return n; // agent has no SOUL either
        mutated = true;
        return {
          ...n,
          data: {
            ...n.data,
            config: {
              ...cfg,
              system_prompt: agent.soul,
              model: agent.model || cfg.model || 'minimax-m3',
            },
          },
        };
      });
      return mutated ? next : prevNodes;
    });
  }, [agents, setNodes]);

  const updateNodeConfig = useCallback(
    (nodeId: string, config: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, config } } : n,
        ),
      );
      setSelectedNode((prev) =>
        prev && prev.id === nodeId
          ? { ...prev, data: { ...prev.data, config } }
          : prev,
      );
    },
    [setNodes],
  );

  const updateNodeLabel = useCallback(
    (nodeId: string, label: string) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, label } } : n,
        ),
      );
      setSelectedNode((prev) =>
        prev && prev.id === nodeId
          ? { ...prev, data: { ...prev.data, label } }
          : prev,
      );
    },
    [setNodes],
  );

  const onConnect = useCallback(
    (params: Connection | Edge) =>
      setEdges((eds) => addEdge({ ...params, type: 'smoothstep' }, eds)),
    [setEdges],
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData('application/reactflow') as NodeType;
      if (!type) return;

      const bounds = reactFlowWrapper.current?.getBoundingClientRect();
      if (!bounds) return;

      const position = {
        x: event.clientX - bounds.left - 80,
        y: event.clientY - bounds.top - 30,
      };

      const newNode = createNode(type, position);
      setNodes((nds) => nds.concat(newNode));
      setSelectedNode(newNode);
    },
    [setNodes],
  );

  const handleAddNode = useCallback(
    (type: NodeType) => {
      const newNode = createNode(type);
      setNodes((nds) => nds.concat(newNode));
      setSelectedNode(newNode);
      setConfigOpen(true);
      setTimeout(() => fitView({ maxZoom: 1.5 }), 50);
    },
    [setNodes, fitView],
  );

  const handleDeleteSelected = useCallback(() => {
    if (!selectedNode) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
    setEdges((eds) =>
      eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id),
    );
    setSelectedNode(null);
  }, [selectedNode, setNodes, setEdges]);

  const handleSave = useCallback(() => {
    const definition: WorkflowDefinition = {
      nodes: nodes.map(nodeToWorkflow),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: typeof e.label === 'string' ? e.label : undefined,
      })),
    };
    onSave(definition);
  }, [nodes, edges, onSave]);

  const handleExecute = useCallback(async () => {
    const definition: WorkflowDefinition = {
      nodes: nodes.map(nodeToWorkflow),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: typeof e.label === 'string' ? e.label : undefined,
      })),
    };

    // Reset execution state and switch to the execution tab.
    setExecutionEvents([]);
    setExecutionError(null);
    setRightTab('execution');

    // If a parent-provided handler exists, defer execution to it (used
    // when the page-level component owns the workflow API call).
    if (onExecute) {
      try {
        await onExecute(definition);
      } catch (err) {
        setExecutionError(err instanceof Error ? err.message : String(err));
      }
      return;
    }

    // Otherwise, run the execution inline using the workflow API.
    if (!workflowId) {
      setExecutionError('请先保存工作流后再执行。');
      return;
    }

    setIsExecuting(true);
    try {
      const { executeWorkflow } = await import('@/core/workflows/api');
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
            const parsed = JSON.parse(dataStr);
            const eventType = parsed.event ?? parsed.event_type ?? 'message';
            const eventData = parsed.data ?? parsed;
            setExecutionEvents((prev) => [
              ...prev,
              { event: String(eventType), data: eventData as Record<string, unknown> },
            ]);
          } catch {
            // ignore parse errors
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setExecutionError(msg);
      console.error('Workflow execution failed:', err);
    } finally {
      setIsExecuting(false);
    }
  }, [nodes, edges, onExecute, workflowId]);

  // nodeTypesConfig is defined at module level (see above) to keep a
  // stable reference and avoid React Flow's "new nodeTypes object" warning.

  const nodeTypeOptions: NodeType[] = ['agent', 'code', 'input', 'output', 'condition'];

  const renderNodeConfig = () => {
    if (!selectedNode) return null;
    const { data } = selectedNode;
    const config = data.config as Record<string, string>;
    const meta = nodeTypeMeta[data.nodeType];

    const baseInput = "w-full rounded-md border bg-background px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100";
    const labelClass = "mb-1.5 block text-xs font-medium text-muted-foreground";

    return (
      <div className="space-y-4">
        {/* Label */}
        <div>
          <label className={labelClass}>节点名称</label>
          <input
            className={baseInput}
            value={data.label}
            onChange={(e) => updateNodeLabel(selectedNode.id, e.target.value)}
            placeholder="输入节点名称"
          />
        </div>

        {/* Type-specific config */}
        {data.nodeType === 'agent' && (
          <>
            <div>
              <label className={labelClass}>选择 Agent</label>
              <select
                className={baseInput}
                value={config.agent_name || ''}
                onChange={(e) => {
                  const selectedAgent = agents.find((a) => a.name === e.target.value);
                  updateNodeConfig(selectedNode.id, {
                    ...config,
                    agent_name: e.target.value,
                    // Always sync SOUL and model from the agent registry on selection.
                    // If the user later customizes them here, those overrides stay.
                    system_prompt: selectedAgent?.soul || config.system_prompt || '',
                    model: selectedAgent?.model || config.model || 'minimax-m3',
                  });
                }}
              >
                <option value="">— 选择已有 Agent —</option>
                {agents.map((agent) => (
                  <option key={agent.name} value={agent.name}>
                    {agent.name}{agent.description ? ` — ${agent.description}` : ''}
                  </option>
                ))}
              </select>
              {agents.length === 0 && (
                <p className="mt-1 text-[10px] text-amber-600">
                  暂无可用 Agent，请先在智能体管理中创建
                </p>
              )}
              <a
                href="/workspace/agents/new"
                className="mt-1 inline-block text-[10px] text-blue-600 hover:underline"
              >
                + 创建新 Agent →
              </a>
            </div>

            <div>
              <div className="mb-1 flex items-center justify-between">
                <label className={labelClass}>系统提示词 (SOUL.md)</label>
                <span className="text-muted-foreground text-[10px] tabular-nums">
                  {(config.system_prompt || '').length} 字符
                </span>
              </div>
              <textarea
                className="h-64 w-full resize-y rounded-md border bg-background px-3 py-2 font-mono text-xs leading-relaxed focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                value={config.system_prompt || ''}
                onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, system_prompt: e.target.value })}
                placeholder={
                  config.agent_name
                    ? '该 Agent 在 SOUL.md 中还没有内容，请到智能体管理中配置。'
                    : '请先选择 Agent，或直接在此填写系统提示词。'
                }
                spellCheck={false}
              />
              <div className="mt-1 flex items-center justify-between gap-2">
                <p className="text-[10px] text-gray-400">
                  {config.agent_name
                    ? '已从智能体管理同步 SOUL.md，可在此微调覆盖'
                    : 'SOUL.md 定义 Agent 的角色、行为规范和输出格式'}
                </p>
                {config.agent_name && (
                  <button
                    type="button"
                    className="text-[10px] text-blue-600 hover:underline"
                    onClick={() => {
                      const selectedAgent = agents.find((a) => a.name === config.agent_name);
                      if (selectedAgent?.soul) {
                        updateNodeConfig(selectedNode.id, {
                          ...config,
                          system_prompt: selectedAgent.soul,
                        });
                      }
                    }}
                  >
                    ↺ 从智能体管理重新同步
                  </button>
                )}
              </div>
            </div>
            <div>
              <label className={labelClass}>模型选择</label>
              <select
                className={baseInput}
                value={config.model || 'minimax-m3'}
                onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, model: e.target.value })}
              >
                <option value="minimax-m3">MiniMax M3</option>
                <option value="deepseek-v4-Flash">DeepSeek V4 Flash</option>
              </select>
            </div>
          </>
        )}

        {data.nodeType === 'code' && (
          <div>
            <label className={labelClass}>Python 代码</label>
            <textarea
              className="h-32 w-full rounded-md border bg-gray-50 px-3 py-2 font-mono text-xs focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              value={config.code || ''}
              onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, code: e.target.value })}
              placeholder="output = {'result': 'Hello World'}"
            />
            <p className="mt-1 text-[10px] text-gray-400">使用 inputs 变量获取输入，output 变量返回结果</p>
          </div>
        )}

        {data.nodeType === 'input' && (
          <>
            <div>
              <label className={labelClass}>输入键名</label>
              <input
                className={baseInput}
                value={config.input_key || ''}
                onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, input_key: e.target.value })}
                placeholder="如：topic, question"
              />
            </div>
            <div>
              <label className={labelClass}>默认值</label>
              <input
                className={baseInput}
                value={config.default_value || ''}
                onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, default_value: e.target.value })}
                placeholder="当未提供输入时使用的默认值"
              />
            </div>
          </>
        )}

        {data.nodeType === 'output' && (
          <>
            <div>
              <label className={labelClass}>输出键名</label>
              <input
                className={baseInput}
                value={config.output_key || ''}
                onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, output_key: e.target.value })}
                placeholder="如：result, answer"
              />
            </div>
            <div>
              <label className={labelClass}>输出描述</label>
              <input
                className={baseInput}
                value={config.description || ''}
                onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, description: e.target.value })}
                placeholder="描述这个输出的用途"
              />
            </div>
          </>
        )}

        {data.nodeType === 'condition' && (
          <>
            <div>
              <label className={labelClass}>条件表达式</label>
              <textarea
                className="h-20 w-full rounded-md border bg-gray-50 px-3 py-2 font-mono text-xs focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                value={config.expression || ''}
                onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, expression: e.target.value })}
                placeholder="inputs.get('value', 0) > 0"
              />
              <p className="mt-1 text-[10px] text-gray-400">使用 inputs 变量，支持比较和逻辑运算</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className={labelClass}>真分支节点</label>
                <input
                  className={baseInput}
                  value={config.true_branch || ''}
                  onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, true_branch: e.target.value })}
                  placeholder="节点 ID"
                />
              </div>
              <div>
                <label className={labelClass}>假分支节点</label>
                <input
                  className={baseInput}
                  value={config.false_branch || ''}
                  onChange={(e) => updateNodeConfig(selectedNode.id, { ...config, false_branch: e.target.value })}
                  placeholder="节点 ID"
                />
              </div>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      {!readOnly && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">添加节点:</span>
          {nodeTypeOptions.map((type) => {
            const meta = nodeTypeMeta[type];
            const Icon = meta.icon;
            return (
              <DropdownMenu key={type}>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5 border-2" style={{ borderColor: `${meta.color}40` }}>
                    <Icon className="size-3.5" style={{ color: meta.color }} />
                    {meta.label}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuItem onClick={() => handleAddNode(type)}>
                    <div className="flex flex-col">
                      <span className="font-medium">添加 {meta.label} 节点</span>
                      <span className="text-xs text-gray-500">{meta.description}</span>
                    </div>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            );
          })}
          <div className="ml-auto flex gap-2">
            {selectedNode && (
              <Button variant="destructive" size="sm" onClick={handleDeleteSelected}>
                <Trash2Icon className="size-4" /> 删除节点
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={handleSave}>
              <SaveIcon className="size-4" /> 保存
            </Button>
            {onExecute && (
              <Button size="sm" onClick={handleExecute} className="bg-green-600 hover:bg-green-700">
                <PlayIcon className="size-4" /> 执行
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Main layout */}
      <div className="flex gap-4">
        {/* Canvas */}
        <div
          ref={reactFlowWrapper}
          className="flex-1 overflow-hidden rounded-xl border-2 bg-gradient-to-br from-gray-50 to-white"
          style={{ height }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange as (changes: NodeChange[]) => void}
            onEdgesChange={onEdgesChange as (changes: EdgeChange[]) => void}
            onConnect={onConnect}
            onInit={() => fitView({ maxZoom: 1.5 })}
            onNodeClick={(_, node) => {
              setSelectedNode(node as Node<WorkflowNodeData>);
              setConfigOpen(true);
            }}
            onPaneClick={() => setSelectedNode(null)}
            nodeTypes={nodeTypesConfig}
            onDrop={onDrop}
            onDragOver={onDragOver}
            fitView
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{
              type: 'smoothstep',
              style: { strokeWidth: 2, stroke: '#94a3b8' },
            }}
          >
            <Background gap={20} size={1} color="#e5e7eb" />
            <Controls className="!bg-white !border-gray-200 !shadow-md" />
            <MiniMap
              nodeStrokeWidth={3}
              className="!bg-white !border-gray-200 !shadow-md"
              style={{ backgroundColor: '#f8fafc' }}
            />
          </ReactFlow>
        </div>

        {/* Right side panel — tabs: 节点配置 / 执行历史 */}
        {!readOnly && (
          <div
            className="w-80 shrink-0 rounded-xl border-2 bg-white shadow-lg transition-all"
            style={{ height }}
          >
            {/* Tab strip */}
            <div className="flex items-center justify-between border-b border-gray-200 px-3 py-2">
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => setRightTab('config')}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    rightTab === 'config'
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-500 hover:bg-gray-100'
                  }`}
                >
                  <Settings2Icon className="size-3.5" />
                  节点配置
                  {selectedNode && rightTab !== 'config' && (
                    <span
                      className="ml-1 rounded-full px-1.5 py-0.5 text-[10px] text-white"
                      style={{
                        backgroundColor: nodeTypeMeta[selectedNode.data.nodeType].color,
                      }}
                    >
                      {nodeTypeMeta[selectedNode.data.nodeType].label}
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => setRightTab('execution')}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    rightTab === 'execution'
                      ? 'bg-yellow-50 text-yellow-700'
                      : 'text-gray-500 hover:bg-gray-100'
                  }`}
                >
                  <PlayIcon className="size-3.5" />
                  执行
                  {isExecuting && (
                    <span className="ml-1 inline-flex size-2 animate-pulse rounded-full bg-yellow-500" />
                  )}
                  {executionEvents.length > 0 && !isExecuting && (
                    <span className="ml-1 rounded-full bg-gray-200 px-1.5 py-0.5 text-[10px] tabular-nums">
                      {executionEvents.length}
                    </span>
                  )}
                </button>
              </div>
              {(rightTab === 'execution' && (executionEvents.length > 0 || executionError)) && (
                <button
                  type="button"
                  onClick={() => {
                    setExecutionEvents([]);
                    setExecutionError(null);
                  }}
                  className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  title="清空执行历史"
                >
                  <Trash2Icon className="size-3.5" />
                </button>
              )}
            </div>

            {/* Tab content */}
            <div className="overflow-y-auto p-4" style={{ height: 'calc(100% - 49px)' }}>
              {rightTab === 'config' && (
                <>
                  {selectedNode ? (
                    renderNodeConfig()
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center text-center text-gray-400">
                      <Settings2Icon className="mb-3 size-10 opacity-30" />
                      <p className="text-sm">点击节点进行配置</p>
                      <p className="mt-1 text-xs text-gray-300">或从上方添加新节点</p>
                    </div>
                  )}
                </>
              )}
              {rightTab === 'execution' && (
                <ExecutionLogPanel
                  isExecuting={isExecuting}
                  events={executionEvents}
                  error={executionError}
                  onJumpToConfig={() => {
                    setRightTab('config');
                    setConfigOpen(true);
                  }}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Right-panel tab that shows real-time workflow execution log.
 * Each SSE event is rendered as a card with its event type, status icon,
 * and a JSON dump of the data payload.
 */
function ExecutionLogPanel({
  isExecuting,
  events,
  error,
  onJumpToConfig,
}: {
  isExecuting: boolean;
  events: ExecutionEvent[];
  error: string | null;
  onJumpToConfig: () => void;
}) {
  if (error) {
    return (
      <div className="space-y-2">
        <div className="flex items-start gap-2 rounded border border-red-200 bg-red-50 p-3">
          <span className="mt-0.5 text-red-500">⚠</span>
          <div className="flex-1">
            <p className="text-xs font-semibold text-red-700">执行出错</p>
            <p className="mt-1 text-xs text-red-600 break-words">{error}</p>
          </div>
        </div>
        {events.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] font-medium text-gray-400">之前的执行步骤:</p>
            {events.map((e, idx) => (
              <ExecutionEventCard key={idx} event={e} onJumpToConfig={onJumpToConfig} />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (events.length === 0 && !isExecuting) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center text-gray-400">
        <PlayIcon className="mb-3 size-10 opacity-30" />
        <p className="text-sm">尚未执行工作流</p>
        <p className="mt-1 text-xs text-gray-300">点击上方"执行"按钮开始</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {isExecuting && events.length === 0 && (
        <div className="flex items-center gap-2 rounded border border-yellow-200 bg-yellow-50 p-3 text-xs text-yellow-700">
          <span className="inline-flex size-3 animate-spin rounded-full border-2 border-yellow-500 border-t-transparent" />
          正在启动工作流执行...
        </div>
      )}
      {events.map((e, idx) => (
        <ExecutionEventCard key={idx} event={e} onJumpToConfig={onJumpToConfig} />
      ))}
    </div>
  );
}

/**
 * Render a single SSE event with an icon based on its event type.
 */
function ExecutionEventCard({
  event,
  onJumpToConfig,
}: {
  event: ExecutionEvent;
  onJumpToConfig: () => void;
}) {
  const eventType = event.event;
  const data = event.data;

  // Visual style based on event type
  let icon = '📨';
  let label = eventType;
  let colorClass = 'border-gray-200 bg-gray-50';
  let labelClass = 'text-gray-700';

  if (eventType.includes('started')) {
    icon = '▶️';
    colorClass = 'border-blue-200 bg-blue-50';
    labelClass = 'text-blue-700';
  } else if (eventType.includes('completed') && !eventType.includes('error')) {
    icon = '✅';
    colorClass = 'border-green-200 bg-green-50';
    labelClass = 'text-green-700';
  } else if (eventType.includes('failed') || eventType.includes('error')) {
    icon = '❌';
    colorClass = 'border-red-200 bg-red-50';
    labelClass = 'text-red-700';
  } else if (eventType === 'workflow_started' || eventType === 'workflow_completed') {
    icon = eventType === 'workflow_completed' ? '🎉' : '🚀';
    colorClass = 'border-purple-200 bg-purple-50';
    labelClass = 'text-purple-700';
  }

  // Pull out the most informative bits
  const nodeId = (data.node_id as string | undefined) ?? '';
  const duration = (data.duration_ms as number | undefined) ?? null;
  const step = (data.step as number | undefined) ?? null;
  const total = (data.total_steps as number | undefined) ?? null;

  // For node_completed, show output preview
  let outputPreview: string | null = null;
  if (eventType.includes('node_completed')) {
    const output = data.output as Record<string, unknown> | undefined;
    if (output && typeof output === 'object') {
      const response = (output.response as string | undefined) ?? '';
      const codeResult = (output.code_result as string | undefined) ?? '';
      const text = response || codeResult || '';
      if (text) {
        outputPreview = text.length > 200 ? text.slice(0, 200) + '...' : text;
      }
    }
  }

  return (
    <div className={`rounded-md border ${colorClass} p-2 text-xs`}>
      <div className={`flex items-center gap-2 font-semibold ${labelClass}`}>
        <span>{icon}</span>
        <span className="flex-1 truncate">{label}</span>
        {duration != null && (
          <span className="rounded bg-white/60 px-1.5 py-0.5 text-[10px] tabular-nums">
            {duration}ms
          </span>
        )}
        {step != null && total != null && (
          <span className="rounded bg-white/60 px-1.5 py-0.5 text-[10px] tabular-nums">
            {step}/{total}
          </span>
        )}
      </div>
      {nodeId && (
        <p className="mt-0.5 truncate font-mono text-[10px] text-gray-500">
          node: {nodeId}
        </p>
      )}
      {outputPreview && (
        <p className="mt-1 whitespace-pre-wrap break-words text-[11px] text-gray-700">
          {outputPreview}
        </p>
      )}
      {!outputPreview && (
        <details className="mt-1">
          <summary className="cursor-pointer text-[10px] text-gray-400 hover:text-gray-600">
            查看详情
          </summary>
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-white/60 p-1.5 font-mono text-[10px] text-gray-600">
            {JSON.stringify(data, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

export function WorkflowCanvas(props: WorkflowCanvasProps) {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}