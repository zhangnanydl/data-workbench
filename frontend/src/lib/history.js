const cloneConfig = (config) => JSON.parse(JSON.stringify(config || {}));

export function createCanvasSnapshot(nodes, edges, selectedNodeId = null) {
  return {
    nodes: nodes.map((node) => ({
      ...node,
      position: { ...node.position },
      data: { ...node.data, config: cloneConfig(node.data?.config) },
    })),
    edges: edges.map((edge) => ({ ...edge, style: edge.style ? { ...edge.style } : edge.style })),
    selectedNodeId,
  };
}

export function canvasSnapshotKey(snapshot) {
  return JSON.stringify({
    nodes: snapshot.nodes.map((node) => ({ id: node.id, position: node.position, label: node.data?.label, config: node.data?.config })),
    edges: snapshot.edges.map(({ id, source, target, sourceHandle, targetHandle }) => ({ id, source, target, sourceHandle: sourceHandle || null, targetHandle: targetHandle || null })),
  });
}

export function appendCanvasHistory(history, snapshot, limit = 50) {
  const last = history.at(-1);
  if (last && canvasSnapshotKey(last) === canvasSnapshotKey(snapshot)) return history;
  return [...history, snapshot].slice(-limit);
}
