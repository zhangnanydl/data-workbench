const DEFAULTS = {
  startX: 48,
  startY: 72,
  horizontalSpacing: 220,
  verticalSpacing: 158,
};

export function layoutPipelineNodes(nodes, edges, options = {}) {
  if (!nodes.length) return [];
  const settings = { ...DEFAULTS, ...options };
  const ids = new Set(nodes.map((node) => node.id));
  const incoming = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, []]));

  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target) || edge.source === edge.target) continue;
    outgoing.get(edge.source).push(edge.target);
    incoming.set(edge.target, incoming.get(edge.target) + 1);
  }

  const depth = new Map();
  const queue = nodes.filter((node) => incoming.get(node.id) === 0).map((node) => node.id);
  queue.forEach((id) => depth.set(id, 0));
  for (let index = 0; index < queue.length; index += 1) {
    const id = queue[index];
    for (const target of outgoing.get(id)) {
      depth.set(target, Math.max(depth.get(target) ?? 0, (depth.get(id) ?? 0) + 1));
      incoming.set(target, incoming.get(target) - 1);
      if (incoming.get(target) === 0) queue.push(target);
    }
  }

  let overflowDepth = Math.max(0, ...depth.values()) + 1;
  for (const node of nodes) {
    if (!depth.has(node.id)) depth.set(node.id, overflowDepth++);
  }

  const layers = new Map();
  for (const node of nodes) {
    const layer = depth.get(node.id);
    if (!layers.has(layer)) layers.set(layer, []);
    layers.get(layer).push(node.id);
  }

  const positions = new Map();
  for (const [layer, nodeIds] of layers) {
    const offset = ((nodeIds.length - 1) * settings.verticalSpacing) / 2;
    nodeIds.forEach((id, index) => positions.set(id, {
      x: settings.startX + layer * settings.horizontalSpacing,
      y: settings.startY + index * settings.verticalSpacing - offset,
    }));
  }
  return nodes.map((node) => ({ ...node, position: positions.get(node.id) }));
}
