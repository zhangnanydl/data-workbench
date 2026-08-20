export function connectionFromNodeDrop(start, droppedNodeId) {
  if (!start?.nodeId || !droppedNodeId || start.nodeId === droppedNodeId) return null;
  if (start.handleType === "target") {
    return { source: droppedNodeId, target: start.nodeId, ...(start.handleId ? { targetHandle: start.handleId } : {}) };
  }
  return { source: start.nodeId, target: droppedNodeId, ...(start.handleId ? { sourceHandle: start.handleId } : {}) };
}
