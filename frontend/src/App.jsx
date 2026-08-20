import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import {
  ArrowCounterClockwise,
  ArrowsOutSimple,
  CaretDown,
  CheckCircle,
  DotsThree,
  FloppyDisk,
  GearSix,
  MagicWand,
  Plus,
  Play,
  Trash,
  X,
} from "@phosphor-icons/react";
import { initialEdges, initialNodes } from "./data/defaultPipeline.js";
import { bridge, fallbackPlugins } from "./lib/bridge.js";
import { connectionFromNodeDrop } from "./lib/connections.js";
import { layoutPipelineNodes } from "./lib/layout.js";
import { createAutomaticProject, createPluginNode } from "./lib/projects.js";
import { appendCanvasHistory, createCanvasSnapshot } from "./lib/history.js";
import { pluginNeedsUpstreamFields, upstreamSchemaKey } from "./lib/preview.js";
import { Icon } from "./components/Icon.jsx";
import { ModuleLibrary } from "./components/ModuleLibrary.jsx";
import { PluginNode } from "./components/PluginNode.jsx";
import { Inspector } from "./components/Inspector.jsx";
import { PreviewTable } from "./components/PreviewTable.jsx";
import { RunProgress } from "./components/RunProgress.jsx";
import { StorageSettings } from "./components/StorageSettings.jsx";
import appLogo from "./assets/data-workbench-logo.png";

const nodeTypes = { plugin: PluginNode };

function buildPipeline(nodes, edges) {
  return {
    version: 1,
    name: "访问日志清洗_20260819",
    nodes: nodes.map((node) => ({ id: node.id, pluginId: node.data.pluginId, label: node.data.label, config: node.data.config, position: node.position })),
    edges: edges.map(({ id, source, target }) => ({ id, source, target })),
  };
}

function hydratePipeline(pipeline, pluginMap) {
  return {
    nodes: (pipeline.nodes || []).map((node) => ({
      id: node.id,
      type: "plugin",
      position: node.position || { x: 80, y: 100 },
      data: { pluginId: node.pluginId, label: node.label, config: node.config || {}, plugin: pluginMap.get(node.pluginId) },
    })),
    edges: (pipeline.edges || []).map((edge) => ({ ...edge, type: "smoothstep", style: { stroke: "#8390a3", strokeWidth: 1.6 } })),
  };
}

const starterProjects = [
  { id: "access-log", name: "access_log_pipeline", meta: "更新于 2026-08-19 10:30", pipeline: buildPipeline(initialNodes, initialEdges) },
  { id: "network", name: "network_analysis", meta: "更新于 2026-08-18 16:20", pipeline: buildPipeline(initialNodes, initialEdges) },
  { id: "payment", name: "payment_etl", meta: "更新于 2026-08-18 09:15", pipeline: buildPipeline(initialNodes, initialEdges) },
];

