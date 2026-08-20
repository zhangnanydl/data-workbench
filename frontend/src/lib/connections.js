export function connectionFromNodeDrop(start, droppedNodeId) {
  if (!start?.nodeId || !droppedNodeId || start.nodeId === droppedNodeId) return null;
  return start.handleType === "target"
    ? { source: droppedNodeId, target: start.nodeId }
    : { source: start.nodeId, target: droppedNodeId };
}