function Workbench() {
  const [plugins, setPlugins] = useState(fallbackPlugins);
  const pluginMap = useMemo(() => new Map(plugins.map((plugin) => [plugin.id, plugin])), [plugins]);
  const decorate = useCallback((items) => items.map((node) => ({ ...node, data: { ...node.data, plugin: pluginMap.get(node.data.pluginId) } })), [pluginMap]);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [preview, setPreview] = useState(null);
  const [inputPreview, setInputPreview] = useState(null);
  const [availableColumns, setAvailableColumns] = useState([]);
  const [previewError, setPreviewError] = useState("");
  const [inputPreviewError, setInputPreviewError] = useState("");
  const [previewMode, setPreviewMode] = useState("output");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewPage, setPreviewPage] = useState(1);
  const [previewPageSize, setPreviewPageSize] = useState(100);
  const [pcapMode, setPcapMode] = useState("packets");
  const [livePreview, setLivePreview] = useState(true);
  const [runState, setRunState] = useState("idle");
  const [runProgress, setRunProgress] = useState(null);
  const [toast, setToast] = useState("");
  const [projects, setProjects] = useState(starterProjects);
  const [activeProjectId, setActiveProjectId] = useState(null);
  const [projectSwitcherOpen, setProjectSwitcherOpen] = useState(false);
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [clearCanvasOpen, setClearCanvasOpen] = useState(false);
  const [historyCount, setHistoryCount] = useState(0);
  const reactFlow = useReactFlow();
  const reactFlowWrapper = useRef(null);
  const previewRequestId = useRef(0);
  const previewInFlight = useRef(false);
  const previewQueued = useRef(false);
  const previewState = useRef(null);
  const upstreamSchemaCache = useRef({ key: "", preview: null });
  const connectionStart = useRef(null);
  const connectionCompleted = useRef(false);
  const canvasState = useRef({ nodes: [], edges: [], selectedNodeId: null });
  const history = useRef([]);
  const configHistoryTimer = useRef(null);
  const configHistoryOpen = useRef(false);
  const runPollToken = useRef(0);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId);
  const selectedPlugin = selectedNode ? pluginMap.get(selectedNode.data.pluginId) : null;
  const activeProject = projects.find((project) => project.id === activeProjectId);
  const flowEdges = useMemo(() => {
    const running = runState === "running";
    const color = running ? "#3978f6" : "#8390a3";
    return edges.map((edge) => ({
      ...edge,
      animated: running,
      className: `${edge.className || ""} ${running ? "is-data-flowing" : ""}`.trim(),
      markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15, color },
    }));
  }, [edges, runState]);
  canvasState.current = { nodes, edges, selectedNodeId };
  previewState.current = { nodes, edges, selectedNodeId, selectedPlugin, previewPage, previewPageSize, pcapMode };

  useEffect(() => {
    setPreviewPage(1);
    setPcapMode("packets");
    setPreviewMode("output");
    setInputPreview(null);
    setInputPreviewError("");
  }, [selectedNodeId]);

  useEffect(() => {
    let active = true;
    bridge.listPlugins().then((items) => {
      if (active && items?.length) setPlugins(items);
    });
    return () => { active = false; };
  }, []);

  const reloadStoredProjects = useCallback(async () => {
    try {
      const items = await bridge.listProjects();
      const names = new Set(starterProjects.map((project) => project.name));
      const saved = (items || []).filter((item) => !names.has(item.name)).map((item) => ({ id: `saved-${item.name}`, name: item.name, meta: item.path?.startsWith("mysql:") ? "数据库已保存" : "本地已保存", path: item.path, pipeline: null }));
      setProjects([...starterProjects, ...saved]);
    } catch (error) {
      setToast(`读取项目失败：${error?.message || error}`);
    }
  }, []);

  useEffect(() => { reloadStoredProjects(); }, [reloadStoredProjects]);

  useEffect(() => {
    setNodes((current) => decorate(current));
  }, [decorate, setNodes]);

  const refreshPreview = useCallback(async () => {
    if (!previewState.current?.selectedNodeId) return;
    if (previewInFlight.current) {
      previewQueued.current = true;
      return;
    }
    previewInFlight.current = true;
    setPreviewLoading(true);
    try {
      do {
        previewQueued.current = false;
        const state = previewState.current;
        if (!state?.selectedNodeId) break;
        const requestId = ++previewRequestId.current;
        const pipeline = buildPipeline(state.nodes, state.edges);
        setPreviewError("");

        if (state.selectedPlugin?.id === "input.pcap") {
          const currentNode = state.nodes.find((node) => node.id === state.selectedNodeId);
          const path = String(currentNode?.data?.config?.path || "").trim();
          if (!path) {
            setPreview(null);
            setAvailableColumns([]);
            setPreviewError("请先选择 PCAP / PCAPNG 文件");
            continue;
          }
          const result = state.pcapMode === "sessions"
            ? await bridge.pcapSessions(path, state.previewPage, state.previewPageSize)
            : await bridge.pcapPage(path, state.previewPage, state.previewPageSize, currentNode?.data?.config?.display_filter || "");
          if (requestId !== previewRequestId.current) continue;
          if (result.ok) {
            setPreview(result.data);
            setInputPreview(result.data);
            setAvailableColumns(result.data?.columns || []);
            setPreviewError("");
          } else {
            setPreview(null);
            setAvailableColumns([]);
            setPreviewError(result.error || "PCAP 索引读取失败");
          }
          continue;
        }

        const needsFields = pluginNeedsUpstreamFields(state.selectedPlugin);
        const schemaKey = needsFields ? `${upstreamSchemaKey(pipeline, state.selectedNodeId)}|page:${state.previewPage}|size:${state.previewPageSize}` : "";
        const cachedInput = needsFields && upstreamSchemaCache.current.key === schemaKey ? upstreamSchemaCache.current.preview : null;
        const inputPromise = cachedInput ? Promise.resolve({ ok: true, data: cachedInput }) : bridge.previewNodeInput(pipeline, state.selectedNodeId, state.previewPageSize, state.previewPage);
        const [inputResult, result] = await Promise.all([inputPromise, bridge.previewPipeline(pipeline, state.selectedNodeId, state.previewPageSize, state.previewPage)]);
        if (requestId !== previewRequestId.current) continue;
        const upstreamPreview = inputResult.ok ? inputResult.data : null;
        if (needsFields && inputResult.ok && !cachedInput) upstreamSchemaCache.current = { key: schemaKey, preview: upstreamPreview };
        setInputPreview(upstreamPreview);
        setInputPreviewError(inputResult?.ok ? "" : inputResult?.error || "输入数据读取失败");
        setAvailableColumns(needsFields ? upstreamPreview?.columns || [] : []);
        if (result.ok) {
          setPreview(result.data);
          setPreviewError("");
        } else {
          setPreview(null);
          setPreviewError(result.error || "预览失败");
        }
      } while (previewQueued.current);
    } finally {
      previewInFlight.current = false;
      setPreviewLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!livePreview || !selectedNodeId) return undefined;
    const timer = setTimeout(refreshPreview, 420);
    return () => clearTimeout(timer);
  }, [livePreview, refreshPreview, selectedNodeId, nodes, edges, previewPage, previewPageSize, pcapMode]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(""), 2600);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => () => clearTimeout(configHistoryTimer.current), []);
  useEffect(() => () => { runPollToken.current += 1; }, []);

  const resetHistory = useCallback(() => {
    history.current = [];
    configHistoryOpen.current = false;
    clearTimeout(configHistoryTimer.current);
    setHistoryCount(0);
  }, []);

  const recordHistory = useCallback(() => {
    const current = canvasState.current;
    history.current = appendCanvasHistory(history.current, createCanvasSnapshot(current.nodes, current.edges, current.selectedNodeId));
    setHistoryCount(history.current.length);
  }, []);

  const recordGroupedConfigHistory = useCallback(() => {
    if (!configHistoryOpen.current) recordHistory();
    configHistoryOpen.current = true;
    clearTimeout(configHistoryTimer.current);
    configHistoryTimer.current = setTimeout(() => { configHistoryOpen.current = false; }, 650);
  }, [recordHistory]);

  const undoCanvas = useCallback(() => {
    const snapshot = history.current.pop();
    if (!snapshot) return;
    configHistoryOpen.current = false;
    clearTimeout(configHistoryTimer.current);
    setNodes(snapshot.nodes);
    setEdges(snapshot.edges);
    setSelectedNodeId(snapshot.nodes.some((node) => node.id === snapshot.selectedNodeId) ? snapshot.selectedNodeId : null);
    setPreview(null);
    setInputPreview(null);
    setHistoryCount(history.current.length);
    setToast("已撤销上一步操作");
  }, [setEdges, setNodes]);

  const handleNodesChange = useCallback((changes) => {
    if (changes.some((change) => change.type === "remove")) recordHistory();
    onNodesChange(changes);
  }, [onNodesChange, recordHistory]);

  const handleEdgesChange = useCallback((changes) => {
    if (changes.some((change) => change.type === "remove")) recordHistory();
    onEdgesChange(changes);
  }, [onEdgesChange, recordHistory]);

  const appendConnection = useCallback((connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return false;
    const duplicate = canvasState.current.edges.some((edge) => edge.source === connection.source && edge.target === connection.target);
    if (duplicate) return false;
    recordHistory();
    setEdges((current) => {
      return addEdge({ ...connection, type: "smoothstep", style: { stroke: "#8390a3", strokeWidth: 1.6 } }, current);
    });
    return true;
  }, [recordHistory, setEdges]);

  const onConnect = useCallback((connection) => {
    connectionCompleted.current = true;
    appendConnection(connection);
  }, [appendConnection]);

  const onConnectStart = useCallback((_, params) => {
    connectionStart.current = { nodeId: params.nodeId, handleType: params.handleType };
    connectionCompleted.current = false;
  }, []);

  const onConnectEnd = useCallback((event) => {
    const start = connectionStart.current;
    connectionStart.current = null;
    if (!start || connectionCompleted.current) {
      connectionCompleted.current = false;
      return;
    }
    connectionCompleted.current = false;
    const point = "changedTouches" in event ? event.changedTouches[0] : event;
    const droppedElement = document.elementFromPoint(point.clientX, point.clientY);
    const droppedNodeId = droppedElement?.closest?.(".react-flow__node")?.dataset?.id;
    if (!droppedNodeId || droppedNodeId === start.nodeId) return;
    const connection = connectionFromNodeDrop(start, droppedNodeId);
    if (connection && appendConnection(connection)) setToast("已自动连接到节点");
  }, [appendConnection]);

  const addPlugin = useCallback((plugin, position) => {
    if (!plugin) return;
    const now = Date.now();
    const node = createPluginNode(plugin, position, now);
    if (!activeProjectId) {
      const project = createAutomaticProject(node, now);
      setProjects((current) => [...current, project]);
      setActiveProjectId(project.id);
      setNodes([node]);
      setEdges([]);
      setSelectedNodeId(node.id);
      setPreview(null);
      setToast(`已自动创建项目并添加：${plugin.name}`);
      bridge.saveProject(buildPipeline([node], []), project.name).then((result) => {
        if (!result.ok) return;
        setProjects((current) => current.map((item) => item.id === project.id ? { ...item, path: result.path, meta: "已自动保存" } : item));
      });
      resetHistory();
      return;
    }
    recordHistory();
    setNodes((current) => [...current, node]);
    setSelectedNodeId(node.id);
    setToast(`已添加模块：${plugin.name}`);
  }, [activeProjectId, recordHistory, resetHistory, setEdges, setNodes]);

  const onDrop = useCallback((event) => {
    event.preventDefault();
    const pluginId = event.dataTransfer.getData("application/data-workbench-plugin");
    addPlugin(pluginMap.get(pluginId), reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  }, [addPlugin, pluginMap, reactFlow]);

  const addPluginFromLibrary = useCallback((plugin) => {
    addPlugin(plugin, { x: 70 + (nodes.length % 5) * 40, y: 80 + (nodes.length % 4) * 35 });
  }, [addPlugin, nodes.length]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const changeConfig = useCallback((key, value) => {
    recordGroupedConfigHistory();
    setNodes((current) => current.map((node) => node.id === selectedNodeId ? { ...node, data: { ...node.data, config: { ...node.data.config, [key]: value } } } : node));
  }, [recordGroupedConfigHistory, selectedNodeId, setNodes]);

  const removeSelected = useCallback(() => {
    if (!selectedNodeId) return;
    recordHistory();
    setNodes((current) => current.filter((node) => node.id !== selectedNodeId));
    setEdges((current) => current.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId));
    setSelectedNodeId(null);
    setToast("模块已删除");
  }, [recordHistory, selectedNodeId, setEdges, setNodes]);

  const pickFile = useCallback(async (field) => {
    const outputExtension = selectedPlugin?.id === "output.sqlite" ? "sqlite" : selectedNode?.data.config?.format || "csv";
    const result = field.field_type === "save_file" ? await bridge.pickSaveFile(outputExtension) : await bridge.pickFile();
    if (result.ok && result.path) changeConfig(field.key, result.path);
  }, [changeConfig, selectedNode, selectedPlugin]);

  const saveProject = useCallback(async () => {
    if (!activeProjectId || !activeProject) {
      setToast("当前未打开项目");
      return;
    }
    const pipeline = buildPipeline(nodes, edges);
    const projectName = activeProject?.name || "未命名流程";
    setProjects((current) => current.map((project) => project.id === activeProjectId ? { ...project, pipeline, meta: "刚刚保存" } : project));
    const result = await bridge.saveProject(pipeline, projectName);
    if (result.ok) setProjects((current) => current.map((project) => project.id === activeProjectId ? { ...project, path: result.path } : project));
    setToast(result.message || (result.ok ? "项目已保存" : result.error));
  }, [activeProject?.name, activeProjectId, edges, nodes]);

  const switchProject = useCallback(async (project) => {
    const currentPipeline = buildPipeline(nodes, edges);
    setProjects((current) => current.map((item) => item.id === activeProjectId ? { ...item, pipeline: currentPipeline } : item));
    let pipeline = project.pipeline;
    if (!pipeline && project.path) {
      const result = await bridge.loadProject(project.path);
      if (!result.ok) {
        setToast(result.error || "项目加载失败");
        return;
      }
      pipeline = result.data;
    }
    const hydrated = hydratePipeline(pipeline || { nodes: [], edges: [] }, pluginMap);
    setNodes(hydrated.nodes);
    setEdges(hydrated.edges);
    setActiveProjectId(project.id);
    setSelectedNodeId(hydrated.nodes.find((node) => node.data.pluginId.startsWith("transform."))?.id || hydrated.nodes[0]?.id || null);
    resetHistory();
    setToast(`已打开项目：${project.name}`);
  }, [activeProjectId, edges, nodes, pluginMap, resetHistory, setEdges, setNodes]);

  const createProject = useCallback(async () => {
    const name = newProjectName.trim();
    if (!name) return;
    const project = { id: `project-${Date.now()}`, name, meta: "刚刚创建", pipeline: { version: 1, name, nodes: [], edges: [] } };
    const saved = await bridge.saveProject(project.pipeline, name);
    const persistedProject = { ...project, path: saved.path };
    setProjects((current) => [...current.map((item) => item.id === activeProjectId ? { ...item, pipeline: buildPipeline(nodes, edges) } : item), persistedProject]);
    setActiveProjectId(project.id);
    setNodes([]);
    setEdges([]);
    setSelectedNodeId(null);
    setPreview(null);
    resetHistory();
    setNewProjectName("");
    setShowNewProject(false);
    setToast(`已新建项目：${name}`);
  }, [activeProjectId, edges, newProjectName, nodes, resetHistory, setEdges, setNodes]);

  const runPipeline = useCallback(async () => {
    if (!activeProjectId) {
      setToast("请先新建或打开项目");
      return;
    }
    setRunState("running");
    setRunProgress({ status: "queued", percent: 0, nodeCount: nodes.length, strategy: "正在评估数据量" });
    const started = await bridge.startPipelineRun(buildPipeline(nodes, edges));
    if (!started.ok) {
      setRunState("error");
      setRunProgress({ status: "error", percent: 0, error: started.error, nodeCount: nodes.length });
      setToast(started.error || "任务启动失败");
      return;
    }
    const token = ++runPollToken.current;
    setRunProgress(started.job);
    const poll = async () => {
      if (token !== runPollToken.current) return;
      const result = await bridge.getPipelineRun(started.job.jobId);
      if (token !== runPollToken.current) return;
      if (!result.ok) {
        setRunState("error");
        setRunProgress((current) => ({ ...current, status: "error", error: result.error }));
        setToast(result.error || "无法读取运行进度");
        return;
      }
      const job = result.job;
      setRunProgress(job);
      if (job.status === "queued" || job.status === "running") {
        globalThis.setTimeout(poll, 500);
        return;
      }
      const ok = job.status === "success";
      setRunState(ok ? "success" : "error");
      setToast(job.message || job.error || "流程运行结束");
      if (ok && job.result) setPreview(job.result);
      globalThis.setTimeout(() => {
        if (token === runPollToken.current) { setRunState("idle"); setRunProgress(null); }
      }, 3500);
    };
    poll();
  }, [activeProjectId, edges, nodes]);

  const autoLayout = useCallback(() => {
    if (!nodes.length) return;
    recordHistory();
    setNodes((current) => layoutPipelineNodes(current, edges));
    setTimeout(() => reactFlow.fitView({ padding: 0.18, duration: 350 }), 0);
  }, [edges, nodes.length, reactFlow, recordHistory, setNodes]);

  const clearCanvas = useCallback(() => {
    if (!nodes.length && !edges.length) return;
    recordHistory();
    setNodes([]);
    setEdges([]);
    setSelectedNodeId(null);
    setPreview(null);
    setInputPreview(null);
    setClearCanvasOpen(false);
    setToast("画布已清空，可点击撤销恢复");
  }, [edges.length, nodes.length, recordHistory, setEdges, setNodes]);

  return (
    <main className="app-shell">
      <ModuleLibrary plugins={plugins} onAdd={addPluginFromLibrary} />

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-project">
            <span className="topbar-brand"><img src={appLogo} alt="数据工坊 Logo" /><strong>数据工坊</strong></span>
            <button className="project-switch-button" aria-label="切换项目" onClick={() => setProjectSwitcherOpen(true)}>
              <span><small>当前项目</small><strong>{activeProject?.name || "选择或新建项目"}</strong></span><CaretDown size={15} />
            </button>
            {activeProject ? <span className="saved-state"><CheckCircle size={14} weight="fill" />已保存</span> : null}
          </div>
          <div className="topbar-actions">
            <button className="text-button history-button" onClick={undoCanvas} disabled={!historyCount} aria-label="撤销" title="撤销上一步"><ArrowCounterClockwise size={16} />撤销</button>
            <button className="text-button clear-canvas-button" onClick={() => setClearCanvasOpen(true)} disabled={!nodes.length && !edges.length} aria-label="清空画布" title="清空画布"><Trash size={16} />清空画布</button>
            <button className="text-button" onClick={autoLayout} disabled={!activeProject}><MagicWand size={16} />自动布局</button>
            <button className={`run-button ${runState}`} onClick={runPipeline} disabled={!activeProject || runState === "running"}><Play size={17} weight="fill" />{runState === "running" ? `${Math.round(runProgress?.percent || 0)}%` : runState === "success" ? "运行成功" : runState === "error" ? "运行失败" : "运行全部"}</button>
            <button className="save-button" onClick={saveProject} disabled={!activeProject}><FloppyDisk size={17} />保存</button>
            <button className="icon-button" aria-label="设置" onClick={() => setSettingsOpen(true)}><GearSix size={18} /></button>
            <button className="icon-button" aria-label="更多"><DotsThree size={20} weight="bold" /></button>
          </div>
        </header>

        <div className="canvas-and-inspector">
          <div className={`flow-canvas ${runState === "running" ? "is-running" : ""}`} ref={reactFlowWrapper}>
            <ReactFlow
              nodes={nodes}
              edges={flowEdges}
              onNodesChange={handleNodesChange}
              onEdgesChange={handleEdgesChange}
              onNodeDragStart={recordHistory}
              onConnect={onConnect}
              onConnectStart={onConnectStart}
              onConnectEnd={onConnectEnd}
              isValidConnection={(connection) => connection.source !== connection.target}
              connectionRadius={48}
              connectOnClick
              onDrop={onDrop}
              onDragOver={onDragOver}
              onNodeClick={(_, node) => setSelectedNodeId(node.id)}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.12 }}
              minZoom={0.4}
              maxZoom={1.6}
              deleteKeyCode={["Backspace", "Delete"]}
              onNodesDelete={(deleted) => deleted.some((node) => node.id === selectedNodeId) && setSelectedNodeId(null)}
              proOptions={{ hideAttribution: true }}
            >
              <Background id="minor-grid" variant={BackgroundVariant.Lines} gap={20} size={0.7} color="#edf1f5" />
              <Background id="major-grid" variant={BackgroundVariant.Lines} gap={100} size={1} color="#dde4ec" />
              <Controls showInteractive={false} className="flow-controls" />
              <div className="canvas-hint">拖拽模块到画布开始处理</div>
              <button className="canvas-expand" onClick={() => reactFlow.fitView({ padding: 0.12, duration: 300 })}><ArrowsOutSimple size={16} />适应画布</button>
            </ReactFlow>
            <RunProgress progress={runProgress} />
          </div>
          <Inspector
            node={selectedNode}
            plugin={selectedPlugin}
            columns={availableColumns}
            onConfigChange={changeConfig}
            onDelete={removeSelected}
            onPickFile={pickFile}
            livePreview={livePreview}
            onLivePreviewChange={setLivePreview}
          />
        </div>
        <PreviewTable preview={previewMode === "input" ? inputPreview : preview} loading={previewLoading} error={previewMode === "input" ? inputPreviewError : previewError} onRefresh={refreshPreview} page={previewPage} pageSize={previewPageSize} onPageChange={setPreviewPage} onPageSizeChange={(size) => { setPreviewPageSize(size); setPreviewPage(1); }} pcapMode={selectedPlugin?.id === "input.pcap" ? pcapMode : null} onPcapModeChange={(mode) => { setPcapMode(mode); setPreviewPage(1); }} previewMode={previewMode} onPreviewModeChange={setPreviewMode} />
      </section>
      {projectSwitcherOpen ? <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setProjectSwitcherOpen(false)}><section className="simple-modal project-switch-modal"><header><div><span>数据工坊</span><h2>切换项目</h2></div><button onClick={() => setProjectSwitcherOpen(false)} aria-label="关闭"><X size={18} /></button></header><p>项目已包含原来的任务流程和运行记录，不再单独显示任务导航。</p><div className="project-switch-list">{projects.map((project) => <button className={project.id === activeProjectId ? "is-active" : ""} onClick={async () => { await switchProject(project); setProjectSwitcherOpen(false); }} key={project.id}><Icon name="file-text" size={18} /><span><strong>{project.name}</strong><small>{project.meta}</small></span>{project.id === activeProjectId ? <CheckCircle size={17} weight="fill" /> : null}</button>)}</div><footer><button onClick={() => { setProjectSwitcherOpen(false); setSettingsOpen(true); }}><GearSix size={16} />设置</button><button className="primary" onClick={() => { setProjectSwitcherOpen(false); setShowNewProject(true); }}><Plus size={16} />新建项目</button></footer></section></div> : null}
      {showNewProject ? <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setShowNewProject(false)}><section className="simple-modal"><header><div><span>项目</span><h2>新建数据处理项目</h2></div><button onClick={() => setShowNewProject(false)} aria-label="关闭"><X size={18} /></button></header><p>输入一个容易识别的名称。创建后，从模块库拖入数据源即可开始。</p><label><span>项目名称</span><input autoFocus value={newProjectName} onChange={(event) => setNewProjectName(event.target.value)} onKeyDown={(event) => event.key === "Enter" && createProject()} placeholder="例如：8月访问日志清洗" /></label><footer><button onClick={() => setShowNewProject(false)}>取消</button><button className="primary" disabled={!newProjectName.trim()} onClick={createProject}>创建项目</button></footer></section></div> : null}
      {clearCanvasOpen ? <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setClearCanvasOpen(false)}><section className="simple-modal clear-canvas-modal"><header><div><span>画布操作</span><h2>确定清空当前画布？</h2></div><button onClick={() => setClearCanvasOpen(false)} aria-label="关闭"><X size={18} /></button></header><p>将移除当前项目中的全部节点和连线。清空后仍可立即点击“撤销”恢复。</p><footer><button onClick={() => setClearCanvasOpen(false)}>取消</button><button className="danger-primary" onClick={clearCanvas}><Trash size={16} />确认清空</button></footer></section></div> : null}
      <StorageSettings open={settingsOpen} onClose={() => setSettingsOpen(false)} pluginCount={plugins.length} onSaved={() => { setActiveProjectId(null); setNodes([]); setEdges([]); setSelectedNodeId(null); setPreview(null); resetHistory(); reloadStoredProjects(); }} />
      {toast ? <div className="toast"><CheckCircle size={17} weight="fill" />{toast}</div> : null}
    </main>
  );
}

export function App() {
  return <ReactFlowProvider><Workbench /></ReactFlowProvider>;
}
